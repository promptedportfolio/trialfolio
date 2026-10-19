"""`trialfolio run` of an experiment configuration whose baseline's ranking is a definition: it
reads the configuration 1.1.0, its definition, and its ranking variants in step 2, shows the plan
with each case's definition, obtains its approval, gives the core the ranking lock's file, and
runs each case's `rank_update`, then its backtest; run again into its own directory, it resumes
or revises the experiment, and the repeat's prompt counts two requests a case.

Traces to R04-AC01 through the CLI, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_experiment.py`: under the terminal, the full plan display gives that
the run overwrites `ApiRankingSystem`, and what the lock can't exclude; the definition's source;
each node's weight, and each variant's change; each case's `case_id`, its `rank_update` with its
definition line by line, and its hash, then its backtest; and the budget, with each operation's
cost and 6 credits a case; before the prompt, and the server receives nothing until `approve` is
typed. Without a terminal, stderr gives only the plan hash, the budget, and the line that the run
overwrites `ApiRankingSystem`; and without `--approve`, `run --json` creates no output directory,
and gives `ids.plan_hash` and the cases. Also to the repeat's prompt and the plan display's
budget, with two requests a case (docs/contracts.md, repeating a case, the budget; plans with a
ranking definition, the display); to R04-AC08's interface checks that R04-T10 left to R04-T12, for
`ranking-example.yaml` naming a snapshot, a synthetic one included; and to an experiment
configuration 1.1.0 ranked by a formula, which gives plan 1.1.0, as 0.4.0's planner gives it,
and resumes. R04-T12 wrote them. The checks of the budget and the resume that R04-AC10 pairs with
`test_ranking_budget.py` and `test_ranking_resume.py` are R04-T13's.
"""

import json
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, FaultyStores, Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    RANK_UPDATED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.snapshot_builder import SnapshotBuilder, naming
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

EXAMPLE = experiment_config("ranking-example.yaml")
BUDGET_RAISED = experiment_config("revisions/ranking-budget-raised.yaml")
DEFINITION_CHANGED = experiment_config("revisions/ranking-definition-changed.yaml")
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RESPONSES = FIXTURES / "responses"
DEFINITION_HASH = "sha256:6bc59b992f83d5e4c245f37f187651ed18de6b9cb5949ac9f29b743273b26895"
OVERWRITES = (
    "This run overwrites ApiRankingSystem, a ranking system in your Portfolio123 account, with"
    " each case's ranking definition."
)
CASES = ("baseline", "value-heavy", "tilt-earnings-yield", "no-sales-yield")


def four(reply: Reply) -> tuple[Reply, ...]:
    return (reply,) * 4


def error_code(outcome: Outcome) -> str:
    return cast("dict[str, str]", outcome.summary["error"])["code"]


def message(outcome: Outcome) -> str:
    return cast("dict[str, str]", outcome.summary["error"])["message"]


def counts(outcome: Outcome) -> dict[str, object]:
    return cast("dict[str, object]", outcome.summary["counts"])


def summary_cases(outcome: Outcome) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", outcome.summary["cases"])


def read_plan(out: Path, number: int = 1) -> PlanV1_3:
    return PlanV1_3.model_validate_json((out / "plans" / str(number) / "plan.json").read_bytes())


def in_sequence(shown: str, texts: list[str]) -> int:
    """Where the last of `texts` is in `shown`, each found after the one before it."""
    at = 0
    for text in texts:
        at = shown.index(text, at)
    return at


