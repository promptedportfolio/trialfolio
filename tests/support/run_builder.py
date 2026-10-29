"""The run builder: writes the runs a review compares, with `trialfolio run`, through the CLI's
entry function in the test process (release 0.2.0, test pairing). It isn't a double: each run is
real `trialfolio run` output, or a copy of the committed run `trialfolio demo` wrote,
`runs/synthetic-run-1.0.0/`.

Each run is approved with `--approve` and its plan's hash, and written with the fixed clock. The
fake Portfolio123 server answers its backtest request with a response from `responses/`, with a
200, or with a failure, such as a 400. Each run has a server of its own, stopped before the
builder returns, so none runs when a review starts.

The runs' values are invented, but nothing labels them synthetic, so a committed copy would read
as a Portfolio123 backtest (DSC-04). They exist only in the test's temporary directory.

R02-T06 wrote it ahead of R02-T09, for the comparison core's tests, R02-T07 added the committed
synthetic run, for the review report's, and R02-T09 added `canaries.yaml`'s runs.

From release 0.4.0, a screen configuration 1.1.0's run, whose ranking is a definition, is
written with `trialfolio run` too, approved with its plan's hash: the fake server answers its
`POST /rank` with `rank-update.json`, before its backtest, and the run takes the ranking lock on a
file in the builder's temporary home, which `TRIALFOLIO_LOCK_DIR` names. R04-T11 added them, for
the review's weight rows, written through the core until R04-T12 made `trialfolio run` read a
1.1.0 file; since then, they're written through the CLI.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tests.support.cli import plan_hash_for
from tests.support.clock import no_wait
from tests.support.environment import isolated, run_cli
from tests.support.fake_portfolio123 import AUTHENTICATED, FakePortfolio123, Reply
from tests.support.paths import FIXTURES, RESPONSES, SCREEN_CONFIGS
from trialfolio.configuration import read_screen_configuration_v1_1
from trialfolio.ranking_lock import LOCK_DIRECTORY_VARIABLE

REVIEW_CONFIGS: Final = FIXTURES / "review-configs"

SYNTHETIC_RUN: Final = FIXTURES / "runs" / "synthetic-run-1.0.0"
"""The committed run `trialfolio demo` wrote, labeled synthetic. A review gets a copy of it at the
`run` path that names it."""

RANK_UPDATED: Final = Reply(200, (RESPONSES / "rank-update.json").read_bytes())
"""Portfolio123's answer to a `rank_update` that wrote the definition."""

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
"""The baseline's run, in every review configuration the comparison core's tests read, apart
from those that compare weight rows."""

DEFINITION: Final = Run("definition.yaml", "complete.json")
"""The baseline's run of the reviews that compare weight rows: the ranking example's baseline,
ranked by its definition."""

HOLDINGS_50: Final = Run("holdings-50.yaml", "changed-metrics.json")
BENCHMARK_OTHER: Final = Run("benchmark-other.yaml", "changed-metrics.json")
CANARIES: Final = Run("canaries.yaml", "canaries.json")
"""Each result's run in `canaries.yaml`, so its results share one response."""

RUNS: Final[dict[str, dict[str, Run | Path]]] = {
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
    "ranking-weights.yaml": {
        "runs/definition": DEFINITION,
        "runs/value-heavy": Run("value-heavy.yaml", "changed-metrics.json"),
    },
    "ranking-undeclared.yaml": {
        "runs/definition": DEFINITION,
        "runs/value-heavy": Run("value-heavy.yaml", "changed-metrics.json"),
    },
    "ranking-other-forms.yaml": {
        "runs/definition": DEFINITION,
        "runs/formula": Run("formula.yaml", "changed-metrics.json"),
        "runs/ranking-name": Run("ranking-name.yaml", "missing-metrics.json"),
    },
    "ranking-without-tables.yaml": {
        "runs/definition": DEFINITION,
        "runs/value-heavy": Run("value-heavy.yaml", REJECTED),
    },
    "ranking-removal.yaml": {
        "runs/positions": Run("positions.yaml", "complete.json"),
        "runs/without-first-yield": Run(
            "positions-without-first-yield.yaml", "changed-metrics.json"
        ),
    },
    "synthetic.yaml": {"runs/demo": SYNTHETIC_RUN, "runs/hold50": HOLDINGS_50},
    "synthetic-only.yaml": {"runs/demo": SYNTHETIC_RUN},
    "canaries.yaml": {
        "runs/canary-run-da943a28": CANARIES,
        "runs/canary-run-bdcb5a6c": CANARIES,
        "runs/canary-run-993a190a": CANARIES,
    },
}
"""The runs each review configuration names, by its `run` path, as `review-configs/README.md`
gives them: a run to write, or the committed run to copy."""


class RunBuilder:
    """Writes runs with `trialfolio run`, in the test process, with a temporary home and without
    the variables Trial Folio reads, apart from the license acknowledgment and the canary
    credentials (`tests/support/environment.py`)."""

    def __init__(self, home: Path) -> None:
        self._home = home

    def run(self, run: Run, out: Path) -> Path:
        """Writes `run` into the new output directory `out`, and returns it. A run whose ranking
        is a definition gets `rank-update.json`'s 200 to its `POST /rank` first."""
        path = SCREEN_CONFIGS / run.configuration
        read = read_screen_configuration_v1_1(path.read_bytes(), run.configuration, path)
        server = FakePortfolio123()
        try:
            server.reply("/auth", AUTHENTICATED)
            if read.definition is not None:
                server.reply("/rank", RANK_UPDATED, method="POST")
            server.reply("/screen/backtest", run.reply)
            self._home.mkdir(parents=True, exist_ok=True)
            with isolated(self._home, licensed=True, credentials=True) as patch:
                # The ranking lock's file is in the builder's home, never the machine's.
                patch.setenv(LOCK_DIRECTORY_VARIABLE, str(self._home))
                outcome = run_cli(
                    "run",
                    path,
                    "--out",
                    out,
                    "--approve",
                    plan_hash_for(path),
                    endpoint=server.endpoint,
                    pause=no_wait(),
                )
        finally:
            server.close()
        # A run that fails still writes its manifest, so it's complete, and can be reviewed.
        assert (out / "manifest.json").is_file(), outcome.stderr
        return out

    def review(self, name: str, directory: Path) -> Path:
        """Copies the review configuration `name` into `directory`, writes or copies each run it
        names at its `run` path, and returns the configuration's path."""
        directory.mkdir(parents=True, exist_ok=True)
        path = Path(shutil.copy(REVIEW_CONFIGS / name, directory / name))
        for run_path, run in RUNS[name].items():
            if isinstance(run, Path):
                shutil.copytree(run, directory / run_path)
            else:
                self.run(run, directory / run_path)
        return path
