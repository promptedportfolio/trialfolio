"""Attempt recording: the start record, the exchange record, and the attempt record
(docs/contracts.md, execution outcomes and attempts, uncertain completion, endings that decide the
error code, and interrupts).

An `Attempt` is one execution of a plan's case. The command creates it once it has claimed the
output directory, and it ends once. `Attempt.run` carries out steps 8 and 9 of `trialfolio run`
(docs/contracts.md, approval), writing each file into `cases/<case_id>/attempts/<attempt_id>/`:

1. It authenticates with Trial Folio's own call.
2. It writes the redacted request, `request.json`: the request's `params`, which hold no
   credentials. That comes before the start record, so the start record is the last write before
   the send, and an attempt restarted with a saved response has a request to reference.
3. It writes the start record, `started.json`, durably, with the directories that hold it. From
   here on, without an attempt record, the attempt reads as `running`.
4. It sends the request, at most once.
5. It saves the response: `response.json`, or `response.raw` for a 200 the wrapper couldn't decode.
6. It writes the attempt record, `attempt.json`, whatever ended the attempt.

`Attempt.end_before_authenticating` ends an attempt that stopped before step 1, for example after
an interrupt just after the claim, with an attempt record only. Neither method raises for an
ending it records: a provider failure, a storage failure, a user interrupt, or an unexpected
exception. Each returns an `AttemptResult`, whose `error` is the one the command reports. Only a
second interrupt, while the attempt record is written once more after a first, gets through.

An `ExperimentAttempt` is one attempt of an experiment's case, with start and attempt records
1.1.0 (docs/contracts.md, experiment attempts). The attempts of a session share one client, so
one that sends with the token an earlier attempt obtained skips step 1, and one that
authenticates first writes its authentication record, `authenticating.json`, durably before the
call. Its records name its session, its place in it, the attempt whose authentication gave its
token, and the attempt a repeat repeats. Both kinds of attempt write their files, and end, the
same way.

No file is written twice, and none is replaced. The outcome follows the request's exchange and
whether the response was saved. An interrupt or a storage failure decides only the error code.

- **`request.json`** is `json.dumps` of the `params` sent, indented. `requests` writes the body
  with the same function, unindented, so each number's text is the body's. Non-ASCII text is
  escaped, as in the body.
- **`response.json`** is `json.dumps` of the decoded value, on one line. Unindented, `json` uses
  its C encoder, which nests as deep as the C decoder that read the value; the Python encoder
  that indenting uses could run out of recursion first. Non-ASCII text is escaped, so a lone
  surrogate the decoder accepted is written back as it came. So are `NaN` and `Infinity`.
- **`provider_metadata`** takes `cost` and `quotaRemaining` from the top level of a decoded
  response. Each is null when it's absent or isn't a non-negative integer.
- **Logs** name the plan hash, the case, and the attempt, and give the outcome, the error code,
  and the duration. For an unexpected exception they give its type and frames, never its message,
  which could hold a value.
"""

import json
import logging
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal, TypedDict, cast

from pydantic import BaseModel

from trialfolio.canonical import sha256_hex
from trialfolio.contracts.attempt import (
    ArtifactReference,
    AttemptRecord,
    AttemptRecordV1_1,
    AuthenticationRecord,
    Exchange,
    ProviderMetadata,
    SavedResponse,
    StartRecord,
    StartRecordV1_1,
)
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    ErrorDetail,
    TransportVersions,
    WrapperVersions,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, PlanV1_1
from trialfolio.contracts.plan import Plan
from trialfolio.errors import TrialFolioError
from trialfolio.planning import check_approval
from trialfolio.provider import (
    DecodedResponse,
    ProviderError,
    ScreenBacktestClient,
    ScreenBacktestResponse,
    UndecodedResponse,
)
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger(__name__)

type Clock = Callable[[], datetime]
"""Gives the current time in UTC. Tests inject a fixed one."""

type Outcome = Literal["succeeded", "failed", "unknown"]

type AttemptRole = Literal[
    "authentication_record",
    "start_record",
    "attempt_record",
    "provider_request",
    "provider_response",
    "provider_response_undecoded",
]
"""The role of each file an attempt writes, as a manifest lists it. Only an experiment's attempts
write an authentication record."""

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of a screen run's start records and attempt records."""

EXPERIMENT_SCHEMA_VERSION: Final = "1.1.0"
"""The schema version of an experiment's start records and attempt records."""

AUTHENTICATION_SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the authentication records an experiment's attempts write."""

AUTHENTICATION_RECORD: Final = "authenticating.json"
START_RECORD: Final = "started.json"
ATTEMPT_RECORD: Final = "attempt.json"


