"""Suite-wide setup: the network guard, here and in every Python subprocess (P-12)."""

import os
from collections.abc import Callable

import pytest
import trialfolio_network_guard as network_guard

_RESTORE = pytest.StashKey[Callable[[], None]]()


def pytest_configure(config: pytest.Config) -> None:
    # Before collection, so importing a test module is guarded too. A pytest run under another
    # one shares its guard, and leaves it on.
    installed = network_guard.install()
    env = pytest.MonkeyPatch()
    # Subprocesses inherit this, so their sitecustomize installs the guard.
    env.setenv("PYTHONPATH", network_guard.with_guard_path(os.environ)["PYTHONPATH"])
    # A proxy on localhost would relay a request to any host. So no inherited proxy setting
    # applies, and NO_PROXY also turns off macOS's system proxies. A test of proxy handling
    # removes NO_PROXY itself.
    for name in list(os.environ):
        if name.lower().endswith("_proxy"):
            env.delenv(name)
    env.setenv("NO_PROXY", "*")
    env.setenv("no_proxy", "*")

    def restore() -> None:
        env.undo()
        if installed:
            network_guard.uninstall()

    config.stash[_RESTORE] = restore


def pytest_unconfigure(config: pytest.Config) -> None:
    # Restores the environment and the socket module for a pytest run inside another process.
    restore = config.stash.get(_RESTORE, None)
    if restore is not None:
        restore()
