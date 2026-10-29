"""The budget of an experiment with a ranking definition, through `trialfolio run`: each case's
`rank_update` and backtest count as one provider request each, and their costs sum; an attempt
starts only when both its requests fit, so a repeat the counted requests leave no room for waits
for a revision that raises the budget; and a revision of the definition, of the ranking method, or
from a formula, counts the requests every earlier plan sent.

Traces to R04-AC10, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_budget.py`: `ranking-example.yaml`'s 8 requests count both kinds,
and so does `cost`. After a 503 to a backtest, its repeat isn't started, since its two requests
don't fit the 8 counted, and its confirmation stays unused, until `ranking-budget-raised.yaml`'s
revision lets it repeat. After `ranking-example.yaml`'s four cases succeeded,
`ranking-definition-changed.yaml` retires `baseline` and `value-heavy`, keeps
`tilt-earnings-yield` and `no-sales-yield`, with their attempts, unsent, and sends the two new
cases, whose 4 requests its budget of 12 covers beside the 8 counted; `ranking-method-changed.yaml`
retires every case; and `ranking-from-formula.yaml`, after `example.yaml`, revises plan 1.1.0 into
1.3.0, whose display gives the most the counted backtests can have cost apart from the most the
remaining requests can cost. In every scenario, the server receives no `POST /screen/backtest`
that doesn't follow its own case's `POST /rank`. Also to docs/contracts.md, sending a definition
(counting the requests, and the budget's check), experiment plans and revisions (the budget across
runs), plans with a ranking definition (revisions, and the display's wording), and repeating a
case (the budget).

The pairing's check that a remaining budget of one request never sends a `rank_update` is
`test_a_remaining_budget_of_one_request_covers_no_case`, in
`tests/interface/test_ranking_experiment.py`, which R04-T12 wrote ahead of this task. Each
experiment is written with the experiment builder, through the CLI's entry function in the test
process, with the real client, `requests`, and `urllib3` over the fake server, whose end-of-test
check reads every `POST /rank` body (R04-AC09). The plan display's check runs under a real
pseudo-terminal in the test process. The ranking lock's file is in the test's own directory.
`tests/core/test_ranking_resume.py` makes the same checks at the core.
"""

import json
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    RANK_UPDATED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    returns,
    returns_each,
)
from tests.support.fake_portfolio123 import AUTH, BACKTEST, RANK, FakePortfolio123
from tests.support.saved_records import saved_plan, session_manifest
from tests.support.terminal import PseudoTerminal
from trialfolio.contracts.attempt import AttemptRecordV1_3
from trialfolio.contracts.experiment_manifest import ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecordV1_1

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

EXAMPLE = experiment_config("ranking-example.yaml")
BUDGET_RAISED = experiment_config("revisions/ranking-budget-raised.yaml")
DEFINITION_CHANGED = experiment_config("revisions/ranking-definition-changed.yaml")
METHOD_CHANGED = experiment_config("revisions/ranking-method-changed.yaml")
FORMULA = experiment_config("example.yaml")
FROM_FORMULA = experiment_config("revisions/ranking-from-formula.yaml")
DEFINITIONS = experiment_config("ranking")
REASON = "A revised ranking."

CASE_IDS = {
    "baseline": "case-a8c9e5f0cbee31ad",
    "value-heavy": "case-3dbf62e2f8ee9d8e",
    "tilt-earnings-yield": "case-4aacdc96152316a0",
    "no-sales-yield": "case-600a63188a800a32",
}
"""`ranking-example.yaml`'s cases, by key, as release 0.4.0 gives them, written by hand."""

type Builder = ExperimentBuilder[Outcome]


def attempt_files(out: Path, case_id: str) -> dict[str, bytes]:
    """Every file of the case's attempts, by its path under the case, with its bytes."""
    case = out / "cases" / case_id / "attempts"
    return {
        path.relative_to(case).as_posix(): path.read_bytes()
        for path in sorted(case.rglob("*"))
        if path.is_file()
    }


def each_backtest_follows_its_cases_rank_update(
    server: FakePortfolio123, out: Path, *, since: int = 0
) -> None:
    """Every `POST /screen/backtest` the server received, from its request `since` on, came right
    after a `POST /rank`, and the two are one case's, of a plan 1.3.0 of the experiment in `out`:
    its `rank_update`'s params, and its backtest's, compared as JSON (R04-AC10)."""
    sent = {
        (
            json.dumps(case.requests[0].params.model_dump(mode="json"), sort_keys=True),
            json.dumps(case.requests[1].params.model_dump(mode="json"), sort_keys=True),
        )
        for directory in sorted((out / "plans").iterdir())
        if isinstance(plan := saved_plan(out, int(directory.name)), PlanV1_3)
        for case in plan.cases
    }
    received = server.received
    backtests = 0
    for place, request in enumerate(received):
        if place < since or request.request != BACKTEST:
            continue
        backtests += 1
        previous = received[place - 1]
        assert previous.request == RANK, "a backtest was sent without its rank_update"
        pair = (
            json.dumps(json.loads(previous.body), sort_keys=True),
            json.dumps(json.loads(request.body), sort_keys=True),
        )
        assert pair in sent, "a backtest followed another case's rank_update"
    assert backtests