def utc_now() -> datetime:
    """The current time in UTC: the clock the installed command uses."""
    return datetime.now(UTC)


def attempt_directory(case_id: str, attempt_id: uuid.UUID) -> str:
    """`cases/<case_id>/attempts/<attempt_id>`, relative to the output root."""
    return f"cases/{case_id}/attempts/{attempt_id}"


@dataclass(frozen=True)
class AttemptFile:
    """A file an attempt wrote, with its role in the manifest."""

    role: AttemptRole
    file: StoredFile


@dataclass(frozen=True)
class AttemptResult:
    """How an attempt ended."""

    record: AttemptRecord
    """The attempt record: as written, or, when `recorded` is false, as it would have been."""
    recorded: bool
    """Whether `attempt.json` was written. If it wasn't, an attempt with a start record reads as
    `running`."""
    files: tuple[AttemptFile, ...]
    """Every file the attempt wrote, in order."""
    response: ScreenBacktestResponse | None
    """The saved response, exactly when the attempt succeeded. An undecoded one is a success for
    capture; normalizing it flags `provider.response_invalid`."""
    error: TrialFolioError | None
    """The error the command reports, or None. It's the record's, unless an interrupt or a storage
    failure decided the code, which it can even when the attempt succeeded."""


@dataclass(frozen=True)
class AttemptStatus:
    """How a saved attempt reads (uncertain completion)."""

    attempt_id: uuid.UUID
    outcome: Literal["running", "succeeded", "failed", "unknown"]
    """`running` for a start record without an attempt record; otherwise the record's."""
    possibly_charged: bool
    provider_requests: int
    """The sends of the request that may have reached Portfolio123, never authentication."""


def provider_requests(record: AttemptRecord | AttemptRecordV1_1) -> int:
    """The sends of the request that may have reached Portfolio123: its exchanges other than
    authentication that aren't `not_connected`. An attempt restarted without a saved response is
    `unknown` with only its start record's exchange, and counts as one (uncertain completion)."""
    sends = [e for e in record.exchanges if e.request != AUTHENTICATION_REQUEST]
    if not sends and record.outcome == "unknown":
        return 1
    return sum(1 for e in sends if e.result != "not_connected")


def read_attempt(store: ArtifactStore, case_id: str, attempt_id: uuid.UUID) -> AttemptStatus | None:
    """Reads how a saved attempt reads: from its attempt record, or, without one, from its start
    record, as `running`, possibly charged, with one provider request. Returns None when it has
    neither, as after a process killed before it wrote the start record.

    Raises `ValueError`, pydantic's `ValidationError` included, when a record isn't valid, names
    another attempt, or the attempt record doesn't hold its start record's contents; and
    `OSError` when one can't be read.
    """
    directory = attempt_directory(case_id, attempt_id)
    start = _read(store, f"{directory}/{START_RECORD}", StartRecord)
    record = _read(store, f"{directory}/{ATTEMPT_RECORD}", AttemptRecord)
    check_records(start, record, case_id, attempt_id)
    return attempt_status(start, record)


def check_records(
    start: StartRecord | None, record: AttemptRecord | None, case_id: str, attempt_id: uuid.UUID
) -> None:
    """Checks that an attempt's records belong together, in the directory of `case_id` and
    `attempt_id`.

    Raises `ValueError` when a record names another attempt than its directory, or the attempt
    record doesn't hold its start record's contents.
    """
    for read in (start, record):
        if read is not None and (read.case_id, read.attempt_id) != (case_id, attempt_id):
            raise ValueError("the record names another attempt than its directory")
    if record is not None and start is not None:
        shared = set(StartRecord.model_fields) - {"exchanges"}
        if record.model_dump(include=shared) != start.model_dump(include=shared) or (
            record.exchanges[: len(start.exchanges)] != start.exchanges
        ):
            raise ValueError("the attempt record doesn't hold its start record's contents")


def attempt_status(start: StartRecord | None, record: AttemptRecord | None) -> AttemptStatus | None:
    """How an attempt with these records reads: from its attempt record, or, without one, from its
    start record, as `running`, possibly charged, with one provider request. None when it has
    neither."""
    if record is not None:
        return AttemptStatus(
            attempt_id=record.attempt_id,
            outcome=record.outcome,
            possibly_charged=record.possibly_charged,
            provider_requests=provider_requests(record),
        )
    if start is not None:
        # The request is sent at most once, so a start record is one possible send.
        return AttemptStatus(
            attempt_id=start.attempt_id,
            outcome="running",
            possibly_charged=True,
            provider_requests=1,
        )
    return None


