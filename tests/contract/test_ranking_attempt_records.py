"""The start and attempt records of a ranking definition, and of a ranking snapshot, accept what
docs/contracts.md describes, and reject what it calls invalid.

Traces to release 0.4.0's test pairing, which names tests/contract/test_ranking_artifact_models.py
for the records' contract tests (R04-T05), here for start and attempt records 1.2.0 and 1.3.0
(sending a definition, and ranking snapshot output): the update record, the start record, and the
attempt record 1.2.0 of a screen run's attempt and of a snapshot's, and 1.3.0 of an experiment's.
Each document is tests/support/ranking_documents.py's, synthetic, changed one way, and read as a
reader reads it: from JSON text, with `model_validate_json`. TS-T07 separated these tests from
tests/contract/test_ranking_artifact_models.py (docs/test-refactoring.md, modules to separate).
"""

from collections.abc import Callable

import pytest

from tests.support.contract_checks import Change, Document, accepts, changed, rejects
from tests.support.ranking_documents import (
    ATTEMPT_ID,
    AUTH,
    BASELINE_ID,
    EARLIER_ATTEMPT,
    ERROR,
    RANK,
    SEND,
    SNAPSHOT_DIRECTORY,
    UNKNOWN,
    attempt_record_1_2,
    exchange,
    experiment_attempt_record,
    experiment_start_record,
    experiment_update_record,
    failed,
    ranking_update,
    reference,
    snapshot_attempt_record,
    snapshot_start_record,
    start_record_1_2,
    unknown,
    update_record,
)
from trialfolio.contracts.attempt import (
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    StartRecordV1_2,
    StartRecordV1_3,
)

# Start records 1.2.0 and 1.3.0

START_1_2_REJECTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "an update record that holds the rank_update's exchange": (
        update_record,
        lambda d: d.update(exchanges=[AUTH, RANK]),
    ),
    "an update record without authentication": (update_record, lambda d: d.update(exchanges=[])),
    "an update record whose one exchange isn't authentication's": (
        update_record,
        lambda d: d.update(exchanges=[RANK]),
    ),
    "an update record after failed authentication": (
        update_record,
        lambda d: d.update(exchanges=[exchange("POST /auth", 401)]),
    ),
    "started.json without the rank_update's exchange": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH]),
    ),
    "started.json after a rank_update's 400": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH, exchange("POST /rank", 400)]),
    ),
    "started.json after an interrupted rank_update": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH, exchange("POST /rank", None)]),
    ),
    "started.json with its exchanges in another order": (
        start_record_1_2,
        lambda d: d.update(exchanges=[RANK, AUTH]),
    ),
    "started.json after another request": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH, exchange("POST /rank/create")]),
    ),
    "a start record's exchange with a note": (
        start_record_1_2,
        lambda d: d.update(exchanges=[AUTH, RANK | {"note": "completed_from_saved_response"}]),
    ),
    "a snapshot's start record with a case": (
        snapshot_start_record,
        lambda d: d.update(case_id=BASELINE_ID),
    ),
    "a case's start record without one": (update_record, lambda d: d.update(case_id=None)),
    "another operation": (update_record, lambda d: d.update(operation="rank_create")),
    "a session's fields": (update_record, lambda d: d.update(session=1)),
}


@pytest.mark.parametrize(
    ("build", "change"), START_1_2_REJECTS.values(), ids=START_1_2_REJECTS.keys()
)
def test_start_record_1_2_rejects(build: Callable[[], Document], change: Change) -> None:
    rejects(StartRecordV1_2, changed(build, change))


def own_authentication(document: Document) -> None:
    document.update(authenticated_by=ATTEMPT_ID, exchanges=[AUTH, *document["exchanges"]])


START_1_3_ACCEPTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "an update record that authenticated": (experiment_update_record, own_authentication),
    "started.json of an attempt that authenticated": (experiment_start_record, own_authentication),
    "a repeat": (experiment_start_record, lambda d: d.update(repeat_of=EARLIER_ATTEMPT)),
}


@pytest.mark.parametrize(
    ("build", "change"), START_1_3_ACCEPTS.values(), ids=START_1_3_ACCEPTS.keys()
)
def test_start_record_1_3_accepts(build: Callable[[], Document], change: Change) -> None:
    accepts(StartRecordV1_3, changed(build, change))


