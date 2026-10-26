"""How an attempt ends (docs/contracts.md, execution outcomes, endings that decide the error code,
and interrupts): `Ending`, what its exchanges, and whether its response was saved, give it; what
its messages say of its requests; `prevailing`, the error that decides the code; and
`AttemptEnding`, the ending policy, which writes the attempt record whatever ended the attempt,
and logs how it ended.

- **Logs** name the plan hash, the case, and the attempt, and give the outcome, the error code,
  and the duration. For an unexpected exception they give its type and frames, never its message,
  which could hold a value. They log as `trialfolio.attempts`, as the package's attempts do
  (docs/refactoring.md, decision 11).
"""

import logging
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, TypedDict

from pydantic import BaseModel

from trialfolio.attempts.files import (
    ATTEMPT_RECORD,
    AttemptFiles,
    reference,
    response_metadata,
    saved_response,
)
from trialfolio.attempts.reading import AnyAttemptRecord
from trialfolio.contracts.attempt import (
    ArtifactReference,
    AttemptRecord,
    AttemptRecordV1_1,
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    Exchange,
    ProviderMetadata,
    SavedResponse,
)
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    RANK_UPDATE_REQUEST,
    SCREEN_BACKTEST_REQUEST,
    ErrorDetail,
)
from trialfolio.errors import TrialFolioError, interrupted
from trialfolio.manifests import model_json
from trialfolio.provider import ProviderError

_logger = logging.getLogger("trialfolio.attempts")

type Outcome = Literal["succeeded", "failed", "unknown"]

BACKTEST_REQUEST_NAME: Final = "screen backtest request"
RANK_GET_REQUEST_NAME: Final = "rank_get request"
"""How messages name a snapshot's one request, as "the screen backtest request" names a run's."""


@dataclass(frozen=True)
class Ending:
    """What the request's exchange, and whether the response was saved, give the attempt."""

    outcome: Outcome
    possibly_charged: bool
    detail: str
    """What it says about the request, or an attempt with a definition's two, for a message."""


type Classifier = Callable[[tuple[Exchange, ...], bool], Ending]
"""How an attempt's exchanges, and whether its response was saved, end it: `one_request_ending`,
`snapshot_ending`, or `ranking_ending`."""


def one_request_ending(
    exchanges: tuple[Exchange, ...], saved: bool, name: str = BACKTEST_REQUEST_NAME
) -> Ending:
    """How an attempt with one request ended: as its exchange gives it (execution outcomes).
    `name` names the request in its detail, as `request_detail` takes it."""
    sends = [e for e in exchanges if e.request != AUTHENTICATION_REQUEST]
    outcome = _outcome(sends[0] if sends else None, saved=saved)
    charged = outcome == "unknown" or any(e.result != "not_connected" for e in sends)
    return Ending(outcome, charged, request_detail(outcome, possibly_charged=charged, name=name))


def snapshot_ending(exchanges: tuple[Exchange, ...], saved: bool) -> Ending:
    """How a snapshot's attempt ended: as its `rank_get`'s exchange gives it, as an attempt with
    one request ends."""
    return one_request_ending(exchanges, saved, name=RANK_GET_REQUEST_NAME)


def ranking_ending(exchanges: tuple[Exchange, ...], saved: bool) -> Ending:
    """How an attempt that sends a definition ended (sending a definition, the outcome): as its
    backtest's exchange gives it; without one, the backtest wasn't sent, and the attempt is
    `unknown` when its `rank_update`'s exchange is `interrupted` or got a 5xx, since the write may
    or may not have taken effect, and `failed` otherwise, after a 200 included."""
    rank = _first(exchanges, RANK_UPDATE_REQUEST)
    backtest = _first(exchanges, SCREEN_BACKTEST_REQUEST)
    if backtest is not None:
        outcome = _outcome(backtest, saved=saved)
    elif rank is not None and rank.result == "response" and rank.status is not None:
        outcome = "unknown" if rank.status >= 500 else "failed"
    else:
        outcome = "unknown" if rank is not None and rank.result == "interrupted" else "failed"
    sends = [e for e in (rank, backtest) if e is not None]
    charged = outcome == "unknown" or any(e.result != "not_connected" for e in sends)
    sent = backtest is not None and backtest.result != "not_connected"
    detail = ranking_detail(outcome, possibly_charged=charged, backtest_sent=sent)
    return Ending(outcome, charged, detail)


def _first(exchanges: tuple[Exchange, ...], request: str) -> Exchange | None:
    return next((e for e in exchanges if e.request == request), None)


