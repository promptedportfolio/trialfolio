"""The network guard: tests may reach localhost and nothing else (P-12).

Its pytest plugin, ``trialfolio_network_guard_plugin``, installs it in the test process.
``sitecustomize.py``, beside this module, installs it in every Python subprocess the suite starts,
because the plugin puts this directory first on PYTHONPATH. Both import this module by the same
name, so a process has one guard and one ``NetworkAccessRefused``, even when the suite runs under
another copy of itself.

For any host but localhost, the guard refuses ``connect``, ``connect_ex``, ``sendto``, and
``sendmsg`` on a socket, and the ``socket`` module's name and address lookups, before anything
leaves the machine. A lookup of another name never reaches a resolver. ``socket.getfqdn`` gives
back a name the guard won't look up, as it does when a lookup fails.

A refusal raises ``NetworkAccessRefused``. It derives from ``BaseException``, so no
``except Exception`` or ``except OSError`` handler, in Trial Folio, ``requests``, or ``urllib3``,
can mistake it for a provider failure and carry on. The guard also records each refusal, so that
one that is caught, or left in a future nobody reads, still counts: the pytest plugin fails the
test it happened in, and a subprocess refused anything, in any thread, exits with status 70 when
it ends. A test that provokes a refusal on purpose takes it with ``take_refusals()``.

The guard also keeps itself in subprocesses that ``subprocess`` starts, including shell commands
and ``os.popen``. A child's environment, whether passed or inherited, gets this directory first on
PYTHONPATH. If it sets no proxy variable to a value, it also loses any empty one and gets
``NO_PROXY=*``, so a proxy on localhost, such as one from macOS's system settings, can't relay its
requests; an environment that sets one, as a test of proxy handling does, keeps exactly what it
says. A command that would start Python without the guard is refused: with ``-I``, ``-E``, or
``-S``, which skip ``sitecustomize``, even behind a wrapper such as ``env`` or ``uv run``; or after
changing PYTHONPATH, or clearing the environment with ``env -i``, before it. A test that needs
another PYTHONPATH passes ``env``. What the guard can't see, a child must keep itself: one started
another way, such as with ``os.system`` or ``os.execve``; a wrapper that clears the environment
on its own, such as ``sudo``; and a command inside another, such as a shell's ``-c`` string.

On Windows, asyncio's default event loop connects and sends through the system's overlapped
calls, not through ``socket``. So its connections to an address, rather than a name, aren't
refused there. Trial Folio and its dependencies don't use asyncio.

Only the live check lifts the guard, and only partly: it names Portfolio123's API host in
``TRIALFOLIO_TEST_NETWORK_ALLOW``, in the environment of its one ``trialfolio run`` subprocess.
That process may then look the host up, and reach the addresses the lookup returned. Its
``sitecustomize`` removes the variable from its environment, so nothing it starts inherits it.
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

# The characters that join, group, or redirect commands in a shell. A run of them is a word of its
# own, as in `true;python`. Those without a redirection end one command and start another.
_SHELL_PUNCTUATION = ";&|()`\n<>"
_SEPARATORS = frozenset(";&|()`\n")

# The status a subprocess exits with, when it ends, after any refusal.
REFUSED_EXIT_STATUS = 70

# What install() replaced, and whether the owner defined it itself, for uninstall().
_originals: dict[tuple[Any, str], tuple[Any, bool]] = {}

# What this process may reach besides localhost: the allowed names, and the addresses their
# lookups returned.
_allowed_names: set[str] = set()
_allowed_addresses: set[str] = set()

# Whether this process exits with REFUSED_EXIT_STATUS after a refusal, and the refusals that
# take_refusals() hasn't taken.
_exit_after_refusal = False
_refusals: list[str] = []


class NetworkAccessRefused(BaseException):
    """A test tried to reach a host other than localhost, or to start Python without the guard."""


def _refuse(what: str) -> NoReturn:
    message = f"network guard: refused {what}; tests may reach only localhost (P-12)"
    _refusals.append(message)
    raise NetworkAccessRefused(message)


def take_refusals() -> list[str]:
    """The refusals since the last call, which no longer count. A test that provokes one on
    purpose takes it, so that the pytest plugin doesn't fail the test for it."""
    taken = _refusals[:]
    del _refusals[: len(taken)]  # Without any a thread has just added.
    return taken


def exit_after_refusal(enabled: bool) -> bool:
    """Set whether this process exits with REFUSED_EXIT_STATUS when it ends, if any refusal is
    left that nothing took. Returns the previous setting. The pytest plugin turns it off, because
    it reports refusals itself, and back on after the run if the guard stays."""
    global _exit_after_refusal
    previous, _exit_after_refusal = _exit_after_refusal, enabled
    atexit.unregister(_exit_if_refused)
    if enabled:
        atexit.register(_exit_if_refused)
    return previous


def _exit_if_refused() -> None:
    if not (_exit_after_refusal and _refusals):
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


def _is_proxy_variable(key: object) -> bool:
    return _variable(key).lower().endswith("_proxy")


