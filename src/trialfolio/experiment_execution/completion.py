"""The attempt records a resume writes, in step 8, for the attempts a stopped run left without
one (docs/contracts.md, uncertain completion, experiment attempts, and the resume's attempt
records; sending a definition, an attempt stopped after its update record).

`completed_record` builds each from the attempt's records, as `read_experiment` read them, so
nothing is read again. It keeps their contents, `session`, `sequence`, and `repeat_of`, and
records the attempt as its records left it: one builder for an attempt that stopped while it
authenticated, one for a `running` attempt, which sent its backtest, and one for an attempt
whose latest record is its update record, which sent only its `rank_update`. Nothing here writes,
sends, or logs: the writer of the session's records writes what it builds.
"""

import json
from datetime import datetime
from typing import Final, cast

from trialfolio.attempts import (
    RANK_UPDATE_REQUEST_FILE,
    RANK_UPDATE_RESPONSE_RAW,
    provider_metadata,
    ranking_detail,
    request_detail,
)
from trialfolio.contracts.attempt import (
    ArtifactReference,
    AttemptRecordV1_1,
    AttemptRecordV1_3,
    Exchange,
    ProviderMetadata,
    RankingUpdate,
    RankUpdateResponse,
    SavedResponse,
    StartRecordV1_3,
)
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    RANK_UPDATE_REQUEST,
    SCREEN_BACKTEST_REQUEST,
    ErrorDetail,
)
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.experiment_paths import REQUEST
from trialfolio.experiment_records import (
    AnyAttemptRecord,
    AnyPlan,
    AnyStart,
    SavedExperimentAttempt,
)

_NO_METADATA: Final = ProviderMetadata(cost=None, quota_remaining=None)
"""What a request without a decoded response reports of its charge: nothing."""

_AUTHENTICATION_INTERRUPTED: Final = Exchange(
    request=AUTHENTICATION_REQUEST, result="interrupted", status=None, note=None
)
"""The authentication call of an attempt whose only record is its authentication record: nothing
shows whether it was made, or how it ended."""


def completed_record(
    attempt: SavedExperimentAttempt, plan: AnyPlan, ended_at: datetime
) -> AnyAttemptRecord:
    """The attempt record a resume writes for `attempt`, which has none, keeping its records'
    contents, `session`, `sequence`, and `repeat_of` (docs/contracts.md, uncertain completion,
    and experiment attempts). `plan` is the plan it ran under, and `ended_at` when the record is
    written, or its start time when the clock reads earlier.

    - **A `running` attempt with a saved response** is `succeeded`: its request's exchange is
      recorded as a `response` with status 200 and the note `completed_from_saved_response`.
    - **A `running` attempt without one** is `unknown`, possibly charged, with its start record's
      exchanges, and `command.interrupted`, as an interrupt during the send gives.
    - **An attempt with only its authentication record** is `failed`, not possibly charged, with
      `command.interrupted`, and its one exchange, the authentication call's, recorded as
      `interrupted`. A `request.json` it wrote isn't referenced.

    Under a plan 1.3.0, the record is 1.3.0, with the `rank_update`'s files in its
    `ranking_update`, and a `running` attempt's exchanges are its start record's, the
    `rank_update`'s 200 among them. An attempt whose latest record is its update record is
    recorded as sending a definition says: with the `rank_update`'s saved response, its exchange
    is a `response` with status 200 and the note `completed_from_saved_response`, and the attempt
    is `failed`, with `command.interrupted`, or `provider.response_invalid` for a response saved
    undecoded; without it, the exchange is `interrupted`, and the attempt `unknown`, with
    `command.interrupted`. Either way, it's possibly charged, and a backtest's `request.json` it
    wrote isn't referenced.

    Raises `ValueError` when it has an attempt record.
    """
    if attempt.record is not None:
        raise ValueError("the attempt has its attempt record")
    ended_at = max(ended_at, attempt.started_at)
    ranking = isinstance(plan, PlanV1_3)
    opening = attempt.opening if ranking else attempt.start
    if opening is None:
        return _stopped_authenticating(attempt, plan, ended_at)
    started = _started(attempt, opening, ended_at, ranking)
    if attempt.start is not None:
        return _running(attempt, attempt.start, started, ranking)
    return _updated(attempt, cast("StartRecordV1_3", attempt.update), started)


