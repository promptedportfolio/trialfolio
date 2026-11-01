"""Each case of an experiment with a ranking definition writes its definition into
`ApiRankingSystem`, then backtests ranked by that system, in the core: a new experiment, with its
records 1.3.0, a plan's `definition.xml`, `settings.csv` 1.1.0, and manifest 1.1.0.

Traces to docs/contracts.md, sending a definition (the calls, nothing between them, the backtest
only after the write, the errors, cancellation, the attempt's files, records 1.3.0, and counting the
requests), the ranking lock, plans with a ranking definition, weight rows, an experiment's
normalized tables, the experiment manifest's version 1.1.0, and CLI behavior (the demo's client);
and to R04-AC03 at the core: the calls in R04-T01's verified order, the records holding the
definition sent, byte for byte, each failing reply's outcome and error code, a cancellation that
never falls between a case's two calls, and a synthetic experiment the core writes with the demo's
client. The real client, `requests`, and `urllib3` run over the fake server, whose end-of-test check
reads every `POST /rank` body (R04-AC09); storage faults wrap the real store; the clock is fixed;
and every execution takes the ranking lock on a file in the test's temporary directory. TS-T07
separated a screen run's tests, with their own driver, into tests/core/test_ranking_screen_run.py
(docs/test-refactoring.md, modules to separate), and moved what an ending's message says of an
attempt a second interrupt stopped, which both modules check, to tests/support/ranking_messages.py.
"""

import json
import threading
import time
from pathlib import Path

import pytest

from tests.support.clock import no_wait
from tests.support.experiment_lab import Lab, Ran
from tests.support.fake_portfolio123 import (
    AUTH,
    AUTHENTICATED,
    BACKTEST,
    RANK,
    FakePortfolio123,
    Reply,
    distinct,
    exchange,
    response,
)
from tests.support.paths import EXPERIMENT_CONFIGS
from tests.support.plans import experiment_plan, ranked_experiment
from tests.support.ranking_messages import RAN_UPDATE, UPDATING
from tests.support.storage_faults import Fault, StorageFaults
from trialfolio.contracts.attempt import AttemptRecordV1_3, StartRecordV1_3
from trialfolio.contracts.experiment_manifest import ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecordV1_1
from trialfolio.contracts.tables import SettingsRowV1_1
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.experiment_execution import Cancellation, ExperimentExecution
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_settings_csv_v1_1

# A new experiment


def script_experiment(server: FakePortfolio123, cases: int) -> None:
    """Each case's `rank_update` gets a 200, and its backtest a response of its own, so none is a
    stale backtest (D-45)."""
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", *(response("rank-update.json") for _ in range(cases)), method="POST")
    server.reply(
        "/screen/backtest", *distinct(*(response("complete.json").body for _ in range(cases)))
    )


