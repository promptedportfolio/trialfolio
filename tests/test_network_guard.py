"""The network guard refuses every host but localhost, in the test process and in subprocesses.

Traces to P-12 (docs/spec.md) and to the network guard in release 0.1.0's test pairing. The
other host is a reserved name and a documentation address (RFC 6761, RFC 5737), so even a
broken guard would reach no real service.
"""

import contextlib
import email.utils
import inspect
import os
import shlex
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import requests
from trialfolio_network_guard import (
    ALLOW_ENV,
    GUARD_DIR,
    REFUSED_EXIT_STATUS,
    NetworkAccessRefused,
    take_refusals,
)

OTHER_NAME = "example.invalid"
OTHER_ADDRESS = "192.0.2.1"
REPO_ROOT = Path(__file__).resolve().parent.parent

REACH_OTHER_HOST = (
    "import socket, sys\n"
    "try:\n"
    "    socket.getaddrinfo('example.invalid', 443)\n"
    "except BaseException as error:\n"
    "    print(type(error).__name__)\n"
)


@contextlib.contextmanager
def refused() -> Iterator[None]:
    """Expects the guard to refuse the block, and takes the refusal, which would otherwise fail
    the test though the block caught it."""
    with pytest.raises(NetworkAccessRefused):
        yield
    take_refusals()


def run_python(
    code: str, *args: str, options: list[str] | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *(options or []), "-c", code, *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )


def probe(tmp_path: Path, test_body: str) -> list[str]:
    """pytest arguments that run one test, written outside the repository, with its settings.

    Collecting src/ too makes pytest load the repository's root conftest, as it does for any
    path in the repository.
    """
    path = tmp_path / "test_probe.py"
    path.write_text(f"def test_probe():\n{test_body}", encoding="utf-8")
    pyproject = str(REPO_ROOT / "pyproject.toml")
    return ["-c", pyproject, "--rootdir", str(REPO_ROOT), str(REPO_ROOT / "src"), str(path)]


