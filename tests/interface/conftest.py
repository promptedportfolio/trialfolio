"""The interface tests' fixtures: the fake Portfolio123 server; the tests' CLI, `tests/support/cli.py`,
which runs `trialfolio` through its entry function in the test process, with doubles only at the
boundaries the release allows; the experiment builder over it; and storage faults.

A review's tests read runs that the run builder writes, once for each module, beside a copy of the
review configuration that names them (`built`). A review only reads them. An experiment's tests
write their experiments with the experiment builder (`experiments`), through this `Cli`, over the
test's own server.

TS-T03 moved the helpers the tests import to modules under `tests/support/`, so this file keeps
only the fixtures.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import ExperimentBuilder
from tests.support.fake_portfolio123 import FakePortfolio123
from tests.support.run_builder import RunBuilder
from tests.support.storage_faults import FaultyStores


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
def experiments(cli: Cli, server: FakePortfolio123) -> ExperimentBuilder[Outcome]:
    """The experiment builder, running `trialfolio run` through `cli`, over `server`."""
    return ExperimentBuilder(server, cli)


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> FaultyStores:
    return FaultyStores(monkeypatch)


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Path]:
    """Builds the runs a review configuration in `review-configs/` names, once for the module,
    beside a copy of it, and gives the copy's path. A test must leave the runs as they are."""
    root = tmp_path_factory.mktemp("runs")
    paths: dict[str, Path] = {}
    builder = RunBuilder(root / "home")

    def get(name: str) -> Path:
        if name not in paths:
            paths[name] = builder.review(name, root / name.removesuffix(".yaml"))
        return paths[name]

    return get
