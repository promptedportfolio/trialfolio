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
can mistake it for a provider failure and carry on. A test that reaches another host fails; in a
background thread, pytest's warning about the unhandled exception is an error.

The guard also keeps itself in subprocesses. ``subprocess.Popen`` puts this directory first on
the child's PYTHONPATH, whether the caller passes an environment or the child inherits one, and
refuses to start Python with ``-I``, ``-E``, or ``-S``, which skip ``sitecustomize``. A child
started some other way, such as with ``os.execve`` and its own environment, must keep PYTHONPATH
itself.

Only the live check lifts the guard, and only partly: it names Portfolio123's API host in
``TRIALFOLIO_TEST_NETWORK_ALLOW``, in the environment of its one ``trialfolio run`` subprocess.
That process may then look the host up, and reach the addresses the lookup returned.
"""

from __future__ import annotations

import functools
import os
import socket
import subprocess
from collections.abc import Callable, Iterable, Mapping
from typing import Any, NoReturn

GUARD_DIR = os.path.dirname(os.path.realpath(__file__))

# Host names, separated by commas, that sitecustomize lets its process reach (release 0.1.0's
# live check). The suite itself refuses to run with it.
ALLOW_ENV = "TRIALFOLIO_TEST_NETWORK_ALLOW"

_LOOKUPS = ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")

# Where each guarded socket method takes its address, as an index into its arguments.
_ADDRESS_ARGUMENT = {"connect": 0, "connect_ex": 0, "sendto": -1, "sendmsg": 3}

# Popen's documented positional parameters: Popen(args, bufsize, executable, ..., cwd, env, ...).
_POPEN_POSITION = {"args": 0, "executable": 2, "env": 10}

# What install() replaced, and whether the owner defined it itself, for uninstall().
_originals: dict[tuple[Any, str], tuple[Any, bool]] = {}

# What this process may reach besides localhost: the allowed names, and the addresses their
# lookups returned.
_allowed_names: set[str] = set()
_allowed_addresses: set[str] = set()


class NetworkAccessRefused(BaseException):
    """A test tried to reach a host other than localhost, or to start Python without the guard."""


def _refuse(what: str) -> NoReturn:
    raise NetworkAccessRefused(
        f"network guard: refused {what}; tests may reach only localhost (P-12)"
    )


def _host_name(host: object) -> str | None:
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    return host.rstrip(".").lower() if isinstance(host, str) else None


def _is_local(host: object) -> bool:
    """Whether a host, as a socket call receives it, never leaves this machine."""
    if host is None:  # getaddrinfo(None, port) resolves to loopback.
        return True
    name = _host_name(host)
    if name is None:
        return False
    if name in ("", "localhost"):  # "" is the wildcard address.
        return True
    import ipaddress  # Here, not at the top, to keep each subprocess's startup fast.

    try:
        address = ipaddress.ip_address(name.split("%", 1)[0])  # Drop an IPv6 zone.
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_loopback or address.is_unspecified


def _is_allowed(host: object) -> bool:
    name = _host_name(host)
    return _is_local(host) or name in _allowed_names or name in _allowed_addresses


def _guard_socket_method(attribute: str, original: Callable[..., Any]) -> Callable[..., Any]:
    index = _ADDRESS_ARGUMENT[attribute]

    @functools.wraps(original)
    def guarded(self: socket.socket, *args: Any) -> Any:
        # Unix and other local families have no host to check. sendmsg takes no address on a
        # connected socket, which connect already checked.
        if self.family in (socket.AF_INET, socket.AF_INET6) and -len(args) <= index < len(args):
            address = args[index]
            if isinstance(address, tuple) and address and not _is_allowed(address[0]):
                _refuse(f"{attribute} to {address[0]!r}")
        return original(self, *args)

    return guarded


def _addresses(lookup: str, result: Any) -> list[str]:
    """The addresses a lookup of an allowed host returned."""
    if lookup == "getaddrinfo":
        return [str(info[4][0]).lower() for info in result]
    if lookup == "gethostbyname":
        return [result]
    if lookup in ("gethostbyname_ex", "gethostbyaddr"):
        return [address.lower() for address in result[2]]
    return []  # getnameinfo returns a name.


def _guard_lookup(attribute: str, original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def guarded(host: object, *args: Any, **kwargs: Any) -> Any:
        # getnameinfo takes a socket address; the others take a host.
        target: object = host[0] if isinstance(host, tuple) and host else host
        if not _is_allowed(target):
            _refuse(f"{attribute} for {target!r}")
        result = original(host, *args, **kwargs)
        if not _is_local(target):
            _allowed_addresses.update(_addresses(attribute, result))
        return result

    return guarded


def _guard_getfqdn(attribute: str, original: Callable[[str], str]) -> Callable[..., str]:
    @functools.wraps(original)
    def getfqdn(name: str = "") -> str:
        name = name.strip()
        if not name or name in ("0.0.0.0", "::"):
            name = socket.gethostname()
        return original(name) if _is_allowed(name) else name

    return getfqdn


def _is_pythonpath(key: str | bytes) -> bool:
    name = os.fsdecode(key)
    return (name.upper() if os.name == "nt" else name) == "PYTHONPATH"


def with_guard_path(env: Mapping[Any, Any]) -> dict[Any, Any]:
    """A copy of env whose PYTHONPATH starts with the guard's directory, once.

    Keys may be bytes, as POSIX allows, and on Windows in any case. The other entries stay as
    they are, empty ones included: Python reads an empty entry as the current directory.
    """
    keys = [key for key in env if isinstance(key, (str, bytes)) and _is_pythonpath(key)]
    value = os.fsdecode(env[keys[0]]) if keys else ""
    entries = value.split(os.pathsep) if value else []
    rest = [entry for entry in entries if not entry or os.path.realpath(entry) != GUARD_DIR]
    path = os.pathsep.join([GUARD_DIR, *rest])
    copy = {key: item for key, item in env.items() if key not in keys}
    if isinstance(keys[0] if keys else next(iter(env), ""), bytes):
        copy[b"PYTHONPATH"] = os.fsencode(path)
    else:
        copy["PYTHONPATH"] = path
    return copy


def _python_kind(program: str) -> str | None:
    """'python' for a Python interpreter, 'py' for the Windows launcher, otherwise None."""
    name = os.path.basename(program).lower().removesuffix(".exe")
    if name in ("py", "pyw"):
        return "py"
    return "python" if name.startswith(("python", "pypy")) else None


def _check_python_options(argv: list[str], executable: Any) -> None:
    """Refuse to start Python with an option that skips sitecustomize."""
    program = os.fsdecode(executable) if executable is not None else argv[0] if argv else ""
    kind = _python_kind(program)
    if kind is None:
        return
    rest = iter(argv[1:])
    for arg in rest:
        if kind == "py" and (arg[1:2].isdigit() or arg.startswith("-V:")):
            continue  # The launcher's choice of Python, such as -3.12.
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


def _guard_popen(attribute: str, original: Callable[..., None]) -> Callable[..., None]:
    @functools.wraps(original)
    def __init__(self: subprocess.Popen[Any], *args: Any, **kwargs: Any) -> None:
        positional = list(args)

        def get(parameter: str) -> Any:
            index = _POPEN_POSITION[parameter]
            return positional[index] if index < len(positional) else kwargs.get(parameter)

        def put(parameter: str, value: Any) -> None:
            index = _POPEN_POSITION[parameter]
            if index < len(positional):
                positional[index] = value
            else:
                kwargs[parameter] = value

        command = get("args")
        if isinstance(command, Iterable) and not isinstance(command, (str, bytes, os.PathLike)):
            command = list(command)  # A generator can be read only once.
            put("args", command)
            _check_python_options([os.fsdecode(arg) for arg in command], get("executable"))
        env = get("env")
        if env is not None:
            put("env", with_guard_path(env))
        else:
            inherited = with_guard_path(os.environ)
            if inherited["PYTHONPATH"] != os.environ.get("PYTHONPATH"):
                put("env", inherited)
        original(self, *positional, **kwargs)

    return __init__


def install(allowed_hosts: Iterable[str] = ()) -> bool:
    """Install the guard in this process, letting it reach localhost and allowed_hosts.

    Returns False, and changes nothing, if the guard is already on.
    """
    if _originals:
        return False
    _allowed_names.update(name for host in allowed_hosts if (name := _host_name(host.strip())))
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
    _allowed_names.clear()
    _allowed_addresses.clear()


def allowed_hosts() -> frozenset[str]:
    """The host names this process may reach besides localhost."""
    return frozenset(_allowed_names)