def pairs(requests: list[str]) -> bool:
    """Whether each `POST /screen/backtest` follows its own `POST /rank`, with nothing between."""
    sends = [request for request in requests if request != "POST /auth"]
    return sends[0::2] == ["POST /rank"] * (len(sends) // 2) and sends[1::2] == [
        "POST /screen/backtest"
    ] * (len(sends) // 2)


# The plan, and its approval


@posix_only
def test_under_a_terminal_the_plan_shows_each_cases_definition_and_nothing_is_sent_first(
    cli: Cli,
) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", *four(RANK_UPDATED), method="POST")
    cli.server.reply("/screen/backtest", *four(returns()))
    out = cli.tmp / "experiment"
    expected_hash = plan_hash(EXAMPLE, out)

    with cli.on_terminal("run", EXAMPLE, "--out", out) as terminal:
        terminal.wait_for("Type approve")
        shown = terminal.shown()
        received_before = cli.server.requests()
        terminal.press("approve\n")
        exit_code = terminal.wait()

    assert received_before == []
    assert exit_code == 0, terminal.shown()
    prompt = shown.index("Type approve to run this plan")
    plan = read_plan(out)
    in_order = [
        f"Experiment plan {expected_hash}",
        OVERWRITES,
        (
            "Nothing keeps Portfolio123's website, or another machine, from writing or using it"
            " at the same time."
        ),
        f"The ranking definition's source: a file, by the definition's hash, {DEFINITION_HASH}.",
        "ranking_weight Value: 40 (verified)",
        "ranking_weight Value/Sales Yield: 50 (verified)",
    ]
    for case in plan.cases:
        rank_update = case.requests[0].params
        in_order += [
            f"Case {case.case_key} ({case.case_id}):",
            "The request, exactly as p123api's rank_update will send it to Portfolio123",
            f"line by line:\n      {rank_update.nodes.splitlines()[0]}",
            "The request, exactly as p123api's screen_backtest will send it to Portfolio123:",
        ]
    in_order += [
        (
            "Budget: at most 8 provider requests, each sent at most once: 24 credits at most, at"
            " Portfolio123's documented costs of 1 credit per rank_update (API functions: Rank,"
            " checked 2026-10-12) and 5 credits per screen_backtest (API: Screen, checked"
            " 2026-10-01)."
        ),
        "two requests that can cost 6 credits.",
        f"Plan hash: {expected_hash}",
    ]
    assert in_sequence(shown, in_order) < prompt
    # Each variant's change, and each case's definition, by its hash.
    assert "ranking: sets the weights of Value to 60, Momentum to 20, Quality to 20" in shown
    assert (
        "ranking: removes the factor Value/Sales Yield, and sets the weights of"
        " Value/Earnings Yield to 100"
    ) in shown
    for case in plan.cases:
        assert f"the definition {case.settings[3].model_dump()['value']['definition']}" in shown
    # The definition, line by line, with its tabs, not as one JSON string among the params.
    assert '      \t<Composite Name="Value" Weight="60" RankType="Summation">' in shown
    assert '"nodes"' not in shown
    assert pairs(cli.server.requests())


def test_without_approval_the_plan_hash_and_the_cases_are_given_and_nothing_is_written(
    cli: Cli,
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = cli("run", EXAMPLE, "--out", out, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome) == "plan.approval_required"
    assert not out.exists()
    assert cli.server.requests() == []
    assert cast("dict[str, str]", outcome.summary["ids"])["plan_hash"] == plan_hash(EXAMPLE, out)
    assert [case["case_key"] for case in summary_cases(outcome)] == list(CASES)
    assert {case["outcome"] for case in summary_cases(outcome)} == {"not_yet_run"}
    assert counts(outcome)["cases_planned"] == 4
    lines = outcome.stderr.splitlines()
    assert lines[0] == f"Plan hash: {plan_hash(EXAMPLE, out)}"
    assert OVERWRITES in lines
    for text in ("<RankingSystem", "Composite", "Earnings Yield", "value-heavy", DEFINITION_HASH):
        assert text not in outcome.stderr


def test_before_its_plan_the_summary_counts_the_ranking_variants_cases(cli: Cli) -> None:
    """A failure after the configuration is read and before the plan is built, such as an output
    path whose parent is a file, gives a new experiment's counts, each case not yet run, its
    ranking variants' cases included (JSON summary, an experiment's counts)."""
    cli.ready()
    parent = cli.tmp / "a-file"
    parent.write_bytes(b"not a directory\n")

    outcome = cli("run", EXAMPLE, "--out", parent / "experiment", "--json")

    assert outcome.exit_code == 4, outcome.stderr
    assert "cases" not in outcome.summary
    assert (counts(outcome)["cases_planned"], counts(outcome)["cases_not_yet_run"]) == (4, 4)
    assert cli.server.requests() == []


# The run, the resume, and a revision


def test_an_approved_experiment_sends_each_cases_rank_update_then_its_backtest(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = experiments.run(EXAMPLE, out, ranks=four(RANK_UPDATED), sends=four(returns()))

    assert outcome.exit_code == 0, outcome.stderr
    requests = cli.server.requests()
    assert requests[0] == "POST /auth"
    assert len(requests) == 9
    assert pairs(requests)
    plan = read_plan(out)
    for case, received in zip(
        plan.cases, [r for r in cli.server.received if r.request == "POST /rank"], strict=True
    ):
        assert json.loads(received.body)["nodes"] == case.requests[0].params.nodes
    assert (out / "plans" / "1" / "definition.xml").read_bytes() == (
        FIXTURES / "experiment-configs" / "ranking" / "value-momentum.xml"
    ).read_bytes()
    assert {key: counts(outcome)[key] for key in ("attempts", "provider_requests", "cost")} == {
        "attempts": 4,
        "provider_requests": 8,
        "cost": 24,
    }
    assert {case["outcome"] for case in summary_cases(outcome)} == {"succeeded"}


def test_a_complete_experiment_resumes_without_credentials_and_sends_nothing(
    cli: Cli, experiments: ExperimentBuilder[Outcome], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`trialfolio run` reads an experiment with a ranking definition's records since R04-T12;
    a resume that sends nothing needs no credentials, and takes no ranking lock."""
    cli.ready()
    out = cli.tmp / "experiment"
    assert (
        experiments.run(EXAMPLE, out, ranks=four(RANK_UPDATED), sends=four(returns())).exit_code
        == 0
    )
    received = cli.server.requests()
    monkeypatch.delenv("TRIALFOLIO_P123_API_ID")
    monkeypatch.delenv("TRIALFOLIO_P123_API_KEY")

    resumed = experiments.run(EXAMPLE, out)

    assert resumed.exit_code == 0, resumed.stderr
    assert cast("dict[str, object]", resumed.summary["ids"])["session"] == 2
    assert cli.server.requests() == received


def test_a_revised_definition_sends_only_the_cases_it_adds(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """`ranking-definition-changed.yaml` retires `baseline` and `value-heavy`, keeps the two
    cases whose definitions don't change, and sends the two new ones, each with its `rank_update`
    and its backtest (plans with a ranking definition, revisions)."""
    cli.ready()
    out = cli.tmp / "experiment"
    assert (
        experiments.run(EXAMPLE, out, ranks=four(RANK_UPDATED), sends=four(returns())).exit_code
        == 0
    )
    before = len(cli.server.requests())

    revised = experiments.run(
        DEFINITION_CHANGED,
        out,
        "--revision-reason",
        "The Value factors weigh 60 and 40.",
        ranks=(RANK_UPDATED, RANK_UPDATED),
        sends=(returns(), returns()),
    )

    assert revised.exit_code == 0, revised.stderr
    sent = cli.server.requests()[before:]
    assert sent == [
        "POST /auth",
        "POST /rank",
        "POST /screen/backtest",
        "POST /rank",
        "POST /screen/backtest",
    ]
    assert counts(revised)["cases_retired"] == 2
    assert counts(revised)["provider_requests"] == 12
    plan = read_plan(out, 2)
    assert plan.revises == read_plan(out).plan_hash
    # The same command again, with the reason the revision recorded in its experiment.json
    # 1.1.0, resumes the revised plan, and sends nothing (approving a revision).
    received = cli.server.requests()
    again = experiments.run(
        DEFINITION_CHANGED, out, "--revision-reason", "The Value factors weigh 60 and 40."
    )
    assert again.exit_code == 0, again.stderr
    assert cli.server.requests() == received


# The repeat, with two requests a case


def awaiting_baseline(cli: Cli, experiments: ExperimentBuilder[Outcome], out: Path) -> str:
    """Runs `ranking-budget-raised.yaml`, a budget of 10, as a new experiment, whose baseline's
    backtest gets a 503, so it awaits a repeat with 8 requests counted, and returns its attempt's
    ID, which confirms the repeat."""
    outcome = experiments.run(
        BUDGET_RAISED, out, ranks=four(RANK_UPDATED), sends=(UNAVAILABLE, *(returns(),) * 3)
    )
    assert outcome.exit_code == 6, outcome.stderr
    (baseline,) = [case for case in summary_cases(outcome) if case["case_key"] == "baseline"]
    assert counts(outcome)["provider_requests"] == 8
    return cast("str", baseline["repeat_attempt_id"])


@posix_only
def test_the_repeats_prompt_counts_both_of_a_cases_requests(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """The prompt gives, of the budget's provider requests, how many remain, and that this run
    sends two for the case: its `rank_update` and its backtest (repeating a case, the budget). The
    full display gives the most the counted requests can have cost, apart from the most the
    remaining ones can cost (plans with a ranking definition, the display)."""
    cli.ready()
    out = cli.tmp / "experiment"
    attempt = awaiting_baseline(cli, experiments, out)
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", RANK_UPDATED, method="POST")
    cli.server.reply("/screen/backtest", returns())
    before = len(cli.server.requests())

    with cli.on_terminal("run", BUDGET_RAISED, "--out", out, "--repeat", "baseline") as terminal:
        terminal.wait_for("Type approve")
        display = terminal.shown()
        terminal.press("approve\n")
        terminal.wait_for("Type repeat")
        prompt = terminal.shown()[len(display) :]
        terminal.press("repeat\n")
        exit_code = terminal.wait()

    assert exit_code == 0, terminal.shown()
    assert (
        "Its rank_update, or its backtest, may have reached Portfolio123, and may have been"
        " charged, so it's sent again only by a repeat, which sends both again, and may be"
        f" charged again: --repeat baseline:{attempt}"
    ) in display
    # 4 rank_updates at 1 and 4 backtests at 5; 2 requests remain, a rank_update and a backtest.
    assert (
        "At the documented costs, the requests counted so far can have cost at most 24 credits,"
        " and the 2 provider requests that remain at most 6 credits."
    ) in display
    assert (
        "A repeat sends the case's rank_update and its backtest again, two requests, as a new"
        " attempt of the case. It may be charged again, and it counts against the experiment's"
        " budget: of its 10 provider requests, 2 remain, and this run sends 2 requests, with the"
        " cases that are due and the repeats an attempt ID confirmed, which leaves 0 provider"
        " requests."
    ) in prompt.replace("\n", " ").replace("  ", " ")
    assert cli.server.requests()[before:] == ["POST /auth", "POST /rank", "POST /screen/backtest"]


def test_a_remaining_budget_of_one_request_covers_no_case(
    cli: Cli, experiments: ExperimentBuilder[Outcome], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A case's attempt starts only when both its requests fit, so a confirmed repeat with one
    request left isn't started: the run needs no credentials, sends nothing, and the display names
    the case the remaining budget can't cover (the budget across runs)."""
    cli.ready()
    out = cli.tmp / "experiment"
    # The baseline's rank_update gets a 400: one request counted, failed and possibly charged.
    first = experiments.run(
        EXAMPLE,
        out,
        ranks=(Reply(400, b"Unsupported value"), *(RANK_UPDATED,) * 3),
        sends=(returns(),) * 3,
    )
    assert first.exit_code == 6, first.stderr
    assert counts(first)["provider_requests"] == 7
    (baseline,) = [case for case in summary_cases(first) if case["case_key"] == "baseline"]
    received = cli.server.requests()
    monkeypatch.delenv("TRIALFOLIO_P123_API_ID")
    monkeypatch.delenv("TRIALFOLIO_P123_API_KEY")

    outcome = experiments.run(EXAMPLE, out, "--repeat", f"baseline:{baseline['repeat_attempt_id']}")

    assert outcome.exit_code == 6, outcome.stderr
    assert error_code(outcome) == "execution.partial"
    assert cli.server.requests() == received
    assert counts(outcome)["provider_requests"] == 7


# A snapshot as the baseline's ranking (R04-AC08)


def test_an_experiment_naming_a_snapshot_plans_offline_with_the_definition_files_cases(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = SnapshotBuilder(monkeypatch, cli.tmp / "builder").snapshot(cli.tmp / "snapshot")
    config = naming(EXAMPLE, snapshot, cli.tmp / "configs")
    cli.accept_license()
    out = cli.tmp / "experiment"

    by_snapshot = cli("run", config, "--out", out, "--json")
    by_file = cli("run", EXAMPLE, "--out", out, "--json")

    assert (by_snapshot.exit_code, by_file.exit_code) == (2, 2)
    assert cli.server.requests() == []
    assert not out.exists()
    assert [case["case_id"] for case in summary_cases(by_snapshot)] == [
        case["case_id"] for case in summary_cases(by_file)
    ]
    assert cast("dict[str, str]", by_snapshot.summary["ids"])["plan_hash"] != plan_hash(
        EXAMPLE, out
    )


def test_a_synthetic_snapshot_named_by_the_baseline_is_config_invalid(cli: Cli) -> None:
    from trialfolio.configuration import read_ranking_snapshot_configuration
    from trialfolio.planning import build_snapshot_plan, installed_versions
    from trialfolio.snapshot_execution import SnapshotExecution
    from trialfolio.storage import LocalArtifactStore

    example = FIXTURES / "ranking-snapshot-configs" / "example.yaml"
    content = example.read_bytes()
    plan = build_snapshot_plan(
        read_ranking_snapshot_configuration(content, example.name), installed_versions()
    )
    synthetic = cli.tmp / "synthetic"
    system = (RESPONSES / "rank-get.json").read_bytes()
    with LocalArtifactStore(synthetic) as store:
        error = SnapshotExecution(plan, plan.plan_hash, "not_required", store, None).run(
            content, lambda: SyntheticScreenBacktestClient(response_bytes(), system=system)
        )
    assert error is None
    config = naming(EXAMPLE, synthetic, cli.tmp / "configs")
    cli.ready()
    out = cli.tmp / "experiment"

    outcome = cli("run", config, "--out", out, "--json")

    assert outcome.exit_code == 3
    assert error_code(outcome) == "config.invalid"
    assert "`baseline.ranking.snapshot` names a snapshot that's synthetic" in message(outcome)
    assert not out.exists()
    assert cli.server.requests() == []


# A configuration 1.1.0 ranked by a formula


def test_an_experiment_1_1_0_ranked_by_a_formula_runs_and_resumes_as_a_plan_1_1_0(
    cli: Cli, experiments: ExperimentBuilder[Outcome], faults: FaultyStores
) -> None:
    """`example.yaml` as version 1.1.0, ranked by a formula, gives plan 1.1.0, as 0.4.0's planner
    gives it. A storage failure at a case's `settings.csv` ends the session without its
    manifest, so the resume reads `plans/1/configuration.yaml` 1.1.0, which no manifest lists,
    with 0.4.0's reader, and completes that case's table from it (R04-T12)."""
    cli.ready()
    content = experiment_config("example.yaml").read_bytes()
    config = cli.tmp / "example.yaml"
    config.write_bytes(content.replace(b"schema_version: 1.0.0", b"schema_version: 1.1.0"))
    out = cli.tmp / "experiment"
    without = cli("run", config, "--out", out, "--json")
    baseline = summary_cases(without)[0]["case_id"]
    faults.fail_os(f"{baseline}/settings.csv")

    stopped = experiments.run(config, out, sends=(returns(),), store_factory=faults)

    assert stopped.exit_code == 4, stopped.stderr
    assert error_code(stopped) == "storage.write_failed"
    assert not list(out.glob("sessions/*/manifest.json"))
    plan = PlanV1_1.model_validate_json((out / "plans" / "1" / "plan.json").read_bytes())
    assert plan.schema_version == "1.1.0"
    assert b"schema_version: 1.1.0" in (out / "plans" / "1" / "configuration.yaml").read_bytes()

    resumed = experiments.run(config, out, sends=(returns(),) * 4)

    assert resumed.exit_code == 0, resumed.stderr
    assert (out / "cases" / str(baseline) / "normalized" / "settings.csv").is_file()
    assert "POST /rank" not in cli.server.requests()