def _stopped_authenticating(
    attempt: SavedExperimentAttempt, plan: AnyPlan, ended_at: datetime
) -> AnyAttemptRecord:
    """The record of an attempt whose only record is its authentication record: `failed`, not
    possibly charged, with its plan's versions, and, under a plan 1.3.0, a `ranking_update`
    without files."""
    ranking = isinstance(plan, PlanV1_3)
    fields: dict[str, object] = {
        **_identity(attempt, "1.3.0" if ranking else "1.1.0"),
        "authenticated_by": None,
        "repeat_of": attempt.repeat_of,
        "started_at": attempt.started_at,
        "provider_wrapper": plan.provider_wrapper,
        "transport": plan.transport,
        "ended_at": ended_at,
        "outcome": "failed",
        "error": _authentication_error(ranking=ranking),
        "exchanges": (_AUTHENTICATION_INTERRUPTED,),
        "possibly_charged": False,
        "request": None,
        "response": None,
        "provider_metadata": _NO_METADATA,
    }
    if not ranking:
        return AttemptRecordV1_1.model_validate(fields)
    return AttemptRecordV1_3.model_validate(
        {
            **fields,
            "operation": "screen_backtest",
            "ranking_update": RankingUpdate(
                request=None, response=None, provider_metadata=_NO_METADATA
            ),
        }
    )


def _started(
    attempt: SavedExperimentAttempt, opening: AnyStart, ended_at: datetime, ranking: bool
) -> dict[str, object]:
    """The fields of the record of an attempt that sent its first request, from its first start
    record, `opening`: possibly charged, and, under a plan 1.3.0, with the `rank_update`'s
    files."""
    fields: dict[str, object] = {
        **_identity(attempt, "1.3.0" if ranking else "1.1.0"),
        "authenticated_by": opening.authenticated_by,
        "repeat_of": opening.repeat_of,
        "started_at": opening.started_at,
        "provider_wrapper": opening.provider_wrapper,
        "transport": opening.transport,
        "ended_at": ended_at,
        "possibly_charged": True,
    }
    if ranking:
        fields |= {"operation": "screen_backtest", "ranking_update": _ranking_update(attempt)}
    return fields


def _running(
    attempt: SavedExperimentAttempt, start: AnyStart, started: dict[str, object], ranking: bool
) -> AnyAttemptRecord:
    """The record of a `running` attempt, whose latest record is its start record: `succeeded`
    from its saved response, or `unknown` without one (uncertain completion)."""
    fields = {
        **started,
        "request": _reference(attempt, REQUEST),
        **_backtest_ending(attempt, start),
    }
    if ranking:
        return AttemptRecordV1_3.model_validate(fields)
    return AttemptRecordV1_1.model_validate(fields)


def _updated(
    attempt: SavedExperimentAttempt, update: StartRecordV1_3, started: dict[str, object]
) -> AttemptRecordV1_3:
    """The record of an attempt whose latest record is its update record, with no backtest's
    request or response (an attempt stopped after its update record)."""
    return AttemptRecordV1_3.model_validate(
        {
            **started,
            **_update_ending(attempt, update),
            "request": None,
            "response": None,
            "provider_metadata": _NO_METADATA,
        }
    )