START_1_3_REJECTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "a snapshot's operation": (experiment_update_record, lambda d: d.update(operation="rank_get")),
    "no case": (experiment_update_record, lambda d: d.update(case_id=None)),
    "its own token, without authenticating": (
        experiment_update_record,
        lambda d: d.update(authenticated_by=ATTEMPT_ID),
    ),
    "authenticated, and sent with another's token": (
        experiment_update_record,
        lambda d: d.update(exchanges=[AUTH]),
    ),
    "started.json without the rank_update's exchange": (
        experiment_start_record,
        lambda d: d.update(exchanges=[]),
    ),
    "started.json after a rank_update's 503": (
        experiment_start_record,
        lambda d: d.update(exchanges=[exchange("POST /rank", 503)]),
    ),
    "an update record that holds the rank_update's exchange": (
        experiment_update_record,
        lambda d: d.update(exchanges=[RANK]),
    ),
    "a repeat of itself": (experiment_start_record, lambda d: d.update(repeat_of=ATTEMPT_ID)),
}


@pytest.mark.parametrize(
    ("build", "change"), START_1_3_REJECTS.values(), ids=START_1_3_REJECTS.keys()
)
def test_start_record_1_3_rejects(build: Callable[[], Document], change: Change) -> None:
    rejects(StartRecordV1_3, changed(build, change))


# Attempt records 1.2.0 and 1.3.0


def update_of(document: Document) -> Document:
    update: Document = document["ranking_update"]
    return update


def rank_rejected(document: Document) -> None:
    failed(document, AUTH, exchange("POST /rank", 400))
    update_of(document).update(
        response=None, provider_metadata={"cost": None, "quota_remaining": None}
    )


ATTEMPT_1_2_ACCEPTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "a rank_update rejected with a 400": (attempt_record_1_2, rank_rejected),
    "a rank_update that got a 503": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, exchange("POST /rank", 503)),
            update_of(d).update(response=None),
        ),
    ),
    "a rank_update interrupted": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, exchange("POST /rank", None)),
            update_of(d).update(response=None),
        ),
    ),
    "a rank_update that never connected": (
        attempt_record_1_2,
        lambda d: (
            failed(d, AUTH, exchange("POST /rank", None, result="not_connected")),
            update_of(d).update(response=None),
            d.update(possibly_charged=False),
        ),
    ),
    "authentication that failed": (
        attempt_record_1_2,
        lambda d: (
            failed(d, exchange("POST /auth", 401)),
            update_of(d).update(request=None, response=None),
            d.update(possibly_charged=False),
        ),
    ),
    "an interrupt before the rank_update's send": (
        attempt_record_1_2,
        lambda d: (
            failed(d, AUTH),
            update_of(d).update(response=None),
            d.update(possibly_charged=False),
        ),
    ),
    "a rank_update's 200 the wrapper couldn't decode": (
        attempt_record_1_2,
        lambda d: (failed(d, AUTH, RANK), d.update(ranking_update=ranking_update("undecoded"))),
    ),
    "a failure after the rank_update's response was saved": (
        attempt_record_1_2,
        lambda d: failed(d, AUTH, RANK),
    ),
    "resumed from its update record, with a saved response": (
        attempt_record_1_2,
        lambda d: failed(d, AUTH, RANK | {"note": "completed_from_saved_response"}),
    ),
    "resumed from its update record, without one": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, exchange("POST /rank", None)),
            update_of(d).update(response=None),
        ),
    ),
    "resumed from started.json, without a saved response": (
        attempt_record_1_2,
        lambda d: (unknown(d, AUTH, RANK), d.update(request=reference("request.json"))),
    ),
    "a backtest that got a 503": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, RANK, exchange("POST /screen/backtest", 503)),
            d.update(request=reference("request.json")),
        ),
    ),
    "a backtest restarted with its saved response": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[AUTH, RANK, SEND | {"note": "completed_from_saved_response"}]
        ),
    ),
    "a snapshot's 404": (
        snapshot_attempt_record,
        lambda d: (
            failed(d, AUTH, exchange("GET /rank", 404)),
            d.update(request=reference("request.json", SNAPSHOT_DIRECTORY)),
        ),
    ),
}


@pytest.mark.parametrize(
    ("build", "change"), ATTEMPT_1_2_ACCEPTS.values(), ids=ATTEMPT_1_2_ACCEPTS.keys()
)
def test_attempt_record_1_2_accepts(build: Callable[[], Document], change: Change) -> None:
    accepts(AttemptRecordV1_2, changed(build, change))