class _Identity(TypedDict):
    """The fields the start record and the attempt record share."""

    schema_version: Literal["1.0.0"]
    trialfolio_version: str
    attempt_id: uuid.UUID
    case_id: str
    plan_hash: str
    started_at: datetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions


@dataclass(frozen=True)
class _Ending:
    """What the request's exchange, and whether the response was saved, give the attempt."""

    outcome: Outcome
    possibly_charged: bool

    @property
    def detail(self) -> str:
        """What it says about the request, for a message."""
        return request_detail(self.outcome, possibly_charged=self.possibly_charged)


def request_detail(outcome: Outcome, *, possibly_charged: bool) -> str:
    """What an attempt with this outcome says about the request, for a message: whether it was
    sent, and whether it may have been charged, as the attempt record does."""
    if outcome == "succeeded":
        return "The screen backtest request succeeded, and its response was saved."
    if outcome == "unknown":
        return (
            "The screen backtest request may have been charged, and its outcome is unknown: no"
            " response was saved. Trial Folio never retries it automatically: check the account's"
            " API credits on Portfolio123's website before running the command again."
        )
    if possibly_charged:
        return "The screen backtest request reached Portfolio123, and may have been charged."
    return "The screen backtest request wasn't sent."


class _AttemptFiles:
    """An attempt's directory, `cases/<case_id>/attempts/<attempt_id>/`, for either version of its
    records: it writes each file once, never replacing one, saves the response, and ends the
    attempt with its attempt record, whatever ended it."""

    def __init__(
        self,
        store: ArtifactStore,
        directory: str,
        log_fields: Callable[[str], dict[str, str]],
        *,
        synthetic: bool,
    ) -> None:
        self._store = store
        self._directory = directory
        self._log_fields = log_fields
        self._synthetic = synthetic
        self._started = time.monotonic()
        self._files: list[AttemptFile] = []
        self.request: StoredFile | None = None
        self.response: tuple[StoredFile, ScreenBacktestResponse] | None = None

    @property
    def files(self) -> tuple[AttemptFile, ...]:
        """Every file written so far, in order."""
        return tuple(self._files)

    def write(
        self, name: str, data: bytes, role: AttemptRole, *, list_published: bool = False
    ) -> StoredFile:
        """Writes `name`, and lists it. With `list_published`, a write that fails after the store
        published the file, whatever the failure, lists it all the same, so a manifest written
        later lists every file the attempt wrote."""
        try:
            stored = self._store.write(f"{self._directory}/{name}", data)
        except BaseException:
            if list_published:
                self.published(name, data, role)
            raise
        self._files.append(AttemptFile(role, stored))
        return stored

    def write_request(self, params: dict[str, object], *, list_published: bool = False) -> None:
        self.request = self.write(
            "request.json", _request_json(params), "provider_request", list_published=list_published
        )

    def save(self, response: ScreenBacktestResponse, *, list_published: bool = False) -> None:
        match response:
            case DecodedResponse(payload=payload):
                stored = self.write(
                    "response.json",
                    _response_json(payload),
                    "provider_response",
                    list_published=list_published,
                )
            case UndecodedResponse(body=body):
                stored = self.write(
                    "response.raw",
                    body,
                    "provider_response_undecoded",
                    list_published=list_published,
                )
        self.response = (stored, response)

    def published(self, name: str, data: bytes, role: AttemptRole) -> bool:
        """Whether an interrupted write of `name` published it whole. If it did, it's listed."""
        path = f"{self._directory}/{name}"
        try:
            published = self._store.read(path) == data
        except OSError:
            return False
        if published:
            stored = StoredFile(path=path, artifact_id="sha256:" + sha256_hex(data), size=len(data))
            self._files.append(AttemptFile(role, stored))
        return published

    def end[R: (AttemptRecord, AttemptRecordV1_1)](
        self,
        exchanges: tuple[Exchange, ...],
        ending: BaseException | None,
        record: Callable[["_Ending", TrialFolioError | None], R],
    ) -> tuple[R, bool, TrialFolioError | None]:
        """Classifies the attempt from its exchanges, and whether its response was saved, and
        writes the attempt record `record` builds from that and the command's error. Returns the
        record, whether it was written, and the command's error."""
        sends = [e for e in exchanges if e.request != AUTHENTICATION_REQUEST]
        outcome = _outcome(sends[0] if sends else None, saved=self.response is not None)
        end = _Ending(
            outcome=outcome,
            possibly_charged=outcome == "unknown"
            or any(e.result != "not_connected" for e in sends),
        )
        if ending is not None and not isinstance(ending, KeyboardInterrupt | TrialFolioError):
            self.log_unexpected(ending)
        error = _error(ending, end)
        recorded, error, written = self._write_record(record(end, error), error, end)
        charged = "yes" if written.possibly_charged else "no"
        if self._synthetic and written.possibly_charged:
            charged = "yes, in its invented records, though nothing was sent"
        _logger.log(
            logging.INFO if error is None else logging.ERROR,
            "Attempt ended %s after %.3f s: %s; possibly charged: %s; attempt record written: %s.",
            written.outcome,
            time.monotonic() - self._started,
            "no error" if error is None else error.code,
            charged,
            "yes" if recorded else "no",
            extra=self._log_fields("attempt.completed"),
        )
        return written, recorded, error

    def saved(self, end: "_Ending") -> tuple[StoredFile, ScreenBacktestResponse] | None:
        """The saved response, exactly when the attempt succeeded."""
        return self.response if end.outcome == "succeeded" else None

    def ending_fields(
        self, end: "_Ending", error: TrialFolioError | None, ended_at: datetime
    ) -> "_EndingFields":
        """The fields of the attempt record that say how it ended, in either version."""
        saved = self.saved(end)
        return _EndingFields(
            ended_at=ended_at,
            outcome=end.outcome,
            error=None if saved is not None or error is None else _detail_of(error),
            possibly_charged=end.possibly_charged,
            request=None if self.request is None else _reference(self.request),
            response=None if saved is None else _saved_response(*saved),
            provider_metadata=_metadata(None if saved is None else saved[1]),
        )

    def _write_record[R: (AttemptRecord, AttemptRecordV1_1)](
        self, record: R, error: TrialFolioError | None, end: "_Ending"
    ) -> tuple[bool, TrialFolioError | None, R]:
        """Writes the attempt record. Returns whether it was written, the command's error, and the
        record, which an interrupt can change before it's written.

        After an interrupt while it's written, a record that was published is left as it is.
        Otherwise it's written once more, with `command.interrupted` unless it succeeded.
        """
        data = _model_json(record)
        try:
            self.write(ATTEMPT_RECORD, data, "attempt_record")
        except KeyboardInterrupt:
            error = prevailing(_interrupted(end), error)
            if self.published(ATTEMPT_RECORD, data, "attempt_record"):
                return True, error, record
            if record.error is not None:
                record = record.model_copy(update={"error": _detail_of(error)})
            return self._write_again(record), error, record
        except TrialFolioError as failure:
            return False, prevailing(_with_detail(failure, end), error), record
        # Unwritten, the start record, if any, reads as running.
        except Exception as failure:  # noqa: BLE001
            self.log_unexpected(failure)
            return False, prevailing(_unexpected(failure, end), error), record
        return True, error, record

    def _write_again(self, record: BaseModel) -> bool:
        try:
            self.write(ATTEMPT_RECORD, _model_json(record), "attempt_record")
        # The interrupt's code stays; unwritten, the start record, if any, reads as running.
        except Exception as failure:  # noqa: BLE001
            if not isinstance(failure, TrialFolioError):
                self.log_unexpected(failure)
            return False
        return True

    def log_unexpected(self, error: BaseException) -> None:
        # Its type and frames only: its message could hold a value, which logs never do.
        _logger.error(
            "Unexpected %s during the attempt, at:\n%s",
            type(error).__name__,
            "".join(traceback.format_tb(error.__traceback__)),
            extra=self._log_fields("attempt.unexpected"),
        )


