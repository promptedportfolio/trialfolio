"""A resumed experiment with a ranking definition, through `trialfolio run`: an attempt stopped
during its `rank_update`, or after it and before its backtest was sent, is recorded on resume as
possibly charged, its case awaits a repeat and isn't sent again on its own, and a confirmed repeat
sends its `rank_update` and its backtest again, once.

Traces to R04-AC10, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_resume.py`: a run killed with `SIGKILL` while the server holds a
case's `rank_update` reply leaves `rank-update-request.json` and `updating.json` alone; the resume
writes its attempt record, `unknown` and possibly charged, with `POST /rank` `interrupted` and
`command.interrupted`, counts it as one request, and doesn't send the case, which the plan display
lists as awaiting a repeat, with the option that repeats it. A `KeyboardInterrupt` at the
backtest's `request.json`, after the `rank_update`'s response was saved, leaves the attempt
`failed` and possibly charged; and, with storage faults at both of the attempt record's writes,
the resume records `POST /rank` as a 200 with `completed_from_saved_response`. Neither case is
sent again without `--repeat`. A confirmed repeat sends `POST /rank`, then `POST /screen/backtest`,
with `repeat_of`, and the same command, run again, doesn't repeat it. In every scenario, no
`POST /screen/backtest` reaches the server but right after its own case's `POST /rank`. Also to
docs/contracts.md, sending a definition (an attempt stopped after its update record, and counting
the requests) and repeating a case (one confirmation, one repeat, and the budget).

Each experiment is written with the experiment builder, through the CLI's entry function in the
test process, with the real client, `requests`, and `urllib3` over the fake server, whose
end-of-test check reads every `POST /rank` body (R04-AC09); and stopped where the test needs it:
by an interrupt from the storage faults, with storage faults at both writes of an attempt record,
or by `SIGKILL`, under the test launcher in a new process, while the fake server holds a reply.
The plan display's check runs under a real pseudo-terminal in the test process. The ranking lock's
file is in the test's own directory. `tests/core/test_ranking_resume.py` makes the same checks at
the core.
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    RANK_UPDATED,
    ExperimentBuilder,
    experiment_config,
    held,
    returns,
    returns_each,
)
from tests.support.fake_portfolio123 import AUTH, BACKTEST, RANK, FakePortfolio123
from tests.support.saved_records import (
    attempt_directories,
    attempt_records,
    saved_plan,
    session_manifest,
)
from tests.support.storage_faults import FaultyStores
from tests.support.terminal import PseudoTerminal
from trialfolio.contracts.attempt import AttemptRecordV1_3, StartRecordV1_3
from trialfolio.contracts.experiment_manifest import ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_3

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no SIGKILL and no pseudo-terminals"
)

EXAMPLE = experiment_config("ranking-example.yaml")
BUDGET_RAISED = experiment_config("revisions/ranking-budget-raised.yaml")
RAISED = "A raised budget, for the repeat."

CASE_IDS = {
    "baseline": "case-a8c9e5f0cbee31ad",
    "value-heavy": "case-3dbf62e2f8ee9d8e",
    "tilt-earnings-yield": "case-4aacdc96152316a0",
    "no-sales-yield": "case-600a63188a800a32",
}
"""`ranking-example.yaml`'s cases, by key, as release 0.4.0 gives them, written by hand."""

type Builder = ExperimentBuilder[Outcome]


def names(directory: Path) -> set[str]:
    return {path.name for path in directory.iterdir()}


def exchanges(record: AttemptRecordV1_3) -> list[tuple[str, str, int | None, str | None]]:
    return [(e.request, e.result, e.status, e.note) for e in record.exchanges]


def each_backtest_follows_its_cases_rank_update(server: FakePortfolio123, out: Path) -> None:
    """Every `POST /screen/backtest` the server received came right after a `POST /rank`, and the
    two are one case's, of a plan of the experiment in `out`: its `rank_update`'s params, and its
    backtest's, compared as JSON (R04-AC10)."""
    sent = {
        (
            json.dumps(case.requests[0].params.model_dump(mode="json"), sort_keys=True),
            json.dumps(case.requests[1].params.model_dump(mode="json"), sort_keys=True),
        )
        for plan in sorted((out / "plans").iterdir())
        for case in saved_plan(out, int(plan.name), PlanV1_3).cases
    }
    received = server.received
    backtests = 0
    for place, request in enumerate(received):
        if request.request != BACKTEST:
            continue
        backtests += 1
        previous = received[place - 1]
        assert place > 0 and previous.request == RANK, "a backtest was sent without its rank_update"
        pair = (
            json.dumps(json.loads(previous.body), sort_keys=True),
            json.dumps(json.loads(request.body), sort_keys=True),
        )
        assert pair in sent, "a backtest followed another case's rank_update"
    assert backtests


