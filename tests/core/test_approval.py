"""The CLI's side of approval shows the plan as docs/contracts.md's plan display says, and approves
only the plan's exact hash, from `--approve` or typed confirmation on a terminal.

Traces to R01-AC01 in release 0.1.0's test pairing, ahead of the CLI (R01-T14), whose interface
tests (`tests/interface/test_run_approval.py`, R01-T16) run the command itself: each refusal fails
with `plan.approval_required`; the full hash approves without a prompt, as `option`; typing
`approve` approves the plan shown, as `interactive`; and when stderr isn't a terminal, only the
hash and the budget are shown, never the formulas. The terminal is a real pseudo-terminal.
"""

import io
import subprocess
import sys
from pathlib import Path
from typing import TextIO

import pytest

from tests.support.terminal import PseudoTerminal
from trialfolio.approval import Approval, format_plan, obtain_approval
from trialfolio.configuration import read_screen_configuration
from trialfolio.contracts.plan import Plan
from trialfolio.errors import TrialFolioError
from trialfolio.planning import VERIFIED_VERSIONS, Versions, build_plan

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "screen-configs"

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


@pytest.fixture
def plan() -> Plan:
    path = FIXTURES / "canaries.yaml"
    versions = Versions(
        trialfolio="0.1.0",
        p123api=VERIFIED_VERSIONS["p123api"][0],
        requests=VERIFIED_VERSIONS["requests"][0],
        urllib3=VERIFIED_VERSIONS["urllib3"][0],
    )
    return build_plan(read_screen_configuration(path.read_bytes(), path.name), versions)


def assert_summary_only(shown: str, plan: Plan) -> None:
    assert plan.plan_hash in shown
    assert "at most 1 provider request" in shown
    assert "5 credits" in shown
    for canary in CANARIES:
        assert canary not in shown


def assert_full_plan(shown: str, plan: Plan) -> None:
    assert plan.plan_hash in shown
    for canary in CANARIES:
        assert canary in shown


def refusal(plan: Plan, approve: str | None, *, stdin: TextIO, stderr: TextIO) -> str:
    with pytest.raises(TrialFolioError) as raised:
        obtain_approval(plan, approve, stdin=stdin, stderr=stderr)
    assert raised.value.code == "plan.approval_required"
    # The message gives the exact option that approves this plan.
    assert f"--approve {plan.plan_hash}" in raised.value.message
    return raised.value.message


def test_without_a_terminal_only_the_hash_and_the_budget_are_shown(plan: Plan) -> None:
    stdin = io.StringIO("approve\n")
    stderr = io.StringIO()

    refusal(plan, None, stdin=stdin, stderr=stderr)

    assert stdin.read() == "approve\n"  # never asked
    assert_summary_only(stderr.getvalue(), plan)
    assert "in a terminal to see the full plan" in stderr.getvalue()


def test_the_full_hash_approves_without_a_prompt(plan: Plan) -> None:
    stderr = io.StringIO()

    approval = obtain_approval(plan, plan.plan_hash, stdin=io.StringIO(), stderr=stderr)

    assert approval == Approval(plan.plan_hash, "option")
    assert_summary_only(stderr.getvalue(), plan)


@pytest.mark.parametrize("given", ["abbreviated", "uppercase", "different"])
def test_a_hash_that_isnt_the_full_hash_is_refused(plan: Plan, given: str) -> None:
    approve = {
        "abbreviated": plan.plan_hash[:15],
        "uppercase": plan.plan_hash.upper(),
        "different": "sha256:" + "0" * 64,
    }[given]
    stderr = io.StringIO()

    message = refusal(plan, approve, stdin=io.StringIO(), stderr=stderr)

    assert "isn't this plan's hash" in message
    assert_summary_only(stderr.getvalue(), plan)