ATTEMPT_1_2_REJECTS: dict[str, tuple[Callable[[], Document], Change]] = {
    "a backtest without its rank_update": (
        attempt_record_1_2,
        lambda d: (
            d.update(exchanges=[AUTH, SEND]),
            update_of(d).update(request=None, response=None),
        ),
    ),
    "a backtest after a rank_update's 400": (
        attempt_record_1_2,
        lambda d: (
            d.update(exchanges=[AUTH, exchange("POST /rank", 400), SEND]),
            update_of(d).update(response=None),
        ),
    ),
    "a backtest after a rank_update the wrapper couldn't decode": (
        attempt_record_1_2,
        lambda d: d.update(ranking_update=ranking_update("undecoded")),
    ),
    "a backtest after a rank_update whose response wasn't saved": (
        attempt_record_1_2,
        lambda d: update_of(d).update(response=None),
    ),
    "the backtest before the rank_update": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[AUTH, SEND, RANK]),
    ),
    "two rank_updates": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[AUTH, RANK, RANK, SEND]),
    ),
    "a request Trial Folio doesn't send": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[AUTH, RANK, exchange("POST /rank/create"), SEND]),
    ),
    "a rank_update's exchange without its saved request": (
        attempt_record_1_2,
        lambda d: update_of(d).update(request=None),
    ),
    "a rank_update's response saved after a 400": (
        attempt_record_1_2,
        lambda d: failed(d, AUTH, exchange("POST /rank", 400)),
    ),
    "a rank_update's response saved as the backtest's": (
        attempt_record_1_2,
        lambda d: update_of(d).update(response=reference("response.json") | {"form": "decoded"}),
    ),
    "a rank_update's request saved as the backtest's": (
        attempt_record_1_2,
        lambda d: update_of(d).update(request=reference("request.json")),
    ),
    "no ranking_update": (attempt_record_1_2, lambda d: d.update(ranking_update=None)),
    "unknown after a rank_update's 400": (
        attempt_record_1_2,
        lambda d: (rank_rejected(d), d.update(outcome="unknown", error=UNKNOWN)),
    ),
    "unknown without a rank_update exchange": (
        attempt_record_1_2,
        lambda d: (unknown(d, AUTH), update_of(d).update(response=None)),
    ),
    "unknown after a rank_update's 200, without the backtest's request": (
        attempt_record_1_2,
        lambda d: unknown(d, AUTH, RANK),
    ),
    "unknown after a rank_update's 200 the wrapper couldn't decode": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, RANK),
            d.update(ranking_update=ranking_update("undecoded"), request=reference("request.json")),
        ),
    ),
    "unknown after a rank_update's 200 whose response wasn't saved": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, RANK),
            update_of(d).update(response=None),
            d.update(request=reference("request.json")),
        ),
    ),
    "failed after an interrupted rank_update": (
        attempt_record_1_2,
        lambda d: (
            failed(d, AUTH, exchange("POST /rank", None)),
            update_of(d).update(response=None),
        ),
    ),
    "not possibly charged after a rank_update's 400": (
        attempt_record_1_2,
        lambda d: (rank_rejected(d), d.update(possibly_charged=False)),
    ),
    "possibly charged after nothing was sent": (
        attempt_record_1_2,
        lambda d: (failed(d, AUTH), update_of(d).update(response=None)),
    ),
    "a noted rank_update before a backtest": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[AUTH, RANK | {"note": "completed_from_saved_response"}, SEND]
        ),
    ),
    "a noted rank_update that ended unknown": (
        attempt_record_1_2,
        lambda d: unknown(d, AUTH, RANK | {"note": "completed_from_saved_response"}),
    ),
    "a noted rank_update without its saved response": (
        attempt_record_1_2,
        lambda d: (
            failed(d, AUTH, RANK | {"note": "completed_from_saved_response"}),
            update_of(d).update(response=None),
        ),
    ),
    "a noted authentication": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[AUTH | {"note": "completed_from_saved_response"}, RANK, SEND]
        ),
    ),
    "a noted backtest that didn't succeed": (
        attempt_record_1_2,
        lambda d: (
            unknown(d, AUTH, RANK, SEND | {"note": "completed_from_saved_response"}),
            d.update(request=reference("request.json")),
        ),
    ),
    "a backtest without its saved request": (attempt_record_1_2, lambda d: d.update(request=None)),
    "a backtest's request saved under another name": (
        attempt_record_1_2,
        lambda d: d.update(request=reference("backtest.json")),
    ),
    "a failed backtest with a saved response": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[AUTH, RANK, exchange("POST /screen/backtest", 400)],
            outcome="failed",
            error=ERROR,
        ),
    ),
    "a noted rank_update before a backtest that failed": (
        attempt_record_1_2,
        lambda d: d.update(
            exchanges=[
                AUTH,
                RANK | {"note": "completed_from_saved_response"},
                exchange("POST /screen/backtest", 400),
            ],
            outcome="failed",
            error=ERROR,
            response=None,
        ),
    ),
    "a backtest's 200 without its saved response": (
        attempt_record_1_2,
        lambda d: d.update(response=None),
    ),
    "a succeeded attempt with an error": (attempt_record_1_2, lambda d: d.update(error=ERROR)),
    "sending without authentication": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[RANK, SEND]),
    ),
    "sending after failed authentication": (
        attempt_record_1_2,
        lambda d: d.update(exchanges=[exchange("POST /auth", 401), RANK, SEND]),
    ),
    "a snapshot's attempt with a rank_update": (
        snapshot_attempt_record,
        lambda d: d.update(ranking_update=ranking_update()),
    ),
    "a snapshot's attempt that sends a backtest": (
        snapshot_attempt_record,
        lambda d: d.update(exchanges=[AUTH, SEND]),
    ),
    "a snapshot's attempt with a case": (
        snapshot_attempt_record,
        lambda d: d.update(case_id=BASELINE_ID),
    ),
    "a case's attempt without one": (attempt_record_1_2, lambda d: d.update(case_id=None)),
    "the operation rank_update": (attempt_record_1_2, lambda d: d.update(operation="rank_update")),
    "an end before the start": (
        attempt_record_1_2,
        lambda d: d.update(ended_at="2026-10-14T12:00:00Z"),
    ),
}


