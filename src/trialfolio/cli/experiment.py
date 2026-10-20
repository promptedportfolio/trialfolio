"""`trialfolio run` of an experiment's configuration (docs/contracts.md, running an experiment;
release 0.3.0), which plans and executes a new experiment, or resumes or revises one.

A directory that isn't empty is resumed when it holds `experiment.lock`, whose lock the store
takes before anything else is read, and holds until the command ends. The installed versions are
checked once it's taken, before the records are read, since the modules that read them import
`p123api`, `requests`, and `urllib3`. From release 0.4.0's R04-T12, the configuration is read by
0.4.0's reader, and the records with `ranking`, so a plan 1.3.0, whose baseline's ranking is a
definition, is planned, resumed, and revised too, and its execution is given the ranking lock's
file.

`ExperimentOutcome` holds what the run has done so far, for its summary.
"""

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, NoReturn

from trialfolio.cli.invocation import Context, Invocation, shown
from trialfolio.cli.steps import (
    definition_bytes,
    plan_approved,
    plan_built,
    provider_client,
    ranking_lock,
    read_credentials,
)
from trialfolio.configuration import ExperimentConfigurationRead
from trialfolio.contracts.attempt import Exchange
from trialfolio.contracts.experiment_configuration import (
    ExperimentConfiguration,
    ExperimentConfigurationV1_1,
    configured_variants,
    configured_variants_v1_1,
)
from trialfolio.contracts.experiment_manifest import (
    ExperimentCommandRecord,
    ExperimentManifestCounts,
)
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.summary import ExperimentCounts, NoCounts, SummaryCase, SummaryIdsV1_2
from trialfolio.errors import TrialFolioError
from trialfolio.planning import Versions, installed_versions
from trialfolio.storage import LOCK_PATH, ArtifactStore

if TYPE_CHECKING:
    from trialfolio.case_state import CaseOutcome
    from trialfolio.contracts.experiment_record import PlanChangesV1_1
    from trialfolio.experiment_approval import ExperimentApproval, ExperimentRun
    from trialfolio.experiment_execution import ExperimentExecution
    from trialfolio.experiment_records import SavedExperiment
    from trialfolio.provider import ScreenBacktestClient


@dataclass
class ExperimentOutcome:
    """What `run` has done so far with an experiment's configuration, for its summary."""

    out: str
    """`--out`, as given."""
    configuration: ExperimentConfiguration | ExperimentConfigurationV1_1
    resume: bool = False
    """Whether the output directory holds the experiment, which the run resumes or revises."""
    experiment: "SavedExperiment | None" = None
    """The experiment's records, once a resume has read and checked them, and found them this
    configuration's experiment's, and not synthetic (running an experiment, step 4)."""
    plan: PlanV1_1 | PlanV1_3 | None = None
    """The plan this run builds, once it's built: the current plan, or its revision."""
    run: "ExperimentRun | None" = None
    execution: "ExperimentExecution | None" = None

    @property
    def counts_known(self) -> bool:
        """Whether the experiment's counts are known: once a new experiment's configuration is
        valid, and once a resumed experiment's records are read and checked."""
        return not self.resume or self.experiment is not None

    def output_dir(self, claimed: str | None) -> str | None:
        """A new experiment's once the command has claimed it. A resumed experiment's once its
        session record is written: the command writes nothing into it before."""
        if not self.resume:
            return claimed
        execution = self.execution
        return None if execution is None or execution.session is None else self.out

    def ids(self) -> SummaryIdsV1_2:
        """The session's number, once its session record is written."""
        execution = self.execution
        if execution is None or execution.session is None:
            return SummaryIdsV1_2()
        return SummaryIdsV1_2(session=execution.session)

    def outputs(self) -> dict[str, str]:
        outputs: dict[str, str] = {}
        ran = self.execution
        if ran is not None and ran.manifest is not None:
            outputs["manifest"] = _session_file(ran.manifest.session, "manifest.json")
        if ran is not None and ran.report is not None:
            outputs["report"] = ran.report.path
        return outputs

    def cases(self) -> tuple[SummaryCase, ...] | None:
        """The experiment's `cases`, once its plan is built: each case of the plan this run
        builds, with its outcome as the records give it, as the command leaves them, and the
        attempt that confirms a repeat of a case awaiting one."""
        plan = self.plan
        if plan is None:
            return None
        execution, run = self.execution, self.run
        outcomes: dict[str, CaseOutcome]
        if execution is not None:
            outcomes = {case.case_id: outcome for case, outcome in execution.outcomes}
            repeats = execution.repeat_attempts
        elif run is not None:
            outcomes = {saved.case.case_id: saved.outcome for saved in run.cases}
            repeats = {
                saved.case.case_id: attempt.attempt_id for saved, attempt in run.awaiting_repeat()
            }
        else:  # Built, and not yet approved: no record read gives it an attempt.
            outcomes, repeats = {}, {}
        return tuple(
            SummaryCase(
                case_key=case.case_key,
                case_id=case.case_id,
                outcome=outcomes.get(case.case_id, "not_yet_run"),
                repeat_attempt_id=repeats.get(case.case_id),
            )
            for case in plan.cases
        )

    def counts(self, error: TrialFolioError | None, warnings: int) -> ExperimentCounts | NoCounts:
        """The experiment's counts, as its manifest counts them: the session's manifest's, once
        it's written, and otherwise as the records give them, over the plan this run builds, or
        the current plan before it's built. `{}` until they're known, and after
        `experiment.locked`, whose run read nothing."""
        if not self.counts_known or (error is not None and error.code == "experiment.locked"):
            return NoCounts()
        execution = self.execution
        if execution is not None:
            return _flattened(execution.counts, execution.metrics_unavailable, warnings)
        saved = self.experiment
        if saved is None:  # a new experiment's, before anything is sent
            return _nothing_sent(self._planned_cases(), warnings)
        plan = saved.current.plan if self.plan is None else self.plan
        return _flattened(saved.counts(plan), saved.metrics_unavailable(plan), warnings)

    def ending_detail(self) -> str | None:
        ran = self.execution
        return ran.ending_detail() if ran is not None and ran.claimed else None

    def records(self, output_dir: str) -> str | None:
        return f"The experiment's records are in {shown(output_dir)}."

    def _planned_cases(self) -> int:
        """How many cases a new experiment plans: its plan's, or, before the plan is built, the
        baseline's and each variant's its configuration gives."""
        if self.plan is not None:
            return len(self.plan.cases)
        configuration = self.configuration
        variants = (
            configured_variants_v1_1(configuration)
            if isinstance(configuration, ExperimentConfigurationV1_1)
            else configured_variants(configuration)
        )
        return len(variants) + 1


