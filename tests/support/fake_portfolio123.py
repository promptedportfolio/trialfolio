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
"""

import json
import socket
import struct
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import MappingProxyType
from typing import Final, Literal, override
from urllib.parse import urlsplit

SENT: Final = frozenset({"POST /auth", "POST /screen/backtest", "POST /rank", "GET /rank"})
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
