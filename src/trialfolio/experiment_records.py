"""An experiment's records, read back and checked, as a resume reads them before it builds its
plan (docs/contracts.md, running an experiment: a resumed experiment, checking the records, and
the cases that are due; experiment output; experiment attempts; an experiment's normalized
tables; and the experiment manifest).

`open_experiment` takes the experiment lock on a store's output directory, which holds
`experiment.lock`, and `read_experiment` reads every record of the experiment through the store,
each file once, and checks them:

- **The plans.** Each `plans/<n>/` that holds an `experiment.json`: the file is valid; its last
  entry is its directory's plan, by its number, its hash, and the `artifact_id`s of its
  `plan.json` and `configuration.yaml`; its earlier entries are the previous plan's; its plan
  recomputes to its hash, and revises the previous plan; and it records the experiment and the
  planned cases as its plan declares them. A plan's directory without `experiment.json` is a
  revision whose approval was never recorded, and isn't a plan. Without `plans/1/experiment.json`,
  the experiment's first run stopped before anything was sent, and there's nothing to resume.
- **The latest manifest,** the highest-numbered session's that has one: it's valid, and each file
  it lists has the size and `artifact_id` it records, so a record missing from an incomplete copy
  fails the check, instead of leaving its case looking due. It's the experiment's, names one of
  its plans, and is `synthetic` exactly when the plans record the approval `not_required`.
- **The attempts,** in `cases/<case_id>/attempts/<attempt_id>/`: their records are valid, and
  agree with each other and with their directory; they name a plan of the experiment, a case of
  that plan, and a session; no two attempts of a session have one `sequence`; each file an
  attempt record references has the `artifact_id` it records; each request was sent with a token
  an attempt of its session obtained, which no 401 or 403 had dropped since; and an attempt that
  follows a possibly charged attempt of its case names the latest one in `repeat_of`, and no
  other attempt names one.
- **The tables,** in `cases/<case_id>/normalized/`: only a case with a succeeded attempt has
  them, and `settings.csv` never alone; each reads back as a valid table, labeled with the case's
  `case_id`, and drawn from that attempt's saved response and the configuration of the plan it
  ran under; and a `metrics.csv` the latest manifest doesn't list is exactly what the installed
  parser writes from that response.

An attempt with a start record and no attempt record is `running`, and one whose only record is
its authentication record stopped before its send. `SavedExperimentAttempt` reads each as the
resume's step 8 will record it: the first `succeeded` with a saved response and `unknown` without
one, possibly charged either way, and the second `failed`, not possibly charged, and
`completed_record` gives the attempt record step 8 writes. The case states, and the budget's
counts, read them the same way.

The check also prepares the tables a stopped run didn't write: for each case with a succeeded
attempt and no `settings.csv`, the rows its `metrics.csv` will hold, from the response's bytes the
check read, or that the response fails validation, and the original values from its plan's
configuration. So the resume writes them without reading anything again.

Nothing here writes, sends, or logs. A refusal is `input.not_a_run`, or
`artifact.unknown_schema_version` for a record whose schema version has no reader, and its
message names the problem and the file, by its path in the output directory, which holds no
configuration value, never a value.
"""

import json
import re
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Final, Literal, cast

from pydantic import BaseModel, ValidationError

from trialfolio.attempts import (
    ATTEMPT_RECORD,
    AUTHENTICATION_RECORD,
    START_RECORD,
    AttemptFile,
    AttemptRole,
    attempt_directory,
    provider_requests,
    request_detail,
)
from trialfolio.canonical import sha256_hex
from trialfolio.configuration import experiment_original_values, read_experiment_configuration
from trialfolio.contracts.attempt import (
    ArtifactReference,
    AttemptRecordV1_1,
    AuthenticationRecord,
    Exchange,
    ProviderMetadata,
    SavedResponse,
    StartRecordV1_1,
)
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    SCREEN_BACKTEST_REQUEST,
    ErrorDetail,
)
from trialfolio.contracts.experiment_manifest import (
    ExperimentArtifact,
    ExperimentArtifactRole,
    ExperimentManifest,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord, RecordedCase, SessionRecord
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION, MetricsRow
from trialfolio.display import visible
from trialfolio.errors import TrialFolioError
from trialfolio.normalization import (
    METRICS,
    METRICS_PATH,
    PARSER_VERSION,
    SETTINGS_PATH,
    case_metrics_rows,
    case_tables_path,
)
from trialfolio.planning import plan_hash
from trialfolio.storage import ArtifactStore, StoredFile
from trialfolio.tables import metrics_csv, read_metrics_csv, read_settings_csv

LOCK_PATH: Final = "experiment.lock"
"""The file that claims an experiment's output directory, and on which the lock is taken."""

LOCK_LINE: Final = b"Trial Folio experiment lock: it claims this directory for one experiment.\n"
"""The lock file's one fixed line, so the file is never empty (docs/contracts.md, the lock)."""

CONFIGURATION: Final = "configuration.yaml"
PLAN: Final = "plan.json"
EXPERIMENT_RECORD: Final = "experiment.json"
SESSION_RECORD: Final = "session.json"
REPORT: Final = "report.html"
MANIFEST: Final = "manifest.json"
REQUEST: Final = "request.json"
RESPONSE: Final = "response.json"
RESPONSE_RAW: Final = "response.raw"


def plan_path(plan: int, name: str) -> str:
    """`plans/<plan>/<name>`, relative to the output root."""
    return f"plans/{plan}/{name}"


def session_path(session: int, name: str) -> str:
    """`sessions/<session>/<name>`, relative to the output root."""
    return f"sessions/{session}/{name}"


type CaseOutcome = Literal["succeeded", "failed", "unknown", "not_yet_run"]
type CaseState = Literal["complete", "due", "awaiting_repeat"]
type AttemptOutcome = Literal["succeeded", "failed", "unknown"]

_ATTEMPT_FILES: Final[dict[str, AttemptRole]] = {
    AUTHENTICATION_RECORD: "authentication_record",
    REQUEST: "provider_request",
    START_RECORD: "start_record",
    RESPONSE: "provider_response",
    RESPONSE_RAW: "provider_response_undecoded",
    ATTEMPT_RECORD: "attempt_record",
}
"""The files an attempt writes, in the order it writes them, with their roles."""

_NUMBER: Final = re.compile(r"[1-9][0-9]*")
_CASE_ID: Final = re.compile(r"case-[0-9a-f]{16}")
_ATTEMPT_ID: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_METRIC_ROWS: Final = tuple((metric.subject, metric.metric_id, metric.unit) for metric in METRICS)
"""`metrics.csv`'s rows, in order, by subject and `metric_id`, with the unit the layout fixes."""
_TOKEN_DROPPED: Final = frozenset({401, 403})
"""The statuses after which the client drops its token, so a later request authenticates again."""

_READABLE: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "experiment_record": ("experiment records", ("1.0.0",)),
    "plan": ("plans", ("1.1.0",)),
    "session_record": ("session records", ("1.0.0",)),
    "manifest": ("experiment manifests", ("1.0.0",)),
    "authentication_record": ("authentication records", ("1.0.0",)),
    "start_record": ("start records", ("1.1.0",)),
    "attempt_record": ("attempt records", ("1.1.0",)),
    "configuration": ("experiment configurations", ("1.0.0",)),
    "metrics": ("metrics.csv", (TABLES_SCHEMA_VERSION,)),
    "settings": ("settings.csv", (TABLES_SCHEMA_VERSION,)),
}
"""The schema versions this version reads, for each kind of record, with what they're called in
messages."""


