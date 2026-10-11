"""`trialfolio run` with an experiment's configuration, which it chooses by its `kind`: the plan
display and the approval; the first plan's `experiment.json`; the summary on stdout; and the
output directories an experiment runs into.

Traces to R03-AC01's interface part (every case is shown with its `case_id` before any request,
and without a terminal only the plan hash and the budget are), R03-AC03's (the first plan's
`experiment.json`), and to docs/contracts.md, running an experiment (the directory a resume takes
the lock of, the installed versions, which a resume checks once it holds the lock and before it
reads the records, a synthetic experiment, which `run` doesn't resume, and the credentials a
resume needs only when it sends) and CLI behavior (the summary on stdout). Through the CLI's entry
function in the test process, with the real client, `requests`, and `urllib3` over the fake
server. The terminal is a real pseudo-terminal in the test process, except for R03-AC01's check
that nothing is sent until `approve` is typed, which runs the command under the test launcher, in
its own process.
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, Outcome, occupied, snapshot
from tests.support import canaries
from tests.support.clock import FixedClock
from tests.support.experiment_builder import (
    AUTHENTICATED,
    REFUSED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.package_versions import fake_distribution
from tests.support.terminal import PseudoTerminal
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.experiment_execution import ExperimentExecution
from trialfolio.planning import build_experiment_plan, installed_versions
from trialfolio.storage import LocalArtifactStore

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

EXAMPLE = experiment_config("example.yaml")
RECORD_SCHEMA = (
    Path(__file__).resolve().parents[2] / "schemas" / "experiment-record-1.0.0.schema.json"
)

type Builder = ExperimentBuilder[Outcome]


def plan_of(path: Path) -> PlanV1_1:
    """The plan of a new experiment of the configuration at `path`, with the installed versions."""
    configuration = read_experiment_configuration(path.read_bytes(), str(path))
    return build_experiment_plan(configuration, installed_versions())


def complete() -> list[Reply]:
    """A 200 with `complete.json` for each of `example.yaml`'s five cases."""
    return [returns() for _ in range(5)]


def error_code(outcome: Outcome) -> str:
    return cast("dict[str, str]", outcome.summary["error"])["code"]


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# The plan display and the approval (R03-AC01)


@posix_only
def test_under_a_terminal_every_case_is_shown_before_the_prompt_and_nothing_is_sent_first(
    cli: Cli,
) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", *complete())
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)

    with cli.on_terminal("run", EXAMPLE, "--out", out, "--json") as terminal:
        terminal.wait_for("Type approve")
        shown = terminal.shown()
        received_before = cli.server.requests()
        terminal.press("approve\n")
        exit_code = terminal.wait()

    assert received_before == []
    prompt = shown.index("Type approve to run this plan")
    changes = [
        "the baseline",
        "replaces the rule AvgDailyTot(30) > 1000000 with AvgDailyTot(30) > 100000000",
        "max_holdings set to 50",
        "rebalance_weeks set to 1, the default rebalance variant",
        "slippage_percent set to 0.5",
    ]
    for case, change in zip(plan.cases, changes, strict=True):
        line = f"Case {case.case_key} ({case.case_id}): {change}"
        assert line in shown
        assert shown.index(line) < prompt
    assert "Description: A stricter liquidity floor, 100 million dollars a day." in shown
    # Each case's request, exactly as it will be sent.
    for sent in ('"maxNumHoldings": 50', '"rebalFreq": "Every Week"', '"slippage": 0.5'):
        assert shown.index(sent) < prompt
    assert '"formula": "AvgDailyTot(30) > 100000000"' in shown
    assert "Budget: at most 6 provider requests, each sent at most once: 30 credits" in shown
    assert "At most 6 authentication calls" in shown
    assert f"Plan hash: {plan.plan_hash}" in shown
    assert exit_code == 0, shown
    assert cli.server.requests() == ["POST /auth", *["POST /screen/backtest"] * 5]


