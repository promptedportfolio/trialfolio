"""`trialfolio run` of a screen configuration whose ranking is a definition: it reads the
configuration 1.1.0 and its definition in step 2, shows the plan with the definition, obtains its
approval, gives the core the ranking lock's file, and runs the case's `rank_update`, then its
backtest; and the JSON summary counts both requests.

Traces to R04-AC01 through the CLI, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_run.py`: under the terminal, the full plan display gives that the run
overwrites `ApiRankingSystem`, and what the lock can't exclude; the definition's source; each
node's weight; the case's `case_id`, its `rank_update` with its definition line by line, tabs
kept, and its hash, then its backtest; and the budget, with each operation's cost and 6 credits a
case, before the prompt, and the server receives nothing until `approve` is typed. A definition
file changed while the run waits at its prompt doesn't change the copy. Without a terminal, stderr
gives only the plan hash, the budget, and the line that the run overwrites `ApiRankingSystem`;
and without `--approve`, `run --json` creates nothing, and gives the plan hash. Also to R04-AC08's
interface checks that R04-T10 left to R04-T12: `definition.yaml` naming a snapshot builds its plan
offline, with the snapshot's source and the definition file's `case_id`, and copies the snapshot's
two files; a synthetic snapshot named by it is `config.invalid`. And to the JSON summary's counts
(docs/contracts.md, sending a definition, counting the requests): a run with a definition counts
both kinds of request, its attempt's update record included, and sums each reported cost. R04-T12
wrote them. The CLI's entry function runs in the test process, with the fake server below
`urllib3`, the fixed clock, storage faults, and the terminal through the test launcher.
"""