# Case outcomes (docs/contracts.md, the experiment manifest)


@dataclass(frozen=True)
class CaseAttempt:
    """What a case's outcome reads of one of its attempts."""

    session: int
    sequence: int
    outcome: Literal["running", "succeeded", "failed", "unknown"]
    """`running` for a start record without an attempt record."""
    possibly_charged: bool
    valid: bool
    """For a succeeded attempt, whether its response passed validation."""


def case_outcome(attempts: Sequence[CaseAttempt]) -> CaseOutcome:
    """A case's outcome, as the manifest counts it: `succeeded` when one of its attempts
    succeeded with a valid response, and `failed` when that response failed validation;
    otherwise the outcome of its latest possibly charged attempt, by session and then sequence,
    with a `running` one counted as `unknown`; `failed` when it has attempts and none is
    possibly charged; and `not_yet_run` when it has none."""
    succeeded = [attempt for attempt in attempts if attempt.outcome == "succeeded"]
    if succeeded:
        return "succeeded" if any(attempt.valid for attempt in succeeded) else "failed"
    charged = [attempt for attempt in attempts if attempt.possibly_charged]
    if charged:
        latest = max(charged, key=lambda attempt: (attempt.session, attempt.sequence))
        return "failed" if latest.outcome == "failed" else "unknown"
    return "failed" if attempts else "not_yet_run"


# What a resume reads


@dataclass(frozen=True)
class SavedPlan:
    """A plan of the experiment: `plans/<number>/`, with its `experiment.json`."""

    number: int
    plan: PlanV1_1
    record: ExperimentRecord
    configuration: StoredFile
    configuration_content: bytes
    files: tuple[tuple[ExperimentArtifactRole, StoredFile], ...]
    """Its `configuration.yaml`, `plan.json`, and `experiment.json`, in the order they're
    written."""
    configuration_version: str
    """The schema version of its `configuration.yaml`, which its manifest entry records."""

    def case(self, case_id: str) -> ExperimentPlanCase:
        """The plan's case with this `case_id`. Raises `KeyError` when it has none."""
        for case in self.plan.cases:
            if case.case_id == case_id:
                return case
        raise KeyError(case_id)


@dataclass(frozen=True)
class SavedExperimentAttempt:
    """An attempt of the experiment, as its records read: an attempt record, or, without one, a
    start record, which reads as `running`, or only its authentication record. The outcome and
    the counts read an attempt without its attempt record as step 8 will record it."""

    case_id: str
    attempt_id: uuid.UUID
    plan: int
    """The number of the plan it ran under."""
    session: int
    sequence: int
    repeat_of: uuid.UUID | None
    authentication: AuthenticationRecord | None
    start: StartRecordV1_1 | None
    record: AttemptRecordV1_1 | None
    files: tuple[AttemptFile, ...]
    """Each file of its directory, in the order the attempt writes them."""
    response: tuple[SavedResponse, bytes] | None
    """The saved response its attempt record references, or, without an attempt record, the one
    its directory holds, with its bytes."""

    @property
    def directory(self) -> str:
        return attempt_directory(self.case_id, self.attempt_id)

    @property
    def outcome(self) -> AttemptOutcome:
        """Its attempt record's, or the one step 8 will record: `succeeded` for a `running`
        attempt with a saved response, `unknown` for one without, and `failed` for one with only
        its authentication record."""
        if self.record is not None:
            return self.record.outcome
        if self.start is not None:
            return "succeeded" if self.response is not None else "unknown"
        return "failed"

    @property
    def possibly_charged(self) -> bool:
        """Whether its request may have reached Portfolio123: a `running` attempt's may have,
        and one with only its authentication record sent nothing."""
        if self.record is not None:
            return self.record.possibly_charged
        return self.start is not None

    @property
    def error_code(self) -> str | None:
        """Its attempt record's error code, or the one step 8 will record."""
        if self.record is not None:
            return None if self.record.error is None else self.record.error.code
        return None if self.outcome == "succeeded" else "command.interrupted"

    @property
    def provider_requests(self) -> int:
        """The sends the budget counts: a `running` attempt's request is one."""
        if self.record is not None:
            return provider_requests(self.record)
        return 1 if self.start is not None else 0

    @property
    def authentication_calls(self) -> int:
        """Trial Folio's own authentication calls the budget counts: the `POST /auth` exchanges
        of its attempt record, or of its start record when it has no attempt record yet, or one
        when its authentication record is its only record (the budget across runs)."""
        if self.record is not None:
            return _authentications(self.record.exchanges)
        if self.start is not None:
            return _authentications(self.start.exchanges)
        return 1

    def completed_record(self, plan: PlanV1_1, ended_at: datetime) -> AttemptRecordV1_1:
        """The attempt record a resume writes for this attempt, which has none, keeping its
        records' contents, `session`, `sequence`, and `repeat_of` (docs/contracts.md, uncertain
        completion, and experiment attempts). `plan` is the plan it ran under, and `ended_at`
        when the record is written, or its start time when the clock reads earlier.

        - **A `running` attempt with a saved response** is `succeeded`: its request's exchange is
          recorded as a `response` with status 200 and the note `completed_from_saved_response`.
        - **A `running` attempt without one** is `unknown`, possibly charged, with its start
          record's exchanges, and `command.interrupted`, as an interrupt during the send gives.
        - **An attempt with only its authentication record** is `failed`, not possibly charged,
          with `command.interrupted`, and its one exchange, the authentication call's, recorded
          as `interrupted`. A `request.json` it wrote isn't referenced.

        Raises `ValueError` when it has an attempt record.
        """
        if self.record is not None:
            raise ValueError("the attempt has its attempt record")
        ended_at = max(ended_at, self.started_at)
        start = self.start
        if start is None:
            return AttemptRecordV1_1.model_validate(
                {
                    **self._identity(),
                    "authenticated_by": None,
                    "repeat_of": self.repeat_of,
                    "started_at": self.started_at,
                    "provider_wrapper": plan.provider_wrapper,
                    "transport": plan.transport,
                    "ended_at": ended_at,
                    "outcome": "failed",
                    "error": ErrorDetail(
                        code="command.interrupted",
                        message=(
                            "The run that started the attempt stopped while it authenticated,"
                            " before its request was sent."
                            f" {request_detail('failed', possibly_charged=False)}"
                        ),
                    ),
                    "exchanges": (
                        Exchange(
                            request=AUTHENTICATION_REQUEST,
                            result="interrupted",
                            status=None,
                            note=None,
                        ),
                    ),
                    "possibly_charged": False,
                    "request": None,
                    "response": None,
                    "provider_metadata": ProviderMetadata(cost=None, quota_remaining=None),
                }
            )
        request = next(file.file for file in self.files if file.role == "provider_request")
        reference = ArtifactReference(path=request.path, artifact_id=request.artifact_id)
        common = {
            **self._identity(),
            "authenticated_by": start.authenticated_by,
            "repeat_of": start.repeat_of,
            "started_at": start.started_at,
            "provider_wrapper": start.provider_wrapper,
            "transport": start.transport,
            "ended_at": ended_at,
            "possibly_charged": True,
            "request": reference,
        }
        if self.response is None:
            return AttemptRecordV1_1.model_validate(
                {
                    **common,
                    "outcome": "unknown",
                    "error": ErrorDetail(
                        code="command.interrupted",
                        message=(
                            "The run that started the attempt stopped after its start record was"
                            " written, before a response was saved."
                            f" {request_detail('unknown', possibly_charged=True)}"
                        ),
                    ),
                    "exchanges": start.exchanges,
                    "response": None,
                    "provider_metadata": ProviderMetadata(cost=None, quota_remaining=None),
                }
            )
        saved, content = self.response
        return AttemptRecordV1_1.model_validate(
            {
                **common,
                "outcome": "succeeded",
                "error": None,
                "exchanges": (
                    *start.exchanges,
                    Exchange(
                        request=SCREEN_BACKTEST_REQUEST,
                        result="response",
                        status=200,
                        note="completed_from_saved_response",
                    ),
                ),
                "response": saved,
                "provider_metadata": _metadata(saved, content),
            }
        )

    @property
    def started_at(self) -> datetime:
        records = (self.record, self.start, self.authentication)
        return next(record.started_at for record in records if record is not None)

    def _identity(self) -> dict[str, object]:
        records = (self.start, self.authentication)
        version = next(record.trialfolio_version for record in records if record is not None)
        plan_hash_ = next(record.plan_hash for record in records if record is not None)
        return {
            "schema_version": "1.1.0",
            "trialfolio_version": version,
            "attempt_id": self.attempt_id,
            "case_id": self.case_id,
            "plan_hash": plan_hash_,
            "session": self.session,
            "sequence": self.sequence,
        }


