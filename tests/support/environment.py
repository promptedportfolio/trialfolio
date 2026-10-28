"""The environment a test runs Trial Folio's CLI in, and the runner that runs it there.

The environment has none of the variables Trial Folio reads, apart from `HOME`, which a test
points at a temporary directory, so nothing on the machine running the tests leaks in. `isolate`
sets it up through a `MonkeyPatch` the caller holds, as the tests' `Cli` does for the whole test,
and `isolated` for the length of a block, with the license acknowledged and the canary
credentials injected when asked, as the run and snapshot builders, the manual's reference test,
and the two writers of the committed fixtures, which also run as scripts, do.

`run_cli` runs one command through the CLI's entry function, in this process, with stdin empty
unless given, and gives what it did, as an `Outcome`, whose properties read its JSON summary;
`Outcome.of` gives the same for a command run in a new process.
TS-T03 wrote them once, for the six places that each wrote their own.
"""

import contextlib
import io
import json
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Self, TextIO, cast

import pytest

from tests.support import canaries
from tests.support.clock import FixedClock
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE, main
from trialfolio.pause import REAL_PAUSE, Pause
from trialfolio.ranking_lock import LOCK_DIRECTORY_VARIABLE
from trialfolio.storage import ArtifactStore, LocalArtifactStore

VARIABLES: Final = (
    "TRIALFOLIO_CONFIG_DIR",
    "TRIALFOLIO_LOG_DIR",
    "TRIALFOLIO_LOG_LEVEL",
    LOCK_DIRECTORY_VARIABLE,
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
"""The variables Trial Folio reads, which each test starts without, apart from `HOME`. A test that
runs the CLI then names a ranking lock's directory of its own, `TRIALFOLIO_LOCK_DIR`, so the
default suite never takes the machine's lock (release 0.4.0, test doubles)."""


def isolate(patch: pytest.MonkeyPatch, home: Path) -> None:
    """Through `patch`, points `HOME` at `home`, and removes each of `VARIABLES`."""
    patch.setenv("HOME", str(home))
    for name in VARIABLES:
        patch.delenv(name, raising=False)


def accept_license(patch: pytest.MonkeyPatch) -> None:
    """Through `patch`, acknowledges the license for the process, as CI would, without a
    record."""
    patch.setenv(ACCEPT_VARIABLE, ACCEPT_VALUE)


def inject_credentials(patch: pytest.MonkeyPatch) -> None:
    """Through `patch`, injects the canary credentials."""
    patch.setenv(API_ID_VARIABLE, canaries.API_ID)
    patch.setenv(API_KEY_VARIABLE, canaries.API_KEY)


@contextlib.contextmanager
def isolated(
    home: Path, *, licensed: bool = False, credentials: bool = False
) -> Iterator[pytest.MonkeyPatch]:
    """`isolate`'s environment, with `home` as `HOME`, until the block ends: with the license
    acknowledged when `licensed`, and the canary credentials when `credentials`. Yields the
    patch, through which the block may change it more."""
    with pytest.MonkeyPatch.context() as patch:
        isolate(patch, home)
        if licensed:
            accept_license(patch)
        if credentials:
            inject_credentials(patch)
        yield patch


@dataclass(frozen=True)
class Outcome:
    """What one command did: its exit code, and what it wrote to stdout and stderr. The
    properties read its JSON summary, and each fails when the summary doesn't have what it
    reads."""

    exit_code: int
    stdout: str
    stderr: str

    @classmethod
    def of(cls, process: subprocess.CompletedProcess[str]) -> Self:
        """What a command run in a new process did, from what it left."""
        return cls(process.returncode, process.stdout, process.stderr)

    @property
    def summary(self) -> dict[str, object]:
        """The JSON summary on stdout: exactly one object, followed by a newline."""
        assert self.stdout.endswith("\n")
        assert self.stdout.count("\n") == 1
        loaded: object = json.loads(self.stdout)
        assert isinstance(loaded, dict)
        return loaded  # pyright: ignore[reportUnknownVariableType]

    @property
    def error(self) -> dict[str, str]:
        """The summary's error, with its `code` and its `message`, of a command that failed."""
        error = self.summary["error"]
        assert isinstance(error, dict), f"the summary's error is {error!r}"
        return cast("dict[str, str]", error)

    @property
    def error_code(self) -> str:
        """The code of the summary's error."""
        return self.error["code"]

    @property
    def ids(self) -> dict[str, object]:
        """The summary's `ids`."""
        return self._mapping("ids")

    @property
    def outputs(self) -> dict[str, str]:
        """The summary's `outputs`, each by its role."""
        return cast("dict[str, str]", self._mapping("outputs"))

    @property
    def counts(self) -> dict[str, int | None]:
        """The summary's `counts`."""
        return cast("dict[str, int | None]", self._mapping("counts"))

    @property
    def cases(self) -> list[dict[str, object]]:
        """The summary's `cases`, an experiment's, in its plan's order."""
        cases = self.summary["cases"]
        assert isinstance(cases, list), f"the summary's cases are {cases!r}"
        return cast("list[dict[str, object]]", cases)

    @property
    def cases_by_key(self) -> dict[str, dict[str, object]]:
        """The summary's `cases`, by each one's `case_key`, which no two of them share."""
        cases = self.cases
        keys = [cast("str", case["case_key"]) for case in cases]
        assert len(set(keys)) == len(keys), f"a case key is given twice: {keys}"
        return dict(zip(keys, cases, strict=True))

    def _mapping(self, key: str) -> dict[str, object]:
        value = self.summary[key]
        assert isinstance(value, dict), f"the summary's {key} is {value!r}"
        return cast("dict[str, object]", value)


def run_cli(
    *argv: str | Path,
    endpoint: str | None = None,
    timeout: int | None = None,
    clock: Callable[[], datetime] | None = None,
    store_factory: Callable[[str], ArtifactStore] = LocalArtifactStore,
    pause: Pause = REAL_PAUSE,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
    check: bool = False,
) -> Outcome:
    """Runs `trialfolio` with `argv` through its entry function, in this process, in the
    environment as it is, and returns what it did. stdin is empty unless given. stdout is
    captured, and so is stderr, unless given, such as a pseudo-terminal's, when the outcome's is
    empty. The clock is a new `FixedClock`, unless given; the other keywords are the entry
    function's, which it gives as they are. With `check`, it raises `AssertionError`, with what
    the command wrote, unless the command succeeds."""
    out = io.StringIO()
    captured = io.StringIO()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "stdin", io.StringIO() if stdin is None else stdin)
        patch.setattr(sys, "stdout", out)
        patch.setattr(sys, "stderr", captured if stderr is None else stderr)
        code = main(
            [str(arg) for arg in argv],
            endpoint=endpoint,
            timeout=timeout,
            clock=FixedClock() if clock is None else clock,
            store_factory=store_factory,
            pause=pause,
        )
    outcome = Outcome(code, out.getvalue(), captured.getvalue() if stderr is None else "")
    if check and code != 0:
        raise AssertionError(
            f"trialfolio {' '.join(map(str, argv))} exited with {code}:\n"
            f"{outcome.stdout}{outcome.stderr}"
        )
    return outcome
