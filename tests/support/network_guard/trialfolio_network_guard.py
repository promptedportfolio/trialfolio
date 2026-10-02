"""The network guard: tests may reach localhost and nothing else (P-12).

The root conftest installs it in the test process. ``sitecustomize.py``, beside this module,
installs it in every Python subprocess the suite starts, because the conftest puts this directory
first on PYTHONPATH. Both import this module by the same name, so a process has one guard and
one ``NetworkAccessRefused``, even when the suite runs under another copy of itself.

For any host but localhost, the guard refuses ``connect``, ``connect_ex``, ``sendto``, and
``sendmsg`` on a socket, and the ``socket`` module's name and address lookups, before anything
leaves the machine. A lookup of another name never reaches a resolver. ``socket.getfqdn`` gives
back a name the guard won't look up, as it does when a lookup fails.

A refusal raises ``NetworkAccessRefused``. It derives from ``BaseException``, so no
``except Exception`` or ``except OSError`` handler, in Trial Folio, ``requests``, or ``urllib3``,
can mistake it for a provider failure and carry on. A test that reaches another host fails.

The guard also keeps itself in subprocesses. ``subprocess.Popen`` puts this directory first on
the PYTHONPATH of any environment its caller passes, and refuses to start Python with ``-I``,
``-E``, or ``-S``, which skip ``sitecustomize``. A child started some other way, such as with
``os.execve`` and its own environment, must keep PYTHONPATH itself.
"""

from __future__ import annotations

import inspect
import ipaddress
import os
import re
import socket
import subprocess
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NoReturn

GUARD_DIR = os.path.dirname(os.path.realpath(__file__))

_LOOKUPS = ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")

# Where each guarded socket method takes its address, as an index into its arguments.
_ADDRESS_ARGUMENT = {"connect": 0, "connect_ex": 0, "sendto": -1, "sendmsg": 3}

_PYTHON = re.compile(r"python[0-9.]*w?(\.exe)?", re.IGNORECASE)

# What install() replaced, and whether the owner defined it itself, for uninstall().
_originals: dict[tuple[Any, str], tuple[Any, bool]] = {}


class NetworkAccessRefused(BaseException):
    """A test tried to reach a host other than localhost, or to start Python without the guard."""


def _refuse(what: str) -> NoReturn:
    raise NetworkAccessRefused(
        f"network guard: refused {what}; tests may reach only localhost (P-12)"
    )


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


def _guard_socket_method(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    index = _ADDRESS_ARGUMENT[name]

    def guarded(self: socket.socket, *args: Any) -> Any:
        # Unix and other local families have no host to check. sendmsg takes no address on a
        # connected socket, which connect already checked.
        if self.family in (socket.AF_INET, socket.AF_INET6) and -len(args) <= index < len(args):
            address = args[index]
            if isinstance(address, tuple) and address and not _is_local(address[0]):
                _refuse(f"{name} to {address[0]!r}")
        return original(self, *args)

    return guarded


def _guard_lookup(name: str, original: Callable[..., Any]) -> Callable[..., Any]:
    def guarded(host: object, *args: Any, **kwargs: Any) -> Any:
        # getnameinfo takes a socket address; the others take a host.
        target: object = host[0] if isinstance(host, tuple) and host else host
        if not _is_local(target):
            _refuse(f"{name} for {target!r}")
        return original(host, *args, **kwargs)

    return guarded


def _guard_getfqdn(name: str, original: Callable[[str], str]) -> Callable[..., str]:
    def getfqdn(host: str = "") -> str:
        host = host.strip()
        if not host or host in ("0.0.0.0", "::"):
            host = socket.gethostname()
        return original(host) if _is_local(host) else host

    return getfqdn


def with_guard_path(env: Mapping[str, str]) -> dict[str, str]:
    """A copy of env whose PYTHONPATH starts with the guard's directory, once."""
    entries = env.get("PYTHONPATH", "").split(os.pathsep)
    rest = [entry for entry in entries if entry and os.path.realpath(entry) != GUARD_DIR]
    return {**env, "PYTHONPATH": os.pathsep.join([GUARD_DIR, *rest])}


def _check_python_options(args: Any, executable: Any) -> None:
    """Refuse to start Python with an option that skips sitecustomize."""
    if isinstance(args, (str, bytes, os.PathLike)) or not isinstance(args, Iterable):
        return  # A shell command or a bare program: no options to read.
    argv: list[str] = [os.fsdecode(arg) for arg in args]
    program = os.fsdecode(executable) if executable is not None else argv[0] if argv else ""
    if not _PYTHON.fullmatch(os.path.basename(program)):
        return
    rest = iter(argv[1:])
    for arg in rest:
        if arg in ("-", "--") or not arg.startswith("-"):
            return  # The script, or standard input, and its own arguments follow.
        if arg.startswith("--"):
            if arg == "--check-hash-based-pycs":
                next(rest, None)
            continue
        flags = arg[1:]
        for position, flag in enumerate(flags):
            if flag in "IES":
                _refuse(f"starting Python with -{flag}, which would run it without the guard")
            if flag in "cm":
                return  # The program follows.
            if flag in "WX":
                if position == len(flags) - 1:
                    next(rest, None)  # Its value is the next argument.
                break  # Its value is the rest of this one.


def _guard_popen(name: str, original: Callable[..., None]) -> Callable[..., None]:
    signature = inspect.signature(original)

    def __init__(self: subprocess.Popen[Any], *args: Any, **kwargs: Any) -> None:
        bound = signature.bind(self, *args, **kwargs)
        env = bound.arguments.get("env")
        if env is not None:
            bound.arguments["env"] = with_guard_path(env)
        _check_python_options(bound.arguments["args"], bound.arguments.get("executable"))
        original(*bound.args, **bound.kwargs)

    return __init__


def install() -> bool:
    """Install the guard in this process. Returns False, and changes nothing, if it's on."""
    if _originals:
        return False
    replacements: list[tuple[Any, str, Callable[[str, Any], Any]]] = [
        *((socket.socket, name, _guard_socket_method) for name in _ADDRESS_ARGUMENT),
        *((socket, name, _guard_lookup) for name in _LOOKUPS),
        (socket, "getfqdn", _guard_getfqdn),
        (subprocess.Popen, "__init__", _guard_popen),
    ]
    for owner, name, guard in replacements:
        if not hasattr(owner, name):  # Windows sockets have no sendmsg.
            continue
        original = getattr(owner, name)
        _originals[owner, name] = (original, name in vars(owner))
        setattr(owner, name, guard(name, original))
    return True


def uninstall() -> None:
    """Undo install()."""
    for (owner, name), (original, owned) in _originals.items():
        if owned:
            setattr(owner, name, original)
        else:
            delattr(owner, name)
    _originals.clear()
