"""Each case with a ranking definition writes its definition into `ApiRankingSystem`, then
backtests ranked by that system, in the core: a screen run, and a new experiment, with their
records 1.2.0 and 1.3.0, a plan's `definition.xml`, `settings.csv` 1.1.0, and manifests 1.1.0.

Traces to docs/contracts.md, sending a definition (the calls, nothing between them, the backtest
only after the write, the errors, cancellation, the attempt's files, records 1.2.0 and 1.3.0, and
counting the requests), the ranking lock, plans with a ranking definition, weight rows, a run with
a ranking definition, an experiment's normalized tables, the experiment manifest's version 1.1.0,
and CLI behavior (the demo's client); and to R04-AC03 at the core: the calls in R04-T01's verified
order, the records holding the definition sent, byte for byte, each failing reply's outcome and
error code, a cancellation that never falls between a case's two calls, and a synthetic run the
core writes with the demo's client. The real client, `requests`, and `urllib3` run over the fake
server, whose end-of-test check reads every `POST /rank` body (R04-AC09); storage faults wrap the
real store; the clock is fixed; and every execution takes the ranking lock on a file in the
test's temporary directory.
"""

import json
import logging
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support import canaries
from tests.support.clock import FixedClock
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.storage_faults import StorageFaults
from trialfolio.configuration import (
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.attempt import (
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    Exchange,
    StartRecordV1_2,
    StartRecordV1_3,
)
from trialfolio.contracts.experiment_manifest import ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecordV1_1
from trialfolio.contracts.manifest import CommandRecord, RunManifestV1_1
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.contracts.tables import SettingsRowV1_1
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.experiment_execution import Cancellation, ExperimentExecution
from trialfolio.experiment_records import open_experiment
from trialfolio.planning import (
    build_experiment_plan,
    build_experiment_plan_v1_1,
    build_plan_v1_1,
    installed_versions,
)
from trialfolio.provider import Credentials, P123ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_settings_csv_v1_1

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONFIGS = FIXTURES / "experiment-configs"
RESPONSES = FIXTURES / "responses"
SCREEN = FIXTURES / "screen-configs" / "definition.yaml"

AUTH, RANK, BACKTEST = "POST /auth", "POST /rank", "POST /screen/backtest"
COMMAND = CommandRecord(name="run", options={}, started_at=FixedClock()())
RANK_UPDATE_EVENT = "attempt.rank_update.started"

ATTEMPT_FILES = (
    "rank-update-request.json",
    "updating.json",
    "rank-update-response.json",
    "request.json",
    "started.json",
    "response.json",
    "attempt.json",
)
"""An attempt's files, in the order it writes them (sending a definition, the attempt's files)."""


def authenticated() -> Reply:
    return Reply(200, canaries.TOKEN.encode())


def updated() -> Reply:
    return Reply(200, (RESPONSES / "rank-update.json").read_bytes())


def complete() -> Reply:
    return Reply(200, (RESPONSES / "complete.json").read_bytes())


def exchange(request: str, status: int | None, result: str = "response") -> Exchange:
    return Exchange.model_validate(
        {"request": request, "result": result, "status": status, "note": None}
    )


def screen() -> tuple[bytes, bytes, PlanV1_2]:
    content = SCREEN.read_bytes()
    read = read_screen_configuration_v1_1(content, SCREEN.name, SCREEN)
    plan = build_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_2) and read.definition is not None
    return content, read.definition.content, plan


def experiment(name: str) -> tuple[bytes, bytes, PlanV1_3]:
    path = CONFIGS / name
    content = path.read_bytes()
    read = read_experiment_configuration_v1_1(content, path.name, path)
    plan = build_experiment_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_3) and read.definition is not None
    return content, read.definition.content, plan


@pytest.fixture
def server() -> Iterator[FakePortfolio123]:
    fake = FakePortfolio123()
    yield fake
    fake.close()


@dataclass(frozen=True)
class Ran:
    out: Path
    error: TrialFolioError | None
    received: tuple[str, ...]
    published: tuple[str, ...]

    def json(self, path: str) -> dict[str, object]:
        return json.loads((self.out / path).read_bytes())

    def attempt(self, case_id: str) -> Path:
        (attempt,) = sorted((self.out / "cases" / case_id / "attempts").iterdir())
        return attempt


