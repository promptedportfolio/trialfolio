"""The rule of a stale backtest, which the executor and the records check share,
`trialfolio.stale_backtests`.

Traces to docs/contracts.md, running an experiment (a stale backtest), and to D-45.

A session sends each case once, so two of its attempts never send the same definition and the
same backtest request, and each session's attempts are compared only with one another: these
parts of the rule are checked here, on the rule itself, as no session's records can show them.
"""

import uuid

from trialfolio.stale_backtests import SentBacktest, same_results, stale

RESULTS = b'{"cost": 5, "quotaRemaining": 4321, "stats": {"beta": 1.04, "cost": 1}}'


def sent(
    *,
    update: str = "definition-a",
    request: str = "request",
    response: bytes = RESULTS,
    session: int = 1,
) -> SentBacktest:
    return SentBacktest(
        case_id="case-0123456789abcdef",
        attempt_id=uuid.uuid4(),
        session=session,
        update_request=update,
        request=request,
        response=response,
    )


AFTER = sent(update="definition-b", response=RESULTS.replace(b'"cost": 5', b'"cost": 6'))
"""A backtest after another definition, with the previous one's results and another cost."""


def test_the_previous_backtests_results_after_another_definition_are_stale() -> None:
    assert stale(AFTER, sent())


def test_after_the_same_definition_the_same_results_arent_stale() -> None:
    assert not stale(sent(), sent())


def test_another_sessions_backtest_isnt_compared() -> None:
    assert not stale(AFTER, sent(session=2))
    assert not stale(AFTER, None)


def test_another_backtest_request_isnt_stale() -> None:
    assert not stale(AFTER, sent(request="another request"))


def test_only_the_top_levels_cost_and_quota_are_left_out() -> None:
    quota = RESULTS.replace(b"4321", b"4316")
    assert same_results(RESULTS, quota)
    nested = RESULTS.replace(b'"cost": 1}', b'"cost": 2}')
    assert not same_results(RESULTS, nested)
    assert not stale(sent(update="definition-b", response=nested), sent())


def test_results_are_compared_as_json_values() -> None:
    # The order of an object's keys doesn't matter, and NaN equals NaN, as in two copies of one
    # response, while a number's type does.
    reordered = b'{"stats": {"cost": 1, "beta": 1.04}, "quotaRemaining": 1, "cost": 9}'
    assert same_results(RESULTS, reordered)
    assert same_results(b'{"x": NaN}', b'{"x": NaN}')
    assert not same_results(b'{"x": 1}', b'{"x": 1.0}')


def test_a_response_that_isnt_json_equals_none() -> None:
    assert not same_results(b"not JSON", b"not JSON")
    assert not stale(sent(update="b", response=b"not JSON"), sent(response=b"not JSON"))
