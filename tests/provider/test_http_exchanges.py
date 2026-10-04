"""The transport adapter records every HTTP exchange the wrapper makes, and allows one exchange in
each call, over the real `p123api`, `requests`, and `urllib3`.

Traces to docs/contracts.md, HTTP exchanges, and ADR 0006's follow-up conditions, which R01-T09
verifies: every exchange passes through the adapter, each failure kind gets its documented result,
a second exchange in a call is refused before connecting, including the re-authentication and a
redirect, and `urllib3` retries stay at `Retry(0, read=False)`. Also to R01-AC26's cases and the
codes of 0.1.0's failure table for authentication and the request, R01-AC06 (a read timeout is
`interrupted` and the server receives the request once), and R01-AC07 (the exchanges, in order).
Through attempt recording, each case also gives the attempt its outcome, code, and
`possibly_charged`, as the failure table does, and R01-AC07's `provider_requests`: 1 after a
success, and 0 after a failed authentication or a `not_connected` request.
"""

import json
import socket
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest
import requests

from tests.provider.conftest import PARAMS, ClientFactory, authenticate
from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.socket_faults import SocketFaults
from trialfolio.attempts import Attempt, AttemptStatus, provider_requests, read_attempt
from trialfolio.configuration import read_screen_configuration
from trialfolio.contracts.attempt import Exchange
from trialfolio.planning import build_plan, installed_versions
from trialfolio.provider import (
    REQUEST_TIMEOUT_SECONDS,
    DecodedResponse,
    ExchangeRecordingAdapter,
    ExchangeRefused,
    P123ScreenBacktestClient,
    ProviderError,
    ScreenBacktestResponse,
    UndecodedResponse,
)
from trialfolio.storage import LocalArtifactStore

AUTH = "POST /auth"
BACKTEST = "POST /screen/backtest"

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
NOT_JSON = (FIXTURES / "responses/not-json.txt").read_bytes()
"""The response fixture whose body isn't JSON."""


def response(request: str, status: int) -> Exchange:
    return Exchange(request=request, result="response", status=status, note=None)


def ended(request: str, result: str) -> Exchange:
    return Exchange.model_validate(
        {"request": request, "result": result, "status": None, "note": None}
    )


AUTHENTICATED = response(AUTH, 200)


@pytest.fixture
def not_tls() -> Iterator[str]:
    """An `https://` endpoint whose server answers the TLS handshake with plain text."""
    listener = socket.create_server(("127.0.0.1", 0))

    def answer() -> None:
        try:
            connection, _ = listener.accept()
        except OSError:
            return
        with connection:
            connection.sendall(b"HTTP/1.0 400 Bad Request\r\n\r\n")

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    yield f"https://127.0.0.1:{listener.getsockname()[1]}"
    listener.close()
    thread.join()


# Success


