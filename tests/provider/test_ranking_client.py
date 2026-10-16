"""The client's `rank_update` writes a case's definition into `ApiRankingSystem` through
`p123api`'s `rank_update`: it sends its params exactly as given, with no `id`, as one exchange,
and its failures are classified as a backtest's are, saying that the backtest wasn't sent.

Traces to docs/contracts.md, sending a definition (the calls, and their errors), and HTTP
exchanges; R04-AC03 (a `rank_update` is a provider request, recorded as an exchange), and
R04-AC09 (the client's `rank_update` sends its params exactly as given, through `p123api`'s
`rank_update`, with no `id`). The real `p123api`, `requests`, and `urllib3` run over the fake
server, whose end-of-test check reads every `POST /rank` body too.
"""

import json
from pathlib import Path

import pytest

from tests.provider.conftest import ClientFactory, authenticate
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.contracts.attempt import Exchange
from trialfolio.provider import (
    DecodedResponse,
    P123ScreenBacktestClient,
    ProviderError,
    UndecodedResponse,
)

RESPONSES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"
DEFINITION = (
    Path(__file__).resolve().parents[1] / "fixtures" / "experiment-configs" / "ranking"
).joinpath("value-momentum.xml")

PARAMS: dict[str, object] = {
    "type": "stock",
    "nodes": DEFINITION.read_text(encoding="utf-8"),
    "rankingMethod": 2,
    "currency": "USD",
}
"""A `rank_update`'s params, as a plan gives them: the definition holds `…`, which isn't ASCII."""

BACKTEST_NOT_SENT = "so the case's screen backtest wasn't sent"


def response(request: str, status: int) -> Exchange:
    return Exchange(request=request, result="response", status=status, note=None)


def test_rank_update_sends_its_params_exactly_as_given_with_no_id(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    authenticate(server, client)
    server.reply("/rank", Reply(200, (RESPONSES / "rank-update.json").read_bytes()), method="POST")

    sent = client.rank_update(PARAMS)

    assert sent == DecodedResponse({"cost": 1, "quotaRemaining": 4320})
    received = server.received[-1]
    assert (received.method, received.path) == ("POST", "/rank")
    # `requests` writes the body with `json.dumps`, so its text, its keys' order and the
    # definition's escapes included, is the params' as the plan gives them.
    assert received.body == json.dumps(PARAMS).encode()
    assert list(json.loads(received.body)) == ["type", "nodes", "rankingMethod", "currency"]
    assert "id" not in json.loads(received.body)
    assert client.exchanges == (response("POST /auth", 200), response("POST /rank", 200))
    assert server.problems() == []


def test_a_rank_update_needs_trial_folios_own_authentication_first(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    with pytest.raises(RuntimeError):
        client.rank_update(PARAMS)

    assert client.exchanges == ()
    assert server.requests() == []


def test_a_200_the_wrapper_cant_decode_is_kept_undecoded(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    authenticate(server, client)
    server.reply("/rank", Reply(200, b"<html>not JSON</html>"), method="POST")

    assert client.rank_update(PARAMS) == UndecodedResponse(b"<html>not JSON</html>")
    assert client.exchanges[-1] == response("POST /rank", 200)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "provider.unsupported_capability"),
        (409, "provider.unsupported_capability"),
        (402, "provider.quota_exceeded"),
        (401, "provider.auth_failed"),
        (403, "provider.auth_failed"),
        (503, "provider.outcome_unknown"),
        (418, "provider.request_rejected"),
    ],
)
def test_a_rank_updates_failure_is_classified_as_a_requests_is(
    server: FakePortfolio123, client: P123ScreenBacktestClient, status: int, code: str
) -> None:
    authenticate(server, client)
    server.reply("/rank", Reply(status, b"Invalid ranking system"), method="POST")

    with pytest.raises(ProviderError) as raised:
        client.rank_update(PARAMS)

    assert raised.value.code == code
    assert "rank_update request" in raised.value.message
    assert BACKTEST_NOT_SENT in raised.value.message
    # Sent once: a 401 or 403's re-authentication and resend were refused.
    assert server.requests()[1:] == ["POST /rank"]
    assert client.exchanges[1] == response("POST /rank", status)
    assert client.authenticated == (status not in (401, 403))


def test_a_rejected_definition_keeps_portfolio123s_message(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    authenticate(server, client)
    server.reply("/rank", Reply(400, b"Invalid weight"), method="POST")

    with pytest.raises(ProviderError) as raised:
        client.rank_update(PARAMS)

    assert raised.value.provider_message == "Invalid weight"
    assert "doesn't accept the ranking definition" in raised.value.message
    # The logged message never holds Portfolio123's text.
    assert "Invalid weight" not in raised.value.log_message


def test_a_rank_update_that_times_out_has_an_unknown_outcome(
    server: FakePortfolio123, make_client: ClientFactory
) -> None:
    client = make_client(timeout=1)
    authenticate(server, client)
    server.reply("/rank", Reply(200, b"{}", delay=3), method="POST")

    with pytest.raises(ProviderError) as raised:
        client.rank_update(PARAMS)

    assert raised.value.code == "provider.outcome_unknown"
    assert BACKTEST_NOT_SENT in raised.value.message
    assert client.exchanges[-1] == Exchange(
        request="POST /rank", result="interrupted", status=None, note=None
    )


def test_a_backtests_messages_are_unchanged(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    # The backtest's message names its request, and says nothing of a definition.
    authenticate(server, client)
    server.reply("/screen/backtest", Reply(400, b""))

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest({"screen": {}})

    assert raised.value.message == (
        "Portfolio123 rejected the screen backtest request (HTTP 400): it doesn't support a"
        " setting or value in it. The request may have been charged. Check the configuration"
        " before running the command again, which is a new attempt."
    )
