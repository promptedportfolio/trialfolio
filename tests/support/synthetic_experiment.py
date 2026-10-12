"""The synthetic experiment's writer (release 0.3.0, test pairing): writes a complete synthetic
experiment through the core, with the fixed clock. It plans `experiment-configs/synthetic.yaml`,
executes it with the demo's client, which sends nothing, then revises it with
`synthetic-revised.yaml` and the reason `Adds a holdings variant.`, and executes that. So the
experiment has two plans and two sessions, each with its report and manifest, and every case
succeeded. Its manifests and reports label it synthetic.

It isn't a double: the experiment is the core's real output. R03-T11 wrote it, and committed its
output once, as `experiments/synthetic-experiment-1.0.0/`, the historical fixture for 0.3.0's
schemas, with

    uv run python -m tests.support.synthetic_experiment tests/fixtures/experiments/synthetic-experiment-1.0.0

The fixture changes only with a stated reason, so the writer runs again only for one. No
`trialfolio` command writes a synthetic experiment, so only the tests use the core's synthetic path.
"""

import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Final

from tests.support.clock import FixedClock
from trialfolio.configuration import read_experiment_configuration
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.experiment_execution import ExperimentExecution
from trialfolio.experiment_records import open_experiment
from trialfolio.planning import build_experiment_plan, installed_versions, plan_revision
from trialfolio.storage import LocalArtifactStore

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures"
EXPERIMENT_CONFIGS: Final = FIXTURES / "experiment-configs"

SYNTHETIC_EXPERIMENT: Final = FIXTURES / "experiments" / "synthetic-experiment-1.0.0"
"""The committed synthetic experiment, which this writer wrote."""

FIRST: Final = EXPERIMENT_CONFIGS / "synthetic.yaml"
REVISED: Final = EXPERIMENT_CONFIGS / "synthetic-revised.yaml"
REASON: Final = "Adds a holdings variant."
"""The reason the writer gives for the revision."""


def write_synthetic_experiment(out: Path, clock: Callable[[], datetime] | None = None) -> None:
    """Writes the synthetic experiment into `out`, a new or empty directory. One clock, a new
    `FixedClock` unless given, serves both sessions, so the second's times follow the first's."""
    clock = FixedClock() if clock is None else clock
    first = FIRST.read_bytes()
    plan = build_experiment_plan(
        read_experiment_configuration(first, FIRST.name), installed_versions()
    )
    client = SyntheticScreenBacktestClient(response_bytes())
    try:
        with LocalArtifactStore(out) as store:
            error = ExperimentExecution(
                plan, plan.plan_hash, "not_required", store, client, command=None, clock=clock
            ).run(first)
    finally:
        client.close()
    if error is not None:
        raise error

    revised = REVISED.read_bytes()
    configuration = read_experiment_configuration(revised, REVISED.name)
    client = SyntheticScreenBacktestClient(response_bytes())
    try:
        with LocalArtifactStore(out) as store:
            saved = open_experiment(store)
            revision = plan_revision(configuration, installed_versions(), saved.plan)
            if revision is None:
                raise AssertionError("synthetic-revised.yaml must revise synthetic.yaml's plan")
            error = ExperimentExecution(
                revision.plan,
                revision.plan.plan_hash,
                "not_required",
                store,
                client,
                command=None,
                clock=clock,
                experiment=saved,
                reason=REASON,
            ).run(revised)
    finally:
        client.close()
    if error is not None:
        raise error


if __name__ == "__main__":
    write_synthetic_experiment(Path(sys.argv[1]))