def test_a_success_records_authentication_then_the_request(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    payload = {"stats": {"port": {"total_return": 12.3}}, "cost": 5, "quotaRemaining": 995}
    server.reply("/screen/backtest", Reply(200, json.dumps(payload).encode()))

    authenticate(server, client)
    assert client.authenticated
    result = client.screen_backtest(PARAMS)

    assert result == DecodedResponse(payload)
    # Every exchange passed through the adapter: it recorded exactly what the server received.
    assert client.exchanges == (AUTHENTICATED, response(BACKTEST, 200))
    assert server.requests() == [AUTH, BACKTEST]
    sent = server.received[1]
    assert json.loads(sent.body) == PARAMS
    assert sent.headers["authorization"] == f"Bearer {canaries.TOKEN}"
    # The authentication body is the token, and the adapter never keeps it.
    assert canaries.TOKEN not in repr(client.exchanges)


def test_an_https_endpoint_passes_through_the_adapter_and_a_tls_failure_is_interrupted(
    make_client: ClientFactory, not_tls: str
) -> None:
    client = make_client(endpoint=not_tls)

    with pytest.raises(ProviderError) as raised:
        client.authenticate()

    assert client.exchanges == (ended(AUTH, "interrupted"),)
    assert raised.value.code == "provider.unavailable"


# Not connected: provably not sent


@pytest.mark.parametrize("fault", ["name lookup", "refused", "connect timeout"])
def test_a_request_that_never_connected_is_not_connected(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    faults: SocketFaults,
    fault: str,
) -> None:
    authenticate(server, client)
    connects = faults.connects
    match fault:
        case "name lookup":
            faults.fail_name_lookup()
        case "refused":
            server.close()
        case _:
            faults.time_out_connect()

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    assert client.exchanges == (AUTHENTICATED, ended(BACKTEST, "not_connected"))
    assert raised.value.code == "provider.unavailable"
    assert "wasn't sent" in raised.value.message
    assert server.requests() == [AUTH]
    # urllib3 didn't try to connect again.
    assert faults.connects - connects == (0 if fault == "name lookup" else 1)


@pytest.mark.parametrize("fault", ["name lookup", "refused", "connect timeout"])
def test_authentication_that_never_connected_is_not_connected(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    faults: SocketFaults,
    fault: str,
) -> None:
    match fault:
        case "name lookup":
            faults.fail_name_lookup()
        case "refused":
            server.close()
        case _:
            faults.time_out_connect()

    with pytest.raises(ProviderError) as raised:
        client.authenticate()

    assert client.exchanges == (ended(AUTH, "not_connected"),)
    assert raised.value.code == "provider.unavailable"
    assert not client.authenticated
    assert faults.connects == (0 if fault == "name lookup" else 1)


def test_a_refused_proxy_connection_is_not_connected(
    server: FakePortfolio123, faults: SocketFaults
) -> None:
    # 0.1.0's client uses no proxy, so this drives the adapter directly. The rule unwraps a
    # urllib3 ProxyError, so a later release that adds a proxy keeps it.
    adapter = ExchangeRecordingAdapter()
    session = requests.Session()
    session.trust_env = False
    session.mount("http://", adapter)
    session.proxies = {"http": server.endpoint}
    server.close()

    with adapter.call("request"), pytest.raises(requests.exceptions.ProxyError):
        session.post("http://127.0.0.1:9/screen/backtest")

    assert adapter.exchanges == (ended(BACKTEST, "not_connected"),)
    assert faults.connects == 1


# Interrupted: possibly sent


@pytest.mark.parametrize(
    ("reply", "timeout"),
    [
        pytest.param(Reply(action="reset"), 300, id="reset"),
        pytest.param(Reply(200, b"{}", delay=3), 1, id="read timeout"),
        pytest.param(Reply(200, b'{"stats": {}}', action="break_off"), 300, id="body breaks off"),
    ],
)
def test_a_request_without_a_complete_response_is_interrupted(
    server: FakePortfolio123, make_client: ClientFactory, reply: Reply, timeout: int
) -> None:
    client = make_client(timeout=timeout)
    authenticate(server, client)
    server.reply("/screen/backtest", reply)

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    assert client.exchanges == (AUTHENTICATED, ended(BACKTEST, "interrupted"))
    assert raised.value.code == "provider.outcome_unknown"
    assert "may have been charged" in raised.value.message
    # Neither urllib3 nor the wrapper sent it again.
    assert server.requests() == [AUTH, BACKTEST]


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param(Reply(action="reset"), id="reset"),
        pytest.param(Reply(200, canaries.TOKEN.encode(), action="break_off"), id="breaks off"),
    ],
)
def test_authentication_without_a_complete_response_is_interrupted(
    server: FakePortfolio123, client: P123ScreenBacktestClient, reply: Reply
) -> None:
    server.reply("/auth", reply)

    with pytest.raises(ProviderError) as raised:
        client.authenticate()

    assert client.exchanges == (ended(AUTH, "interrupted"),)
    assert raised.value.code == "provider.unavailable"
    assert server.requests() == [AUTH]


def test_ctrl_c_while_the_request_is_sent_leaves_it_interrupted(
    server: FakePortfolio123, client: P123ScreenBacktestClient, faults: SocketFaults
) -> None:
    authenticate(server, client)
    faults.interrupt_send()

    with pytest.raises(KeyboardInterrupt):
        client.screen_backtest(PARAMS)

    # Recorded before it was sent, so the interrupt left it without a result.
    assert client.exchanges == (AUTHENTICATED, ended(BACKTEST, "interrupted"))


@pytest.mark.parametrize("stage", ["name lookup", "send"])
def test_ctrl_c_during_authentication_leaves_it_interrupted(
    client: P123ScreenBacktestClient, faults: SocketFaults, stage: str
) -> None:
    if stage == "name lookup":
        faults.interrupt_name_lookup()
    else:
        faults.interrupt_send()

    with pytest.raises(KeyboardInterrupt):
        client.authenticate()

    assert client.exchanges == (ended(AUTH, "interrupted"),)