# An attempt killed during its rank_update


def killed_value_heavy(cli: Cli, experiments: Builder, out: Path) -> StartRecordV1_3:
    """Runs `ranking-example.yaml` in a new process, and kills it with `SIGKILL` while the server
    holds `value-heavy`'s `rank_update` reply, after the baseline succeeded. Returns that attempt's
    update record, its only record."""
    experiments.kill(
        EXAMPLE,
        out,
        ranks=[RANK_UPDATED, held(RANK_UPDATED)],
        sends=[returns()],
        received=4,
    )
    assert cli.server.requests() == [AUTH, RANK, BACKTEST, RANK]
    (directory,) = attempt_directories(out, CASE_IDS["value-heavy"])
    # It sends with the session's token, so it has no authentication record: the request's file
    # and the update record, its last write before the send, are all it wrote.
    assert names(directory) == {"rank-update-request.json", "updating.json"}
    assert not (out / "sessions/1/manifest.json").exists()
    return StartRecordV1_3.model_validate_json((directory / "updating.json").read_bytes())


@posix_only
def test_a_rank_update_killed_mid_flight_is_recorded_unknown_and_awaits_a_repeat_unsent(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    update = killed_value_heavy(cli, experiments, out)
    value_heavy = CASE_IDS["value-heavy"]
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", RANK_UPDATED, RANK_UPDATED, method="POST")
    cli.server.reply("/screen/backtest", *returns_each(2))
    received = len(cli.server.received)

    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        outcome = cli(
            "run", EXAMPLE, "--out", out, "--json", stdin=terminal.stdin, stderr=terminal.stderr
        )
    shown = terminal.shown()

    # The plan display lists it as awaiting a repeat, with the option that repeats it.
    option = f"--repeat value-heavy:{update.attempt_id}"
    awaiting = (
        "So far: unknown (command.interrupted), after 1 attempt. Its rank_update, or its"
        " backtest, may have reached Portfolio123, and may have been charged, so it's sent again"
        f" only by a repeat, which sends both again, and may be charged again: {option}"
    )
    case_line = f"Case value-heavy ({value_heavy}):"
    assert shown.index(case_line) < shown.index(awaiting) < shown.index("Type approve")
    assert outcome.exit_code == 6, shown
    assert outcome.error_code == "execution.partial"
    assert outcome.cases_by_key["value-heavy"] == {
        "case_key": "value-heavy",
        "case_id": value_heavy,
        "outcome": "unknown",
        "repeat_attempt_id": str(update.attempt_id),
    }
    # The resume sends the two cases that are due, each its rank_update then its backtest, and
    # not value-heavy's again.
    assert cli.server.requests()[received:] == [AUTH, RANK, BACKTEST, RANK, BACKTEST]
    each_backtest_follows_its_cases_rank_update(cli.server, out)
    # Its attempt record, which the resume wrote, keeps what its update record holds: unknown
    # and possibly charged, since its rank_update may or may not have taken effect.
    (record,) = attempt_records(out, value_heavy, AttemptRecordV1_3)
    assert (record.attempt_id, record.session, record.sequence) == (
        update.attempt_id,
        update.session,
        update.sequence,
    )
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert exchanges(record) == [(RANK, "interrupted", None, None)]
    assert record.ranking_update.request is not None
    assert record.ranking_update.request.path.endswith("/rank-update-request.json")
    assert (record.ranking_update.response, record.request, record.response) == (None, None, None)
    # It counts as one request: its rank_update. The three others count two each.
    assert session_manifest(out, 2, ExperimentManifestV1_1).counts.provider_requests == 1 + 2 * 3
    assert outcome.counts["provider_requests"] == 7


# An attempt stopped after its rank_update's response was saved


def interrupted_baseline(experiments: Builder, faults: FaultyStores, out: Path) -> Outcome:
    """Runs `ranking-example.yaml` with a `KeyboardInterrupt` at the baseline's backtest's
    `request.json`, once its `rank_update`'s 200 was saved, so its backtest isn't sent."""
    interrupted = experiments.run(EXAMPLE, out, ranks=[RANK_UPDATED], store_factory=faults)
    assert interrupted.exit_code == 130, interrupted.stderr
    assert interrupted.error_code == "command.interrupted"
    return interrupted


def test_an_interrupt_at_the_backtests_request_leaves_the_attempt_failed_and_unsent_again(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    baseline = CASE_IDS["baseline"]
    faults.fail_before(f"{baseline}/request.json", KeyboardInterrupt())

    interrupted = interrupted_baseline(experiments, faults, out)

    assert cli.server.requests() == [AUTH, RANK]
    message = interrupted.error["message"]
    assert (
        "The rank_update request, which writes the case's ranking definition into"
        " ApiRankingSystem, reached Portfolio123, and may have been charged. The screen backtest"
        " request wasn't sent."
    ) in message
    (directory,) = attempt_directories(out, baseline)
    assert names(directory) == {
        "authenticating.json",
        "rank-update-request.json",
        "updating.json",
        "rank-update-response.json",
        "attempt.json",
    }
    # The attempt records itself: failed, since its backtest was never sent, and possibly
    # charged, since its rank_update reached Portfolio123.
    (record,) = attempt_records(out, baseline, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert exchanges(record) == [(AUTH, "response", 200, None), (RANK, "response", 200, None)]
    received = len(cli.server.received)

    resumed = experiments.run(EXAMPLE, out, ranks=[RANK_UPDATED] * 3, sends=returns_each(3))

    # Without --repeat, it isn't sent again: only the three cases that are due are.
    assert resumed.exit_code == 6, resumed.stderr
    assert cli.server.requests()[received:] == [AUTH, *(RANK, BACKTEST) * 3]
    each_backtest_follows_its_cases_rank_update(cli.server, out)
    assert attempt_records(out, baseline, AttemptRecordV1_3) == [record]
    assert resumed.cases_by_key["baseline"] == {
        "case_key": "baseline",
        "case_id": baseline,
        "outcome": "failed",
        "repeat_attempt_id": str(record.attempt_id),
    }
    assert session_manifest(out, 2, ExperimentManifestV1_1).counts.provider_requests == 1 + 2 * 3


def test_an_attempt_record_unwritten_after_the_rank_updates_response_is_recorded_from_it(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    baseline = CASE_IDS["baseline"]
    faults.fail_before(f"{baseline}/request.json", KeyboardInterrupt())
    # Both writes of its attempt.json fail: the first is interrupted before it starts, and the
    # second, which an interrupt gives a record that wasn't published, fails as a full disk would.
    faults.fail_before(f"{baseline}/attempt.json", KeyboardInterrupt())
    faults.fail_os(f"{baseline}/attempt.json")

    interrupted_baseline(experiments, faults, out)

    (directory,) = attempt_directories(out, baseline)
    assert names(directory) == {
        "authenticating.json",
        "rank-update-request.json",
        "updating.json",
        "rank-update-response.json",
    }
    received = len(cli.server.received)

    resumed = experiments.run(EXAMPLE, out, ranks=[RANK_UPDATED] * 3, sends=returns_each(3))

    assert resumed.exit_code == 6, resumed.stderr
    assert cli.server.requests()[received:] == [AUTH, *(RANK, BACKTEST) * 3]
    each_backtest_follows_its_cases_rank_update(cli.server, out)
    # The resume writes its attempt record from its update record and its saved response: its
    # rank_update got a 200, completed from that response, and its backtest was never sent.
    (record,) = attempt_records(out, baseline, AttemptRecordV1_3)
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert exchanges(record) == [
        (AUTH, "response", 200, None),
        (RANK, "response", 200, "completed_from_saved_response"),
    ]
    response = record.ranking_update.response
    assert response is not None and response.form == "decoded"
    assert response.path == (
        f"cases/{baseline}/attempts/{directory.name}/rank-update-response.json"
    )
    assert record.ranking_update.provider_metadata.cost == 1
    assert (record.request, record.response) == (None, None)
    assert resumed.cases_by_key["baseline"]["repeat_attempt_id"] == str(record.attempt_id)
    assert session_manifest(out, 2, ExperimentManifestV1_1).counts.provider_requests == 1 + 2 * 3


# A confirmed repeat sends both again, once


class Stopped(NamedTuple):
    """A case whose attempt a stop left possibly charged, awaiting a repeat."""

    key: str
    attempt: str
    """The stopped attempt's ID."""
    due: int
    """How many cases a resume then sends."""


def stop_value_heavy_during_its_rank_update(
    cli: Cli, experiments: Builder, faults: FaultyStores, out: Path
) -> Stopped:
    """`value-heavy`, killed with `SIGKILL` during its `rank_update`, after the baseline
    succeeded: its attempt's update record is its only record, and the two cases after it are
    due."""
    return Stopped("value-heavy", str(killed_value_heavy(cli, experiments, out).attempt_id), 2)


def stop_the_baseline_before_its_backtest(
    cli: Cli, experiments: Builder, faults: FaultyStores, out: Path
) -> Stopped:
    """The baseline, interrupted at its backtest's `request.json`, once its `rank_update`'s 200
    was saved: its attempt record is written, and the three cases after it are due."""
    faults.fail_before(f"{CASE_IDS['baseline']}/request.json", KeyboardInterrupt())
    interrupted_baseline(experiments, faults, out)
    (record,) = attempt_records(out, CASE_IDS["baseline"], AttemptRecordV1_3)
    return Stopped("baseline", str(record.attempt_id), 3)


STOPS: dict[str, Callable[[Cli, Builder, FaultyStores, Path], Stopped]] = {
    "killed": stop_value_heavy_during_its_rank_update,
    "interrupted": stop_the_baseline_before_its_backtest,
}


@pytest.mark.parametrize(
    "stopped",
    [pytest.param("killed", marks=posix_only), "interrupted"],
    ids=["killed during its rank_update", "interrupted before its backtest"],
)
def test_a_confirmed_repeat_sends_the_rank_update_then_the_backtest_once(
    cli: Cli, experiments: Builder, faults: FaultyStores, stopped: str
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    key, attempt, due = STOPS[stopped](cli, experiments, faults, out)
    sends = returns_each(due)
    resumed = experiments.run(EXAMPLE, out, ranks=[RANK_UPDATED] * len(sends), sends=sends)
    assert resumed.exit_code == 6, resumed.stderr
    # Seven of the budget's 8 requests are counted, so the repeat's two need the raised budget.
    assert resumed.counts["provider_requests"] == 7
    option = f"{key}:{attempt}"
    received = len(cli.server.received)

    repeated = experiments.run(
        BUDGET_RAISED,
        out,
        "--revision-reason",
        RAISED,
        "--repeat",
        option,
        ranks=[RANK_UPDATED],
        sends=[returns()],
    )

    assert repeated.exit_code == 0, repeated.stderr
    assert cli.server.requests()[received:] == [AUTH, RANK, BACKTEST]
    each_backtest_follows_its_cases_rank_update(cli.server, out)
    stopped_record, repeat = attempt_records(out, CASE_IDS[key], AttemptRecordV1_3)
    assert str(stopped_record.attempt_id) == attempt
    assert (repeat.outcome, str(repeat.repeat_of), repeat.session) == ("succeeded", attempt, 3)
    assert exchanges(repeat) == [
        (AUTH, "response", 200, None),
        (RANK, "response", 200, None),
        (BACKTEST, "response", 200, None),
    ]
    assert repeated.cases_by_key[key]["outcome"] == "succeeded"
    assert session_manifest(out, 3, ExperimentManifestV1_1).counts.attempts.repeats == 1
    assert session_manifest(out, 3, ExperimentManifestV1_1).counts.provider_requests == 7 + 2

    # The same command, run again, doesn't repeat it: its confirmation is used.
    received = len(cli.server.received)
    again = experiments.run(BUDGET_RAISED, out, "--revision-reason", RAISED, "--repeat", option)

    assert again.exit_code == 0, again.stderr
    assert len(cli.server.received) == received
    assert (
        f"Case {key} isn't repeated: the repeat confirmed for its attempt {attempt} was made"
        " already"
    ) in again.stderr
    assert len(attempt_records(out, CASE_IDS[key], AttemptRecordV1_3)) == 2
    assert session_manifest(out, 4, ExperimentManifestV1_1).counts.attempts.repeats == 1
