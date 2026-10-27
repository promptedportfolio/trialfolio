"""The executor of an approved experiment plan, in the core: `ExperimentExecution`, which takes
the steps the package lists, in their order (docs/contracts.md, running an experiment, the
executor, and the resume).

It checks its arguments and the authorization before anything is written, takes the ranking lock
when its session sends under a plan 1.3.0, claims a new experiment's directory, and then has the
package's parts take each step: the writer of the session's records, its session record and its
plan; the case runner, the cases; and the manifest's builder, with the report, the session's
end. An ending without a manifest gets its message from `ending`, with what the records say.
"""

import logging
import os
import uuid
from collections.abc import Callable, Sequence

from trialfolio.attempts import Clock, ExperimentAttemptResult, utc_now
from trialfolio.case_state import CaseOutcome
from trialfolio.configuration import read_experiment_configuration_v1_1
from trialfolio.contracts.common import Approval
from trialfolio.contracts.experiment_configuration import ExperimentConfigurationV1_1
from trialfolio.contracts.experiment_manifest import (
    ExperimentCommandRecord,
    ExperimentManifest,
    ExperimentManifestCounts,
    ExperimentManifestV1_1,
)
from trialfolio.contracts.experiment_plan import (
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanV1_1,
    PlanV1_3,
)
from trialfolio.demo import SyntheticScreenBacktestClient
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution.authorization import authorize
from trialfolio.experiment_execution.cases import CaseRunner
from trialfolio.experiment_execution.context import SessionContext
from trialfolio.experiment_execution.ending import (
    MANIFEST_DETAILS,
    attempt_detail,
    before_cases,
    incomplete,
    partial,
)
from trialfolio.experiment_execution.ledger import Ledger
from trialfolio.experiment_execution.manifest import ManifestBuilder
from trialfolio.experiment_execution.progress import (
    Cancellation,
    Progress,
    SessionEnded,
    SessionStarted,
    emit,
)
from trialfolio.experiment_execution.records import CheckedConfiguration, SessionRecords, copies
from trialfolio.experiment_paths import CONFIGURATION, MANIFEST, plan_path, session_path
from trialfolio.experiment_records import SavedExperiment
from trialfolio.experiment_repeats import Repeat
from trialfolio.manifests import EndingWithoutManifest, ManifestFile, utc
from trialfolio.pause import REAL_PAUSE, Pause
from trialfolio.planning import Versions, build_experiment_plan_v1_1
from trialfolio.provider import ScreenBacktestClient
from trialfolio.ranking_lock import RankingLock
from trialfolio.report import ExperimentEvidence, HtmlReportRenderer, write_experiment_report
from trialfolio.snapshots import SnapshotFiles
from trialfolio.storage import LOCK_LINE, LOCK_PATH, ArtifactStore, StoredFile

_logger = logging.getLogger("trialfolio.experiment_execution")


