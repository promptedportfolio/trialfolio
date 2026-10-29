"""The fake Portfolio123 server: a scripted HTTP server on localhost, the double for the network
below `urllib3` (release 0.1.0, test pairing).

Each request to a path takes the next reply scripted for it: a status, a body, and any headers,
such as `Location`. A reply can also wait first, for a time or until the test releases it, reset
the connection, or break its body off. A request with no reply left gets a 404 with an empty body.
The server records every complete request it receives, so a test can show how many times each one
arrived.

From 0.4.0, `POST /rank` and `GET /rank` share a path, so a reply can be scripted for a method and
a path, which takes precedence over one scripted for the path alone. A request's path is matched
without its query, which the server records, so a test can check the `name` a `rank_get` sends
(release 0.4.0, test pairing).

It checks every request it received when it closes, at the end of each test that uses it, and the
test fails there when a request went to a path Trial Folio doesn't send, such as `/rank/create`
or `/rank/<id>/touch`, or when the body of a `POST /rank` isn't exactly
`{"type": "stock", "nodes": …, "rankingMethod": …, "currency": "USD"}`, in that order, with a
method of 2 or 4 (R04-AC09). So every test that sends a definition checks that Trial Folio writes
only `ApiRankingSystem`: a body with an `id` would write another system.

It answers with HTTP/1.0, so each connection carries one exchange, and the client opens a new one
for the next.

Beside it are replies the tests share: `AUTHENTICATED`, `response`, a response fixture's 200, and
`serve_success`, which scripts a run that succeeds. TS-T03 moved them here from the interface's
conftest. TS-T04 added the requests' names, `AUTH`, `RANK`, `RANK_GET`, and `BACKTEST`, as a
request's `request` gives them; `CREDENTIALS`, the canary credentials the client sends to the
server; `exchange`, an exchange with the server as an attempt record gives it; and
`BeforeTheBacktest`, the real client with an action just before each backtest's call, from
`tests/core/test_attempt_records.py`'s `Interposed` and `tests/provider/test_http_exchanges.py`'s
`BeforeTheRequest`, which were the same.
"""

import json
import socket
import struct
import threading
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import MappingProxyType
from typing import Final, Literal, override
from urllib.parse import urlsplit

from tests.support import canaries
from tests.support.paths import RESPONSES
from trialfolio.contracts.attempt import Exchange
from trialfolio.provider import Credentials, P123ScreenBacktestClient, ScreenBacktestResponse

AUTH: Final = "POST /auth"
"""Trial Folio's authentication call."""
RANK: Final = "POST /rank"
"""A `rank_update`, which writes a ranking definition into `ApiRankingSystem`."""
RANK_GET: Final = "GET /rank"
"""A `rank_get`, which reads a ranking system for a snapshot."""
BACKTEST: Final = "POST /screen/backtest"
"""A screen backtest."""

SENT: Final = frozenset({AUTH, BACKTEST, RANK, RANK_GET})
"""Every request Trial Folio sends, by its method and its path without the query."""

RANK_UPDATE_KEYS: Final = ("type", "nodes", "rankingMethod", "currency")
"""The params of a `rank_update`, in the order Trial Folio sends them (sending a definition)."""


@dataclass(frozen=True)
class Reply:
    """What the server does with one request."""

    status: int = 200
    body: bytes = b""
    headers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    delay: float = 0.0
    """Seconds to wait, after reading the request, before doing anything else."""
    action: Literal["send", "reset", "break_off"] = "send"
    """`reset` closes the connection with a TCP reset instead of answering. `break_off` sends the
    status, the headers, a `Content-Length` for the whole body, and only half the body."""
    release: threading.Event | None = None
    """An event to wait for, after any delay, before doing anything else: the test sets it to let
    the reply go."""