class _EndingFields(TypedDict):
    """The fields of an attempt record, of either version, that say how the attempt ended."""

    ended_at: datetime
    outcome: Outcome
    error: ErrorDetail | None
    possibly_charged: bool
    request: ArtifactReference | None
    response: SavedResponse | None
    provider_metadata: ProviderMetadata


class Attempt:
    """One attempt of the case of an approved plan, writing into a claimed output directory.

    The plan must have been built in this process, from the installed versions: the records name
    its versions as the ones that sent the request. The properties stay readable whatever
    happens, so a command interrupted again while the attempt ends still knows its ID and what it
    wrote.
    """

    def __init__(
        self,
        plan: Plan,
        approved_hash: str,
        store: ArtifactStore,
        *,
        clock: Clock = utc_now,
        synthetic: bool = False,
    ) -> None:
        """Starts the attempt: gives it an ID and its start time. Writes nothing.

        `synthetic` is for the attempt of the run `trialfolio demo` writes, which sends nothing.
        Its records are a real attempt's. Where they say it's possibly charged, its progress says
        they're invented.

        Raises `TrialFolioError` with `plan.approval_required` unless `approved_hash` is the
        plan's hash, recomputed from its contents (approval), and `ValueError` if `clock` doesn't
        give a UTC time.
        """
        plan_hash = check_approval(plan, approved_hash)
        (case,) = plan.cases
        (request,) = case.requests
        self._attempt_id = uuid.uuid4()
        self._identity = _Identity(
            schema_version=SCHEMA_VERSION,
            trialfolio_version=plan.trialfolio_version,
            attempt_id=self._attempt_id,
            case_id=case.case_id,
            plan_hash=plan_hash,
            started_at=_utc(clock()),
            provider_wrapper=plan.provider_wrapper,
            transport=plan.transport,
        )
        self._params: dict[str, object] = request.params.model_dump(mode="json")
        self._clock = clock
        self._directory = attempt_directory(case.case_id, self._attempt_id)
        self._files = _AttemptFiles(store, self._directory, self._log_fields, synthetic=synthetic)
        self._start: StartRecord | None = None
        self._ended = False
        _logger.info("Attempt started.", extra=self._log_fields("attempt.started"))

    @property
    def attempt_id(self) -> uuid.UUID:
        return self._attempt_id

    @property
    def case_id(self) -> str:
        return self._identity["case_id"]

    @property
    def plan_hash(self) -> str:
        return self._identity["plan_hash"]

    @property
    def started_at(self) -> datetime:
        return self._identity["started_at"]

    @property
    def directory(self) -> str:
        """`cases/<case_id>/attempts/<attempt_id>`, relative to the output root."""
        return self._directory

    @property
    def files(self) -> tuple[AttemptFile, ...]:
        """Every file written so far, in order."""
        return self._files.files

    @property
    def start_record(self) -> StartRecord | None:
        """The start record, once it's written."""
        return self._start

    def run(self, client: ScreenBacktestClient) -> AttemptResult:
        """Authenticates, writes the request and the start record, sends the request once, saves
        the response, and writes the attempt record, as the module says.

        `client` must be new: its exchanges are the attempt's. Raises `RuntimeError` if the
        attempt has already ended or the client has made an exchange, and `KeyboardInterrupt`
        only as the module says.
        """
        if client.exchanges:
            raise RuntimeError("an attempt needs a new client: its exchanges are the attempt's")
        self._end_once()
        ending: BaseException | None = None
        try:
            client.authenticate()
            self._files.write_request(self._params)
            # Exactly the authentication exchange; the model refuses anything else.
            exchanges = cast("tuple[Exchange]", client.exchanges)
            start = StartRecord(**self._identity, exchanges=exchanges)
            self._files.write(START_RECORD, _model_json(start), "start_record")
            self._start = start
            self._files.save(client.screen_backtest(self._params))
        except KeyboardInterrupt as interrupt:
            ending = interrupt
        # Every ending is recorded. An unexpected one is classified, and logged by its frames.
        except Exception as error:  # noqa: BLE001
            ending = error
        return self._end(client.exchanges, ending)

    def end_before_authenticating(self, ending: BaseException) -> AttemptResult:
        """Writes the attempt record of an attempt that ended after the claim and before it
        authenticated, as `failed`, not possibly charged: for example after an interrupt, or a
        failure to write `configuration.yaml` (interrupts).

        `ending` gives the error: `command.interrupted` for a `KeyboardInterrupt`, the code of a
        `TrialFolioError`, and `internal.unexpected` for anything else. Raises `RuntimeError` if
        the attempt has already ended, and `KeyboardInterrupt` only as the module says.
        """
        self._end_once()
        return self._end((), ending)

    def _end_once(self) -> None:
        if self._ended:
            raise RuntimeError("an attempt ends once")
        self._ended = True

    def _end(self, exchanges: tuple[Exchange, ...], ending: BaseException | None) -> AttemptResult:
        def record(end: _Ending, error: TrialFolioError | None) -> AttemptRecord:
            fields = self._files.ending_fields(end, error, _utc(self._clock()))
            return AttemptRecord(**self._identity, **fields, exchanges=exchanges)

        written, recorded, error = self._files.end(exchanges, ending, record)
        saved = self._files.response if written.outcome == "succeeded" else None
        return AttemptResult(
            record=written,
            recorded=recorded,
            files=self.files,
            response=None if saved is None else saved[1],
            error=error,
        )

    def _log_fields(self, event: str) -> dict[str, str]:
        return {
            "event": event,
            "plan_hash": self._identity["plan_hash"],
            "case_id": self._identity["case_id"],
            "attempt_id": str(self._attempt_id),
        }


