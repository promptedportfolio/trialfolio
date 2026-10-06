"""Running the CLI's entry function in the test process, with doubles only at the boundaries the
release allows (AGENTS.md, verification expectations; release 0.1.0, test pairing):

- the fake Portfolio123 server, below `urllib3`, through the entry function's `endpoint`;
- a fixed clock, through `clock`;
- storage faults, through `store_factory`.

`on_terminal` runs the command in a new process instead, under a real pseudo-terminal, through
the test launcher, with the fake server's endpoint and no other double.

Each test gets a temporary home, so the per-user configuration and log directories are under it,
and an environment without the variables Trial Folio reads, so nothing on the machine running the
tests leaks in. stdin is empty and isn't a terminal, unless a test gives a pseudo-terminal.

A review's tests read runs that the run builder writes, once for each module, beside a copy of the
review configuration that names them (`built`). A review only reads them.
"""

import io
import json
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

import pytest

from tests.support import canaries, launcher
from tests.support.clock import FixedClock
from tests.support.environment import VARIABLES
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.run_builder import RunBuilder
from tests.support.storage_faults import StorageFaults
from tests.support.terminal import Terminal
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE, main
from trialfolio.configuration import read_screen_configuration
from trialfolio.planning import build_plan, installed_versions
from trialfolio.provider import REQUEST_TIMEOUT_SECONDS
from trialfolio.storage import ArtifactStore, LocalArtifactStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONFIGS = FIXTURES / "screen-configs"
RESPONSES = FIXTURES / "responses"


def config(name: str) -> Path:
    return CONFIGS / name


def response(name: str) -> Reply:
    """A 200 whose body is the response fixture `name`."""
    return Reply(200, (RESPONSES / name).read_bytes())


AUTHENTICATED = Reply(200, canaries.TOKEN.encode())
"""Portfolio123's answer to a successful authentication: the token."""


@dataclass(frozen=True)
class Outcome:
    """What one command did: its exit code, and what it wrote to stdout and stderr."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def summary(self) -> dict[str, object]:
        """The JSON summary on stdout: exactly one object, followed by a newline."""
        assert self.stdout.endswith("\n")
        assert self.stdout.count("\n") == 1
        loaded: object = json.loads(self.stdout)
        assert isinstance(loaded, dict)
        return loaded  # pyright: ignore[reportUnknownVariableType]


class FaultyStores:
    """A `store_factory` that wraps each output directory's real store in storage faults, set up
    as the test asks before the command runs."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._setups: list[Callable[[StorageFaults], None]] = []
        self.stores: list[StorageFaults] = []

    def fail_os(self, name: str) -> None:
        self._setups.append(lambda store: store.fail_os(name))

    def fail_before(self, name: str, error: BaseException) -> None:
        self._setups.append(lambda store: store.fail_before(name, error))

    def fail_after(self, name: str, error: BaseException) -> None:
        self._setups.append(lambda store: store.fail_after(name, error))

    def fail_link(self, name: str) -> None:
        self._setups.append(lambda store: store.fail_link(name))

    def __call__(self, root: str) -> ArtifactStore:
        store = StorageFaults(LocalArtifactStore(root), self._monkeypatch)
        for setup in self._setups:
            setup(store)
        self.stores.append(store)
        return store

    @property
    def published(self) -> list[str]:
        """Every path the store published, in order."""
        (store,) = self.stores
        return store.published


