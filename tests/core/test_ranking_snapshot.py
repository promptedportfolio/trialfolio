"""A ranking snapshot, in the core: its run, which reads the system its configuration names with one
`rank_get`, and writes its plan, its attempt's records 1.2.0, `definition.xml`, `snapshot.json`, and
its manifest; and a synthetic snapshot the core takes with the demo's client.

Traces to docs/contracts.md, ranking snapshot output (its steps, plan, layout, records, manifest,
response, `definition.xml`, `snapshot.json`, and the executors), and CLI behavior (the demo's
client); and to R04-AC08 at the core: the snapshot's files and records, its failures, and the
synthetic snapshot, which takes no lock. The real client, `requests`, and `urllib3` run over the
fake server, whose end-of-test check reads every request's path; and the clock is fixed. Each
snapshot is taken with tests/support/snapshot_builder.py's `take`, since TS-T07 separated the tests
of reading a snapshot as a configuration's ranking into tests/core/test_ranking_from_snapshot.py,
which take theirs with it too (docs/test-refactoring.md, modules to separate).
"""

import json
from pathlib import Path

import pytest

from tests.support.clock import FixedClock
from tests.support.fake_portfolio123 import (
    AUTH,
    CREDENTIALS,
    RANK_GET,
    FakePortfolio123,
    Reply,
    exchange,
    response,
)
from tests.support.paths import RANKING_DEFINITIONS, RESPONSES
from tests.support.snapshot_builder import (
    SNAPSHOT_COMMAND,
    STARTED_AT,
    artifact_id,
    read_json,
    snapshot_plan,
    system_reply,
    take,
)
from trialfolio.contracts.attempt import AttemptRecordV1_2, StartRecordV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotManifest, RankingSnapshotRecord
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.snapshot_execution import SnapshotExecution
from trialfolio.storage import LocalArtifactStore

DEFINITION = RANKING_DEFINITIONS / "value-momentum.xml"


def attempt_directory(out: Path) -> Path:
    (attempt,) = sorted((out / "attempts").iterdir())
    return attempt


# The snapshot's run


