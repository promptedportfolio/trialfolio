"""`trialfolio run --repeat`: a case whose request may have been charged is sent again only when
`--repeat` names it and the possible repeat charge is confirmed, by typing `repeat` on a terminal,
or with the attempt ID that names the case's latest possibly charged attempt; a confirmed repeat
is one new attempt of the case, whose records name that attempt; once it may have reached
Portfolio123, the same command, run again, doesn't repeat the case again; and a repeat that can't
apply fails before anything is sent.

Traces to R03-AC14's interface part (D-31), and to docs/contracts.md, repeating a case (the
prompt, the usage errors, and what fails and what doesn't), running an experiment (the plan
display's progress and budget, whose sends, like the prompt's, are the core's, as R03-T13's
review corrected) and CLI behavior (a usage error has no JSON summary). Each test writes
`example.yaml`'s experiment with the experiment builder, with a 503 for `holdings-50`'s request,
which leaves it `unknown`, a 402, which stops the later cases, or a 401 for Trial Folio's
authentication call, which leaves every case due, through the CLI's entry function in the test
process, over the fake server. The terminal is a real pseudo-terminal in the test process, and
the socket faults interrupt a repeat during its send, as Ctrl-C does.
"""

import json
import sys
import uuid
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, Outcome, config, snapshot
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
from tests.support.socket_faults import SocketFaults
from tests.support.terminal import PseudoTerminal
from trialfolio.contracts.attempt import AttemptRecordV1_1, StartRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

EXAMPLE = experiment_config("example.yaml")
HOLDINGS = "holdings-50"

type Builder = ExperimentBuilder[Outcome]


def cases_of(outcome: Outcome) -> dict[str, dict[str, object]]:
    """The summary's cases, by key."""
    cases = cast("list[dict[str, object]]", outcome.summary["cases"])
    return {cast("str", case["case_key"]): case for case in cases}


def error_of(outcome: Outcome) -> dict[str, str]:
    return cast("dict[str, str]", outcome.summary["error"])


def unknown_case(cli: Cli, experiments: Builder) -> tuple[Path, str, str]:
    """Writes `example.yaml`'s experiment with `holdings-50`'s request answered with a 503, and
    returns its directory, the case's `case_id`, and its `unknown` attempt's ID."""
    cli.ready()
    out = cli.tmp / "experiment"
    outcome = experiments.run(
        EXAMPLE, out, sends=[returns(), returns(), UNAVAILABLE, returns(), returns()]
    )
    assert outcome.exit_code == 6, outcome.stderr
    case = cases_of(outcome)[HOLDINGS]
    assert case["outcome"] == "unknown"
    return out, cast("str", case["case_id"]), cast("str", case["repeat_attempt_id"])


def attempts_of(out: Path, case_id: str) -> list[AttemptRecordV1_1]:
    """The case's attempt records, by session and then sequence."""
    records = [
        AttemptRecordV1_1.model_validate_json(path.read_bytes())
        for path in (out / "cases" / case_id / "attempts").glob("*/attempt.json")
    ]
    return sorted(records, key=lambda record: (record.session, record.sequence))


def manifest(out: Path, session: int) -> ExperimentManifest:
    return ExperimentManifest.model_validate_json(
        (out / f"sessions/{session}/manifest.json").read_bytes()
    )


def test_without_repeat_a_resume_doesnt_send_the_case_awaiting_one(
    cli: Cli, experiments: Builder
) -> None:
    out, _, attempt = unknown_case(cli, experiments)
    received = len(cli.server.received)

    outcome = experiments.run(EXAMPLE, out)

    assert outcome.exit_code == 6
    assert len(cli.server.received) == received
    assert cases_of(outcome)[HOLDINGS]["repeat_attempt_id"] == attempt
    assert f"--repeat {HOLDINGS}:{attempt}" in error_of(outcome)["message"]
    # Without a terminal, the counts so far, and nothing from the configuration.
    assert (
        "Counted so far, across every run of the experiment: 5 provider requests and 1"
        " authentication call, which leaves 1 provider request and 5 authentication calls."
    ) in outcome.stderr
    assert "It's the experiment's current plan, plan 1, which this run resumes." in outcome.stderr
    assert HOLDINGS not in outcome.stderr.split("Error (")[0]


