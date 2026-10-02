"""The network guard's pytest plugin: the guard in the test process, and in every Python
subprocess it starts (P-12).

pyproject.toml's addopts loads it with -p, so pytest imports it before any conftest or installed
plugin, and the repository's root conftest loads it for a run without those addopts. pytest then
reports every refusal, wherever the test is.
"""

import os
import sys
import threading
from collections.abc import Callable, Generator

import pytest
import trialfolio_network_guard as network_guard

_RESTORE = pytest.StashKey[Callable[[], None]]()


def _allowance() -> bool:
    return bool(network_guard.allowed_hosts()) or network_guard.ALLOW_ENV in os.environ


def _guard() -> Callable[[], None]:
    """Guard this process and the subprocesses it starts. Returns what undoes it."""
    # A pytest run under another one shares its guard, which sitecustomize installed.
    installed = network_guard.install()
    # That guard would end the process after a refusal. Here the hooks below report refusals.
    exited = network_guard.exit_after_refusal(False)
    threads = set(threading.enumerate())
    env = pytest.MonkeyPatch()
    # Subprocesses inherit PYTHONPATH, so their sitecustomize installs the guard. A proxy on
    # localhost would relay a request to any host, so no proxy applies, inherited or the system's.
    guarded = network_guard.with_guard_path(network_guard.without_proxies(os.environ))
    for name in set(os.environ) - set(guarded):
        env.delenv(name)
    for name, value in guarded.items():
        if os.environ.get(name) != value:
            env.setenv(name, value)

    def restore() -> None:
        env.undo()
        if not installed:
            network_guard.exit_after_refusal(exited)
        elif set(threading.enumerate()) <= threads:
            network_guard.uninstall()  # For a pytest run inside another process.
        else:
            # A thread a test started may still be running. The guard stays, and the process
            # ends with REFUSED_EXIT_STATUS if anything is refused from now on.
            network_guard.exit_after_refusal(True)

    return restore


# Guarded as pytest imports this plugin, so that the conftests and plugins it imports later are
# guarded as they are imported.
_restore = None if _allowance() else _guard()


def pytest_configure(config: pytest.Config) -> None:
    global _restore
    # Only the live check's one subprocess may reach another host; the suite never may.
    if _allowance():
        raise pytest.UsageError(
            f"{network_guard.ALLOW_ENV} is set. The suite never runs with it: only the live"
            " check passes it, to its one `trialfolio run` subprocess."
        )
    # Another pytest run in this process doesn't import this plugin again.
    config.stash[_RESTORE] = _restore or _guard()
    _restore = None


def pytest_unconfigure(config: pytest.Config) -> None:
    restore = config.stash.get(_RESTORE, None)
    if restore is not None:
        restore()


def _fail_if_refused(report: pytest.CollectReport | pytest.TestReport) -> None:
    # pytest reports nothing for a refusal that was caught, or left in a future or a task nobody
    # read.
    refusals = network_guard.take_refusals()
    if refusals and report.passed:
        report.outcome = "failed"
        report.longrepr = "\n".join(
            [*refusals, "The refusal was caught, but it still fails the test."]
        )


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(
    collector: pytest.Collector,
) -> Generator[None, pytest.CollectReport, pytest.CollectReport]:
    report = yield
    _fail_if_refused(report)
    return report


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    _fail_if_refused(report)
    return report


def pytest_sessionfinish(session: pytest.Session) -> None:
    # Refused after the last report, such as in a thread a test left running.
    refusals = network_guard.take_refusals()
    if refusals:
        sys.stderr.write("\n".join([*refusals, ""]))
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
