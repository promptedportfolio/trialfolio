"""The run builder: writes the runs a review compares, with `trialfolio run`, through the CLI's
entry function in the test process (release 0.2.0, test pairing). It isn't a double: each run is
real `trialfolio run` output.

Each run is approved with `--approve` and its plan's hash, and written with the fixed clock. The
fake Portfolio123 server answers its backtest request with a response from `responses/`, with a
200, or with a failure, such as a 400. Each run has a server of its own, stopped before the
builder returns, so none runs when a review starts.

The runs' values are invented, but nothing labels them synthetic, so a committed copy would read
as a Portfolio123 backtest (DSC-04). They exist only in the test's temporary directory.

R02-T06 wrote it ahead of R02-T09, for the comparison core's tests.
"""

import io
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from tests.support import canaries
from tests.support.clock import FixedClock
from tests.support.environment import VARIABLES
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE, main
from trialfolio.configuration import read_screen_configuration
from trialfolio.planning import build_plan, installed_versions

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures"
SCREEN_CONFIGS: Final = FIXTURES / "screen-configs"
RESPONSES: Final = FIXTURES / "responses"
REVIEW_CONFIGS: Final = FIXTURES / "review-configs"

REJECTED: Final = Reply(400, b"Unsupported value")
"""Portfolio123's 400 for a request the provider path doesn't support. The run saves no
response."""


@dataclass(frozen=True)
class Run:
    """A run to write: its screen configuration, in `screen-configs/`, and the fake server's
    reply to its backtest request: a response in `responses/`, sent with a 200, or a failure."""

    configuration: str
    backtest: str | Reply

    @property
    def reply(self) -> Reply:
        if isinstance(self.backtest, Reply):
            return self.backtest
        return Reply(200, (RESPONSES / self.backtest).read_bytes())


BASELINE: Final = Run("formula.yaml", "complete.json")
"""The baseline's run, in every review configuration the comparison core's tests read."""

HOLDINGS_50: Final = Run("holdings-50.yaml", "changed-metrics.json")
BENCHMARK_OTHER: Final = Run("benchmark-other.yaml", "changed-metrics.json")

RUNS: Final[dict[str, dict[str, Run]]] = {
    "example.yaml": {"runs/hold25": BASELINE, "runs/hold50": HOLDINGS_50},
    "undeclared.yaml": {
        "runs/baseline": BASELINE,
        "runs/slippage": Run("slippage-whole.yaml", "same-metrics.json"),
        "runs/benchmark": BENCHMARK_OTHER,
        "runs/ranking-name": Run("ranking-name.yaml", "missing-metrics.json"),
    },
    "declared-benchmark.yaml": {"runs/baseline": BASELINE, "runs/benchmark": BENCHMARK_OTHER},
    "not-observed.yaml": {
        "runs/baseline": BASELINE,
        "runs/declared": Run("formula.yaml", "changed-metrics.json"),
    },
    "coverage.yaml": {
        "runs/baseline": BASELINE,
        "runs/coverage-mismatch": Run("formula.yaml", "coverage-mismatch.json"),
        "runs/no-periods": Run("formula.yaml", "no-periods.json"),
    },
    "coverage-and-benchmark.yaml": {
        "runs/baseline": BASELINE,
        "runs/benchmark": Run("benchmark-other.yaml", "coverage-mismatch.json"),
    },
    "missing-metrics.yaml": {
        "runs/baseline": BASELINE,
        "runs/missing": Run("formula.yaml", "missing-metrics.json"),
    },
    "without-tables.yaml": {
        "runs/baseline": BASELINE,
        "runs/rejected": Run("formula.yaml", REJECTED),
        "runs/invalid-structure": Run("formula.yaml", "invalid-structure.json"),
        "runs/not-json": Run("formula.yaml", "not-json.txt"),
    },
    "shared-response.yaml": {
        "runs/baseline": BASELINE,
        "runs/written-differently": Run("written-differently.yaml", "complete.json"),
        "runs/hold50-first": HOLDINGS_50,
        "runs/hold50-second": HOLDINGS_50,
        "runs/slippage": Run("slippage-whole.yaml", "same-metrics.json"),
    },
}
"""The runs each review configuration names, by its `run` path, as `review-configs/README.md`
gives them."""


class RunBuilder:
    """Writes runs with `trialfolio run`, in the test process, with a temporary home and without
    the variables Trial Folio reads, apart from the license acknowledgment and the canary
    credentials."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
        self._monkeypatch = monkeypatch
        self._home = home

    def run(self, run: Run, out: Path) -> Path:
        """Writes `run` into the new output directory `out`, and returns it."""
        path = SCREEN_CONFIGS / run.configuration
        configuration = read_screen_configuration(path.read_bytes(), run.configuration)
        plan_hash = build_plan(configuration, installed_versions()).plan_hash
        server = FakePortfolio123()
        stderr = io.StringIO()
        try:
            server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
            server.reply("/screen/backtest", run.reply)
            with self._monkeypatch.context() as patch:
                self._home.mkdir(parents=True, exist_ok=True)
                patch.setenv("HOME", str(self._home))
                for name in VARIABLES:
                    patch.delenv(name, raising=False)
                patch.setenv(ACCEPT_VARIABLE, ACCEPT_VALUE)
                patch.setenv(API_ID_VARIABLE, canaries.API_ID)
                patch.setenv(API_KEY_VARIABLE, canaries.API_KEY)
                patch.setattr(sys, "stdin", io.StringIO())
                patch.setattr(sys, "stdout", io.StringIO())
                patch.setattr(sys, "stderr", stderr)
                main(
                    ["run", str(path), "--out", str(out), "--approve", plan_hash],
                    endpoint=server.endpoint,
                    clock=FixedClock(),
                )
        finally:
            server.close()
        # A run that fails still writes its manifest, so it's complete, and can be reviewed.
        assert (out / "manifest.json").is_file(), stderr.getvalue()
        return out

    def review(self, name: str, directory: Path) -> Path:
        """Copies the review configuration `name` into `directory`, writes each run it names at
        its `run` path, and returns the configuration's path."""
        directory.mkdir(parents=True, exist_ok=True)
        path = Path(shutil.copy(REVIEW_CONFIGS / name, directory / name))
        for run_path, run in RUNS[name].items():
            self.run(run, directory / run_path)
        return path