import json
import shutil
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import (
    AUTHENTICATED,
    Cli,
    FaultyStores,
    Outcome,
    plan_hash_for,
    response,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.snapshot_builder import SnapshotBuilder, naming
from trialfolio.contracts.manifest import RunManifestV1_1
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotRecord
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DEFINITION = FIXTURES / "screen-configs" / "definition.yaml"
VALUE_MOMENTUM = FIXTURES / "experiment-configs" / "ranking" / "value-momentum.xml"
RESPONSES = FIXTURES / "responses"
DEFINITION_HASH = "sha256:6bc59b992f83d5e4c245f37f187651ed18de6b9cb5949ac9f29b743273b26895"
"""The hash of `value-momentum.xml`'s text, as the plan's `ranking` setting gives it."""

RANK_UPDATED = Reply(200, (RESPONSES / "rank-update.json").read_bytes())
"""`rank-update.json`'s 200, whose `cost` is 1."""


def serve(cli: Cli, rank: Reply = RANK_UPDATED, backtest: Reply | None = None) -> None:
    """Scripts a run with a definition: authentication, its `POST /rank`, then its backtest,
    `complete.json`'s 200 by default, whose `cost` is 5."""
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", rank, method="POST")
    cli.server.reply(
        "/screen/backtest", response("complete.json") if backtest is None else backtest
    )


def run(cli: Cli, out: Path, *args: str | Path, config: Path = DEFINITION) -> Outcome:
    """Runs `config` into `out`, approved with `--approve` and its plan's hash, with `--json`."""
    return cli("run", config, "--out", out, "--approve", plan_hash_for(config), "--json", *args)


def error_code(outcome: Outcome) -> str:
    return cast("dict[str, str]", outcome.summary["error"])["code"]


def counts(outcome: Outcome) -> dict[str, object]:
    return cast("dict[str, object]", outcome.summary["counts"])


def copied(cli: Cli) -> Path:
    """A copy of `definition.yaml`, with its definition at the path it names, in the test's
    directory, so the test can change the definition."""
    configs = cli.tmp / "configs" / "screen-configs"
    ranking = cli.tmp / "configs" / "experiment-configs" / "ranking"
    configs.mkdir(parents=True)
    ranking.mkdir(parents=True)
    shutil.copy(VALUE_MOMENTUM, ranking / VALUE_MOMENTUM.name)
    return Path(shutil.copy(DEFINITION, configs / DEFINITION.name))


# The plan, and its approval


@posix_only
def test_under_a_terminal_the_plan_shows_the_definition_and_nothing_is_sent_first(
    cli: Cli,
) -> None:
    """The full display, before the prompt (R04-AC01). Then the definition file changes while the
    run waits at its prompt: the copy holds the bytes the plan was built from."""
    cli.ready()
    serve(cli)
    config = copied(cli)
    plan_hash = plan_hash_for(config)
    original = VALUE_MOMENTUM.read_bytes()
    out = cli.tmp / "run"

    with cli.on_terminal("run", config, "--out", out) as terminal:
        terminal.wait_for("Type approve")
        shown = terminal.shown()
        received_before = cli.server.requests()
        changed = original.replace(b'Weight="40"', b'Weight="45"', 1)
        (config.parent.parent / "experiment-configs" / "ranking" / VALUE_MOMENTUM.name).write_bytes(
            changed
        )
        terminal.press("approve\n")
        exit_code = terminal.wait()

    assert received_before == []
    prompt = shown.index("Type approve to run this plan")
    case_id = json.loads((out / "plan.json").read_bytes())["cases"][0]["case_id"]
    in_order = [
        f"Plan {plan_hash}",
        (
            "This run overwrites ApiRankingSystem, a ranking system in your Portfolio123"
            " account, with each case's ranking definition."
        ),
        (
            "Nothing keeps Portfolio123's website, or another machine, from writing or using it"
            " at the same time."
        ),
        f"The ranking definition's source: a file, by the definition's hash, {DEFINITION_HASH}.",
        f"Case {case_id}",
        "The request, exactly as p123api's rank_update will send it to Portfolio123",
        '"rankingMethod": 2,',
        f"the definition {DEFINITION_HASH}, line by line:",
        '    <RankingSystem RankType="Higher">',
        # The definition's tabs are kept, line by line.
        '    \t<Composite Name="Value" Weight="40" RankType="Summation">',
        "The request, exactly as p123api's screen_backtest will send it to Portfolio123:",
        '"ranking": "ApiRankingSystem",',
        "ranking_weight Value: 40 (verified)",
        "ranking_weight Value/Earnings Yield: 50 (verified)",
        "ranking_weight Quality/Gross Margin: 50 (verified)",
        (
            "Budget: at most 2 provider requests, each sent at most once: 6 credits at most, at"
            " Portfolio123's documented costs of 1 credit per rank_update (API functions: Rank,"
            " checked 2026-10-12) and 5 credits per screen_backtest (API: Screen, checked"
            " 2026-10-01)."
        ),
        "two requests that can cost 6 credits.",
        f"Plan hash: {plan_hash}",
    ]
    positions = [shown.index(line) for line in in_order]
    assert positions == sorted(positions)
    assert positions[-1] < prompt
    assert "The ranking lock keeps other Trial Folio processes on this machine" in shown
    # nodes is shown as the definition's lines, not as one JSON string among the params.
    assert '"nodes"' not in shown
    assert exit_code == 0, terminal.shown()
    assert cli.server.requests() == ["POST /auth", "POST /rank", "POST /screen/backtest"]
    # The copy, and the definition sent, are the bytes the plan was built from.
    assert (out / "definition.xml").read_bytes() == original
    (rank,) = [r for r in cli.server.received if r.request == "POST /rank"]
    assert json.loads(rank.body)["nodes"] == original.decode("utf-8")


def test_without_a_terminal_stderr_gives_the_hash_the_budget_and_the_overwrite(cli: Cli) -> None:
    """Without a terminal, the display holds nothing from the configuration: the plan hash, the
    budget, and the line that the run overwrites `ApiRankingSystem` (R04-AC01)."""
    cli.ready()
    out = cli.tmp / "run"

    outcome = cli("run", DEFINITION, "--out", out, "--json")

    assert outcome.exit_code == 2
    assert error_code(outcome) == "plan.approval_required"
    assert not out.exists()
    assert cli.server.requests() == []
    ids = cast("dict[str, str]", outcome.summary["ids"])
    assert ids["plan_hash"] == plan_hash_for(DEFINITION)
    assert set(ids) == {"plan_hash", "case_id"}
    assert outcome.stderr.splitlines()[:7] == [
        f"Plan hash: {plan_hash_for(DEFINITION)}",
        (
            "Budget: at most 2 provider requests, each sent at most once: 6 credits at most, at"
            " Portfolio123's documented costs of 1 credit per rank_update (API functions: Rank,"
            " checked 2026-10-12) and 5 credits per screen_backtest (API: Screen, checked"
            " 2026-10-01)."
        ),
        (
            "  Each case's attempt sends a rank_update, then a screen_backtest, two requests that"
            " can cost 6 credits."
        ),
        "  A request that reaches Portfolio123 may be charged even if it fails.",
        (
            "  At most 1 authentication call, whose cost isn't documented. Authentication cost"
            " no credits when last measured, and the credits above leave it out."
        ),
        (
            "This run overwrites ApiRankingSystem, a ranking system in your Portfolio123"
            " account, with each case's ranking definition."
        ),
        "Run the command in a terminal to see the full plan.",
    ]
    for text in ("<RankingSystem", "Composite", "Earnings Yield", "Momentum", DEFINITION_HASH):
        assert text not in outcome.stderr


def test_with_a_matching_approve_stderr_gives_the_overwrite_too(cli: Cli) -> None:
    cli.ready()
    serve(cli)

    outcome = run(cli, cli.tmp / "run")

    assert outcome.exit_code == 0, outcome.stderr
    lines = outcome.stderr.splitlines()
    assert lines[0] == f"Plan hash: {plan_hash_for(DEFINITION)}"
    assert (
        "This run overwrites ApiRankingSystem, a ranking system in your Portfolio123 account,"
        " with each case's ranking definition."
    ) in lines
    assert "Run the command in a terminal to see the full plan." not in lines
    assert "Earnings Yield" not in outcome.stderr


# The run


def test_an_approved_run_writes_the_definition_then_backtests_and_counts_both(cli: Cli) -> None:
    """The case's `rank_update`, then its backtest, ranked by `ApiRankingSystem`; the run's
    records with a definition; and the JSON summary, which counts both requests, and sums both
    costs Portfolio123 reported (sending a definition, counting the requests)."""
    cli.ready()
    serve(cli)
    out = cli.tmp / "run"

    outcome = run(cli, out)

    assert outcome.exit_code == 0, outcome.stderr
    assert cli.server.requests() == ["POST /auth", "POST /rank", "POST /screen/backtest"]
    backtest = next(r for r in cli.server.received if r.request == "POST /screen/backtest")
    assert json.loads(backtest.body)["screen"]["ranking"] == "ApiRankingSystem"
    assert (out / "definition.xml").read_bytes() == VALUE_MOMENTUM.read_bytes()
    plan = PlanV1_2.model_validate_json((out / "plan.json").read_bytes())
    manifest = RunManifestV1_1.model_validate_json((out / "manifest.json").read_bytes())
    assert (manifest.outcome, manifest.synthetic) == ("completed", False)
    summary = outcome.summary
    assert summary["outcome"] == "completed"
    ids = cast("dict[str, str]", summary["ids"])
    assert (ids["plan_hash"], ids["case_id"]) == (plan.plan_hash, plan.cases[0].case_id)
    assert "attempt_id" in ids
    assert summary["outputs"] == {
        "manifest": "manifest.json",
        "report": "report.html",
        "metrics": "normalized/metrics.csv",
        "settings": "normalized/settings.csv",
    }
    assert {key: counts(outcome)[key] for key in ("attempts", "provider_requests", "cost")} == {
        "attempts": 1,
        "provider_requests": 2,
        "cost": 6,
    }


def test_a_rank_update_that_fails_counts_one_request_and_sends_no_backtest(cli: Cli) -> None:
    """A 503 to the `rank_update` leaves the attempt `unknown`, possibly charged, with one
    request counted, and its backtest unsent."""
    cli.ready()
    serve(cli, rank=Reply(503, b""))
    out = cli.tmp / "run"

    outcome = run(cli, out)

    assert outcome.exit_code == 5
    assert error_code(outcome) == "provider.outcome_unknown"
    assert cli.server.requests() == ["POST /auth", "POST /rank"]
    assert {key: counts(outcome)[key] for key in ("attempts", "provider_requests", "cost")} == {
        "attempts": 1,
        "provider_requests": 1,
        "cost": None,
    }


@pytest.mark.parametrize(
    ("rank", "sent"),
    [(RANK_UPDATED, 2), (Reply(503, b""), 1)],
    ids=["after-backtest", "after-rank-update"],
)
def test_without_its_attempt_record_the_summary_counts_each_start_record(
    cli: Cli, faults: FaultyStores, rank: Reply, sent: int
) -> None:
    """An attempt whose attempt record couldn't be written reads as running, and counts one
    possible send for each start record it wrote: its update record, and its `started.json` when
    it sent its backtest (counting the requests). The summary gives its `attempt_id` either way."""
    cli.ready()
    serve(cli, rank=rank)
    faults.fail_os("attempt.json")
    out = cli.tmp / "run"

    outcome = cli(
        "run",
        DEFINITION,
        "--out",
        out,
        "--approve",
        plan_hash_for(DEFINITION),
        "--json",
        store_factory=faults,
    )

    assert outcome.exit_code == 4
    assert error_code(outcome) == "storage.write_failed"
    assert (counts(outcome)["attempts"], counts(outcome)["provider_requests"]) == (1, sent)
    assert "attempt_id" in cast("dict[str, str]", outcome.summary["ids"])


def test_a_screen_configuration_1_1_0_ranked_by_a_formula_runs_as_a_plan_1_0_0(cli: Cli) -> None:
    """A configuration 1.1.0 whose ranking is a formula gives plan 1.0.0, as 0.4.0's planner
    gives it, whichever version the file is, so the run sends its backtest alone, and its
    executor reads its configuration with 0.4.0's reader (R04-T12)."""
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("complete.json"))
    formula = (FIXTURES / "screen-configs" / "formula.yaml").read_bytes()
    config = cli.tmp / "formula.yaml"
    config.write_bytes(formula.replace(b"schema_version: 1.0.0", b"schema_version: 1.1.0"))
    out = cli.tmp / "run"

    outcome = run(cli, out, config=config)

    assert outcome.exit_code == 0, outcome.stderr
    assert cli.server.requests() == ["POST /auth", "POST /screen/backtest"]
    assert json.loads((out / "plan.json").read_bytes())["schema_version"] == "1.0.0"
    manifest = json.loads((out / "manifest.json").read_bytes())
    (configuration,) = [a for a in manifest["artifacts"] if a["role"] == "configuration"]
    assert configuration["schema_version"] == "1.1.0"
    assert not (out / "definition.xml").exists()
    # trialfolio report reads it back as a complete run.
    report = cli("report", out, "--out", cli.tmp / "report")
    assert report.exit_code == 0, report.stderr