def test_each_case_of_an_experiment_writes_its_definition_then_backtests(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    planned = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml")
    definition, plan = planned.definition, planned.plan
    script_experiment(server, 4)

    ran = Lab(tmp_path, server).new()

    assert ran.error is None
    assert ran.received == (AUTH, *(RANK, BACKTEST) * 4)
    ranks = [r for r in server.received if r.request == RANK]
    backtests = [r for r in server.received if r.request == BACKTEST]
    for case, rank, sent in zip(plan.cases, ranks, backtests, strict=True):
        update, backtest = case.requests
        assert rank.body == json.dumps(update.params.model_dump(mode="json")).encode()
        assert json.loads(sent.body) == backtest.params.model_dump(mode="json")
        assert json.loads(sent.body)["screen"]["ranking"] == "ApiRankingSystem"
    assert (ran.out / "plans/1/definition.xml").read_bytes() == definition
    record = ExperimentRecordV1_1.model_validate_json(
        (ran.out / "plans/1/experiment.json").read_bytes()
    )
    assert [case.case_key for case in record.planned_cases] == [
        case.case_key for case in plan.cases
    ]


def test_an_experiments_records_are_1_3_0(tmp_path: Path, server: FakePortfolio123) -> None:
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    script_experiment(server, 4)

    ran = Lab(tmp_path, server).new()

    records = [
        AttemptRecordV1_3.model_validate_json(
            (ran.attempt(case.case_id) / "attempt.json").read_bytes()
        )
        for case in plan.cases
    ]
    for place, (case, record) in enumerate(zip(plan.cases, records, strict=True)):
        attempt = ran.attempt(case.case_id)
        update = StartRecordV1_3.model_validate_json((attempt / "updating.json").read_bytes())
        start = StartRecordV1_3.model_validate_json((attempt / "started.json").read_bytes())
        assert (update.operation, update.sequence) == ("rank_update", place + 1)
        assert start.exchanges[-1] == exchange(RANK, 200)
        # Only the session's first attempt authenticates; the others send with its token.
        assert len(update.exchanges) == int(place == 0)
        assert record.authenticated_by == records[0].attempt_id
        assert record.outcome == "succeeded"
        assert record.ranking_update.provider_metadata.cost == 1
    manifest = ExperimentManifestV1_1.model_validate_json(
        (ran.out / "sessions/1/manifest.json").read_bytes()
    )
    assert manifest.outcome == "completed"
    assert manifest.counts.provider_requests == 8
    assert manifest.counts.authentication_calls == 1
    assert manifest.counts.cost == 24
    roles = {artifact.role for artifact in manifest.artifacts}
    assert {"ranking_definition", "update_record", "rank_update_request"} <= roles
    assert "rank_update_response" in roles
    # The definition's copy is acquired with its configuration, when the plan was recorded; each
    # rank_update's request when its attempt started, and its response when it ended.
    acquired = {a.path: a.source.acquired_at for a in manifest.artifacts if a.source is not None}
    recorded = ExperimentRecordV1_1.model_validate_json(
        (ran.out / "plans/1/experiment.json").read_bytes()
    )
    assert acquired["plans/1/definition.xml"] == recorded.created_at
    assert acquired["plans/1/configuration.yaml"] == recorded.created_at
    for case, record in zip(plan.cases, records, strict=True):
        directory = ran.attempt(case.case_id).relative_to(ran.out).as_posix()
        assert record.started_at < record.ended_at
        assert acquired[f"{directory}/rank-update-request.json"] == record.started_at
        assert acquired[f"{directory}/rank-update-response.json"] == record.ended_at


def test_an_experiments_cases_settings_csv_takes_each_weights_original(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    script_experiment(server, 4)

    ran = Lab(tmp_path, server).new()

    manifest = ExperimentManifestV1_1.model_validate_json(
        (ran.out / "sessions/1/manifest.json").read_bytes()
    )
    ids = {a.path: a.artifact_id for a in manifest.artifacts}
    definition, configuration = ids["plans/1/definition.xml"], ids["plans/1/configuration.yaml"]

    def rows(key: str) -> list[SettingsRowV1_1]:
        (case,) = [case for case in plan.cases if case.case_key == key]
        path = ran.out / "cases" / case.case_id / "normalized/settings.csv"
        return [r for r in read_settings_csv_v1_1(path.read_bytes(), path.name) if r.node]

    value_heavy = {row.node: row for row in rows("value-heavy")}
    assert value_heavy["Value"].original_key == "variants.ranking[0].set[0]"
    assert value_heavy["Value"].original_value == "60"
    assert value_heavy["Value"].source_artifact == configuration
    assert value_heavy["Value/Earnings Yield"].original_key == "baseline.ranking.definition"
    assert value_heavy["Value/Earnings Yield"].source_artifact == definition
    no_sales_yield = rows("no-sales-yield")
    assert len(no_sales_yield) == 8
    assert "Value/Sales Yield" not in {row.node for row in no_sales_yield}
    removal = {row.node: row for row in no_sales_yield}
    assert removal["Value/Earnings Yield"].original_value == "100"


def test_only_a_weight_a_variant_changes_takes_its_original_from_the_variant(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # Weight rows (what a variant changes), as R04-T08 settled it: a `set` entry gives a row's
    # original only when it changes the baseline's weight, compared as decimals; and a removal's
    # rows are named by the case's own canonical paths, where a position the removal changes
    # becomes a name. ranking-example.yaml's entries all change their weights, and its removal
    # renames nothing, so neither rule had a test (the review of R04-T08's pull request).
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-positions.yaml").plan
    script_experiment(server, len(plan.cases))

    ran = Lab(tmp_path, server).new("ranking-positions.yaml")

    assert ran.error is None
    manifest = ExperimentManifestV1_1.model_validate_json(
        (ran.out / "sessions/1/manifest.json").read_bytes()
    )
    ids = {a.path: a.artifact_id for a in manifest.artifacts}
    definition, configuration = ids["plans/1/definition.xml"], ids["plans/1/configuration.yaml"]

    def rows(key: str) -> dict[str, SettingsRowV1_1]:
        (case,) = [case for case in plan.cases if case.case_key == key]
        path = ran.out / "cases" / case.case_id / "normalized/settings.csv"
        read = read_settings_csv_v1_1(path.read_bytes(), path.name)
        return {row.node: row for row in read if row.node is not None}

    # `'\#Momentum': 15` keeps the baseline's weight, so its row keeps the definition's original.
    kept = rows("positions-heavy")["\\#Momentum"]
    assert (kept.original_key, kept.original_value, kept.source_artifact) == (
        "baseline.ranking.definition",
        "15",
        definition,
    )
    changed = rows("positions-heavy")["Value P\\/E"]
    assert (changed.original_key, changed.original_value, changed.source_artifact) == (
        "variants.ranking[0].set[0]",
        "30",
        configuration,
    )
    # Removing `#1` leaves one `Yield`, so the node the variant sets as `#2` is `Yield` in the
    # case's definition, and its row takes the variant's original.
    removal = rows("no-first-yield")
    assert "Value P\\/E/#2" not in removal
    renamed = removal["Value P\\/E/Yield"]
    assert (renamed.value, renamed.original_key, renamed.original_value) == (
        "60",
        "variants.ranking[1].set[0]",
        "60",
    )
    assert renamed.source_artifact == configuration


def test_a_variant_of_another_setting_sends_the_baselines_definition(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-mixed.yaml").plan
    script_experiment(server, len(plan.cases))

    ran = Lab(tmp_path, server).new("ranking-mixed.yaml")

    assert ran.error is None
    baseline = plan.cases[0].requests[0].params.nodes
    nodes = [json.loads(r.body)["nodes"] for r in server.received if r.request == RANK]
    keys = [case.case_key for case in plan.cases]
    assert [key for key, sent in zip(keys, nodes, strict=True) if sent == baseline] == [
        key for key in keys if key != "value-heavy"
    ]


def test_a_rank_updates_quota_exceeded_stops_the_experiment(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", Reply(402, b""), method="POST")

    ran = Lab(tmp_path, server).new()

    # D-32: every later case would be refused the same way.
    assert ran.received == (AUTH, RANK)
    assert ran.error is not None
    assert ran.error.code == "execution.partial"
    assert "provider.quota_exceeded" in ran.error.message
    record = AttemptRecordV1_3.model_validate_json(
        (ran.attempt(plan.cases[0].case_id) / "attempt.json").read_bytes()
    )
    assert (record.outcome, record.possibly_charged) == ("failed", True)


def test_after_a_401_to_a_rank_update_the_next_case_authenticates_again(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    server.reply(
        "/rank", Reply(401, b""), *(response("rank-update.json") for _ in range(3)), method="POST"
    )
    server.reply("/screen/backtest", *distinct(*(response("complete.json").body for _ in range(3))))

    ran = Lab(tmp_path, server).new()

    assert ran.received == (AUTH, RANK, AUTH, *(RANK, BACKTEST) * 3)
    assert ran.error is not None
    assert ran.error.code == "execution.partial"


def test_a_cancellation_never_falls_between_a_cases_two_calls(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    release = threading.Event()
    server.reply("/auth", AUTHENTICATED)
    server.reply(
        "/rank", Reply(200, response("rank-update.json").body, release=release), method="POST"
    )
    server.reply("/screen/backtest", response("complete.json"))
    cancellation = Cancellation()
    ran: list[Ran] = []
    thread = threading.Thread(
        target=lambda: ran.append(Lab(tmp_path, server).new(cancellation=cancellation))
    )
    thread.start()
    deadline = time.monotonic() + 30
    while RANK not in server.requests() and time.monotonic() < deadline:
        time.sleep(0.01)
    cancellation.cancel()
    release.set()
    thread.join(60)

    (done,) = ran
    # The case written is backtested, right after its rank_update, and no later case starts.
    assert done.received == (AUTH, RANK, BACKTEST)
    record = AttemptRecordV1_3.model_validate_json(
        (done.attempt(plan.cases[0].case_id) / "attempt.json").read_bytes()
    )
    assert record.outcome == "succeeded"
    assert done.error is not None
    assert done.error.code == "execution.partial"
    assert "cancelled" in done.error.message
    manifest = ExperimentManifestV1_1.model_validate_json(
        (done.out / "sessions/1/manifest.json").read_bytes()
    )
    assert manifest.outcome == "partial"


@pytest.mark.parametrize(
    ("faults", "received", "outcome", "requests", "said"),
    [
        (
            {"attempt.json": "unexpected"},
            (AUTH, RANK, BACKTEST),
            "running",
            2,
            RAN_UPDATE,
        ),
        (
            {"request.json": "unexpected", "attempt.json": "unexpected"},
            (AUTH, RANK),
            "failed",
            1,
            UPDATING,
        ),
        (
            {"rank-update-response.json": "full disk", "attempt.json": "unexpected"},
            (AUTH, RANK),
            "unknown",
            1,
            UPDATING,
        ),
        (
            {"rank-update-response.json": "published", "attempt.json": "full disk"},
            (AUTH, RANK),
            "failed",
            1,
            UPDATING,
        ),
    ],
    ids=[
        "after its start record",
        "after its update record, with its response saved",
        "after its update record, without its response",
        "after its update record, with its response published before its write failed",
    ],
)
def test_an_attempt_without_its_record_counts_as_its_records_read(
    tmp_path: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
    faults: dict[str, Fault],
    received: tuple[str, ...],
    outcome: str,
    requests: int,
    said: tuple[str, ...],
) -> None:
    # A storage fault, or an unexpected one, leaves the first case's attempt without its attempt
    # record, which ends the session without its manifest. Its records say what a resume will
    # record (counting the requests; an attempt stopped after its update record): `running`,
    # with both requests counted, after `started.json`; and with only `updating.json`, one
    # request, `failed` with the rank_update's response in its directory, and `unknown` without
    # it. A response the store published before its write failed, as when the directory's sync
    # fails, is in the directory whole, so a resume reads it as saved (uncertain completion),
    # though the attempt record would reference only a completed write.
    script_experiment(server, 4)

    def set_faults(store: StorageFaults) -> None:
        store.fail_each(faults)

    ran = Lab(tmp_path, server, monkeypatch).new(arm=set_faults)

    assert ran.received == received
    assert ran.error is not None
    assert not (ran.out / "sessions/1/manifest.json").exists()
    execution = ran.execution
    assert execution is not None
    counts = execution.counts
    assert counts.provider_requests == requests
    attempts = counts.attempts
    assert (attempts.running, attempts.failed, attempts.unknown) == (
        int(outcome == "running"),
        int(outcome == "failed"),
        int(outcome == "unknown"),
    )
    first = execution.outcomes[0][1]
    assert first == ("failed" if outcome == "failed" else "unknown")
    # Every such attempt may have been charged, so its case awaits a repeat.
    assert list(execution.repeat_attempts) == [execution.outcomes[0][0].case_id]
    for part in said:
        assert part.format(of=" of the last attempt", record="its") in ran.error.message


@pytest.mark.parametrize(
    ("interrupted", "said"),
    [("attempt.json", RAN_UPDATE), ("request.json", UPDATING)],
    ids=["after its start record", "after its update record"],
)
def test_a_second_interrupt_at_an_experiments_attempt_record_says_what_each_request_did(
    tmp_path: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
    interrupted: str,
    said: tuple[str, ...],
) -> None:
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    first = plan.cases[0].case_id
    script_experiment(server, 4)

    def set_faults(store: StorageFaults) -> None:
        if interrupted != "attempt.json":
            store.fail_before(interrupted, KeyboardInterrupt())
        store.fail_before(f"{first}/attempt.json", KeyboardInterrupt())
        store.fail_before("attempt.json", KeyboardInterrupt())

    ran = Lab(tmp_path, server, monkeypatch).new(arm=set_faults)

    assert ran.error is not None
    assert ran.error.code == "command.interrupted"
    for part in said:
        assert part.format(of=" of the attempt under way", record="its") in ran.error.message


def test_an_update_record_published_before_its_write_failed_counts_as_written(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Its rank_update isn't sent, and its attempt record agrees with the update record the store
    # published, as for any start record: the attempt authenticated, and its token is its own.
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    first = plan.cases[0].case_id
    script_experiment(server, 4)

    def set_faults(store: StorageFaults) -> None:
        store.fail_after(f"{first}/updating.json", RuntimeError())

    ran = Lab(tmp_path, server, monkeypatch).new(arm=set_faults)

    assert ran.received == (AUTH, *(RANK, BACKTEST) * 3)
    attempt = ran.attempt(first)
    update = StartRecordV1_3.model_validate_json((attempt / "updating.json").read_bytes())
    record = AttemptRecordV1_3.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", False)
    assert record.authenticated_by == update.authenticated_by == record.attempt_id
    manifest = ExperimentManifestV1_1.model_validate_json(
        (ran.out / "sessions/1/manifest.json").read_bytes()
    )
    listed = {artifact.path: artifact.role for artifact in manifest.artifacts}
    directory = attempt.relative_to(ran.out).as_posix()
    assert listed[f"{directory}/updating.json"] == "update_record"


def test_a_rank_update_response_published_before_its_write_failed_is_listed(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The manifest lists every file the attempt wrote, and its attempt record references only a
    # completed write, as for a backtest's response.
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    first = plan.cases[0].case_id
    script_experiment(server, 4)

    def set_faults(store: StorageFaults) -> None:
        store.fail_after(f"{first}/rank-update-response.json", RuntimeError())

    ran = Lab(tmp_path, server, monkeypatch).new(arm=set_faults)

    assert ran.received == (AUTH, RANK, *(RANK, BACKTEST) * 3)
    attempt = ran.attempt(first)
    record = AttemptRecordV1_3.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.ranking_update is not None
    assert record.ranking_update.response is None
    manifest = ExperimentManifestV1_1.model_validate_json(
        (ran.out / "sessions/1/manifest.json").read_bytes()
    )
    listed = {artifact.path: artifact.role for artifact in manifest.artifacts}
    directory = attempt.relative_to(ran.out).as_posix()
    assert listed[f"{directory}/rank-update-response.json"] == "rank_update_response"


def test_the_core_writes_a_synthetic_experiment_with_the_demos_client(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    lab = Lab(tmp_path, server)
    out = lab.out

    error = lab.new(synthetic=True).error

    assert error is None
    manifest = ExperimentManifestV1_1.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    assert (manifest.synthetic, manifest.approval, manifest.command) == (
        True,
        "not_required",
        None,
    )
    assert manifest.counts.cases.succeeded == len(plan.cases)
    # The baseline's settings table names every weight row's node beside its setting. A defect
    # found by the review of R04-T08's pull request: the report kept only the last weight row.
    report = (out / "sessions/1/report.html").read_text(encoding="utf-8")
    (baseline, *_) = plan.cases
    nodes = [row.node for row in baseline.settings if row.node is not None]
    assert len(nodes) == 9
    for node in nodes:
        assert f"<code>ranking_weight</code> <code>{node}</code>" in report
    # Each ranking variant's change, and the budget's cost of each operation.
    (removal,) = [case for case in plan.cases if case.case_key == "no-sales-yield"]
    assert removal.variant is not None
    assert removal.variant.remove == "Value/Sales Yield"
    assert (
        "Removes the ranking's factor <code>Value/Sales Yield</code>, and sets"
        " <code>Value/Earnings Yield</code> to <code>100</code>" in report
    )
    assert "Sets the ranking's weights: <code>Value</code> to <code>60</code>" in report
    assert {cost.operation for cost in plan.budget.costs} == {"rank_update", "screen_backtest"}
    for cost in plan.budget.costs:
        assert f"<code>{cost.operation}</code>, {cost.credits_per_request} each" in report


def test_an_experiment_with_a_definition_takes_the_ranking_lock(tmp_path: Path) -> None:
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    with (
        LocalArtifactStore(tmp_path / "out") as store,
        pytest.raises(ValueError, match="takes the lock"),
    ):
        ExperimentExecution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            SyntheticScreenBacktestClient(response_bytes()),
            command=None,
        )


def synthetic_plan_1_1_0() -> tuple[bytes, PlanV1_1]:
    """`synthetic.yaml`'s content and plan 1.1.0, an experiment without a ranking definition."""
    example = EXPERIMENT_CONFIGS / "synthetic.yaml"
    return example.read_bytes(), experiment_plan(example)


def test_an_experiment_is_given_its_definition_as_the_plan_has_it(tmp_path: Path) -> None:
    # So `plans/1/definition.xml` holds the definition the plan sends (R04-AC03).
    planned = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml")
    content, definition, plan = planned.content, planned.definition, planned.plan
    out = tmp_path / "out"

    def execution() -> ExperimentExecution:
        return ExperimentExecution(
            plan,
            plan.plan_hash,
            "not_required",
            LocalArtifactStore(out),
            SyntheticScreenBacktestClient(response_bytes()),
            command=None,
            ranking_lock=tmp_path / LOCK_FILE,
            pause=no_wait(),
        )

    # Another formula, so the weights' rules still hold, and only its plan differs.
    assert definition is not None
    other = definition.replace("<Formula>…</Formula>".encode(), b"<Formula>Close(0)</Formula>", 1)
    with pytest.raises(ValueError, match="doesn't give the plan"):
        execution().run(content, definition=other)
    with pytest.raises(ValueError, match="given its bytes"):
        execution().run(content)
    assert not out.exists()
    assert not (tmp_path / LOCK_FILE).exists()


def test_an_experiment_without_a_definition_is_refused_one_and_the_ranking_lock(
    tmp_path: Path,
) -> None:
    content, plan = synthetic_plan_1_1_0()
    definition = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").definition
    out = tmp_path / "out"

    def execution(lock: Path | None = None) -> ExperimentExecution:
        return ExperimentExecution(
            plan,
            plan.plan_hash,
            "not_required",
            LocalArtifactStore(out),
            SyntheticScreenBacktestClient(response_bytes()),
            command=None,
            ranking_lock=lock,
            pause=no_wait(),
        )

    with pytest.raises(ValueError, match="only an experiment with a ranking definition"):
        execution().run(content, definition=definition)
    with pytest.raises(ValueError, match="takes the lock"):
        execution(tmp_path / LOCK_FILE)
    assert not out.exists()