def run_screen(
    tmp_path: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
    *,
    faults: dict[str, BaseException] | None = None,
    os_fault: str | None = None,
    timeout: int | None = None,
) -> Ran:
    content, definition, plan = screen()
    out = tmp_path / "out"
    real = LocalArtifactStore(out)
    store = StorageFaults(real, monkeypatch)
    for name, error in (faults or {}).items():
        store.fail_before(name, error)
    if os_fault is not None:
        store.fail_os(os_fault)
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    options = {} if timeout is None else {"timeout": timeout}
    before = len(server.received)
    try:
        error = Execution(
            plan,
            plan.plan_hash,
            "option",
            store,
            COMMAND,
            clock=FixedClock(),
            ranking_lock=tmp_path / LOCK_FILE,
        ).run(
            content,
            lambda: P123ScreenBacktestClient(credentials, endpoint=server.endpoint, **options),
            definition=definition,
        )
    finally:
        real.close()
    received = tuple(r.request for r in server.received[before:])
    return Ran(out, error, received, tuple(store.published))


def run_experiment(
    tmp_path: Path,
    server: FakePortfolio123,
    name: str = "ranking-example.yaml",
    *,
    cancellation: Cancellation | None = None,
) -> Ran:
    content, definition, plan = experiment(name)
    out = tmp_path / "out"
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    before = len(server.received)
    with (
        P123ScreenBacktestClient(credentials, endpoint=server.endpoint) as client,
        LocalArtifactStore(out) as store,
    ):
        error = ExperimentExecution(
            plan,
            plan.plan_hash,
            "option",
            store,
            client,
            command=None,
            clock=FixedClock(),
            cancellation=cancellation,
            ranking_lock=tmp_path / LOCK_FILE,
        ).run(content, definition=definition)
    received = tuple(r.request for r in server.received[before:])
    return Ran(out, error, received, ())


# A screen run