def completed(cli: Cli, experiments: Builder, out: Path) -> Outcome:
    """`ranking-example.yaml`'s four cases, each succeeded, with `rank-update.json`, whose `cost`
    is 1, and `complete.json`, whose `cost` is 5."""
    outcome = experiments.run(EXAMPLE, out, ranks=[RANK_UPDATED] * 4, sends=returns_each(4))
    assert outcome.exit_code == 0, outcome.stderr
    assert cli.server.requests() == [AUTH, *(RANK, BACKTEST) * 4]
    return outcome


# Both kinds of request count


def test_both_kinds_of_request_count_against_the_budget_and_in_the_cost(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = completed(cli, experiments, out)

    # 4 rank_updates and 4 backtests: the budget's 8 requests, and 4 times 1 and 5 credits.
    assert (outcome.counts["provider_requests"], outcome.counts["cost"]) == (8, 24)
    assert outcome.counts["authentication_calls"] == 1
    totals = session_manifest(out, 1, ExperimentManifestV1_1).counts
    assert (totals.provider_requests, totals.cost) == (8, 24)
    assert (totals.budget.provider_requests, totals.budget.authentication_calls) == (8, 8)
    for case_id in CASE_IDS.values():
        ((path, content),) = [
            (path, content)
            for path, content in attempt_files(out, case_id).items()
            if path.endswith("/attempt.json")
        ]
        record = AttemptRecordV1_3.model_validate_json(content)
        assert (record.ranking_update.provider_metadata.cost, record.provider_metadata.cost) == (
            1,
            5,
        ), path
    each_backtest_follows_its_cases_rank_update(cli.server, out)


# A repeat waits until both its requests fit


def test_a_repeat_the_counted_requests_leave_no_room_for_waits_for_a_raised_budget(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # A 503 to the last case's backtest leaves it unknown, with all 8 requests counted.
    first = experiments.run(
        EXAMPLE, out, ranks=[RANK_UPDATED] * 4, sends=[*returns_each(3), UNAVAILABLE]
    )
    assert first.exit_code == 6, first.stderr
    assert first.counts["provider_requests"] == 8
    attempt = cast("str", first.cases_by_key["no-sales-yield"]["repeat_attempt_id"])
    option = f"no-sales-yield:{attempt}"
    received = cli.server.requests()

    spent = experiments.run(EXAMPLE, out, "--repeat", option)

    # Its two requests don't fit, so it isn't started, and nothing is sent.
    assert spent.exit_code == 6, spent.stderr
    assert spent.error["code"] == "execution.partial"
    assert (
        "The experiment's budget couldn't cover the next case, so it and the cases after it"
        " weren't started. A revision that raises budget.provider_requests lets them run."
    ) in spent.error["message"]
    assert cli.server.requests() == received
    assert spent.counts["provider_requests"] == 8
    assert session_manifest(out, 2, ExperimentManifestV1_1).counts.attempts.repeats == 0
    # Its confirmation is unused, so the summary still names the same attempt.
    assert spent.cases_by_key["no-sales-yield"]["repeat_attempt_id"] == attempt

    raised = experiments.run(
        BUDGET_RAISED,
        out,
        "--revision-reason",
        "A raised budget, for the repeat.",
        "--repeat",
        option,
        ranks=[RANK_UPDATED],
        sends=[returns()],
    )

    # The same confirmation repeats it under the raised budget: both its requests, within 10.
    assert raised.exit_code == 0, raised.stderr
    assert cli.server.requests()[len(received) :] == [AUTH, RANK, BACKTEST]
    assert raised.counts["provider_requests"] == 10
    assert session_manifest(out, 3, ExperimentManifestV1_1).counts.attempts.repeats == 1
    each_backtest_follows_its_cases_rank_update(cli.server, out)


# Revisions count every earlier plan's requests


def test_a_changed_definition_keeps_its_unchanged_cases_attempts_and_sends_two_new_cases(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    completed(cli, experiments, out)
    kept = {
        key: attempt_files(out, CASE_IDS[key]) for key in ("tilt-earnings-yield", "no-sales-yield")
    }
    received = len(cli.server.received)

    revised = experiments.run(
        DEFINITION_CHANGED,
        out,
        "--revision-reason",
        REASON,
        ranks=[RANK_UPDATED] * 2,
        sends=returns_each(2),
    )

    assert revised.exit_code == 0, revised.stderr
    # The session sets out to send the two new cases alone, so the budget never stops it.
    assert "Case 1 of 2 this session:" in revised.stderr
    assert "the budget can't cover" not in revised.stderr
    plan = saved_plan(out, 2)
    assert isinstance(plan, PlanV1_3)
    cases = {case.case_key: case.case_id for case in plan.cases}
    # The two cases whose definitions the revision doesn't change keep their case_ids, and their
    # attempts, as session 1 wrote them, and aren't sent again.
    for key, files in kept.items():
        assert cases[key] == CASE_IDS[key]
        assert attempt_files(out, CASE_IDS[key]) == files
        assert revised.cases_by_key[key]["outcome"] == "succeeded"
    # The other two are new cases, sent with the revised definition: within the budget of 12, the
    # 8 requests counted and their 4.
    assert {key: cases[key] == CASE_IDS[key] for key in ("baseline", "value-heavy")} == {
        "baseline": False,
        "value-heavy": False,
    }
    record = ExperimentRecordV1_1.model_validate_json(
        (out / "plans/2/experiment.json").read_bytes()
    )
    changes = record.plans[-1].changes
    assert changes is not None
    assert [case.case_key for case in changes.cases_retired] == ["baseline", "value-heavy"]
    sent = cli.server.received[received:]
    assert [request.request for request in sent] == [AUTH, RANK, BACKTEST, RANK, BACKTEST]
    revised_definition = (DEFINITIONS / "value-momentum-revised.xml").read_text(encoding="utf-8")
    assert json.loads(sent[1].body)["nodes"] == revised_definition
    assert revised.counts["provider_requests"] == 8 + 4
    assert plan.budget.provider_requests == 12
    each_backtest_follows_its_cases_rank_update(cli.server, out)


def test_a_changed_ranking_method_retires_every_case_and_its_spent_budget_sends_none(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    completed(cli, experiments, out)
    received = cli.server.requests()

    revised = experiments.run(METHOD_CHANGED, out, "--revision-reason", REASON)

    # The ranking method is in every case's ranking row, so every case is new, and the 8
    # requests counted leave the budget of 8 nothing for them.
    assert revised.exit_code == 6, revised.stderr
    assert revised.error["code"] == "execution.partial"
    assert cli.server.requests() == received
    assert revised.counts["cases_retired"] == 4
    new = revised.cases_by_key
    assert {case["outcome"] for case in new.values()} == {"not_yet_run"}
    assert set(new) == set(CASE_IDS)
    assert {cast("str", case["case_id"]) for case in new.values()}.isdisjoint(CASE_IDS.values())
    record = ExperimentRecordV1_1.model_validate_json(
        (out / "plans/2/experiment.json").read_bytes()
    )
    changes = record.plans[-1].changes
    assert changes is not None
    assert [case.case_key for case in changes.cases_retired] == list(CASE_IDS)
    assert revised.counts["provider_requests"] == 8


@posix_only
def test_a_revision_from_a_formula_gives_what_the_counted_backtests_and_the_rest_can_cost(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    first = experiments.run(FORMULA, out, sends=returns_each(5))
    assert first.exit_code == 0, first.stderr
    since = len(cli.server.received)
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", *[RANK_UPDATED] * 5, method="POST")
    cli.server.reply("/screen/backtest", *returns_each(5))

    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        outcome = cli(
            "run",
            FROM_FORMULA,
            "--out",
            out,
            "--json",
            "--revision-reason",
            REASON,
            stdin=terminal.stdin,
            stderr=terminal.stderr,
        )
    shown = terminal.shown()

    assert outcome.exit_code == 0, shown
    # 5 backtests counted, at 5 credits each, apart from the 10 requests that remain, two for
    # each of the 5 new cases, at most 6 credits a case.
    assert (
        "At the documented costs, the requests counted so far can have cost at most 25 credits,"
        " and the 10 provider requests that remain at most 30 credits."
    ) in shown
    assert shown.index("at most 25 credits") < shown.index("Type approve")
    # The revision is plan 1.3.0, which revises plan 1.1.0, and sends both of each new case's
    # requests, within the budget of 15.
    first_plan, second = saved_plan(out, 1), saved_plan(out, 2)
    assert isinstance(first_plan, PlanV1_1) and isinstance(second, PlanV1_3)
    assert second.revises == first_plan.plan_hash
    assert cli.server.requests()[since:] == [AUTH, *(RANK, BACKTEST) * 5]
    assert outcome.counts["provider_requests"] == 5 + 10
    assert outcome.counts["cases_retired"] == 5
    each_backtest_follows_its_cases_rank_update(cli.server, out, since=since)