def distinct(*bodies: bytes) -> tuple[Reply, ...]:
    """A 200 for each of `bodies`, backtest responses that are JSON objects, each with a member of
    its own first, `fixtureReply`, its number from 1, which no layout reads, so no two have the
    same results, as backtests of cases ranked by different definitions wouldn't. A case whose
    response is the previous case's, apart from `cost` and `quotaRemaining`, after the same
    backtest request and a different definition, is flagged as a stale backtest (D-45)."""
    if not all(body.lstrip().startswith(b"{") for body in bodies):
        raise ValueError("each body is a JSON object")
    return each_its_own([Reply(200, body) for body in bodies])


def each_its_own(replies: Sequence[Reply]) -> tuple[Reply, ...]:
    """`replies`, with each 200 whose body is a JSON object given a member of its own, as
    `distinct` gives it, numbered from 1 among them, and each other reply as it is."""
    numbered: list[Reply] = []
    number = 0
    for reply in replies:
        if reply.status == 200 and reply.body.lstrip().startswith(b"{"):
            number += 1
            body = reply.body.replace(b"{", b'{"fixtureReply": %d, ' % number, 1)
            reply = replace(reply, body=body)
        numbered.append(reply)
    return tuple(numbered)


AUTHENTICATED: Final = Reply(200, canaries.TOKEN.encode())
"""Portfolio123's answer to a successful authentication: the token."""


def response(name: str) -> Reply:
    """A 200 whose body is the response fixture `name`, in `responses/`."""
    return Reply(200, (RESPONSES / name).read_bytes())


CREDENTIALS: Final = Credentials(canaries.API_ID, canaries.API_KEY)
"""The canary API ID and API key, which a client sends to the server, and which no log, record, or
output may hold."""


def exchange(
    request: str, status: int | None, result: str = "response", note: str | None = None
) -> Exchange:
    """An exchange with the server, `request` such as `AUTH`, as an attempt record gives it."""
    return Exchange.model_validate(
        {"request": request, "result": result, "status": status, "note": note}
    )


@dataclass(frozen=True)
class Received:
    """One complete request the server received. Header names are lowercase, and `path` holds
    any query the request sent."""

    method: str
    path: str
    headers: Mapping[str, str]
    body: bytes

    @property
    def request(self) -> str:
        """Its method and path, without the query, as an exchange names it."""
        return f"{self.method} {urlsplit(self.path).path}"


class _Pairs(list[tuple[str, object]]):
    """A JSON object's members, in the order its text gives them."""


def problems_of(received: Received) -> list[str]:
    """What's wrong with a request Trial Folio sent, by R04-AC09: a path it doesn't send, or a
    `POST /rank` whose body isn't exactly a `rank_update`'s params, in their order, compared as
    the JSON text gives them, never as a parsed mapping."""
    if received.request not in SENT:
        return [f"{received.request} is a request Trial Folio doesn't send"]
    if received.request != "POST /rank":
        return []
    try:
        body: object = json.loads(received.body, object_pairs_hook=_Pairs)
    except ValueError:
        return ["a POST /rank body isn't JSON"]
    if not isinstance(body, _Pairs) or [key for key, _ in body] != list(RANK_UPDATE_KEYS):
        return [f"a POST /rank body's keys aren't exactly {', '.join(RANK_UPDATE_KEYS)}, in order"]
    params = dict(body)
    method = params["rankingMethod"]
    found: list[str] = []
    if params["type"] != "stock":
        found.append("a POST /rank body's type isn't stock")
    if not isinstance(params["nodes"], str):
        found.append("a POST /rank body's nodes isn't text")
    if type(method) is not int or method not in (2, 4):
        found.append("a POST /rank body's rankingMethod isn't 2 or 4")
    if params["currency"] != "USD":
        found.append("a POST /rank body's currency isn't USD")
    return found