def run_pytest(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Runs pytest in a subprocess, as a nested run inherits the guard."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )


@pytest.fixture
def listener() -> Iterator[socket.socket]:
    """A listening TCP socket on 127.0.0.1. A connection completes without accept()."""
    with socket.create_server(("127.0.0.1", 0)) as server:
        server.setblocking(False)
        yield server


def connect_by_name() -> None:
    socket.create_connection((OTHER_NAME, 443), timeout=1).close()


def look_up_name() -> None:
    socket.getaddrinfo(OTHER_NAME, 443)


def connect_by_address() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((OTHER_ADDRESS, 443))


def send_datagram() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(b"x", (OTHER_ADDRESS, 53))


def send_datagram_message() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendmsg([b"x"], [], 0, (OTHER_ADDRESS, 53))


def get_with_requests() -> None:
    # Trial Folio's provider calls go through requests and urllib3. The refusal isn't an OSError,
    # so neither can turn it into a connection error.
    requests.get(f"https://{OTHER_NAME}/", timeout=1)


@pytest.mark.parametrize(
    "reach",
    [
        connect_by_name,
        look_up_name,
        connect_by_address,
        send_datagram,
        pytest.param(
            send_datagram_message,
            marks=pytest.mark.skipif(not hasattr(socket.socket, "sendmsg"), reason="no sendmsg"),
        ),
        get_with_requests,
    ],
)
def test_test_process_refuses_another_host(reach: Callable[[], None]) -> None:
    with refused():
        reach()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_test_process_reaches_localhost(listener: socket.socket, host: str) -> None:
    socket.create_connection((host, listener.getsockname()[1]), timeout=5).close()


def test_a_proxy_on_localhost_cannot_relay_a_request(
    listener: socket.socket, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = f"http://127.0.0.1:{listener.getsockname()[1]}"
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(name, proxy)
    with refused():
        requests.get(f"https://{OTHER_NAME}/", timeout=1)
    with pytest.raises(BlockingIOError):  # The proxy received no connection.
        listener.accept()


def test_a_refusal_in_a_background_thread_fails_the_test(tmp_path: Path) -> None:
    result = run_pytest(
        *probe(
            tmp_path,
            "    import socket, threading\n"
            "    thread = threading.Thread(target=socket.getaddrinfo, args=('example.invalid', 1))\n"
            "    thread.start()\n"
            "    thread.join()\n",
        )
    )
    assert result.returncode == pytest.ExitCode.TESTS_FAILED, result.stdout + result.stderr
    assert "NetworkAccessRefused" in result.stdout


@pytest.mark.parametrize(
    "test_body",
    [
        (
            "    import socket\n"
            "    try:\n"
            "        socket.getaddrinfo('example.invalid', 1)\n"
            "    except BaseException:\n"
            "        pass\n"
        ),
        (
            "    import socket\n"
            "    from concurrent.futures import ThreadPoolExecutor\n"
            "    with ThreadPoolExecutor() as pool:\n"
            "        pool.submit(socket.getaddrinfo, 'example.invalid', 1)\n"
        ),
    ],
    ids=["caught", "in a future nobody read"],
)
def test_a_refusal_the_test_never_sees_still_fails_it(tmp_path: Path, test_body: str) -> None:
    result = run_pytest(*probe(tmp_path, test_body))
    assert result.returncode == pytest.ExitCode.TESTS_FAILED, result.stdout + result.stderr
    assert "refused getaddrinfo for 'example.invalid'" in result.stdout


def spawn_pytest(*args: str) -> int:
    """Runs pytest as a top-level run, which installs the guard itself. os.spawnve starts it
    without subprocess.Popen, which would put the guard first on its PYTHONPATH."""
    env = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"}
    argv = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]
    return os.spawnve(os.P_WAIT, sys.executable, argv, env)


@pytest.mark.parametrize(
    "options",
    [[], ["--noconftest"], ["-o", "addopts="]],
    ids=["default", "no conftest", "no addopts"],
)
def test_any_pytest_run_in_the_repository_is_guarded(
    tmp_path: Path, capfd: pytest.CaptureFixture[str], options: list[str]
) -> None:
    # A run that collects nothing under tests/, such as one over src/, still loads the guard:
    # through addopts, or else through the root conftest.
    status = spawn_pytest(
        *options,
        *probe(
            tmp_path, "    import socket\n    assert hasattr(socket.getaddrinfo, '__wrapped__')\n"
        ),
    )
    out, err = capfd.readouterr()
    assert status == 0, out + err


def test_a_conftest_is_guarded_from_its_import(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    # pytest imports the guard's plugin before any conftest.
    (tmp_path / "conftest.py").write_text(
        "import socket\nassert hasattr(socket.getaddrinfo, '__wrapped__')\n", encoding="utf-8"
    )
    status = spawn_pytest(*probe(tmp_path, "    pass\n"))
    out, err = capfd.readouterr()
    assert status == 0, out + err


def test_a_refusal_after_the_run_ends_the_process(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    # A thread the test leaves running still runs under the guard once pytest has finished, and
    # a refusal then, even a caught one, ends the process.
    status = spawn_pytest(
        *probe(
            tmp_path,
            "    import socket, threading, time\n"
            "    def after_the_run():\n"
            "        while threading.main_thread().is_alive():\n"
            "            time.sleep(0.01)\n"
            "        try:\n"
            "            socket.getaddrinfo('example.invalid', 1)\n"
            "        except BaseException:\n"
            "            pass\n"
            "    threading.Thread(target=after_the_run).start()\n",
        )
    )
    out, err = capfd.readouterr()
    assert status == REFUSED_EXIT_STATUS, out + err


def test_local_name_lookups_degrade_instead_of_failing() -> None:
    # As after a failed lookup, getfqdn gives back the name, which local servers and email
    # message IDs rely on.
    assert socket.getfqdn(OTHER_NAME) == OTHER_NAME
    assert socket.getfqdn("") and socket.getfqdn("0.0.0.0")
    assert socket.getfqdn(name="localhost")
    assert email.utils.make_msgid()


@pytest.mark.parametrize("host", ["", "0.0.0.0", "::"])
def test_wildcard_addresses_resolve(host: str) -> None:
    # A local server may resolve the address it binds to; these never leave the machine.
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    assert socket.getaddrinfo(host, 0, family, socket.SOCK_STREAM, 0, socket.AI_PASSIVE)


def test_the_guard_wraps_each_call_once() -> None:
    for wrapped in (socket.getaddrinfo, socket.socket.connect, subprocess.Popen.__init__):
        inner = getattr(wrapped, "__wrapped__", None)
        assert inner is not None
        assert not hasattr(inner, "__wrapped__")
    # Popen's signature still reads as the standard library's.
    assert {"args", "env", "executable"} <= set(inspect.signature(subprocess.Popen).parameters)


def test_subprocess_refuses_another_host() -> None:
    result = run_python(
        "import socket, sys; socket.create_connection((sys.argv[1], 443), timeout=1)", OTHER_NAME
    )
    assert result.returncode == REFUSED_EXIT_STATUS
    assert "NetworkAccessRefused" in result.stderr


@pytest.mark.parametrize(
    "code",
    [
        (
            "import threading\n"
            "thread = threading.Thread(target=socket.getaddrinfo, args=('example.invalid', 1))\n"
            "thread.start()\n"
            "thread.join()\n"
        ),
        "try:\n    socket.getaddrinfo('example.invalid', 1)\nexcept BaseException:\n    pass\n",
    ],
    ids=["in a thread", "caught"],
)
def test_subprocess_refused_anything_exits_with_the_refusal_status(code: str) -> None:
    result = run_python("import socket\n" + code + "print('carried on')\n")
    assert result.stdout.split() == ["carried", "on"], result.stderr
    assert result.returncode == REFUSED_EXIT_STATUS, result.stderr


def test_subprocess_reaches_localhost(listener: socket.socket) -> None:
    result = run_python(
        "import socket, sys\n"
        "for host in ('127.0.0.1', 'localhost'):\n"
        "    socket.create_connection((host, int(sys.argv[1])), timeout=5).close()\n",
        str(listener.getsockname()[1]),
    )
    assert result.returncode == 0, result.stderr


def test_subprocess_with_its_own_environment_is_still_guarded() -> None:
    result = run_python(REACH_OTHER_HOST, env={"PATH": os.environ.get("PATH", "")})
    assert result.stdout.split() == ["NetworkAccessRefused"], result.stderr


PRINT_PROXY_SETTINGS = (
    "import os\nprint([os.environ.get(name) for name in ('NO_PROXY', 'no_proxy', 'HTTPS_PROXY')])"
)


@pytest.mark.parametrize("settings", [{}, {"HTTPS_PROXY": ""}], ids=["none", "empty"])
def test_a_child_environment_without_proxy_settings_turns_proxies_off(
    settings: dict[str, str],
) -> None:
    # Otherwise requests would read macOS's system proxies, which may be on localhost. It reads
    # them when every proxy variable is empty, too. On Windows, no_proxy is NO_PROXY.
    result = run_python(PRINT_PROXY_SETTINGS, env={"PATH": os.environ.get("PATH", ""), **settings})
    assert result.stdout.strip() == repr(["*", "*", None]), result.stderr


def test_a_child_environment_with_proxy_settings_keeps_them() -> None:
    # A test of proxy handling, such as R01-AC32's, sets what it means to test.
    proxy = "http://127.0.0.1:9"
    env = {"PATH": os.environ.get("PATH", ""), "HTTPS_PROXY": proxy}
    result = run_python(PRINT_PROXY_SETTINGS, env=env)
    assert result.stdout.strip() == repr([None, None, proxy]), result.stderr


def test_the_suite_turns_off_the_proxy_settings_it_inherits(tmp_path: Path) -> None:
    names = ("NO_PROXY", "no_proxy", "HTTPS_PROXY")
    body = f"    import os\n    print([os.environ.get(name) for name in {names!r}])\n"
    result = run_pytest(
        "-s",
        *probe(tmp_path, body),
        env={**os.environ, "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "localhost"},
    )
    assert repr(["*", "*", None]) in result.stdout, result.stdout + result.stderr


def test_subprocess_inheriting_a_replaced_pythonpath_is_still_guarded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    result = run_python(REACH_OTHER_HOST)
    assert result.stdout.split() == ["NetworkAccessRefused"], result.stderr


@pytest.mark.skipif(os.name == "nt", reason="Windows environments have no bytes keys")
def test_subprocess_with_a_bytes_environment_is_still_guarded(tmp_path: Path) -> None:
    env = {os.fsencode(key): os.fsencode(value) for key, value in os.environ.items()}
    env[b"PYTHONPATH"] = os.fsencode(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", REACH_OTHER_HOST],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,  # pyright: ignore[reportArgumentType]
        check=False,
    )
    assert result.stdout.split() == ["NetworkAccessRefused"], result.stderr


def test_subprocess_keeps_empty_pythonpath_entries(tmp_path: Path) -> None:
    # Python reads an empty entry as the current directory.
    (tmp_path / "script").mkdir()
    (tmp_path / "script" / "main.py").write_text("import here\n", encoding="utf-8")
    (tmp_path / "cwd").mkdir()
    (tmp_path / "cwd" / "here.py").write_text("", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(tmp_path / "script" / "main.py")],
        cwd=tmp_path / "cwd",
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONPATH": os.pathsep + str(tmp_path / "elsewhere")},
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_subprocess_accepts_a_generator_of_arguments() -> None:
    # Popen reads any iterable at run time, though its type stubs say a sequence.
    command = (arg for arg in [sys.executable, "-c", "pass"])
    result = subprocess.run(command, timeout=60, check=False)  # pyright: ignore[reportCallIssue, reportArgumentType]
    assert result.returncode == 0


def test_subprocess_keeps_its_arguments_as_given() -> None:
    # A tuple stays a tuple in CompletedProcess.args and CalledProcessError.cmd.
    command = (sys.executable, "-c", "pass")
    assert subprocess.run(command, timeout=60, check=True).args == command


@pytest.mark.parametrize(
    "options", [["-I"], ["-E"], ["-S"], ["-sE"], ["-W", "ignore", "-I"], ["-X", "dev", "-S"]]
)
def test_python_without_the_guard_is_refused(options: list[str]) -> None:
    with refused():
        subprocess.run([sys.executable, *options, "-c", "pass"], check=False)


@pytest.mark.parametrize(
    "command",
    [
        ["python3.13t", "-I"],
        ["python3.12d", "-E"],
        ["python3.12-intel64", "-S"],
        ["pypy3", "-I"],
        ["python.exe", "-I"],
        ["py", "-3.12", "-I"],
        ["py", "-V:3.12", "-E"],
    ],
)
def test_other_interpreter_names_are_checked_too(command: list[str]) -> None:
    # Refused before the program is looked for, so none of these needs to exist.
    with refused():
        subprocess.run([*command, "-c", "pass"], check=False)


@pytest.mark.parametrize(
    "command",
    [
        ["env", sys.executable, "-I"],
        ["uv", "run", "python", "-S"],
        ["env", "-u", "PYTHONPATH", sys.executable],
        ["env", "PYTHONPATH=", sys.executable],
        ["env", "-i", sys.executable],
    ],
    ids=["env -I", "uv run -S", "env -u", "env assignment", "env -i"],
)
def test_python_behind_a_wrapper_is_checked_too(command: list[str]) -> None:
    with refused():
        subprocess.run([*command, "-c", "pass"], check=False)


def test_a_script_the_launcher_runs_keeps_its_own_arguments() -> None:
    # a1.py isn't a choice of Python, such as -3.12, so -I is the script's.
    with contextlib.suppress(FileNotFoundError):  # Not refused, so the launcher is looked for.
        subprocess.run(["py", "a1.py", "-I"], capture_output=True, timeout=60, check=False)


# A command line for the platform's shell.
command_line = subprocess.list2cmdline if os.name == "nt" else shlex.join
PYTHON = command_line([sys.executable])


def shell(command: str) -> Callable[[], object]:
    return lambda: subprocess.run(command, shell=True, check=False)


@pytest.mark.parametrize(
    "start",
    [
        pytest.param(shell(f"{PYTHON} -I -c pass"), id="string"),
        pytest.param(
            lambda: subprocess.run([f"cd . && {PYTHON} -S -c pass"], shell=True, check=False),
            id="list",
        ),
        pytest.param(lambda: os.popen(f"{PYTHON} -E -c pass").close(), id="os.popen"),
        pytest.param(shell("true;python3 -I -c pass"), id="joined without spaces"),
        pytest.param(shell(f"PYTHONPATH= {PYTHON} -c pass"), id="PYTHONPATH assigned"),
        pytest.param(shell(f"unset PYTHONPATH; {PYTHON} -c pass"), id="PYTHONPATH unset"),
        pytest.param(shell(f"env -i {PYTHON} -c pass"), id="env -i"),
        pytest.param(shell('"py" -I -c pass'), id="quoted launcher"),
        pytest.param(
            lambda: subprocess.run(f"{PYTHON} -I -c pass", check=False),
            id="command line",
            marks=pytest.mark.skipif(os.name != "nt", reason="a command line only on Windows"),
        ),
    ],
)
def test_shell_commands_without_the_guard_are_refused(start: Callable[[], object]) -> None:
    with refused():
        start()


def test_shell_commands_that_keep_the_guard_run() -> None:
    # Python's own arguments may name PYTHONPATH; only a command that changes it is refused.
    code = "import os, socket; os.environ['PYTHONPATH']; socket.getaddrinfo('example.invalid', 1)"
    result = subprocess.run(
        f"cd . && {command_line([sys.executable, '-c', code])}",
        shell=True,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == REFUSED_EXIT_STATUS, result.stderr
    assert "NetworkAccessRefused" in result.stderr


@pytest.mark.parametrize(
    "options", [["-Werror::ImportWarning"], ["-W", "ignore::EncodingWarning"], ["-u"]]
)
def test_python_options_that_keep_the_guard_are_allowed(options: list[str]) -> None:
    # A value such as ImportWarning isn't an option, nor is an argument after -c.
    result = run_python(REACH_OTHER_HOST, "-I", options=options)
    assert result.stdout.split() == ["NetworkAccessRefused"], result.stderr


def test_subprocess_stops_if_the_guard_cannot_be_installed(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken"
    shutil.copytree(GUARD_DIR, broken, ignore=shutil.ignore_patterns("__pycache__"))
    (broken / "trialfolio_network_guard.py").write_text("raise RuntimeError('broken guard')\n")
    # os.spawnve starts the child without subprocess.Popen, which would put the working guard
    # first on its PYTHONPATH.
    code = os.spawnve(
        os.P_WAIT,
        sys.executable,
        [sys.executable, "-c", "print('ran without the guard')"],
        {**os.environ, "PYTHONPATH": str(broken)},
    )
    out, err = capfd.readouterr()
    assert code == 70
    assert "ran without the guard" not in out
    assert "broken guard" in err


def test_subprocess_runs_the_sitecustomize_the_guard_shadows_once(tmp_path: Path) -> None:
    # Another checkout's copy of the guard is passed over, and the real one runs once.
    other_checkout = tmp_path / "other-checkout"
    shutil.copytree(GUARD_DIR, other_checkout, ignore=shutil.ignore_patterns("__pycache__"))
    shadowed = tmp_path / "shadowed"
    shadowed.mkdir()
    (shadowed / "sitecustomize.py").write_text(
        "import os\nos.environ['SHADOWED_RUNS'] = os.environ.get('SHADOWED_RUNS', '') + 'x'\n",
        encoding="utf-8",
    )
    path = os.pathsep.join([os.environ["PYTHONPATH"], str(other_checkout), str(shadowed)])
    result = run_python(
        "import os, sitecustomize\n"
        "print(os.environ['SHADOWED_RUNS'])\n"
        "print(os.path.basename(os.path.dirname(sitecustomize.__file__)))\n" + REACH_OTHER_HOST,
        env={**os.environ, "PYTHONPATH": path},
    )
    # `import sitecustomize` gives the shadowed module, as it would without the guard.
    assert result.stdout.split() == ["x", "shadowed", "NetworkAccessRefused"], result.stderr


def test_a_suite_run_under_the_guard_shares_it() -> None:
    # The environment any nested pytest run inherits: the guard is already installed, by
    # sitecustomize, when the plugin installs it again. Wrapping each call once shows that
    # it's one guard.
    result = run_pytest(
        f"{__file__}::test_test_process_refuses_another_host",
        f"{__file__}::test_the_guard_wraps_each_call_once",
    )
    assert result.returncode == 0, result.stdout + result.stderr


ALLOWANCE = """\
import socket
import trialfolio_network_guard as guard

def attempt(call, *args):
    try:
        call(*args)
    except BaseException as error:
        print(type(error).__name__)

print(sorted(guard.allowed_hosts()))
attempt(socket.getaddrinfo, "other.invalid", 443)

# Below the guard, a fake resolver and a fake connect, so nothing leaves the machine.
guard.uninstall()
reached = []
socket.getaddrinfo = lambda host, port, *args, **kwargs: [
    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", port))
]
socket.socket.connect = lambda self, address: reached.append(address[0])
guard.install(["API.example.invalid."])
sock = socket.socket()
sock.connect(socket.getaddrinfo("api.example.invalid", 443)[0][4])
attempt(sock.connect, ("192.0.2.2", 443))
attempt(sock.connect, ("other.invalid", 443))
sock.close()
print(reached)
"""


def test_an_allowed_host_and_its_addresses_are_reachable_and_nothing_else() -> None:
    result = run_python(ALLOWANCE, env={**os.environ, ALLOW_ENV: "api.example.invalid"})
    assert result.stdout.splitlines() == [
        "['api.example.invalid']",
        "NetworkAccessRefused",
        "NetworkAccessRefused",
        "NetworkAccessRefused",
        "['192.0.2.1']",
    ], result.stderr


ALLOWED_PROCESS = f"""\
import os, shlex, subprocess, sys
show = (
    "import os, trialfolio_network_guard as guard;"
    "print(os.environ.get({ALLOW_ENV!r}), sorted(guard.allowed_hosts()), flush=True)"
)
command = [sys.executable, "-c", show]
subprocess.run(command, check=True)
os.system(subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command))
"""


def test_the_allowance_reaches_no_process_the_allowed_one_starts() -> None:
    result = run_python(ALLOWED_PROCESS, env={**os.environ, ALLOW_ENV: "api.example.invalid"})
    assert result.stdout.splitlines() == ["None []", "None []"], result.stderr


def test_the_suite_refuses_to_run_with_an_allowance() -> None:
    result = run_pytest(
        f"{__file__}::test_the_guard_wraps_each_call_once",
        env={**os.environ, ALLOW_ENV: "api.example.invalid"},
    )
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout + result.stderr
    assert ALLOW_ENV in result.stderr
