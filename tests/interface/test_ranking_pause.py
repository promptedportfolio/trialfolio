"""The pause between a `rank_update`'s 200 and its backtest, through `trialfolio run` (D-45): each
attempt that sends a definition, in a screen run, a new experiment, a resume, or a repeat, waits
10 seconds after its `rank_update`'s 200 before it sends its backtest, and says so on the
terminal, as progress; a snapshot, which writes nothing, and a run without a definition don't
wait; the full plan display says that each case's backtest is sent 10 seconds after its
`rank_update`; and the installed command waits on the real monotonic clock.

Traces to docs/contracts.md, sending a definition (the pause), plans with a ranking definition
(the display's wording), logging and local diagnostics (`attempt.backtest.waiting`), and CLI
behavior (the entry function's parameters for tests); and to D-45. The CLI's entry function runs
in the test process, with the fake server below `urllib3`, the fixed clock, and the fake pause,
`Cli`'s own, which records each wait with what the server had received then.
"""

import inspect
import json
import sys
import time
from pathlib import Path

import pytest

from tests.support.cli import Cli
from tests.support.clock import Slept
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    RANK_UPDATED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    returns_each,
)
from tests.support.fake_portfolio123 import AUTHENTICATED, response
from tests.support.snapshot_builder import serve_snapshot, take_snapshot
from tests.support.storage_faults import StorageFaults
from tests.support.terminal import PseudoTerminal
from trialfolio.cli import main
from trialfolio.configuration import read_experiment_configuration_v1_1
from trialfolio.pause import REAL_PAUSE, UPDATE_PAUSE_SECONDS
from trialfolio.planning import build_experiment_plan_v1_1, installed_versions

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DEFINITION = FIXTURES / "screen-configs" / "definition.yaml"
FORMULA = FIXTURES / "screen-configs" / "formula.yaml"
EXAMPLE = experiment_config("ranking-example.yaml")
BUDGET_RAISED = experiment_config("revisions/ranking-budget-raised.yaml")

AUTH, RANK, BACKTEST = "POST /auth", "POST /rank", "POST /screen/backtest"
WAITING = (
    "Waiting 10 seconds after the rank_update before sending the backtest, so Portfolio123 ranks"
    " by the definition just written."
)
SAYS_10_SECONDS = (
    "  Each case writes its definition there with its rank_update, and its backtest, which ranks"
    " by that system's name, is sent 10 seconds after the rank_update's response, so that"
    " Portfolio123 ranks it by the definition just written."
)


def waited_after(*received: str) -> Slept:
    """A wait of 10 seconds, which began once the server had received `received`."""
    return Slept(UPDATE_PAUSE_SECONDS, received)