def test_a_screen_run_writes_its_definition_then_backtests_ranked_by_api_ranking_system(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, definition, plan = screen()
    (case,) = plan.cases
    update, backtest = case.requests
    server.reply("/auth", authenticated())
    server.reply("/rank", updated(), method="POST")
    server.reply("/screen/backtest", complete())

    ran = run_screen(tmp_path, server, monkeypatch)

    assert ran.error is None
    assert ran.received == (AUTH, RANK, BACKTEST)
    rank, sent = server.received[1], server.received[2]
    params = update.params.model_dump(mode="json")
    assert rank.body == json.dumps(params).encode()
    assert json.loads(sent.body)["screen"]["ranking"] == "ApiRankingSystem"
    assert json.loads(sent.body) == backtest.params.model_dump(mode="json")
    attempt = ran.attempt(case.case_id)
    directory = attempt.relative_to(ran.out).as_posix()
    assert ran.published == (
        "plan.json",
        "configuration.yaml",
        "definition.xml",
        *(f"{directory}/{name}" for name in ATTEMPT_FILES),
        "normalized/metrics.csv",
        "normalized/settings.csv",
        "report.html",
        "manifest.json",
    )
    # The definition's copy, and the request's, hold the definition the plan was built from.
    assert (ran.out / "definition.xml").read_bytes() == definition
    request = (attempt / "rank-update-request.json").read_bytes()
    assert request == (json.dumps(params, indent=2) + "\n").encode()
    assert json.loads(request)["nodes"] == params["nodes"]


def test_a_screen_runs_records_are_1_2_0(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, plan = screen()
    (case,) = plan.cases
    server.reply("/auth", authenticated())
    server.reply("/rank", updated(), method="POST")
    server.reply("/screen/backtest", complete())

    ran = run_screen(tmp_path, server, monkeypatch)

    attempt = ran.attempt(case.case_id)
    update = StartRecordV1_2.model_validate_json((attempt / "updating.json").read_bytes())
    start = StartRecordV1_2.model_validate_json((attempt / "started.json").read_bytes())
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (update.operation, update.exchanges) == ("rank_update", (exchange(AUTH, 200),))
    assert (start.operation, start.exchanges) == (
        "screen_backtest",
        (exchange(AUTH, 200), exchange(RANK, 200)),
    )
    assert update.model_dump(exclude={"operation", "exchanges"}) == start.model_dump(
        exclude={"operation", "exchanges"}
    )
    assert record.outcome == "succeeded"
    assert record.exchanges == (exchange(AUTH, 200), exchange(RANK, 200), exchange(BACKTEST, 200))
    assert record.ranking_update is not None
    assert record.ranking_update.request is not None
    assert record.ranking_update.request.path.endswith("/rank-update-request.json")
    assert record.ranking_update.response is not None
    assert record.ranking_update.response.form == "decoded"
    assert record.ranking_update.provider_metadata.cost == 1
    assert record.provider_metadata.cost == 5
    manifest = RunManifestV1_1.model_validate_json((ran.out / "manifest.json").read_bytes())
    assert manifest.outcome == "completed"
    assert manifest.counts.provider_requests == 2
    assert manifest.counts.cost == 6
    roles = {artifact.role: artifact for artifact in manifest.artifacts}
    assert roles["ranking_definition"].path == "definition.xml"
    assert roles["ranking_definition"].source is not None
    assert roles["ranking_definition"].source.provenance == "user_supplied"
    assert roles["update_record"].schema_version == "1.2.0"
    assert roles["settings"].schema_version == "1.1.0"
    for role in ("rank_update_request", "rank_update_response"):
        source = roles[role].source
        assert source is not None
        assert (source.operation, source.provenance) == ("rank_update", "verified")


def test_a_screen_runs_settings_csv_has_a_weight_row_for_each_node(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    server.reply("/auth", authenticated())
    server.reply("/rank", updated(), method="POST")
    server.reply("/screen/backtest", complete())

    ran = run_screen(tmp_path, server, monkeypatch)

    rows = read_settings_csv_v1_1((ran.out / "normalized/settings.csv").read_bytes(), "settings")
    manifest = RunManifestV1_1.model_validate_json((ran.out / "manifest.json").read_bytes())
    copies = {artifact.role: artifact.artifact_id for artifact in manifest.artifacts}
    settings = [row.setting for row in rows]
    weights = [row for row in rows if row.node is not None]
    assert settings.index("ranking") + 1 == settings.index("ranking_weight")
    assert [row.node for row in weights] == [
        "Value",
        "Value/Earnings Yield",
        "Value/Sales Yield",
        "Momentum",
        "Momentum/Six-Month Return",
        "Momentum/Year Return",
        "Quality",
        "Quality/Return on Equity",
        "Quality/Gross Margin",
    ]
    assert [row.value for row in weights] == ["40", "50", "50", "30", "50", "50", "30", "50", "50"]
    for row in weights:
        assert (row.original_key, row.provenance) == ("ranking.definition", "verified")
        assert row.source_artifact == copies["ranking_definition"]
    (ranking,) = [row for row in rows if row.setting == "ranking"]
    assert ranking.original_key == "ranking"
    assert ranking.source_artifact == copies["configuration"]
    assert all(row.node is None for row in rows if row.setting != "ranking_weight")


def test_a_rank_updates_events_name_its_case_and_attempt_never_the_definition(
    tmp_path: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, _, plan = screen()
    server.reply("/auth", authenticated())
    server.reply("/rank", updated(), method="POST")
    server.reply("/screen/backtest", complete())
    caplog.set_level(logging.DEBUG, logger="trialfolio")

    ran = run_screen(tmp_path, server, monkeypatch)

    assert ran.error is None
    (started,) = [r for r in caplog.records if getattr(r, "event", None) == RANK_UPDATE_EVENT]
    assert "rank_update" in started.getMessage()
    assert getattr(started, "case_id", None) == plan.cases[0].case_id
    assert getattr(started, "attempt_id", None) == ran.attempt(plan.cases[0].case_id).name
    events = {getattr(r, "event", None) for r in caplog.records}
    assert {"ranking.lock.taken", "ranking.lock.released"} <= events
    # Logs never hold the user's strategy definition: no node's name, and no path to one.
    logged = "\n".join(r.getMessage() for r in caplog.records)
    for name in ("Earnings Yield", "Sales Yield", "Six-Month Return", "Gross Margin", "…"):
        assert name not in logged
    assert "value-momentum.xml" not in logged


@pytest.mark.parametrize(
    ("reply", "outcome", "code"),
    [
        (Reply(400, b"Invalid ranking system"), "failed", "provider.unsupported_capability"),
        (Reply(409, b"Conflict"), "failed", "provider.unsupported_capability"),
        (Reply(402, b""), "failed", "provider.quota_exceeded"),
        (Reply(401, b""), "failed", "provider.auth_failed"),
        (Reply(403, b""), "failed", "provider.auth_failed"),
        (Reply(503, b""), "unknown", "provider.outcome_unknown"),
        (Reply(200, b"<html>not JSON</html>"), "failed", "provider.response_invalid"),
    ],
    ids=["400", "409", "402", "401", "403", "503", "200 not JSON"],
)
def test_after_each_failing_reply_to_a_rank_update_the_backtest_isnt_sent(
    tmp_path: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
    reply: Reply,
    outcome: str,
    code: str,
) -> None:
    _, _, plan = screen()
    server.reply("/auth", authenticated())
    server.reply("/rank", reply, method="POST")

    ran = run_screen(tmp_path, server, monkeypatch)

    assert ran.received == (AUTH, RANK)
    assert ran.error is not None
    assert ran.error.code == code
    attempt = ran.attempt(plan.cases[0].case_id)
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == (outcome, True)
    assert record.error is not None
    assert record.error.code == code
    assert not (attempt / "request.json").exists()
    assert not (attempt / "started.json").exists()
    raw = (attempt / "rank-update-response.raw").exists()
    assert raw == (code == "provider.response_invalid")
    # The run is accounted for: its manifest gives the attempt's error.
    manifest = RunManifestV1_1.model_validate_json((ran.out / "manifest.json").read_bytes())
    assert manifest.outcome == "failed"
    assert manifest.error is not None
    assert manifest.error.code == code
    assert manifest.counts.provider_requests == 1


def test_a_rank_update_that_times_out_leaves_the_attempt_unknown(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, plan = screen()
    server.reply("/auth", authenticated())
    server.reply("/rank", Reply(200, b"{}", delay=3), method="POST")

    ran = run_screen(tmp_path, server, monkeypatch, timeout=1)

    assert ran.received == (AUTH, RANK)
    assert ran.error is not None
    assert ran.error.code == "provider.outcome_unknown"
    attempt = ran.attempt(plan.cases[0].case_id)
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert record.exchanges[-1] == exchange(RANK, None, "interrupted")


def test_no_backtest_follows_a_rank_update_whose_response_wasnt_saved(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, plan = screen()
    server.reply("/auth", authenticated())
    server.reply("/rank", updated(), method="POST")

    ran = run_screen(tmp_path, server, monkeypatch, os_fault="rank-update-response.json")

    assert ran.received == (AUTH, RANK)
    assert ran.error is not None
    assert ran.error.code == "storage.write_failed"
    attempt = ran.attempt(plan.cases[0].case_id)
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.ranking_update is not None
    assert record.ranking_update.response is None
    assert not (ran.out / "manifest.json").exists()


def test_an_interrupt_after_the_rank_updates_response_sends_no_backtest(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, plan = screen()
    server.reply("/auth", authenticated())
    server.reply("/rank", updated(), method="POST")

    ran = run_screen(tmp_path, server, monkeypatch, faults={"request.json": KeyboardInterrupt()})

    assert ran.received == (AUTH, RANK)
    assert ran.error is not None
    assert ran.error.code == "command.interrupted"
    assert "The screen backtest request wasn't sent" in ran.error.message
    attempt = ran.attempt(plan.cases[0].case_id)
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.ranking_update is not None
    assert record.ranking_update.response is not None
    assert not (ran.out / "manifest.json").exists()


def test_the_core_writes_a_synthetic_run_with_the_demos_client(tmp_path: Path) -> None:
    content, definition, plan = screen()
    lock = tmp_path / LOCK_FILE
    out = tmp_path / "out"
    with LocalArtifactStore(out) as store:
        error = Execution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            None,
            clock=FixedClock(),
            ranking_lock=lock,
        ).run(
            content, lambda: SyntheticScreenBacktestClient(response_bytes()), definition=definition
        )

    assert error is None
    manifest = RunManifestV1_1.model_validate_json((out / "manifest.json").read_bytes())
    assert (manifest.outcome, manifest.synthetic, manifest.command, manifest.approval) == (
        "completed",
        True,
        None,
        "not_required",
    )
    (attempt,) = sorted((out / "cases" / plan.cases[0].case_id / "attempts").iterdir())
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert record.exchanges == (exchange(AUTH, 200), exchange(RANK, 200), exchange(BACKTEST, 200))
    for name in ATTEMPT_FILES:
        assert (attempt / name).exists()
    assert (out / "definition.xml").read_bytes() == definition
    # The report names each weight row's node, by its canonical path, beside its setting.
    report = (out / "report.html").read_text(encoding="utf-8")
    assert "<code>ranking_weight</code> <code>Value/Earnings Yield</code>" in report
    # Its configuration is acquired when its execution began, since no command started.
    configuration = next(a for a in manifest.artifacts if a.role == "configuration")
    assert configuration.source is not None
    assert configuration.source.acquired_at == FixedClock()()
    assert lock.exists()


def test_a_screen_run_is_given_its_definition_as_the_plan_has_it(tmp_path: Path) -> None:
    content, definition, plan = screen()
    store = LocalArtifactStore(tmp_path / "out")
    execution = Execution(
        plan, plan.plan_hash, "option", store, COMMAND, ranking_lock=tmp_path / LOCK_FILE
    )

    with pytest.raises(ValueError, match="definition"):
        execution.run(content, lambda: SyntheticScreenBacktestClient(b"{}"))
    with pytest.raises(ValueError, match="plan's"):
        Execution(
            plan, plan.plan_hash, "option", store, COMMAND, ranking_lock=tmp_path / LOCK_FILE
        ).run(
            content,
            lambda: SyntheticScreenBacktestClient(b"{}"),
            definition=definition.replace(b'Weight="40"', b'Weight="45"'),
        )
    assert not (tmp_path / "out").exists()


# A new experiment


def script_experiment(server: FakePortfolio123, cases: int) -> None:
    server.reply("/auth", authenticated())
    server.reply("/rank", *(updated() for _ in range(cases)), method="POST")
    server.reply("/screen/backtest", *(complete() for _ in range(cases)))


def test_each_case_of_an_experiment_writes_its_definition_then_backtests(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    _, definition, plan = experiment("ranking-example.yaml")
    script_experiment(server, 4)

    ran = run_experiment(tmp_path, server)

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
    _, _, plan = experiment("ranking-example.yaml")
    script_experiment(server, 4)

    ran = run_experiment(tmp_path, server)

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


def test_an_experiments_cases_settings_csv_takes_each_weights_original(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    _, _, plan = experiment("ranking-example.yaml")
    script_experiment(server, 4)

    ran = run_experiment(tmp_path, server)

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


def test_a_variant_of_another_setting_sends_the_baselines_definition(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    _, _, plan = experiment("ranking-mixed.yaml")
    script_experiment(server, len(plan.cases))

    ran = run_experiment(tmp_path, server, "ranking-mixed.yaml")

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
    _, _, plan = experiment("ranking-example.yaml")
    server.reply("/auth", authenticated())
    server.reply("/rank", Reply(402, b""), method="POST")

    ran = run_experiment(tmp_path, server)

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
    server.reply("/auth", authenticated(), authenticated())
    server.reply("/rank", Reply(401, b""), *(updated() for _ in range(3)), method="POST")
    server.reply("/screen/backtest", *(complete() for _ in range(3)))

    ran = run_experiment(tmp_path, server)

    assert ran.received == (AUTH, RANK, AUTH, *(RANK, BACKTEST) * 3)
    assert ran.error is not None
    assert ran.error.code == "execution.partial"


def test_a_cancellation_never_falls_between_a_cases_two_calls(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    _, _, plan = experiment("ranking-example.yaml")
    release = threading.Event()
    server.reply("/auth", authenticated())
    server.reply("/rank", Reply(200, updated().body, release=release), method="POST")
    server.reply("/screen/backtest", complete())
    cancellation = Cancellation()
    ran: list[Ran] = []
    thread = threading.Thread(
        target=lambda: ran.append(run_experiment(tmp_path, server, cancellation=cancellation))
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


def test_the_core_writes_a_synthetic_experiment_with_the_demos_client(tmp_path: Path) -> None:
    content, definition, plan = experiment("ranking-example.yaml")
    out = tmp_path / "out"
    with LocalArtifactStore(out) as store:
        error = ExperimentExecution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            SyntheticScreenBacktestClient(response_bytes()),
            command=None,
            clock=FixedClock(),
            ranking_lock=tmp_path / LOCK_FILE,
        ).run(content, definition=definition)

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


def test_an_experiment_with_a_definition_takes_the_ranking_lock(tmp_path: Path) -> None:
    _, _, plan = experiment("ranking-example.yaml")
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


def test_an_experiment_with_a_definition_isnt_resumed_by_this_executor_yet(
    tmp_path: Path,
) -> None:
    # Resuming or revising one is release 0.4.0's R04-T09: until then, the executor refuses a
    # plan 1.3.0 given an experiment's records, here a synthetic one's of plan 1.1.0.
    example = CONFIGS / "synthetic.yaml"
    content = example.read_bytes()
    earlier = build_experiment_plan(
        read_experiment_configuration(content, example.name), installed_versions()
    )
    out = tmp_path / "out"
    with LocalArtifactStore(out) as store:
        ExperimentExecution(
            earlier,
            earlier.plan_hash,
            "not_required",
            store,
            SyntheticScreenBacktestClient(response_bytes()),
            command=None,
            clock=FixedClock(),
        ).run(content)
    _, _, plan = experiment("ranking-example.yaml")
    with LocalArtifactStore(out) as store:
        saved = open_experiment(store)
        with pytest.raises(TypeError):
            ExperimentExecution(
                plan,
                plan.plan_hash,
                "not_required",
                store,
                SyntheticScreenBacktestClient(response_bytes()),
                command=None,
                experiment=saved,
                ranking_lock=tmp_path / LOCK_FILE,
            )