def run_experiment(
    invocation: Invocation,
    read: ExperimentConfigurationRead,
    content: bytes,
    started_at: datetime,
) -> TrialFolioError | None:
    """Plans and executes a new experiment, or resumes or revises one, in the order of steps
    docs/contracts.md's running an experiment gives: it opens the output directory, or the lock
    of the experiment in it; loads the resume, or plans a new experiment; obtains the approval;
    builds the executor, and runs it; and maps its ending to the command's."""
    configuration = read.configuration
    invocation.ids["experiment_id"] = configuration.experiment_id
    outcome = ExperimentOutcome(invocation.context.args.out, configuration)
    invocation.outcome = outcome
    store = _opened(invocation, outcome)
    versions = installed_versions()
    plan, changes = _planned(read, store, outcome, versions)
    invocation.ids["plan_hash"] = plan.plan_hash
    plan_built(invocation)
    approved = _approved(invocation, outcome, read, plan, changes)
    client = _session_client(invocation.context, sends=approved.sends)
    execution = _executor(invocation, outcome, approved, plan, store, client, started_at)
    definition, files = definition_bytes(read)
    out = outcome.out
    try:
        error = execution.run(
            content,
            definition=definition,
            snapshot=files,
            on_claimed=lambda: (
                invocation.resuming(out) if outcome.resume else invocation.claimed(out)
            ),
        )
    finally:
        client.close()
    return _ended(invocation, plan, execution, error)


def _opened(invocation: Invocation, outcome: ExperimentOutcome) -> ArtifactStore:
    """The output directory's store, which holds the experiment's lock until the command ends:
    an empty directory's, for a new experiment, or a directory's that holds `experiment.lock`,
    whose lock it takes before anything else is read, for a resume. A directory that holds
    anything else is refused as for a screen."""
    store = invocation.context.store_factory(outcome.out)
    invocation.lock_holder = store
    try:
        store.check_empty()
    except TrialFolioError as occupied:
        if occupied.code != "output.not_empty":
            raise
        # Its counts are unknown until its records are read, whatever stops the run first.
        outcome.resume = True
        try:
            store.lock(LOCK_PATH)
        except FileNotFoundError:
            # Anything else, and no experiment.lock: as for a screen.
            outcome.resume = False
            raise occupied from None
    return store


