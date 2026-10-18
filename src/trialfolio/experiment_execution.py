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
for it. Every attempt written so far stays, and is never replaced. `trialfolio.manifests` holds
what a session shares here with a run and a review: writing the manifest and discarding it, the
endings without one, and the parts of the manifest that a run and an experiment record alike.

From 0.4.0, a new experiment whose plan is 1.3.0, whose ranking is a definition, takes the same
steps, with these differences (sending a definition, running an experiment):

- Before step 1, it takes the ranking lock, on the file its caller gives, and holds it until the
  execution ends, after the session's manifest (`experiment.locked`, `storage.write_failed`).
- Step 3 also writes `plans/1/definition.xml`, right after `configuration.yaml`, from the
  definition's bytes the configuration was validated with, and `experiment.json` 1.1.0. For a
  baseline named by a snapshot, it's the snapshot's `definition.xml`, and the snapshot's
  record, `snapshot.json`, follows it, each from the bytes read and checked when the
  configuration was validated (reading a snapshot).
- Step 4's attempts (`RankingExperimentAttempt`) each send the case's `rank_update`, then its
  backtest, with start and attempt records 1.3.0. An attempt starts only when the budget covers
  both its requests.
- Step 5 writes `settings.csv` 1.1.0, with a weight row for each node, and step 6 experiment
  manifest 1.1.0, with the roles and source records of the files a definition adds.