class FakePortfolio123:
    """The server, listening on 127.0.0.1 until `close`."""

    def __init__(self) -> None:
        self._replies: dict[tuple[str | None, str], deque[Reply]] = {}
        self._received: list[Received] = []
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._server = _Server(self)
        # A short poll interval, so close doesn't wait the default half second.
        self._thread = threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self._thread.start()
        host, port = self._server.server_address[:2]
        self.endpoint = f"http://{host!s}:{port}"
        """The URL to pass as the wrapper's endpoint."""

    def reply(self, path: str, *replies: Reply, method: str | None = None) -> None:
        """Adds replies for requests to `path`, used in order: requests of `method` only, when
        it's given, and of any method otherwise. A request takes a reply scripted for its method
        first."""
        with self._lock:
            self._replies.setdefault((method, path), deque()).extend(replies)

    @property
    def received(self) -> tuple[Received, ...]:
        """Every complete request, in the order it arrived."""
        with self._lock:
            return tuple(self._received)

    def requests(self) -> list[str]:
        """Each request received, as its method and path, in order."""
        return [f"{r.method} {r.path}" for r in self.received]

    def problems(self) -> list[str]:
        """What's wrong with the requests received, by R04-AC09, each once, in order."""
        found: list[str] = []
        for received in self.received:
            found.extend(problem for problem in problems_of(received) if problem not in found)
        return found

    def close(self) -> None:
        """Stops listening, and cuts every reply's wait short. A later connection is refused.
        Then it checks every request it received: an `AssertionError` lists what's wrong, which
        fails the test whose fixture closes it."""
        self._stopping.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()
        problems = self.problems()
        if problems:
            raise AssertionError(
                "The fake Portfolio123 server received requests Trial Folio doesn't send: "
                + "; ".join(problems)
            )

    def _take(self, request: Received) -> Reply:
        path = urlsplit(request.path).path
        with self._lock:
            self._received.append(request)
            replies = self._replies.get((request.method, path)) or self._replies.get((None, path))
            return replies.popleft() if replies else Reply(status=404)


class BeforeTheBacktest:
    """The real client, with an action just before each screen backtest's call: the provider
    client is a boundary the tests may stand in at (AGENTS.md, verification expectations)."""

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

    def rank_update(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        return self._client.rank_update(params)

    def rank_get(self, name: str) -> ScreenBacktestResponse:
        return self._client.rank_get(name)

    def close(self) -> None:
        self._client.close()


def serve_success(server: FakePortfolio123, body: str = "complete.json") -> None:
    """Scripts a run that succeeds: authentication, then the backtest's 200 with `body`."""
    server.reply("/auth", AUTHENTICATED)
    server.reply("/screen/backtest", response(body))


_POLL_SECONDS = 0.01
"""How often a reply waiting for its release checks whether the server is closing."""


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, fake: FakePortfolio123) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.fake = fake

    @override
    def handle_error(self, request: object, client_address: object) -> None:
        # A client that went away, after a timeout or a reset, isn't the test's failure.
        pass


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self._answer()

    def do_POST(self) -> None:
        self._answer()

    def do_DELETE(self) -> None:
        self._answer()

    @override
    def log_message(self, format: str, *args: object) -> None:
        pass

    def _answer(self) -> None:
        assert isinstance(self.server, _Server)
        fake = self.server.fake
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        if len(body) < length:
            return
        headers = {name.lower(): value for name, value in self.headers.items()}
        reply = fake._take(  # pyright: ignore[reportPrivateUsage]
            Received(self.command, self.path, MappingProxyType(headers), body)
        )
        stopping = fake._stopping  # pyright: ignore[reportPrivateUsage]
        if reply.delay and stopping.wait(reply.delay):
            return
        if reply.release is not None:
            while not reply.release.wait(_POLL_SECONDS):
                if stopping.is_set():
                    return
        if reply.action == "reset":
            # SO_LINGER with a zero timeout makes close send a reset instead of a FIN.
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            self.connection.close()
            return
        self.send_response(reply.status)
        for name, value in reply.headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(reply.body)))
        self.end_headers()
        if reply.action == "break_off":
            self.wfile.write(reply.body[: len(reply.body) // 2])
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        self.wfile.write(reply.body)