def _planned(
    read: ExperimentConfigurationRead,
    store: ArtifactStore,
    outcome: ExperimentOutcome,
    versions: Versions,
) -> tuple[PlanV1_1 | PlanV1_3, "PlanChangesV1_1 | None"]:
    """The plan this run builds, and what it changes from the current plan, if it revises it: a
    new experiment's plan, or, once a resume has read and checked the records, and found them
    this configuration's experiment's, and not synthetic, the current plan or its revision."""
    from trialfolio.experiment_records import read_experiment
    from trialfolio.planning import build_experiment_plan_v1_1, plan_revision_v1_1

    if not outcome.resume:
        outcome.plan = build_experiment_plan_v1_1(read, versions)
        return outcome.plan, None
    saved = read_experiment(store, ranking=True)
    if saved.synthetic:
        raise TrialFolioError(
            "output.not_empty",
            "The output directory holds a synthetic experiment, whose values are invented,"
            " and trialfolio run doesn't resume one, so invented and real attempts never share"
            " an experiment. Nothing was sent or written. Run the configuration into another"
            " output directory.",
        )
    revision = plan_revision_v1_1(read, versions, saved.current.plan)
    # Only now are the records this experiment's: a synthetic experiment, or another
    # experiment, in the directory has counts that aren't this configuration's.
    outcome.experiment = saved
    outcome.plan = saved.current.plan if revision is None else revision.plan
    return outcome.plan, None if revision is None else revision.changes


def _approved(
    invocation: Invocation,
    outcome: ExperimentOutcome,
    read: ExperimentConfigurationRead,
    plan: PlanV1_1 | PlanV1_3,
    changes: "PlanChangesV1_1 | None",
) -> "ExperimentApproval":
    """The plan's approval, and the confirmed repeats, once the plan is shown, and the reason and
    each `--repeat` are checked (running an experiment, steps 5 and 6)."""
    from trialfolio.experiment_approval import ExperimentRun, RepeatOption, approve_experiment

    context = invocation.context
    args = context.args
    repeats = tuple(RepeatOption(key, attempt) for key, attempt in args.repeat or ())
    snapshot = None if read.snapshot is None else read.snapshot.record
    run = ExperimentRun(plan, outcome.experiment, changes, args.revision_reason, repeats, snapshot)
    outcome.run = run
    approved = approve_experiment(run, args.approve, stdin=context.stdin, stderr=context.stderr)
    plan_approved(invocation, approved.approval.method)
    return approved


def _executor(
    invocation: Invocation,
    outcome: ExperimentOutcome,
    approved: "ExperimentApproval",
    plan: PlanV1_1 | PlanV1_3,
    store: ArtifactStore,
    client: "ScreenBacktestClient",
    started_at: datetime,
) -> "ExperimentExecution":
    """The session's executor, which sends with `client`, of the approved plan and repeats."""
    from trialfolio.experiment_execution import ExperimentExecution

    context = invocation.context
    args = context.args
    execution = ExperimentExecution(
        plan,
        approved.approval.plan_hash,
        approved.approval.method,
        store,
        client,
        command=ExperimentCommandRecord(
            name="run",
            # No path: one can name the user, and the manifest is in the output directory.
            options={
                "approve": args.approve,
                "json": args.json,
                "revision_reason": args.revision_reason is not None,
                "repeat": bool(args.repeat),
            },
            started_at=started_at,
        ),
        clock=context.clock,
        experiment=outcome.experiment,
        reason=args.revision_reason,
        repeats=approved.repeats,
        ranking_lock=ranking_lock(context, plan),
    )
    outcome.execution = execution
    return execution


def _ended(
    invocation: Invocation,
    plan: PlanV1_1 | PlanV1_3,
    execution: "ExperimentExecution",
    error: TrialFolioError | None,
) -> TrialFolioError | None:
    """The command's error once the session has run: `execution.partial` with the `--repeat`
    option of each case awaiting a repeat, and where the session's report is; or None, when every
    planned case succeeded, with the human summary."""
    out = invocation.context.args.out
    if error is not None and error.code == "execution.partial":
        error = _with_repeat_options(error, plan, execution.repeat_attempts)
        return _with_report(error, out, execution)
    return invocation.ended(error, lambda: _experiment_result(out, plan, execution))


def _session_client(context: Context, *, sends: bool) -> "ScreenBacktestClient":
    """The session's client: Portfolio123's, with the credentials, when a case is due or to be
    repeated, and otherwise one that sends nothing, so a run that sends nothing needs no
    credentials (running an experiment, step 7)."""
    if not sends:
        return _NothingToSend()
    return provider_client(context, read_credentials(context.environ))


