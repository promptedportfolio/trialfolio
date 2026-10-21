"""A stale backtest, and the repeat of a case whose response failed validation, through
`trialfolio run` (D-45): a flagged case fails with `provider.response_invalid`, and
`execution.partial`'s message says why, by its key, and gives the option that repeats it once,
where the CLI ends that message, as for any case awaiting a repeat, while the log names it only
by its `case_id`; the JSON summary gives its `repeat_attempt_id`; a resume's plan display, and
the prompt that confirms a repeat, say that its response failed validation; its repeat completes
it, as a repeat completes a 0.3.0 case whose response lacked the layout's structure.

Traces to docs/contracts.md, running an experiment (a stale backtest, a response that fails
validation, the command's plan display and repeats, and `execution.partial`'s message), repeating
a case, the JSON summary (`cases`), and logging and local diagnostics; and to D-45. The CLI's
entry function runs in the test process, with the fake server below `urllib3`, the fixed clock,
the fake pause, and an in-process pseudo-terminal.
"""

import json
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import AUTHENTICATED, Cli, Outcome
from tests.support.experiment_builder import (
    RANK_UPDATED,
    ExperimentBuilder,
    experiment_config,
    returns,
    returns_each,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.terminal import PseudoTerminal

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RESPONSES = FIXTURES / "responses"
EXAMPLE = experiment_config("ranking-example.yaml")
BUDGET_RAISED = experiment_config("revisions/ranking-budget-raised.yaml")
DEFAULT_ONLY = experiment_config("default-only.yaml")
DEFAULT_ONLY_RAISED = experiment_config("revisions/default-only-budget-3.yaml")
RAISED = "A raised budget, for the repeat."

SAME_RESULTS = Reply(
    200,
    (RESPONSES / "same-metrics.json").read_bytes().replace(b'"cost": 5,', b'"cost": 7,', 1),
)
"""`complete.json`'s results, with another `cost` and `quotaRemaining`."""


def summary_cases(outcome: Outcome) -> dict[str, dict[str, object]]:
    cases = cast("list[dict[str, object]]", outcome.summary["cases"])
    return {cast("str", case["case_key"]): case for case in cases}


def error(outcome: Outcome) -> dict[str, str]:
    return cast("dict[str, str]", outcome.summary["error"])


def stale_value_heavy(experiments: ExperimentBuilder[Outcome], out: Path) -> tuple[Outcome, str]:
    """Runs `ranking-example.yaml` into `out`, `value-heavy`'s backtest getting the baseline's
    results with another cost and quota, so it's flagged, and returns the outcome and its
    attempt's ID."""
    outcome = experiments.run(
        EXAMPLE,
        out,
        ranks=(RANK_UPDATED,) * 4,
        sends=(returns(), SAME_RESULTS, returns("changed-metrics.json"), returns()),
    )
    assert outcome.exit_code == 6, outcome.stderr
    attempt = summary_cases(outcome)["value-heavy"]["repeat_attempt_id"]
    assert isinstance(attempt, str)
    return outcome, attempt


def test_a_stale_backtest_fails_its_case_and_the_runs_message_gives_its_repeat_option_once(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome, attempt = stale_value_heavy(experiments, out)

    cases = summary_cases(outcome)
    assert {key: case["outcome"] for key, case in cases.items()} == {
        "baseline": "succeeded",
        "value-heavy": "failed",
        "tilt-earnings-yield": "succeeded",
        "no-sales-yield": "succeeded",
    }
    assert [case["repeat_attempt_id"] for key, case in cases.items() if key != "value-heavy"] == [
        None
    ] * 3
    assert cast("dict[str, int]", outcome.summary["counts"])["cases_failed"] == 1
    failure = error(outcome)
    assert failure["code"] == "execution.partial"
    message = failure["message"]
    assert "`value-heavy`, failed (provider.response_invalid)" in message
    assert (
        "The backtest of case `value-heavy` returned the same response, apart from cost and"
        " quotaRemaining, as that of case `baseline`, the case before it in session 1"
    ) in message
    assert "Identical results can sometimes be genuine" in message
    # The option comes once, where the CLI ends execution.partial's message, as for any case
    # awaiting a repeat, and only the report's location follows it; the case's own sentence ends
    # without it.
    assert f"Error (execution.partial): {message}\n" in outcome.stderr
    option = f"--repeat value-heavy:{attempt}"
    assert outcome.stderr.count("--repeat") == message.count("--repeat") == 1
    said, after = message.split(option)
    assert said.endswith(
        " To repeat the case awaiting a repeat, which may be charged again, run the same command"
        " with its option: "
    )
    assert after.startswith(". Session 1's report gives each case's attempts: ")
    assert after.endswith("report.html.")
    assert (
        " The response is saved, but the case isn't normalized, and it awaits a repeat, which"
        " sends its rank_update and its backtest again, and may be charged again. A case whose"
        " request may have reached Portfolio123"
    ) in said
    # The log names the cases by their case_ids, never by their keys, and the attempt by its ID,
    # once, with no option.
    log = (out / "logs" / "trialfolio.log").read_text(encoding="utf-8")
    events = [json.loads(line) for line in log.splitlines()]
    (invalid,) = [event for event in events if event["event"] == "experiment.case.invalid"]
    assert invalid["case_id"] == cases["value-heavy"]["case_id"]
    (ended,) = [event for event in events if event["event"] == "cli.command.completed"]
    logged = str(ended["message"])
    assert f"The backtest of case {cases['value-heavy']['case_id']}" in logged
    assert (
        f" The response of attempt {attempt} is saved, but the case isn't normalized, and it"
        " awaits a repeat, which sends its rank_update and its backtest again, and may be charged"
        " again."
    ) in logged
    assert logged.count(attempt) == 1
    assert "--repeat" not in log
    for key in cases:
        assert key not in log


@posix_only
def test_a_resumes_display_and_its_repeats_prompt_say_the_response_failed_validation(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    _, attempt = stale_value_heavy(experiments, out)
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", RANK_UPDATED, method="POST")
    cli.server.reply("/screen/backtest", *returns_each(1))
    before = len(cli.server.requests())

    with PseudoTerminal() as terminal:
        terminal.press("approve\nrepeat\n")
        outcome = cli(
            "run",
            BUDGET_RAISED,
            "--out",
            out,
            "--json",
            "--revision-reason",
            RAISED,
            "--repeat",
            "value-heavy",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown().replace("\n", " ").replace("  ", " ")

    assert outcome.exit_code == 0, shown
    assert (
        "So far: failed (provider.response_invalid), after 1 attempt. Its attempt succeeded, but"
        " its saved response failed validation, so it wasn't normalized, and it's sent again"
        " only by a repeat, which sends its rank_update and its backtest again, and may be"
        f" charged again: --repeat value-heavy:{attempt}"
    ) in shown
    assert (
        f"value-heavy ({summary_cases(outcome)['value-heavy']['case_id']}): its attempt"
        f" {attempt} succeeded, but its saved response failed validation"
        " (provider.response_invalid), and its request may already have been charged."
    ) in shown
    assert cli.server.requests()[before:] == ["POST /auth", "POST /rank", "POST /screen/backtest"]
    cases = summary_cases(outcome)
    assert {case["outcome"] for case in cases.values()} == {"succeeded"}
    assert {case["repeat_attempt_id"] for case in cases.values()} == {None}


def test_a_case_whose_response_had_no_required_structure_awaits_a_repeat_that_completes_it(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    # A plan 1.1.0, as in 0.3.0, which read such a case as complete, so it was never sent again.
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiments.run(DEFAULT_ONLY, out, sends=(returns(), returns("invalid-structure.json")))
    assert first.exit_code == 6, first.stderr
    ((key, invalid),) = [
        (key, case) for key, case in summary_cases(first).items() if case["outcome"] == "failed"
    ]
    attempt = invalid["repeat_attempt_id"]
    assert isinstance(attempt, str)
    assert f"--repeat {key}:{attempt}" in error(first)["message"]

    repeated = experiments.run(
        DEFAULT_ONLY_RAISED,
        out,
        "--revision-reason",
        RAISED,
        "--repeat",
        f"{key}:{attempt}",
        sends=(returns(),),
    )

    assert repeated.exit_code == 0, repeated.stderr
    assert {case["outcome"] for case in summary_cases(repeated).values()} == {"succeeded"}
    tables = out / "cases" / cast("str", invalid["case_id"]) / "normalized"
    assert sorted(path.name for path in tables.iterdir()) == ["metrics.csv", "settings.csv"]
