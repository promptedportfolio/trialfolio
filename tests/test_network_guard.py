"""The network guard refuses every host but localhost, in the test process and in subprocesses.

Traces to P-12 (docs/spec.md) and to the network guard in release 0.1.0's test pairing. The
other host is a reserved name and a documentation address (RFC 6761, RFC 5737), so even a
broken guard would reach no real service.
"""

import os
import socket
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import requests

from tests.support.network_guard import NetworkAccessRefused

OTHER_NAME = "example.invalid"
OTHER_ADDRESS = "192.0.2.1"


def run_python(
    code: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        check=False,
    )


@pytest.fixture
def local_port() -> Iterator[int]:
    """A listening TCP port on 127.0.0.1. A connection completes without accept()."""
    with socket.create_server(("127.0.0.1", 0)) as server:
        yield server.getsockname()[1]


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


def get_with_requests() -> None:
    # Trial Folio's provider calls go through requests and urllib3. The refusal isn't an OSError,
    # so neither can turn it into a connection error.
    requests.get(f"https://{OTHER_NAME}/", timeout=1)


@pytest.mark.parametrize(
    "reach",
    [connect_by_name, look_up_name, connect_by_address, send_datagram, get_with_requests],
)
def test_test_process_refuses_another_host(reach: Callable[[], None]) -> None:
    with pytest.raises(NetworkAccessRefused):
        reach()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_test_process_reaches_localhost(local_port: int, host: str) -> None:
    socket.create_connection((host, local_port), timeout=5).close()


def test_subprocess_refuses_another_host() -> None:
    result = run_python(
        "import socket, sys; socket.create_connection((sys.argv[1], 443), timeout=1)", OTHER_NAME
    )
    assert result.returncode != 0
    assert "NetworkAccessRefused" in result.stderr


def test_subprocess_reaches_localhost(local_port: int) -> None:
    result = run_python(
        "import socket, sys\n"
        "for host in ('127.0.0.1', 'localhost'):\n"
        "    socket.create_connection((host, int(sys.argv[1])), timeout=5).close()\n",
        str(local_port),
    )
    assert result.returncode == 0, result.stderr


def test_subprocess_still_runs_the_sitecustomize_the_guard_shadows(tmp_path: Path) -> None:
    (tmp_path / "sitecustomize.py").write_text(
        "import os\nos.environ['SHADOWED_SITECUSTOMIZE'] = 'ran'\n", encoding="utf-8"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([os.environ["PYTHONPATH"], str(tmp_path)])}
    result = run_python(
        "import os, socket\n"
        "print(os.environ.get('SHADOWED_SITECUSTOMIZE'))\n"
        "try:\n"
        "    socket.getaddrinfo('example.invalid', 443)\n"
        "except BaseException as error:\n"
        "    print(type(error).__name__)\n",
        env=env,
    )
    assert result.stdout.split() == ["ran", "NetworkAccessRefused"], result.stderr