@dataclass(frozen=True)
class SavedTables:
    """A case's normalized tables, as the check read them."""

    metrics: StoredFile
    metrics_rows: tuple[MetricsRow, ...]
    settings: StoredFile | None
    """None when a stopped run wrote `metrics.csv` alone."""
    parser_version: int
    """The parser that wrote `metrics.csv`: the one the latest manifest names, when it lists the
    table, and otherwise the installed one, which the check found writes it."""


@dataclass(frozen=True)
class MissingTables:
    """What a resume writes for a case whose succeeded attempt has no `settings.csv`: both
    tables, or `settings.csv` beside a `metrics.csv` a stopped run wrote."""

    attempt: SavedExperimentAttempt
    case: ExperimentPlanCase
    """The case as the plan its attempt ran under holds it."""
    configuration: StoredFile
    """That plan's `configuration.yaml`."""
    originals: Mapping[str, tuple[str, str]]
    """Each setting's key path and text in that configuration."""
    response: SavedResponse
    content: bytes
    """The response's bytes, as the check read them."""
    metrics_rows: tuple[MetricsRow, ...] | None
    """The rows the installed parser writes to `metrics.csv` from the response, when the case
    has none yet; None when it has, or when the response fails validation."""
    invalid: TrialFolioError | None
    """The `provider.response_invalid` the response gets, when the case has no `metrics.csv`."""


@dataclass(frozen=True)
class SavedCase:
    """A case of a plan, and what the experiment's records say of it (the cases that are due)."""

    case: ExperimentPlanCase
    attempts: tuple[SavedExperimentAttempt, ...]
    """Every attempt of the case, under any plan, by session and then sequence."""
    valid: bool
    """Whether its succeeded attempt's response passed validation, or will once a resume writes
    its tables, when it has one."""

    @property
    def state(self) -> CaseState:
        """`complete` when one of its attempts succeeded; `awaiting_repeat` when one is possibly
        charged and none succeeded, so only a confirmed repeat sends it; and `due` otherwise, so
        a resume sends it."""
        if any(attempt.outcome == "succeeded" for attempt in self.attempts):
            return "complete"
        if any(attempt.possibly_charged for attempt in self.attempts):
            return "awaiting_repeat"
        return "due"

    @property
    def latest_charged(self) -> SavedExperimentAttempt | None:
        """Its latest possibly charged attempt, whose `attempt_id` confirms a repeat."""
        charged = [attempt for attempt in self.attempts if attempt.possibly_charged]
        return charged[-1] if charged else None

    @property
    def outcome(self) -> CaseOutcome:
        """As the manifest counts it."""
        return case_outcome(
            tuple(
                CaseAttempt(a.session, a.sequence, a.outcome, a.possibly_charged, valid=self.valid)
                for a in self.attempts
            )
        )


