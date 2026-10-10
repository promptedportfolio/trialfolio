"""The executor: executing an approved experiment plan, in the core (docs/contracts.md, running
an experiment, experiment output, the lock, the budget across runs, repeating a case, and
progress and cancellation).

`ExperimentExecution.run` executes a new experiment into an output directory that's absent or
empty:

1. It claims the directory with `experiment.lock`, and takes the experiment lock on it
   (`output.not_empty`, `experiment.locked`). The store holds the lock until its owner closes
   it, so no other process can run the experiment meanwhile.
2. It writes `sessions/1/session.json`, which reserves the session. That's the first atomic
   write, so a file system that can't take one fails here, before any request
   (`storage.write_failed`).
3. It writes `plans/1/configuration.yaml`, `plan.json`, and then `experiment.json`. Nothing is
   sent under a plan before its `experiment.json` is written.
4. It runs the cases in the plan's order, one attempt each, with one client, so the session
   authenticates once, and again only after a 401 or 403 drops its token. Before each attempt,
   it checks the cancellation, and that the budget covers one more request, and one more
   authentication call when the attempt authenticates. A case the budget can't cover isn't
   started, and neither is any case after it. So it is after Trial Folio's own authentication
   call fails, whatever its result, or after a request gets `provider.quota_exceeded`, since
   every later case would end the same way (D-32), and after a cancellation.
5. It writes each succeeded case's tables, `cases/<case_id>/normalized/metrics.csv` and
   `settings.csv`, right after its attempt record. A response that fails validation leaves the
   case `failed`, with `provider.response_invalid`, and the session goes on.
6. It writes the session's report, `sessions/1/report.html`, and then its manifest,
   `sessions/1/manifest.json`, last.

Given the experiment's records, which `open_experiment` read and checked while taking the lock,
it resumes the experiment in the same directory instead (R03-T09):

1. It writes the new session's `sessions/<s>/session.json`, numbered after every session in the
   directory.
2. It writes the attempt record of each attempt a stopped run left without one: `succeeded` for
   a start record with a saved response, `unknown` for one without, and `failed` for an attempt
   with only its authentication record. Then it writes each complete case's tables that a stopped
   run didn't, from the response's bytes the check read. For a revision, it writes
   `plans/<n>/`, as for the first plan, with the reason in its `experiment.json`.
3. It runs the cases that are due, and each case a confirmed repeat names, in the plan's order,
   as a new experiment runs its cases, with the budget counting every attempt of the experiment.
   A complete case, and one awaiting a repeat that no repeat names, are skipped.
4. It writes the session's report and manifest, which list every file of the experiment's
   records and count every attempt.

A case that fails is recorded, and the session goes on to the next one. An interrupt or a storage
failure ends the session at once, without its manifest, so the experiment's output reads as
incomplete until a later run resumes it. So does an attempt whose attempt record wasn't written,
such as after an unexpected exception while writing it, as for a run: a manifest couldn't account
for it. Every attempt written so far stays, and is never replaced.

Execution with the demo's client, which sends nothing, writes a synthetic experiment: its plan
and manifest record the approval `not_required`, and its report says its values are invented.
It resumes and revises only a synthetic experiment, and nothing else does.

Nothing here prompts, prints, reads the environment, or reads secrets: the caller passes the
approved hash, the confirmed repeats, and the client, which holds any credentials. Progress goes
to the caller's callback, as events that name each case by its `case_id` and hold no text from
the configuration, and the caller may cancel from any thread. Logs name the plan by its hash and
each case by its `case_id`, never by its key.
"""

import json
import logging
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from pydantic import BaseModel, TypeAdapter, ValidationError