@dataclass(frozen=True)
class ExperimentAttemptResult:
    """How an experiment's attempt ended."""

    record: AttemptRecordV1_1
    """The attempt record: as written, or, when `recorded` is false, as it would have been."""
    recorded: bool
    """Whether `attempt.json` was written. If it wasn't, an attempt with a start record reads as
    `running`, and one with only its authentication record stopped before its send."""
    start: StartRecordV1_1 | None
    """The start record, when it was written."""
    files: tuple[AttemptFile, ...]
    """Every file the attempt wrote, in order."""
    response: ScreenBacktestResponse | None
    """The saved response, exactly when the attempt succeeded."""
    error: TrialFolioError | None
    """The error the session reports for this attempt, or None. It's the record's, unless an
    interrupt or a storage failure decided the code."""
    authenticated: bool
    """Whether the attempt made Trial Folio's own authentication call, so the budget counts it."""
    authentication_failed: bool
    """Whether that call failed, whatever its result, which stops the session (D-32)."""


class ExperimentAttempt:
    """One attempt of an experiment's case, in a session that holds the experiment lock
    (docs/contracts.md, experiment attempts). Its start and attempt records are version 1.1.0.

    A session authenticates once, and again only after a 401 or 403 drops its token, so the
    session's attempts share one client: an attempt sends with the token an earlier attempt
    obtained, or authenticates first, writing its authentication record, `authenticating.json`,
    durably before the call, so the budget counts the call even if the process is killed during
    it. It then writes its files in a run's order: `request.json`, `started.json`, the response,
    and `attempt.json`, whatever ended it. Its records name its session, its place in the
    session, `sequence`, the attempt whose authentication gave its token, `authenticated_by`,
    and the attempt a repeat repeats, `repeat_of`.

    A file before the attempt record that the store published before its write failed, whatever
    the failure, is in `files` all the same, so the session's manifest lists every file the
    attempt wrote. The attempt record references a request or a response only when its write
    completed, so a 200 whose `response.json` was published that way is `unknown`, as one whose
    save failed.

    The properties stay readable whatever happens, as an `Attempt`'s do.
    """

    def __init__(
        self,
        plan: PlanV1_1,
        case: ExperimentPlanCase,
        store: ArtifactStore,
        *,
        session: int,
        sequence: int,
        repeat_of: uuid.UUID | None = None,
        clock: Clock = utc_now,
        synthetic: bool = False,
    ) -> None:
        """Starts the attempt of `case`, one of the approved `plan`'s cases, as the `sequence`th
        attempt of `session`: gives it an ID and its start time. Writes nothing.

        `repeat_of` is the attempt a confirmed repeat names, and `synthetic` is for an
        experiment executed with the demo's client, which sends nothing. Raises `ValueError` if
        `case` isn't one of the plan's, or `clock` doesn't give a UTC time.
        """
        if case not in plan.cases:
            raise ValueError("the attempt's case is one of the plan's")
        (request,) = case.requests
        self._attempt_id = uuid.uuid4()
        self._case_id = case.case_id
        self._plan_hash = plan.plan_hash
        self._version = plan.trialfolio_version
        self._session = session
        self._sequence = sequence
        self._repeat_of = repeat_of
        self._started_at = _utc(clock())
        self._wrapper = plan.provider_wrapper
        self._transport = plan.transport
        self._params: dict[str, object] = request.params.model_dump(mode="json")
        self._clock = clock
        self._directory = attempt_directory(case.case_id, self._attempt_id)
        self._files = _AttemptFiles(store, self._directory, self._log_fields, synthetic=synthetic)
        self._start: StartRecordV1_1 | None = None
        self._authenticated = False
        self._authentication_failed = False
        self._ended = False
        _logger.info("Attempt started.", extra=self._log_fields("attempt.started"))

    @property
    def attempt_id(self) -> uuid.UUID:
        return self._attempt_id

    @property
    def case_id(self) -> str:
        return self._case_id

    @property
    def directory(self) -> str:
        """`cases/<case_id>/attempts/<attempt_id>`, relative to the output root."""
        return self._directory

    @property
    def files(self) -> tuple[AttemptFile, ...]:
        """Every file written so far, in order."""
        return self._files.files

    @property
    def start_record(self) -> StartRecordV1_1 | None:
        """The start record, once it's written."""
        return self._start

    def run(
        self, client: ScreenBacktestClient, token_from: uuid.UUID | None
    ) -> ExperimentAttemptResult:
        """Sends the case's request once, with the session's `client`, and records the attempt.

        `token_from` is the attempt whose successful authentication gave the token the client
        holds, or None when it holds none: the attempt then authenticates first. Raises
        `RuntimeError` if the attempt has already ended, or `token_from` is given while the
        client holds no token; and `KeyboardInterrupt` only while the attempt record is written
        once more after an interrupt, as an `Attempt` does.
        """
        if token_from is not None and not client.authenticated:
            raise RuntimeError("the client holds no token to send with")
        if self._ended:
            raise RuntimeError("an attempt ends once")
        self._ended = True
        first = len(client.exchanges)
        ending: BaseException | None = None
        try:
            if token_from is None:
                self._authenticate(client)
                token_from = self._attempt_id
            self._files.write_request(self._params, list_published=True)
            start = StartRecordV1_1(
                **self._placed(),
                authenticated_by=token_from,
                repeat_of=self._repeat_of,
                started_at=self._started_at,
                provider_wrapper=self._wrapper,
                transport=self._transport,
                exchanges=client.exchanges[first:],
            )
            self._write_start(start)
            self._files.save(client.screen_backtest(self._params), list_published=True)
        except KeyboardInterrupt as interrupt:
            ending = interrupt
        # Every ending is recorded. An unexpected one is classified, and logged by its frames.
        except Exception as error:  # noqa: BLE001
            ending = error
        return self._end(client.exchanges[first:], ending)

    def _placed(self) -> "_Placed":
        return _Placed(
            schema_version=EXPERIMENT_SCHEMA_VERSION,
            trialfolio_version=self._version,
            attempt_id=self._attempt_id,
            case_id=self._case_id,
            plan_hash=self._plan_hash,
            session=self._session,
            sequence=self._sequence,
        )

    def _authenticate(self, client: ScreenBacktestClient) -> None:
        """Writes the authentication record durably, then makes Trial Folio's own
        authentication call."""
        record = AuthenticationRecord(
            schema_version=AUTHENTICATION_SCHEMA_VERSION,
            trialfolio_version=self._version,
            attempt_id=self._attempt_id,
            case_id=self._case_id,
            plan_hash=self._plan_hash,
            session=self._session,
            sequence=self._sequence,
            repeat_of=self._repeat_of,
            started_at=self._started_at,
        )
        self._files.write(
            AUTHENTICATION_RECORD, _model_json(record), "authentication_record", list_published=True
        )
        self._authenticated = True
        try:
            client.authenticate()
        except Exception:
            self._authentication_failed = True
            raise

    def _write_start(self, start: StartRecordV1_1) -> None:
        """Writes the start record. After a failure while it's written, an interrupt or a
        storage failure such as a sync after the store published it, a record that was
        published counts as written, so the attempt record agrees with it."""
        data = _model_json(start)
        try:
            self._files.write(START_RECORD, data, "start_record")
        except BaseException:
            if self._files.published(START_RECORD, data, "start_record"):
                self._start = start
            raise
        self._start = start

    def _end(
        self, exchanges: tuple[Exchange, ...], ending: BaseException | None
    ) -> ExperimentAttemptResult:
        def record(end: _Ending, error: TrialFolioError | None) -> AttemptRecordV1_1:
            fields = self._files.ending_fields(end, error, _utc(self._clock()))
            return AttemptRecordV1_1(
                **self._placed(),
                authenticated_by=None if self._start is None else self._start.authenticated_by,
                repeat_of=self._repeat_of,
                started_at=self._started_at,
                provider_wrapper=self._wrapper,
                transport=self._transport,
                **fields,
                exchanges=exchanges,
            )

        written, recorded, error = self._files.end(exchanges, ending, record)
        saved = self._files.response if written.outcome == "succeeded" else None
        return ExperimentAttemptResult(
            record=written,
            recorded=recorded,
            start=self._start,
            files=self.files,
            response=None if saved is None else saved[1],
            error=error,
            authenticated=self._authenticated,
            authentication_failed=self._authentication_failed,
        )

    def _log_fields(self, event: str) -> dict[str, str]:
        return {
            "event": event,
            "plan_hash": self._plan_hash,
            "case_id": self._case_id,
            "attempt_id": str(self._attempt_id),
        }