@dataclass(frozen=True)
class SavedExperiment:
    """An experiment's records, read and checked.

    The store it was read from holds the experiment lock, when `open_experiment` read it, until
    its owner closes it, so the records don't change while a resume uses them.
    """

    plans: tuple[SavedPlan, ...]
    """Each plan with its `experiment.json`, by number. The last is the current plan."""
    sessions: tuple[SessionRecord, ...]
    """Each session with its session record, by number."""
    attempts: tuple[SavedExperimentAttempt, ...]
    """Every attempt, of every case, retired ones included, by session and then sequence."""
    tables: Mapping[str, SavedTables]
    """Each case's tables, by `case_id`."""
    missing: Mapping[str, MissingTables]
    """What a resume writes for each case whose succeeded attempt has no `settings.csv`, by
    `case_id`."""
    manifest: ExperimentManifest | None
    """The latest manifest; None when no session has one."""
    next_plan: int
    """The number a revision's `plans/<n>/` takes: one more than the largest in the directory,
    with or without its `experiment.json`."""
    next_session: int
    """The number the next session takes, as `next_plan`."""

    @property
    def current(self) -> SavedPlan:
        """The current plan: the highest-numbered one with an `experiment.json`."""
        return self.plans[-1]

    @property
    def plan(self) -> PlanV1_1:
        return self.current.plan

    @property
    def record(self) -> ExperimentRecord:
        """The current plan's `experiment.json`, the experiment's research record."""
        return self.current.record

    @property
    def synthetic(self) -> bool:
        """Whether the experiment was executed with the demo's client: its plans record the
        approval `not_required`."""
        return self.record.plans[0].approval == "not_required"

    @property
    def provider_requests(self) -> int:
        """The sends counted against the budget, across every attempt of the experiment."""
        return sum(attempt.provider_requests for attempt in self.attempts)

    @property
    def authentication_calls(self) -> int:
        """Trial Folio's own authentication calls counted against the budget."""
        return sum(attempt.authentication_calls for attempt in self.attempts)

    def saved_plan(self, number: int) -> SavedPlan:
        """The plan with this number. Raises `KeyError` when there's none."""
        for saved in self.plans:
            if saved.number == number:
                return saved
        raise KeyError(number)

    def attempts_of(self, case_id: str) -> tuple[SavedExperimentAttempt, ...]:
        """The case's attempts, by session and then sequence."""
        return tuple(attempt for attempt in self.attempts if attempt.case_id == case_id)

    def cases(self, plan: PlanV1_1) -> tuple[SavedCase, ...]:
        """Each case of `plan`, the current plan or a revision of it, in its order, with what the
        records say of it."""
        return tuple(
            SavedCase(case, self.attempts_of(case.case_id), self.valid(case.case_id))
            for case in plan.cases
        )

    def valid(self, case_id: str) -> bool:
        """Whether the case's succeeded attempt's response passed validation, or will pass it
        when a resume writes its tables: it has `metrics.csv`, or the installed parser reads its
        response. True for a case without a succeeded attempt."""
        missing = self.missing.get(case_id)
        return missing is None or missing.invalid is None

    def listed(self, path: str) -> ExperimentArtifact | None:
        """The latest manifest's entry for the file at `path`, when it lists it."""
        if self.manifest is None:
            return None
        for artifact in self.manifest.artifacts:
            if artifact.path == path:
                return artifact
        return None


def open_experiment(store: ArtifactStore) -> SavedExperiment:
    """Takes the experiment lock on the output directory of `store`, and reads and checks its
    records, as `read_experiment` does (docs/contracts.md, a resumed experiment, steps 3 and 4).

    The store holds the lock until its owner closes it, whatever this raises, so the records
    can't change while the caller uses them.

    Raises `TrialFolioError` with `output.not_empty` when the directory holds no
    `experiment.lock`, so it isn't an experiment's; with `experiment.locked` when another process
    holds the lock; with `storage.write_failed` when the file system refuses it; and as
    `read_experiment` does.
    """
    try:
        store.lock(LOCK_PATH)
    except FileNotFoundError:
        raise TrialFolioError(
            "output.not_empty",
            "The output directory isn't empty, and it isn't an experiment's: it holds no"
            f" {LOCK_PATH}. Nothing was sent or written. Run the configuration into a new or"
            " empty output directory.",
        ) from None
    return read_experiment(store)


def read_experiment(store: ArtifactStore) -> SavedExperiment:
    """Reads the records of the experiment in the output directory of `store`, each file once,
    and checks them, as the module says. Writes nothing.

    Raises `TrialFolioError` with `input.not_a_run` when they aren't a complete, consistent
    experiment; with `artifact.unknown_schema_version` when a record, or the latest manifest's
    entry for one, has a schema version this version has no reader for; and with
    `output.not_empty` when the directory has no `plans/1/experiment.json`, because its first run
    stopped before anything was sent.
    """
    reader = _Reader(store)
    # The latest manifest's files first: one missing from an incomplete copy, the first plan's
    # included, is reported as missing.
    sessions, manifest_session, next_session = _sessions(reader)
    manifest = None if manifest_session is None else _latest_manifest(reader, manifest_session)
    plans, next_plan = _plans(reader)
    synthetic = plans[0].record.plans[0].approval == "not_required"
    if manifest is not None:
        _check_manifest(manifest, plans, synthetic=synthetic)
    attempts = _attempts(reader, plans, {record.session for record in sessions})
    _check_authentication(attempts)
    _check_repeats(attempts)
    listed = {} if manifest is None else {a.path: a for a in manifest.artifacts}
    plans = [_with_version(saved, listed) for saved in plans]
    since = tuple(
        record.trialfolio_version
        for record in sessions
        if manifest is None or record.session > manifest.session
    )
    tables = _tables(reader, plans, attempts, listed, since)
    missing = _missing(plans, attempts, tables)
    return SavedExperiment(
        plans=tuple(plans),
        sessions=tuple(sessions),
        attempts=tuple(attempts),
        tables=MappingProxyType(tables),
        missing=MappingProxyType(missing),
        manifest=manifest,
        next_plan=next_plan,
        next_session=next_session,
    )


# Reading


class _Reader:
    """Reads the output directory's files through the store, each once."""

    def __init__(self, store: ArtifactStore) -> None:
        self._store = store
        self._contents: dict[str, bytes | None] = {}

    def get(self, path: str) -> bytes | None:
        """The file's bytes, or None when there's no such file."""
        if path not in self._contents:
            try:
                self._contents[path] = self._store.read(path)
            except FileNotFoundError:
                self._contents[path] = None
            except OSError as error:
                raise _refused(f"{_named(path)} can't be read ({_reason(error)}).") from None
        return self._contents[path]

    def require(self, path: str) -> bytes:
        content = self.get(path)
        if content is None:
            raise _refused(f"{_named(path)} is missing.")
        return content

    def names(self, path: str) -> tuple[str, ...]:
        """The names in the directory, apart from hidden ones: a store's temporary files, which a
        stopped write can leave, and a file system's own. Empty when there's no such
        directory."""
        try:
            found = self._store.entries(path)
        except FileNotFoundError:
            return ()
        except NotADirectoryError:
            raise _refused(f"{_named(path)} isn't a directory.") from None
        except OSError as error:
            raise _refused(f"{_named(path)} can't be read ({_reason(error)}).") from None
        return tuple(name for name in found if not name.startswith("."))

    def numbered(self, path: str) -> list[int]:
        """The numbers of the directories in `plans/` or `sessions/`, in order."""
        names = self.names(path)
        if any(not _NUMBER.fullmatch(name) for name in names):
            raise _refused(f"{_named(path + '/')} holds an entry that isn't a numbered directory.")
        return sorted(int(name) for name in names)