def ranking_detail(outcome: Outcome, *, possibly_charged: bool, backtest_sent: bool) -> str:
    """What an attempt that sends a definition says about its two requests, for a message:
    whether each was sent, and whether it may have been charged, as its attempt record does.
    `backtest_sent` is whether its backtest may have reached Portfolio123."""
    update = (
        "The rank_update request, which writes the case's ranking definition into ApiRankingSystem,"
    )
    never = (
        "Trial Folio never retries it automatically: check the account's API credits on"
        " Portfolio123's website before running the command again."
    )
    if outcome == "succeeded":
        return (
            f"{update} and the screen backtest request succeeded, and their responses were saved."
        )
    if backtest_sent and outcome == "unknown":
        return (
            f"{update} succeeded. The screen backtest request may have been charged, and its"
            f" outcome is unknown: no response was saved. {never}"
        )
    if backtest_sent:
        return f"{update} and the screen backtest request reached Portfolio123, and may have been charged."
    if outcome == "unknown":
        return (
            f"{update} may have been charged, and its outcome is unknown: no response was saved."
            f" The screen backtest request wasn't sent. {never}"
        )
    if possibly_charged:
        return (
            f"{update} reached Portfolio123, and may have been charged. The screen backtest"
            " request wasn't sent."
        )
    return "Neither the rank_update request nor the screen backtest request was sent."


def record_detail(record: AnyAttemptRecord) -> str:
    """What an attempt record says about its request, or an attempt with a definition's two, for
    a message, as `request_detail` and `ranking_detail` give it."""
    if isinstance(record, AttemptRecordV1_2) and record.operation == "rank_get":
        return request_detail(
            record.outcome, possibly_charged=record.possibly_charged, name=RANK_GET_REQUEST_NAME
        )
    if (
        not isinstance(record, AttemptRecordV1_2 | AttemptRecordV1_3)
        or record.ranking_update is None
    ):
        return request_detail(record.outcome, possibly_charged=record.possibly_charged)
    backtest = _first(record.exchanges, SCREEN_BACKTEST_REQUEST)
    # A resume records an attempt from `started.json` without a saved response as `unknown`,
    # with no backtest exchange: its backtest may have been sent (uncertain completion).
    sent = (backtest is not None and backtest.result != "not_connected") or (
        backtest is None and record.outcome == "unknown" and record.request is not None
    )
    return ranking_detail(
        record.outcome, possibly_charged=record.possibly_charged, backtest_sent=sent
    )


def request_detail(
    outcome: Outcome, *, possibly_charged: bool, name: str = BACKTEST_REQUEST_NAME
) -> str:
    """What an attempt with this outcome says about the request, for a message: whether it was
    sent, and whether it may have been charged, as the attempt record does. `name` names the
    request: a screen run's backtest, or a snapshot's `rank_get`."""
    if outcome == "succeeded":
        return f"The {name} succeeded, and its response was saved."
    if outcome == "unknown":
        return (
            f"The {name} may have been charged, and its outcome is unknown: no response was saved."
            " Trial Folio never retries it automatically: check the account's API credits on"
            " Portfolio123's website before running the command again."
        )
    if possibly_charged:
        return f"The {name} reached Portfolio123, and may have been charged."
    return f"The {name} wasn't sent."


class EndingFields(TypedDict):
    """The fields of an attempt record, of any version, that say how the attempt ended."""

    ended_at: datetime
    outcome: Outcome
    error: ErrorDetail | None
    possibly_charged: bool
    request: ArtifactReference | None
    response: SavedResponse | None
    provider_metadata: ProviderMetadata


