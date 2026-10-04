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
    Exchange,
    ProviderMetadata,
    SavedResponse,
    StartRecord,
)
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    ErrorDetail,
    TransportVersions,
    WrapperVersions,
)
from trialfolio.contracts.manifest import ArtifactRole
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

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the start records and attempt records this module writes."""

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

    role: ArtifactRole
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


def provider_requests(record: AttemptRecord) -> int:
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
        Its records are a real attempt's, possibly charged, and its progress says they're invented.

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
        self._store = store
        self._clock = clock
        self._synthetic = synthetic
        self._started = time.monotonic()
        self._directory = attempt_directory(case.case_id, self._attempt_id)
        self._files: list[AttemptFile] = []
        self._request: StoredFile | None = None
        self._response: tuple[StoredFile, ScreenBacktestResponse] | None = None
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
        return tuple(self._files)

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
            request = self._write("request.json", _request_json(self._params), "provider_request")
            self._request = request
            # Exactly the authentication exchange; the model refuses anything else.
            exchanges = cast("tuple[Exchange]", client.exchanges)
            start = StartRecord(**self._identity, exchanges=exchanges)
            self._write(START_RECORD, _model_json(start), "start_record")
            self._start = start
            self._save(client.screen_backtest(self._params))
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

    def _write(self, name: str, data: bytes, role: ArtifactRole) -> StoredFile:
        stored = self._store.write(f"{self._directory}/{name}", data)
        self._files.append(AttemptFile(role, stored))
        return stored

    def _save(self, response: ScreenBacktestResponse) -> None:
        match response:
            case DecodedResponse(payload=payload):
                stored = self._write("response.json", _response_json(payload), "provider_response")
            case UndecodedResponse(body=body):
                stored = self._write("response.raw", body, "provider_response_undecoded")
        self._response = (stored, response)

    def _end(self, exchanges: tuple[Exchange, ...], ending: BaseException | None) -> AttemptResult:
        sends = [e for e in exchanges if e.request != AUTHENTICATION_REQUEST]
        outcome = _outcome(sends[0] if sends else None, saved=self._response is not None)
        end = _Ending(
            outcome=outcome,
            possibly_charged=outcome == "unknown"
            or any(e.result != "not_connected" for e in sends),
        )
        if ending is not None and not isinstance(ending, KeyboardInterrupt | TrialFolioError):
            self._log_unexpected(ending)
        error = _error(ending, end)
        record = self._record(exchanges, end, error)
        recorded, error, record = self._write_record(record, error, end)
        charged = "yes" if record.possibly_charged else "no"
        if self._synthetic:
            charged = f"{charged}, in its invented records, though nothing was sent"
        _logger.log(
            logging.INFO if error is None else logging.ERROR,
            "Attempt ended %s after %.3f s: %s; possibly charged: %s; attempt record written: %s.",
            record.outcome,
            time.monotonic() - self._started,
            "no error" if error is None else error.code,
            charged,
            "yes" if recorded else "no",
            extra=self._log_fields("attempt.completed"),
        )
        saved = self._response if outcome == "succeeded" else None
        return AttemptResult(
            record=record,
            recorded=recorded,
            files=self.files,
            response=None if saved is None else saved[1],
            error=error,
        )

    def _record(
        self, exchanges: tuple[Exchange, ...], end: _Ending, error: TrialFolioError | None
    ) -> AttemptRecord:
        saved = self._response if end.outcome == "succeeded" else None
        return AttemptRecord(
            **self._identity,
            ended_at=_utc(self._clock()),
            outcome=end.outcome,
            error=None if saved is not None or error is None else _detail_of(error),
            exchanges=exchanges,
            possibly_charged=end.possibly_charged,
            request=None if self._request is None else _reference(self._request),
            response=None if saved is None else _saved_response(*saved),
            provider_metadata=_metadata(None if saved is None else saved[1]),
        )

    def _write_record(
        self, record: AttemptRecord, error: TrialFolioError | None, end: _Ending
    ) -> tuple[bool, TrialFolioError | None, AttemptRecord]:
        """Writes the attempt record. Returns whether it was written, the command's error, and the
        record, which an interrupt can change before it's written.

        After an interrupt while it's written, a record that was published is left as it is.
        Otherwise it's written once more, with `command.interrupted` unless it succeeded.
        """
        data = _model_json(record)
        try:
            self._write(ATTEMPT_RECORD, data, "attempt_record")
        except KeyboardInterrupt:
            error = prevailing(_interrupted(end), error)
            if self._published(data):
                return True, error, record
            if record.error is not None:
                record = record.model_copy(update={"error": _detail_of(error)})
            return self._write_again(record), error, record
        except TrialFolioError as failure:
            return False, prevailing(_with_detail(failure, end), error), record
        # Unwritten, the start record, if any, reads as running.
        except Exception as failure:  # noqa: BLE001
            self._log_unexpected(failure)
            return False, prevailing(_unexpected(failure, end), error), record
        return True, error, record

    def _write_again(self, record: AttemptRecord) -> bool:
        try:
            self._write(ATTEMPT_RECORD, _model_json(record), "attempt_record")
        # The interrupt's code stays; unwritten, the start record, if any, reads as running.
        except Exception as failure:  # noqa: BLE001
            if not isinstance(failure, TrialFolioError):
                self._log_unexpected(failure)
            return False
        return True

    def _published(self, data: bytes) -> bool:
        """Whether an interrupted write of the attempt record published it whole."""
        path = f"{self._directory}/{ATTEMPT_RECORD}"
        try:
            published = self._store.read(path) == data
        except OSError:
            return False
        if published:
            stored = StoredFile(path=path, artifact_id="sha256:" + sha256_hex(data), size=len(data))
            self._files.append(AttemptFile("attempt_record", stored))
        return published

    def _log_unexpected(self, error: BaseException) -> None:
        # Its type and frames only: its message could hold a value, which logs never do.
        _logger.error(
            "Unexpected %s during the attempt, at:\n%s",
            type(error).__name__,
            "".join(traceback.format_tb(error.__traceback__)),
            extra=self._log_fields("attempt.unexpected"),
        )

    def _log_fields(self, event: str) -> dict[str, str]:
        return {
            "event": event,
            "plan_hash": self._identity["plan_hash"],
            "case_id": self._identity["case_id"],
            "attempt_id": str(self._attempt_id),
        }


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
