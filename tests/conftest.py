"""Suite-wide setup: the network guard, here and in every Python subprocess (P-12)."""

import os
from pathlib import Path

import pytest

from tests.support import network_guard

GUARDED_SITE = Path(__file__).parent / "support" / "guarded_site"


def pytest_configure(config: pytest.Config) -> None:
    # Before collection, so importing a test module is guarded too.
    network_guard.install()
    # Subprocesses inherit this, so their sitecustomize installs the guard. A test that sets its
    # own PYTHONPATH for a subprocess must keep this directory first.
    inherited = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(GUARDED_SITE), inherited]))