class AttemptEnding:
    """An attempt's ending policy: it classifies the attempt from its exchanges, and whether its
    response was saved, decides the command's error, writes the attempt record whatever ended
    the attempt, and logs how it ended. It ends the attempt whose files `files` writes."""

    def __init__(
        self,
        files: AttemptFiles,
        log_fields: Callable[[str], dict[str, str]],
        classify: Classifier,
        *,
        synthetic: bool,
        experiment_case: str | None = None,
    ) -> None:
        """`classify` gives how the attempt's exchanges end it, and `experiment_case` is an
        experiment's attempt's case, which its ending's line names."""
        self._files = files
        self._log_fields = log_fields
        self._classify = classify
        self._synthetic = synthetic
        self._case_id = experiment_case
        self._started = time.monotonic()

    def end[R: (AttemptRecord, AttemptRecordV1_1, AttemptRecordV1_2, AttemptRecordV1_3)](
        self,
        exchanges: tuple[Exchange, ...],
        ending: BaseException | None,
        record: Callable[[Ending, TrialFolioError | None], R],
    ) -> tuple[R, bool, TrialFolioError | None]:
        """Classifies the attempt from its exchanges, and whether its response was saved, and
        writes the attempt record `record` builds from that and the command's error. Returns the
        record, whether it was written, and the command's error."""
        end = self._classify(exchanges, self._files.response is not None)
        if ending is not None and not isinstance(ending, KeyboardInterrupt | TrialFolioError):
            self._log_unexpected(ending)
        error = _error(ending, end)
        recorded, error, written = self._write_record(record(end, error), error, end)
        self._log_end(written, recorded, error)
        return written, recorded, error

    def fields(
        self, end: Ending, error: TrialFolioError | None, ended_at: datetime
    ) -> EndingFields:
        """The fields of the attempt record that say how it ended, in any version."""
        saved = self._files.response if end.outcome == "succeeded" else None
        request = self._files.request
        return EndingFields(
            ended_at=ended_at,
            outcome=end.outcome,
            error=None if saved is not None or error is None else _detail_of(error),
            possibly_charged=end.possibly_charged,
            request=None if request is None else reference(request),
            response=None if saved is None else saved_response(*saved),
            provider_metadata=response_metadata(None if saved is None else saved[1]),
        )

    def _write_record[R: (AttemptRecord, AttemptRecordV1_1, AttemptRecordV1_2, AttemptRecordV1_3)](
        self, record: R, error: TrialFolioError | None, end: Ending
    ) -> tuple[bool, TrialFolioError | None, R]:
        """Writes the attempt record. Returns whether it was written, the command's error, and the
        record, which an interrupt can change before it's written.

        After an interrupt while it's written, a record that was published is left as it is.
        Otherwise it's written once more, with `command.interrupted` unless it succeeded. After a
        storage failure, a record that was published counts as written too: the store can
        publish a file and then fail a later step, such as the directory's sync, and the attempt
        then reads as its record says, not as running.
        """
        data = model_json(record)
        try:
            self._files.write(ATTEMPT_RECORD, data, "attempt_record")
        except KeyboardInterrupt:
            error = prevailing(interrupted(end.detail), error)
            if self._files.published(ATTEMPT_RECORD, data, "attempt_record"):
                return True, error, record
            if record.error is not None:
                record = record.model_copy(update={"error": _detail_of(error)})
            return self._write_again(record), error, record
        except TrialFolioError as failure:
            recorded = self._files.published(ATTEMPT_RECORD, data, "attempt_record")
            return recorded, prevailing(failure.with_detail(end.detail), error), record
        # Unwritten, the start record, if any, reads as running.
        except Exception as failure:  # noqa: BLE001
            self._log_unexpected(failure)
            return False, prevailing(_unexpected(failure, end), error), record
        return True, error, record

    def _write_again(self, record: BaseModel) -> bool:
        try:
            self._files.write(ATTEMPT_RECORD, model_json(record), "attempt_record")
        # The interrupt's code stays; unwritten, the start record, if any, reads as running.
        except Exception as failure:  # noqa: BLE001
            if not isinstance(failure, TrialFolioError):
                self._log_unexpected(failure)
            return False
        return True

    def _log_end(
        self, written: AnyAttemptRecord, recorded: bool, error: TrialFolioError | None
    ) -> None:
        charged = "yes" if written.possibly_charged else "no"
        if self._synthetic and written.possibly_charged:
            charged = "yes, in its invented records, though nothing was sent"
        subject = "Attempt" if self._case_id is None else f"Attempt for {self._case_id}"
        _logger.log(
            logging.INFO if error is None else logging.ERROR,
            "%s ended %s after %.3f s: %s; possibly charged: %s; attempt record written: %s.",
            subject,
            written.outcome,
            time.monotonic() - self._started,
            "no error" if error is None else error.code,
            charged,
            "yes" if recorded else "no",
            extra={
                **self._log_fields("attempt.completed"),
                # An experiment's session goes on after an attempt whose record was written, unless
                # an interrupt or a storage failure ended it, as its `CaseRunner` does, or ends with
                # `execution.partial`, so the terminal shows that ending, an internal error's
                # included (D-38). The command shows the error of any other ending itself, as it
                # does a screen run's.
                "terminal": error is None
                or (
                    self._case_id is not None
                    and recorded
                    and error.code not in ("command.interrupted", "storage.write_failed")
                ),
            },
        )

    def _log_unexpected(self, error: BaseException) -> None:
        # Its type and frames only: its message could hold a value, which logs never do.
        _logger.error(
            "Unexpected %s during the attempt, at:\n%s",
            type(error).__name__,
            "".join(traceback.format_tb(error.__traceback__)),
            extra=self._log_fields("attempt.unexpected"),
        )


def _outcome(send: Exchange | None, *, saved: bool) -> Outcome:
    """The outcome the request's exchange gives (execution outcomes, field shapes)."""
    if send is None or send.result == "not_connected":
        return "failed"
    if send.status is None or send.status >= 500:
        return "unknown"
    if send.status == 200:
        return "succeeded" if saved else "unknown"
    return "failed"


def _error(ending: BaseException | None, end: Ending) -> TrialFolioError | None:
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
            return interrupted(end.detail)
        case ProviderError():
            # Its message already says whether the request may have been charged.
            return ending
        case TrialFolioError():
            return ending.with_detail(end.detail)
        case _:
            return _unexpected(ending, end)


def _unexpected(error: BaseException, end: Ending) -> TrialFolioError:
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