def _plans(reader: _Reader) -> tuple[list[SavedPlan], int]:
    numbers = reader.numbered("plans")
    if 1 not in numbers or EXPERIMENT_RECORD not in reader.names("plans/1"):
        raise TrialFolioError(
            "output.not_empty",
            "The output directory holds an experiment whose first run stopped before its first"
            " plan was recorded, so nothing was sent, and it can't be resumed. Remove the"
            " directory, and run the command again.",
        )
    plans: list[SavedPlan] = []
    for number in numbers:
        names = reader.names(f"plans/{number}")
        if set(names) - {CONFIGURATION, PLAN, EXPERIMENT_RECORD}:
            raise _refused(f"{_named(f'plans/{number}/')} holds a file no plan has.")
        if EXPERIMENT_RECORD in names:
            plans.append(_plan(reader, number, plans[-1] if plans else None))
    return plans, max(numbers) + 1


def _plan(reader: _Reader, number: int, previous: SavedPlan | None) -> SavedPlan:
    record_path = plan_path(number, EXPERIMENT_RECORD)
    record_content = reader.require(record_path)
    record = _model(ExperimentRecord, record_content, record_path, "experiment_record")
    path = plan_path(number, PLAN)
    content = reader.require(path)
    plan = _model(PlanV1_1, content, path, "plan")
    try:
        recomputed = plan_hash(plan)
    except ValueError as error:
        raise _refused(f"{_named(path)} can't be hashed ({error}).") from None
    if recomputed != plan.plan_hash:
        raise _refused(
            f"{_named(path)} doesn't recompute to its plan_hash, so the plan changed after it was"
            " approved."
        )
    configuration_path = plan_path(number, CONFIGURATION)
    configuration = reader.require(configuration_path)
    entry = record.plans[-1]
    last = f"{_named(record_path)}'s last entry isn't its directory's plan"
    if entry.plan != number:
        raise _refused(f"{last}: it gives another number.")
    if entry.plan_hash != plan.plan_hash:
        raise _refused(f"{last}: it gives another plan_hash than its plan.json.")
    if (entry.plan_artifact_id, entry.configuration_artifact_id) != (
        _artifact_id(content),
        _artifact_id(configuration),
    ):
        raise _refused(
            f"{last}: its plan.json or configuration.yaml has another artifact_id than it records."
        )
    earlier = () if previous is None else previous.record.plans
    if record.plans[:-1] != earlier:
        raise _refused(
            f"{_named(record_path)}'s earlier entries aren't those of the previous plan's"
            " experiment.json."
        )
    if plan.revises != (None if previous is None else previous.plan.plan_hash):
        raise _refused(f"{_named(path)} doesn't revise the previous plan.")
    planned = tuple(
        RecordedCase(
            case_key=case.case_key,
            case_id=case.case_id,
            description=case.description,
            variant=case.variant,
        )
        for case in plan.cases
    )
    declared = (record.experiment_id, record.title, record.purpose, record.prior_research)
    if planned != record.planned_cases or declared != (
        plan.experiment_id,
        plan.title,
        plan.purpose,
        plan.prior_research,
    ):
        raise _refused(
            f"{_named(record_path)} doesn't record the experiment and its planned cases as its"
            " plan declares them."
        )
    if previous is not None and plan.experiment_id != previous.plan.experiment_id:
        raise _refused(f"{_named(path)} is another experiment's plan.")
    return SavedPlan(
        number=number,
        plan=plan,
        record=record,
        configuration=_stored(configuration_path, configuration),
        configuration_content=configuration,
        files=(
            ("configuration", _stored(configuration_path, configuration)),
            ("plan", _stored(path, content)),
            ("experiment_record", _stored(record_path, record_content)),
        ),
        configuration_version="",
    )


def _with_version(saved: SavedPlan, listed: Mapping[str, ExperimentArtifact]) -> SavedPlan:
    """`saved` with its configuration's schema version: the latest manifest's, when it lists the
    file, and otherwise the version the configuration gives, read as a configuration is."""
    path = saved.configuration.path
    entry = listed.get(path)
    if entry is not None and entry.schema_version is not None:
        return replace(saved, configuration_version=entry.schema_version)
    try:
        read = read_experiment_configuration(saved.configuration_content, path)
    except TrialFolioError:
        raise _refused(
            f"{_named(path)} isn't an experiment configuration this version reads."
        ) from None
    return replace(saved, configuration_version=read.schema_version)


def _sessions(reader: _Reader) -> tuple[list[SessionRecord], int | None, int]:
    numbers = reader.numbered("sessions")
    records: list[SessionRecord] = []
    manifest: int | None = None
    for number in numbers:
        names = reader.names(f"sessions/{number}")
        if set(names) - {SESSION_RECORD, REPORT, MANIFEST}:
            raise _refused(f"{_named(f'sessions/{number}/')} holds a file no session has.")
        if SESSION_RECORD in names:
            path = session_path(number, SESSION_RECORD)
            record = _model(SessionRecord, reader.require(path), path, "session_record")
            if record.session != number:
                raise _refused(f"{_named(path)} names another session than its directory's.")
            records.append(record)
        if MANIFEST in names:
            manifest = number
    return records, manifest, max(numbers, default=0) + 1


def _latest_manifest(reader: _Reader, session: int) -> ExperimentManifest:
    path = session_path(session, MANIFEST)
    content = reader.require(path)
    fields = _json_object(content, path)
    if fields.get("artifact_type") != "experiment":
        raise _refused(f"{_named(path)} isn't an experiment's manifest.")
    _check_version(fields.get("schema_version"), path, "manifest")
    manifest = _validated(ExperimentManifest, content, path, "experiment manifest")
    if manifest.session != session:
        raise _refused(f"{_named(path)} names another session than its directory's.")
    for artifact in manifest.artifacts:
        if artifact.schema_version is not None and artifact.role in _READABLE:
            _check_version(artifact.schema_version, artifact.path, artifact.role, listed=True)
        listed = reader.get(artifact.path)
        if listed is None:
            raise _refused(
                f"the latest manifest, {_named(path)}, lists {_named(artifact.path)}, which is"
                " missing."
            )
        if len(listed) != artifact.size or _artifact_id(listed) != artifact.artifact_id:
            raise _refused(
                f"{_named(artifact.path)} doesn't match its artifact_id in the latest manifest,"
                " so it changed after the session wrote it."
            )
    return manifest


def _check_manifest(
    manifest: ExperimentManifest, plans: Sequence[SavedPlan], *, synthetic: bool
) -> None:
    path = session_path(manifest.session, MANIFEST)
    if manifest.experiment_id != plans[0].plan.experiment_id:
        raise _refused(f"{_named(path)} is another experiment's manifest.")
    named = [saved for saved in plans if saved.number == manifest.plan]
    if not named or named[0].plan.plan_hash != manifest.plan_hash:
        raise _refused(f"{_named(path)} names a plan the experiment doesn't have.")
    if manifest.synthetic and not synthetic:
        raise _refused(
            f"{_named(path)} is synthetic, though the experiment's plans don't record the"
            " approval not_required."
        )
    if synthetic and not manifest.synthetic:
        raise _refused(
            f"{_named(path)} isn't synthetic, though the experiment's plans record the approval"
            " not_required."
        )