def test_a_snapshot_reads_the_system_with_one_rank_get_and_writes_its_records(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    _, plan = snapshot_plan()
    out = tmp_path / "snapshot"

    execution, error = take(server, out)

    assert error is None
    # Trial Folio's authentication, then the one rank_get, by the system's name, and nothing
    # else: nothing is written to the account (R04-AC09).
    assert [r.request for r in server.received] == [AUTH, RANK_GET]
    assert server.received[1].path == "/rank?name=Value+and+momentum"
    attempt = attempt_directory(out)
    assert sorted(p.name for p in attempt.iterdir()) == [
        "attempt.json",
        "request.json",
        "response.json",
        "started.json",
    ]
    assert read_json(attempt / "request.json") == {"name": "Value and momentum"}
    start = StartRecordV1_2.model_validate_json((attempt / "started.json").read_bytes())
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (start.operation, start.case_id, start.plan_hash) == ("rank_get", None, plan.plan_hash)
    assert (record.operation, record.case_id, record.ranking_update) == ("rank_get", None, None)
    assert record.outcome == "succeeded"
    assert record.exchanges == (exchange(AUTH, 200), exchange(RANK_GET, 200))
    assert (record.provider_metadata.cost, record.provider_metadata.quota_remaining) == (1, 4319)
    # definition.xml is the response's xml, encoded as UTF-8, byte for byte.
    response = read_json(RESPONSES / "rank-get.json")
    definition = (out / "definition.xml").read_bytes()
    assert definition == str(response["xml"]).encode("utf-8")
    assert definition == DEFINITION.read_bytes()
    snapshot = RankingSnapshotRecord.model_validate_json((out / "snapshot.json").read_bytes())
    assert snapshot.model_dump(mode="json") == {
        "schema_version": "1.0.0",
        "trialfolio_version": plan.trialfolio_version,
        "requested": "Value and momentum",
        "system": {
            "name": "Value and momentum",
            "id": 104729,
            "ranking_method": 2,
            "currency": "USD",
            "type": "Stock",
        },
        "taken_at": record.ended_at.isoformat().replace("+00:00", "Z"),
        "attempt_id": str(record.attempt_id),
        "plan_hash": plan.plan_hash,
        "definition": artifact_id(definition),
        "response": artifact_id((attempt / "response.json").read_bytes()),
    }
    assert execution.record == snapshot
    assert execution.problems == ()


def test_a_snapshots_manifest_lists_every_file_with_its_role_and_source(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    _, plan = snapshot_plan()
    out = tmp_path / "snapshot"

    take(server, out)

    manifest = RankingSnapshotManifest.model_validate_json((out / "manifest.json").read_bytes())
    attempt = attempt_directory(out).relative_to(out).as_posix()
    record = AttemptRecordV1_2.model_validate_json((out / attempt / "attempt.json").read_bytes())
    assert (manifest.outcome, manifest.error, manifest.synthetic) == ("completed", None, False)
    assert (manifest.command, manifest.approval) == (SNAPSHOT_COMMAND, "option")
    assert manifest.plan_hash == plan.plan_hash
    listed = {a.path: a for a in manifest.artifacts}
    assert list(listed) == [
        "plan.json",
        "configuration.yaml",
        f"{attempt}/request.json",
        f"{attempt}/started.json",
        f"{attempt}/response.json",
        f"{attempt}/attempt.json",
        "definition.xml",
        "snapshot.json",
    ]
    for path, artifact in listed.items():
        assert artifact.artifact_id == artifact_id((out / path).read_bytes())
    assert [(a.role, a.schema_version) for a in manifest.artifacts if a.source is None] == [
        ("plan", "1.0.0"),
        ("start_record", "1.2.0"),
        ("attempt_record", "1.2.0"),
        ("ranking_snapshot_record", "1.0.0"),
    ]
    sources = {
        a.role: (
            s.format,
            s.format_version,
            s.parser_version,
            s.provenance,
            s.operation,
            s.acquired_at,
        )
        for a in manifest.artifacts
        if (s := a.source) is not None
    }
    assert sources == {
        "configuration": (
            "ranking-snapshot-configuration",
            "1.0.0",
            None,
            "user_supplied",
            None,
            STARTED_AT,
        ),
        "provider_request": (
            "p123api-rank-get-request",
            "1",
            None,
            "verified",
            "rank_get",
            record.started_at,
        ),
        "provider_response": ("p123api-rank-get", "1", 1, "verified", "rank_get", record.ended_at),
        "ranking_definition": (
            "ranking-definition",
            "1",
            None,
            "verified",
            "rank_get",
            record.ended_at,
        ),
    }
    assert [p.model_dump() for p in manifest.parsers] == [
        {"layout": "p123api-rank-get", "layout_version": 1, "parser_version": 1}
    ]
    assert manifest.counts.model_dump() == {
        "attempts": {"succeeded": 1, "failed": 0, "unknown": 0, "running": 0},
        "provider_requests": 1,
        "retries": 0,
        "cost": 1,
    }


def test_a_snapshot_of_a_system_that_cant_be_a_ranking_completes_and_says_why(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    """The snapshot is the evidence of what the system held, whatever it holds: whether it can
    be a ranking is checked each time a configuration names it."""
    execution, error = take(server, tmp_path / "snapshot", response("rank-get-type-etf.json"))

    assert error is None
    assert (tmp_path / "snapshot" / "definition.xml").is_file()
    assert execution.problems == ("whose system's type isn't Stock",)


@pytest.mark.parametrize(
    ("reply", "code", "outcome"),
    [
        (Reply(404, b"Not found"), "provider.request_rejected", "failed"),
        (Reply(503, b""), "provider.outcome_unknown", "unknown"),
        (response("rank-get-without-xml.json"), "provider.response_invalid", "succeeded"),
        (response("rank-get-unknown-method.json"), "provider.response_invalid", "succeeded"),
        (response("rank-get-lone-surrogate.json"), "provider.response_invalid", "succeeded"),
    ],
    ids=["404", "503", "without-xml", "unknown-method", "lone-surrogate"],
)
def test_a_failed_rank_get_leaves_no_definition_and_a_failed_manifest(
    tmp_path: Path, server: FakePortfolio123, reply: Reply, code: str, outcome: str
) -> None:
    out = tmp_path / "snapshot"

    execution, error = take(server, out, reply)

    assert error is not None and error.code == code
    assert not (out / "definition.xml").exists()
    assert not (out / "snapshot.json").exists()
    assert execution.record is None
    manifest = RankingSnapshotManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert (manifest.outcome, manifest.error and manifest.error.code) == ("failed", code)
    record = AttemptRecordV1_2.model_validate_json(
        (attempt_directory(out) / "attempt.json").read_bytes()
    )
    # A response without the structure is saved, and the attempt succeeded for capture.
    assert record.outcome == outcome


@pytest.mark.parametrize(
    "reply",
    [
        system_reply(id=True),
        system_reply(rankingMethod=2.0),
        system_reply(currency=None),
        Reply(
            200,
            json.dumps(read_json(RESPONSES / "rank-get.json"))
            .replace('"Value and momentum"', '"Value \\ud800"')
            .encode(),
        ),
    ],
    ids=["id-boolean", "method-float", "currency-null", "name-lone-surrogate"],
)
def test_a_response_without_the_structure_a_snapshot_needs_is_invalid(
    tmp_path: Path, server: FakePortfolio123, reply: Reply
) -> None:
    """An object with `name`, `xml`, `currency`, and `type` as text that UTF-8 can encode, and
    `id` and `rankingMethod` as integers, never booleans (the response)."""
    out = tmp_path / "snapshot"

    _, error = take(server, out, reply)

    assert error is not None and error.code == "provider.response_invalid"
    assert "doesn't have the structure a snapshot needs" in error.message
    assert not (out / "definition.xml").exists()
    assert (out / "manifest.json").is_file()


def test_an_interrupt_while_the_response_is_saved_leaves_no_manifest(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The message says what the attempt's records say of its `rank_get`, and that the snapshot
    has no manifest (endings that decide the error code)."""
    out = tmp_path / "snapshot"

    _, error = take(server, out, faults=(monkeypatch, "response.json", KeyboardInterrupt()))

    assert error is not None and error.code == "command.interrupted"
    assert "The rank_get request may have been charged" in error.message
    assert "screen backtest" not in error.message
    assert not (out / "manifest.json").exists()
    assert not (out / "definition.xml").exists()


@pytest.mark.parametrize("name", ["definition.xml", "snapshot.json"])
def test_a_storage_failure_at_the_snapshots_files_leaves_no_manifest(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    out = tmp_path / "snapshot"
    failure = TrialFolioError("storage.write_failed", "The disk is full.")

    _, error = take(server, out, faults=(monkeypatch, name, failure))

    assert error is not None and error.code == "storage.write_failed"
    # Its attempt record says the rank_get succeeded, so the message does, and names no backtest.
    assert "The rank_get request succeeded, and its response was saved." in error.message
    assert "screen backtest" not in error.message
    assert "The snapshot has no manifest, so its output is incomplete." in error.message
    assert not (out / "manifest.json").exists()


def test_a_snapshot_without_its_attempt_record_says_its_rank_get_may_have_been_sent(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only its start record says what became of the `rank_get`, so what the snapshot's records
    say, for an ending the command doesn't record itself, such as a second interrupt, is that it
    may have been sent and charged (the CLI's `ending_detail`)."""
    out = tmp_path / "snapshot"
    failure = TrialFolioError("storage.write_failed", "The disk is full.")

    execution, error = take(server, out, faults=(monkeypatch, "attempt.json", failure))

    assert error is not None and error.code == "storage.write_failed"
    assert (attempt_directory(out) / "started.json").is_file()
    assert not (attempt_directory(out) / "attempt.json").exists()
    assert not (out / "manifest.json").exists()
    detail = execution.ending_detail()
    assert detail.startswith(
        "The rank_get request may have been sent, and may have been charged: the attempt's start"
        " record reads as running."
    )
    assert "screen backtest" not in detail


def test_a_ranking_method_the_wrapper_doesnt_know_is_saved_undecoded(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    out = tmp_path / "snapshot"

    _, error = take(server, out, response("rank-get-unknown-method.json"))

    assert error is not None
    attempt = attempt_directory(out)
    assert (attempt / "response.raw").read_bytes() == (
        RESPONSES / "rank-get-unknown-method.json"
    ).read_bytes()
    assert "response.raw" in error.message
    assert "The snapshot has no definition.xml or snapshot.json." in error.message


def test_a_rank_get_that_times_out_has_an_unknown_outcome(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    out = tmp_path / "snapshot"

    _, error = take(server, out, Reply(200, b"{}", delay=3), timeout=1)

    assert error is not None and error.code == "provider.outcome_unknown"
    assert "rank_get request" in error.message
    record = AttemptRecordV1_2.model_validate_json(
        (attempt_directory(out) / "attempt.json").read_bytes()
    )
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert not (out / "definition.xml").exists()


def test_the_core_takes_a_synthetic_snapshot_with_the_demos_client(tmp_path: Path) -> None:
    """The demo's client answers the `rank_get` with the invented system its caller gives, and
    sends nothing: the snapshot's manifest says it's synthetic, with no command and the approval
    `not_required`. A snapshot takes no lock: its execution has none to take (CLI behavior)."""
    content, plan = snapshot_plan()
    out = tmp_path / "snapshot"
    system = (RESPONSES / "rank-get.json").read_bytes()

    with LocalArtifactStore(out) as store:
        execution = SnapshotExecution(
            plan, plan.plan_hash, "not_required", store, None, clock=FixedClock()
        )
        error = execution.run(
            content, lambda: SyntheticScreenBacktestClient(response_bytes(), system=system)
        )

    assert error is None
    manifest = RankingSnapshotManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert (manifest.synthetic, manifest.command, manifest.approval) == (True, None, "not_required")
    assert manifest.outcome == "completed"
    record = AttemptRecordV1_2.model_validate_json(
        (attempt_directory(out) / "attempt.json").read_bytes()
    )
    assert record.exchanges == (exchange(AUTH, 200), exchange(RANK_GET, 200))
    assert (out / "definition.xml").read_bytes() == DEFINITION.read_bytes()
    assert (out / "snapshot.json").is_file()
    configuration = next(a for a in manifest.artifacts if a.role == "configuration")
    # No command started, so the configuration is acquired when the execution began.
    assert configuration.source is not None
    assert configuration.source.acquired_at == STARTED_AT
    assert not list(tmp_path.glob(f"**/{LOCK_FILE}"))


def test_a_snapshot_without_a_command_sends_nothing_with_a_client_that_isnt_the_demos(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    content, plan = snapshot_plan()

    with LocalArtifactStore(tmp_path / "snapshot") as store:
        execution = SnapshotExecution(
            plan, plan.plan_hash, "not_required", store, None, clock=FixedClock()
        )
        with pytest.raises(ValueError, match="demo"):
            execution.run(
                content, lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint)
            )

    assert server.received == ()
    assert not (tmp_path / "snapshot" / "manifest.json").exists()
    # Its attempt has no start record, so the snapshot's records say the rank_get wasn't sent.
    assert execution.ending_detail().startswith("The rank_get request wasn't sent.")


def test_a_snapshot_needs_its_plans_approval_and_its_configuration(tmp_path: Path) -> None:
    content, plan = snapshot_plan()
    other, _ = snapshot_plan("canaries.yaml")

    with LocalArtifactStore(tmp_path / "snapshot") as store:
        with pytest.raises(TrialFolioError) as raised:
            SnapshotExecution(plan, "sha256:" + "0" * 64, "option", store, SNAPSHOT_COMMAND)
        assert raised.value.code == "plan.approval_required"
        with pytest.raises(ValueError, match="synthetic"):
            SnapshotExecution(plan, plan.plan_hash, "option", store, None)
        execution = SnapshotExecution(plan, plan.plan_hash, "option", store, SNAPSHOT_COMMAND)
        with pytest.raises(ValueError, match="configuration"):
            execution.run(other, lambda: SyntheticScreenBacktestClient(response_bytes()))
    assert not (tmp_path / "snapshot").exists()
    del content