class _Placed(TypedDict):
    """The fields an experiment's start record and attempt record share, before
    `authenticated_by`: the attempt, its plan, and its place in its session."""

    schema_version: Literal["1.1.0"]
    trialfolio_version: str
    attempt_id: uuid.UUID
    case_id: str
    plan_hash: str
    session: int
    sequence: int


def _read[M: BaseModel](store: ArtifactStore, path: str, model: type[M]) -> M | None:
    try:
        content = store.read(path)
    except FileNotFoundError:
        return None
    return model.model_validate_json(content)


def _utc(moment: datetime) -> datetime:
    if moment.utcoffset() != timedelta(0):
        raise ValueError("the clock must give UTC times")
    return moment


def _outcome(send: Exchange | None, *, saved: bool) -> Outcome:
    """The outcome the request's exchange gives (execution outcomes, field shapes)."""
    if send is None or send.result == "not_connected":
        return "failed"
    if send.status is None or send.status >= 500:
        return "unknown"
    if send.status == 200:
        return "succeeded" if saved else "unknown"
    return "failed"


def _error(ending: BaseException | None, end: _Ending) -> TrialFolioError | None:
    """The command's error for how the attempt's steps ended."""
    match ending:
        case None if end.outcome == "succeeded":
            return None
        case None:
            return TrialFolioError(
                "internal.unexpected",
                "The attempt ended without an error, but didn't succeed. This is a defect in Trial"
                " Folio; please report it.",
            )
        case KeyboardInterrupt():
            return _interrupted(end)
        case ProviderError():
            # Its message already says whether the request may have been charged.
            return ending
        case TrialFolioError():
            return _with_detail(ending, end)
        case _:
            return _unexpected(ending, end)