def _backtest_ending(attempt: SavedExperimentAttempt, start: AnyStart) -> dict[str, object]:
    """The ending of a `running` attempt: `succeeded` from its saved response, or `unknown`
    without one (uncertain completion)."""
    ranking = isinstance(start, StartRecordV1_3)
    if attempt.response is None:
        detail = (
            ranking_detail("unknown", possibly_charged=True, backtest_sent=True)
            if ranking
            else request_detail("unknown", possibly_charged=True)
        )
        return {
            "outcome": "unknown",
            "error": ErrorDetail(
                code="command.interrupted",
                message=(
                    "The run that started the attempt stopped after its start record was"
                    f" written, before a response was saved. {detail}"
                ),
            ),
            "exchanges": start.exchanges,
            "response": None,
            "provider_metadata": _NO_METADATA,
        }
    saved, content = attempt.response
    return {
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


def _update_ending(attempt: SavedExperimentAttempt, update: StartRecordV1_3) -> dict[str, object]:
    """The ending of an attempt whose latest record is its update record (an attempt stopped
    after its update record): `failed` with the `rank_update`'s saved response, and `unknown`
    without it."""
    if attempt.rank_response is None:
        detail = ranking_detail("unknown", possibly_charged=True, backtest_sent=False)
        return {
            "outcome": "unknown",
            "error": ErrorDetail(
                code="command.interrupted",
                message=(
                    "The run that started the attempt stopped after its update record was"
                    f" written, before the rank_update's response was saved. {detail}"
                ),
            ),
            "exchanges": (
                *update.exchanges,
                Exchange(request=RANK_UPDATE_REQUEST, result="interrupted", status=None, note=None),
            ),
        }
    saved, _ = attempt.rank_response
    return {
        "outcome": "failed",
        "error": _stopped_after_update(saved),
        "exchanges": (
            *update.exchanges,
            Exchange(
                request=RANK_UPDATE_REQUEST,
                result="response",
                status=200,
                note="completed_from_saved_response",
            ),
        ),
    }


def _stopped_after_update(saved: RankUpdateResponse) -> ErrorDetail:
    """The error of an attempt stopped after its `rank_update`'s response, `saved`, was saved:
    `provider.response_invalid` for one saved undecoded, which no backtest follows, and
    `command.interrupted` otherwise."""
    detail = ranking_detail("failed", possibly_charged=True, backtest_sent=False)
    if saved.form == "undecoded":
        return ErrorDetail(
            code="provider.response_invalid",
            message=(
                "Portfolio123 answered the rank_update request with a 200 whose body couldn't"
                f" be decoded as JSON, so it was saved as it came, as {RANK_UPDATE_RESPONSE_RAW}."
                " Trial Folio sends the case's screen backtest only after one whose response"
                f" it could read, and the run that started the attempt stopped. {detail}"
            ),
        )
    return ErrorDetail(
        code="command.interrupted",
        message=(
            "The run that started the attempt stopped after the rank_update's response"
            f" was saved, before the screen backtest request was sent. {detail}"
        ),
    )


def _ranking_update(attempt: SavedExperimentAttempt) -> RankingUpdate:
    """The `rank_update`'s files, as the attempt record references them: its request, and its
    saved response, with what that response reports of its charge."""
    response = None
    metadata = _NO_METADATA
    if attempt.rank_response is not None:
        response, content = attempt.rank_response
        metadata = _metadata(response, content)
    return RankingUpdate(
        request=_reference(attempt, RANK_UPDATE_REQUEST_FILE),
        response=response,
        provider_metadata=metadata,
    )


def _reference(attempt: SavedExperimentAttempt, name: str) -> ArtifactReference:
    """A reference to the file `name` of the attempt's directory, which the records check
    found."""
    path = f"{attempt.directory}/{name}"
    stored = next(file.file for file in attempt.files if file.file.path == path)
    return ArtifactReference(path=stored.path, artifact_id=stored.artifact_id)


def _identity(attempt: SavedExperimentAttempt, schema_version: str) -> dict[str, object]:
    records = (attempt.update, attempt.start, attempt.authentication)
    version = next(record.trialfolio_version for record in records if record is not None)
    plan_hash_ = next(record.plan_hash for record in records if record is not None)
    return {
        "schema_version": schema_version,
        "trialfolio_version": version,
        "attempt_id": attempt.attempt_id,
        "case_id": attempt.case_id,
        "plan_hash": plan_hash_,
        "session": attempt.session,
        "sequence": attempt.sequence,
    }


def _authentication_error(*, ranking: bool) -> ErrorDetail:
    """The error of an attempt whose only record is its authentication record."""
    detail = (
        ranking_detail("failed", possibly_charged=False, backtest_sent=False)
        if ranking
        else request_detail("failed", possibly_charged=False)
    )
    return ErrorDetail(
        code="command.interrupted",
        message=(
            "The run that started the attempt stopped while it authenticated, before its request"
            f" was sent. {detail}"
        ),
    )


def _metadata(response: SavedResponse | RankUpdateResponse, content: bytes) -> ProviderMetadata:
    """`cost` and `quotaRemaining` from the top level of a saved decoded response, as the
    attempt that saved it would have recorded them."""
    if response.form == "undecoded":
        return ProviderMetadata(cost=None, quota_remaining=None)
    try:
        payload: object = json.loads(content)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return ProviderMetadata(cost=None, quota_remaining=None)
    return provider_metadata(payload)
