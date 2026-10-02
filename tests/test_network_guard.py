"""The network guard refuses every host but localhost, in the test process and in subprocesses.

Traces to P-12 (docs/spec.md) and to the network guard in release 0.1.0's test pairing. The
other host is a reserved name and a documentation address (RFC 6761, RFC 5737), so even a
broken guard would reach no real service.
"""

import email.utils
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import requests
from trialfolio_network_guard import GUARD_DIR, NetworkAccessRefused

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
    with pytest.raises(NetworkAccessRefused):
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
    with pytest.raises(NetworkAccessRefused):
        requests.get(f"https://{OTHER_NAME}/", timeout=1)
    with pytest.raises(BlockingIOError):  # The proxy received no connection.
        listener.accept()


def test_local_name_lookups_degrade_instead_of_failing() -> None:
    # As after a failed lookup, getfqdn gives back the name, which local servers and email
    # message IDs rely on.
    assert socket.getfqdn(OTHER_NAME) == OTHER_NAME
    assert socket.getfqdn("") and socket.getfqdn("0.0.0.0")
    assert email.utils.make_msgid()


def test_subprocess_refuses_another_host() -> None:
    result = run_python(
        "import socket, sys; socket.create_connection((sys.argv[1], 443), timeout=1)", OTHER_NAME
    )
    assert result.returncode != 0
    assert "NetworkAccessRefused" in result.stderr


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


@pytest.mark.parametrize(
    "options", [["-I"], ["-E"], ["-S"], ["-sE"], ["-W", "ignore", "-I"], ["-X", "dev", "-S"]]
)
def test_python_without_the_guard_is_refused(options: list[str]) -> None:
    with pytest.raises(NetworkAccessRefused):
        subprocess.run([sys.executable, *options, "-c", "pass"], check=False)


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
        "import os\nprint(os.environ['SHADOWED_RUNS'])\n" + REACH_OTHER_HOST,
        env={**os.environ, "PYTHONPATH": path},
    )
    assert result.stdout.split() == ["x", "NetworkAccessRefused"], result.stderr


def test_a_suite_run_under_the_guard_shares_it() -> None:
    # The environment any nested pytest run inherits: the guard is already installed, by
    # sitecustomize, when the conftest installs it again.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            f"{__file__}::test_test_process_refuses_another_host",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