It resumes and revises such an experiment the same way (release 0.4.0's R04-T09), given its
records, which `open_experiment` read with `ranking`:

- It takes the ranking lock, on the file its caller gives, only when its session sends: when a
  case is due or confirmed to repeat, and the budget covers the first one's two requests. It
  takes it before its session record, and holds it until the execution ends. A resume that sends
  nothing doesn't take it.
- Step 2 writes the attempt record of each attempt whose latest record is its update record, as
  sending a definition says, and a case's `settings.csv` 1.1.0, from the configuration and the
  `definition.xml` of the plan its attempt ran under. A revision into a plan 1.3.0 writes its
  `plans/<n>/definition.xml`, right after its `configuration.yaml`, and, for a snapshot, its
  `snapshot.json` after it.
- The budget counts each attempt's requests, two for an attempt that sends a definition, under
  every plan, and an attempt starts only when both its requests fit; a repeat sends both again.
- Each session of an experiment any of whose plans is 1.3.0 writes experiment manifest 1.1.0,
  which lists each file of an earlier plan, or of an attempt under one, with the version it has,
  and a file the latest manifest lists as it lists it.

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
import os
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, TypedDict, get_args

from pydantic import TypeAdapter, ValidationError

from trialfolio.attempts import (
    ATTEMPT_RECORD,
    AttemptFile,
    Clock,
    ExperimentAttempt,
    ExperimentAttemptResult,
    RankingExperimentAttempt,
    provider_requests,
    record_detail,
    utc_now,
)
from trialfolio.case_state import (
    CaseOutcome,
    case_outcome,
    case_state,
    confirmation_used,
    counted_authentications,
    counted_requests,
    described,
    described_by,
    experiment_counts,
    latest_charged,
    outcome_code,
    repeatable,
    unavailable_metrics,
)
from trialfolio.configuration import (
    ExperimentConfigurationRead,
    experiment_original_values,
    experiment_original_values_v1_1,
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
)
from trialfolio.contracts.attempt import AttemptRecordV1_1, AttemptRecordV1_3
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    Approval,
    ErrorDetail,
    RevisionReason,
)
from trialfolio.contracts.experiment_manifest import (
    EXPERIMENT_CONFIGURATION_FORMAT,
    ExperimentArtifact,
    ExperimentArtifactRole,
    ExperimentArtifactRoleV1_1,
    ExperimentArtifactV1_1,
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
from trialfolio.contracts.experiment_record import (
    ExperimentRecord,
    ExperimentRecordV1_1,
    SessionRecord,
)
from trialfolio.contracts.manifest import (
    Capabilities,
    ParserVersion,
    Reproducibility,
    SourceRecord,
    SourceRecordV1_1,
)
from trialfolio.contracts.plan import RankingSource
from trialfolio.contracts.tables import (
    TABLES_SCHEMA_VERSION,
    TABLES_SCHEMA_VERSION_V1_1,
    MetricsRow,
    SettingsRowV1_1,
)
from trialfolio.demo import SyntheticScreenBacktestClient
from trialfolio.display import series
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_paths import plan_path, session_path
from trialfolio.experiment_records import (
    MissingTables,
    SavedExperiment,
    SavedExperimentAttempt,
    SavedPlan,
)
from trialfolio.manifests import (
    PROVIDER_ROLES,
    RANK_UPDATE_ROLES,
    EndingWithoutManifest,
    ManifestDetails,
    ManifestFile,
    capabilities,
    configuration_source,
    definition_source,
    ends_without_manifest,
    model_json,
    parsers,
    provider_source,
    rank_update_source,
    reproducibility,
    running_detail,
    snapshot_definition_source,
    source_v1_1,
    updating_detail,
    utc,
)
from trialfolio.normalization import (
    METRICS_PATH,
    PARSER_VERSION,
    AnySettingsRows,
    RankingOriginals,
    case_tables_path,
    holds_series,
    write_case_settings,
    write_case_tables,
)
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.planning import (
    PlanRevision,
    PlanRevisionV1_1,
    Versions,
    build_experiment_plan,
    build_experiment_plan_v1_1,
    check_approval,
    first_experiment_record_v1_1,
    plan_changes,
    plan_changes_v1_1,
    plan_hash,
    retired_cases,
    retired_cases_v1_1,
    revised_experiment_record,
    revised_experiment_record_v1_1,
)
from trialfolio.provider import DecodedResponse, ScreenBacktestClient, provider_message_of
from trialfolio.ranking_lock import RankingLock
from trialfolio.report import (
    CaseView,
    ExperimentEvidence,
    HtmlReportRenderer,
    PlanRanking,
    RetiredCaseView,
    write_experiment_report,
)
from trialfolio.snapshots import SnapshotFiles
from trialfolio.storage import LOCK_LINE, LOCK_PATH, ArtifactStore, StoredFile, published
from trialfolio.tables import read_metrics_csv

_logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the experiment manifests, `experiment.json` files, and session records
this module writes, without a ranking definition."""

RANKING_SCHEMA_VERSION: Final = "1.1.0"
"""The schema version of the experiment manifests of an experiment with a ranking definition."""

DEFINITION_FILE: Final = "definition.xml"
"""The copy of a plan's ranking definition, in its `plans/<n>/` (ranking definitions)."""

SNAPSHOT_FILE: Final = "snapshot.json"
"""The copy of the record of the snapshot a plan's baseline names, after its `definition.xml`
(reading a snapshot)."""

_SCHEMA_VERSIONS: Final[dict[ExperimentArtifactRoleV1_1, str]] = {
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

_FIXED_VERSIONS: Final[dict[ExperimentArtifactRoleV1_1, str]] = {
    "ranking_snapshot_record": "1.0.0",
    "authentication_record": "1.0.0",
    "metrics": TABLES_SCHEMA_VERSION,
    "session_record": "1.0.0",
}
"""The same, for an experiment with a ranking definition, for the roles whose files have one
version: each other file's is its plan's, its attempt's, or its table's (the experiment manifest's
version 1.1.0)."""

_ATTEMPT_RECORDS: Final[frozenset[ExperimentArtifactRoleV1_1]] = frozenset(
    {"update_record", "start_record", "attempt_record"}
)
"""The roles of an attempt's records whose version is its attempt's: 1.3.0 for an attempt that
sends a definition, and 1.1.0 otherwise."""

_REASON: Final = TypeAdapter[str](RevisionReason)

_MANIFEST: Final = ManifestDetails(
    written="The session's manifest was written, so the experiment's output is complete.",
    left=(
        "The session's manifest.json was published before the failure, and couldn't be removed,"
        " so the experiment reads as complete although the run failed."
    ),
    missing=(
        "The attempts recorded so far are kept. The session has no manifest, so the experiment's"
        " output reads as incomplete until running the same command again resumes it."
    ),
)

type StopReason = Literal["budget", "authentication_budget", "authentication", "quota", "cancelled"]


_ROLES_V1_0: Final[dict[str, ExperimentArtifactRole]] = {
    role: role for role in get_args(ExperimentArtifactRole)
}
"""Experiment manifest 1.0.0's roles, which every experiment without a ranking definition's files
have."""


class _SessionManifestFields(TypedDict):
    """The fields experiment manifests 1.0.0 and 1.1.0 share, but the schema version and the
    artifacts."""

    artifact_type: Literal["experiment"]
    trialfolio_version: str
    created_at: datetime
    experiment_id: str
    session: int
    command: ExperimentCommandRecord | None
    synthetic: bool
    plan: int
    plan_hash: str
    approval: Approval
    outcome: Literal["completed", "partial"]
    error: ErrorDetail | None
    parsers: tuple[ParserVersion, ...]
    license_id: str
    notice_version: str
    capabilities: Capabilities
    reproducibility: Reproducibility
    counts: ExperimentManifestCounts


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
    budget, and manifest read it, and the rules of its case's state (`case_state.py`)."""

    case_id: str
    attempt_id: uuid.UUID
    session: int
    sequence: int
    outcome: Literal["running", "succeeded", "failed", "unknown"] | None
    """As its records read: `running` for a start record without an attempt record, and None for
    an attempt of this session that left no record. An earlier session's attempt without its
    attempt record reads as step 8 records it."""
    possibly_charged: bool
    error_code: str | None
    repeat_of: uuid.UUID | None
    provider_requests: int
    """The sends the budget counts."""
    authentication_calls: int
    """Trial Folio's own authentication calls the budget counts."""
    record: AttemptRecordV1_1 | AttemptRecordV1_3 | None
    """Its attempt record, once it's written."""
    files: tuple[AttemptFile, ...]
    version: str
    """The schema version of its start and attempt records: 1.3.0 for an attempt that sends a
    definition, and 1.1.0 otherwise."""


def _saved(attempt: SavedExperimentAttempt) -> _Attempt:
    return _Attempt(
        case_id=attempt.case_id,
        attempt_id=attempt.attempt_id,
        session=attempt.session,
        sequence=attempt.sequence,
        outcome=attempt.outcome,
        possibly_charged=attempt.possibly_charged,
        error_code=attempt.error_code,
        repeat_of=attempt.repeat_of,
        provider_requests=attempt.provider_requests,
        authentication_calls=attempt.authentication_calls,
        record=attempt.record,
        files=attempt.files,
        version=attempt.version,
    )


def _recorded(
    record: AttemptRecordV1_1 | AttemptRecordV1_3, files: tuple[AttemptFile, ...]
) -> _Attempt:
    return _Attempt(
        case_id=record.case_id,
        attempt_id=record.attempt_id,
        session=record.session,
        sequence=record.sequence,
        outcome=record.outcome,
        possibly_charged=record.possibly_charged,
        error_code=None if record.error is None else record.error.code,
        repeat_of=record.repeat_of,
        provider_requests=provider_requests(record),
        authentication_calls=sum(e.request == AUTHENTICATION_REQUEST for e in record.exchanges),
        record=record,
        files=files,
        version=record.schema_version,
    )


def _ended(result: ExperimentAttemptResult) -> _Attempt:
    """An attempt of this session, as its records read. Without its attempt record, which a
    resume writes, it reads as the resume will count it: `running` with its start record, and
    `failed`, not possibly charged, with only its authentication record. An attempt that sends a
    definition counts one request for each start record it wrote, and with only its update
    record, reads as `failed` with its `rank_update`'s response in its directory, saved or
    published before its write failed, and `unknown` without one, possibly charged either way
    (sending a definition)."""
    record = result.record
    if result.recorded:
        return _recorded(record, result.files)
    updated = int(result.update is not None)
    outcome: Literal["running", "failed", "unknown"] | None
    if result.start is not None:
        outcome, charged, requests = "running", True, 1 + updated
    elif result.update is not None:
        outcome = "failed" if result.update_saved else "unknown"
        charged, requests = True, 1
    elif any(file.role == "authentication_record" for file in result.files):
        outcome, charged, requests = "failed", False, 0
    else:
        outcome, charged, requests = None, False, 0
    return _Attempt(
        case_id=record.case_id,
        attempt_id=record.attempt_id,
        session=record.session,
        sequence=record.sequence,
        outcome=outcome,
        possibly_charged=charged,
        error_code=None if record.error is None else record.error.code,
        repeat_of=record.repeat_of,
        provider_requests=requests,
        authentication_calls=int(result.authenticated),
        record=None,
        files=result.files,
        version=record.schema_version,
    )


@dataclass(frozen=True)
class _Tables:
    """A case's normalized tables, their rows, and the parser that wrote its `metrics.csv`."""

    metrics: StoredFile
    settings: StoredFile
    parser_version: int
    metrics_rows: tuple[MetricsRow, ...]
    settings_rows: AnySettingsRows

    @property
    def settings_version(self) -> str:
        """`settings.csv`'s schema version: 1.1.0 for a case whose ranking is a definition."""
        rows = self.settings_rows
        if rows and isinstance(rows[0], SettingsRowV1_1):
            return TABLES_SCHEMA_VERSION_V1_1
        return TABLES_SCHEMA_VERSION


@dataclass(frozen=True)
class _RecordedPlan:
    """A plan of the experiment, with its files, as the manifest lists them."""

    number: int
    record: ExperimentRecord | ExperimentRecordV1_1
    files: tuple[tuple[ExperimentArtifactRoleV1_1, StoredFile], ...]
    configuration: bytes
    """Its `configuration.yaml`'s bytes, from which its cases' tables take their original
    values."""
    configuration_version: str
    plan_version: str
    """Its `plan.json`'s schema version: 1.3.0 for a plan with a ranking definition."""
    read: ExperimentConfigurationRead | None = None
    """The configuration as 0.4.0's reader read it, with its definition, for a plan with a
    ranking definition, from which its cases' weight rows take their original values."""
    source: RankingSource | None = None
    """Its `ranking_source`, for a plan with a ranking definition, which its report shows."""

    @property
    def ranking(self) -> PlanRanking:
        """Where its ranking definition came from, as the session's report shows it."""
        snapshot = None if self.read is None else self.read.snapshot
        return PlanRanking(self.number, self.source, None if snapshot is None else snapshot.record)


class ExperimentExecution:
    """One execution of an approved experiment plan into the output directory of `store`: a new
    experiment, or, given its records, a resumed one.

    Its properties stay readable whatever happens, so a caller whose execution was interrupted
    still knows what was written: whether the directory was claimed, the session, each attempt,
    and the manifest.
    """

    def __init__(  # noqa: C901, PLR0915 - RF-T11 shortens it.
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
        experiment takes it, and a resumed one when its session sends.

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
        reason isn't a valid reason; when `approval` or `command` doesn't fit whether the
        experiment is synthetic; and when `ranking_lock` is given for a plan without a ranking
        definition, or not given for one.
        """
        synthetic = isinstance(client, SyntheticScreenBacktestClient)
        if (approval == "not_required") != synthetic:
            raise ValueError("only an experiment executed with the demo's client needs no approval")
        if synthetic and command is not None:
            raise ValueError("no trialfolio command writes a synthetic experiment")
        if (ranking_lock is not None) != isinstance(plan, PlanV1_3):
            raise ValueError(
                "an experiment with a ranking definition, and only one, takes the lock"
            )
        self._revision: PlanRevision | PlanRevisionV1_1 | None = None
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
        self._lock = None if ranking_lock is None else RankingLock(ranking_lock)
        self._read: ExperimentConfigurationRead | None = None
        """The configuration, as 0.4.0's reader read it, for a plan with a ranking definition."""
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
        self._record: ExperimentRecord | ExperimentRecordV1_1 | None = (
            None if experiment is None else experiment.current.record
        )
        self._plans: list[_RecordedPlan] = (
            [] if experiment is None else [_recorded_plan(saved) for saved in experiment.plans]
        )
        self._attempts: list[_Attempt] = (
            [] if experiment is None else [_saved(attempt) for attempt in experiment.attempts]
        )
        self._tables: dict[str, _Tables] = {}
        self._metrics_alone: dict[str, tuple[MetricsRow, ...]] = {}
        """The rows of each `metrics.csv` this session published whose `settings.csv` it didn't
        write, because a failure came between them: a resume completes the pair."""
        if experiment is not None:
            for case_id, tables in experiment.tables.items():
                if tables.settings is not None and tables.settings_rows is not None:
                    self._tables[case_id] = _Tables(
                        tables.metrics,
                        tables.settings,
                        tables.parser_version,
                        tables.metrics_rows,
                        tables.settings_rows,
                    )
        self._invalid: dict[str, TrialFolioError] = (
            {}
            if experiment is None
            else {
                case_id: missing.invalid
                for case_id, missing in experiment.missing.items()
                if missing.invalid is not None
            }
        )
        """The `provider.response_invalid` each case's saved response got, by `case_id`: in a
        resume, from the start, those the records check found, so the outcomes are the records'
        before step 8 logs them, and after a failure that ends the session before it does."""
        self._results: list[ExperimentAttemptResult] = []
        self._current: ExperimentAttempt | RankingExperimentAttempt | None = None
        self._stopped: tuple[StopReason, TrialFolioError | None] | None = None
        self._report: StoredFile | None = None
        self._evidence: ExperimentEvidence | None = None
        self._manifest: ExperimentManifest | ExperimentManifestV1_1 | None = None
        self._manifest_file = ManifestFile(
            store, session_path(self._session, "manifest.json"), _MANIFEST
        )
        self._configuration_version = ""
        self._record_data = b""
        """The first plan's `experiment.json`, once it's built."""

    def _approve(
        self,
        plan: PlanV1_1 | PlanV1_3,
        approved_hash: str,
        experiment: SavedExperiment,
        reason: str | None,
    ) -> None:
        """Checks the approval of a resumed experiment's plan: the current plan's, as a new
        plan's is, or a revision's, with its reason (approving a revision)."""
        current = experiment.current.plan
        if plan == current:
            if reason is not None and reason != experiment.current.record.plans[-1].reason:
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
        record = experiment.current.record
        if (
            isinstance(record, ExperimentRecord)
            and isinstance(current, PlanV1_1)
            and isinstance(plan, PlanV1_1)
        ):
            self._revision = PlanRevision(plan, plan_changes(current, plan))
            return
        # Once a plan of the experiment has a ranking definition, release 0.4.0's rules record
        # its revisions, in experiment.json 1.1.0.
        self._revision = PlanRevisionV1_1(plan, plan_changes_v1_1(current, plan))

    @property
    def claimed(self) -> bool:
        """Whether the output directory was claimed, or, for a resume, whether the run began
        writing into it. Before then, nothing was written."""
        return self._claimed

    @property
    def session(self) -> int | None:
        """The session's number, once its session record is written, or published whole before
        its write failed."""
        return None if self._session_record is None else self._session

    @property
    def synthetic(self) -> bool:
        return self._synthetic

    @property
    def attempts(self) -> tuple[ExperimentAttemptResult, ...]:
        """Each attempt that ended in this session, in order."""
        return tuple(self._results)

    @property
    def outcomes(
        self,
    ) -> tuple[tuple[ExperimentPlanCase | ExperimentPlanCaseV1_3, CaseOutcome], ...]:
        """Each planned case, in the plan's order, with its outcome as the records now give it."""
        return tuple((case, self._outcome(case.case_id)) for case in self._plan.cases)

    @property
    def repeats_used(self) -> tuple[Repeat, ...]:
        """The confirmed repeats this session doesn't make, because an earlier repeat used their
        confirmation: a later attempt of the case may have reached Portfolio123."""
        return self._used

    @property
    def repeat_attempts(self) -> dict[str, uuid.UUID]:
        """Each planned case awaiting a repeat, by its `case_id`, with its latest possibly
        charged attempt's `attempt_id`, which confirms a repeat of it (repeating a case)."""
        repeats: dict[str, uuid.UUID] = {}
        for case in self._plan.cases:
            attempts = self._of(case.case_id)
            latest = latest_charged(attempts)
            if case_state(attempts) == "awaiting_repeat" and latest is not None:
                repeats[case.case_id] = latest.attempt_id
        return repeats

    @property
    def counts(self) -> ExperimentManifestCounts:
        """The experiment's counts, as the session's manifest counts them, over the plan this
        execution runs: the manifest's, once it's written, and otherwise as the records now give
        them, so an interface can report them after an ending without a manifest too."""
        if self._manifest is not None:
            return self._manifest.counts
        return self._counts()

    @property
    def metrics_unavailable(self) -> int:
        """The `unavailable` rows of the planned cases' `metrics.csv` files, as written so far,
        those whose `settings.csv` a failure kept this session from writing included, so the
        count agrees with the records however the session ends."""
        rows = {case_id: tables.metrics_rows for case_id, tables in self._tables.items()}
        for case_id, metrics in self._metrics_alone.items():
            rows.setdefault(case_id, metrics)
        if self._experiment is not None:
            for case_id, saved in self._experiment.tables.items():
                rows.setdefault(case_id, saved.metrics_rows)
        return unavailable_metrics(self._plan, rows)

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
        """Takes the steps the module lists. `configuration` is the bytes of the experiment
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
        self._check_configuration(configuration, definition, snapshot)
        copies = _copies(definition, snapshot)
        if self._lock is None or not self._sends_any():
            return self._run(configuration, copies, on_claimed)
        with self._lock:
            return self._run(configuration, copies, on_claimed)

    def _sends_any(self) -> bool:
        """Whether the session will send anything, so it takes the ranking lock: a new
        experiment's always does, and a resumed one's when a case is due, or confirmed to
        repeat, and the remaining budget covers the first one's requests (the ranking lock)."""
        if self._experiment is None:
            return True
        return bool(self._to_send()) and self._stop_before(authenticates=True) is None

    def _run(
        self,
        configuration: bytes,
        copies: tuple["_Copy", ...],
        on_claimed: Callable[[], object] | None,
    ) -> TrialFolioError | None:
        """The steps the module lists, once the ranking lock, if any, is held."""
        if self._experiment is None:
            self._store.claim(LOCK_PATH, LOCK_LINE, lock=True)
        self._claimed = True
        with EndingWithoutManifest() as ended:
            if on_claimed is not None:
                on_claimed()
            self._write_session()
            if self._experiment is None:
                self._write_plan(configuration, copies)
            else:
                self._complete_records(self._experiment)
                if self._revision is not None:
                    self._write_revision(self._revision, configuration, copies)
        if ended.error is not None:
            return self._before_cases(ended.error)
        _logger.info(
            "Session %d started, under plan %d.",
            self._session,
            self._plan_number,
            extra=self._log_fields("experiment.session.started"),
        )
        error: TrialFolioError | None = None  # The session's, once it reaches its end.
        with EndingWithoutManifest() as ended:
            sends = self._sends()
            self._emit(SessionStarted(self._session, tuple(case.case_id for case, _ in sends)))
            ending = self._run_cases(sends)
            if ending is not None:
                return self._incomplete(ending)
            error = self._partial()
            self._write_ending(error)
        if ended.error is not None:
            return self._incomplete(ended.error)
        manifest = self._manifest
        if manifest is not None:
            self._emit(SessionEnded(self._session, manifest.counts))
        return error

    def ending_detail(self) -> str:
        """What the session's records say, for the message of an ending the session didn't
        record itself, such as an unexpected exception: whether the request of the attempt under
        way may have been sent, and whether the session has its manifest."""
        return f"{self._attempt_detail()} {self._manifest_file.detail}"

    # The session's records

    def _check_configuration(
        self, configuration: bytes, definition: bytes | None, snapshot: SnapshotFiles | None
    ) -> None:
        """Checks that the configuration gives the plan, and, for a plan 1.3.0, with the
        definition's bytes it's given, or the snapshot's files', which `plans/<n>/definition.xml`
        and `snapshot.json` then hold."""
        plan = self._plan
        versions = Versions(
            trialfolio=plan.trialfolio_version,
            p123api=plan.provider_wrapper.p123api,
            requests=plan.transport.requests,
            urllib3=plan.transport.urllib3,
        )
        number = self._plan_number if self._revision is None else self._next_plan()
        source_name = plan_path(number, "configuration.yaml")
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
            self._read = ranked
            self._configuration_version = ranked.configuration.schema_version
            return
        if definition is not None or snapshot is not None:
            raise ValueError("only an experiment with a ranking definition is given one")
        read = read_experiment_configuration(configuration, source_name)
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
            started_at=utc(self._clock()),
        )
        path, data = session_path(self._session, "session.json"), model_json(record)
        try:
            self._session_record = self._store.write(path, data)
        except BaseException:
            # A record the store published before its write failed reserves the session, as an
            # attempt record published so counts as written (R03-T11).
            self._session_record = published(self._store, path, data)
            raise

    def _write_plan(self, configuration: bytes, copies: tuple["_Copy", ...]) -> None:
        number = self._plan_number
        files: list[tuple[ExperimentArtifactRoleV1_1, StoredFile]] = []
        saved = self._store.write(plan_path(number, "configuration.yaml"), configuration)
        files.append(("configuration", saved))
        for role, name, data in copies:
            files.append((role, self._store.write(plan_path(number, name), data)))
        plan = self._store.write(plan_path(number, "plan.json"), model_json(self._plan))
        files.append(("plan", plan))
        record = first_experiment_record_v1_1(
            self._plan,
            plan_artifact_id=plan.artifact_id,
            configuration_artifact_id=saved.artifact_id,
            approval=self._approval,
            created_at=utc(self._clock()),
        )
        self._record_data = model_json(record)
        written = self._store.write(plan_path(number, "experiment.json"), self._record_data)
        files.append(("experiment_record", written))
        self._record = record
        self._plans.append(
            _RecordedPlan(
                number,
                record,
                tuple(files),
                configuration,
                self._configuration_version,
                self._plan.schema_version,
                self._read,
                _ranking_source(self._plan),
            )
        )
        _logger.info(
            "Recorded plan %d.", number, extra=self._log_fields("experiment.plan.recorded")
        )

    def _write_revision(
        self,
        revision: PlanRevision | PlanRevisionV1_1,
        configuration: bytes,
        copies: tuple["_Copy", ...],
    ) -> None:
        """Writes the revision's `plans/<n>/`, as for the first plan, with the reason in its
        `experiment.json`, written last: nothing is sent under it before. A revision into a plan
        1.3.0 writes its `definition.xml` right after its `configuration.yaml`, and, for a
        snapshot, its `snapshot.json` after that, and its `experiment.json` is 1.1.0, as is
        every one after a plan 1.3.0."""
        number = self._next_plan()
        previous = self._experiment_record()
        files: list[tuple[ExperimentArtifactRoleV1_1, StoredFile]] = []
        saved = self._store.write(plan_path(number, "configuration.yaml"), configuration)
        files.append(("configuration", saved))
        for role, name, data in copies:
            files.append((role, self._store.write(plan_path(number, name), data)))
        plan = self._store.write(plan_path(number, "plan.json"), model_json(revision.plan))
        files.append(("plan", plan))
        record = self._revised_record(previous, revision, number, plan, saved)
        written = self._store.write(plan_path(number, "experiment.json"), model_json(record))
        files.append(("experiment_record", written))
        self._record = record
        self._plan_number = number
        self._plans.append(
            _RecordedPlan(
                number,
                record,
                tuple(files),
                configuration,
                self._configuration_version,
                revision.plan.schema_version,
                self._read,
                _ranking_source(revision.plan),
            )
        )
        _logger.info(
            "Recorded plan %d, which revises plan %d.",
            number,
            previous.plans[-1].plan,
            extra=self._log_fields("experiment.plan.recorded"),
        )

    def _revised_record(
        self,
        previous: ExperimentRecord | ExperimentRecordV1_1,
        revision: PlanRevision | PlanRevisionV1_1,
        number: int,
        plan: StoredFile,
        configuration: StoredFile,
    ) -> ExperimentRecord | ExperimentRecordV1_1:
        """The revision's `experiment.json`, `plans/<number>/`'s, from the current plan's,
        `previous`, written once its `plan.json` and its `configuration.yaml` are: 1.0.0 by
        0.3.0's rules while no plan of the experiment has a ranking definition, and 1.1.0 by
        release 0.4.0's once one has."""
        reason, created_at = str(self._reason), utc(self._clock())
        if isinstance(revision, PlanRevision) and isinstance(previous, ExperimentRecord):
            return revised_experiment_record(
                previous,
                revision,
                number=number,
                reason=reason,
                plan_artifact_id=plan.artifact_id,
                configuration_artifact_id=configuration.artifact_id,
                approval=self._approval,
                created_at=created_at,
            )
        if isinstance(revision, PlanRevision):  # an experiment.json 1.1.0 takes 0.4.0's changes
            raise TypeError("a revision recorded in experiment.json 1.1.0 is a PlanRevisionV1_1")
        return revised_experiment_record_v1_1(
            previous,
            revision,
            number=number,
            reason=reason,
            plan_artifact_id=plan.artifact_id,
            configuration_artifact_id=configuration.artifact_id,
            approval=self._approval,
            created_at=created_at,
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
            record = saved.completed_record(plan, utc(self._clock()))
            path, data = f"{saved.directory}/{ATTEMPT_RECORD}", model_json(record)
            try:
                stored = self._store.write(path, data)
            except BaseException:
                # The store may publish the record and still fail its write, as when the
                # directory's sync fails. The records then hold it, so the counts read it.
                whole = published(self._store, path, data)
                if whole is not None:
                    files = (*saved.files, AttemptFile("attempt_record", whole))
                    self._attempts[place] = _recorded(record, files)
                raise
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
            try:
                tables = write_case_tables(
                    self._store,
                    missing.case,
                    missing.originals,
                    configuration=missing.configuration,
                    response=missing.response,
                    content=missing.content,
                    ranking=missing.ranking,
                )
            except BaseException:
                self._keep_published_metrics(case_id)
                raise
            self._tables[case_id] = _Tables(
                tables.metrics,
                tables.settings,
                PARSER_VERSION,
                tables.metrics_rows,
                tables.settings_rows,
            )
            return
        saved = experiment.tables[case_id]
        settings, rows = write_case_settings(
            self._store,
            missing.case,
            missing.originals,
            configuration=missing.configuration,
            metrics=saved.metrics_rows,
            ranking=missing.ranking,
        )
        self._tables[case_id] = _Tables(
            saved.metrics, settings, saved.parser_version, saved.metrics_rows, rows
        )

    # The cases

    def _sends(self) -> list[tuple[ExperimentPlanCase | ExperimentPlanCaseV1_3, uuid.UUID | None]]:
        """The cases this session sends, in the plan's order, each with the attempt a repeat of
        it repeats, as `_to_send` gives them, once the repeats whose confirmation is used are
        logged."""
        for repeat in self._used:
            _logger.info(
                "The case isn't repeated: the repeat confirmed for its attempt %s was made"
                " already.",
                repeat.attempt_id,
                # The CLI says so on stderr itself, by the case's key, before the session starts.
                extra={
                    **self._log_fields("experiment.repeat.used", repeat.case_id),
                    "terminal": False,
                },
            )
        return self._to_send()

    def _to_send(
        self,
    ) -> list[tuple[ExperimentPlanCase | ExperimentPlanCaseV1_3, uuid.UUID | None]]:
        """The cases this session sends, in the plan's order, each with the attempt a repeat of
        it repeats: every case of a new experiment; and in a resume, each case that's due, and
        each awaiting a repeat that a confirmed repeat names."""
        experiment = self._experiment
        if experiment is None:
            return [(case, None) for case in self._plan.cases]
        sends: list[tuple[ExperimentPlanCase | ExperimentPlanCaseV1_3, uuid.UUID | None]] = []
        for saved in experiment.cases(self._plan):
            repeat = self._repeats.get(saved.case.case_id)
            if saved.state == "due":
                sends.append((saved.case, None))
            elif saved.state == "awaiting_repeat" and repeat is not None:
                sends.append((saved.case, repeat.attempt_id))
        return sends

    def _run_cases(
        self, sends: Sequence[tuple[ExperimentPlanCase | ExperimentPlanCaseV1_3, uuid.UUID | None]]
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
            _logger.info(
                "Case %d of %d this session: %s.",
                place,
                len(sends),
                case.case_id,
                extra=self._log_fields("experiment.case.started", case.case_id),
            )
            if repeat_of is not None:
                _logger.info(
                    "Repeating the case's request, as confirmed for its attempt %s.",
                    repeat_of,
                    extra=self._log_fields("experiment.repeat.started", case.case_id),
                )
            attempt = self._new_attempt(case, repeat_of)
            self._current = attempt
            self._emit(AttemptStarted(case.case_id, attempt.attempt_id))
            result = attempt.run(self._client, token_from)
            self._current = None
            self._results.append(result)
            self._attempts.append(_ended(result))
            error = result.error
            if ends_without_manifest(recorded=result.recorded, error=error):
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

    def _new_attempt(
        self, case: ExperimentPlanCase | ExperimentPlanCaseV1_3, repeat_of: uuid.UUID | None
    ) -> ExperimentAttempt | RankingExperimentAttempt:
        """The next attempt of the session, of `case`: one that sends the case's definition,
        then its backtest, under a plan 1.3.0, and one that sends its backtest otherwise."""
        plan = self._plan
        # The session starts its attempts one at a time, so this is its next one.
        sequence = len(self._results) + 1
        if isinstance(plan, PlanV1_3) and isinstance(case, ExperimentPlanCaseV1_3):
            return RankingExperimentAttempt(
                plan,
                case,
                self._store,
                session=self._session,
                sequence=sequence,
                repeat_of=repeat_of,
                clock=self._clock,
                synthetic=self._synthetic,
            )
        if isinstance(plan, PlanV1_1) and isinstance(case, ExperimentPlanCase):
            return ExperimentAttempt(
                plan,
                case,
                self._store,
                session=self._session,
                sequence=sequence,
                repeat_of=repeat_of,
                clock=self._clock,
                synthetic=self._synthetic,
            )
        raise TypeError("a case is one of its plan's")

    def _stop_before(self, authenticates: bool) -> StopReason | None:
        """Why the next attempt can't start, if it can't: a cancellation, or a budget that
        doesn't cover one more case's requests, one or, for a case with a ranking definition, two
        (sending a definition), or one more authentication call when it authenticates. The
        budget counts every attempt of the experiment, earlier sessions' included."""
        if self._cancellation is not None and self._cancellation.requested:
            return "cancelled"
        budget, attempts = self._plan.budget, self._attempts
        sends = 2 if isinstance(self._plan, PlanV1_3) else 1
        if counted_requests(attempts) + sends > budget.provider_requests:
            return "budget"
        if authenticates and counted_authentications(attempts) + 1 > budget.authentication_calls:
            return "authentication_budget"
        return None

    def _stop(self, reason: StopReason, error: TrialFolioError | None) -> None:
        self._stopped = (reason, error)
        _logger.warning(
            "No later case starts: %s.",
            _STOPS[reason],
            extra=self._log_fields("experiment.stopped"),
        )

    def _write_tables(
        self, case: ExperimentPlanCase | ExperimentPlanCaseV1_3, result: ExperimentAttemptResult
    ) -> None:
        """Writes the case's tables from its saved response, right after its attempt record. A
        response that fails validation leaves the case `failed`."""
        response = result.record.response
        if not result.recorded or response is None:
            return
        # The session's attempts run under the current plan, and its saved configuration gives
        # the original values, however the configuration given to this run is written.
        plan = self._plans[-1]
        files = dict(plan.files)
        configuration_file = files["configuration"]
        ranking = None
        if plan.read is None:
            originals = experiment_original_values(
                plan.configuration, configuration_file.path, case.case_key
            )
        else:
            originals, weights = experiment_original_values_v1_1(
                plan.configuration, configuration_file.path, plan.read, case.case_key
            )
            ranking = RankingOriginals(weights, files["ranking_definition"])
        try:
            tables = write_case_tables(
                self._store,
                case,
                originals,
                configuration=configuration_file,
                response=response,
                ranking=ranking,
            )
        except TrialFolioError as failure:
            if failure.code != "provider.response_invalid":
                self._keep_published_metrics(case.case_id)
                raise
            self._case_invalid(case.case_id, failure)
            return
        except BaseException:
            self._keep_published_metrics(case.case_id)
            raise
        self._tables[case.case_id] = _Tables(
            tables.metrics,
            tables.settings,
            PARSER_VERSION,
            tables.metrics_rows,
            tables.settings_rows,
        )

    def _keep_published_metrics(self, case_id: str) -> None:
        """After a failed write of the case's tables, keeps the rows of its `metrics.csv` if the
        store published it, as when `settings.csv`'s write fails, or an interrupt comes between
        them. The records then hold it, so `metrics_unavailable` counts it. It's read back, as
        an attempt's file published before its write failed is, because the store may publish
        a file and still fail its write."""
        path = case_tables_path(case_id, METRICS_PATH)
        try:
            self._metrics_alone[case_id] = read_metrics_csv(self._store.read(path), path)
        except (OSError, TrialFolioError):
            return  # Never published, or not readable: a resume's records check reads it.

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
        return case_outcome(self._of(case_id), valid=case_id not in self._invalid)

    def _described(self, case_id: str) -> str:
        """The case's outcome, with the error code that gives it."""
        return described(self._of(case_id), valid=case_id not in self._invalid)

    def _provider_said(self, case_id: str) -> str | None:
        """Portfolio123's own message in the error a case that didn't succeed is described by,
        when it has one."""
        giving = described_by(self._of(case_id))
        if giving is None or giving.record is None or giving.record.error is None:
            return None
        return provider_message_of(giving.record.error.message)

    # The end of the session

    def _write_ending(self, error: TrialFolioError | None) -> None:
        """Writes the session's report, then its manifest. A write of the manifest that fails,
        an interrupt included, discards it if the store had published it."""
        created_at = utc(self._clock())
        record = self._experiment_record()
        evidence = ExperimentEvidence(
            plan=self._plan,
            plan_number=self._plan_number,
            record=record,
            session=self._session,
            synthetic=self._synthetic,
            approval=self._approval,
            command=self._command,
            outcome="completed" if error is None else "partial",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            cases=tuple(self._case_view(case) for case in self._plan.cases),
            retired=tuple(
                RetiredCaseView(
                    case=retired,
                    outcome=self._outcome(retired.case_id),
                    attempts=self._records_of(retired.case_id),
                )
                for retired in record.retired_cases
            ),
            counts=self._counts(),
            parsers=self._parsers(),
            capabilities=capabilities(series=self._holds_series()),
            reproducibility=reproducibility(self._plan.cases),
            artifacts=(self._artifacts_v1_1() if self._ranked else self._artifacts()),
            rankings=tuple(plan.ranking for plan in self._plans) if self._ranked else (),
        )
        self._evidence = evidence
        self._report = write_experiment_report(
            self._store, evidence, HtmlReportRenderer(self._plan.trialfolio_version)
        )
        manifest = self._build_manifest(error, created_at)
        self._manifest_file.write(manifest)
        self._manifest = manifest
        _logger.log(
            logging.INFO if error is None else logging.WARNING,
            "Session %d ended %s: %s.",
            self._session,
            manifest.outcome,
            "no error" if error is None else error.code,
            extra=self._log_fields("experiment.session.ended"),
        )

    def _case_view(self, case: ExperimentPlanCase | ExperimentPlanCaseV1_3) -> CaseView:
        tables = self._tables.get(case.case_id)
        invalid = self._invalid.get(case.case_id)
        return CaseView(
            case=case,
            outcome=self._outcome(case.case_id),
            attempts=self._records_of(case.case_id),
            metrics=None if tables is None else tables.metrics_rows,
            settings=None if tables is None else tables.settings_rows,
            invalid=(
                None if invalid is None else ErrorDetail(code=invalid.code, message=invalid.message)
            ),
        )

    def _records_of(self, case_id: str) -> tuple[AttemptRecordV1_1 | AttemptRecordV1_3, ...]:
        """The case's attempt records, by session and then sequence. Once the session reaches
        its end, every attempt has one: step 8 wrote those a stopped run left, and an attempt of
        this session that left none ended the session before its end."""
        records: list[AttemptRecordV1_1 | AttemptRecordV1_3] = []
        for attempt in self._of(case_id):
            if attempt.outcome is None:
                continue
            if attempt.record is None:
                raise RuntimeError("every attempt has its record before the session's report")
            records.append(attempt.record)
        return tuple(records)

    def _partial(self) -> TrialFolioError | None:
        """`execution.partial` when a planned case didn't succeed, with what happened to each,
        and why the session stopped, if it did."""
        missed = [case for case in self._plan.cases if self._outcome(case.case_id) != "succeeded"]
        if not missed:
            return None
        planned = len(self._plan.cases)

        def listing(named: Callable[[ExperimentPlanCase | ExperimentPlanCaseV1_3], str]) -> str:
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
            if any(case_state(self._of(case.case_id)) == "awaiting_repeat" for case in missed)
            else ""
        )
        # Portfolio123's own text can repeat configuration values, so logs never hold it. The
        # loggable message leaves out the revision's sentence too (D-38).
        said = "".join(
            f' Portfolio123\'s message for `{case.case_key}`: "{text}".'
            for case in missed
            if (text := self._provider_said(case.case_id)) is not None
        )
        rejected = [
            f"`{case.case_key}`"
            for case in missed
            if outcome_code(self._of(case.case_id), valid=case.case_id not in self._invalid)
            == "provider.unsupported_capability"
        ]
        revise = (
            f" Portfolio123 rejected a setting of {series(rejected)}: a repeat sends the same"
            " request again, so change the setting instead, and revise the plan with"
            " --revision-reason."
            if rejected
            else ""
        )
        tail = " Every planned case is accounted for in the session's manifest."
        return TrialFolioError(
            "execution.partial",
            f"{lead} {listing(lambda c: f'`{c.case_key}`')}.{said}{why}{charged}{revise}{tail}",
            f"{lead} {listing(lambda c: c.case_id)}.{why}{charged}{tail}",
        )

    def _build_manifest(
        self, error: TrialFolioError | None, created_at: datetime
    ) -> ExperimentManifest | ExperimentManifestV1_1:
        """The session's manifest: version 1.1.0 for an experiment with a ranking definition,
        and 1.0.0 otherwise."""
        fields = _SessionManifestFields(
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
            parsers=self._parsers(),
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            capabilities=capabilities(series=self._holds_series()),
            reproducibility=reproducibility(self._plan.cases),
            counts=self._counts(),
        )
        if self._ranked:
            ranked = self._artifacts_v1_1()
            if self._report is not None:
                ranked = (*ranked, self._listed_v1_1("report", self._report))
            return ExperimentManifestV1_1(
                **fields, schema_version=RANKING_SCHEMA_VERSION, artifacts=ranked
            )
        artifacts = self._artifacts()
        if self._report is not None:
            artifacts = (*artifacts, self._listed("report", self._report))
        return ExperimentManifest(**fields, schema_version=SCHEMA_VERSION, artifacts=artifacts)

    def _parsers(self) -> tuple[ParserVersion, ...]:
        """Each parser that wrote a case's `metrics.csv`, or the installed one when none did."""
        return parsers(tables.parser_version for tables in self._tables.values())

    def _holds_series(self) -> bool:
        """Whether a saved response of the experiment holds per-period series: each decoded
        response the manifest lists, one whose write failed after the store published it
        included, though no attempt record references it."""
        responses = [r for result in self._results for r in (result.response, result.published)]
        if any(isinstance(r, DecodedResponse) and holds_series(r.payload) for r in responses):
            return True
        experiment = self._experiment
        if experiment is None:
            return False
        for attempt in experiment.attempts:
            if attempt.decoded_response is None:
                continue
            try:
                payload: object = json.loads(attempt.decoded_response)
            except (UnicodeDecodeError, ValueError, RecursionError):
                continue
            if holds_series(payload):
                return True
        return False

    def _counts(self) -> ExperimentManifestCounts:
        return experiment_counts(
            self._plan, self._attempts, invalid=self._invalid, retired=self._retired()
        )

    def _retired(self) -> int:
        """How many cases revisions retired, once the plan this execution runs is current: the
        current plan's, or a revision's before its `plans/<n>/` is written."""
        record = self._record
        if record is None:  # a new experiment's, before its first plan is recorded
            return 0
        if isinstance(record, ExperimentRecord) and isinstance(self._plan, PlanV1_1):
            return len(retired_cases(record, self._plan))
        return len(retired_cases_v1_1(record, self._plan))

    def _experiment_record(self) -> ExperimentRecord | ExperimentRecordV1_1:
        if self._record is None:  # written before any case runs
            raise RuntimeError("the plan is recorded before the session ends")
        return self._record

    def _artifacts(self) -> tuple[ExperimentArtifact, ...]:
        """Each file of the experiment's records so far, as the manifest lists it, apart from
        the report: each plan's files, each attempt's, followed by its case's tables once it
        succeeded, and the session's record. A file the latest manifest lists is listed as it
        lists it, its source record included."""
        listed = [
            self._earlier(stored.path) or self._listed(_ROLES_V1_0[role], stored, plan=recorded)
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

    @property
    def _ranked(self) -> bool:
        """Whether a plan of the experiment has a ranking definition, so its sessions write
        experiment manifest 1.1.0: the current plan's `experiment.json` is 1.1.0, or the plan
        this execution runs is 1.3.0 (the experiment manifest's version 1.1.0)."""
        return isinstance(self._record, ExperimentRecordV1_1) or isinstance(self._plan, PlanV1_3)

    def _artifacts_v1_1(self) -> tuple[ExperimentArtifactV1_1, ...]:
        """Each file of the records of an experiment with a ranking definition, as experiment
        manifest 1.1.0 lists it, in `_artifacts`' order, a plan's `definition.xml` and each
        attempt's update record and `rank_update` files included. A file the latest manifest
        lists is listed as it lists it, as `_artifacts` lists one, an entry of a manifest 1.0.0
        as version 1.1.0 lists it; and each other file with its own version, its plan's, its
        attempt's, or its table's."""
        listed = [
            self._earlier_v1_1(stored.path) or self._listed_v1_1(role, stored, plan=recorded)
            for recorded in self._plans
            for role, stored in recorded.files
        ]
        for attempt in self._attempts:
            listed.extend(self._attempt_file_v1_1(file, attempt) for file in attempt.files)
            tables = self._tables.get(attempt.case_id)
            if tables is not None and attempt.outcome == "succeeded":
                metrics, settings = tables.metrics, tables.settings
                listed.append(
                    self._earlier_v1_1(metrics.path) or self._listed_v1_1("metrics", metrics)
                )
                listed.append(
                    self._earlier_v1_1(settings.path)
                    or self._listed_v1_1("settings", settings, version=tables.settings_version)
                )
        if self._session_record is not None:
            listed.append(self._listed_v1_1("session_record", self._session_record))
        return tuple(listed)

    def _attempt_file_v1_1(self, file: AttemptFile, attempt: _Attempt) -> ExperimentArtifactV1_1:
        """The file as experiment manifest 1.1.0 lists it, by `_attempt_file`'s rule."""
        earlier = self._earlier_v1_1(file.file.path)
        tables = self._tables.get(attempt.case_id)
        if earlier is not None and not (
            file.role == "provider_response"
            and tables is not None
            and self._earlier_v1_1(tables.metrics.path) is None
        ):
            return earlier
        return self._listed_v1_1(file.role, file.file, attempt=attempt)

    def _attempt_file(self, file: AttemptFile, attempt: _Attempt) -> ExperimentArtifact:
        """The file as the manifest lists it: as the latest manifest does, unless it's a
        response whose case's `metrics.csv` that manifest doesn't list, which the installed
        parser wrote since, and which its source record then names (which parser wrote them)."""
        role = _ROLES_V1_0[file.role]
        earlier = self._earlier(file.file.path)
        tables = self._tables.get(attempt.case_id)
        if earlier is not None and not (
            role == "provider_response"
            and tables is not None
            and self._earlier(tables.metrics.path) is None
        ):
            return earlier
        source = None
        if role in PROVIDER_ROLES:
            started, ended = self._attempt_times(attempt)
            source = provider_source(role, started_at=started, ended_at=ended)
        return self._listed(role, file.file, source)

    def _attempt_times(self, attempt: _Attempt) -> tuple[datetime, datetime]:
        """When the attempt started and ended, as its record gives them, which date its
        request's and its response's source records; without a record, the clock's time."""
        record = attempt.record
        started = record.started_at if record is not None else utc(self._clock())
        ended = record.ended_at if record is not None else started
        return started, ended

    def _earlier(self, path: str) -> ExperimentArtifact | None:
        """The latest manifest's entry for a file of the experiment's records, which the new
        manifest lists as it is, its source record included. A manifest 1.0.0 follows only
        manifests 1.0.0: once a plan has a ranking definition, every session writes 1.1.0."""
        entry = None if self._experiment is None else self._experiment.listed(path)
        if entry is not None and not isinstance(entry, ExperimentArtifact):
            raise RuntimeError("an experiment manifest 1.0.0 never follows a 1.1.0")
        return entry

    def _earlier_v1_1(self, path: str) -> ExperimentArtifactV1_1 | None:
        """The latest manifest's entry for a file, as `_earlier` gives it, as experiment
        manifest 1.1.0 lists it: an entry of a manifest 1.0.0, written before a plan of the
        experiment had a ranking definition, has the same fields, and its source record a
        version 1.1.0's."""
        entry = None if self._experiment is None else self._experiment.listed(path)
        if entry is None or isinstance(entry, ExperimentArtifactV1_1):
            return entry
        return ExperimentArtifactV1_1.model_validate_json(entry.model_dump_json())

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
            source = configuration_source(
                EXPERIMENT_CONFIGURATION_FORMAT, schema_version, plan.record.created_at
            )
        return ExperimentArtifact(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=role,
            schema_version=schema_version,
            source=source,
        )

    def _listed_v1_1(
        self,
        role: ExperimentArtifactRoleV1_1,
        stored: StoredFile,
        *,
        plan: _RecordedPlan | None = None,
        attempt: _Attempt | None = None,
        version: str | None = None,
    ) -> ExperimentArtifactV1_1:
        """A file as experiment manifest 1.1.0 lists it: with its schema version, and the source
        record of a source artifact. A plan's `configuration.yaml` and `definition.xml` are
        acquired when the plan is recorded, as its `experiment.json` records; an attempt's
        requests and responses, at its times (a run with a ranking definition). Its version is
        its plan's, for a plan's file, its attempt's, for an attempt's records, `version`, for
        `settings.csv`, and otherwise its role's."""
        schema_version = _FIXED_VERSIONS.get(role, version)
        if plan is not None and role == "plan":
            schema_version = plan.plan_version
        elif plan is not None and role == "experiment_record":
            schema_version = plan.record.schema_version
        elif attempt is not None and role in _ATTEMPT_RECORDS:
            schema_version = attempt.version
        source: SourceRecordV1_1 | None = None
        if plan is not None and role == "configuration":
            schema_version = plan.configuration_version
            source = source_v1_1(
                configuration_source(
                    EXPERIMENT_CONFIGURATION_FORMAT, schema_version, plan.record.created_at
                )
            )
        elif plan is not None and role == "ranking_definition":
            snapshot = None if plan.read is None else plan.read.snapshot
            source = (
                definition_source(plan.record.created_at)
                if snapshot is None
                else snapshot_definition_source(snapshot.record.taken_at)
            )
        elif attempt is not None and role in PROVIDER_ROLES:
            started, ended = self._attempt_times(attempt)
            source = source_v1_1(provider_source(role, started_at=started, ended_at=ended))
        elif attempt is not None and role in RANK_UPDATE_ROLES:
            started, ended = self._attempt_times(attempt)
            source = rank_update_source(role, started_at=started, ended_at=ended)
        return ExperimentArtifactV1_1(
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
        if self._record is None and (
            not self._record_data
            or published(self._store, plan_path(1, "experiment.json"), self._record_data) is None
        ):
            return self._unrecorded(failure)
        detail = (
            "Nothing was sent. The session has no manifest, so the experiment's output reads as"
            " incomplete until running the same command again resumes it."
        )
        return failure.with_detail(detail)

    def _unrecorded(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped before its first plan was recorded."""
        detail = (
            "Nothing was sent. The experiment's first plan wasn't recorded, so its output is"
            " incomplete, and the directory can't be resumed: remove the directory, and run the"
            " command again."
        )
        return failure.with_detail(detail)

    def _incomplete(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped without its manifest, with what its records say.
        An attempt's own error already says what happened to its request, and so does its
        attempt record once it's written, so the error of an attempt that wrote it gets only what
        the records say of the manifest."""
        detail = self.ending_detail()
        if failure.message.endswith(detail):
            return failure
        last = self._results[-1] if self._results else None
        if last is not None and last.recorded and failure is last.error:
            detail = self._manifest_file.detail
        return failure.with_detail(detail)

    def _attempt_detail(self) -> str:
        current = self._current
        if current is not None and current.start_record is not None:
            ranking = isinstance(current, RankingExperimentAttempt)
            return running_detail("the attempt under way", ranking=ranking)
        if isinstance(current, RankingExperimentAttempt) and current.update_record is not None:
            return updating_detail("the attempt under way")
        if self._results:
            last = self._results[-1]
            record = last.record
            if not last.recorded:
                if last.start is not None:
                    return running_detail("the last attempt", ranking=last.update is not None)
                if last.update is not None:
                    return updating_detail("the last attempt")
                return "The last attempt's request wasn't sent."
            detail = record_detail(record)
            return f"Of the last attempt: {detail}"
        return "No case's request was sent."

    # Progress and logs

    def _emit(self, event: ProgressEvent) -> None:
        if self._progress is not None:
            self._progress(event)

    def _log_fields(self, event: str, case_id: str | None = None) -> dict[str, str]:
        fields = {"event": event, "plan_hash": self._plan.plan_hash}
        if case_id is not None:
            fields["case_id"] = case_id
        return fields


type _Copy = tuple[Literal["ranking_definition", "ranking_snapshot_record"], str, bytes]
"""A copy a plan with a ranking definition holds after its `configuration.yaml`: its role, its
file's name in `plans/<n>/`, and its bytes."""


def _copies(definition: bytes | None, snapshot: SnapshotFiles | None) -> tuple[_Copy, ...]:
    """The copies a plan's directory holds after its `configuration.yaml`, in order: the
    definition's, `definition.xml`, from its file's bytes, or from a snapshot's, and then, for a
    snapshot, its record's, `snapshot.json` (ranking definitions, reading a snapshot)."""
    if snapshot is not None:
        return (
            ("ranking_definition", DEFINITION_FILE, snapshot.definition),
            ("ranking_snapshot_record", SNAPSHOT_FILE, snapshot.record),
        )
    if definition is not None:
        return (("ranking_definition", DEFINITION_FILE, definition),)
    return ()


def _recorded_plan(saved: SavedPlan) -> _RecordedPlan:
    """A plan of a resumed experiment, as the records hold it."""
    return _RecordedPlan(
        saved.number,
        saved.record,
        saved.files,
        saved.configuration_content,
        saved.configuration_version,
        saved.plan.schema_version,
        saved.read,
        _ranking_source(saved.plan),
    )


def _ranking_source(plan: PlanV1_1 | PlanV1_3) -> RankingSource | None:
    """A plan's `ranking_source`: where its ranking definition came from, or None for a plan
    without one."""
    return plan.ranking_source if isinstance(plan, PlanV1_3) else None


def _confirmed(
    plan: PlanV1_1 | PlanV1_3, experiment: SavedExperiment, repeats: Sequence[Repeat]
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
        if not named or not repeatable(named[0]):
            message = (
                f"A repeat of case {{}} names attempt {repeat.attempt_id}, which isn't an attempt"
                " of the case whose request may have been charged and that didn't succeed. A"
                " repeat names the case's latest attempt whose request may have been charged."
            )
            raise _not_repeated(message.format(key), message.format(saved.case.case_id))
        if confirmation_used(saved.attempts, repeat.attempt_id):
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
    "authentication_budget": "the budget's authentication calls are spent",
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
    "authentication_budget": (
        "The experiment's budget of authentication calls is spent, so the next case, which"
        " would authenticate before its request, and the cases after it weren't started. A"
        " revision that raises budget.provider_requests, which sets the authentication calls"
        " too, lets them run."
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