# Authentication's statuses (0.1.0's failure table)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "provider.auth_failed"),
        (401, "provider.auth_failed"),
        (402, "provider.auth_failed"),
        (403, "provider.auth_failed"),
        (406, "provider.auth_failed"),
        (204, "provider.request_rejected"),
        (300, "provider.request_rejected"),
        (404, "provider.request_rejected"),
        (429, "provider.request_rejected"),
        (503, "provider.unavailable"),
    ],
)
def test_authentication_statuses_give_their_documented_codes(
    server: FakePortfolio123, client: P123ScreenBacktestClient, status: int, code: str
) -> None:
    server.reply("/auth", Reply(status))

    with pytest.raises(ProviderError) as raised:
        client.authenticate()

    assert raised.value.code == code
    assert f"HTTP {status}" in raised.value.message
    assert "wasn't sent" in raised.value.message
    if code == "provider.request_rejected":
        assert "isn't a problem with the API ID or key" in raised.value.message
    assert client.exchanges == (response(AUTH, status),)
    # The wrapper made one attempt.
    assert server.requests() == [AUTH]
    assert not client.authenticated


def test_a_redirect_on_authentication_is_refused_before_connecting(
    server: FakePortfolio123, client: P123ScreenBacktestClient, faults: SocketFaults
) -> None:
    server.reply("/auth", Reply(307, headers={"Location": f"{server.endpoint}/elsewhere"}))

    with pytest.raises(ProviderError) as raised:
        client.authenticate()

    assert raised.value.code == "provider.request_rejected"
    assert "HTTP 307" in raised.value.message
    assert "doesn't follow redirects" in raised.value.message
    assert client.exchanges == (response(AUTH, 307),)
    assert server.requests() == [AUTH]
    assert faults.connects == 1


# The request's statuses (0.1.0's failure table)


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "provider.unsupported_capability"),
        (402, "provider.quota_exceeded"),
        (204, "provider.request_rejected"),
        (300, "provider.request_rejected"),
        (404, "provider.request_rejected"),
        (429, "provider.request_rejected"),
        (500, "provider.outcome_unknown"),
        (503, "provider.outcome_unknown"),
    ],
)
def test_request_statuses_give_their_documented_codes(
    server: FakePortfolio123, client: P123ScreenBacktestClient, status: int, code: str
) -> None:
    authenticate(server, client)
    server.reply("/screen/backtest", Reply(status))

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    assert raised.value.code == code
    assert f"HTTP {status}" in raised.value.message
    assert "may have been charged" in raised.value.message
    assert client.exchanges == (AUTHENTICATED, response(BACKTEST, status))
    # Sent once, even after a 5xx, which the wrapper would otherwise retry.
    assert server.requests() == [AUTH, BACKTEST]


@pytest.mark.parametrize("call", ["authentication", "request"])
def test_a_status_that_isnt_http_is_interrupted(
    server: FakePortfolio123, client: P123ScreenBacktestClient, call: str
) -> None:
    # HTTP statuses run from 100 to 599 (RFC 9110, section 15), so no complete response arrived.
    if call == "authentication":
        server.reply("/auth", Reply(600))
        with pytest.raises(ProviderError) as raised:
            client.authenticate()
        assert client.exchanges == (ended(AUTH, "interrupted"),)
        assert raised.value.code == "provider.unavailable"
    else:
        authenticate(server, client)
        server.reply("/screen/backtest", Reply(600))
        with pytest.raises(ProviderError) as raised:
            client.screen_backtest(PARAMS)
        assert client.exchanges == (AUTHENTICATED, ended(BACKTEST, "interrupted"))
        assert raised.value.code == "provider.outcome_unknown"


@pytest.mark.parametrize(
    "case", ["authentication 503", "request 503", "request refused", "request reset"]
)
def test_the_wrapper_makes_one_attempt_in_each_call(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    caplog: pytest.LogCaptureFixture,
    case: str,
) -> None:
    # Configured with set_max_request_retries(1), the wrapper never tries again, so the adapter
    # never has to refuse its retry as a second exchange.
    with pytest.raises(ProviderError):
        if case == "authentication 503":
            server.reply("/auth", Reply(503))
            client.authenticate()
        else:
            authenticate(server, client)
            if case == "request 503":
                server.reply("/screen/backtest", Reply(503))
            elif case == "request refused":
                server.close()
            else:
                server.reply("/screen/backtest", Reply(action="reset"))
            client.screen_backtest(PARAMS)

    events = [getattr(record, "event", None) for record in caplog.records]
    assert "provider.request.refused" not in events


