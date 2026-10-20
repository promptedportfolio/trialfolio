"""`trialfolio run`, which runs a configuration by its `kind` (D-24, D-36), and `trialfolio demo`
(docs/contracts.md, approval; release 0.1.0).

`run` plans and executes one screen backtest, once its plan is approved, in the order of steps
docs/contracts.md's approval gives. Given an experiment's configuration, it runs the experiment,
as `trialfolio.cli.experiment` gives. Given a ranking snapshot configuration, it reads the
ranking system the configuration names, with one `rank_get`, into a ranking snapshot, once its
plan is approved (release 0.4.0; ranking snapshot output). From release 0.4.0's R04-T12, it reads
a screen's and an experiment's configuration 1.0.0 or 1.1.0, whose ranking may be a ranking
system's definition, in a file or a snapshot: each case's attempt then writes its definition into
`ApiRankingSystem` with `rank_update`, before its backtest, and the run holds the ranking lock,
on the file `TRIALFOLIO_LOCK_DIR`, `/tmp`, or `%ProgramData%` gives, which the CLI gives the core
(sending a definition, the ranking lock). `demo` takes a screen run's steps over the packaged
synthetic configuration, offline, labeled synthetic.

A screen run's outcome is a `ScreenOutcome`, and a snapshot's a `SnapshotOutcome`: each has one
attempt, which the summary counts.
"""

import argparse
import os
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from trialfolio.approval import obtain_approval
from trialfolio.cli.experiment import run_experiment
from trialfolio.cli.invocation import Invocation, shown
from trialfolio.cli.steps import (
    definition_bytes,
    empty_store,
    ignore_key_log,
    opened,
    plan_approved,
    plan_built,
    provider_client,
    ranking_lock,
    read_credentials,
    read_input,
)
from trialfolio.configuration import (
    ExperimentConfigurationRead,
    ScreenConfigurationRead,
    read_run_configuration,
    read_screen_configuration,
)
from trialfolio.contracts.manifest import CommandRecord
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotPlan, SnapshotCommandRecord
from trialfolio.contracts.ranking_snapshot_configuration import RankingSnapshotConfiguration
from trialfolio.contracts.summary import RunCounts, SummaryCase, SummaryIdsV1_2
from trialfolio.display import visible
from trialfolio.errors import TrialFolioError
from trialfolio.planning import build_plan, build_plan_v1_1, build_snapshot_plan, installed_versions

if TYPE_CHECKING:
    from trialfolio.execution import Execution
    from trialfolio.snapshot_execution import SnapshotExecution


@dataclass
class ScreenOutcome:
    """What `run` of a screen's configuration, or `demo`, has done so far, for its summary: its
    execution, once it has one. `run` has one before it knows the configuration's kind too."""

    execution: "Execution | None" = None

    def output_dir(self, claimed: str | None) -> str | None:
        return claimed

    def ids(self) -> SummaryIdsV1_2:
        return _attempt_id(self.execution)

    def outputs(self) -> dict[str, str]:
        execution = self.execution
        outputs: dict[str, str] = {}
        if execution is None:
            return outputs
        if execution.manifest is not None:
            outputs["manifest"] = execution.manifest.path
        if execution.report is not None:
            outputs["report"] = execution.report.path
        if execution.tables is not None:
            outputs["metrics"] = execution.tables.metrics.path
            outputs["settings"] = execution.tables.settings.path
        return outputs

    def cases(self) -> tuple[SummaryCase, ...] | None:
        return None

    def counts(self, error: TrialFolioError | None, warnings: int) -> RunCounts:
        tables = None if self.execution is None else self.execution.tables
        unavailable = 0 if tables is None else tables.metrics_unavailable
        return _run_counts(self.execution, unavailable, warnings)

    def ending_detail(self) -> str | None:
        return _ending_detail(self.execution)

    def records(self, output_dir: str) -> str | None:
        return f"The run's records are in {shown(output_dir)}."


@dataclass
class SnapshotOutcome:
    """What `run` of a ranking snapshot configuration has done so far, for its summary: its
    execution, once it has one."""

    execution: "SnapshotExecution | None" = None

    def output_dir(self, claimed: str | None) -> str | None:
        return claimed

    def ids(self) -> SummaryIdsV1_2:
        return _attempt_id(self.execution)

    def outputs(self) -> dict[str, str]:
        execution = self.execution
        if execution is None or execution.manifest is None:
            return {}
        return {"manifest": execution.manifest.path}

    def cases(self) -> tuple[SummaryCase, ...] | None:
        return None

    def counts(self, error: TrialFolioError | None, warnings: int) -> RunCounts:
        return _run_counts(self.execution, 0, warnings)

    def ending_detail(self) -> str | None:
        return _ending_detail(self.execution)

    def records(self, output_dir: str) -> str | None:
        return f"The snapshot's records are in {shown(output_dir)}."


