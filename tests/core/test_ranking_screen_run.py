"""A screen run with a ranking definition writes its definition into `ApiRankingSystem`, then
backtests ranked by that system, in the core, with its records 1.2.0, `settings.csv` 1.1.0, and
manifest 1.1.0.

Traces to docs/contracts.md, sending a definition (the calls, nothing between them, the backtest
only after the write, the errors, the attempt's files, records 1.2.0, and counting the requests),
the ranking lock, plans with a ranking definition, weight rows, a run with a ranking definition, and
CLI behavior (the demo's client); and to R04-AC03 at the core: the calls in R04-T01's verified
order, the records holding the definition sent, byte for byte, each failing reply's outcome and
error code, and a synthetic run the core writes with the demo's client. The real client, `requests`,
and `urllib3` run over the fake server, whose end-of-test check reads every `POST /rank` body
(R04-AC09); storage faults wrap the real store; the clock is fixed; and every execution takes the
ranking lock on a file in the test's temporary directory. TS-T07 separated these tests from
tests/core/test_ranking_execution.py, with their driver, `run_screen` (docs/test-refactoring.md,
modules to separate).
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support.clock import FixedClock, no_wait
from tests.support.fake_portfolio123 import (
    AUTH,
    AUTHENTICATED,
    BACKTEST,
    CREDENTIALS,
    RANK,
    FakePortfolio123,
    Reply,
    exchange,
    response,
)
from tests.support.paths import screen_config
from tests.support.plans import ranked_screen, screen_plan
from tests.support.ranking_messages import RAN_UPDATE, UPDATING
from tests.support.storage_faults import StorageFaults
from trialfolio.contracts.attempt import AttemptRecordV1_2, StartRecordV1_2
from trialfolio.contracts.manifest import CommandRecord, RunManifestV1_1
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.provider import REQUEST_TIMEOUT_SECONDS, P123ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_settings_csv_v1_1

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


@dataclass(frozen=True)
class ScreenRun:
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
) -> ScreenRun:
    planned = ranked_screen()
    content, definition, plan = planned.content, planned.definition, planned.plan
    out = tmp_path / "out"
    real = LocalArtifactStore(out)
    store = StorageFaults(real, monkeypatch)
    for name, error in (faults or {}).items():
        store.fail_before(name, error)
    if os_fault is not None:
        store.fail_os(os_fault)
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
                CREDENTIALS, endpoint=server.endpoint, timeout=seconds
            ),
            definition=definition,
        )
    finally:
        real.close()
    received = tuple(r.request for r in server.received[before:])
    return ScreenRun(out, error, received, tuple(store.published))


# A screen run


def test_a_screen_run_writes_its_definition_then_backtests_ranked_by_api_ranking_system(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    planned = ranked_screen()
    definition, plan = planned.definition, planned.plan
    (case,) = plan.cases
    update, backtest = case.requests
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))

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
    plan = ranked_screen().plan
    (case,) = plan.cases
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))

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
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))

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
    plan = ranked_screen().plan
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
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
    plan = ranked_screen().plan
    server.reply("/auth", AUTHENTICATED)
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
    plan = ranked_screen().plan
    server.reply("/auth", AUTHENTICATED)
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
    plan = ranked_screen().plan
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")

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
    plan = ranked_screen().plan
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")

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
    planned = ranked_screen()
    content, definition, plan = planned.content, planned.definition, planned.plan
    (case,) = plan.cases
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
    out = tmp_path / "out"
    real = LocalArtifactStore(out)
    store = StorageFaults(real, monkeypatch)
    if interrupted != "attempt.json":
        store.fail_before(interrupted, KeyboardInterrupt())
    store.fail_before(f"{case.case_id}/attempt.json", KeyboardInterrupt())
    store.fail_before("attempt.json", KeyboardInterrupt())
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
                lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint),
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
    planned = ranked_screen()
    content, definition, plan = planned.content, planned.definition, planned.plan
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
    planned = ranked_screen()
    content, definition, plan = planned.content, planned.definition, planned.plan
    out = tmp_path / "out"
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
                lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint),
                definition=definition,
            )

    assert server.requests() == []
    assert not (out / "manifest.json").exists()
    assert "Neither the rank_update request nor" in execution.ending_detail()


def test_a_screen_run_is_given_its_definition_as_the_plan_has_it(tmp_path: Path) -> None:
    planned = ranked_screen()
    content, definition, plan = planned.content, planned.definition, planned.plan
    assert definition is not None
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
    plan = ranked_screen().plan

    with pytest.raises(ValueError, match="ranking lock"):
        Execution(plan, plan.plan_hash, "option", LocalArtifactStore(tmp_path / "out"), COMMAND)

    assert not (tmp_path / "out").exists()


def test_a_screen_run_without_a_definition_is_refused_one(tmp_path: Path) -> None:
    formula = screen_config("formula.yaml")
    content = formula.read_bytes()
    plan = screen_plan(formula)
    definition = ranked_screen().definition
    execution = Execution(
        plan, plan.plan_hash, "option", LocalArtifactStore(tmp_path / "out"), COMMAND
    )

    with pytest.raises(ValueError, match="only a run with a ranking definition"):
        execution.run(content, lambda: SyntheticScreenBacktestClient(b"{}"), definition=definition)

    assert not (tmp_path / "out").exists()
