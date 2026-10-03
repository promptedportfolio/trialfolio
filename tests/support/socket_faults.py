"""Socket faults: failures a local server can't produce, made by replacing the socket calls
`urllib3` makes, the double for the network below `urllib3` (release 0.1.0, test pairing).

A fault applies only in the thread that installs it, so a fake server's threads are unaffected.
Each fault replaces the network guard's own wrapper for the test, and pytest's `monkeypatch`
puts the guard back afterwards.
"""

import errno
import socket
import threading
from collections.abc import Callable
from typing import Any

import pytest


class SocketFaults:
    """Installs faults in the calling thread, and counts its connection attempts."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._thread = threading.current_thread()
        self.connects = 0
        """How many times this thread called `connect` on a socket."""
        real_connect: Callable[..., Any] = socket.socket.connect

        def connect(sock: socket.socket, address: Any) -> None:
            if threading.current_thread() is self._thread:
                self.connects += 1
            real_connect(sock, address)

        monkeypatch.setattr(socket.socket, "connect", connect)

    def fail_name_lookup(self) -> None:
        """`socket.getaddrinfo` fails as a lookup of a name that doesn't exist does."""
        real: Callable[..., Any] = socket.getaddrinfo

        def getaddrinfo(*args: Any, **kwargs: Any) -> Any:
            if threading.current_thread() is self._thread:
                raise socket.gaierror(socket.EAI_NONAME, "nodename nor servname provided")
            return real(*args, **kwargs)

        self._monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    def interrupt_name_lookup(self) -> None:
        """`socket.getaddrinfo` raises `KeyboardInterrupt`, as Ctrl-C during the lookup does."""
        real: Callable[..., Any] = socket.getaddrinfo

        def getaddrinfo(*args: Any, **kwargs: Any) -> Any:
            if threading.current_thread() is self._thread:
                raise KeyboardInterrupt
            return real(*args, **kwargs)

        self._monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    def time_out_connect(self) -> None:
        """`connect` times out, as it does when the server never answers the handshake."""
        self._replace_connect(TimeoutError(errno.ETIMEDOUT, "timed out"))

    def interrupt_send(self) -> None:
        """`sendall`, which sends the request, raises `KeyboardInterrupt`, as Ctrl-C does."""
        real: Callable[..., Any] = socket.socket.sendall

        def sendall(sock: socket.socket, data: Any, *args: Any) -> None:
            if threading.current_thread() is self._thread:
                raise KeyboardInterrupt
            real(sock, data, *args)

        self._monkeypatch.setattr(socket.socket, "sendall", sendall)

    def _replace_connect(self, error: OSError) -> None:
        real: Callable[..., Any] = socket.socket.connect

        def connect(sock: socket.socket, address: Any) -> None:
            if threading.current_thread() is self._thread:
                self.connects += 1
                raise error
            real(sock, address)

        self._monkeypatch.setattr(socket.socket, "connect", connect)