def test_without_a_terminal_only_the_hash_and_the_budget_are_shown(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    path = experiment_config("canaries.yaml")

    outcome = cli("run", path, "--out", out, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome) == "plan.approval_required"
    assert f"Plan hash: {plan_of(path).plan_hash}" in outcome.stderr
    assert "Budget: at most 6 provider requests" in outcome.stderr
    assert "Run the command in a terminal to see the full plan." in outcome.stderr
    for canary in canaries.EXPERIMENT:
        assert canary not in outcome.stderr
    assert not out.exists()
    assert cli.server.requests() == []


def test_without_approval_the_summary_gives_the_plan_hash_and_every_case(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)

    outcome = cli("run", EXAMPLE, "--out", out, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome) == "plan.approval_required"
    assert f"--approve {plan.plan_hash}" in outcome.stderr
    summary = outcome.summary
    assert summary["ids"] == {"experiment_id": "earnyield-sensitivity", "plan_hash": plan.plan_hash}
    assert summary["cases"] == [
        {
            "case_key": case.case_key,
            "case_id": case.case_id,
            "outcome": "not_yet_run",
            "repeat_attempt_id": None,
        }
        for case in plan.cases
    ]
    assert summary["output_dir"] is None
    assert not out.exists()
    assert cli.server.requests() == []


def test_a_hash_that_isnt_the_plans_is_refused(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = cli("run", EXAMPLE, "--out", out, "--approve", "sha256:" + "0" * 64, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome) == "plan.approval_required"
    assert "isn't this plan's hash" in outcome.stderr
    assert not out.exists()
    assert cli.server.requests() == []


@posix_only
def test_typing_approve_runs_the_plan_shown_and_is_recorded_as_interactive(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", *complete())
    out = cli.tmp / "experiment"

    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        outcome = cli(
            "run", EXAMPLE, "--out", out, "--json", stdin=terminal.stdin, stderr=terminal.stderr
        )
    shown = terminal.shown()

    assert outcome.exit_code == 0, shown
    manifest = ExperimentManifest.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    assert manifest.approval == "interactive"
    assert manifest.plan_hash == plan_of(EXAMPLE).plan_hash
    record = ExperimentRecord.model_validate_json((out / "plans/1/experiment.json").read_bytes())
    assert record.plans[0].approval == "interactive"


# The first plan's experiment.json (R03-AC03)


def test_the_first_plan_records_the_research_context_and_every_planned_case(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)

    outcome = experiments.run(EXAMPLE, out, sends=complete())

    assert outcome.exit_code == 0, outcome.stderr
    data = (out / "plans/1/experiment.json").read_bytes()
    record = ExperimentRecord.model_validate_json(data)
    schema = json.loads(RECORD_SCHEMA.read_bytes())
    loaded = json.loads(data)
    assert set(schema["required"]) <= set(loaded) <= set(schema["properties"])
    configuration = read_experiment_configuration(EXAMPLE.read_bytes(), "example.yaml")
    assert record.experiment_id == configuration.experiment_id == "earnyield-sensitivity"
    assert record.title == configuration.title
    assert record.purpose == configuration.purpose
    assert record.prior_research.status == "partial"
    assert record.prior_research.description == configuration.prior_research.description
    assert [
        (case.case_key, case.case_id, case.description, case.variant)
        for case in record.planned_cases
    ] == [(case.case_key, case.case_id, case.description, case.variant) for case in plan.cases]
    assert record.retired_cases == ()
    (entry,) = record.plans
    assert (entry.plan, entry.plan_hash, entry.revises) == (1, plan.plan_hash, None)
    assert entry.plan_artifact_id == sha256(out / "plans/1/plan.json")
    assert entry.configuration_artifact_id == sha256(out / "plans/1/configuration.yaml")
    assert (entry.approval, entry.reason, entry.changes) == ("option", None, None)
    # It records no outcome: the attempts' records do, and the manifest counts them.
    assert b'"outcome"' not in data
    manifest = ExperimentManifest.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    assert manifest.command is not None
    assert manifest.command.options == {
        "approve": plan.plan_hash,
        "json": True,
        "revision_reason": False,
        "repeat": False,
    }


# The summary on stdout


def test_a_completed_experiment_prints_where_its_report_is(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", *complete())
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)

    outcome = cli("run", EXAMPLE, "--out", out, "--approve", plan.plan_hash)

    assert outcome.exit_code == 0, outcome.stderr
    assert outcome.stdout.splitlines() == [
        f"Experiment completed: {out}",
        "Session 1: every one of the 5 planned cases succeeded.",
        f"Report: {out / 'sessions/1/report.html'}",
        f"Plan hash: {plan.plan_hash}",
        "Statistical validation and trading readiness: not assessed.",
    ]


def test_a_partial_experiment_prints_nothing_on_stdout_and_says_where_its_records_are(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    replies = [returns(), returns(), UNAVAILABLE, returns(), returns()]
    plan = plan_of(EXAMPLE)
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", *replies)

    outcome = cli("run", EXAMPLE, "--out", out, "--approve", plan.plan_hash)

    assert outcome.exit_code == 6
    assert outcome.stdout == ""
    assert "Error (execution.partial): 1 of the 5 planned cases didn't succeed" in outcome.stderr
    assert f"The experiment's records are in {out}." in outcome.stderr


# The output directory and the credentials


def test_a_directory_that_isnt_an_experiments_is_refused_as_for_a_screen(cli: Cli) -> None:
    cli.ready()
    out = occupied(cli, "notes.txt")
    before = snapshot(out)

    outcome = cli("run", EXAMPLE, "--out", out, "--approve", plan_of(EXAMPLE).plan_hash, "--json")

    assert outcome.exit_code == 4
    assert error_code(outcome) == "output.not_empty"
    assert "The output directory isn't empty." in outcome.stderr
    assert snapshot(out) == before
    # The configuration is valid, so its counts are known: no case has run. No plan was built.
    counts = cast("dict[str, int]", outcome.summary["counts"])
    assert (counts["cases_planned"], counts["cases_not_yet_run"], counts["attempts"]) == (5, 5, 0)
    assert "cases" not in outcome.summary
    assert cli.server.requests() == []


def test_an_output_path_that_is_a_file_is_refused(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    out.write_bytes(b"a file\n")

    outcome = cli("run", EXAMPLE, "--out", out, "--approve", plan_of(EXAMPLE).plan_hash, "--json")

    assert outcome.exit_code == 4
    assert error_code(outcome) == "output.not_empty"
    assert "The output path exists and isn't a directory." in outcome.stderr
    assert out.read_bytes() == b"a file\n"


@pytest.mark.parametrize("held", [False, True], ids=["records-broken", "lock-held"])
def test_a_resume_checks_the_versions_once_it_holds_the_lock_and_before_the_records(
    cli: Cli, experiments: Builder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, held: bool
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=complete()).exit_code == 0
    # A record the latest manifest lists is gone, which the records check would refuse.
    (out / "sessions/1/report.html").unlink()
    # Neither run gets as far as the approval.
    approve = "sha256:" + "0" * 64
    unverified = tmp_path / "unverified"
    unverified.mkdir()
    fake_distribution(unverified, "p123api", "3.2.0")
    monkeypatch.syspath_prepend(unverified)
    holder = LocalArtifactStore(out)
    if held:
        holder.lock("experiment.lock")
    try:
        outcome = cli("run", EXAMPLE, "--out", out, "--approve", approve, "--json")
    finally:
        holder.close()

    expected = "experiment.locked" if held else "environment.unsupported"
    assert error_code(outcome) == expected
    assert outcome.summary["counts"] == {}
    assert cli.server.requests()[5 + 1 :] == []


def test_a_resume_that_sends_nothing_needs_no_credentials(
    cli: Cli, experiments: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=complete()).exit_code == 0
    monkeypatch.delenv(API_ID_VARIABLE)
    monkeypatch.delenv(API_KEY_VARIABLE)
    received = len(cli.server.received)

    outcome = experiments.run(EXAMPLE, out)

    assert outcome.exit_code == 0, outcome.stderr
    assert len(cli.server.received) == received
    manifest = ExperimentManifest.model_validate_json(
        (out / "sessions/2/manifest.json").read_bytes()
    )
    assert (manifest.outcome, manifest.counts.cases.succeeded) == ("completed", 5)


def test_a_resume_with_a_case_due_needs_credentials_and_writes_nothing_without_them(
    cli: Cli, experiments: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # Trial Folio's authentication call gets a 401, so no case's request is sent: each is due.
    assert experiments.run(EXAMPLE, out, authenticates=[REFUSED]).exit_code == 6
    monkeypatch.delenv(API_KEY_VARIABLE)
    before = snapshot(out)
    received = len(cli.server.received)

    outcome = experiments.run(EXAMPLE, out)

    assert outcome.exit_code == 5
    assert error_code(outcome) == "provider.auth_failed"
    assert snapshot(out) == before
    assert len(cli.server.received) == received
    assert outcome.summary["output_dir"] is None


def test_run_doesnt_resume_a_synthetic_experiment(cli: Cli, experiments: Builder) -> None:
    # The core writes a synthetic experiment with the demo's client; no command does.
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)
    with LocalArtifactStore(out) as store:
        execution = ExperimentExecution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            SyntheticScreenBacktestClient(response_bytes()),
            command=None,
            clock=FixedClock(),
        )
        assert execution.run(EXAMPLE.read_bytes()) is None
    before = snapshot(out)

    # Without approval: it fails once the records pass, before the plan is shown.
    outcome = experiments.run(EXAMPLE, out, approve=False)

    assert outcome.exit_code == 4
    assert error_code(outcome) == "output.not_empty"
    assert "trialfolio run doesn't resume one" in outcome.stderr
    assert "Plan hash" not in outcome.stderr
    assert snapshot(out) == before
    assert cli.server.requests() == []
    assert plan_hash(EXAMPLE, out) == plan.plan_hash