def run(invocation: Invocation) -> TrialFolioError | None:
    """Runs a screen's configuration, an experiment's, or a ranking snapshot's, by its `kind`
    (D-24, D-36)."""
    invocation.outcome = ScreenOutcome()
    args = invocation.context.args
    ignore_key_log(invocation.context.environ)
    started_at = opened(invocation)
    content = read_input(args.config)
    # Release 0.4.0's readers, which read 1.0.0 or 1.1.0, and the definition file, or the
    # snapshot, a ranking names, in step 2, before the output directory is checked (R04-T12).
    configuration = read_run_configuration(content, shown(args.config), args.config)
    if isinstance(configuration, ExperimentConfigurationRead):
        return run_experiment(invocation, configuration, content, started_at)
    if isinstance(configuration, RankingSnapshotConfiguration):
        return _run_snapshot(invocation, configuration, content, started_at)
    return _run_screen(invocation, configuration, content, started_at)


def _run_screen(
    invocation: Invocation,
    configuration: ScreenConfigurationRead,
    content: bytes,
    started_at: datetime,
) -> TrialFolioError | None:
    """Plans and executes one screen backtest, once its plan is approved."""
    context = invocation.context
    args = context.args
    store = empty_store(context, args.out)
    plan = _plan(invocation, build_plan_v1_1(configuration, installed_versions()))
    snapshot = configuration.snapshot
    approval = obtain_approval(
        plan,
        args.approve,
        stdin=context.stdin,
        stderr=context.stderr,
        refused=_experiment_options(args),
        snapshot=None if snapshot is None else snapshot.record,
    )
    plan_approved(invocation, approval.method)
    credentials = read_credentials(context.environ)

    from trialfolio.execution import Execution

    execution = Execution(
        plan,
        approval.plan_hash,
        approval.method,
        store,
        CommandRecord(
            name="run",
            # No path: one can name the user, and the manifest is in the output directory.
            options={"approve": args.approve, "json": args.json},
            started_at=started_at,
        ),
        clock=context.clock,
        ranking_lock=ranking_lock(context, plan),
    )
    invocation.outcome = ScreenOutcome(execution)
    definition, files = definition_bytes(configuration)
    error = execution.run(
        content,
        lambda: provider_client(context, credentials),
        definition=definition,
        snapshot=files,
        on_claimed=lambda: invocation.claimed(args.out),
    )
    return invocation.ended(error, lambda: _run_result(args.out, plan, execution, synthetic=False))


def _run_snapshot(
    invocation: Invocation,
    configuration: RankingSnapshotConfiguration,
    content: bytes,
    started_at: datetime,
) -> TrialFolioError | None:
    """Takes a ranking snapshot, as a screen's run takes its steps (ranking snapshot output): the
    output directory must be absent or empty, since a snapshot is never resumed or added to; its
    plan, with its one `rank_get`, is shown and approved; and its execution reads the system with
    the credentials, and writes nothing to the account, so it takes no lock."""
    context = invocation.context
    args = context.args
    store = empty_store(context, args.out)
    plan = build_snapshot_plan(configuration, installed_versions())
    invocation.ids["plan_hash"] = plan.plan_hash
    plan_built(invocation)
    approval = obtain_approval(
        plan,
        args.approve,
        stdin=context.stdin,
        stderr=context.stderr,
        refused=_experiment_options(args, "A ranking snapshot's run"),
    )
    plan_approved(invocation, approval.method)
    credentials = read_credentials(context.environ)

    from trialfolio.snapshot_execution import SnapshotExecution

    execution = SnapshotExecution(
        plan,
        approval.plan_hash,
        approval.method,
        store,
        SnapshotCommandRecord(
            name="run",
            # No path: one can name the user, and the manifest is in the output directory.
            options={"approve": args.approve, "json": args.json},
            started_at=started_at,
        ),
        clock=context.clock,
    )
    invocation.outcome = SnapshotOutcome(execution)
    error = execution.run(
        content,
        lambda: provider_client(context, credentials, snapshot=True),
        on_claimed=lambda: invocation.claimed(args.out),
    )
    return invocation.ended(error, lambda: _snapshot_result(args.out, plan, execution))


def demo(invocation: Invocation) -> TrialFolioError | None:
    """Writes a synthetic example run offline, labeled synthetic, as `run` writes a screen's,
    with its packaged configuration, over a client that opens no connection."""
    invocation.outcome = ScreenOutcome()
    context = invocation.context
    args = context.args
    started_at = opened(invocation)
    store = empty_store(context, args.out)
    versions = installed_versions()

    from trialfolio.demo import (
        CONFIGURATION_NAME,
        SyntheticScreenBacktestClient,
        configuration_bytes,
        response_bytes,
    )
    from trialfolio.execution import Execution

    content = configuration_bytes()
    configuration = read_screen_configuration(content, CONFIGURATION_NAME)
    plan = _plan(invocation, build_plan(configuration, versions))
    execution = Execution(
        plan,
        plan.plan_hash,
        "not_required",
        store,
        CommandRecord(
            name="demo",
            options={"json": args.json},
            started_at=started_at,
        ),
        clock=context.clock,
    )
    invocation.outcome = ScreenOutcome(execution)
    error = execution.run(
        content,
        lambda: SyntheticScreenBacktestClient(response_bytes()),
        on_claimed=lambda: invocation.claimed(args.out),
    )
    return invocation.ended(error, lambda: _run_result(args.out, plan, execution, synthetic=True))


