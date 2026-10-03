"""The fake Portfolio123 server: a scripted HTTP server on localhost, the double for the network
below `urllib3` (release 0.1.0, test pairing).

Each request to a path takes the next reply scripted for it: a status, a body, and any headers,
such as `Location`. A reply can also wait first, reset the connection, or break its body off. A
request with no reply left gets a 404 with an empty body. The server records every complete
request it receives, so a test can show how many times each one arrived.

It answers with HTTP/1.0, so each connection carries one exchange, and the client opens a new one
for the next.
"""

import socket
import struct
import threading
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import MappingProxyType
from typing import Literal, override


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


@dataclass(frozen=True)
class Received:
    """One complete request the server received. Header names are lowercase."""

    method: str
    path: str
    headers: Mapping[str, str]
    body: bytes


class FakePortfolio123:
    """The server, listening on 127.0.0.1 until `close`."""

    def __init__(self) -> None:
        self._replies: dict[str, deque[Reply]] = {}
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

    def reply(self, path: str, *replies: Reply) -> None:
        """Adds replies for requests to `path`, used in order."""
        with self._lock:
            self._replies.setdefault(path, deque()).extend(replies)

    @property
    def received(self) -> tuple[Received, ...]:
        """Every complete request, in the order it arrived."""
        with self._lock:
            return tuple(self._received)

    def requests(self) -> list[str]:
        """Each request received, as its method and path, in order."""
        return [f"{r.method} {r.path}" for r in self.received]

    def close(self) -> None:
        """Stops listening, and cuts every reply's wait short. A later connection is refused."""
        self._stopping.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join()

    def _take(self, request: Received) -> Reply:
        with self._lock:
            self._received.append(request)
            replies = self._replies.get(request.path)
            return replies.popleft() if replies else Reply(status=404)


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
        if reply.delay and fake._stopping.wait(reply.delay):  # pyright: ignore[reportPrivateUsage]
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
