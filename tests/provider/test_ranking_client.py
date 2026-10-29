"""The client's `rank_update` writes a case's definition into `ApiRankingSystem` through
`p123api`'s `rank_update`: it sends its params exactly as given, with no `id`, as one exchange,
and its failures are classified as a backtest's are, saying that the backtest wasn't sent.

From R04-T10, its `rank_get` reads the ranking system a snapshot configuration names through
`p123api`'s `rank_get`, by its name, as one exchange, and gives the 200's body its adapter holds,
decoded with the standard library's `json`, since the wrapper's result leaves out `cost` and
`quotaRemaining`; or the body undecoded when the wrapper raises after the 200.

Traces to docs/contracts.md, sending a definition (the calls, and their errors), HTTP exchanges,
and `p123api-rank-get` version 1; R04-AC03 (a `rank_update` is a provider request, recorded as
an exchange), R04-AC08 (the client's `rank_get` decodes the 200's body its adapter holds, `cost`
and `quotaRemaining` included, and saves the body undecoded when the wrapper raises after the
200), and R04-AC09 (the client's `rank_update` sends its params exactly as given, through
`p123api`'s `rank_update`, with no `id`). The real `p123api`, `requests`, and `urllib3` run over
the fake server, whose end-of-test check reads every `POST /rank` body, and every path, too.
"""

import json

import pytest

from tests.support.clients import ClientFactory, authenticate
from tests.support.fake_portfolio123 import FakePortfolio123, Reply, exchange
from tests.support.paths import RANKING_DEFINITIONS, RESPONSES
from trialfolio.contracts.attempt import Exchange
from trialfolio.provider import (
    DecodedResponse,
    P123ScreenBacktestClient,
    ProviderError,
    UndecodedResponse,
)

DEFINITION = RANKING_DEFINITIONS / "value-momentum.xml"

PARAMS: dict[str, object] = {
    "type": "stock",
    "nodes": DEFINITION.read_text(encoding="utf-8"),
    "rankingMethod": 2,
    "currency": "USD",
}
"""A `rank_update`'s params, as a plan gives them: the definition holds `…`, which isn't ASCII."""

BACKTEST_NOT_SENT = "so the case's screen backtest wasn't sent"


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
    assert client.exchanges == (exchange("POST /auth", 200), exchange("POST /rank", 200))
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
    assert client.exchanges[-1] == exchange("POST /rank", 200)


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
    assert client.exchanges[1] == exchange("POST /rank", status)
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


# A snapshot's rank_get (R04-AC08)

RANK_GET = (RESPONSES / "rank-get.json").read_bytes()
SNAPSHOT_NOT_SAVED = "So the snapshot has no definition.xml or snapshot.json."


def test_rank_get_decodes_the_body_its_adapter_holds(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    """The wrapper's `RankInfoResult` keeps only the fields it knows, so the client decodes the
    body itself: every field Portfolio123 sent, `cost` and `quotaRemaining` included."""
    authenticate(server, client)
    server.reply("/rank", Reply(200, RANK_GET), method="GET")

    sent = client.rank_get("Value and momentum")

    assert sent == DecodedResponse(json.loads(RANK_GET))
    assert isinstance(sent, DecodedResponse)
    assert isinstance(sent.payload, dict)
    assert (sent.payload["cost"], sent.payload["quotaRemaining"]) == (1, 4319)
    received = server.received[-1]
    # p123api sends the name as the query of GET /rank, and no ID.
    assert (received.method, received.path) == ("GET", "/rank?name=Value+and+momentum")
    assert received.body == b""
    assert client.exchanges == (exchange("POST /auth", 200), exchange("GET /rank", 200))


def test_a_rank_get_needs_trial_folios_own_authentication_first(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    with pytest.raises(RuntimeError):
        client.rank_get("Value and momentum")

    assert client.exchanges == ()
    assert server.requests() == []


def test_a_ranking_method_the_wrapper_doesnt_know_keeps_the_body_undecoded(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    """p123api raises after the 200 for a ranking method its enum doesn't hold, so the body is
    kept as it came, as for any request whose call raised after a 200."""
    body = (RESPONSES / "rank-get-unknown-method.json").read_bytes()
    authenticate(server, client)
    server.reply("/rank", Reply(200, body), method="GET")

    assert client.rank_get("Value and momentum") == UndecodedResponse(body)
    assert client.exchanges[-1] == exchange("GET /rank", 200)


def test_a_body_only_the_wrapper_could_decode_is_kept_undecoded(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    """`requests` decodes a body in the charset its response names, and `json` reads bytes as
    UTF-8, so a body in Latin-1 is one the wrapper returns, but `json` can't decode: it's kept
    as it came, as one the wrapper raised after is."""
    body = '{"name": "Caf\u00e9"}'.encode("latin-1")
    authenticate(server, client)
    server.reply(
        "/rank",
        Reply(200, body, headers={"Content-Type": "application/json; charset=latin-1"}),
        method="GET",
    )

    assert client.rank_get("Value and momentum") == UndecodedResponse(body)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "provider.unsupported_capability"),
        (402, "provider.quota_exceeded"),
        (403, "provider.auth_failed"),
        (404, "provider.request_rejected"),
        (503, "provider.outcome_unknown"),
    ],
)
def test_a_rank_gets_failure_is_classified_as_a_requests_is(
    server: FakePortfolio123, client: P123ScreenBacktestClient, status: int, code: str
) -> None:
    authenticate(server, client)
    server.reply("/rank", Reply(status, b"No such ranking system"), method="GET")

    with pytest.raises(ProviderError) as raised:
        client.rank_get("Value and momentum")

    assert raised.value.code == code
    assert "rank_get request" in raised.value.message
    assert SNAPSHOT_NOT_SAVED in raised.value.message
    assert [received.request for received in server.received[1:]] == ["GET /rank"]
    assert client.exchanges[1] == exchange("GET /rank", status)


def test_a_snapshots_failed_authentication_says_its_rank_get_wasnt_sent(
    server: FakePortfolio123, make_client: ClientFactory
) -> None:
    client = make_client(snapshot=True)
    server.reply("/auth", Reply(401, b""))

    with pytest.raises(ProviderError) as raised:
        client.authenticate()

    assert raised.value.code == "provider.auth_failed"
    assert raised.value.message.endswith("The rank_get request wasn't sent.")
    assert "backtest" not in raised.value.message