def _attempts(
    reader: _Reader, plans: Sequence[SavedPlan], sessions: set[int]
) -> list[SavedExperimentAttempt]:
    by_hash = {saved.plan.plan_hash: saved for saved in plans}
    attempts: list[SavedExperimentAttempt] = []
    for case_id in reader.names("cases"):
        if not _CASE_ID.fullmatch(case_id):
            raise _refused(f"{_named('cases/')} holds an entry that isn't a case's directory.")
        names = reader.names(f"cases/{case_id}")
        if set(names) - {"attempts", "normalized"}:
            raise _refused(f"{_named(f'cases/{case_id}/')} holds an entry no case has.")
        for name in reader.names(f"cases/{case_id}/attempts"):
            if not _ATTEMPT_ID.fullmatch(name):
                raise _refused(
                    f"{_named(f'cases/{case_id}/attempts/')} holds an entry that isn't an"
                    " attempt's directory."
                )
            attempt = _attempt(reader, case_id, uuid.UUID(name), by_hash, sessions)
            if attempt is not None:
                attempts.append(attempt)
    attempts.sort(key=lambda attempt: (attempt.session, attempt.sequence))
    for (session, sequence), count in Counter((a.session, a.sequence) for a in attempts).items():
        if count > 1:
            raise _refused(
                f"two attempts of session {session} have the same sequence, {sequence}, though a"
                " session starts its attempts one at a time."
            )
    return attempts


def _attempt(
    reader: _Reader,
    case_id: str,
    attempt_id: uuid.UUID,
    plans: Mapping[str, SavedPlan],
    sessions: set[int],
) -> SavedExperimentAttempt | None:
    """The attempt in this directory, or None when it has none of its records, as after a
    process killed before it wrote its first: there's no record of the attempt then."""
    directory = attempt_directory(case_id, attempt_id)
    names = reader.names(directory)
    if set(names) - set(_ATTEMPT_FILES):
        raise _refused(f"{_named(directory + '/')} holds a file no attempt writes.")

    def read[M: BaseModel](name: str, model: type[M], kind: str) -> M | None:
        if name not in names:
            return None
        path = f"{directory}/{name}"
        return _model(model, reader.require(path), path, kind)

    authentication = read(AUTHENTICATION_RECORD, AuthenticationRecord, "authentication_record")
    start = read(START_RECORD, StartRecordV1_1, "start_record")
    record = read(ATTEMPT_RECORD, AttemptRecordV1_1, "attempt_record")
    present = [r for r in (authentication, start, record) if r is not None]
    if not present:
        return None
    disagree = f"the records in {_named(directory + '/')} don't agree"
    if any((r.case_id, r.attempt_id) != (case_id, attempt_id) for r in present):
        raise _refused(f"the records in {_named(directory + '/')} name another attempt.")
    shared = ("trialfolio_version", "plan_hash", "session", "sequence", "repeat_of", "started_at")
    if len({tuple(getattr(r, field) for field in shared) for r in present}) > 1:
        raise _refused(f"{disagree}: they give it another plan, place, or start.")
    _check_agreement(authentication, start, record, disagree)
    first = present[0]
    saved = plans.get(first.plan_hash)
    if saved is None:
        raise _refused(
            f"the records in {_named(directory + '/')} name a plan the experiment doesn't have."
        )
    if case_id not in {case.case_id for case in saved.plan.cases}:
        raise _refused(
            f"the records in {_named(directory + '/')} name a case their plan doesn't have."
        )
    if first.session not in sessions:
        raise _refused(
            f"the records in {_named(directory + '/')} name a session the experiment doesn't have."
        )
    files = tuple(
        AttemptFile(role, _stored(f"{directory}/{name}", reader.require(f"{directory}/{name}")))
        for name, role in _ATTEMPT_FILES.items()
        if name in names
    )
    contents = {file.file.path: file.file for file in files}
    response = _response(reader, directory, names, start, record, contents)
    return SavedExperimentAttempt(
        case_id=case_id,
        attempt_id=attempt_id,
        plan=saved.number,
        session=first.session,
        sequence=first.sequence,
        repeat_of=first.repeat_of,
        authentication=authentication,
        start=start,
        record=record,
        files=files,
        response=response,
    )


def _check_agreement(
    authentication: AuthenticationRecord | None,
    start: StartRecordV1_1 | None,
    record: AttemptRecordV1_1 | None,
    disagree: str,
) -> None:
    """The records agree with each other: the attempt record holds its start record's contents,
    and an attempt that authenticated wrote its authentication record first."""
    if start is not None and record is not None:
        # Their exchanges then agree too: both name the same `authenticated_by`, and the models
        # hold an attempt that authenticated to one successful `POST /auth` exchange, first, and
        # one sent with another's token to none.
        fields = set(StartRecordV1_1.model_fields) - {"exchanges"}
        if record.model_dump(include=fields) != start.model_dump(include=fields):
            raise _refused(f"{disagree}: the attempt record doesn't hold its start record's.")
    if start is None and record is not None and record.authenticated_by is not None:
        raise _refused(f"{disagree}: the attempt record names a token, without a start record.")
    if start is not None and (authentication is not None) != bool(start.exchanges):
        raise _refused(
            f"{disagree}: an attempt authenticates exactly when it has its authentication record."
        )
    if (
        record is not None
        and authentication is None
        and any(e.request == AUTHENTICATION_REQUEST for e in record.exchanges)
    ):
        raise _refused(
            f"{disagree}: the attempt authenticated without writing its authentication record."
        )


def _response(
    reader: _Reader,
    directory: str,
    names: Sequence[str],
    start: StartRecordV1_1 | None,
    record: AttemptRecordV1_1 | None,
    files: Mapping[str, StoredFile],
) -> tuple[SavedResponse, bytes] | None:
    """The saved response the attempt record references, with each file it references checked;
    or, for a `running` attempt, the one its directory holds, with its request checked."""
    if record is not None:
        references: list[ArtifactReference] = []
        if record.request is not None:
            references.append(record.request)
        if record.response is not None:
            references.append(record.response)
        for reference in references:
            stored = files.get(reference.path)
            if stored is None:
                raise _refused(
                    f"the attempt record in {_named(directory + '/')} references a file that isn't"
                    " in its directory."
                )
            if stored.artifact_id != reference.artifact_id:
                raise _refused(
                    f"{_named(reference.path)} doesn't match the artifact_id its attempt record"
                    " gives it."
                )
        if record.response is None:
            return None
        return record.response, reader.require(record.response.path)
    if start is None:
        return None
    if REQUEST not in names:
        raise _refused(
            f"{_named(directory + '/')} has a start record, but not the request.json written"
            " before it."
        )
    saved = [name for name in (RESPONSE, RESPONSE_RAW) if name in names]
    if len(saved) > 1:
        raise _refused(f"{_named(directory + '/')} holds two saved responses.")
    if not saved:
        return None
    path = f"{directory}/{saved[0]}"
    content = reader.require(path)
    response = SavedResponse(
        path=path,
        artifact_id=_artifact_id(content),
        form="decoded" if saved[0] == RESPONSE else "undecoded",
    )
    return response, content


