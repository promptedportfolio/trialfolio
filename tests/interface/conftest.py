"""The interface tests' fixtures: the tests' CLI, `tests/support/cli.py`, which runs `trialfolio`
through its entry function in the test process, with doubles only at the boundaries the release
allows; the experiment builder over it; and storage faults. The fake Portfolio123 server, and the
runs a review reads (`built`), are `tests/conftest.py`'s.

An experiment's tests write their experiments with the experiment builder (`experiments`), through
this `Cli`, over the test's own server.

TS-T03 moved the helpers the tests import to modules under `tests/support/`, so this file keeps
only the fixtures.
"""

from pathlib import Path

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import ExperimentBuilder
from tests.support.fake_portfolio123 import FakePortfolio123
from tests.support.storage_faults import FaultyStores


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
