"""The live check: a real screen backtest with the owner's account succeeds within its budget, and
its output is archived locally and re-rendered offline.

Traces to R01-AC24, and to release 0.1.0's verification commands:
`TRIALFOLIO_LIVE_BUDGET_CREDITS=5 uv run pytest -m live`, with the credentials injected as
AGENTS.md describes. The marker keeps it out of the default suite and of `scripts/check`. It runs
only with the owner present, who grants its network access for this one command.

The test refuses to start, with a failure that says why, without both credentials, or with a
budget that's missing or below the plan's `credits`. A skip would let `pytest -m live` pass
without checking anything.

It runs the installed `trialfolio`, never the test launcher, with `formula.yaml`'s settings,
approved with `--approve` and the plan's hash, and with the default endpoint and timeout. The
network guard stays on: `TRIALFOLIO_TEST_NETWORK_ALLOW`, in that one subprocess's environment,
names the host of `p123api`'s own default endpoint, and the subprocess's guard removes it from its
environment, so nothing it starts inherits it. The run goes into a new directory under
`reference/p123api-live-check/payloads/`, which is git-ignored, and `trialfolio report` then
re-renders it under the full guard into a second new directory there. So nothing from the
response leaves a git-ignored folder. No assertion here shows anything from the response, only
outcomes, counts, codes, and the credits used.
"""

import inspect
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

import p123api
import pytest
import trialfolio_network_guard as network_guard

from tests.support.package_versions import installed_command
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE
from trialfolio.configuration import read_screen_configuration
from trialfolio.contracts.common import AUTHENTICATION_REQUEST
from trialfolio.planning import build_plan, installed_versions
from trialfolio.provider import REQUEST_TIMEOUT_SECONDS
from trialfolio.runs import read_run
from trialfolio.storage import LocalArtifactStore

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGURATION = REPO_ROOT / "tests" / "fixtures" / "screen-configs" / "formula.yaml"
PAYLOADS = REPO_ROOT / "reference" / "p123api-live-check" / "payloads"
"""Git-ignored, like every `payloads/` folder under `reference/` (REQ-11)."""
BUDGET_VARIABLE = "TRIALFOLIO_LIVE_BUDGET_CREDITS"
COMMAND_TIMEOUT_SECONDS = 2 * REQUEST_TIMEOUT_SECONDS
"""Room for authentication and the request, each under the client's own timeout."""


def refuse(reason: str) -> NoReturn:
    pytest.fail(f"The live check refuses to start: {reason}", pytrace=False)


def portfolio123_host() -> str:
    """The host of `p123api`'s default endpoint, which the installed command uses: no Trial Folio
    setting changes it."""
    default: object = inspect.signature(p123api.Client).parameters["endpoint"].default
    host = urlsplit(str(default)).hostname
    assert host, "p123api's Client has no default endpoint"
    return host


def trialfolio(*argv: str | Path, env: dict[str, str]) -> tuple[int, dict[str, Any]]:
    """Runs the installed command with `argv` and `--json`, with stdin closed. Returns its exit
    code and its JSON summary."""
    result = subprocess.run(
        [str(installed_command()), *(str(arg) for arg in argv), "--json"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env=env,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode == network_guard.REFUSED_EXIT_STATUS:
        pytest.fail("The network guard refused a connection: see the run's logs", pytrace=False)
    # Checked into a name of its own, so a failure doesn't show stdout.
    one_line = result.stdout.count("\n") == 1 and result.stdout.endswith("\n")
    assert one_line, "stdout isn't exactly one JSON summary"
    return result.returncode, json.loads(result.stdout)


def error_code(summary: dict[str, Any]) -> object:
    """The summary's error code. Never its message, which can hold Portfolio123's text."""
    error = summary["error"]
    return error["code"] if isinstance(error, dict) else None


def test_a_real_screen_backtest_succeeds_within_its_budget_and_rerenders_offline() -> None:
    # Before anything else, the test refuses to start without what it needs.
    missing = [name for name in (API_ID_VARIABLE, API_KEY_VARIABLE) if not os.environ.get(name)]
    if missing:
        refuse(f"set {' and '.join(missing)}, as AGENTS.md says, for this command only.")
    configuration = read_screen_configuration(CONFIGURATION.read_bytes(), str(CONFIGURATION))
    plan = build_plan(configuration, installed_versions())
    credits = plan.budget.credits
    given = os.environ.get(BUDGET_VARIABLE, "")
    if not (given.isascii() and given.isdecimal()):
        refuse(f"set {BUDGET_VARIABLE} to the approved budget in credits, at least {credits}.")
    budget = int(given)
    if budget < credits:
        refuse(f"the plan needs {credits} credits, and {BUDGET_VARIABLE} is {budget}.")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = PAYLOADS / f"run-{stamp}"
    report_dir = PAYLOADS / f"report-{stamp}"
    assert not run_dir.exists()
    assert not report_dir.exists()
    PAYLOADS.mkdir(parents=True, exist_ok=True)
    # The owner, who runs the check, acknowledges the license for these two processes only.
    environment = {**os.environ, ACCEPT_VARIABLE: ACCEPT_VALUE}

    # The run: the only process that may reach Portfolio123.
    exit_code, summary = trialfolio(
        "run",
        CONFIGURATION,
        "--out",
        run_dir,
        "--approve",
        plan.plan_hash,
        env={**environment, network_guard.ALLOW_ENV: portfolio123_host()},
    )

    code = error_code(summary)
    assert exit_code == 0, f"trialfolio run failed with {code}; its records are in {run_dir}"
    assert summary["outcome"] == "completed"
    assert summary["ids"]["plan_hash"] == plan.plan_hash
    counts = summary["counts"]
    assert counts["attempts"] == 1
    assert counts["provider_requests"] == 1
    cost = counts["cost"]
    assert isinstance(cost, int), "Portfolio123 reported no cost"
    assert cost <= budget, f"the request used {cost} credits, over the budget of {budget}"
    run = read_run(LocalArtifactStore(str(run_dir)))
    assert run.manifest.synthetic is False
    assert run.manifest.approval == "option"
    (attempt,) = run.attempts
    assert attempt.status.outcome == "succeeded"
    assert attempt.status.possibly_charged is True
    assert attempt.status.provider_requests == 1
    assert attempt.record is not None
    exchanges = [(e.request, e.result, e.status) for e in attempt.record.exchanges]
    assert exchanges == [
        (AUTHENTICATION_REQUEST, "response", 200),
        ("POST /screen/backtest", "response", 200),
    ]
    assert run.metrics is not None
    assert run.settings is not None

    # The re-render, under the full guard: localhost only. It sends nothing, so it gets no
    # credentials.
    offline = {
        name: value
        for name, value in environment.items()
        if name not in (API_ID_VARIABLE, API_KEY_VARIABLE)
    }
    exit_code, summary = trialfolio("report", run_dir, "--out", report_dir, env=offline)

    code = error_code(summary)
    assert exit_code == 0, f"trialfolio report failed with {code}"
    assert summary["outcome"] == "completed"
    assert (report_dir / "report.html").is_file()