def _check_authentication(attempts: Sequence[SavedExperimentAttempt]) -> None:
    """Each request was sent with a token that an attempt of its session obtained, itself or an
    earlier one, and that no 401 or 403 to an earlier request sent with it had dropped."""
    by_id = {attempt.attempt_id: attempt for attempt in attempts}
    for attempt in attempts:
        if attempt.start is None:
            continue
        origin = by_id.get(attempt.start.authenticated_by)
        if (
            origin is None
            or origin.session != attempt.session
            or origin.sequence > attempt.sequence
            or not _authenticated(origin)
        ):
            raise _refused(
                f"the request of {_named(attempt.directory + '/')} was sent with a token no"
                " attempt of its session obtained before it."
            )
        for earlier in attempts:
            if (
                earlier.session == attempt.session
                and earlier.sequence < attempt.sequence
                and earlier.start is not None
                and earlier.start.authenticated_by == origin.attempt_id
                and _token_dropped(earlier)
            ):
                raise _refused(
                    f"the request of {_named(attempt.directory + '/')} was sent with a token that"
                    " a 401 or 403 to an earlier request had dropped."
                )


def _authenticated(attempt: SavedExperimentAttempt) -> bool:
    exchanges = (
        attempt.record.exchanges
        if attempt.record is not None
        else attempt.start.exchanges
        if attempt.start is not None
        else ()
    )
    return any(e.request == AUTHENTICATION_REQUEST and e.status == 200 for e in exchanges)


def _token_dropped(attempt: SavedExperimentAttempt) -> bool:
    if attempt.record is None:
        return False
    return any(
        e.request != AUTHENTICATION_REQUEST and e.status in _TOKEN_DROPPED
        for e in attempt.record.exchanges
    )


def _check_repeats(attempts: Sequence[SavedExperimentAttempt]) -> None:
    """An attempt that follows a possibly charged attempt of its case, by session and then
    sequence, names the latest such attempt in `repeat_of`, and no other attempt names one. No
    attempt follows its case's succeeded attempt: a complete case is never sent again."""
    by_case: dict[str, list[SavedExperimentAttempt]] = {}
    for attempt in attempts:
        by_case.setdefault(attempt.case_id, []).append(attempt)
    for group in by_case.values():
        latest: SavedExperimentAttempt | None = None
        succeeded = False
        for attempt in group:
            directory = _named(attempt.directory + "/")
            if succeeded:
                raise _refused(
                    f"{directory} follows its case's succeeded attempt, and a complete case is"
                    " never sent again."
                )
            expected = None if latest is None else latest.attempt_id
            if attempt.repeat_of != expected:
                if attempt.repeat_of is None:
                    raise _refused(
                        f"{directory} was started after an attempt of its case whose request may"
                        " have been charged, without a confirmed repeat of it."
                    )
                raise _refused(
                    f"{directory} names in repeat_of an attempt that isn't its case's latest"
                    " whose request may have been charged."
                )
            if attempt.possibly_charged:
                latest = attempt
            succeeded = attempt.outcome == "succeeded"


def _tables(
    reader: _Reader,
    plans: Sequence[SavedPlan],
    attempts: Sequence[SavedExperimentAttempt],
    listed: Mapping[str, ExperimentArtifact],
    since: Sequence[str],
) -> dict[str, SavedTables]:
    tables: dict[str, SavedTables] = {}
    numbered = {saved.number: saved for saved in plans}
    for case_id in reader.names("cases"):
        names = reader.names(f"cases/{case_id}/normalized")
        if set(names) - {"metrics.csv", "settings.csv"}:
            raise _refused(f"{_named(f'cases/{case_id}/normalized/')} holds a file no case has.")
        if not names:
            continue
        metrics_path = case_tables_path(case_id, METRICS_PATH)
        settings_path = case_tables_path(case_id, SETTINGS_PATH)
        if "metrics.csv" not in names:
            raise _refused(f"{_named(settings_path)} is there without its metrics.csv.")
        succeeded = [
            a
            for a in attempts
            if a.case_id == case_id and a.record is not None and a.record.outcome == "succeeded"
        ]
        if not succeeded:
            raise _refused(
                f"{_named(f'cases/{case_id}/')} has normalized tables, but no succeeded attempt."
            )
        (attempt,) = succeeded
        response = cast("tuple[SavedResponse, bytes]", attempt.response)
        saved = numbered[attempt.plan]
        case = saved.case(case_id)
        content = reader.require(metrics_path)
        metrics = _table_rows(read_metrics_csv, content, metrics_path)
        if any(row.label != case_id for row in metrics):
            raise _refused(f"{_named(metrics_path)} labels its rows with another case.")
        if tuple((row.subject, row.metric_id, row.unit) for row in metrics) != _METRIC_ROWS:
            raise _refused(
                f"{_named(metrics_path)} doesn't hold one row for each of the layout's metrics, in"
                " order, each in the metric's unit."
            )
        if any(row.source_artifact != response[0].artifact_id for row in metrics):
            raise _refused(
                f"{_named(metrics_path)} was drawn from another response than its case's"
                " succeeded attempt's."
            )
        entry = listed.get(metrics_path)
        if entry is None:
            _check_parser(content, case, response, metrics_path, since)
        settings: StoredFile | None = None
        if "settings.csv" in names:
            settings_content = reader.require(settings_path)
            rows = _table_rows(read_settings_csv, settings_content, settings_path)
            if any(row.label != case_id for row in rows):
                raise _refused(f"{_named(settings_path)} labels its rows with another case.")
            if tuple(row.setting for row in rows) != tuple(s.setting for s in case.settings):
                raise _refused(
                    f"{_named(settings_path)} doesn't hold one row for each of its plan's"
                    " settings, in order."
                )
            if any(row.source_artifact != saved.configuration.artifact_id for row in rows):
                raise _refused(
                    f"{_named(settings_path)} was drawn from another configuration than that of"
                    " the plan its case's attempt ran under."
                )
            settings = _stored(settings_path, settings_content)
        tables[case_id] = SavedTables(
            metrics=_stored(metrics_path, content),
            metrics_rows=metrics,
            settings=settings,
            parser_version=_parser_of(response[0].path, listed),
        )
    return tables