class Cli:
    """Runs `trialfolio` through its entry function, in the test process."""

    def __init__(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, server: FakePortfolio123
    ) -> None:
        self._monkeypatch = monkeypatch
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.server = server
        monkeypatch.setenv("HOME", str(self.home))
        for name in VARIABLES:
            monkeypatch.delenv(name, raising=False)

    def accept_license(self) -> None:
        """Acknowledges the license for the test, as CI would, without a record."""
        self._monkeypatch.setenv(ACCEPT_VARIABLE, ACCEPT_VALUE)

    def credentials(self) -> None:
        """Injects the canary credentials."""
        self._monkeypatch.setenv(API_ID_VARIABLE, canaries.API_ID)
        self._monkeypatch.setenv(API_KEY_VARIABLE, canaries.API_KEY)

    def ready(self) -> None:
        """The license acknowledged and the credentials injected."""
        self.accept_license()
        self.credentials()

    def __call__(
        self,
        *argv: str | Path,
        stdin: TextIO | None = None,
        stderr: TextIO | None = None,
        store_factory: Callable[[str], ArtifactStore] = LocalArtifactStore,
        timeout: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> Outcome:
        """Runs the command with `argv`. stdin is empty unless given. stderr is captured unless
        given, such as a pseudo-terminal's. The clock is a new `FixedClock`, unless given."""
        out = io.StringIO()
        captured = io.StringIO()
        err = captured if stderr is None else stderr
        with self._monkeypatch.context() as patch:
            patch.setattr(sys, "stdin", io.StringIO() if stdin is None else stdin)
            patch.setattr(sys, "stdout", out)
            patch.setattr(sys, "stderr", err)
            code = main(
                [str(arg) for arg in argv],
                endpoint=self.server.endpoint,
                timeout=timeout,
                clock=FixedClock() if clock is None else clock,
                store_factory=store_factory,
            )
        return Outcome(code, out.getvalue(), captured.getvalue() if stderr is None else "")

    def on_terminal(self, *argv: str | Path, timeout: int = REQUEST_TIMEOUT_SECONDS) -> Terminal:
        """Starts the command with `argv` through the test launcher, in a new process under a real
        pseudo-terminal, with this one's environment and the test's directory as its working
        directory."""
        return Terminal(
            launcher.command(self.server.endpoint, *argv, timeout=timeout), cwd=self.tmp
        )

    def without_module(self, name: str, *argv: str | Path) -> Outcome:
        """Runs the command with `argv` in a new process, in which the module `name` can't be
        imported, as when its files are gone. In the test process, the modules that import it are
        loaded already. The new process has this one's environment, with the test's home, and
        stdin closed; the network guard stays on in it."""
        result = subprocess.run(
            [sys.executable, "-c", _WITHOUT_MODULE, name, *(str(arg) for arg in argv)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.tmp,
        )
        return Outcome(result.returncode, result.stdout, result.stderr)


_WITHOUT_MODULE = """
import sys

sys.modules[sys.argv[1]] = None  # importing it fails, as when its files are gone
from trialfolio.cli import main

sys.exit(main(sys.argv[2:]))
"""


@pytest.fixture
def server() -> Iterator[FakePortfolio123]:
    """The fake Portfolio123 server, with nothing scripted: a request it isn't told how to answer
    gets a 404."""
    fake = FakePortfolio123()
    yield fake
    fake.close()


@pytest.fixture
def cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, server: FakePortfolio123) -> Cli:
    return Cli(monkeypatch, tmp_path, server)


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> FaultyStores:
    return FaultyStores(monkeypatch)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[str], Path]]:
    """Builds the runs a review configuration in `review-configs/` names, once for the module,
    beside a copy of it, and gives the copy's path. A test must leave the runs as they are."""
    root = tmp_path_factory.mktemp("runs")
    paths: dict[str, Path] = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        builder = RunBuilder(monkeypatch, root / "home")

        def get(name: str) -> Path:
            if name not in paths:
                paths[name] = builder.review(name, root / name.removesuffix(".yaml"))
            return paths[name]

        yield get


def serve_success(server: FakePortfolio123, body: str = "complete.json") -> None:
    """Scripts a run that succeeds: authentication, then the backtest's 200 with `body`."""
    server.reply("/auth", AUTHENTICATED)
    server.reply("/screen/backtest", response(body))


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Every file and directory under `root`, hidden ones included: a file's bytes, or None for a
    directory."""
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


type Entry = tuple[bool, int, int, bytes | None]


def metadata(root: Path) -> dict[str, Entry]:
    """The root and everything under it, hidden entries included: whether each is a directory,
    and its size, modification time, and bytes."""
    entries: dict[str, Entry] = {}
    for path in (root, *sorted(root.rglob("*"))):
        status = path.stat()
        directory = path.is_dir()
        entries[path.relative_to(root).as_posix()] = (
            directory,
            status.st_size,
            status.st_mtime_ns,
            None if directory else path.read_bytes(),
        )
    return entries


def occupied(cli: Cli, name: str) -> Path:
    """An output directory holding one file, `name`."""
    out = cli.tmp / "out"
    out.mkdir()
    (out / name).write_bytes(b"someone else's file\n")
    return out


def plan_hash_of(outcome: Outcome) -> str:
    """The plan hash a run without approval shows on stderr."""
    for line in outcome.stderr.splitlines():
        if line.startswith("Plan hash: "):
            return line.removeprefix("Plan hash: ")
    raise AssertionError("no plan hash shown")


def plan_hash_for(path: Path) -> str:
    """The hash of the plan the configuration at `path` resolves to with the installed versions,
    as `trialfolio run` shows it."""
    configuration = read_screen_configuration(path.read_bytes(), str(path))
    return build_plan(configuration, installed_versions()).plan_hash