class ExperimentExecution:
    """One execution of an approved experiment plan into the output directory of `store`: a new
    experiment, or, given its records, a resumed one.

    Its properties stay readable whatever happens, so a caller whose execution was interrupted
    still knows what was written: whether the directory was claimed, the session, each attempt,
    and the manifest.
    """

    def __init__(
        self,
        plan: PlanV1_1 | PlanV1_3,
        approved_hash: str,
        approval: Approval,
        store: ArtifactStore,
        client: ScreenBacktestClient,
        *,
        command: ExperimentCommandRecord | None,
        clock: Clock = utc_now,
        progress: Progress | None = None,
        cancellation: Cancellation | None = None,
        experiment: SavedExperiment | None = None,
        reason: str | None = None,
        repeats: Sequence[Repeat] = (),
        ranking_lock: str | os.PathLike[str] | None = None,
        pause: Pause = REAL_PAUSE,
    ) -> None:
        """Writes nothing.

        `approval` is how the plan was approved, as the records give it: `not_required` exactly
        for the demo's client, `SyntheticScreenBacktestClient`, which makes the experiment
        synthetic. `client` sends every request of the session; its caller closes it. `command`
        is the `trialfolio` command that runs the session, or None when the core runs it for
        another interface, and always for a synthetic experiment.

        `experiment` is the experiment's records, which `open_experiment` read from `store`
        while taking its lock, to resume or revise it; None for a new experiment. `plan` is then
        its current plan, which the session resumes, or a revision of it, which `plan_revision`,
        or `plan_revision_v1_1` for an experiment with a ranking definition, built, with its
        `reason`. `repeats` are the confirmed repeats, each checked as repeating a case says.
        `ranking_lock` is the ranking lock's file, given exactly for a plan 1.3.0: a new
        experiment takes it, and a resumed one when its session sends. `pause` is the wait between
        each `rank_update`'s 200 and its backtest, under a plan 1.3.0 (D-45), which tests inject,
        as they do the clock.

        Raises `TrialFolioError`:

        - with `output.not_empty` when the demo's client is given for an experiment that isn't
          synthetic, or another client for one that is;
        - with `plan.approval_required` when a repeat names no case of the plan, a case that
          isn't awaiting a repeat, or an attempt of it that isn't possibly charged, or that
          succeeded with a response that passed validation; when a new experiment is given a
          reason or a repeat; when a resume of the current plan is given a reason, unless it's the
          one the current plan recorded, which resumes it; and unless `approved_hash` is the
          plan's hash, recomputed from its contents (approval);
        - with `plan.changed` when a revision isn't approved by its hash, with a reason.

        Raises `ValueError` when `plan` revises another without the experiment's records, or
        isn't the current plan or a revision of it; when a repeat names a case twice; when the
        reason isn't a valid reason; when `approval` or `command` doesn't fit whether the
        experiment is synthetic; and when `ranking_lock` is given for a plan without a ranking
        definition, or not given for one.
        """
        synthetic = isinstance(client, SyntheticScreenBacktestClient)
        _check_kinds(plan, approval, command, ranking_lock, synthetic=synthetic)
        self._authorization = authorize(
            plan, approved_hash, experiment, synthetic=synthetic, reason=reason, repeats=repeats
        )
        session = 1 if experiment is None else experiment.next_session
        self._context = SessionContext(
            plan, approval, store, clock, synthetic, session, experiment, command
        )
        self._lock = None if ranking_lock is None else RankingLock(ranking_lock)
        self._ledger = Ledger(plan, experiment)
        self._records = SessionRecords(self._context, self._ledger)
        self._cases = CaseRunner(
            self._context,
            self._ledger,
            self._records,
            client,
            self._authorization,
            pause=pause,
            progress=progress,
            cancellation=cancellation,
        )
        self._builder = ManifestBuilder(
            self._context, self._ledger, self._records, self._cases.results
        )
        self._progress = progress
        self._started = False
        self._claimed = False
        self._report: StoredFile | None = None
        self._evidence: ExperimentEvidence | None = None
        self._manifest: ExperimentManifest | ExperimentManifestV1_1 | None = None
        self._manifest_file = ManifestFile(store, session_path(session, MANIFEST), MANIFEST_DETAILS)

    @property
    def claimed(self) -> bool:
        """Whether the output directory was claimed, or, for a resume, whether the run began
        writing into it. Before then, nothing was written."""
        return self._claimed

    @property
    def session(self) -> int | None:
        """The session's number, once its session record is written, or published whole before
        its write failed."""
        return None if self._records.session_record is None else self._context.session

    @property
    def synthetic(self) -> bool:
        return self._context.synthetic

    @property
    def attempts(self) -> tuple[ExperimentAttemptResult, ...]:
        """Each attempt that ended in this session, in order."""
        return tuple(self._cases.results)

    @property
    def outcomes(
        self,
    ) -> tuple[tuple[ExperimentPlanCase | ExperimentPlanCaseV1_3, CaseOutcome], ...]:
        """Each planned case, in the plan's order, with its outcome as the records now give it."""
        cases = self._context.plan.cases
        return tuple((case, self._ledger.outcome(case.case_id)) for case in cases)

    @property
    def repeats_used(self) -> tuple[Repeat, ...]:
        """The confirmed repeats this session doesn't make, because an earlier repeat used their
        confirmation: a later attempt of the case may have reached Portfolio123."""
        return self._authorization.used

    @property
    def repeat_attempts(self) -> dict[str, uuid.UUID]:
        """Each planned case awaiting a repeat, by its `case_id`, with its latest possibly
        charged attempt's `attempt_id`, which confirms a repeat of it (repeating a case)."""
        return self._ledger.repeat_attempts(self._context.plan)

    @property
    def counts(self) -> ExperimentManifestCounts:
        """The experiment's counts, as the session's manifest counts them, over the plan this
        execution runs: the manifest's, once it's written, and otherwise as the records now give
        them, so an interface can report them after an ending without a manifest too."""
        if self._manifest is not None:
            return self._manifest.counts
        return self._builder.counts()

    @property
    def metrics_unavailable(self) -> int:
        """The `unavailable` rows of the planned cases' `metrics.csv` files, as written so far,
        those whose `settings.csv` a failure kept this session from writing included, so the
        count agrees with the records however the session ends."""
        return self._ledger.metrics_unavailable(self._context.plan)

    @property
    def manifest(self) -> ExperimentManifest | ExperimentManifestV1_1 | None:
        """The session's manifest, once it's written: the session is then complete."""
        return self._manifest

    @property
    def report(self) -> StoredFile | None:
        return self._report

    @property
    def evidence(self) -> ExperimentEvidence | None:
        """What the session's report shows, once the report is rendered: an interface can render
        it again, or show it its own way."""
        return self._evidence

    def run(
        self,
        configuration: bytes,
        *,
        definition: bytes | None = None,
        snapshot: SnapshotFiles | None = None,
        on_claimed: Callable[[], object] | None = None,
    ) -> TrialFolioError | None:
        """Takes the steps the package lists. `configuration` is the bytes of the experiment
        configuration the plan was built from, and, for a plan 1.3.0, `definition` the bytes of
        the definition file its baseline names, or `snapshot` those of the two files of the
        snapshot it names, read when it was validated. `on_claimed` is called
        once the directory is claimed, or, for a resume, whose store already holds the lock,
        before the first write, before anything else is written into it, such as to start
        writing logs there.

        Returns the error the caller reports, or None when every planned case succeeded:
        `execution.partial` when the session reached its end with a case that didn't succeed;
        `command.interrupted` or `storage.write_failed` when an interrupt or a storage failure
        ended the session without its manifest; and the attempt's error, such as
        `internal.unexpected`, when an attempt's record wasn't written, which ends the session
        the same way. Raises `ValueError` before writing
        anything when `configuration` doesn't give the plan; for a new experiment, the claim's
        `TrialFolioError`, `output.not_empty`, `experiment.locked`, or `storage.write_failed`,
        and a `KeyboardInterrupt` during the claim, which removes what the claim created, so
        nothing is left; and any unexpected exception, which leaves the session without its
        manifest. A plan 1.3.0's execution takes the ranking lock first, a resumed one's only
        when its session sends, and raises its `TrialFolioError`, `experiment.locked` or
        `storage.write_failed`, before anything is written, and holds it until it ends. A plan
        1.3.0 not given its definition, or its snapshot's files, or given ones that aren't the
        plan's, or another plan given either, is a `ValueError` too.
        """
        if self._started:
            raise RuntimeError("an execution runs once")
        self._started = True
        checked = self._checked(configuration, definition, snapshot)
        if self._lock is None or not self._sends_any():
            return self._run(checked, on_claimed)
        with self._lock:
            return self._run(checked, on_claimed)

    def ending_detail(self) -> str:
        """What the session's records say, for the message of an ending the session didn't
        record itself, such as an unexpected exception: whether the request of the attempt under
        way may have been sent, and whether the session has its manifest."""
        detail = attempt_detail(self._cases.current, self._cases.results)
        return f"{detail} {self._manifest_file.detail}"

    def _checked(
        self, configuration: bytes, definition: bytes | None, snapshot: SnapshotFiles | None
    ) -> CheckedConfiguration:
        """Checks that the configuration gives the plan, and, for a plan 1.3.0, with the
        definition's bytes it's given, or the snapshot's files', which `plans/<n>/definition.xml`
        and `snapshot.json` then hold."""
        plan, records = self._context.plan, self._records
        versions = Versions.of(plan)
        number = (
            records.plan_number if self._authorization.revision is None else records.next_plan()
        )
        source_name = plan_path(number, CONFIGURATION)
        if isinstance(plan, PlanV1_3):
            if (definition is None) == (snapshot is None) or (snapshot is None) != (
                plan.ranking_source.form == "definition"
            ):
                raise ValueError(
                    "an experiment with a ranking definition is given its bytes: its definition"
                    " file's, or its snapshot's files', as its plan's ranking_source gives"
                )
            ranked = read_experiment_configuration_v1_1(
                configuration, source_name, source_name, definition=definition, snapshot=snapshot
            )
            if build_experiment_plan_v1_1(ranked, versions, plan.revises) != plan:
                raise ValueError("the configuration doesn't give the plan")
            version = ranked.configuration.schema_version
            return CheckedConfiguration(
                configuration, copies(definition, snapshot), version, ranked
            )
        if definition is not None or snapshot is not None:
            raise ValueError("only an experiment with a ranking definition is given one")
        # A configuration 1.1.0 whose baseline is ranked by a formula, a name, or an ID gives a
        # plan 1.1.0 too, so release 0.4.0's reader, which reads either version, reads it, and
        # keeps it for its cases' original values (R04-T12).
        read = read_experiment_configuration_v1_1(
            configuration, source_name, source_name, files=False
        )
        if build_experiment_plan_v1_1(read, versions, plan.revises) != plan:
            raise ValueError("the configuration doesn't give the plan")
        kept = read if isinstance(read.configuration, ExperimentConfigurationV1_1) else None
        return CheckedConfiguration(configuration, (), read.configuration.schema_version, kept)

    def _sends_any(self) -> bool:
        """Whether the session will send anything, so it takes the ranking lock: a new
        experiment's always does, and a resumed one's when a case is due, or confirmed to
        repeat, and the remaining budget covers the first one's requests (the ranking lock)."""
        if self._context.experiment is None:
            return True
        return bool(self._cases.to_send()) and self._cases.stop_before(authenticates=True) is None

    def _run(
        self, checked: CheckedConfiguration, on_claimed: Callable[[], object] | None
    ) -> TrialFolioError | None:
        """The steps the package lists, once the ranking lock, if any, is held."""
        context = self._context
        if context.experiment is None:
            context.store.claim(LOCK_PATH, LOCK_LINE, lock=True)
        self._claimed = True
        with EndingWithoutManifest() as ended:
            if on_claimed is not None:
                on_claimed()
            self._write_plan(checked)
        if ended.error is not None:
            return before_cases(ended.error, recorded=self._records.first_plan_recorded())
        _logger.info(
            "Session %d started, under plan %d.",
            context.session,
            self._records.plan_number,
            extra=context.log_fields("experiment.session.started"),
        )
        error: TrialFolioError | None = None  # The session's, once it reaches its end.
        with EndingWithoutManifest() as ended:
            sends = self._cases.sends()
            emit(
                self._progress, SessionStarted(context.session, tuple(c.case_id for c, _ in sends))
            )
            ending = self._cases.run(sends)
            if ending is not None:
                return self._incomplete(ending)
            error = partial(context.plan, self._ledger, self._cases.stopped)
            self._write_ending(error)
        if ended.error is not None:
            return self._incomplete(ended.error)
        manifest = self._manifest
        if manifest is not None:
            emit(self._progress, SessionEnded(context.session, manifest.counts))
        return error

    def _write_plan(self, checked: CheckedConfiguration) -> None:
        """Writes the session's record, then the first plan's directory, for a new experiment;
        or, for a resume, the attempt records and tables a stopped run left unwritten, then a
        revision's directory, if the session runs one."""
        records, experiment = self._records, self._context.experiment
        records.write_session()
        if experiment is None:
            records.write_first_plan(checked)
            return
        records.complete_records(experiment)
        revision = self._authorization.revision
        if revision is not None:
            records.write_revision(revision, checked)

    def _write_ending(self, error: TrialFolioError | None) -> None:
        """Writes the session's report, then its manifest. A write of the manifest that fails,
        an interrupt included, discards it if the store had published it."""
        context = self._context
        created_at = utc(context.clock())
        evidence = self._builder.evidence(error)
        self._evidence = evidence
        self._report = write_experiment_report(
            context.store, evidence, HtmlReportRenderer(context.plan.trialfolio_version)
        )
        manifest = self._builder.manifest(error, created_at, self._report)
        self._manifest_file.write(manifest)
        self._manifest = manifest
        _logger.log(
            logging.INFO if error is None else logging.WARNING,
            "Session %d ended %s: %s.",
            context.session,
            manifest.outcome,
            "no error" if error is None else error.code,
            extra=context.log_fields("experiment.session.ended"),
        )

    def _incomplete(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped without its manifest, with what its records
        say."""
        results = self._cases.results
        return incomplete(
            failure,
            detail=self.ending_detail(),
            manifest=self._manifest_file.detail,
            last=results[-1] if results else None,
        )


def _check_kinds(
    plan: PlanV1_1 | PlanV1_3,
    approval: Approval,
    command: ExperimentCommandRecord | None,
    ranking_lock: str | os.PathLike[str] | None,
    *,
    synthetic: bool,
) -> None:
    """Checks that the approval and the command fit whether the experiment is synthetic, and
    the ranking lock whether the plan has a ranking definition."""
    if (approval == "not_required") != synthetic:
        raise ValueError("only an experiment executed with the demo's client needs no approval")
    if synthetic and command is not None:
        raise ValueError("no trialfolio command writes a synthetic experiment")
    if (ranking_lock is not None) != isinstance(plan, PlanV1_3):
        raise ValueError("an experiment with a ranking definition, and only one, takes the lock")
