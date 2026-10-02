"""The network guard: tests may reach localhost and nothing else (P-12).

The root conftest installs it in the test process, and ``guarded_site/sitecustomize.py`` installs
it in every Python subprocess the suite starts. For any host but localhost, it refuses
``connect``, ``connect_ex``, and ``sendto`` on a socket, and the ``socket`` module's name and
address lookups, before anything leaves the machine. A lookup of another name never reaches a
resolver.

A refusal raises ``NetworkAccessRefused``. It derives from ``BaseException``, so no
``except Exception`` or ``except OSError`` handler, in Trial Folio, ``requests``, or ``urllib3``,
can mistake it for a provider failure and carry on. A test that reaches another host fails.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Any, NoReturn

# Marks the installed guard, so installing it twice wraps nothing twice.
_MARK = "_trialfolio_network_guard"

_LOOKUPS = ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")


class NetworkAccessRefused(BaseException):
    """A test tried to reach a host other than localhost."""


def _is_local(host: object) -> bool:
    """Whether a host, as a socket call receives it, names this machine's loopback interface."""
    if host is None:  # getaddrinfo(None, port) resolves to loopback.
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    name = host.rstrip(".").lower()
    if name == "localhost":
        return True
    try:
        address = ipaddress.ip_address(name.split("%", 1)[0])  # Drop an IPv6 zone.
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback


def _refuse(action: str, host: object) -> NoReturn:
    raise NetworkAccessRefused(
        f"network guard: refused {action} for {host!r}; tests may reach only localhost (P-12)"
    )


def _check_address(sock: socket.socket, address: object, action: str) -> None:
    # Unix and other local families have no host to check.
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        return
    if isinstance(address, tuple) and address:
        host: object = address[0]
        if not _is_local(host):
            _refuse(action, host)


def _guard_lookup(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def guarded(host: object, *args: Any, **kwargs: Any) -> Any:
        # getnameinfo takes a socket address; the others take a host.
        target: object = host[0] if isinstance(host, tuple) and host else host
        if not _is_local(target):
            _refuse(name, target)
        return original(host, *args, **kwargs)

    return guarded


def install() -> None:
    """Install the guard in this process. Installing it again changes nothing."""
    if getattr(socket.socket.connect, _MARK, False):
        return

    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex
    sendto = socket.socket.sendto

    def guarded_connect(self: socket.socket, address: Any) -> None:
        _check_address(self, address, "connect")
        return connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> int:
        _check_address(self, address, "connect_ex")
        return connect_ex(self, address)

    def guarded_sendto(self: socket.socket, *args: Any) -> int:
        _check_address(self, args[-1], "sendto")  # The address is always the last argument.
        return sendto(self, *args)

    setattr(guarded_connect, _MARK, True)
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.socket.sendto = guarded_sendto

    for name in _LOOKUPS:
        setattr(socket, name, _guard_lookup(name, getattr(socket, name)))
