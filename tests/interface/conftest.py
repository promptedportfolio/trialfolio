"""Running the CLI's entry function in the test process, with doubles only at the boundaries the
release allows (AGENTS.md, verification expectations; release 0.1.0, test pairing):

- the fake Portfolio123 server, below `urllib3`, through the entry function's `endpoint`;
- a fixed clock, through `clock`;
- storage faults, through `store_factory`.

Each test gets a temporary home, so the per-user configuration and log directories are under it,
and an environment without the variables Trial Folio reads, so nothing on the machine running the
tests leaks in. stdin is empty and isn't a terminal, unless a test gives a pseudo-terminal.
"""

import io
import json
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TextIO

import pytest

from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.storage_faults import StorageFaults
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE, main
from trialfolio.configuration import read_screen_configuration
from trialfolio.planning import build_plan, installed_versions
from trialfolio.storage import ArtifactStore, LocalArtifactStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONFIGS = FIXTURES / "screen-configs"
RESPONSES = FIXTURES / "responses"

STARTED = datetime(2026, 10, 3, 14, 0, 0, tzinfo=UTC)
"""The fixed clock's first time; each later reading is a second after the one before."""

_VARIABLES = (
    "TRIALFOLIO_CONFIG_DIR",
    "TRIALFOLIO_LOG_DIR",
    "TRIALFOLIO_LOG_LEVEL",
    "XDG_CONFIG_HOME",
    "XDG_STATE_HOME",
    "APPDATA",
    "LOCALAPPDATA",
    "USERPROFILE",
    ACCEPT_VARIABLE,
    API_ID_VARIABLE,
    API_KEY_VARIABLE,
    "SSLKEYLOGFILE",
)
"""The variables Trial Folio reads, which each test starts without, apart from `HOME`."""


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
        for name in _VARIABLES:
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
    ) -> Outcome:
        """Runs the command with `argv`. stdin is empty unless given. stderr is captured unless
        given, such as a pseudo-terminal's."""
        out = io.StringIO()
        captured = io.StringIO()
        err = captured if stderr is None else stderr
        moments = (STARTED + timedelta(seconds=n) for n in range(10_000))
        with self._monkeypatch.context() as patch:
            patch.setattr(sys, "stdin", io.StringIO() if stdin is None else stdin)
            patch.setattr(sys, "stdout", out)
            patch.setattr(sys, "stderr", err)
            code = main(
                [str(arg) for arg in argv],
                endpoint=self.server.endpoint,
                timeout=timeout,
                clock=lambda: next(moments),
                store_factory=store_factory,
            )
        return Outcome(code, out.getvalue(), captured.getvalue() if stderr is None else "")


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