def _interrupted(end: _Ending) -> TrialFolioError:
    return TrialFolioError("command.interrupted", f"Trial Folio was interrupted. {end.detail}")


def _with_detail(error: TrialFolioError, end: _Ending) -> TrialFolioError:
    return TrialFolioError(
        error.code, f"{error.message} {end.detail}", f"{error.log_message} {end.detail}"
    )


def _unexpected(error: BaseException, end: _Ending) -> TrialFolioError:
    """An ending no rule covers: `provider.outcome_unknown` when the request's outcome is
    unknown, and `internal.unexpected` otherwise (0.1.0's failure table). The message names only
    the exception's type, which can't carry a value."""
    return TrialFolioError(
        "provider.outcome_unknown" if end.outcome == "unknown" else "internal.unexpected",
        f"Trial Folio failed unexpectedly ({type(error).__name__}). {end.detail} This is a defect"
        " in Trial Folio; please report it.",
    )


def _rank(error: TrialFolioError) -> int:
    """Which error decides the code: an interrupt's, then a storage failure's, then an unexpected
    one's, then the provider's (endings that decide the error code)."""
    if error.code == "command.interrupted":
        return 3
    if error.code == "storage.write_failed":
        return 2
    return 0 if isinstance(error, ProviderError) else 1


def prevailing(error: TrialFolioError, earlier: TrialFolioError | None) -> TrialFolioError:
    """The error that decides the code, of `error` and the `earlier` one. When it's `error`, its
    message keeps the earlier one's, Portfolio123's own text included."""
    if earlier is None:
        return error
    if _rank(earlier) >= _rank(error):
        return earlier
    return TrialFolioError(
        error.code,
        f"{error.message} Before that: {earlier.message}",
        f"{error.log_message} Before that: {earlier.log_message}",
    )