def _parser_of(response: str, listed: Mapping[str, ExperimentArtifact]) -> int:
    """The parser the latest manifest names for a response whose table it lists."""
    entry = listed.get(response)
    if entry is None or entry.source is None or entry.source.parser_version is None:
        return PARSER_VERSION
    return entry.source.parser_version


def _check_parser(
    content: bytes,
    case: ExperimentPlanCase,
    response: tuple[SavedResponse, bytes],
    path: str,
    since: Sequence[str],
) -> None:
    """A `metrics.csv` no manifest lists was written by a session that stopped before its end,
    and no record names its parser, so it must be what the installed parser writes."""
    try:
        expected = metrics_csv(case_metrics_rows(response[1], case, response[0]))
    except TrialFolioError:
        expected = None
    if content != expected:
        versions = ", ".join(sorted(set(since))) or "unknown"
        raise _refused(
            f"{_named(path)}, which no session's manifest lists, isn't what this version's parser"
            " writes from its response, as after an upgrade whose parser reads it differently."
            " Resume the experiment first with the version of Trial Folio that wrote it, one of"
            f" those the sessions since the latest manifest record ({versions}), so that a"
            " session's manifest names its parser."
        )


def _missing(
    plans: Sequence[SavedPlan],
    attempts: Sequence[SavedExperimentAttempt],
    tables: Mapping[str, SavedTables],
) -> dict[str, MissingTables]:
    """For each case whose succeeded attempt has no `settings.csv`, what a resume writes: the
    response's rows, read from the bytes the check read, and its plan's original values."""
    numbered = {saved.number: saved for saved in plans}
    missing: dict[str, MissingTables] = {}
    for attempt in attempts:
        saved_tables = tables.get(attempt.case_id)
        if attempt.outcome != "succeeded" or (
            saved_tables is not None and saved_tables.settings is not None
        ):
            continue
        response, content = cast("tuple[SavedResponse, bytes]", attempt.response)
        saved = numbered[attempt.plan]
        case = saved.case(attempt.case_id)
        rows: tuple[MetricsRow, ...] | None = None
        invalid: TrialFolioError | None = None
        if saved_tables is None:
            try:
                rows = case_metrics_rows(content, case, response)
            except TrialFolioError as error:
                invalid = error
        if invalid is None:
            try:
                originals = experiment_original_values(
                    saved.configuration_content, saved.configuration.path, case.case_key
                )
            except (TrialFolioError, ValueError):
                raise _refused(
                    f"{_named(saved.configuration.path)} isn't a configuration this version reads"
                    " for its case, so the tables a stopped run didn't write can't be written."
                ) from None
        else:
            originals: Mapping[str, tuple[str, str]] = {}
        missing[attempt.case_id] = MissingTables(
            attempt=attempt,
            case=case,
            configuration=saved.configuration,
            originals=MappingProxyType(originals),
            response=response,
            content=content,
            metrics_rows=rows,
            invalid=invalid,
        )
    return missing


# Checking a file


def _model[M: BaseModel](model: type[M], content: bytes, path: str, kind: str) -> M:
    """The record in `content`, checked against its schema version, then its model."""
    _check_version(_json_object(content, path).get("schema_version"), path, kind)
    return _validated(model, content, path, _READABLE[kind][0].removesuffix("s"))


def _json_object(content: bytes, path: str) -> dict[str, object]:
    try:
        loaded: object = json.loads(content)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _refused(f"{_named(path)} isn't JSON.") from None
    if not isinstance(loaded, dict):
        raise _refused(f"{_named(path)} isn't a JSON object.")
    return cast("dict[str, object]", loaded)


def _check_version(version: object, path: str, kind: str, *, listed: bool = False) -> None:
    """Checks a schema version, from the file itself or, when `listed`, from the latest
    manifest's entry for it."""
    name, readable = _READABLE[kind]
    if version in readable:
        return
    if not isinstance(version, str):
        raise _refused(f"{_named(path)} has no schema version.")
    where = "the latest manifest gives it" if listed else "it has"
    raise TrialFolioError(
        "artifact.unknown_schema_version",
        f"Trial Folio can't read {_named(path)} in the output directory: {where} a schema version"
        f" this version has no reader for. It reads {name} {' or '.join(readable)}. Resume the"
        " experiment with a version of Trial Folio that has one. Nothing was sent or written.",
    )


def _validated[M: BaseModel](model: type[M], content: bytes, path: str, what: str) -> M:
    try:
        return model.model_validate_json(content)
    except ValidationError as error:
        # Only the model's own fields are named: an unexpected key is text from the file.
        details = error.errors(include_url=False, include_input=False, include_context=False)
        named = sorted(
            {
                str(detail["loc"][0])
                for detail in details
                if detail["loc"] and detail["loc"][0] in model.model_fields
            }
        )
        check = f"check `{'`, `'.join(named)}`" if named else "check its fields"
        raise _refused(f"{_named(path)} isn't a valid {what}: {check}.") from None


def _table_rows[R](
    reader: Callable[[bytes, str], tuple[R, ...]], content: bytes, path: str
) -> tuple[R, ...]:
    try:
        return reader(content, f"its {_named(path)}")
    except TrialFolioError as error:
        # The tables' messages name the line and the column, never a value.
        raise _refused(error.message) from None


def _metadata(response: SavedResponse, content: bytes) -> ProviderMetadata:
    """`cost` and `quotaRemaining` from the top level of a saved decoded response, as the
    attempt that saved it would have recorded them."""
    if response.form == "undecoded":
        return ProviderMetadata(cost=None, quota_remaining=None)
    try:
        payload: object = json.loads(content)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return ProviderMetadata(cost=None, quota_remaining=None)
    if not isinstance(payload, dict):
        return ProviderMetadata(cost=None, quota_remaining=None)
    fields = cast("dict[str, object]", payload)
    return ProviderMetadata(
        cost=_count(fields.get("cost")), quota_remaining=_count(fields.get("quotaRemaining"))
    )


def _count(value: object) -> int | None:
    # A bool is an int in Python, and never a count.
    return value if type(value) is int and value >= 0 else None


def _authentications(exchanges: Sequence[Exchange]) -> int:
    return sum(exchange.request == AUTHENTICATION_REQUEST for exchange in exchanges)


def _stored(path: str, content: bytes) -> StoredFile:
    return StoredFile(path=path, artifact_id=_artifact_id(content), size=len(content))


def _artifact_id(content: bytes) -> str:
    return "sha256:" + sha256_hex(content)


def _named(path: str) -> str:
    return f"`{visible(path)}`"


def _reason(error: OSError) -> str:
    return error.strerror or type(error).__name__


def _refused(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "input.not_a_run",
        f"The output directory doesn't hold a complete, consistent Trial Folio experiment:"
        f" {problem} Nothing was sent or written. Restore the experiment's records from a"
        " complete copy, or run the configuration into a new output directory.",
    )