class _NothingToSend:
    """The client of a session with no case due or to repeat, which sends nothing."""

    @property
    def authenticated(self) -> bool:
        return False

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        return ()

    def authenticate(self) -> None:
        raise RuntimeError("a session with nothing to send authenticated")

    def screen_backtest(self, params: object) -> NoReturn:
        raise RuntimeError("a session with nothing to send sent a request")

    def rank_update(self, params: object) -> NoReturn:
        raise RuntimeError("a session with nothing to send sent a request")

    def rank_get(self, name: str) -> NoReturn:
        raise RuntimeError("a session with nothing to send sent a request")

    def close(self) -> None:
        pass


def _with_repeat_options(
    error: TrialFolioError, plan: PlanV1_1 | PlanV1_3, repeat_attempts: dict[str, uuid.UUID]
) -> TrialFolioError:
    """`execution.partial`, with the exact `--repeat` option for each case awaiting a repeat."""
    awaiting = [case for case in plan.cases if case.case_id in repeat_attempts]
    if not awaiting:
        return error
    options = "; ".join(
        f"--repeat {case.case_key}:{repeat_attempts[case.case_id]}" for case in awaiting
    )
    each = "the case" if len(awaiting) == 1 else "each case"
    return TrialFolioError(
        error.code,
        f"{error.message} To repeat {each} awaiting a repeat, which may be charged again, run the"
        f" same command with its option: {options}.",
        f"{error.log_message} {len(awaiting)} of the planned cases await a repeat.",
    )


def _with_report(
    error: TrialFolioError, out: str, execution: "ExperimentExecution"
) -> TrialFolioError:
    """`execution.partial`, with where the session's report is, which gives each case's
    attempts. Its loggable message leaves the path out, as a log event's message does."""
    report = execution.report
    if report is None:
        return error
    where = shown(os.path.join(out, report.path))
    return TrialFolioError(
        error.code,
        f"{error.message} Session {execution.session}'s report gives each case's attempts:"
        f" {where}.",
        error.log_message,
    )


def _experiment_result(
    out: str, plan: PlanV1_1 | PlanV1_3, execution: "ExperimentExecution"
) -> list[str]:
    report = execution.report
    lines = [
        f"Experiment completed: {out}",
        f"Session {execution.session}: every one of the {len(plan.cases)} planned cases succeeded.",
    ]
    if report is not None:
        lines.append(f"Report: {os.path.join(out, report.path)}")
    lines += [
        f"Plan hash: {plan.plan_hash}",
        "Statistical validation and trading readiness: not assessed.",
    ]
    return lines


def _session_file(session: int, name: str) -> str:
    return f"sessions/{session}/{name}"


def _flattened(
    counts: ExperimentManifestCounts, metrics_unavailable: int, warnings: int
) -> ExperimentCounts:
    """The JSON summary's counts of an experiment, from the counts its manifest gives, as the
    core counts them, the `unavailable` rows of its planned cases' `metrics.csv`, and the
    warnings this command logged."""
    attempts = counts.attempts
    return ExperimentCounts(
        cases_planned=counts.cases.planned,
        cases_succeeded=counts.cases.succeeded,
        cases_failed=counts.cases.failed,
        cases_skipped=counts.cases.skipped,
        cases_unknown=counts.cases.unknown,
        cases_not_yet_run=counts.cases.not_yet_run,
        cases_retired=counts.retired_cases,
        attempts=sum((attempts.succeeded, attempts.failed, attempts.unknown, attempts.running)),
        repeats=attempts.repeats,
        provider_requests=counts.provider_requests,
        authentication_calls=counts.authentication_calls,
        cost=counts.cost,
        metrics_unavailable=metrics_unavailable,
        warnings=warnings,
    )


def _nothing_sent(planned: int, warnings: int) -> ExperimentCounts:
    """The counts of a new experiment before anything is sent, which no record gives: each of
    its `planned` cases not yet run, and the warnings this command logged."""
    return ExperimentCounts(
        cases_planned=planned,
        cases_succeeded=0,
        cases_failed=0,
        cases_skipped=0,
        cases_unknown=0,
        cases_not_yet_run=planned,
        cases_retired=0,
        attempts=0,
        repeats=0,
        provider_requests=0,
        authentication_calls=0,
        cost=None,
        metrics_unavailable=0,
        warnings=warnings,
    )
