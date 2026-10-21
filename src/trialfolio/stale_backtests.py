"""A stale backtest: a case's backtest that may have ranked by the definition written before its
own (docs/contracts.md, running an experiment: a stale backtest; D-45).

The 0.4.0 walk-through found that Portfolio123 sometimes ranks a backtest by the definition
`ApiRankingSystem` held before the latest `rank_update`, although that `rank_update` got its 200,
and its response was then exactly the previous backtest's, apart from `cost` and
`quotaRemaining`. The pause before each backtest prevents it, as far as the diagnostic showed, and
this rule flags what gets through. In an experiment session, a case's backtest that got a 200
decoded with the layout's required structure is stale when the session's previous attempt that
sent a definition and saved its backtest's decoded response, in the session's order:

- sent a backtest whose request body, as its `request.json` holds it, is byte for byte this one's;
- sent a different definition, as its `rank-update-request.json` holds it; and
- got a response equal to this one's, as JSON values, once `cost` and `quotaRemaining` are removed
  from the top level of each.

A stale case gets `provider.response_invalid`, as a response that fails validation does: its
attempt stays `succeeded`, with its response saved as evidence, it has no tables, and it can be
repeated. Identical results can be genuine, as when a changed weight doesn't change which stocks
the screen selects, so its message says so. A synthetic experiment's responses are invented, and
nothing ranked them, so the rule doesn't apply to it.

The executor flags a case as its session runs, and the records check re-derives the flag from the
saved records by the same rule, here, so a resume and the session agree. Nothing here writes,
sends, or logs.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Final, cast

from trialfolio.errors import TrialFolioError

IGNORED_KEYS: Final = frozenset({"cost", "quotaRemaining"})
"""The top-level keys of a response that the comparison leaves out: each backtest's own charge and
the quota after it, which differ between two backtests of the same results."""


@dataclass(frozen=True)
class SentBacktest:
    """An experiment's attempt that sent a definition and saved its backtest's decoded response,
    as the rule reads it."""

    case_id: str
    attempt_id: uuid.UUID
    session: int
    update_request: str
    """The `artifact_id` of its `rank-update-request.json`, which holds the definition it sent."""
    request: str
    """The `artifact_id` of its backtest's `request.json`."""
    response: bytes
    """Its saved `response.json`'s bytes."""


def same_results(first: bytes, second: bytes) -> bool:
    """Whether two saved decoded responses are equal, as JSON values, once `cost` and
    `quotaRemaining` are removed from the top level of each. A response that isn't a JSON object
    is compared whole, and one that can't be read equals none."""
    results = _results(first)
    return results is not None and results == _results(second)


def _results(content: bytes) -> str | None:
    """The response's JSON value without `cost` and `quotaRemaining` at the top level, written
    with its keys sorted, so two equal values give the same text, `NaN` included; None when it
    can't be read, which equals nothing."""
    try:
        value: object = json.loads(content)
        if isinstance(value, dict):
            members = cast("dict[str, object]", value)
            value = {key: item for key, item in members.items() if key not in IGNORED_KEYS}
        return json.dumps(value, sort_keys=True)
    except (UnicodeDecodeError, ValueError, RecursionError, TypeError):
        return None


def stale(backtest: SentBacktest, previous: SentBacktest | None) -> bool:
    """Whether `backtest` is stale against `previous`, the session's previous attempt that sent a
    definition and saved its backtest's decoded response, or None when there's none. `backtest`
    must have the layout's required structure."""
    if previous is None or previous.session != backtest.session:
        return False
    return (
        backtest.request == previous.request
        and backtest.update_request != previous.update_request
        and same_results(backtest.response, previous.response)
    )


def stale_error(
    backtest: SentBacktest, previous: SentBacktest, *, key: str, previous_key: str
) -> TrialFolioError:
    """`provider.response_invalid` for a stale backtest, whose case's key is `key`, and whose
    previous case's is `previous_key`. The message names the cases by their keys, and the
    loggable message by their `case_id`s, since a key is the user's text, and the attempt by its
    `attempt_id`. Neither gives the option that repeats the case: the CLI ends
    `execution.partial`'s message with it, as for any case awaiting a repeat, so a terminal
    shows it once."""

    def said(case: str, before: str, response: str) -> str:
        return (
            f"The backtest of case {case} returned the same response, apart from cost and"
            f" quotaRemaining, as that of case {before}, the case before it in session"
            f" {backtest.session}, which was ranked by a different ranking definition. So"
            f" Portfolio123 may have ranked it by {before}'s definition, although its rank_update"
            " succeeded. Identical results can sometimes be genuine, as when a changed weight"
            f" doesn't change which stocks the screen selects. {response} is saved, but the case"
            " isn't normalized, and it awaits a repeat, which sends its rank_update and its"
            " backtest again, and may be charged again."
        )

    return TrialFolioError(
        "provider.response_invalid",
        said(f"`{key}`", f"`{previous_key}`", "The response"),
        said(backtest.case_id, previous.case_id, f"The response of attempt {backtest.attempt_id}"),
    )
