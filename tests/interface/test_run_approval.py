"""`trialfolio run` sends nothing without the plan's exact hash, given with `--approve` or by typing
`approve` on a terminal; refusals create no output; and when stderr isn't a terminal, only the
plan hash and the budget are shown, never the configuration's values.

Traces to R01-AC01, through the CLI's entry function in the test process, with the real client,
`requests`, and `urllib3` over the fake server. The terminal is a real pseudo-terminal in the test
process (`tests/support/terminal.py`); R01-T15's terminal runs the command in a subprocess under
one, with the test launcher.
"""

import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, Outcome, config, plan_hash_for, serve_success
from tests.support.terminal import PseudoTerminal
from trialfolio.contracts.manifest import RunManifest
from trialfolio.contracts.plan import Plan

CANARIES = (
    "canary-title-5e1d0b7c",
    "canary-purpose-9a42f6e1",
    "canary-universe-3c8b2d40",
    "canary-rule-one-71f0a9d3",
    "canary-rule-two-0b6e4c52",
    "canary-formula-d29a1e87",
    "canary-benchmark-46c3f0b9",
)
"""The configuration values in `canaries.yaml`."""

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")


def error_code(outcome: Outcome) -> str:
    error = cast("dict[str, str]", outcome.summary["error"])
    return error["code"]


def assert_refused(cli: Cli, outcome: Outcome, out: Path) -> None:
    """`plan.approval_required`, exit 2, no output directory, and nothing sent."""
    assert outcome.exit_code == 2
    assert error_code(outcome) == "plan.approval_required"
    assert outcome.summary["output_dir"] is None
    assert not out.exists()
    assert cli.server.requests() == []


def test_without_approve_or_a_terminal_nothing_is_sent(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    outcome = cli("run", config("formula.yaml"), "--out", out, "--json")

    assert_refused(cli, outcome, out)
    ids = cast("dict[str, str]", outcome.summary["ids"])
    assert ids["plan_hash"] == plan_hash_for(config("formula.yaml"))
    assert f"--approve {ids['plan_hash']}" in outcome.stderr


@pytest.mark.parametrize(
    "given",
    [
        pytest.param(lambda full: full[:20], id="abbreviated"),
        pytest.param(lambda full: "sha256:" + full.removeprefix("sha256:").upper(), id="uppercase"),
        pytest.param(lambda full: "sha256:" + "0" * 64, id="different"),
    ],
)
def test_a_hash_that_isnt_the_full_hash_is_refused(cli: Cli, given: Callable[[str], str]) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"
    full = plan_hash_for(config("formula.yaml"))
    hashed = given(full)
    assert hashed != full

    outcome = cli("run", config("formula.yaml"), "--out", out, "--approve", hashed, "--json")

    assert_refused(cli, outcome, out)


def test_the_full_hash_runs_without_a_prompt_and_is_recorded_as_option(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"
    full = plan_hash_for(config("formula.yaml"))

    outcome = cli("run", config("formula.yaml"), "--out", out, "--approve", full, "--json")

    assert outcome.exit_code == 0, outcome.stderr
    assert "Type approve" not in outcome.stderr
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.approval == "option"
    assert manifest.plan_hash == full
    assert cli.server.requests() == ["POST /auth", "POST /screen/backtest"]


def test_without_a_terminal_only_the_hash_and_the_budget_are_shown(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"

    outcome = cli("run", config("canaries.yaml"), "--out", out, "--json")

    assert_refused(cli, outcome, out)
    assert plan_hash_for(config("canaries.yaml")) in outcome.stderr
    assert "at most 1 provider request" in outcome.stderr
    assert "5 credits" in outcome.stderr
    assert "in a terminal to see the full plan" in outcome.stderr
    for canary in CANARIES:
        assert canary not in outcome.stderr
        assert canary not in outcome.stdout


@posix_only
@pytest.mark.parametrize(
    "keys",
    [
        pytest.param("no\n", id="another-word"),
        pytest.param("\n", id="empty-line"),
        pytest.param("\x04", id="end-of-input"),
    ],
)
def test_any_other_answer_at_the_prompt_is_a_refusal(cli: Cli, keys: str) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    with PseudoTerminal() as terminal:
        terminal.press(keys)
        outcome = cli(
            "run",
            config("canaries.yaml"),
            "--out",
            out,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    assert_refused(cli, outcome, out)
    assert "Type approve to run this plan" in shown
    # On a terminal the full plan is shown, the configuration's values included.
    for canary in CANARIES:
        assert canary in shown


@posix_only
def test_typing_approve_runs_the_plan_shown_and_is_recorded_as_interactive(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        outcome = cli(
            "run",
            config("formula.yaml"),
            "--out",
            out,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    assert outcome.exit_code == 0, shown
    (shown_hash,) = {
        line.removeprefix("Plan hash: ")
        for line in shown.splitlines()
        if line.startswith("Plan hash: ")
    }
    plan = Plan.model_validate_json((out / "plan.json").read_bytes())
    assert plan.plan_hash == shown_hash
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.approval == "interactive"
    assert manifest.plan_hash == shown_hash
    assert cli.server.requests() == ["POST /auth", "POST /screen/backtest"]