def test_a_400_carries_portfolio123s_message(
    server: FakePortfolio123, client: P123ScreenBacktestClient
) -> None:
    authenticate(server, client)
    server.reply("/screen/backtest", Reply(400, b"Invalid parameter: pitMethod"))

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    assert raised.value.code == "provider.unsupported_capability"
    assert raised.value.provider_message == "Invalid parameter: pitMethod"
    assert raised.value.message.endswith('Portfolio123\'s message: "Invalid parameter: pitMethod"')


@pytest.mark.parametrize("status", [401, 403])
def test_the_wrappers_reauthentication_is_refused_before_connecting(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    faults: SocketFaults,
    status: int,
) -> None:
    authenticate(server, client)
    server.reply("/screen/backtest", Reply(status))
    server.reply("/auth", Reply(200, b"second-token"))

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    assert raised.value.code == "provider.auth_failed"
    assert f"HTTP {status}" in raised.value.message
    assert "refused the wrapper's re-authentication" in raised.value.message
    assert "right after Trial Folio authenticated" in raised.value.message
    assert client.exchanges == (AUTHENTICATED, response(BACKTEST, status))
    # Neither the re-authentication nor a resend reached the server, or opened a connection.
    assert server.requests() == [AUTH, BACKTEST]
    assert faults.connects == 2
    # The wrapper dropped its token, so a later request needs Trial Folio to authenticate again.
    assert not client.authenticated


def test_a_redirect_on_the_request_is_refused_before_connecting(
    server: FakePortfolio123, client: P123ScreenBacktestClient, faults: SocketFaults
) -> None:
    authenticate(server, client)
    server.reply(
        "/screen/backtest", Reply(307, headers={"Location": f"{server.endpoint}/elsewhere"})
    )

    with pytest.raises(ProviderError) as raised:
        client.screen_backtest(PARAMS)

    assert raised.value.code == "provider.request_rejected"
    assert "redirect (HTTP 307)" in raised.value.message
    assert raised.value.provider_message is None
    assert client.exchanges == (AUTHENTICATED, response(BACKTEST, 307))
    assert server.requests() == [AUTH, BACKTEST]
    assert faults.connects == 2


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(NOT_JSON, id="not JSON"),
        pytest.param(b"", id="empty"),
        # Nested past the decoder's recursion limit, so it raises RecursionError, not a
        # JSONDecodeError: any failure after the 200 means the wrapper couldn't decode it.
        pytest.param(b"[" * 100_000 + b"]" * 100_000, id="too deep"),
    ],
)
def test_a_200_the_wrapper_cant_decode_is_kept_undecoded(
    server: FakePortfolio123, client: P123ScreenBacktestClient, body: bytes
) -> None:
    authenticate(server, client)
    server.reply("/screen/backtest", Reply(200, body))

    result = client.screen_backtest(PARAMS)

    assert result == UndecodedResponse(body)
    assert client.exchanges == (AUTHENTICATED, response(BACKTEST, 200))
    assert server.requests() == [AUTH, BACKTEST]


# No retries inside an exchange


def test_the_adapter_keeps_requests_default_urllib3_retry_setting() -> None:
    retries = ExchangeRecordingAdapter().max_retries

    # requests' default, Retry(0, read=False): no attempt is retried, and a read error is
    # raised as it is, never wrapped in MaxRetryError.
    assert retries.total == 0
    assert retries.read is False
    assert (retries.connect, retries.redirect, retries.status, retries.other) == (None,) * 4


@pytest.mark.parametrize(
    ("kind", "status", "held"),
    [
        ("authentication", 200, False),
        ("request", 200, True),
        ("request", 404, False),
    ],
)
def test_the_adapter_holds_only_the_body_of_a_200_on_the_requests_exchange(
    server: FakePortfolio123, kind: Literal["authentication", "request"], status: int, held: bool
) -> None:
    # An authentication body is the token, so it's never held.
    adapter = ExchangeRecordingAdapter()
    session = requests.Session()
    session.mount("http://", adapter)
    server.reply("/path", Reply(status, b"body"))

    with adapter.call(kind) as call:
        session.post(f"{server.endpoint}/path")

    assert call.body == (b"body" if held else None)
    assert adapter.exchanges == (response("POST /path", status),)


def test_an_exchange_outside_a_call_is_refused() -> None:
    adapter = ExchangeRecordingAdapter()
    session = requests.Session()
    session.mount("http://", adapter)

    with pytest.raises(ExchangeRefused):
        session.get("http://127.0.0.1:9/")

    assert adapter.exchanges == ()


