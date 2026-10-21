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
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support import canaries
from tests.support.clock import FixedClock, no_wait
from tests.support.fake_portfolio123 import FakePortfolio123, Reply, distinct
from tests.support.storage_faults import StorageFaults
from trialfolio.configuration import (
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
    read_screen_configuration,
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
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecordV1_1
from trialfolio.contracts.manifest import CommandRecord, RunManifestV1_1
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.contracts.tables import SettingsRowV1_1
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.experiment_execution import Cancellation, ExperimentExecution
from trialfolio.planning import (
    build_experiment_plan,
    build_experiment_plan_v1_1,
    build_plan,
    build_plan_v1_1,
    installed_versions,
)
from trialfolio.provider import REQUEST_TIMEOUT_SECONDS, Credentials, P123ScreenBacktestClient
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
    execution: ExperimentExecution | None = None

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
    seconds = REQUEST_TIMEOUT_SECONDS if timeout is None else timeout
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
            pause=no_wait(),
        ).run(
            content,
            lambda: P123ScreenBacktestClient(
                credentials, endpoint=server.endpoint, timeout=seconds
            ),
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
    faults: tuple[pytest.MonkeyPatch, Callable[[StorageFaults], object]] | None = None,
) -> Ran:
    """Runs the experiment over the fake server. `faults` sets the storage faults, which wrap the
    real store."""
    content, definition, plan = experiment(name)
    out = tmp_path / "out"
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    before = len(server.received)
    with (
        P123ScreenBacktestClient(credentials, endpoint=server.endpoint) as client,
        LocalArtifactStore(out) as real,
    ):
        store: LocalArtifactStore | StorageFaults = real
        if faults is not None:
            monkeypatch, set_faults = faults
            store = StorageFaults(real, monkeypatch)
            set_faults(store)
        execution = ExperimentExecution(
            plan,
            plan.plan_hash,
            "option",
            store,
            client,
            command=None,
            clock=FixedClock(),
            cancellation=cancellation,
            ranking_lock=tmp_path / LOCK_FILE,
            pause=no_wait(),
        )
        error = execution.run(content, definition=definition)
    received = tuple(r.request for r in server.received[before:])
    published = tuple(store.published) if isinstance(store, StorageFaults) else ()
    return Ran(out, error, received, published, execution)


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
    # Each is acquired when it was: the definition with the configuration, when the command
    # started; the rank_update's request when the attempt started, and its response when it ended.
    acquired = {
        role: artifact.source.acquired_at for role, artifact in roles.items() if artifact.source
    }
    assert record.started_at < record.ended_at
    assert acquired["ranking_definition"] == acquired["configuration"] == COMMAND.started_at
    assert acquired["rank_update_request"] == record.started_at
    assert acquired["rank_update_response"] == record.ended_at


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


RAN_UPDATE: tuple[str, ...] = (
    (
        "The rank_update request{of}, which writes the case's ranking definition into"
        " ApiRankingSystem, reached Portfolio123, and may have been charged."
    ),
    (
        "screen backtest request may have been sent, and may have been charged: {record} start"
        " record reads as running."
    ),
)
"""What an ending's message says of an attempt with a definition whose start record,
`started.json`, was written, and its attempt record wasn't: its `rank_update` reached
Portfolio123, since that start record follows only its 200, and its backtest may have been sent."""

UPDATING: tuple[str, ...] = (
    (
        "The rank_update request{of}, which writes the case's ranking definition into"
        " ApiRankingSystem, may have been sent, and may have been charged: {record} update record"
        " was written, and its screen backtest request wasn't sent."
    ),
)
"""The same, for an attempt whose latest record is its update record, `updating.json`."""


@pytest.mark.parametrize(
    ("interrupted", "said"),
    [("attempt.json", RAN_UPDATE), ("request.json", UPDATING)],
    ids=["after its start record", "after its update record"],
)
def test_a_second_interrupt_at_the_attempt_record_says_what_each_request_did(
    tmp_path: Path,
    server: FakePortfolio123,
    monkeypatch: pytest.MonkeyPatch,
    interrupted: str,
    said: tuple[str, ...],
) -> None:
    # Interrupted, the attempt writes its record once more, and a second interrupt there ends the
    # run without it. A defect found by the review of R04-T08's pull request: the message said
    # only that the backtest may have been sent, though the rank_update had reached Portfolio123.
    content, definition, plan = screen()
    (case,) = plan.cases
    server.reply("/auth", authenticated())
    server.reply("/rank", updated(), method="POST")
    server.reply("/screen/backtest", complete())
    out = tmp_path / "out"
    real = LocalArtifactStore(out)
    store = StorageFaults(real, monkeypatch)
    if interrupted != "attempt.json":
        store.fail_before(interrupted, KeyboardInterrupt())
    store.fail_before(f"{case.case_id}/attempt.json", KeyboardInterrupt())
    store.fail_before("attempt.json", KeyboardInterrupt())
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    execution = Execution(
        plan,
        plan.plan_hash,
        "option",
        store,
        COMMAND,
        ranking_lock=tmp_path / LOCK_FILE,
        pause=no_wait(),
    )
    try:
        with pytest.raises(KeyboardInterrupt):
            execution.run(
                content,
                lambda: P123ScreenBacktestClient(credentials, endpoint=server.endpoint),
                definition=definition,
            )
    finally:
        real.close()

    attempt = next((out / "cases" / case.case_id / "attempts").iterdir())
    assert not (attempt / "attempt.json").exists()
    detail = execution.ending_detail()
    for part in said:
        assert part.format(of="", record="the attempt's") in detail


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
            pause=no_wait(),
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


