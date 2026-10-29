"""`trialfolio run` stops an experiment before it exceeds the current plan's budget, which bounds
the provider requests and the authentication calls across every run: a case, or a repeat, the
budget can't cover isn't started, and neither are the cases after it; a run whose remaining budget
can't cover the first case it would send starts none, and needs no credentials; a `running`
attempt counts as one request; and a revision may set a budget below what's counted, after which
nothing more is sent.

Traces to R03-AC10's interface part, and to docs/contracts.md, the experiment's budget, budget and
retries (within budget), the budget across runs (what's counted, and a budget below it),
repeating a case (the budget: a repeat the remaining budget can't cover isn't started, its
confirmation stays unused, and a revision that raises the budget lets the same confirmation
repeat it), running an experiment (step 7, and a run that sends nothing needs no credentials,
for a due case, as D-38 decided), and the experiment manifest (`counts`). Each test writes
`default-only.yaml`'s experiment, whose budget is its 2 cases, or `example.yaml`'s, whose budget
is 6, with the experiment builder, through the CLI's entry function in the test process, over the
fake server, and runs it again, or a revision of it from `experiment-configs/revisions/`. The
`running` attempt is left by a run the builder kills with `SIGKILL`, under the test launcher,
while the fake server holds the reply to its request.
"""

import sys
from pathlib import Path
from typing import cast

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    REFUSED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    held,
    returns,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.saved_records import attempt_records, session_manifest
from trialfolio.contracts.attempt import AttemptRecordV1_1, StartRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no SIGKILL")

DEFAULT_ONLY = experiment_config("default-only.yaml")
EXAMPLE = experiment_config("example.yaml")
AUTH = "POST /auth"
SEND = "POST /screen/backtest"

BUDGET_SPENT = "The experiment's budget couldn't cover the next case"
"""What `execution.partial`'s message says when the budget stops the run."""

QUOTA = Reply(402, b"")
"""A 402 to a case's request: `failed`, possibly charged, with `provider.quota_exceeded`, which
stops the run before its later cases (D-32)."""

type Builder = ExperimentBuilder[Outcome]


def revision(name: str) -> Path:
    return experiment_config(f"revisions/{name}")


def case_id(outcome: Outcome, key: str) -> str:
    return cast("str", outcome.cases_by_key[key]["case_id"])


def sends(cli: Cli) -> int:
    """How many case requests the server received, across every run of the test."""
    return sum(1 for received in cli.server.received if received.path == "/screen/backtest")


def assert_within_budget(cli: Cli, out: Path, session: int) -> None:
    """The server received at most the budget's provider requests, and the session's manifest
    counts at most that many."""
    counts = session_manifest(out, session, ExperimentManifest).counts
    assert sends(cli) <= counts.budget.provider_requests
    assert counts.provider_requests <= counts.budget.provider_requests


