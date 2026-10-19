"""Reading attempts (docs/contracts.md, uncertain completion, and sending a definition, counting
the requests): how a saved attempt reads, from its attempt record, or, without one, from its
start record or its update record, as `running`; and what an attempt's records count: the sends
of its requests that may have reached Portfolio123, Trial Folio's own authentication calls, and
the credits Portfolio123 reported charging.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from trialfolio.attempts.files import ATTEMPT_RECORD, START_RECORD, attempt_directory
from trialfolio.contracts.attempt import (
    AttemptRecord,
    AttemptRecordV1_1,
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    Exchange,
    StartRecord,
    StartRecordV1_2,
)
from trialfolio.contracts.common import AUTHENTICATION_REQUEST, SCREEN_BACKTEST_REQUEST
from trialfolio.storage import ArtifactStore

type AnyAttemptRecord = AttemptRecord | AttemptRecordV1_1 | AttemptRecordV1_2 | AttemptRecordV1_3
"""An attempt record of any version: a screen run's, 1.0.0, or 1.2.0 with a definition, and an
experiment's, 1.1.0, or 1.3.0 with a definition."""


@dataclass(frozen=True)
class AttemptStatus:
    """How a saved attempt reads (uncertain completion)."""

    attempt_id: uuid.UUID
    outcome: Literal["running", "succeeded", "failed", "unknown"]
    """`running` for a start record without an attempt record; otherwise the record's."""
    possibly_charged: bool
    provider_requests: int
    """The sends of the request that may have reached Portfolio123, never authentication."""


def provider_requests(record: AnyAttemptRecord) -> int:
    """The sends of the request that may have reached Portfolio123: its exchanges other than
    authentication that aren't `not_connected`. An attempt restarted without a saved response is
    `unknown` with only its start record's exchange, and counts as one (uncertain completion).

    An attempt that sends a definition counts each of its two requests so, the `rank_update` and
    the backtest, and its backtest as one when a resume recorded it from `started.json` without a
    saved response: `unknown`, with the backtest's request and no backtest exchange (sending a
    definition, counting the requests)."""
    sends = [e for e in record.exchanges if e.request != AUTHENTICATION_REQUEST]
    counted = sum(1 for e in sends if e.result != "not_connected")
    if (
        isinstance(record, AttemptRecordV1_2 | AttemptRecordV1_3)
        and record.ranking_update is not None
    ):
        restarted = record.outcome == "unknown" and record.request is not None
        backtest = any(e.request == SCREEN_BACKTEST_REQUEST for e in sends)
        return counted + int(restarted and not backtest)
    if not sends and record.outcome == "unknown":
        return 1
    return counted


def authentication_calls(exchanges: Sequence[Exchange]) -> int:
    """Trial Folio's own authentication calls among an attempt's exchanges, which the budget
    counts, whatever their result: its `POST /auth` exchanges."""
    return sum(exchange.request == AUTHENTICATION_REQUEST for exchange in exchanges)


def reported_cost(record: AnyAttemptRecord) -> int | None:
    """The credits Portfolio123 reported charging for the attempt's requests: its backtest's
    `cost`, and its `rank_update`'s, for an attempt that sends a definition, summed; None when it
    reported none (sending a definition, the counts)."""
    costs = [record.provider_metadata.cost]
    if (
        isinstance(record, AttemptRecordV1_2 | AttemptRecordV1_3)
        and record.ranking_update is not None
    ):
        costs.append(record.ranking_update.provider_metadata.cost)
    reported = [cost for cost in costs if cost is not None]
    return sum(reported) if reported else None


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


def attempt_status(
    start: StartRecord | StartRecordV1_2 | None,
    record: AttemptRecord | AttemptRecordV1_2 | None,
    update: StartRecordV1_2 | None = None,
) -> AttemptStatus | None:
    """How an attempt with these records reads: from its attempt record, or, without one, from its
    start record, as `running`, possibly charged, with one provider request, or, for a backtest's
    start record 1.2.0, two, since its update record came before it. An attempt with only its
    update record, `update`, reads as `running` too, with one: its `rank_update` may have been
    sent (counting the requests). None when it has none of them."""
    if record is not None:
        return AttemptStatus(
            attempt_id=record.attempt_id,
            outcome=record.outcome,
            possibly_charged=record.possibly_charged,
            provider_requests=provider_requests(record),
        )
    latest = start if start is not None else update
    if latest is not None:
        # Each request is sent at most once, so each start record is one possible send, and an
        # attempt that sends a definition wrote its update record before its backtest's
        # (counting the requests).
        updated = isinstance(latest, StartRecordV1_2) and latest.operation == "screen_backtest"
        return AttemptStatus(
            attempt_id=latest.attempt_id,
            outcome="running",
            possibly_charged=True,
            provider_requests=2 if updated else 1,
        )
    return None


def _read[M: BaseModel](store: ArtifactStore, path: str, model: type[M]) -> M | None:
    try:
        content = store.read(path)
    except FileNotFoundError:
        return None
    return model.model_validate_json(content)
