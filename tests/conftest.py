"""The fixtures more than one directory of the tests uses: the fake Portfolio123 server, and the
runs a review reads.

A review's tests, in `tests/interface/` and `tests/core/`, read runs that the run builder writes,
once for each module, beside a copy of the review configuration that names them (`built`). A
review only reads them.

TS-T04 wrote each once, here: `server` from its nine copies, in three conftests and six core
modules, and `built` from its two, in the interface's conftest and `tests/core/test_review_report.py`.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.support.fake_portfolio123 import FakePortfolio123
from tests.support.run_builder import RunBuilder


@pytest.fixture
def server() -> Iterator[FakePortfolio123]:
    """The fake Portfolio123 server, with nothing scripted: a request it isn't told how to answer
    gets a 404. Closing it at the end of the test checks every request it received (R04-AC09)."""
    fake = FakePortfolio123()
    yield fake
    fake.close()


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