def test_a_repeat_the_spent_budget_cant_cover_waits_for_a_revision_that_raises_it(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # A 503 leaves the baseline unknown, and the other case is sent: 2 requests, the budget.
    first = experiments.run(DEFAULT_ONLY, out, sends=[UNAVAILABLE, returns()])
    assert first.exit_code == 6, first.stderr
    assert cli.server.requests() == [AUTH, SEND, SEND]
    assert [case["outcome"] for case in first.cases_by_key.values()] == ["unknown", "succeeded"]
    baseline = case_id(first, "baseline")
    (unknown,) = attempt_records(out, baseline, AttemptRecordV1_1)
    option = f"baseline:{unknown.attempt_id}"
    assert_within_budget(cli, out, 1)

    # A confirmed repeat of the baseline isn't started: the budget is spent.
    spent = experiments.run(DEFAULT_ONLY, out, "--repeat", option)

    assert spent.exit_code == 6, spent.stderr
    assert len(cli.server.received) == 3
    error = spent.error
    assert error["code"] == "execution.partial"
    assert BUDGET_SPENT in error["message"]
    # Its confirmation stays unused: the case still awaits a repeat of the same attempt.
    assert "isn't repeated" not in spent.stderr
    assert attempt_records(out, baseline, AttemptRecordV1_1) == [unknown]
    assert spent.cases_by_key["baseline"]["repeat_attempt_id"] == str(unknown.attempt_id)
    counts = session_manifest(out, 2, ExperimentManifest).counts
    assert (counts.provider_requests, counts.budget.provider_requests) == (2, 2)
    assert counts.attempts.repeats == 0
    assert_within_budget(cli, out, 2)

    # A revision that raises the budget to 3 lets the same confirmation repeat it.
    raised = experiments.run(
        revision("default-only-budget-3.yaml"),
        out,
        "--revision-reason",
        "A third request, for the baseline's repeat.",
        "--repeat",
        option,
        sends=[returns()],
    )

    assert raised.exit_code == 0, raised.stderr
    assert cli.server.requests()[3:] == [AUTH, SEND]
    repeat = attempt_records(out, baseline, AttemptRecordV1_1)[-1]
    assert (repeat.outcome, repeat.repeat_of) == ("succeeded", unknown.attempt_id)
    counts = session_manifest(out, 3, ExperimentManifest).counts
    assert (counts.provider_requests, counts.budget.provider_requests) == (3, 3)
    assert counts.attempts.repeats == 1
    assert_within_budget(cli, out, 3)


def test_a_due_case_the_spent_budget_cant_cover_needs_no_credentials(
    cli: Cli, experiments: Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # A 402 fails the baseline, and stops the run, so the other case is still due.
    first = experiments.run(DEFAULT_ONLY, out, sends=[QUOTA])
    assert first.exit_code == 6, first.stderr
    baseline, other = case_id(first, "baseline"), case_id(first, "rebalance-weeks-1")
    (failed,) = attempt_records(out, baseline, AttemptRecordV1_1)
    # The baseline's repeat takes the budget's second and last request, so the due case isn't
    # started.
    repeated = experiments.run(
        DEFAULT_ONLY, out, "--repeat", f"baseline:{failed.attempt_id}", sends=[returns()]
    )
    assert repeated.exit_code == 6, repeated.stderr
    assert BUDGET_SPENT in repeated.error["message"]
    assert repeated.cases_by_key["rebalance-weeks-1"]["outcome"] == "not_yet_run"
    monkeypatch.delenv("TRIALFOLIO_P123_API_ID")
    monkeypatch.delenv("TRIALFOLIO_P123_API_KEY")
    received = len(cli.server.received)

    outcome = experiments.run(DEFAULT_ONLY, out)

    # The due case is the first case the run would send, and the remaining budget can't cover
    # it, so the run starts nothing, and needs no credentials (D-38).
    assert outcome.exit_code == 6, outcome.stderr
    assert len(cli.server.received) == received
    error = outcome.error
    assert error["code"] == "execution.partial"
    assert BUDGET_SPENT in error["message"]
    assert attempt_records(out, other, AttemptRecordV1_1) == []
    assert session_manifest(out, 3, ExperimentManifest).outcome == "partial"
    assert_within_budget(cli, out, 3)


def test_once_the_authentication_calls_are_spent_no_case_starts(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # Each run's authentication call gets a 401, so no request is sent, and each run stops.
    for session in (1, 2):
        ran = experiments.run(DEFAULT_ONLY, out, authenticates=[REFUSED])
        assert ran.exit_code == 6, ran.stderr
        assert_within_budget(cli, out, session)
    assert cli.server.requests() == [AUTH, AUTH]
    counts = session_manifest(out, 2, ExperimentManifest).counts
    assert (counts.authentication_calls, counts.provider_requests) == (2, 0)
    attempts = sorted((out / "cases").glob("*/attempts/*"))
    assert len(attempts) == 2

    third = experiments.run(DEFAULT_ONLY, out, authenticates=[REFUSED])

    assert third.exit_code == 6, third.stderr
    # No authentication call, and no case started.
    assert len(cli.server.received) == 2
    assert sorted((out / "cases").glob("*/attempts/*")) == attempts
    counts = session_manifest(out, 3, ExperimentManifest).counts
    assert (counts.authentication_calls, counts.provider_requests) == (2, 0)
    assert (counts.cases.failed, counts.cases.not_yet_run) == (1, 1)
    assert_within_budget(cli, out, 3)
    error = third.error
    assert error["code"] == "execution.partial"
    # The message says that the budget's authentication calls are spent, though 2 of its
    # provider requests remain.
    assert "The experiment's budget of authentication calls is spent" in error["message"]
    assert "budget couldn't cover the next case" not in error["message"]


@posix_only
def test_a_running_attempt_counts_as_one_request(cli: Cli, experiments: Builder) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # Killed while the server holds the reply to the baseline's request: its start record is
    # written, and its attempt record isn't.
    experiments.kill(DEFAULT_ONLY, out, sends=[held(returns())], received=2)
    (started,) = (out / "cases").glob("*/attempts/*/started.json")
    assert not (started.parent / "attempt.json").exists()
    start = StartRecordV1_1.model_validate_json(started.read_bytes())
    received = len(cli.server.received)

    # The repeat of the baseline is covered, with the running attempt's request counted, and the
    # other case, after it, isn't.
    resumed = experiments.run(
        DEFAULT_ONLY, out, "--repeat", f"baseline:{start.attempt_id}", sends=[returns()]
    )

    assert (
        "Counted so far, across every run of the experiment: 1 provider request and 1"
        " authentication call, which leaves 1 provider request and 1 authentication call."
    ) in resumed.stderr
    assert resumed.exit_code == 6, resumed.stderr
    assert cli.server.requests()[received:] == [AUTH, SEND]
    cases = resumed.cases_by_key
    assert (cases["baseline"]["outcome"], cases["rebalance-weeks-1"]["outcome"]) == (
        "succeeded",
        "not_yet_run",
    )
    assert BUDGET_SPENT in resumed.error["message"]
    first, repeat = attempt_records(out, start.case_id, AttemptRecordV1_1)
    assert (first.attempt_id, first.outcome, first.possibly_charged) == (
        start.attempt_id,
        "unknown",
        True,
    )
    assert repeat.repeat_of == start.attempt_id
    counts = session_manifest(out, 2, ExperimentManifest).counts
    assert (counts.provider_requests, counts.budget.provider_requests) == (2, 2)
    assert_within_budget(cli, out, 2)


def test_a_revision_may_lower_the_budget_below_whats_counted_and_then_sends_nothing(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # example.yaml's five requests, and a repeat of holdings-50 that ends unknown: six in all,
    # the budget.
    first = experiments.run(
        EXAMPLE, out, sends=[returns(), returns(), UNAVAILABLE, returns(), returns()]
    )
    assert first.exit_code == 6, first.stderr
    holdings = case_id(first, "holdings-50")
    (unknown,) = attempt_records(out, holdings, AttemptRecordV1_1)
    repeated = experiments.run(
        EXAMPLE, out, "--repeat", f"holdings-50:{unknown.attempt_id}", sends=[UNAVAILABLE]
    )
    assert repeated.exit_code == 6, repeated.stderr
    repeat = attempt_records(out, holdings, AttemptRecordV1_1)[-1]
    assert (repeat.outcome, repeat.repeat_of) == ("unknown", unknown.attempt_id)
    assert session_manifest(out, 2, ExperimentManifest).counts.provider_requests == 6
    received = len(cli.server.received)

    # The revision lowers the budget to 5, with the confirmation of another repeat too.
    lowered = experiments.run(
        revision("budget-lowered.yaml"),
        out,
        "--revision-reason",
        "Five requests are enough.",
        "--repeat",
        f"holdings-50:{repeat.attempt_id}",
    )

    assert lowered.exit_code == 6, lowered.stderr
    assert len(cli.server.received) == received
    assert BUDGET_SPENT in lowered.error["message"]
    assert (out / "plans/2/experiment.json").is_file()
    assert attempt_records(out, holdings, AttemptRecordV1_1)[-1] == repeat
    session = session_manifest(out, 3, ExperimentManifest)
    assert session.plan == 2
    counts = session.counts
    assert (counts.provider_requests, counts.budget.provider_requests) == (6, 5)
    assert counts.attempts.repeats == 1