from trialfolio.attempts import (
    ATTEMPT_RECORD,
    AttemptFile,
    Clock,
    ExperimentAttempt,
    ExperimentAttemptResult,
    provider_requests,
    request_detail,
    utc_now,
)
from trialfolio.configuration import experiment_original_values, read_experiment_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    Approval,
    ErrorDetail,
    RevisionReason,
)
from trialfolio.contracts.experiment_manifest import (
    EXPERIMENT_CONFIGURATION_FORMAT,
    BudgetLimits,
    CaseCounts,
    ExperimentArtifact,
    ExperimentArtifactRole,
    ExperimentAttemptCounts,
    ExperimentCommandRecord,
    ExperimentManifest,
    ExperimentManifestCounts,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord, SessionRecord
from trialfolio.contracts.manifest import (
    Capabilities,
    ExternalReference,
    ParserVersion,
    Reproducibility,
    SourceRecord,
)
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION
from trialfolio.demo import SyntheticScreenBacktestClient
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_records import (
    LOCK_LINE,
    LOCK_PATH,
    CaseAttempt,
    CaseOutcome,
    MissingTables,
    SavedExperiment,
    SavedExperimentAttempt,
    case_outcome,
    plan_path,
    session_path,
)
from trialfolio.normalization import (
    LAYOUT,
    LAYOUT_VERSION,
    PARSER_VERSION,
    holds_series,
    write_case_settings,
    write_case_tables,
)
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.planning import (
    PlanRevision,
    Versions,
    build_experiment_plan,
    check_approval,
    first_experiment_record,
    plan_changes,
    plan_hash,
    revised_experiment_record,
)
from trialfolio.provider import DecodedResponse, ScreenBacktestClient
from trialfolio.report import (
    CaseView,
    ExperimentEvidence,
    HtmlReportRenderer,
    write_experiment_report,
)
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the experiment manifests, `experiment.json` files, and session records
this module writes."""

_SCHEMA_VERSIONS: Final[dict[ExperimentArtifactRole, str]] = {
    "plan": "1.1.0",
    "experiment_record": "1.0.0",
    "authentication_record": "1.0.0",
    "start_record": "1.1.0",
    "attempt_record": "1.1.0",
    "metrics": TABLES_SCHEMA_VERSION,
    "settings": TABLES_SCHEMA_VERSION,
    "session_record": "1.0.0",
}
"""The schema version the manifest records for each role whose files have one, apart from the
configuration, which gives its own."""

_REASON: Final = TypeAdapter[str](RevisionReason)

type StopReason = Literal["budget", "authentication", "quota", "cancelled"]


# Progress events (docs/contracts.md, progress and cancellation)


@dataclass(frozen=True)
class SessionStarted:
    """The session has reserved its number and recorded its plan, and is about to run its cases."""

    session: int
    cases: tuple[str, ...]
    """The `case_id`s it will send or repeat, in the plan's order."""


@dataclass(frozen=True)
class AttemptStarted:
    case_id: str
    attempt_id: uuid.UUID


@dataclass(frozen=True)
class AttemptEnded:
    """An attempt ended, its attempt record was written, and so were its case's tables, if it
    succeeded."""

    case_id: str
    attempt_id: uuid.UUID
    outcome: Literal["succeeded", "failed", "unknown"]
    possibly_charged: bool


@dataclass(frozen=True)
class SessionEnded:
    """The session wrote its report and its manifest, whose counts these are, so it's complete,
    whatever the callback does with this event."""

    session: int
    counts: ExperimentManifestCounts


type ProgressEvent = SessionStarted | AttemptStarted | AttemptEnded | SessionEnded

type Progress = Callable[[ProgressEvent], object]
"""Receives each progress event, in order, in the thread that runs the execution. An exception
it raises propagates from `run`, as an unexpected exception would. Raised at an event before the
session's end, it ends the session without its manifest. Raised at `SessionEnded`, which comes
once the manifest is written, it leaves the session complete, with its manifest: no record is
ever removed."""


class Cancellation:
    """A request, from any thread, that an execution stop between attempts. Execution checks it
    before each attempt starts, never during one: a send in flight finishes, and is recorded."""

    def __init__(self) -> None:
        self._requested = threading.Event()

    def cancel(self) -> None:
        self._requested.set()

    @property
    def requested(self) -> bool:
        return self._requested.is_set()


@dataclass(frozen=True)
class Repeat:
    """A confirmed repeat (docs/contracts.md, repeating a case): the case to repeat, by its
    `case_id`, and the attempt whose possible charge the user acknowledged, the case's latest
    possibly charged attempt, by its `attempt_id`."""

    case_id: str
    attempt_id: uuid.UUID


# The attempts of the experiment


@dataclass(frozen=True)
class _Attempt:
    """An attempt of the experiment, an earlier session's or this one's, as the session's counts,
    budget, and manifest read it."""

    case_id: str
    session: int
    sequence: int
    outcome: Literal["running", "succeeded", "failed", "unknown"] | None
    """As its records read: `running` for a start record without an attempt record, and None for
    an attempt of this session that left no record. An earlier session's attempt without its
    attempt record reads as step 8 records it."""
    possibly_charged: bool
    error_code: str | None
    repeat_of: uuid.UUID | None
    requests: int
    """The sends the budget counts."""
    authentications: int
    """Trial Folio's own authentication calls the budget counts."""
    record: AttemptRecordV1_1 | None
    """Its attempt record, once it's written."""
    files: tuple[AttemptFile, ...]

    def read(self, *, valid: bool) -> CaseAttempt | None:
        if self.outcome is None:
            return None
        return CaseAttempt(self.session, self.sequence, self.outcome, self.possibly_charged, valid)


def _saved(attempt: SavedExperimentAttempt) -> _Attempt:
    return _Attempt(
        case_id=attempt.case_id,
        session=attempt.session,
        sequence=attempt.sequence,
        outcome=attempt.outcome,
        possibly_charged=attempt.possibly_charged,
        error_code=attempt.error_code,
        repeat_of=attempt.repeat_of,
        requests=attempt.provider_requests,
        authentications=attempt.authentication_calls,
        record=attempt.record,
        files=attempt.files,
    )


def _recorded(record: AttemptRecordV1_1, files: tuple[AttemptFile, ...]) -> _Attempt:
    return _Attempt(
        case_id=record.case_id,
        session=record.session,
        sequence=record.sequence,
        outcome=record.outcome,
        possibly_charged=record.possibly_charged,
        error_code=None if record.error is None else record.error.code,
        repeat_of=record.repeat_of,
        requests=provider_requests(record),
        authentications=sum(e.request == AUTHENTICATION_REQUEST for e in record.exchanges),
        record=record,
        files=files,
    )


def _ended(result: ExperimentAttemptResult) -> _Attempt:
    """An attempt of this session, as its records read. Without its attempt record, which a
    resume writes, it reads as the resume will count it: `running` with its start record, and
    `failed`, not possibly charged, with only its authentication record."""
    record = result.record
    if result.recorded:
        return _recorded(record, result.files)
    outcome: Literal["running", "failed"] | None
    if result.start is not None:
        outcome, charged, requests = "running", True, 1
    elif any(file.role == "authentication_record" for file in result.files):
        outcome, charged, requests = "failed", False, 0
    else:
        outcome, charged, requests = None, False, 0
    return _Attempt(
        case_id=record.case_id,
        session=record.session,
        sequence=record.sequence,
        outcome=outcome,
        possibly_charged=charged,
        error_code=None if record.error is None else record.error.code,
        repeat_of=record.repeat_of,
        requests=requests,
        authentications=int(result.authenticated),
        record=None,
        files=result.files,
    )


@dataclass(frozen=True)
class _Tables:
    """A case's normalized tables, and the parser that wrote its `metrics.csv`."""

    metrics: StoredFile
    settings: StoredFile
    parser_version: int


@dataclass(frozen=True)
class _RecordedPlan:
    """A plan of the experiment, with its files, as the manifest lists them."""

    number: int
    record: ExperimentRecord
    files: tuple[tuple[ExperimentArtifactRole, StoredFile], ...]
    configuration: bytes
    """Its `configuration.yaml`'s bytes, from which its cases' tables take their original
    values."""
    configuration_version: str


class ExperimentExecution:
    """One execution of an approved experiment plan into the output directory of `store`: a new
    experiment, or, given its records, a resumed one.

    Its properties stay readable whatever happens, so a caller whose execution was interrupted
    still knows what was written: whether the directory was claimed, the session, each attempt,
    and the manifest.
    """

    def __init__(
        self,
        plan: PlanV1_1,
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
    ) -> None:
        """Writes nothing.

        `approval` is how the plan was approved, as the records give it: `not_required` exactly
        for the demo's client, `SyntheticScreenBacktestClient`, which makes the experiment
        synthetic. `client` sends every request of the session; its caller closes it. `command`
        is the `trialfolio` command that runs the session, or None when the core runs it for
        another interface, and always for a synthetic experiment.

        `experiment` is the experiment's records, which `open_experiment` read from `store`
        while taking its lock, to resume or revise it; None for a new experiment. `plan` is then
        its current plan, which the session resumes, or a revision of it, which `plan_revision`
        built, with its `reason`. `repeats` are the confirmed repeats, each checked as repeating
        a case says.

        Raises `TrialFolioError`:

        - with `output.not_empty` when the demo's client is given for an experiment that isn't
          synthetic, or another client for one that is;
        - with `plan.approval_required` when a repeat names no case of the plan, a case that
          isn't awaiting a repeat, or an attempt of it that isn't possibly charged, or that
          succeeded; when a new experiment is given a reason or a repeat; when a resume of the
          current plan is given a reason, unless it's the one the current plan recorded, which
          resumes it; and unless `approved_hash` is the plan's hash, recomputed from its
          contents (approval);
        - with `plan.changed` when a revision isn't approved by its hash, with a reason.

        Raises `ValueError` when `plan` revises another without the experiment's records, or
        isn't the current plan or a revision of it; when a repeat names a case twice; when the
        reason isn't a valid reason; and when `approval` or `command` doesn't fit whether the
        experiment is synthetic.
        """
        synthetic = isinstance(client, SyntheticScreenBacktestClient)
        if (approval == "not_required") != synthetic:
            raise ValueError("only an experiment executed with the demo's client needs no approval")
        if synthetic and command is not None:
            raise ValueError("no trialfolio command writes a synthetic experiment")
        self._revision: PlanRevision | None = None
        self._reason: str | None = None
        self._repeats: dict[str, Repeat] = {}
        self._used: tuple[Repeat, ...] = ()
        if experiment is None:
            if reason is not None:
                raise _no_revision("A new experiment has no plan to revise.")
            if repeats:
                raise TrialFolioError(
                    "plan.approval_required",
                    "A new experiment has no attempt to repeat, so no repeat applies. Nothing was"
                    " sent.",
                )
            check_approval(plan, approved_hash)
            if plan.revises is not None:
                raise ValueError("a new experiment's first plan revises none")
        else:
            if synthetic != experiment.synthetic:
                raise _another_kind(synthetic=experiment.synthetic)
            self._repeats, self._used = _confirmed(plan, experiment, repeats)
            self._approve(plan, approved_hash, experiment, reason)
        self._plan = plan
        self._approval: Approval = approval
        self._store = store
        self._client = client
        self._command = command
        self._clock = clock
        self._progress = progress
        self._cancellation = cancellation
        self._synthetic = synthetic
        self._experiment = experiment
        self._started = False
        self._claimed = False
        self._session = 1 if experiment is None else experiment.next_session
        self._plan_number = 1 if experiment is None else experiment.current.number
        self._session_record: StoredFile | None = None
        self._record: ExperimentRecord | None = None if experiment is None else experiment.record
        self._plans: list[_RecordedPlan] = (
            []
            if experiment is None
            else [
                _RecordedPlan(
                    saved.number,
                    saved.record,
                    saved.files,
                    saved.configuration_content,
                    saved.configuration_version,
                )
                for saved in experiment.plans
            ]
        )
        self._attempts: list[_Attempt] = (
            [] if experiment is None else [_saved(attempt) for attempt in experiment.attempts]
        )
        self._tables: dict[str, _Tables] = {}
        if experiment is not None:
            for case_id, tables in experiment.tables.items():
                if tables.settings is not None:
                    self._tables[case_id] = _Tables(
                        tables.metrics, tables.settings, tables.parser_version
                    )
        self._invalid: dict[str, TrialFolioError] = {}
        """The `provider.response_invalid` each case's saved response got, by `case_id`."""
        self._results: list[ExperimentAttemptResult] = []
        self._current: ExperimentAttempt | None = None
        self._stopped: tuple[StopReason, TrialFolioError | None] | None = None
        self._report: StoredFile | None = None
        self._manifest: ExperimentManifest | None = None
        self._manifest_file: StoredFile | None = None
        self._manifest_left = False
        """Whether a manifest whose write failed couldn't be discarded."""
        self._configuration_version = ""
        self._record_data = b""
        """The first plan's `experiment.json`, once it's built."""

    def _approve(
        self,
        plan: PlanV1_1,
        approved_hash: str,
        experiment: SavedExperiment,
        reason: str | None,
    ) -> None:
        """Checks the approval of a resumed experiment's plan: the current plan's, as a new
        plan's is, or a revision's, with its reason (approving a revision)."""
        current = experiment.plan
        if plan == current:
            if reason is not None and reason != experiment.record.plans[-1].reason:
                raise _no_revision(
                    "The configuration gives the experiment's current plan, so there's no"
                    " revision to give a reason for: run it without a reason to resume it."
                )
            check_approval(plan, approved_hash)
            return
        if plan.revises != current.plan_hash:
            raise ValueError("the plan is neither the experiment's current plan nor a revision")
        expected = plan_hash(plan)
        if reason is None or approved_hash != expected:
            missing = "a reason" if reason is None else "the approval of its hash"
            raise TrialFolioError(
                "plan.changed",
                "The configuration, or the installed versions, changed since the experiment's"
                f" current plan, and the revision wasn't approved: it needs {missing}. Approving"
                f" it takes its full hash, {expected}, and a reason for the revision. Nothing was"
                " sent.",
            )
        try:
            self._reason = _REASON.validate_python(reason)
        except ValidationError:
            raise ValueError("the reason isn't a valid revision reason") from None
        self._revision = PlanRevision(plan, plan_changes(current, plan))

    @property
    def claimed(self) -> bool:
        """Whether the output directory was claimed, or, for a resume, whether the run began
        writing into it. Before then, nothing was written."""
        return self._claimed

    @property
    def session(self) -> int | None:
        """The session's number, once its session record is written."""
        return None if self._session_record is None else self._session

    @property
    def synthetic(self) -> bool:
        return self._synthetic

    @property
    def attempts(self) -> tuple[ExperimentAttemptResult, ...]:
        """Each attempt that ended in this session, in order."""
        return tuple(self._results)

    @property
    def outcomes(self) -> tuple[tuple[ExperimentPlanCase, CaseOutcome], ...]:
        """Each planned case, in the plan's order, with its outcome as the records now give it."""
        return tuple((case, self._outcome(case.case_id)) for case in self._plan.cases)

    @property
    def repeats_used(self) -> tuple[Repeat, ...]:
        """The confirmed repeats this session doesn't make, because an earlier repeat used their
        confirmation: a later attempt of the case may have reached Portfolio123."""
        return self._used

    @property
    def manifest(self) -> ExperimentManifest | None:
        """The session's manifest, once it's written: the session is then complete."""
        return self._manifest

    @property
    def report(self) -> StoredFile | None:
        return self._report

    def run(
        self, configuration: bytes, *, on_claimed: Callable[[], object] | None = None
    ) -> TrialFolioError | None:
        """Takes the steps the module lists. `configuration` is the bytes of the experiment
        configuration the plan was built from. `on_claimed` is called once the directory is
        claimed, or, for a resume, whose store already holds the lock, before the first write,
        before anything else is written into it, such as to start writing logs there.

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
        manifest.
        """
        if self._started:
            raise RuntimeError("an execution runs once")
        self._started = True
        self._check_configuration(configuration)
        if self._experiment is None:
            self._store.claim(LOCK_PATH, LOCK_LINE, lock=True)
        self._claimed = True
        try:
            if on_claimed is not None:
                on_claimed()
            self._write_session()
            if self._experiment is None:
                self._write_plan(configuration)
            else:
                self._complete_records(self._experiment)
                if self._revision is not None:
                    self._write_revision(self._revision, configuration)
        except KeyboardInterrupt:
            return self._before_cases(
                TrialFolioError("command.interrupted", "Trial Folio was interrupted.")
            )
        except TrialFolioError as failure:
            if failure.code != "storage.write_failed":
                raise
            return self._before_cases(failure)
        _logger.info(
            "Session %d started, under plan %d.",
            self._session,
            self._plan_number,
            extra=self._log_fields("experiment.session.started"),
        )
        try:
            sends = self._sends()
            self._emit(SessionStarted(self._session, tuple(case.case_id for case, _ in sends)))
            ending = self._run_cases(sends)
            if ending is not None:
                return self._incomplete(ending)
            error = self._partial()
            self._write_ending(error)
        except KeyboardInterrupt:
            return self._incomplete(
                TrialFolioError("command.interrupted", "Trial Folio was interrupted.")
            )
        except TrialFolioError as failure:
            if failure.code != "storage.write_failed":
                raise
            return self._incomplete(failure)
        manifest = self._manifest
        if manifest is not None:
            self._emit(SessionEnded(self._session, manifest.counts))
        return error

    def ending_detail(self) -> str:
        """What the session's records say, for the message of an ending the session didn't
        record itself, such as an unexpected exception: whether the request of the attempt under
        way may have been sent, and whether the session has its manifest."""
        return f"{self._attempt_detail()} {self._manifest_detail()}"

    # The session's records

    def _check_configuration(self, configuration: bytes) -> None:
        plan = self._plan
        versions = Versions(
            trialfolio=plan.trialfolio_version,
            p123api=plan.provider_wrapper.p123api,
            requests=plan.transport.requests,
            urllib3=plan.transport.urllib3,
        )
        number = self._plan_number if self._revision is None else self._next_plan()
        read = read_experiment_configuration(configuration, plan_path(number, "configuration.yaml"))
        if build_experiment_plan(read, versions, plan.revises) != plan:
            raise ValueError("the configuration doesn't give the plan")
        self._configuration_version = read.schema_version

    def _next_plan(self) -> int:
        return 1 if self._experiment is None else self._experiment.next_plan

    def _write_session(self) -> None:
        record = SessionRecord(
            schema_version=SCHEMA_VERSION,
            trialfolio_version=self._plan.trialfolio_version,
            session=self._session,
            started_at=_utc(self._clock()),
        )
        self._session_record = self._store.write(
            session_path(self._session, "session.json"), _model_json(record)
        )

    def _write_plan(self, configuration: bytes) -> None:
        number = self._plan_number
        files: list[tuple[ExperimentArtifactRole, StoredFile]] = []
        saved = self._store.write(plan_path(number, "configuration.yaml"), configuration)
        files.append(("configuration", saved))
        plan = self._store.write(plan_path(number, "plan.json"), _model_json(self._plan))
        files.append(("plan", plan))
        record = first_experiment_record(
            self._plan,
            plan_artifact_id=plan.artifact_id,
            configuration_artifact_id=saved.artifact_id,
            approval=self._approval,
            created_at=_utc(self._clock()),
        )
        self._record_data = _model_json(record)
        written = self._store.write(plan_path(number, "experiment.json"), self._record_data)
        files.append(("experiment_record", written))
        self._record = record
        self._plans.append(
            _RecordedPlan(number, record, tuple(files), configuration, self._configuration_version)
        )
        _logger.info(
            "Recorded plan %d.", number, extra=self._log_fields("experiment.plan.recorded")
        )

    def _write_revision(self, revision: PlanRevision, configuration: bytes) -> None:
        """Writes the revision's `plans/<n>/`, as for the first plan, with the reason in its
        `experiment.json`, written last: nothing is sent under it before."""
        number = self._next_plan()
        previous = self._experiment_record()
        files: list[tuple[ExperimentArtifactRole, StoredFile]] = []
        saved = self._store.write(plan_path(number, "configuration.yaml"), configuration)
        files.append(("configuration", saved))
        plan = self._store.write(plan_path(number, "plan.json"), _model_json(revision.plan))
        files.append(("plan", plan))
        record = revised_experiment_record(
            previous,
            revision,
            number=number,
            reason=str(self._reason),
            plan_artifact_id=plan.artifact_id,
            configuration_artifact_id=saved.artifact_id,
            approval=self._approval,
            created_at=_utc(self._clock()),
        )
        written = self._store.write(plan_path(number, "experiment.json"), _model_json(record))
        files.append(("experiment_record", written))
        self._record = record
        self._plan_number = number
        self._plans.append(
            _RecordedPlan(number, record, tuple(files), configuration, self._configuration_version)
        )
        _logger.info(
            "Recorded plan %d, which revises plan %d.",
            number,
            previous.plans[-1].plan,
            extra=self._log_fields("experiment.plan.recorded"),
        )

    def _complete_records(self, experiment: SavedExperiment) -> None:
        """Step 8 of a resume: writes the attempt record of each attempt a stopped run left
        without one, then the tables of each complete case that a stopped run didn't write."""
        _logger.info(
            "Session %d resumes the experiment under plan %d.",
            self._session,
            experiment.current.number,
            extra=self._log_fields("experiment.resumed"),
        )
        for place, saved in enumerate(experiment.attempts):
            if saved.record is not None:
                continue
            plan = experiment.saved_plan(saved.plan).plan
            record = saved.completed_record(plan, _utc(self._clock()))
            stored = self._store.write(f"{saved.directory}/{ATTEMPT_RECORD}", _model_json(record))
            files = (*saved.files, AttemptFile("attempt_record", stored))
            self._attempts[place] = _recorded(record, files)
            _logger.warning(
                "Recorded the attempt a stopped run left without its attempt record: %s; possibly"
                " charged: %s.",
                record.outcome,
                "yes" if record.possibly_charged else "no",
                extra={
                    **self._log_fields("experiment.attempt.recorded", saved.case_id),
                    "attempt_id": str(saved.attempt_id),
                },
            )
        for case_id, missing in experiment.missing.items():
            self._write_missing(case_id, missing, experiment)

    def _write_missing(
        self, case_id: str, missing: MissingTables, experiment: SavedExperiment
    ) -> None:
        if missing.invalid is not None:
            self._case_invalid(case_id, missing.invalid)
            return
        if missing.metrics_rows is not None:
            tables = write_case_tables(
                self._store,
                missing.case,
                missing.originals,
                configuration=missing.configuration,
                response=missing.response,
                content=missing.content,
            )
            self._tables[case_id] = _Tables(tables.metrics, tables.settings, PARSER_VERSION)
            return
        saved = experiment.tables[case_id]
        settings, _ = write_case_settings(
            self._store,
            missing.case,
            missing.originals,
            configuration=missing.configuration,
            metrics=saved.metrics_rows,
        )
        self._tables[case_id] = _Tables(saved.metrics, settings, saved.parser_version)

    # The cases

    def _sends(self) -> list[tuple[ExperimentPlanCase, uuid.UUID | None]]:
        """The cases this session sends, in the plan's order, each with the attempt a repeat of
        it repeats: every case of a new experiment; and in a resume, each case that's due, and
        each awaiting a repeat that a confirmed repeat names."""
        experiment = self._experiment
        if experiment is None:
            return [(case, None) for case in self._plan.cases]
        for repeat in self._used:
            _logger.info(
                "The case isn't repeated: the repeat confirmed for its attempt %s was made"
                " already.",
                repeat.attempt_id,
                extra=self._log_fields("experiment.repeat.used", repeat.case_id),
            )
        sends: list[tuple[ExperimentPlanCase, uuid.UUID | None]] = []
        for saved in experiment.cases(self._plan):
            repeat = self._repeats.get(saved.case.case_id)
            if saved.state == "due":
                sends.append((saved.case, None))
            elif saved.state == "awaiting_repeat" and repeat is not None:
                sends.append((saved.case, repeat.attempt_id))
        return sends

    def _run_cases(
        self, sends: Sequence[tuple[ExperimentPlanCase, uuid.UUID | None]]
    ) -> TrialFolioError | None:
        """Runs each case to send in the plan's order, until one can't start. Returns the error
        of an attempt that an interrupt or a storage failure ended, or whose attempt record
        wasn't written, which ends the session."""
        token_from: uuid.UUID | None = None
        for place, (case, repeat_of) in enumerate(sends, 1):
            later = place < len(sends)
            stop = self._stop_before(token_from is None)
            if stop is not None:
                self._stop(stop, None)
                break
            if repeat_of is not None:
                _logger.info(
                    "Repeating the case's request, as confirmed for its attempt %s.",
                    repeat_of,
                    extra=self._log_fields("experiment.repeat.started", case.case_id),
                )
            attempt = ExperimentAttempt(
                self._plan,
                case,
                self._store,
                session=self._session,
                # The session starts its attempts one at a time, so this is its next one.
                sequence=len(self._results) + 1,
                repeat_of=repeat_of,
                clock=self._clock,
                synthetic=self._synthetic,
            )
            self._current = attempt
            self._emit(AttemptStarted(case.case_id, attempt.attempt_id))
            result = attempt.run(self._client, token_from)
            self._current = None
            self._results.append(result)
            self._attempts.append(_ended(result))
            error = result.error
            # A manifest can't account for an attempt without its attempt record, whose start
            # record reads as running, so that ends the session too, whatever stopped the write.
            if not result.recorded or (
                error is not None and error.code in ("command.interrupted", "storage.write_failed")
            ):
                return error
            self._write_tables(case, result)
            record = result.record
            self._emit(
                AttemptEnded(
                    case.case_id,
                    attempt.attempt_id,
                    record.outcome,
                    record.possibly_charged,
                )
            )
            if not self._client.authenticated:
                token_from = None
            elif result.authenticated and not result.authentication_failed:
                token_from = attempt.attempt_id
            # Every later case would end the same way (D-32).
            if later and result.authentication_failed:
                self._stop("authentication", error)
                break
            quota = record.error is not None and record.error.code == "provider.quota_exceeded"
            if later and quota:
                self._stop("quota", error)
                break
        return None

    def _stop_before(self, authenticates: bool) -> StopReason | None:
        """Why the next attempt can't start, if it can't: a cancellation, or a budget that
        doesn't cover one more request, or one more authentication call when it authenticates.
        The budget counts every attempt of the experiment, earlier sessions' included."""
        if self._cancellation is not None and self._cancellation.requested:
            return "cancelled"
        budget = self._plan.budget
        if self._provider_requests() + 1 > budget.provider_requests:
            return "budget"
        if authenticates and self._authentication_calls() + 1 > budget.authentication_calls:
            return "budget"
        return None

    def _stop(self, reason: StopReason, error: TrialFolioError | None) -> None:
        self._stopped = (reason, error)
        _logger.warning(
            "No later case starts: %s.",
            _STOPS[reason],
            extra=self._log_fields("experiment.stopped"),
        )

    def _write_tables(self, case: ExperimentPlanCase, result: ExperimentAttemptResult) -> None:
        """Writes the case's tables from its saved response, right after its attempt record. A
        response that fails validation leaves the case `failed`."""
        response = result.record.response
        if not result.recorded or response is None:
            return
        # The session's attempts run under the current plan, and its saved configuration gives
        # the original values, however the configuration given to this run is written.
        plan = self._plans[-1]
        configuration_file = dict(plan.files)["configuration"]
        originals = experiment_original_values(
            plan.configuration, configuration_file.path, case.case_key
        )
        try:
            tables = write_case_tables(
                self._store,
                case,
                originals,
                configuration=configuration_file,
                response=response,
            )
        except TrialFolioError as failure:
            if failure.code != "provider.response_invalid":
                raise
            self._case_invalid(case.case_id, failure)
            return
        self._tables[case.case_id] = _Tables(tables.metrics, tables.settings, PARSER_VERSION)

    def _case_invalid(self, case_id: str, failure: TrialFolioError) -> None:
        self._invalid[case_id] = failure
        _logger.error(
            "The case's response failed validation: %s.",
            failure.code,
            extra=self._log_fields("experiment.case.invalid", case_id),
        )

    # The cases' outcomes

    def _of(self, case_id: str) -> list[_Attempt]:
        """The case's attempts, by session and then sequence."""
        return [attempt for attempt in self._attempts if attempt.case_id == case_id]

    def _outcome(self, case_id: str) -> CaseOutcome:
        valid = case_id not in self._invalid
        reads = (attempt.read(valid=valid) for attempt in self._of(case_id))
        return case_outcome(tuple(read for read in reads if read is not None))

    def _described(self, case_id: str) -> str:
        """The case's outcome, with the error code of the attempt that gives it."""
        outcome = self._outcome(case_id)
        if outcome == "not_yet_run":
            return "not yet run"
        invalid = self._invalid.get(case_id)
        if invalid is not None:
            return f"failed ({invalid.code})"
        attempts = [attempt for attempt in self._of(case_id) if attempt.outcome is not None]
        charged = [attempt for attempt in attempts if attempt.possibly_charged]
        code = (charged or attempts)[-1].error_code
        return outcome if code is None else f"{outcome} ({code})"

    def _awaiting_repeat(self, case_id: str) -> bool:
        """Whether the case awaits a repeat: one of its attempts may have reached Portfolio123,
        and none succeeded. One whose response failed validation succeeded, so it's complete."""
        attempts = self._of(case_id)
        return not any(a.outcome == "succeeded" for a in attempts) and any(
            a.possibly_charged for a in attempts
        )

    # The end of the session

    def _write_ending(self, error: TrialFolioError | None) -> None:
        """Writes the session's report, then its manifest. A write of the manifest that fails,
        an interrupt included, discards it if the store had published it."""
        created_at = _utc(self._clock())
        evidence = ExperimentEvidence(
            plan=self._plan,
            plan_number=self._plan_number,
            record=self._experiment_record(),
            session=self._session,
            synthetic=self._synthetic,
            outcome="completed" if error is None else "partial",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            cases=tuple(
                CaseView(
                    case=case,
                    outcome=self._outcome(case.case_id),
                    attempts=sum(a.outcome is not None for a in self._of(case.case_id)),
                    tables=case.case_id in self._tables,
                )
                for case in self._plan.cases
            ),
            counts=self._counts(),
            artifacts=self._artifacts(),
        )
        self._report = write_experiment_report(
            self._store, evidence, HtmlReportRenderer(self._plan.trialfolio_version)
        )
        manifest = self._build_manifest(error, created_at)
        data = _model_json(manifest)
        path = session_path(self._session, "manifest.json")
        try:
            self._manifest_file = self._store.write(path, data)
        except BaseException:
            try:
                self._store.discard(path, data)
            except TrialFolioError:
                self._manifest_left = True
            raise
        self._manifest = manifest
        _logger.log(
            logging.INFO if error is None else logging.WARNING,
            "Session %d ended %s: %s.",
            self._session,
            manifest.outcome,
            "no error" if error is None else error.code,
            extra=self._log_fields("experiment.session.ended"),
        )

    def _partial(self) -> TrialFolioError | None:
        """`execution.partial` when a planned case didn't succeed, with what happened to each,
        and why the session stopped, if it did."""
        missed = [case for case in self._plan.cases if self._outcome(case.case_id) != "succeeded"]
        if not missed:
            return None
        planned = len(self._plan.cases)

        def listing(named: Callable[[ExperimentPlanCase], str]) -> str:
            return "; ".join(f"{named(case)}, {self._described(case.case_id)}" for case in missed)

        lead = f"{len(missed)} of the {planned} planned cases didn't succeed:"
        why = ""
        if self._stopped is not None:
            reason, error = self._stopped
            why = " " + _STOP_MESSAGES[reason]
            if error is not None:
                why += f" The error was {error.code}."
        charged = (
            " A case whose request may have reached Portfolio123 is never sent again"
            " automatically: a confirmed repeat sends it."
            if any(self._awaiting_repeat(case.case_id) for case in missed)
            else ""
        )
        tail = f"{why}{charged} Every planned case is accounted for in the session's manifest."
        return TrialFolioError(
            "execution.partial",
            f"{lead} {listing(lambda c: f'`{c.case_key}`')}.{tail}",
            f"{lead} {listing(lambda c: c.case_id)}.{tail}",
        )

    def _build_manifest(
        self, error: TrialFolioError | None, created_at: datetime
    ) -> ExperimentManifest:
        artifacts = self._artifacts()
        if self._report is not None:
            artifacts = (*artifacts, self._listed("report", self._report))
        references: dict[str, ExternalReference] = {}
        for case in self._plan.cases:
            for row in case.settings:
                if "not_snapshotted" in row.flags:
                    references.setdefault(
                        row.setting, ExternalReference(setting=row.setting, snapshotted=False)
                    )
        parsers = sorted({tables.parser_version for tables in self._tables.values()}) or [
            PARSER_VERSION
        ]
        return ExperimentManifest(
            schema_version=SCHEMA_VERSION,
            artifact_type="experiment",
            trialfolio_version=self._plan.trialfolio_version,
            created_at=created_at,
            experiment_id=self._plan.experiment_id,
            session=self._session,
            command=self._command,
            synthetic=self._synthetic,
            plan=self._plan_number,
            plan_hash=self._plan.plan_hash,
            approval=self._approval,
            outcome="completed" if error is None else "partial",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            artifacts=artifacts,
            parsers=tuple(
                ParserVersion(layout=LAYOUT, layout_version=LAYOUT_VERSION, parser_version=version)
                for version in parsers
            ),
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            capabilities=Capabilities(
                return_series="source_only" if self._holds_series() else "absent",
                statistical_validation="not_assessed",
                trading_readiness="not_assessed",
            ),
            reproducibility=Reproducibility(
                status="incomplete" if references else "complete",
                external_references=tuple(references.values()),
            ),
            counts=self._counts(),
        )

    def _holds_series(self) -> bool:
        """Whether a saved response of the experiment holds per-period series."""
        if any(
            isinstance(result.response, DecodedResponse) and holds_series(result.response.payload)
            for result in self._results
        ):
            return True
        experiment = self._experiment
        if experiment is None:
            return False
        for attempt in experiment.attempts:
            if attempt.response is None or attempt.response[0].form != "decoded":
                continue
            try:
                payload: object = json.loads(attempt.response[1])
            except (UnicodeDecodeError, ValueError, RecursionError):
                continue
            if holds_series(payload):
                return True
        return False

    def _counts(self) -> ExperimentManifestCounts:
        outcomes = [self._outcome(case.case_id) for case in self._plan.cases]
        attempts = [attempt for attempt in self._attempts if attempt.outcome is not None]
        records = [attempt.record for attempt in attempts if attempt.record is not None]
        costs = [r.provider_metadata.cost for r in records if r.provider_metadata.cost is not None]
        budget = self._plan.budget
        return ExperimentManifestCounts(
            cases=CaseCounts(
                planned=len(outcomes),
                succeeded=outcomes.count("succeeded"),
                failed=outcomes.count("failed"),
                skipped=0,
                unknown=outcomes.count("unknown"),
                not_yet_run=outcomes.count("not_yet_run"),
            ),
            retired_cases=len(self._experiment_record().retired_cases),
            attempts=ExperimentAttemptCounts(
                succeeded=sum(a.outcome == "succeeded" for a in attempts),
                failed=sum(a.outcome == "failed" for a in attempts),
                unknown=sum(a.outcome == "unknown" for a in attempts),
                running=sum(a.outcome == "running" for a in attempts),
                repeats=sum(a.repeat_of is not None for a in attempts),
            ),
            retries=0,
            provider_requests=self._provider_requests(),
            authentication_calls=self._authentication_calls(),
            budget=BudgetLimits(
                provider_requests=budget.provider_requests,
                authentication_calls=budget.authentication_calls,
            ),
            cost=sum(costs) if costs else None,
        )

    def _provider_requests(self) -> int:
        """The sends counted against the budget: each that may have reached Portfolio123, of
        every attempt of the experiment."""
        return sum(attempt.requests for attempt in self._attempts)

    def _authentication_calls(self) -> int:
        """Trial Folio's own authentication calls counted against the budget, whatever their
        result: an attempt's `POST /auth` exchange, or its authentication record alone."""
        return sum(attempt.authentications for attempt in self._attempts)

    def _experiment_record(self) -> ExperimentRecord:
        if self._record is None:  # written before any case runs
            raise RuntimeError("the plan is recorded before the session ends")
        return self._record

    def _artifacts(self) -> tuple[ExperimentArtifact, ...]:
        """Each file of the experiment's records so far, as the manifest lists it, apart from
        the report: each plan's files, each attempt's, followed by its case's tables once it
        succeeded, and the session's record. A file the latest manifest lists is listed as it
        lists it, its source record included."""
        listed = [
            self._earlier(stored.path) or self._listed(role, stored, plan=recorded)
            for recorded in self._plans
            for role, stored in recorded.files
        ]
        for attempt in self._attempts:
            listed.extend(self._attempt_file(file, attempt) for file in attempt.files)
            tables = self._tables.get(attempt.case_id)
            if tables is not None and attempt.outcome == "succeeded":
                metrics, settings = tables.metrics, tables.settings
                listed.append(self._earlier(metrics.path) or self._listed("metrics", metrics))
                listed.append(self._earlier(settings.path) or self._listed("settings", settings))
        if self._session_record is not None:
            listed.append(self._listed("session_record", self._session_record))
        return tuple(listed)

    def _attempt_file(self, file: AttemptFile, attempt: _Attempt) -> ExperimentArtifact:
        """The file as the manifest lists it: as the latest manifest does, unless it's a
        response whose case's `metrics.csv` that manifest doesn't list, which the installed
        parser wrote since, and which its source record then names (which parser wrote them)."""
        role: ExperimentArtifactRole = file.role
        earlier = self._earlier(file.file.path)
        tables = self._tables.get(attempt.case_id)
        if earlier is not None and not (
            role == "provider_response"
            and tables is not None
            and self._earlier(tables.metrics.path) is None
        ):
            return earlier
        source = None
        if role in ("provider_request", "provider_response", "provider_response_undecoded"):
            decoded = role == "provider_response"
            record = attempt.record
            # The request was written just before the attempt's start record, and the response
            # was saved just before its attempt record.
            started = record.started_at if record is not None else _utc(self._clock())
            ended = record.ended_at if record is not None else started
            source = SourceRecord(
                acquired_at=started if role == "provider_request" else ended,
                format=LAYOUT if decoded else f"{LAYOUT}-{role.removeprefix('provider_')}",
                format_version=str(LAYOUT_VERSION),
                parser_version=PARSER_VERSION if decoded else None,
                provenance="verified",
                operation="screen_backtest",
            )
        return self._listed(role, file.file, source)

    def _earlier(self, path: str) -> ExperimentArtifact | None:
        """The latest manifest's entry for a file of the experiment's records, which the new
        manifest lists as it is, its source record included."""
        return None if self._experiment is None else self._experiment.listed(path)

    def _listed(
        self,
        role: ExperimentArtifactRole,
        stored: StoredFile,
        source: SourceRecord | None = None,
        *,
        plan: _RecordedPlan | None = None,
    ) -> ExperimentArtifact:
        schema_version = _SCHEMA_VERSIONS.get(role)
        if role == "configuration" and plan is not None:
            schema_version = plan.configuration_version
            # Acquired when its plan was recorded, so every session's manifest gives it the
            # same time: the plan's `experiment.json` records when.
            source = SourceRecord(
                acquired_at=plan.record.created_at,
                format=EXPERIMENT_CONFIGURATION_FORMAT,
                format_version=schema_version,
                parser_version=None,
                provenance="user_supplied",
                operation=None,
            )
        return ExperimentArtifact(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=role,
            schema_version=schema_version,
            source=source,
        )

    # Endings without a manifest

    def _before_cases(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped before its first case: nothing was sent. Its
        directory can be resumed only once its first plan's `experiment.json` is written, which
        an interrupt may have stopped just after the store published it."""
        if self._record is None and self._record_data:
            try:
                published = self._store.read(plan_path(1, "experiment.json")) == self._record_data
            except OSError:
                published = False
            if not published:
                return self._unrecorded(failure)
        elif self._record is None:
            return self._unrecorded(failure)
        detail = (
            "Nothing was sent. The session has no manifest, so the experiment's output reads as"
            " incomplete until running the same command again resumes it."
        )
        return TrialFolioError(
            failure.code, f"{failure.message} {detail}", f"{failure.log_message} {detail}"
        )

    def _unrecorded(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped before its first plan was recorded."""
        detail = (
            "Nothing was sent. The experiment's first plan wasn't recorded, so its output"
            " directory can't be resumed: remove the directory, and run the command again."
        )
        return TrialFolioError(
            failure.code, f"{failure.message} {detail}", f"{failure.log_message} {detail}"
        )

    def _incomplete(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped without its manifest, with what its records say."""
        detail = self.ending_detail()
        if failure.message.endswith(detail):
            return failure
        return TrialFolioError(
            failure.code, f"{failure.message} {detail}", f"{failure.log_message} {detail}"
        )

    def _attempt_detail(self) -> str:
        current = self._current
        if current is not None and current.start_record is not None:
            return (
                "The screen backtest request of the attempt under way may have been sent, and may"
                " have been charged: its start record reads as running. Trial Folio never"
                " retries it automatically."
            )
        if self._results:
            last = self._results[-1]
            record = last.record
            if not last.recorded:
                if last.start is not None:
                    return (
                        "The screen backtest request of the last attempt may have been sent, and"
                        " may have been charged: its start record reads as running. Trial Folio"
                        " never retries it automatically."
                    )
                return "The last attempt's request wasn't sent."
            detail = request_detail(record.outcome, possibly_charged=record.possibly_charged)
            return f"Of the last attempt: {detail}"
        return "No case's request was sent."

    def _manifest_detail(self) -> str:
        if self._manifest is not None:
            return "The session's manifest was written, so the experiment's output is complete."
        if self._manifest_left:
            return (
                "The session's manifest.json was published before the failure, and couldn't be"
                " removed, so the experiment reads as complete although the run failed."
            )
        return (
            "The attempts recorded so far are kept. The session has no manifest, so the"
            " experiment's output reads as incomplete until running the same command again"
            " resumes it."
        )

    # Progress and logs

    def _emit(self, event: ProgressEvent) -> None:
        if self._progress is not None:
            self._progress(event)

    def _log_fields(self, event: str, case_id: str | None = None) -> dict[str, str]:
        fields = {"event": event, "plan_hash": self._plan.plan_hash}
        if case_id is not None:
            fields["case_id"] = case_id
        return fields


def _confirmed(
    plan: PlanV1_1, experiment: SavedExperiment, repeats: Sequence[Repeat]
) -> tuple[dict[str, Repeat], tuple[Repeat, ...]]:
    """Checks each confirmed repeat against the plan and the records (repeating a case), and
    returns the repeats to make, by `case_id`, and those whose confirmation an earlier repeat
    used, which aren't made."""
    cases = {saved.case.case_id: saved for saved in experiment.cases(plan)}
    to_make: dict[str, Repeat] = {}
    used: list[Repeat] = []
    for repeat in repeats:
        if repeat.case_id in to_make or repeat.case_id in {r.case_id for r in used}:
            raise ValueError("a repeat names each case once")
        saved = cases.get(repeat.case_id)
        if saved is None:
            raise _not_repeated(
                f"A repeat names case {repeat.case_id}, which the plan doesn't include.",
                f"A repeat names case {repeat.case_id}, which the plan doesn't include.",
            )
        key = f"`{saved.case.case_key}`"
        if saved.state == "due":
            message = (
                "Case {} isn't awaiting a repeat: none of its attempts may have reached"
                " Portfolio123, so running the experiment sends it without one."
            )
            raise _not_repeated(message.format(key), message.format(saved.case.case_id))
        named = [a for a in saved.attempts if a.attempt_id == repeat.attempt_id]
        if not named or not named[0].possibly_charged or named[0].outcome == "succeeded":
            message = (
                f"A repeat of case {{}} names attempt {repeat.attempt_id}, which isn't an attempt"
                " of the case whose request may have been charged and that didn't succeed. A"
                " repeat names the case's latest attempt whose request may have been charged."
            )
            raise _not_repeated(message.format(key), message.format(saved.case.case_id))
        later = saved.attempts[saved.attempts.index(named[0]) + 1 :]
        if any(attempt.possibly_charged for attempt in later):
            used.append(repeat)
        else:
            to_make[repeat.case_id] = repeat
    return to_make, tuple(used)


def _not_repeated(message: str, log_message: str) -> TrialFolioError:
    tail = " Nothing was sent."
    return TrialFolioError("plan.approval_required", message + tail, log_message + tail)


def _no_revision(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "plan.approval_required",
        f"A reason for a revision was given, but there's no revision. {problem} Nothing was sent.",
    )


def _another_kind(*, synthetic: bool) -> TrialFolioError:
    """The demo's client for an experiment that isn't synthetic, or another client for one
    that is: invented and real attempts never share an experiment."""
    if synthetic:
        problem = (
            "The output directory holds a synthetic experiment, whose values are invented, and"
            " only the demo's client resumes it."
        )
    else:
        problem = (
            "The output directory holds an experiment whose attempts are real, and the demo's"
            " client, which sends nothing, can't add invented ones to it."
        )
    return TrialFolioError(
        "output.not_empty",
        f"{problem} Nothing was sent or written. Run the configuration into another output"
        " directory.",
    )


_STOPS: Final[dict[StopReason, str]] = {
    "budget": "the budget can't cover the next case",
    "authentication": "Trial Folio's own authentication call failed",
    "quota": "a request got provider.quota_exceeded",
    "cancelled": "the run was cancelled",
}
"""Why no later case starts, for the log."""

_STOP_MESSAGES: Final[dict[StopReason, str]] = {
    "budget": (
        "The experiment's budget couldn't cover the next case, so it and the cases after it"
        " weren't started. A revision that raises budget.provider_requests lets them run."
    ),
    "authentication": (
        "Trial Folio's own authentication call failed, so no later case started: each would"
        " have failed the same way. Once the cause is fixed, running the same command again"
        " resumes the experiment, and runs the cases not started."
    ),
    "quota": (
        "Portfolio123 refused a request because the account's API quota or credits are"
        " exhausted, so no later case started: each would have been refused the same way. Once"
        " the account has credits again, running the same command again resumes the"
        " experiment, and runs the cases not started."
    ),
    "cancelled": (
        "The run was cancelled, so no later case started. Running it again, approved by the"
        " same hash, resumes the experiment, and runs the cases not started."
    ),
}


def _model_json(model: BaseModel) -> bytes:
    return (model.model_dump_json(indent=2) + "\n").encode("utf-8")


def _utc(moment: datetime) -> datetime:
    if moment.utcoffset() != timedelta(0):
        raise ValueError("the clock must give UTC times")
    return moment