def test_a_screen_runs_backtest_waits_10_seconds_after_its_rank_update(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", RANK_UPDATED, method="POST")
    cli.server.reply("/screen/backtest", response("complete.json"))
    out = cli.tmp / "run"

    outcome = cli.run_approved(DEFINITION, out)

    assert outcome.exit_code == 0, outcome.stderr
    assert cli.pause.slept == [waited_after(AUTH, RANK)]
    assert cli.server.requests() == [AUTH, RANK, BACKTEST]
    # The terminal says why it pauses, as progress, and the log holds the event, with the case
    # and the attempt.
    assert WAITING in outcome.stderr.splitlines()
    events = [
        json.loads(line)
        for line in (out / "logs" / "trialfolio.log").read_text(encoding="utf-8").splitlines()
    ]
    (waiting,) = [event for event in events if event["event"] == "attempt.backtest.waiting"]
    assert (waiting["level"], waiting["message"]) == ("INFO", WAITING)
    assert {"case_id", "attempt_id", "plan_hash"} <= waiting.keys()


def test_each_attempt_of_an_experiment_waits_in_a_new_session_a_resume_and_a_repeat(
    cli: Cli, experiments: ExperimentBuilder[Outcome], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A new experiment, stopped at its third case's first file, so a resume sends the last two;
    # the second case's backtest gets a 503, so it awaits a repeat, which the raised budget
    # covers.
    cli.ready()
    out = cli.tmp / "experiment"
    read = read_experiment_configuration_v1_1(EXAMPLE.read_bytes(), EXAMPLE.name, EXAMPLE)
    plan = build_experiment_plan_v1_1(read, installed_versions())
    third = plan.cases[2].case_id

    def stopping(root: str) -> StorageFaults:
        from trialfolio.storage import LocalArtifactStore

        store = StorageFaults(LocalArtifactStore(root), monkeypatch)
        store.fail_before(f"{third}/rank-update-request.json", KeyboardInterrupt())
        return store

    stopped = experiments.run(
        EXAMPLE,
        out,
        ranks=(RANK_UPDATED,) * 2,
        sends=(*returns_each(1), UNAVAILABLE),
        store_factory=stopping,
    )
    assert stopped.exit_code == 130, stopped.stderr
    assert cli.pause.slept == [
        waited_after(AUTH, RANK),
        waited_after(AUTH, RANK, BACKTEST, RANK),
    ]

    resumed = experiments.run(EXAMPLE, out, ranks=(RANK_UPDATED,) * 2, sends=returns_each(2))

    assert resumed.exit_code == 6, resumed.stderr
    sent = cli.server.requests()
    assert sent[5:] == [AUTH, RANK, BACKTEST, RANK, BACKTEST]
    assert cli.pause.slept[2:] == [
        waited_after(*sent[:5], AUTH, RANK),
        waited_after(*sent[:5], AUTH, RANK, BACKTEST, RANK),
    ]
    (second,) = [case for case in resumed.cases if case["case_key"] == "value-heavy"]

    repeated = experiments.run(
        BUDGET_RAISED,
        out,
        "--revision-reason",
        "A raised budget, for the repeat.",
        "--repeat",
        f"value-heavy:{second['repeat_attempt_id']}",
        ranks=(RANK_UPDATED,),
        sends=returns_each(1),
    )

    assert repeated.exit_code == 0, repeated.stderr
    assert cli.pause.slept[4:] == [waited_after(*sent, AUTH, RANK)]


def test_a_snapshot_and_a_run_without_a_definition_never_wait(cli: Cli) -> None:
    cli.ready()
    serve_snapshot(cli)
    snapshot = take_snapshot(cli, cli.tmp / "snapshot")
    assert snapshot.exit_code == 0, snapshot.stderr
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("complete.json"))

    formula = cli.run_approved(FORMULA, cli.tmp / "run")

    assert formula.exit_code == 0, formula.stderr
    assert cli.pause.slept == []
    assert WAITING not in snapshot.stderr + formula.stderr


@posix_only
def test_the_full_plan_display_says_each_backtest_is_sent_10_seconds_after_its_rank_update(
    cli: Cli,
) -> None:
    cli.accept_license()
    for config in (DEFINITION, EXAMPLE):
        with PseudoTerminal() as terminal:
            terminal.press("no\n")
            outcome = cli(
                "run",
                config,
                "--out",
                cli.tmp / config.stem,
                stdin=terminal.stdin,
                stderr=terminal.stderr,
            )
        shown = terminal.shown().replace("\n", " ").replace("   ", " ")

        assert outcome.exit_code == 2, shown
        assert SAYS_10_SECONDS.strip() in shown
    assert cli.server.requests() == []


def test_the_installed_command_waits_on_the_real_monotonic_clock() -> None:
    # The entry function's default, which the installed command takes: no test passes it.
    default = inspect.signature(main).parameters["pause"].default
    assert default is REAL_PAUSE
    assert REAL_PAUSE.monotonic is time.monotonic
    assert REAL_PAUSE.sleep is time.sleep
    assert UPDATE_PAUSE_SECONDS == 10
