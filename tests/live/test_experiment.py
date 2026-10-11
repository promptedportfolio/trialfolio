"""The live experiment: a real experiment of two cases with the owner's account succeeds within its
budget, with one authentication call for both requests, and resumes offline.

Traces to R03-AC12, and to release 0.3.0's verification commands:
`TRIALFOLIO_LIVE_BUDGET_CREDITS=10 uv run pytest -m live tests/live/test_experiment.py`, with the
credentials injected as AGENTS.md describes. The marker keeps it out of the default suite and of
`scripts/check`. It runs only with the owner present, who grants its network access for this one
command.

The test refuses to start, with a failure that says why, when the command selects another live
check, without both credentials, or with a budget that's missing or below the plan's `credits`,
as 0.1.0's live check does. Each live check reads the whole budget, so it runs alone.

The experiment is `default-only.yaml`'s: the documented example's baseline, ranked by a formula,
and the default variant, `rebalance-weeks-1`. Its two requests are those R01-T01 and R01-T05
verified, and its budget is 2 provider requests, 10 credits at the documented cost. The installed
`trialfolio run` runs it with `--approve` and the plan's hash, into a new directory under
`reference/experiment-live-check/payloads/`, which is git-ignored, with the default endpoint and
timeout. As in 0.1.0's live check, only that process may reach Portfolio123's API host, besides
localhost. Then the same command runs again under the full guard, without credentials, so it
can't send anything: it resumes, finds no case due, and writes `sessions/2/` from the records
alone. Nothing from the responses leaves the git-ignored folder: no assertion shows anything from
them, only outcomes, counts, codes, and the credits used. So what the records say is read out as
plain values before it's checked: a failing assertion shows its operands, and the records'
representations hold the responses' bytes, and values read from them.

Before and after the test, the owner notes the account's ranking systems in the Portfolio123
website. If one changed, a formula ranking updates a shared object, and 0.3.0 needs the
per-account lock (docs/contracts.md, the lock). The test can't compare them: Trial Folio reads no
list of the account's ranking systems. The run record, `reference/experiment-live-check/README.md`,
gives what the owner found.
"""

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
import trialfolio_network_guard as network_guard

from tests.live.test_screen_backtest import (
    error_code,
    portfolio123_host,
    refuse,
    refuse_beside_another,
    trialfolio,
)
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.common import AUTHENTICATION_REQUEST
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.experiment_records import read_experiment
from trialfolio.planning import build_experiment_plan, installed_versions
from trialfolio.storage import LocalArtifactStore

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIGURATION = REPO_ROOT / "tests" / "fixtures" / "experiment-configs" / "default-only.yaml"
PAYLOADS = REPO_ROOT / "reference" / "experiment-live-check" / "payloads"
"""Git-ignored, like every `payloads/` folder under `reference/` (REQ-11)."""
BUDGET_VARIABLE = "TRIALFOLIO_LIVE_BUDGET_CREDITS"
BACKTEST_REQUEST = "POST /screen/backtest"