# Each case's outcome, code, and possibly charged, through attempt recording (0.1.0's failure
# table)


type Fault = Callable[[FakePortfolio123, SocketFaults, str], object]
"""Sets up how a call ends, given the fake server, the socket faults, and the call's path."""


def replying(reply: Reply) -> Fault:
    return lambda server, _faults, path: server.reply(path, reply)


def redirecting(server: FakePortfolio123, _faults: SocketFaults, path: str) -> None:
    server.reply(path, Reply(307, headers={"Location": f"{server.endpoint}/elsewhere"}))


NAME_LOOKUP: Fault = lambda _server, faults, _path: faults.fail_name_lookup()
REFUSED: Fault = lambda server, _faults, _path: server.close()
CONNECT_TIMEOUT: Fault = lambda _server, faults, _path: faults.time_out_connect()
CTRL_C: Fault = lambda _server, faults, _path: faults.interrupt_send()


@dataclass(frozen=True)
class Ending:
    """How one of an attempt's calls ends, and what 0.1.0's failure table gives the attempt."""

    call: Literal["authentication", "request"]
    fault: Fault
    result: int | Literal["not_connected", "interrupted"]
    """The call's exchange: its status, or how it ended without one."""
    outcome: Literal["succeeded", "failed", "unknown"]
    code: str | None
    possibly_charged: bool
    timeout: int = REQUEST_TIMEOUT_SECONDS

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        request = AUTH if self.call == "authentication" else BACKTEST
        if isinstance(self.result, int):
            last = response(request, self.result)
        else:
            last = ended(request, self.result)
        return (last,) if self.call == "authentication" else (AUTHENTICATED, last)


def on_authentication(
    fault: Fault, result: int | Literal["not_connected", "interrupted"], code: str
) -> Ending:
    """Authentication's ending: the attempt is failed, and not possibly charged, because the
    request wasn't sent."""
    return Ending("authentication", fault, result, "failed", code, possibly_charged=False)


def on_request(
    fault: Fault,
    result: int | Literal["not_connected", "interrupted"],
    outcome: Literal["succeeded", "failed", "unknown"],
    code: str | None,
    *,
    timeout: int = REQUEST_TIMEOUT_SECONDS,
) -> Ending:
    """The request's ending: possibly charged, unless it never connected."""
    charged = result != "not_connected"
    return Ending("request", fault, result, outcome, code, charged, timeout)


ENDINGS: dict[str, Ending] = {
    "authentication name lookup": on_authentication(
        NAME_LOOKUP, "not_connected", "provider.unavailable"
    ),
    "authentication refused": on_authentication(REFUSED, "not_connected", "provider.unavailable"),
    "authentication connect timeout": on_authentication(
        CONNECT_TIMEOUT, "not_connected", "provider.unavailable"
    ),
    "authentication reset": on_authentication(
        replying(Reply(action="reset")), "interrupted", "provider.unavailable"
    ),
    "authentication breaks off": on_authentication(
        replying(Reply(200, canaries.TOKEN.encode(), action="break_off")),
        "interrupted",
        "provider.unavailable",
    ),
    "authentication ctrl-c": on_authentication(CTRL_C, "interrupted", "command.interrupted"),
    **{
        f"authentication {status}": on_authentication(replying(Reply(status)), status, code)
        for status, code in [
            (400, "provider.auth_failed"),
            (401, "provider.auth_failed"),
            (402, "provider.auth_failed"),
            (403, "provider.auth_failed"),
            (406, "provider.auth_failed"),
            (204, "provider.request_rejected"),
            (300, "provider.request_rejected"),
            (404, "provider.request_rejected"),
            (429, "provider.request_rejected"),
            (503, "provider.unavailable"),
        ]
    },
    "authentication 307": on_authentication(redirecting, 307, "provider.request_rejected"),
    "authentication 600": on_authentication(
        replying(Reply(600)), "interrupted", "provider.unavailable"
    ),
    "request 200": on_request(
        replying(Reply(200, b'{"stats": {}, "cost": 5}')), 200, "succeeded", None
    ),
    # Succeeded for capture: normalizing the saved body flags `provider.response_invalid`.
    "request 200 not JSON": on_request(replying(Reply(200, NOT_JSON)), 200, "succeeded", None),
    "request name lookup": on_request(
        NAME_LOOKUP, "not_connected", "failed", "provider.unavailable"
    ),
    "request refused": on_request(REFUSED, "not_connected", "failed", "provider.unavailable"),
    "request connect timeout": on_request(
        CONNECT_TIMEOUT, "not_connected", "failed", "provider.unavailable"
    ),
    "request reset": on_request(
        replying(Reply(action="reset")), "interrupted", "unknown", "provider.outcome_unknown"
    ),
    "request read timeout": on_request(
        replying(Reply(200, b"{}", delay=3)),
        "interrupted",
        "unknown",
        "provider.outcome_unknown",
        timeout=1,
    ),
    "request breaks off": on_request(
        replying(Reply(200, b'{"stats": {}}', action="break_off")),
        "interrupted",
        "unknown",
        "provider.outcome_unknown",
    ),
    "request ctrl-c": on_request(CTRL_C, "interrupted", "unknown", "command.interrupted"),
    **{
        f"request {status}": on_request(replying(Reply(status)), status, "failed", code)
        for status, code in [
            (400, "provider.unsupported_capability"),
            (401, "provider.auth_failed"),
            (402, "provider.quota_exceeded"),
            (403, "provider.auth_failed"),
            (204, "provider.request_rejected"),
            (300, "provider.request_rejected"),
            (404, "provider.request_rejected"),
            (429, "provider.request_rejected"),
        ]
    },
    **{
        f"request {status}": on_request(
            replying(Reply(status)), status, "unknown", "provider.outcome_unknown"
        )
        for status in (500, 503)
    },
    "request 307": on_request(redirecting, 307, "failed", "provider.request_rejected"),
    "request 600": on_request(
        replying(Reply(600)), "interrupted", "unknown", "provider.outcome_unknown"
    ),
}