@posix_only
def test_on_a_terminal_the_full_hash_still_shows_only_the_hash_and_the_budget(plan: Plan) -> None:
    with PseudoTerminal() as terminal:
        approval = obtain_approval(
            plan, plan.plan_hash, stdin=terminal.stdin, stderr=terminal.stderr
        )

    assert approval == Approval(plan.plan_hash, "option")
    assert_summary_only(terminal.shown(), plan)


@posix_only
def test_on_a_terminal_a_refused_hash_shows_the_full_plan(plan: Plan) -> None:
    with PseudoTerminal() as terminal:
        refusal(plan, plan.plan_hash[:15], stdin=terminal.stdin, stderr=terminal.stderr)

    assert_full_plan(terminal.shown(), plan)


@posix_only
def test_typing_approve_approves_the_plan_shown(plan: Plan) -> None:
    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        approval = obtain_approval(plan, None, stdin=terminal.stdin, stderr=terminal.stderr)

    assert approval == Approval(plan.plan_hash, "interactive")
    shown = terminal.shown()
    assert_full_plan(shown, plan)
    assert shown.index(plan.plan_hash) < shown.index("Type approve to run this plan")


@posix_only
@pytest.mark.parametrize(
    "keys", ["no\n", "\n", "\x04", "Approve\n", " approve\n", "approve \n", "approved\n"]
)
def test_any_other_answer_or_the_end_of_input_is_a_refusal(plan: Plan, keys: str) -> None:
    with PseudoTerminal() as terminal:
        terminal.press(keys)
        message = refusal(plan, None, stdin=terminal.stdin, stderr=terminal.stderr)

    assert "wasn't approved" in message
    assert_full_plan(terminal.shown(), plan)


@posix_only
def test_without_a_terminal_for_stdin_nothing_is_asked(plan: Plan) -> None:
    stdin = io.StringIO("approve\n")
    with PseudoTerminal() as terminal:
        refusal(plan, None, stdin=stdin, stderr=terminal.stderr)

    shown = terminal.shown()
    assert "Type approve" not in shown
    assert stdin.read() == "approve\n"
    assert_full_plan(shown, plan)


@posix_only
def test_without_a_terminal_for_stderr_nothing_is_asked(plan: Plan) -> None:
    stderr = io.StringIO()
    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        refusal(plan, None, stdin=terminal.stdin, stderr=stderr)

    assert "Type approve" not in stderr.getvalue()
    assert_summary_only(stderr.getvalue(), plan)


def test_the_full_plan_shows_what_will_be_sent_and_how_to_approve_it(plan: Plan) -> None:
    shown = format_plan(plan)

    for expected in (
        '"slippage": 0.25',
        '"maxNumHoldings": 25',
        "data_vendor: FactSet (inferred; inferred default)",
        "universe: canary-universe-3c8b2d40 (verified; not snapshotted",
        "commission: not_modeled (inferred; not modeled by this provider path)",
        "max_pos_pct: not_sent (unknown; not sent",
        "may be charged even if it fails",
        "authentication call, whose cost isn't documented",
        "Retries: 0 automatic",
        "credentials: the API ID and key",
        "Nothing else is sent: not the title, the purpose, data_vendor",
        f"--approve {plan.plan_hash}",
    ):
        assert expected in shown


def test_configuration_text_cant_act_on_the_terminal(plan: Plan) -> None:
    escape, bell, override = chr(0x1B), chr(0x07), chr(0x202E)
    hostile = plan.model_copy(update={"title": f"{escape}[2J{bell}title{override}txet"})

    shown = format_plan(hostile)

    for char in (escape, bell, override):
        assert char not in shown
    assert "[2J" in shown


def test_without_termios_this_module_still_imports() -> None:
    # A corrected defect: on Windows, which has no termios, importing the terminal helper failed,
    # so this module didn't collect, rather than only its terminal tests skipping.
    script = "import sys\nsys.modules['termios'] = None\nimport tests.core.test_approval\n"

    subprocess.run([sys.executable, "-c", script], capture_output=True, check=True, cwd=REPO_ROOT)