def test_a_real_experiment_authenticates_once_within_its_budget_and_resumes_offline(
    request: pytest.FixtureRequest,
) -> None:
    # Before anything else, the test refuses to start without what it needs.
    refuse_beside_another(request)
    missing = [name for name in (API_ID_VARIABLE, API_KEY_VARIABLE) if not os.environ.get(name)]
    if missing:
        refuse(f"set {' and '.join(missing)}, as AGENTS.md says, for this command only.")
    configuration = read_experiment_configuration(CONFIGURATION.read_bytes(), str(CONFIGURATION))
    plan = build_experiment_plan(configuration, installed_versions())
    credits = plan.budget.credits
    given = os.environ.get(BUDGET_VARIABLE, "")
    if not (given.isascii() and given.isdecimal()):
        refuse(f"set {BUDGET_VARIABLE} to the approved budget in credits, at least {credits}.")
    budget = int(given)
    if budget < credits:
        refuse(f"the plan needs {credits} credits, and {BUDGET_VARIABLE} is {budget}.")
    assert [case.case_key for case in plan.cases] == ["baseline", "rebalance-weeks-1"]
    assert plan.budget.provider_requests == 2

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = PAYLOADS / f"experiment-{stamp}"
    assert not out.exists()
    PAYLOADS.mkdir(parents=True, exist_ok=True)
    # The owner, who runs the check, acknowledges the license for these two processes only.
    environment = {**os.environ, ACCEPT_VARIABLE: ACCEPT_VALUE}
    command = ("run", CONFIGURATION, "--out", out, "--approve", plan.plan_hash)

    # The run: the only process that may reach Portfolio123.
    exit_code, summary = trialfolio(
        *command, env={**environment, network_guard.ALLOW_ENV: portfolio123_host()}
    )

    code = error_code(summary)
    assert exit_code == 0, f"trialfolio run failed with {code}; its records are in {out}"
    assert summary["outcome"] == "completed"
    assert summary["ids"] == {
        "experiment_id": configuration.experiment_id,
        "plan_hash": plan.plan_hash,
        "session": 1,
    }
    assert [(case["case_key"], case["outcome"]) for case in summary["cases"]] == [
        ("baseline", "succeeded"),
        ("rebalance-weeks-1", "succeeded"),
    ]
    counts = summary["counts"]
    assert (counts["cases_succeeded"], counts["attempts"]) == (2, 2)
    assert (counts["provider_requests"], counts["authentication_calls"]) == (2, 1)
    cost = counts["cost"]
    assert isinstance(cost, int), "Portfolio123 reported no cost"
    assert cost <= budget, f"the requests used {cost} credits, over the budget of {budget}"
    with LocalArtifactStore(str(out)) as store:
        experiment = read_experiment(store)
    # Plain values, read out of the records before they're checked, as the docstring says: the
    # representation of the experiment, a manifest, an attempt, or a record holds the responses.
    saved_manifest = experiment.manifest
    provenance = (
        None if saved_manifest is None else (saved_manifest.synthetic, saved_manifest.approval)
    )
    attempts = [
        (
            attempt.case_id,
            attempt.session,
            attempt.sequence,
            attempt.outcome,
            attempt.possibly_charged,
            attempt.provider_requests,
            attempt.case_id in experiment.tables,
        )
        for attempt in experiment.attempts
    ]
    attempt_ids = [attempt.attempt_id for attempt in experiment.attempts]
    # Whether each attempt authenticated, its exchanges, and the attempt whose token it sent.
    authentication = [
        (
            attempt.authentication is not None,
            None
            if attempt.record is None
            else [(e.request, e.result, e.status) for e in attempt.record.exchanges],
            None if attempt.record is None else attempt.record.authenticated_by,
        )
        for attempt in experiment.attempts
    ]
    assert provenance == (False, "option")
    assert attempts == [
        (case.case_id, 1, sequence, "succeeded", True, 1, True)
        for sequence, case in enumerate(plan.cases, start=1)
    ]
    # One POST /auth, before the first case, whose token the second case's request was sent with.
    first_id = attempt_ids[0]
    assert authentication == [
        (
            True,
            [(AUTHENTICATION_REQUEST, "response", 200), (BACKTEST_REQUEST, "response", 200)],
            first_id,
        ),
        (False, [(BACKTEST_REQUEST, "response", 200)], first_id),
    ]

    # The resume, under the full guard: localhost only, and no credentials, so nothing can be sent.
    offline = {
        name: value
        for name, value in environment.items()
        if name not in (API_ID_VARIABLE, API_KEY_VARIABLE)
    }
    exit_code, summary = trialfolio(*command, env=offline)

    code = error_code(summary)
    assert exit_code == 0, f"the resume failed with {code}; its records are in {out}"
    assert summary["outcome"] == "completed"
    assert summary["ids"]["session"] == 2
    counts = summary["counts"]
    assert (counts["attempts"], counts["provider_requests"]) == (2, 2)
    assert counts["authentication_calls"] == 1
    manifest = ExperimentManifest.model_validate_json(
        (out / "sessions" / "2" / "manifest.json").read_bytes()
    )
    ended = (manifest.outcome, manifest.counts.cases.succeeded)
    assert ended == ("completed", 2)
    assert (out / "sessions" / "2" / "report.html").is_file()
    with LocalArtifactStore(str(out)) as store:
        resumed = read_experiment(store)
    resumed_ids = [attempt.attempt_id for attempt in resumed.attempts]
    assert resumed_ids == attempt_ids