# A snapshot as the ranking (R04-AC08)


def test_a_configuration_naming_a_snapshot_plans_offline_and_copies_its_files(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`definition.yaml` with a snapshot in place of its definition builds its plan with no
    credentials and sends nothing, with the snapshot's source; its case is the definition file's;
    and, approved, the run copies the snapshot's `definition.xml` and `snapshot.json`, byte for
    byte, beside `configuration.yaml`, and sends the snapshot's definition."""
    snapshot = SnapshotBuilder(monkeypatch, cli.tmp / "builder").snapshot(cli.tmp / "snapshot")
    config = naming(DEFINITION, snapshot, cli.tmp / "configs")
    cli.accept_license()
    out = cli.tmp / "run"

    offline = cli("run", config, "--out", out, "--json")

    assert offline.exit_code == 2
    assert error_code(offline) == "plan.approval_required"
    assert cli.server.requests() == []
    assert not out.exists()
    ids = cast("dict[str, str]", offline.summary["ids"])
    by_file = cli("run", DEFINITION, "--out", out, "--json")
    assert ids["case_id"] == cast("dict[str, str]", by_file.summary["ids"])["case_id"]
    assert ids["plan_hash"] != plan_hash_for(DEFINITION)

    cli.credentials()
    serve(cli)
    approved = run(cli, out, config=config)

    assert approved.exit_code == 0, approved.stderr
    assert (out / "definition.xml").read_bytes() == (snapshot / "definition.xml").read_bytes()
    assert (out / "snapshot.json").read_bytes() == (snapshot / "snapshot.json").read_bytes()
    plan = PlanV1_2.model_validate_json((out / "plan.json").read_bytes())
    record = RankingSnapshotRecord.model_validate_json((snapshot / "snapshot.json").read_bytes())
    assert (plan.ranking_source.form, plan.ranking_source.system) == (
        "snapshot",
        record.system.name,
    )
    (rank,) = [r for r in cli.server.received if r.request == "POST /rank"]
    nodes = json.loads(rank.body)["nodes"]
    assert nodes == (snapshot / "definition.xml").read_text(encoding="utf-8")


@posix_only
def test_under_a_terminal_a_snapshot_source_gives_its_system_and_when_it_was_read(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = SnapshotBuilder(monkeypatch, cli.tmp / "builder").snapshot(cli.tmp / "snapshot")
    config = naming(DEFINITION, snapshot, cli.tmp / "configs")
    record = RankingSnapshotRecord.model_validate_json((snapshot / "snapshot.json").read_bytes())
    taken = record.taken_at.isoformat().replace("+00:00", "Z")
    cli.accept_license()

    with cli.on_terminal("run", config, "--out", cli.tmp / "run") as terminal:
        terminal.wait_for("Type approve")
        shown = terminal.shown()
        terminal.press("no\n")
        assert terminal.wait() == 2

    assert (
        f"The ranking definition's source: a ranking snapshot of the system {record.system.name},"
        f" read {taken}, by the definition's hash, {DEFINITION_HASH}."
    ) in shown


def test_a_synthetic_snapshot_named_as_the_ranking_is_config_invalid(cli: Cli) -> None:
    """The core takes a synthetic snapshot with the demo's client; a configuration that names it
    fails in step 2, before the output directory, and nothing is sent (reading a snapshot,
    D-41)."""
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
    config = naming(DEFINITION, synthetic, cli.tmp / "configs")
    cli.ready()
    out = cli.tmp / "run"

    outcome = cli("run", config, "--out", out, "--json")

    assert outcome.exit_code == 3
    assert error_code(outcome) == "config.invalid"
    message = cast("dict[str, str]", outcome.summary["error"])["message"]
    assert "`ranking.snapshot` names a snapshot that's synthetic" in message
    assert not out.exists()
    assert cli.server.requests() == []
