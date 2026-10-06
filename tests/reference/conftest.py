"""The owner's local reference data, which the reference tests read (release 0.1.0's and 0.2.0's
verification commands, `TRIALFOLIO_REFERENCE_DIR=reference uv run pytest -m reference`). It's
git-ignored (REQ-11), so without the variable, or without the data a test needs, the test skips
and says why. A test writes only in a temporary directory, never under the reference directory.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.support.fake_portfolio123 import FakePortfolio123

REFERENCE_DIR_VARIABLE = "TRIALFOLIO_REFERENCE_DIR"


@pytest.fixture
def reference_dir() -> Path:
    given = os.environ.get(REFERENCE_DIR_VARIABLE, "")
    if not given:
        pytest.skip(
            f"{REFERENCE_DIR_VARIABLE} isn't set: these tests read the owner's local reference "
            f"data, as `{REFERENCE_DIR_VARIABLE}=reference uv run pytest -m reference`"
        )
    directory = Path(given).resolve()
    if not directory.is_dir():
        pytest.skip(f"{REFERENCE_DIR_VARIABLE} names no directory: {given}")
    return directory


@pytest.fixture
def server() -> Iterator[FakePortfolio123]:
    fake = FakePortfolio123()
    yield fake
    fake.close()