class BeforeTheRequest:
    """The real client, with an action just before the request's call, once Trial Folio has
    authenticated: the provider client is a boundary the tests may stand in at (AGENTS.md,
    verification expectations)."""

    def __init__(self, client: P123ScreenBacktestClient, action: Callable[[], object]) -> None:
        self._client = client
        self._action = action

    @property
    def authenticated(self) -> bool:
        return self._client.authenticated

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        return self._client.exchanges

    def authenticate(self) -> None:
        self._client.authenticate()

    def screen_backtest(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        self._action()
        return self._client.screen_backtest(params)

    def close(self) -> None:
        self._client.close()


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "out"


@pytest.fixture
def attempt(out: Path) -> Attempt:
    """An attempt of `formula.yaml`'s plan, in an output directory claimed as `run` claims it."""
    path = FIXTURES / "screen-configs/formula.yaml"
    plan = build_plan(read_screen_configuration(path.read_bytes(), path.name), installed_versions())
    store = LocalArtifactStore(out)
    store.claim("plan.json", plan.model_dump_json(indent=2).encode())
    return Attempt(plan, plan.plan_hash, store)


@pytest.mark.parametrize("ending", ENDINGS.values(), ids=ENDINGS.keys())
def test_each_ending_gives_the_attempt_its_documented_outcome_and_possibly_charged(
    server: FakePortfolio123,
    make_client: ClientFactory,
    faults: SocketFaults,
    attempt: Attempt,
    out: Path,
    ending: Ending,
) -> None:
    client = make_client(timeout=ending.timeout)
    if ending.call == "authentication":
        ending.fault(server, faults, "/auth")
        result = attempt.run(client)
    else:
        server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
        result = attempt.run(
            BeforeTheRequest(client, lambda: ending.fault(server, faults, "/screen/backtest"))
        )

    record = result.record
    assert result.recorded
    assert record.exchanges == ending.exchanges
    assert record.outcome == ending.outcome
    assert record.possibly_charged is ending.possibly_charged
    assert (record.error and record.error.code) == ending.code
    assert (result.error and result.error.code) == ending.code
    # The request counts once if it may have reached Portfolio123, and authentication never does
    # (R01-AC07). Saved, the attempt reads as it was recorded.
    requests = 1 if ending.possibly_charged else 0
    assert provider_requests(record) == requests
    assert read_attempt(LocalArtifactStore(out), attempt.case_id, attempt.attempt_id) == (
        AttemptStatus(attempt.attempt_id, ending.outcome, ending.possibly_charged, requests)
    )
    # No request arrived twice, and nothing else arrived: no resend, re-authentication, or
    # redirect's target.
    assert server.requests() in ([], [AUTH], [AUTH, BACKTEST])
