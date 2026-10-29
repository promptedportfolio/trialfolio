"""The wheel the packaging tests check, built once for the session from the working tree, in a
temporary directory, so nothing lands in the tree (release 0.1.0, verification: `uv run pytest -m
packaging` runs on a wheel built from the working tree).

`uv build --offline` needs the build backend in uv's cache. `pyproject.toml` pins it exactly, and
`uv sync` has already cached it, so the build downloads nothing.

TS-T04 moved the helpers its tests import, the repository's root and `run_uv`, to
`tests/support/paths.py` and `tests/support/uv.py`, so this file keeps only the fixture.
"""

from pathlib import Path

import pytest

from tests.support.paths import ROOT
from tests.support.uv import run_uv


@pytest.fixture(scope="session")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The wheel built from the working tree, offline."""
    out = tmp_path_factory.mktemp("wheel")
    run_uv("build", "--wheel", "--offline", "--out-dir", out, cwd=ROOT)
    (built,) = out.glob("*.whl")
    return built