@posix_only
def test_on_a_terminal_typing_repeat_sends_one_attempt_which_the_same_command_doesnt_repeat(
    cli: Cli, experiments: Builder
) -> None:
    out, case_id, attempt = unknown_case(cli, experiments)
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", returns())
    received = len(cli.server.received)

    with PseudoTerminal() as terminal:
        terminal.press("approve\nrepeat\n")
        outcome = cli(
            "run",
            EXAMPLE,
            "--out",
            out,
            "--repeat",
            HOLDINGS,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    assert outcome.exit_code == 0, shown
    assert cli.server.requests()[received:] == ["POST /auth", "POST /screen/backtest"]
    assert (
        f"{HOLDINGS} ({case_id}): its attempt {attempt} is unknown (provider.outcome_unknown),"
        " and its request may already have been charged." in shown
    )
    assert "It may be charged again, and it counts against the experiment's budget" in shown
    assert "of its 6 provider requests, 1 remains" in shown
    assert "which leaves 0 provider requests" in shown
    assert shown.index("Type approve") < shown.index("Type repeat to repeat it")
    first, repeat = attempts_of(out, case_id)
    assert str(first.attempt_id) == attempt
    assert (repeat.outcome, str(repeat.repeat_of)) == ("succeeded", attempt)
    started = StartRecordV1_1.model_validate_json(
        (out / f"cases/{case_id}/attempts/{repeat.attempt_id}/started.json").read_bytes()
    )
    assert str(started.repeat_of) == attempt
    counts = manifest(out, 2).counts
    assert (counts.attempts.repeats, counts.cases.succeeded) == (1, 5)

    # The same command again: the case is complete, so it isn't repeated, and the rest resumes.
    received = len(cli.server.received)
    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        again = cli(
            "run",
            EXAMPLE,
            "--out",
            out,
            "--repeat",
            HOLDINGS,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    assert again.exit_code == 0, shown
    assert len(cli.server.received) == received
    assert f"Case {HOLDINGS} isn't repeated: it's complete" in shown
    assert "Type repeat" not in shown


def test_the_attempt_id_confirms_a_repeat_without_asking_and_is_used_once(
    cli: Cli, experiments: Builder
) -> None:
    out, case_id, attempt = unknown_case(cli, experiments)
    option = f"{HOLDINGS}:{attempt}"
    received = len(cli.server.received)

    outcome = experiments.run(EXAMPLE, out, "--repeat", option, sends=[UNAVAILABLE])

    assert outcome.exit_code == 6, outcome.stderr
    assert cli.server.requests()[received:] == ["POST /auth", "POST /screen/backtest"]
    assert "Type repeat" not in outcome.stderr
    repeat = attempts_of(out, case_id)[-1]
    assert (repeat.outcome, str(repeat.repeat_of)) == ("unknown", attempt)
    assert cases_of(outcome)[HOLDINGS]["repeat_attempt_id"] == str(repeat.attempt_id)
    assert f"--repeat {HOLDINGS}:{repeat.attempt_id}" in error_of(outcome)["message"]
    assert manifest(out, 2).counts.attempts.repeats == 1

    # The same command again: the confirmation is used, so the case isn't repeated again, and a
    # new one names the repeat's own attempt.
    received = len(cli.server.received)
    again = experiments.run(EXAMPLE, out, "--repeat", option)

    assert again.exit_code == 6
    assert len(cli.server.received) == received
    assert (
        f"Case {HOLDINGS} isn't repeated: the repeat confirmed for its attempt {attempt} was made"
        " already" in again.stderr
    )
    assert f"--repeat {HOLDINGS}:{repeat.attempt_id}." in again.stderr
    assert len(attempts_of(out, case_id)) == 2
    assert manifest(out, 3).counts.attempts.repeats == 1


def test_a_key_alone_for_a_complete_case_resumes_the_rest(cli: Cli, experiments: Builder) -> None:
    out, _, _ = unknown_case(cli, experiments)
    received = len(cli.server.received)

    outcome = experiments.run(EXAMPLE, out, "--repeat", "baseline")

    assert outcome.exit_code == 6
    assert len(cli.server.received) == received
    assert "Case baseline isn't repeated: it's complete" in outcome.stderr
    assert (out / "sessions/2/manifest.json").is_file()


def test_a_repeat_whose_authentication_fails_sends_nothing_and_its_confirmation_stays_unused(
    cli: Cli, experiments: Builder
) -> None:
    out, case_id, attempt = unknown_case(cli, experiments)
    option = f"{HOLDINGS}:{attempt}"
    received = len(cli.server.received)

    refused = experiments.run(EXAMPLE, out, "--repeat", option, authenticates=[REFUSED])

    assert refused.exit_code == 6
    assert cli.server.requests()[received:] == ["POST /auth"]
    failed = attempts_of(out, case_id)[-1]
    assert (failed.outcome, failed.possibly_charged, str(failed.repeat_of)) == (
        "failed",
        False,
        attempt,
    )
    # The case is still unknown, by its latest attempt that may have reached Portfolio123.
    assert cases_of(refused)[HOLDINGS]["outcome"] == "unknown"
    assert manifest(out, 2).counts.cases.unknown == 1

    received = len(cli.server.received)
    repeated = experiments.run(EXAMPLE, out, "--repeat", option, sends=[returns()])

    assert repeated.exit_code == 0, repeated.stderr
    assert cli.server.requests()[received:] == ["POST /auth", "POST /screen/backtest"]
    last = attempts_of(out, case_id)[-1]
    assert (last.outcome, str(last.repeat_of)) == ("succeeded", attempt)
    assert manifest(out, 3).counts.attempts.repeats == 2


def test_a_repeat_interrupted_during_its_send_uses_its_confirmation(
    cli: Cli, experiments: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, case_id, attempt = unknown_case(cli, experiments)
    option = f"{HOLDINGS}:{attempt}"
    cli.server.reply("/auth", AUTHENTICATED)
    with monkeypatch.context() as patch:
        SocketFaults(patch).interrupt_send(b"POST /screen/backtest")
        interrupted = cli(
            "run",
            EXAMPLE,
            "--out",
            out,
            "--repeat",
            option,
            "--approve",
            plan_hash(EXAMPLE, out),
            "--json",
        )

    assert interrupted.exit_code == 130
    assert error_of(interrupted)["code"] == "command.interrupted"
    received = len(cli.server.received)

    again = experiments.run(EXAMPLE, out, "--repeat", option)

    assert again.exit_code == 6, again.stderr
    assert len(cli.server.received) == received
    repeat = attempts_of(out, case_id)[-1]
    assert (repeat.outcome, repeat.possibly_charged, str(repeat.repeat_of)) == (
        "unknown",
        True,
        attempt,
    )
    assert f"isn't repeated: the repeat confirmed for its attempt {attempt}" in again.stderr
    assert cases_of(again)[HOLDINGS]["repeat_attempt_id"] == str(repeat.attempt_id)


# What fails, before anything is sent


def case_ids(out: Path) -> dict[str, str]:
    """Each planned case's `case_id`, by key, from the first plan's `experiment.json`."""
    record = json.loads((out / "plans/1/experiment.json").read_bytes())
    return {case["case_key"]: case["case_id"] for case in record["planned_cases"]}


def assert_refused(cli: Cli, outcome: Outcome, before: dict[str, bytes | None], out: Path) -> str:
    """`plan.approval_required`, exit 2, nothing sent or written; returns the message."""
    assert outcome.exit_code == 2, outcome.stderr
    error = error_of(outcome)
    assert error["code"] == "plan.approval_required"
    assert snapshot(out) == before
    assert outcome.summary["output_dir"] is None
    return error["message"]


@pytest.mark.parametrize(
    "given",
    [
        "a-key-alone-without-a-terminal",
        "no-such-attempt",
        "another-cases-attempt",
        "a-succeeded-attempt",
        "no-case-of-the-plan",
    ],
)
def test_a_repeat_that_cant_apply_fails_and_gives_the_option_that_repeats_the_case(
    cli: Cli, experiments: Builder, given: str
) -> None:
    out, _, attempt = unknown_case(cli, experiments)
    baseline = attempts_of(out, case_ids(out)["baseline"])[0].attempt_id
    value = {
        "a-key-alone-without-a-terminal": HOLDINGS,
        "no-such-attempt": f"{HOLDINGS}:{uuid.uuid4()}",
        "another-cases-attempt": f"{HOLDINGS}:{baseline}",
        "a-succeeded-attempt": f"baseline:{baseline}",
        "no-case-of-the-plan": "nothing-of-the-plan",
    }[given]
    before = snapshot(out)
    received = len(cli.server.received)

    outcome = experiments.run(EXAMPLE, out, "--repeat", value)

    message = assert_refused(cli, outcome, before, out)
    why = {
        "a-key-alone-without-a-terminal": "awaits a repeat, but --repeat names it without an"
        " attempt ID",
        "no-case-of-the-plan": "names no case of the plan this run approves",
    }.get(given, "which isn't an attempt of the case whose request may have been charged")
    assert why in message
    assert (
        f"The case awaiting a repeat, with the option that repeats it: --repeat {HOLDINGS}:{attempt}."
        in message
    )
    assert len(cli.server.received) == received


def test_a_due_case_or_an_attempt_that_cant_have_been_charged_isnt_repeated(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # Trial Folio's authentication call gets a 401, so the baseline's attempt sent nothing.
    assert experiments.run(EXAMPLE, out, authenticates=[REFUSED]).exit_code == 6
    ids = case_ids(out)
    (refused,) = attempts_of(out, ids["baseline"])
    before = snapshot(out)

    due = experiments.run(EXAMPLE, out, "--repeat", "liquidity-100m")

    message = assert_refused(cli, due, before, out)
    assert "Case liquidity-100m isn't awaiting a repeat" in message
    assert "No case of the plan awaits a repeat." in message

    # Then the baseline's request gets a 503: it awaits a repeat, of that attempt, not the first.
    assert experiments.run(EXAMPLE, out, sends=[UNAVAILABLE, *[returns()] * 4]).exit_code == 6
    unknown = attempts_of(out, ids["baseline"])[-1]
    before = snapshot(out)

    not_charged = experiments.run(EXAMPLE, out, "--repeat", f"baseline:{refused.attempt_id}")

    message = assert_refused(cli, not_charged, before, out)
    assert f"names attempt {refused.attempt_id}, which isn't an attempt of the case" in message
    assert f"--repeat baseline:{unknown.attempt_id}" in message


@posix_only
def test_any_other_answer_at_the_repeat_prompt_is_a_refusal(cli: Cli, experiments: Builder) -> None:
    out, _, attempt = unknown_case(cli, experiments)
    before = snapshot(out)
    received = len(cli.server.received)

    with PseudoTerminal() as terminal:
        terminal.press("approve\nno\n")
        outcome = cli(
            "run",
            EXAMPLE,
            "--out",
            out,
            "--repeat",
            HOLDINGS,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    terminal.shown()

    message = assert_refused(cli, outcome, before, out)
    assert "wasn't confirmed: the answer wasn't repeat" in message
    assert f"--repeat {HOLDINGS}:{attempt}" in message
    assert len(cli.server.received) == received


def test_a_repeat_with_a_new_experiment_or_a_screen_fails_and_creates_nothing(cli: Cli) -> None:
    cli.ready()
    new = cli.tmp / "experiment"
    screen = cli.tmp / "run"

    experiment = cli(
        "run",
        EXAMPLE,
        "--out",
        new,
        "--approve",
        plan_hash(EXAMPLE, new),
        "--repeat",
        HOLDINGS,
        "--json",
    )
    run = cli("run", config("formula.yaml"), "--out", screen, "--repeat", HOLDINGS, "--json")

    assert (experiment.exit_code, run.exit_code) == (2, 2)
    assert "A new experiment has no attempt to repeat" in error_of(experiment)["message"]
    assert "--repeat applies only to an experiment's configuration" in error_of(run)["message"]
    for outcome in (experiment, run):
        assert error_of(outcome)["code"] == "plan.approval_required"
    assert not new.exists()
    assert not screen.exists()
    assert cli.server.requests() == []


@pytest.mark.parametrize(
    "options",
    [
        pytest.param(["--repeat", "Holdings 50"], id="not-a-case-key"),
        pytest.param(["--repeat", f"{HOLDINGS}:not-an-attempt-id"], id="not-an-attempt-id"),
        pytest.param(
            ["--repeat", f"{HOLDINGS}:{str(uuid.uuid4()).upper()}"], id="an-uppercase-attempt-id"
        ),
        pytest.param(
            ["--repeat", HOLDINGS, "--repeat", f"{HOLDINGS}:{uuid.uuid4()}"], id="a-key-twice"
        ),
    ],
)
def test_a_malformed_repeat_is_a_usage_error_without_a_summary(
    cli: Cli, options: list[str]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = cli("run", EXAMPLE, "--out", out, *options, "--json")

    assert outcome.exit_code == 2
    assert outcome.stdout == ""
    assert "usage: trialfolio run" in outcome.stderr
    assert "argument --repeat" in outcome.stderr
    assert not out.exists()


@posix_only
def test_the_display_gives_each_cases_progress_and_the_cases_the_budget_cant_cover(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiments.run(
        EXAMPLE, out, sends=[returns(), returns(), UNAVAILABLE, returns(), UNAVAILABLE]
    )
    assert first.exit_code == 6
    holdings, slippage = (
        cast("str", cases_of(first)[key]["repeat_attempt_id"]) for key in (HOLDINGS, "slippage-050")
    )
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", returns())
    received = len(cli.server.received)

    with PseudoTerminal() as terminal:
        terminal.press("approve\nrepeat\n")
        outcome = cli(
            "run",
            EXAMPLE,
            "--out",
            out,
            "--repeat",
            HOLDINGS,
            "--repeat",
            "slippage-050",
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    assert "So far: succeeded, after 1 attempt. It's complete, so it isn't sent again." in shown
    assert (
        "So far: unknown (provider.outcome_unknown), after 1 attempt. Its request may have reached"
        " Portfolio123, and may have been charged, so it's sent again only by a repeat, which may"
        f" be charged again: --repeat {HOLDINGS}:{holdings}"
    ) in shown
    assert f"--repeat slippage-050:{slippage}" in shown
    assert "The remaining budget can't cover slippage-050, so this run won't start it." in shown
    assert "this run sends 2 requests, with the cases that are due and the repeats" in shown
    assert "more than remain" in shown
    # One request remained: the first repeat is sent, and the budget stops the second.
    assert outcome.exit_code == 6, shown
    assert cli.server.requests()[received:] == ["POST /auth", "POST /screen/backtest"]
    assert cases_of(outcome)["slippage-050"]["repeat_attempt_id"] == slippage


# What the run sends: the cases that are due, and each repeat it makes (R03-T13's review)

QUOTA = Reply(402, b"")
"""A 402 to a case's request: `failed`, possibly charged, with `provider.quota_exceeded`, which
stops the later cases (D-32)."""

REBALANCE = "rebalance-weeks-1"
DUE = "slippage-050"


def two_awaiting_and_one_due(cli: Cli, experiments: Builder) -> tuple[Path, str, str]:
    """Writes `example.yaml`'s experiment with a 503 for `holdings-50`'s request, and a 402 for
    `rebalance-weeks-1`'s, which stops `slippage-050`: two cases await a repeat, the last is due,
    and 2 of the budget's 6 provider requests remain. Returns its directory, and the attempt IDs
    that confirm a repeat of `holdings-50` and of `rebalance-weeks-1`."""
    cli.ready()
    out = cli.tmp / "experiment"
    outcome = experiments.run(EXAMPLE, out, sends=[returns(), returns(), UNAVAILABLE, QUOTA])
    assert outcome.exit_code == 6, outcome.stderr
    cases = cases_of(outcome)
    assert cases[DUE]["outcome"] == "not_yet_run"
    return (
        out,
        cast("str", cases[HOLDINGS]["repeat_attempt_id"]),
        cast("str", cases[REBALANCE]["repeat_attempt_id"]),
    )


@posix_only
def test_the_repeat_prompt_counts_the_cases_due_and_the_repeats_an_attempt_id_confirmed(
    cli: Cli, experiments: Builder
) -> None:
    out, _, rebalance = two_awaiting_and_one_due(cli, experiments)
    before = snapshot(out)
    received = len(cli.server.received)
    shown: list[str] = []
    for options in ([], ["--repeat", f"{REBALANCE}:{rebalance}"]):
        with PseudoTerminal() as terminal:
            # Any answer but repeat refuses, so nothing is sent or written.
            terminal.press("approve\nno\n")
            outcome = cli(
                "run",
                EXAMPLE,
                "--out",
                out,
                "--repeat",
                HOLDINGS,
                *options,
                "--json",
                stdin=terminal.stdin,
                stderr=terminal.stderr,
            )
        shown.append(terminal.shown())
        assert_refused(cli, outcome, before, out)
    alone, mixed = shown

    # The case that's due is sent too.
    assert "So far: not yet run. This run sends it." in alone
    assert "of its 6 provider requests, 2 remain, and this run sends 2 requests" in alone
    assert "which leaves 0 provider requests" in alone
    # And so is the repeat its attempt ID confirmed, which the prompt doesn't ask about.
    assert "of its 6 provider requests, 2 remain, and this run sends 3 requests" in mixed
    assert "more than remain, so the cases the budget can't cover won't start" in mixed
    assert f"The remaining budget can't cover {DUE}, so this run won't start it." in mixed
    assert len(cli.server.received) == received


@posix_only
def test_a_used_confirmation_isnt_among_the_sends_the_remaining_budget_must_cover(
    cli: Cli, experiments: Builder
) -> None:
    out, holdings, _ = two_awaiting_and_one_due(cli, experiments)
    option = f"{HOLDINGS}:{holdings}"
    # The repeat gets a 402 too, which uses its confirmation and stops the case that's due
    # again: 1 provider request remains.
    assert experiments.run(EXAMPLE, out, "--repeat", option, sends=[QUOTA]).exit_code == 6
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", returns())
    received = len(cli.server.received)

    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        outcome = cli(
            "run",
            EXAMPLE,
            "--out",
            out,
            "--repeat",
            option,
            "--json",
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    # The run sends only the case that's due, which the remaining request covers.
    assert "which leaves 1 provider request and 4 authentication calls." in shown
    assert "The remaining budget can't cover" not in shown
    assert (
        f"Case {HOLDINGS} isn't repeated: the repeat confirmed for its attempt {holdings}" in shown
    )
    assert outcome.exit_code == 6, shown
    assert cli.server.requests()[received:] == ["POST /auth", "POST /screen/backtest"]
    assert cases_of(outcome)[DUE]["outcome"] == "succeeded"


@posix_only
def test_with_no_authentication_call_left_the_budget_covers_no_case(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # Each run's authentication call gets a 401, so no case's request is sent, until the
    # budget's 6 authentication calls are spent: every case is due, and no provider request is.
    for _ in range(6):
        assert experiments.run(EXAMPLE, out, authenticates=[REFUSED]).exit_code == 6
    before = snapshot(out)
    received = len(cli.server.received)

    with PseudoTerminal() as terminal:
        terminal.press("no\n")
        outcome = cli(
            "run", EXAMPLE, "--out", out, "--json", stdin=terminal.stdin, stderr=terminal.stderr
        )
    shown = terminal.shown()

    assert_refused(cli, outcome, before, out)
    assert (
        "So far: failed (provider.auth_failed), after 6 attempts, none of whose requests could"
        " have reached Portfolio123. This run sends it."
    ) in shown
    assert f"Case {DUE} " in shown
    assert "So far: not yet run. This run sends it." in shown
    assert (
        "Counted so far: 0 provider requests and 6 authentication calls, which leaves 6 provider"
        " requests and 0 authentication calls."
    ) in shown
    assert (
        "The remaining budget can't cover baseline, liquidity-100m, holdings-50,"
        f" {REBALANCE}, {DUE}, so this run won't start them."
    ) in shown
    assert len(cli.server.received) == received
