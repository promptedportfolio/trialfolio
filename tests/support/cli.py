"""The tests' CLI: runs `trialfolio` through its entry function, in the test process, with doubles
only at the boundaries the release allows (AGENTS.md, verification expectations; release 0.1.0,
test pairing):

- the fake Portfolio123 server, below `urllib3`, through the entry function's `endpoint`;
- a fixed clock, through `clock`;
- a fake pause, through `pause`, so no command waits 10 seconds before a backtest (D-45): `Cli`'s
  own, for the test, which records each wait with what the server had received then;
- storage faults, through `store_factory`.

`on_terminal` runs the command in a new process instead, under a real pseudo-terminal, through
the test launcher, with the fake server's endpoint and no other double.

Each test gets a temporary home, so the per-user configuration and log directories are under it,
and an environment without the variables Trial Folio reads, so nothing on the machine running the
tests leaks in (`tests/support/environment.py`). stdin is empty and isn't a terminal, unless a
test gives a pseudo-terminal.

TS-T03 moved it here from the interface's conftest, which keeps the fixtures, and added
`run_approved`, for the commands each module ran with `--approve` and the plan's hash, and
`on_pseudo_terminal`, for the runs `tests/interface/test_experiment_repeat.py` wrote under one.
"""

import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TextIO

import pytest

from tests.support import launcher
from tests.support.clock import FakePause
from tests.support.environment import (
    Outcome,
    accept_license,
    inject_credentials,
    isolate,
    run_cli,
)
from tests.support.fake_portfolio123 import FakePortfolio123
from tests.support.terminal import PseudoTerminal, Terminal
from trialfolio.configuration import read_screen_configuration_v1_1
from trialfolio.planning import build_plan_v1_1, installed_versions
from trialfolio.provider import REQUEST_TIMEOUT_SECONDS
from trialfolio.ranking_lock import LOCK_DIRECTORY_VARIABLE
from trialfolio.storage import ArtifactStore, LocalArtifactStore


def plan_hash_for(path: Path) -> str:
    """The hash of the plan the configuration at `path` resolves to with the installed versions,
    as `trialfolio run` shows it: read by release 0.4.0's reader, as `run` reads it from R04-T12,
    so a screen configuration 1.1.0's too."""
    read = read_screen_configuration_v1_1(path.read_bytes(), str(path), path)
    return build_plan_v1_1(read, installed_versions()).plan_hash


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
        isolate(monkeypatch, self.home)
        # The ranking lock's file is in a directory of the test's own, beside its temporary
        # directory, whose contents tests compare, so tests that run at once don't exclude each
        # other, and none takes the machine's lock.
        self.locks = tmp_path.with_name(f"{tmp_path.name}-locks")
        self.locks.mkdir(exist_ok=True)
        monkeypatch.setenv(LOCK_DIRECTORY_VARIABLE, str(self.locks))
        self.pause = FakePause(server)
        """The pause every command of the test takes, which records each wait (D-45)."""

    def accept_license(self) -> None:
        """Acknowledges the license for the test, as CI would, without a record."""
        accept_license(self._monkeypatch)

    def credentials(self) -> None:
        """Injects the canary credentials."""
        inject_credentials(self._monkeypatch)

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
        return run_cli(
            *argv,
            endpoint=self.server.endpoint,
            timeout=timeout,
            clock=clock,
            store_factory=store_factory,
            pause=self.pause.pause,
            stdin=stdin,
            stderr=stderr,
        )

    def run_approved(
        self,
        configuration: Path,
        out: Path,
        *options: str | Path,
        stdin: TextIO | None = None,
        stderr: TextIO | None = None,
        store_factory: Callable[[str], ArtifactStore] = LocalArtifactStore,
        timeout: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> Outcome:
        """Runs `trialfolio run` of the screen configuration at `configuration` into `out`,
        approved with `--approve` and its plan's hash, then `options`, as `__call__` runs any
        command."""
        return self(
            "run",
            configuration,
            "--out",
            out,
            "--approve",
            plan_hash_for(configuration),
            *options,
            stdin=stdin,
            stderr=stderr,
            store_factory=store_factory,
            timeout=timeout,
            clock=clock,
        )

    def on_pseudo_terminal(self, keys: str, *argv: str | Path) -> tuple[Outcome, str]:
        """Runs the command with `argv`, in the test process, with a real pseudo-terminal as its
        stdin and stderr, on which `keys` are typed first, and returns its outcome and everything
        the terminal showed, typed echo included."""
        with PseudoTerminal() as terminal:
            terminal.press(keys)
            outcome = self(*argv, stdin=terminal.stdin, stderr=terminal.stderr)
        return outcome, terminal.shown()

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
        return Outcome.of(result)


_WITHOUT_MODULE = """
import sys

sys.modules[sys.argv[1]] = None  # importing it fails, as when its files are gone
from trialfolio.cli import main

sys.exit(main(sys.argv[2:]))
"""


def occupied(cli: Cli, name: str) -> Path:
    """An output directory holding one file, `name`."""
    out = cli.tmp / "out"
    out.mkdir()
    (out / name).write_bytes(b"someone else's file\n")
    return out