def test_a_run_without_a_command_sends_nothing_with_a_client_that_isnt_the_demos(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # A run without a command is synthetic, so its manifest would say its values are invented. A
    # defect found by the review of R04-T08's pull request: a real client's requests were sent,
    # and the run recorded as synthetic.
    content, definition, plan = screen()
    out = tmp_path / "out"
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    with LocalArtifactStore(out) as store:
        execution = Execution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            None,
            clock=FixedClock(),
            ranking_lock=tmp_path / LOCK_FILE,
            pause=no_wait(),
        )
        with pytest.raises(ValueError, match="demo's"):
            execution.run(
                content,
                lambda: P123ScreenBacktestClient(credentials, endpoint=server.endpoint),
                definition=definition,
            )

    assert server.requests() == []
    assert not (out / "manifest.json").exists()
    assert "Neither the rank_update request nor" in execution.ending_detail()


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


def test_a_screen_run_with_a_definition_is_refused_without_the_ranking_lock(
    tmp_path: Path,
) -> None:
    # So the core never executes a definition without the lock (R04-AC05).
    _, _, plan = screen()

    with pytest.raises(ValueError, match="ranking lock"):
        Execution(plan, plan.plan_hash, "option", LocalArtifactStore(tmp_path / "out"), COMMAND)

    assert not (tmp_path / "out").exists()


def test_a_screen_run_without_a_definition_is_refused_one(tmp_path: Path) -> None:
    formula = FIXTURES / "screen-configs" / "formula.yaml"
    content = formula.read_bytes()
    plan = build_plan(read_screen_configuration(content, formula.name), installed_versions())
    _, definition, _ = screen()
    execution = Execution(
        plan, plan.plan_hash, "option", LocalArtifactStore(tmp_path / "out"), COMMAND
    )

    with pytest.raises(ValueError, match="only a run with a ranking definition"):
        execution.run(content, lambda: SyntheticScreenBacktestClient(b"{}"), definition=definition)

    assert not (tmp_path / "out").exists()


# A new experiment


def script_experiment(server: FakePortfolio123, cases: int) -> None:
    """Each case's `rank_update` gets a 200, and its backtest a response of its own, so none is a
    stale backtest (D-45)."""
    server.reply("/auth", authenticated())
    server.reply("/rank", *(updated() for _ in range(cases)), method="POST")
    server.reply("/screen/backtest", *distinct(*(complete().body for _ in range(cases))))


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


def test_only_a_weight_a_variant_changes_takes_its_original_from_the_variant(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # Weight rows (what a variant changes), as R04-T08 settled it: a `set` entry gives a row's
    # original only when it changes the baseline's weight, compared as decimals; and a removal's
    # rows are named by the case's own canonical paths, where a position the removal changes
    # becomes a name. ranking-example.yaml's entries all change their weights, and its removal
    # renames nothing, so neither rule had a test (the review of R04-T08's pull request).
    _, _, plan = experiment("ranking-positions.yaml")
    script_experiment(server, len(plan.cases))

    ran = run_experiment(tmp_path, server, "ranking-positions.yaml")

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
    server.reply("/screen/backtest", *distinct(*(complete().body for _ in range(3))))

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
    faults: dict[str, str],
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
        for name, fault in faults.items():
            match fault:
                case "full disk":
                    store.fail_os(name)
                case "published":
                    sync = TrialFolioError("storage.write_failed", "Couldn't sync the directory.")
                    store.fail_after(name, sync)
                case _:
                    store.fail_before(name, RuntimeError())

    ran = run_experiment(tmp_path, server, faults=(monkeypatch, set_faults))

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
    _, _, plan = experiment("ranking-example.yaml")
    first = plan.cases[0].case_id
    script_experiment(server, 4)

    def set_faults(store: StorageFaults) -> None:
        if interrupted != "attempt.json":
            store.fail_before(interrupted, KeyboardInterrupt())
        store.fail_before(f"{first}/attempt.json", KeyboardInterrupt())
        store.fail_before("attempt.json", KeyboardInterrupt())

    ran = run_experiment(tmp_path, server, faults=(monkeypatch, set_faults))

    assert ran.error is not None
    assert ran.error.code == "command.interrupted"
    for part in said:
        assert part.format(of=" of the attempt under way", record="its") in ran.error.message


def test_an_update_record_published_before_its_write_failed_counts_as_written(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Its rank_update isn't sent, and its attempt record agrees with the update record the store
    # published, as for any start record: the attempt authenticated, and its token is its own.
    _, _, plan = experiment("ranking-example.yaml")
    first = plan.cases[0].case_id
    script_experiment(server, 4)

    def set_faults(store: StorageFaults) -> None:
        store.fail_after(f"{first}/updating.json", RuntimeError())

    ran = run_experiment(tmp_path, server, faults=(monkeypatch, set_faults))

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
    _, _, plan = experiment("ranking-example.yaml")
    first = plan.cases[0].case_id
    script_experiment(server, 4)

    def set_faults(store: StorageFaults) -> None:
        store.fail_after(f"{first}/rank-update-response.json", RuntimeError())

    ran = run_experiment(tmp_path, server, faults=(monkeypatch, set_faults))

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
            pause=no_wait(),
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


def synthetic_plan_1_1_0() -> tuple[bytes, PlanV1_1]:
    """`synthetic.yaml`'s content and plan 1.1.0, an experiment without a ranking definition."""
    example = CONFIGS / "synthetic.yaml"
    content = example.read_bytes()
    plan = build_experiment_plan(
        read_experiment_configuration(content, example.name), installed_versions()
    )
    return content, plan


def test_an_experiment_is_given_its_definition_as_the_plan_has_it(tmp_path: Path) -> None:
    # So `plans/1/definition.xml` holds the definition the plan sends (R04-AC03).
    content, definition, plan = experiment("ranking-example.yaml")
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
    _, definition, _ = experiment("ranking-example.yaml")
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