@pytest.mark.parametrize(
    ("build", "change"), ATTEMPT_1_2_REJECTS.values(), ids=ATTEMPT_1_2_REJECTS.keys()
)
def test_attempt_record_1_2_rejects(build: Callable[[], Document], change: Change) -> None:
    rejects(AttemptRecordV1_2, changed(build, change))


ATTEMPT_1_3_ACCEPTS: dict[str, Change] = {
    "an attempt that authenticated": own_authentication,
    "a repeat": lambda d: d.update(repeat_of=EARLIER_ATTEMPT),
    "authentication that failed": lambda d: (
        failed(d, exchange("POST /auth", 401)),
        update_of(d).update(request=None, response=None),
        d.update(possibly_charged=False, authenticated_by=None),
    ),
    "a rank_update that got a 402": lambda d: (
        failed(
            d,
            exchange("POST /rank", 402),
            error={"code": "provider.quota_exceeded", "message": "No quota."},
        ),
        update_of(d).update(response=None),
    ),
    "resumed from started.json, without a saved response": lambda d: (
        unknown(d, RANK),
        d.update(request=reference("request.json")),
    ),
}


@pytest.mark.parametrize("change", ATTEMPT_1_3_ACCEPTS.values(), ids=ATTEMPT_1_3_ACCEPTS.keys())
def test_attempt_record_1_3_accepts(change: Change) -> None:
    accepts(AttemptRecordV1_3, changed(experiment_attempt_record, change))


ATTEMPT_1_3_REJECTS: dict[str, Change] = {
    "sending with no authentication named": lambda d: d.update(authenticated_by=None),
    "its own token, without authenticating": lambda d: d.update(authenticated_by=ATTEMPT_ID),
    "authenticated, and sent with another's token": lambda d: d.update(
        exchanges=[AUTH, RANK, SEND]
    ),
    "a snapshot's operation": lambda d: d.update(operation="rank_get"),
    "no ranking_update": lambda d: d.update(ranking_update=None),
    "a backtest without its rank_update": lambda d: (
        d.update(exchanges=[SEND]),
        update_of(d).update(request=None, response=None),
    ),
    "a repeat of itself": lambda d: d.update(repeat_of=ATTEMPT_ID),
    "unknown without a rank_update exchange": lambda d: (
        unknown(d),
        update_of(d).update(response=None),
    ),
    "unknown after a rank_update's 200, without the backtest's request": lambda d: unknown(d, RANK),
    "unknown after a rank_update's 200 the wrapper couldn't decode": lambda d: (
        unknown(d, RANK),
        d.update(ranking_update=ranking_update("undecoded"), request=reference("request.json")),
    ),
    "unknown after a rank_update's 200 whose response wasn't saved": lambda d: (
        unknown(d, RANK),
        update_of(d).update(response=None),
        d.update(request=reference("request.json")),
    ),
    "a noted rank_update without its saved response": lambda d: (
        failed(d, RANK | {"note": "completed_from_saved_response"}),
        update_of(d).update(response=None),
    ),
}


@pytest.mark.parametrize("change", ATTEMPT_1_3_REJECTS.values(), ids=ATTEMPT_1_3_REJECTS.keys())
def test_attempt_record_1_3_rejects(change: Change) -> None:
    rejects(AttemptRecordV1_3, changed(experiment_attempt_record, change))
