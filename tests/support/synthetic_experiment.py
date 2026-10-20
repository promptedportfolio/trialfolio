"""The synthetic writer (releases 0.3.0 and 0.4.0, test pairing): writes the committed synthetic
fixtures that no `trialfolio` command writes, through the core, with the demo's client, which
sends nothing, and the fixed clock.

- **The synthetic experiment.** It plans `experiment-configs/synthetic.yaml`, executes it with the
  demo's client, then revises it with `synthetic-revised.yaml` and the reason
  `Adds a holdings variant.`, and executes that. So the experiment has two plans and two sessions,
  each with its report and manifest, and every case succeeded. Its manifests and reports label it
  synthetic. R03-T11 wrote it, and committed its output once, as
  `experiments/synthetic-experiment-1.0.0/`, the historical fixture for 0.3.0's schemas, with

      uv run python -m tests.support.synthetic_experiment tests/fixtures/experiments/synthetic-experiment-1.0.0

- **Release 0.4.0's, with a ranking definition.** R04-T13 added them, each the historical fixture
  of the schema versions its name gives, and written with the argument beside it:
  - `runs/synthetic-run-1.1.0/`, a screen run of `screen-configs/synthetic-definition.yaml`,
    ranked by `experiment-configs/ranking/synthetic.xml`: `run-1.1.0`.
  - `experiments/synthetic-experiment-1.1.0/`, from `experiment-configs/ranking-synthetic.yaml`,
    then its revision, `ranking-synthetic-revised.yaml`, with the reason
    `Adds a removal variant.`: `experiment-1.1.0`.
  - `snapshots/synthetic-snapshot-1.0.0/`, a ranking snapshot of
    `ranking-snapshot-configs/example.yaml`, whose `rank_get` the demo's client answers with the
    invented system `responses/rank-get.json`: `snapshot-1.0.0`.
  - `reviews/synthetic-ranking-review-1.0.0/`, `trialfolio review` of
    `review-configs/synthetic-ranking.yaml`, which declares `ranking`, over a copy of the
    committed `runs/synthetic-run-1.1.0/` and a synthetic run of
    `screen-configs/synthetic-heavy.yaml`, ranked by `synthetic-heavy.xml`, which the writer
    writes: `review-1.0.0`. A review sends nothing, so it runs through the CLI's entry function,
    as `trialfolio review` wrote 0.2.0's review, with the license acknowledged by
    `TRIALFOLIO_ACCEPT_LICENSE` under a temporary home.

  The runs and the experiment take the ranking lock, as every execution with a definition does,
  on a file in a temporary directory of their own, never the machine's. A snapshot takes no lock.
  Each was committed once, with

      uv run python -m tests.support.synthetic_experiment <argument> <out>

None is a double: each is the core's real output, or the CLI's. A fixture changes only with a
stated reason, so the writer runs again only for one. The check of the reports,
`tests/support/rewritten_fixtures.py`, writes each again too.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Final
from unittest import mock

from tests.support.clock import FixedClock
from trialfolio.configuration import (
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
    read_ranking_snapshot_configuration,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.execution import Execution
from trialfolio.experiment_execution import ExperimentExecution
from trialfolio.experiment_records import open_experiment
from trialfolio.planning import (
    build_experiment_plan,
    build_experiment_plan_v1_1,
    build_plan_v1_1,
    build_snapshot_plan,
    installed_versions,
    plan_revision,
    plan_revision_v1_1,
)
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.snapshot_execution import SnapshotExecution
from trialfolio.storage import LocalArtifactStore

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures"
EXPERIMENT_CONFIGS: Final = FIXTURES / "experiment-configs"
SCREEN_CONFIGS: Final = FIXTURES / "screen-configs"
SNAPSHOT_CONFIGS: Final = FIXTURES / "ranking-snapshot-configs"
REVIEW_CONFIGS: Final = FIXTURES / "review-configs"
RESPONSES: Final = FIXTURES / "responses"

SYNTHETIC_EXPERIMENT: Final = FIXTURES / "experiments" / "synthetic-experiment-1.0.0"
"""The committed synthetic experiment, which this writer wrote."""

FIRST: Final = EXPERIMENT_CONFIGS / "synthetic.yaml"
REVISED: Final = EXPERIMENT_CONFIGS / "synthetic-revised.yaml"
REASON: Final = "Adds a holdings variant."
"""The reason the writer gives for the revision."""

SYNTHETIC_RUN_WITH_DEFINITION: Final = FIXTURES / "runs" / "synthetic-run-1.1.0"
SYNTHETIC_EXPERIMENT_WITH_DEFINITION: Final = (
    FIXTURES / "experiments" / "synthetic-experiment-1.1.0"
)
SYNTHETIC_RANKING_REVIEW: Final = FIXTURES / "reviews" / "synthetic-ranking-review-1.0.0"
SYNTHETIC_SNAPSHOT: Final = FIXTURES / "snapshots" / "synthetic-snapshot-1.0.0"
"""The committed synthetic fixtures of release 0.4.0, which this writer wrote."""

RUN_CONFIGURATION: Final = SCREEN_CONFIGS / "synthetic-definition.yaml"
HEAVY_CONFIGURATION: Final = SCREEN_CONFIGS / "synthetic-heavy.yaml"
RANKING_FIRST: Final = EXPERIMENT_CONFIGS / "ranking-synthetic.yaml"
RANKING_REVISED: Final = EXPERIMENT_CONFIGS / "ranking-synthetic-revised.yaml"
RANKING_REASON: Final = "Adds a removal variant."
"""The reason the writer gives for the revision of the experiment with a ranking definition."""
SNAPSHOT_CONFIGURATION: Final = SNAPSHOT_CONFIGS / "example.yaml"
SYSTEM: Final = RESPONSES / "rank-get.json"
"""The invented system the demo's client answers the snapshot's `rank_get` with."""
REVIEW_CONFIGURATION: Final = REVIEW_CONFIGS / "synthetic-ranking.yaml"
"""The ranking review's configuration, which names the committed run at `runs/synthetic`, and the
run of `synthetic-heavy.yaml` at `runs/synthetic-heavy`."""


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


def write_synthetic_run(
    out: Path,
    configuration: Path = RUN_CONFIGURATION,
    clock: Callable[[], datetime] | None = None,
) -> None:
    """Writes a synthetic screen run of `configuration`, a screen configuration 1.1.0 ranked by a
    definition, into `out`, a new or empty directory, with a new `FixedClock` unless given. Its
    manifest gives `synthetic` true, `command` null, and the approval `not_required`."""
    content = configuration.read_bytes()
    read = read_screen_configuration_v1_1(content, configuration.name, configuration)
    plan = build_plan_v1_1(read, installed_versions())
    if not isinstance(plan, PlanV1_2) or read.definition is None:
        raise AssertionError(f"{configuration.name} must be ranked by a definition")
    with tempfile.TemporaryDirectory() as locks, LocalArtifactStore(out) as store:
        error = Execution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            None,
            clock=FixedClock() if clock is None else clock,
            ranking_lock=Path(locks) / LOCK_FILE,
        ).run(
            content,
            lambda: SyntheticScreenBacktestClient(response_bytes()),
            definition=read.definition.content,
        )
    if error is not None:
        raise error


def write_synthetic_ranking_experiment(
    out: Path, clock: Callable[[], datetime] | None = None
) -> None:
    """Writes the synthetic experiment with a ranking definition into `out`, a new or empty
    directory: `ranking-synthetic.yaml`'s plan, then its revision. One clock, a new `FixedClock`
    unless given, serves both sessions, so the second's times follow the first's."""
    clock = FixedClock() if clock is None else clock
    versions = installed_versions()
    with tempfile.TemporaryDirectory() as locks:
        lock = Path(locks) / LOCK_FILE
        first = RANKING_FIRST.read_bytes()
        read = read_experiment_configuration_v1_1(first, RANKING_FIRST.name, RANKING_FIRST)
        plan = build_experiment_plan_v1_1(read, versions)
        if not isinstance(plan, PlanV1_3) or read.definition is None:
            raise AssertionError("ranking-synthetic.yaml must be ranked by a definition")
        client = SyntheticScreenBacktestClient(response_bytes())
        try:
            with LocalArtifactStore(out) as store:
                error = ExperimentExecution(
                    plan,
                    plan.plan_hash,
                    "not_required",
                    store,
                    client,
                    command=None,
                    clock=clock,
                    ranking_lock=lock,
                ).run(first, definition=read.definition.content)
        finally:
            client.close()
        if error is not None:
            raise error

        revised = RANKING_REVISED.read_bytes()
        read = read_experiment_configuration_v1_1(revised, RANKING_REVISED.name, RANKING_REVISED)
        if read.definition is None:
            raise AssertionError("ranking-synthetic-revised.yaml must be ranked by a definition")
        client = SyntheticScreenBacktestClient(response_bytes())
        try:
            with LocalArtifactStore(out) as store:
                saved = open_experiment(store, ranking=True)
                revision = plan_revision_v1_1(read, versions, saved.current.plan)
                if revision is None:
                    raise AssertionError(
                        "ranking-synthetic-revised.yaml must revise ranking-synthetic.yaml's plan"
                    )
                error = ExperimentExecution(
                    revision.plan,
                    revision.plan.plan_hash,
                    "not_required",
                    store,
                    client,
                    command=None,
                    clock=clock,
                    experiment=saved,
                    reason=RANKING_REASON,
                    ranking_lock=lock,
                ).run(revised, definition=read.definition.content)
        finally:
            client.close()
        if error is not None:
            raise error


def write_synthetic_snapshot(out: Path, clock: Callable[[], datetime] | None = None) -> None:
    """Writes the synthetic ranking snapshot into `out`, a new or empty directory, with a new
    `FixedClock` unless given: the demo's client answers its `rank_get` with `SYSTEM`. Its
    manifest gives `synthetic` true, `command` null, and the approval `not_required`, so no
    configuration can name it as its ranking."""
    content = SNAPSHOT_CONFIGURATION.read_bytes()
    plan = build_snapshot_plan(
        read_ranking_snapshot_configuration(content, SNAPSHOT_CONFIGURATION.name),
        installed_versions(),
    )
    system = SYSTEM.read_bytes()
    with LocalArtifactStore(out) as store:
        error = SnapshotExecution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            None,
            clock=FixedClock() if clock is None else clock,
        ).run(content, lambda: SyntheticScreenBacktestClient(response_bytes(), system=system))
    if error is not None:
        raise error


def write_synthetic_ranking_review(out: Path, inputs: Path, run: Path) -> None:
    """Writes the synthetic ranking review into `out`, a new or empty directory, with
    `trialfolio review`. `inputs`, a new or empty directory, gets a copy of the review's
    configuration; a copy of `run`, the synthetic run with a ranking definition, at
    `runs/synthetic`; and a synthetic run of `synthetic-heavy.yaml`, which this writes, at
    `runs/synthetic-heavy`. Each is written with a new `FixedClock`."""
    inputs.mkdir(parents=True, exist_ok=True)
    configuration = Path(shutil.copy(REVIEW_CONFIGURATION, inputs / REVIEW_CONFIGURATION.name))
    shutil.copytree(run, inputs / "runs" / "synthetic")
    write_synthetic_run(inputs / "runs" / "synthetic-heavy", HEAVY_CONFIGURATION)
    with tempfile.TemporaryDirectory() as home, _environment(Path(home)):
        _command("review", configuration, "--out", out)


@contextlib.contextmanager
def _environment(home: Path) -> Iterator[None]:
    """The environment of the tests' CLI, with the license acknowledged, and `home` as `HOME`."""
    from tests.support.environment import VARIABLES
    from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE

    saved = dict(os.environ)
    try:
        for name in VARIABLES:
            os.environ.pop(name, None)
        os.environ["HOME"] = str(home)
        os.environ[ACCEPT_VARIABLE] = ACCEPT_VALUE
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _command(*argv: str | Path) -> None:
    """Runs `trialfolio` with `argv` and a new fixed clock, and raises `AssertionError`, with what
    it wrote, unless it succeeds."""
    from trialfolio.cli import main

    out, err = io.StringIO(), io.StringIO()
    with (
        mock.patch.object(sys, "stdin", io.StringIO()),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = main([str(arg) for arg in argv], clock=FixedClock())
    if code != 0:
        raise AssertionError(
            f"trialfolio {' '.join(map(str, argv))} exited with {code}:\n"
            f"{out.getvalue()}{err.getvalue()}"
        )


_USAGE: Final = (
    "usage: python -m tests.support.synthetic_experiment <out>\n"
    "       python -m tests.support.synthetic_experiment"
    " {run-1.1.0,experiment-1.1.0,snapshot-1.0.0,review-1.0.0} <out>"
)


def main(argv: list[str]) -> int:
    match argv:
        case ["run-1.1.0", out]:
            write_synthetic_run(Path(out))
        case ["experiment-1.1.0", out]:
            write_synthetic_ranking_experiment(Path(out))
        case ["snapshot-1.0.0", out]:
            write_synthetic_snapshot(Path(out))
        case ["review-1.0.0", out]:
            with tempfile.TemporaryDirectory() as inputs:
                write_synthetic_ranking_review(
                    Path(out), Path(inputs), SYNTHETIC_RUN_WITH_DEFINITION
                )
        case [out]:
            write_synthetic_experiment(Path(out))
        case _:
            print(_USAGE, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