def without_proxies(env: Mapping[Any, Any]) -> dict[Any, Any]:
    """A copy of env in which no proxy applies: without its proxy variables, and with NO_PROXY=*,
    which also turns off the system's proxies.

    Where variable names are case-sensitive, it sets no_proxy=* too, which requests reads first.
    A test of proxy handling in the test process removes both.
    """
    copy = {key: value for key, value in env.items() if not _is_proxy_variable(key)}
    for name in ("NO_PROXY",) if os.name == "nt" else ("NO_PROXY", "no_proxy"):
        _set(copy, name, "*")
    return copy


def child_environment(env: Mapping[Any, Any]) -> dict[Any, Any]:
    """The environment a child gets: env with the guard first on PYTHONPATH, and without_proxies()
    unless env sets a proxy variable to a value. urllib ignores empty ones, and with none left,
    falls back to the system's proxies."""
    copy = with_guard_path(env)
    if not any(value for key, value in copy.items() if _is_proxy_variable(key)):
        copy = without_proxies(copy)
    return copy


def _python_kind(program: str) -> str | None:
    """'python' for a Python interpreter, such as python3.13t or pypy3, 'py' for the Windows
    launcher, otherwise None."""
    import re

    name = os.path.basename(program).lower().removesuffix(".exe")
    if name in ("py", "pyw"):
        return "py"
    return "python" if re.fullmatch(r"(python|pypy)[\d.]*[a-z]?(-\w+)?", name) else None


def _shell_words(command: str) -> list[str]:
    """A shell command's words, and its punctuation, such as `;` or `&&`, as words of its own."""
    import shlex

    posix = os.name != "nt"
    lexer = shlex.shlex(command, posix=posix, punctuation_chars=_SHELL_PUNCTUATION)
    lexer.whitespace = " \t\r"  # A newline ends a command.
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        words = list(lexer)
    except ValueError:
        return []  # The shell rejects unbalanced quotes itself.
    # On Windows the words keep their quotes.
    return words if posix else [word.strip("\"'") for word in words]


def _check_command(words: list[str]) -> None:
    """Refuse a command that would start Python without the guard.

    A shell command's words may hold several commands, split by its separators. The words after
    one naming Python are its own arguments, such as a -c program, so only its options are
    checked there. Any program may be Python, such as an installed command, so a command that
    changes PYTHONPATH or clears the environment is refused whatever it runs.
    """
    import re

    pythonpath = re.compile(r"(?<![$%{])PYTHONPATH\b", re.IGNORECASE if os.name == "nt" else 0)
    in_python = False
    for index, word in enumerate(words):
        if word and set(word) <= _SEPARATORS:
            in_python = False
        elif in_python:
            continue
        elif pythonpath.search(word):  # $PYTHONPATH only reads it.
            _refuse(
                "a command that changes PYTHONPATH, which would run any Python in it without the"
                " guard; pass env instead"
            )
        elif kind := _python_kind(word):
            _check_python_options(kind, words[index + 1 :])
            in_python = True
        elif os.path.basename(word) == "env" and _clears_environment(words[index + 1 :]):
            _refuse("env -i, which would run any Python in it without the guard")


def _clears_environment(args: list[str]) -> bool:
    """Whether env's options, which start args, clear the environment."""
    rest = iter(args)
    for arg in rest:
        if arg in ("-", "-i", "--ignore-environment"):
            return True
        if arg == "--" or not arg.startswith("-"):
            return False  # A variable or the program follows.
        if arg.startswith("--"):
            continue
        for position, flag in enumerate(arg[1:]):
            if flag == "i":
                return True
            if flag in "uCS":
                if position == len(arg) - 2:
                    next(rest, None)  # Its value is the next argument.
                break  # Its value is the rest of this one.
    return False


def _check_python_options(kind: str, args: list[str]) -> None:
    """Refuse to start Python with an option that skips sitecustomize. args follow the program."""
    rest = iter(args)
    for arg in rest:
        if kind == "py" and arg.startswith("-") and (arg[1:2].isdigit() or arg.startswith("-V:")):
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

        command, executable, shell = get("args"), get("executable"), get("shell")
        if isinstance(command, (str, bytes, os.PathLike)):
            if shell or os.name == "nt":  # On Windows, a string is a whole command line.
                _check_command(_shell_words(os.fsdecode(command)))
        elif isinstance(command, Iterable):
            if not isinstance(command, (list, tuple)):
                command = list(command)  # A generator can be read only once.
                put("args", command)
            argv = [os.fsdecode(arg) for arg in command]
            if not shell:
                # Given an executable, argv[0] is only the name the program sees.
                program = [] if executable is None else [os.fsdecode(executable)]
                _check_command([*program, *argv[len(program) :]])
            elif os.name == "nt":
                _check_command(_shell_words(subprocess.list2cmdline(argv)))
            elif argv:
                # The shell runs the first; the rest are its $0, $1, ...
                _check_command(_shell_words(argv[0]))
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
    _refusals.clear()
    exit_after_refusal(False)


def allowed_hosts() -> frozenset[str]:
    """The host names this process may reach besides localhost."""
    return frozenset(_allowed_names)