def _plan[P: Plan | PlanV1_2](invocation: Invocation, plan: P) -> P:
    invocation.ids["plan_hash"] = plan.plan_hash
    invocation.ids["case_id"] = plan.cases[0].case_id
    plan_built(invocation)
    return plan


def _experiment_options(args: argparse.Namespace, run: str = "A screen's run") -> str | None:
    """Why a screen's run, or a ranking snapshot's, refuses `--revision-reason` or `--repeat`,
    when either is given: each applies only to an experiment that has run already. `run` names
    the run that refuses them."""
    given = [
        option
        for option, value in (
            ("--revision-reason", args.revision_reason),
            ("--repeat", args.repeat),
        )
        if value
    ]
    if not given:
        return None
    return (
        f"{' and '.join(given)} {'applies' if len(given) == 1 else 'apply'} only to an"
        f" experiment's configuration, run again into its output directory. {run} has no"
        " plan to revise, and no case to repeat. Run the command without"
        f" {'it' if len(given) == 1 else 'them'}."
    )


def _attempt_id(ran: "Execution | SnapshotExecution | None") -> SummaryIdsV1_2:
    """The attempt's ID, once it has written a start record, or its attempt record."""
    attempt = None if ran is None else ran.attempt
    result = None if ran is None else ran.result
    if attempt is not None and (
        _start_records(attempt) or (result is not None and result.recorded)
    ):
        return SummaryIdsV1_2(attempt_id=attempt.attempt_id)
    return SummaryIdsV1_2()


def _run_counts(
    ran: "Execution | SnapshotExecution | None", unavailable: int, warnings: int
) -> RunCounts:
    """The counts of a screen run's, or a snapshot's, one attempt, with the `unavailable` rows
    of its `metrics.csv`, and the warnings this command logged."""
    attempts = sent = 0
    cost: int | None = None
    if ran is not None and ran.attempt is not None:
        from trialfolio.attempts import provider_requests, reported_cost

        result = ran.result
        if result is not None and result.recorded:
            attempts, sent = 1, provider_requests(result.record)
            # Each rank_update's cost too, for a run with a ranking definition.
            cost = reported_cost(result.record)
        elif _start_records(ran.attempt):
            # It reads as running: one possible send for each start record it wrote, its
            # update record and its start record (uncertain completion, counting the
            # requests).
            attempts, sent = 1, _start_records(ran.attempt)
    return RunCounts(
        attempts=attempts,
        provider_requests=sent,
        metrics_unavailable=unavailable,
        warnings=warnings,
        cost=cost,
    )


def _ending_detail(ran: "Execution | SnapshotExecution | None") -> str | None:
    """What the run's records say about the request and the manifest, once it has claimed its
    output directory; None before."""
    if ran is None or not ran.claimed:
        return None
    return ran.ending_detail()


def _start_records(attempt: object) -> int:
    """How many start records a screen run's, or a snapshot's, attempt has written: its update
    record, before a definition's `rank_update`, and its start record, before its request. An
    attempt without its attempt record counts one possible send for each (counting the
    requests)."""
    written = (getattr(attempt, "update_record", None), getattr(attempt, "start_record", None))
    return sum(record is not None for record in written)


def _run_result(
    out: str, plan: Plan | PlanV1_2, execution: "Execution", *, synthetic: bool
) -> list[str]:
    report = execution.report
    lines = (
        [
            (
                f"Synthetic example run written to {out}. Nothing was sent to Portfolio123: every"
                " value is invented."
            )
        ]
        if synthetic
        else [f"Run completed: {out}"]
    )
    if report is not None:
        lines.append(f"Report: {os.path.join(out, report.path)}")
    lines += [
        f"Plan hash: {plan.plan_hash}",
        "Statistical validation and trading readiness: not assessed.",
    ]
    return lines


def _snapshot_result(
    out: str, plan: RankingSnapshotPlan, execution: "SnapshotExecution"
) -> list[str]:
    """Where the snapshot is, the name of the system it read, and whether its definition, ranking
    method, currency, and type can be a ranking, and if not, which rule each breaks. It never
    shows the definition (ranking snapshot output, the result)."""
    record = execution.record
    if record is None:  # a snapshot completes only once its record is written
        raise RuntimeError("a completed snapshot has its record")
    lines = [
        f"Ranking snapshot taken: {out}",
        f"Ranking system read: {visible(record.system.name)}",
    ]
    if execution.problems:
        lines.append(
            "It can't be a ranking: a screen's or an experiment's configuration that named it"
            " would fail, as one names a snapshot"
        )
        lines += [f"- {problem}." for problem in execution.problems]
    else:
        lines.append(
            "Its definition, ranking method, currency, and type can be a ranking: name the"
            " snapshot's directory as ranking.snapshot in a screen's or an experiment's"
            " configuration, schema version 1.1.0."
        )
    lines.append(f"Plan hash: {plan.plan_hash}")
    return lines