def _detail_of(error: TrialFolioError) -> ErrorDetail:
    return ErrorDetail(code=error.code, message=error.message)


def _request_json(params: dict[str, object]) -> bytes:
    return (json.dumps(params, indent=2, allow_nan=False) + "\n").encode("ascii")


def _response_json(payload: object) -> bytes:
    return (json.dumps(payload) + "\n").encode("ascii")


def _model_json(model: BaseModel) -> bytes:
    return (model.model_dump_json(indent=2) + "\n").encode("utf-8")


def _reference(stored: StoredFile) -> ArtifactReference:
    return ArtifactReference(path=stored.path, artifact_id=stored.artifact_id)


def _saved_response(stored: StoredFile, response: ScreenBacktestResponse) -> SavedResponse:
    return SavedResponse(
        path=stored.path,
        artifact_id=stored.artifact_id,
        form="decoded" if isinstance(response, DecodedResponse) else "undecoded",
    )


def _metadata(response: ScreenBacktestResponse | None) -> ProviderMetadata:
    payload = response.payload if isinstance(response, DecodedResponse) else None
    if not isinstance(payload, dict):
        return ProviderMetadata(cost=None, quota_remaining=None)
    fields = cast("dict[str, object]", payload)
    return ProviderMetadata(
        cost=_count(fields.get("cost")), quota_remaining=_count(fields.get("quotaRemaining"))
    )


def _count(value: object) -> int | None:
    # A bool is an int in Python, and never a count.
    return value if type(value) is int and value >= 0 else None
