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
can mistake it for a provider failure and carry on. A test that reaches another host fails. In
the test process, pytest's warning about an exception in a background thread is an error. A
subprocess refused anything, in any thread, exits with status 70 when it ends, even if the
refusal was caught.

The guard also keeps itself in subprocesses that ``subprocess`` starts, including shell commands
and ``os.popen``. A child's environment, whether passed or inherited, gets this directory first on
PYTHONPATH. If it names no proxy variable at all, it also gets ``NO_PROXY=*``, so a proxy on
localhost, such as one from macOS's system settings, can't relay its requests; an environment
that names one, as a test of proxy handling does, keeps exactly what it says. Python started with
``-I``, ``-E``, or ``-S``, which skip ``sitecustomize``, is refused. A child started another way,
such as with ``os.system`` or ``os.execve``, must keep PYTHONPATH and its proxy settings itself.

Only the live check lifts the guard, and only partly: it names Portfolio123's API host in
``TRIALFOLIO_TEST_NETWORK_ALLOW``, in the environment of its one ``trialfolio run`` subprocess.
That process may then look the host up, and reach the addresses the lookup returned.
"""

from __future__ import annotations

import atexit
import functools
import os
import socket
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping

# typing is only for the type checker: importing it would slow each subprocess's startup.
TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, NoReturn

GUARD_DIR = os.path.dirname(os.path.realpath(__file__))

# Host names, separated by commas, that sitecustomize lets its process reach (release 0.1.0's
# live check). The suite itself refuses to run with it.
ALLOW_ENV = "TRIALFOLIO_TEST_NETWORK_ALLOW"

_LOOKUPS = ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo")

# Where each guarded socket method takes its address, as an index into its arguments.
_ADDRESS_ARGUMENT = {"connect": 0, "connect_ex": 0, "sendto": -1, "sendmsg": 3}

# Popen's documented positional parameters: Popen(args, bufsize, executable, ..., shell, cwd, env,
# ...).
_POPEN_POSITION = {"args": 0, "executable": 2, "shell": 8, "env": 10}

# The status a subprocess exits with, when it ends, after any refusal.
REFUSED_EXIT_STATUS = 70

# What install() replaced, and whether the owner defined it itself, for uninstall().
_originals: dict[tuple[Any, str], tuple[Any, bool]] = {}

# What this process may reach besides localhost: the allowed names, and the addresses their
# lookups returned.
_allowed_names: set[str] = set()
_allowed_addresses: set[str] = set()

# Whether this process exits with REFUSED_EXIT_STATUS after a refusal, and whether one happened.
_exit_after_refusal = False
_refused = False


class NetworkAccessRefused(BaseException):
    """A test tried to reach a host other than localhost, or to start Python without the guard."""


def _refuse(what: str) -> NoReturn:
    global _refused
    _refused = True
    raise NetworkAccessRefused(
        f"network guard: refused {what}; tests may reach only localhost (P-12)"
    )


def exit_after_refusal(enabled: bool) -> bool:
    """Set whether this process, once refused anything, exits with REFUSED_EXIT_STATUS when it
    ends, counting refusals from now on. Returns the previous setting. A pytest process turns it
    off, because pytest reports refusals, and turns it back on after its run."""
    global _exit_after_refusal, _refused
    previous, _exit_after_refusal, _refused = _exit_after_refusal, enabled, False
    atexit.unregister(_exit_if_refused)
    if enabled:
        atexit.register(_exit_if_refused)
    return previous


def _exit_if_refused() -> None:
    if not (_exit_after_refusal and _refused):
        return
    for stream in (sys.stdout, sys.stderr):
        stream.flush()
    sys.stderr.write(
        f"network guard: this process was refused network access, so it exits "
        f"{REFUSED_EXIT_STATUS}\n"
    )
    sys.stderr.flush()
    os._exit(REFUSED_EXIT_STATUS)


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


def _variable(key: object) -> str:
    """An environment key's variable name, compared as the platform compares it."""
    name = os.fsdecode(key) if isinstance(key, (str, bytes)) else ""
    return name.upper() if os.name == "nt" else name


def with_guard_path(env: Mapping[Any, Any]) -> dict[Any, Any]:
    """A copy of env whose PYTHONPATH starts with the guard's directory, once.

    Keys may be bytes, as POSIX allows, and on Windows in any case. The other entries stay as
    they are, empty ones included: Python reads an empty entry as the current directory.
    """
    keys = [key for key in env if _variable(key) == "PYTHONPATH"]
    value = os.fsdecode(env[keys[0]]) if keys else ""
    entries = value.split(os.pathsep) if value else []
    rest = [entry for entry in entries if not entry or os.path.realpath(entry) != GUARD_DIR]
    copy = {key: item for key, item in env.items() if key not in keys}
    _set(copy, "PYTHONPATH", os.pathsep.join([GUARD_DIR, *rest]))
    return copy


def _set(env: dict[Any, Any], name: str, value: str) -> None:
    """Set a variable in env, as bytes if env's keys are bytes."""
    if any(isinstance(key, bytes) for key in env):
        env[os.fsencode(name)] = os.fsencode(value)
    else:
        env[name] = value


def child_environment(env: Mapping[Any, Any]) -> dict[Any, Any]:
    """The environment a child gets: env with the guard first on PYTHONPATH and, if env names
    no proxy variable at all, NO_PROXY=* so that no system proxy applies."""
    copy = with_guard_path(env)
    if not any(_variable(key).lower().endswith("_proxy") for key in copy):
        for name in ("NO_PROXY",) if os.name == "nt" else ("NO_PROXY", "no_proxy"):
            _set(copy, name, "*")
    return copy


def _python_kind(program: str) -> str | None:
    """'python' for a Python interpreter, 'py' for the Windows launcher, otherwise None."""
    name = os.path.basename(program).lower().removesuffix(".exe")
    if name in ("py", "pyw"):
        return "py"
    return "python" if name.startswith(("python", "pypy")) else None


def _check_shell_command(command: str) -> None:
    """Refuse a shell command that starts Python with an option that skips sitecustomize."""
    import shlex

    try:
        words = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return  # The shell rejects unbalanced quotes itself.
    for index, word in enumerate(words):
        if _python_kind(word.strip("\"'")):
            _check_python_options(words[index:], None)


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
        if isinstance(command, (str, bytes, os.PathLike)):
            if get("shell"):
                _check_shell_command(os.fsdecode(command))
        elif isinstance(command, Iterable):
            command = list(command)  # A generator can be read only once.
            put("args", command)
            argv = [os.fsdecode(arg) for arg in command]
            if not get("shell"):
                _check_python_options(argv, get("executable"))
            elif os.name == "nt":
                _check_shell_command(subprocess.list2cmdline(argv))
            elif argv:
                _check_shell_command(argv[0])  # The shell runs the first; the rest are its $0...
        env = get("env")
        if env is not None:
            put("env", child_environment(env))
        else:
            inherited = child_environment(os.environ)
            if inherited != os.environ:
                put("env", inherited)
        original(self, *positional, **kwargs)

    return __init__


def install(allowed_hosts: Iterable[str] = (), *, exit_on_refusal: bool = False) -> bool:
    """Install the guard in this process, letting it reach localhost and allowed_hosts.

    With exit_on_refusal, as in a subprocess, see exit_after_refusal(). Returns False, and
    changes nothing, if the guard is already on.
    """
    if _originals:
        return False
    exit_after_refusal(exit_on_refusal)
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
    exit_after_refusal(False)


def allowed_hosts() -> frozenset[str]:
    """The host names this process may reach besides localhost."""
    return frozenset(_allowed_names)
