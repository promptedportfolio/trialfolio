"""A ranking snapshot, in the core: its run, which reads the system its configuration names with
one `rank_get`, and writes its plan, its attempt's records 1.2.0, `definition.xml`,
`snapshot.json`, and its manifest; a synthetic snapshot the core takes with the demo's client;
and reading a snapshot as a configuration's ranking, offline, in step 2, which plans from it, and
copies its two files beside each plan's `configuration.yaml`.

Traces to docs/contracts.md, ranking snapshot output (its steps, plan, layout, records, manifest,
response, `definition.xml`, `snapshot.json`, reading a snapshot, and the executors), ranking
definitions (a
case's definition and its identity, its source), plans with a ranking definition
(`ranking_source`), a run with a ranking definition (the copies and their roles), the experiment
manifest's version 1.1.0, a complete run, checking the records, and CLI behavior (the demo's
client); and to R04-AC08 at the core: the snapshot's files and records, its failures, the
synthetic snapshot, which takes no lock, and a configuration that names a snapshot, whose plan
is built offline, records the snapshot as its source, and gives each case the `case_id` the
definition's file gives it, or that's refused when the snapshot is missing, incomplete, can't be
a ranking, or is synthetic. The real client, `requests`, and `urllib3` run over the fake server,
whose end-of-test check reads every request's path; the clock is fixed; and a run with a
definition takes the ranking lock on a file in the test's temporary directory.
"""

import json
import shutil
from pathlib import Path
from typing import cast

import pytest

from tests.support.clock import FixedClock, no_wait
from tests.support.experiment_lab import Lab
from tests.support.fake_portfolio123 import (
    AUTH,
    AUTHENTICATED,
    BACKTEST,
    CREDENTIALS,
    RANK,
    RANK_GET,
    FakePortfolio123,
    Reply,
    exchange,
    response,
)
from tests.support.paths import (
    EXPERIMENT_CONFIGS,
    RANKING_DEFINITIONS,
    RESPONSES,
    SNAPSHOT_CONFIGS,
    screen_config,
)
from tests.support.plans import ranked_screen
from tests.support.snapshot_builder import naming
from tests.support.storage_faults import StorageFaults
from trialfolio.canonical import sha256_hex
from trialfolio.configuration import (
    read_experiment_configuration_v1_1,
    read_ranking_snapshot_configuration,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.attempt import AttemptRecordV1_2, StartRecordV1_2
from trialfolio.contracts.experiment_manifest import ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.contracts.manifest import CommandRecord, RunManifestV1_1
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.contracts.ranking_snapshot import (
    RankingSnapshotManifest,
    RankingSnapshotPlan,
    RankingSnapshotRecord,
    SnapshotCommandRecord,
)
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.experiment_records import open_experiment
from trialfolio.planning import (
    build_experiment_plan_v1_1,
    build_plan_v1_1,
    build_snapshot_plan,
    installed_versions,
)
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.runs import read_run
from trialfolio.snapshot_execution import SnapshotExecution
from trialfolio.snapshots import SnapshotFiles
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_settings_csv_v1_1

SCREEN = screen_config("definition.yaml")
EXAMPLE = EXPERIMENT_CONFIGS / "ranking-example.yaml"
DEFINITION = RANKING_DEFINITIONS / "value-momentum.xml"

STARTED_AT = FixedClock()()
SNAPSHOT_COMMAND = SnapshotCommandRecord(
    name="run", options={"approve": None, "json": False}, started_at=STARTED_AT
)
RUN_COMMAND = CommandRecord(name="run", options={}, started_at=STARTED_AT)


def snapshot_plan(name: str = "example.yaml") -> tuple[bytes, RankingSnapshotPlan]:
    path = SNAPSHOT_CONFIGS / name
    content = path.read_bytes()
    read = read_ranking_snapshot_configuration(content, path.name)
    return content, build_snapshot_plan(read, installed_versions())


def artifact_id(content: bytes) -> str:
    return "sha256:" + sha256_hex(content)


def take(
    server: FakePortfolio123,
    out: Path,
    reply: Reply | None = None,
    *,
    timeout: int | None = None,
    faults: tuple[pytest.MonkeyPatch, str, BaseException] | None = None,
) -> tuple[SnapshotExecution, TrialFolioError | None]:
    """Takes `example.yaml`'s snapshot into `out`, through the core, over the fake server, which
    answers its `GET /rank` with `reply`, `rank-get.json`'s 200 by default. `faults` makes the
    write of a named file raise an error, before it starts."""
    content, plan = snapshot_plan()
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-get.json") if reply is None else reply, method="GET")
    options = {} if timeout is None else {"timeout": timeout}
    with LocalArtifactStore(out) as real:
        store: LocalArtifactStore | StorageFaults = real
        if faults is not None:
            monkeypatch, name, error = faults
            store = StorageFaults(real, monkeypatch)
            store.fail_before(name, error)
        execution = SnapshotExecution(
            plan, plan.plan_hash, "option", store, SNAPSHOT_COMMAND, clock=FixedClock()
        )
        error = execution.run(
            content,
            lambda: P123ScreenBacktestClient(
                CREDENTIALS, endpoint=server.endpoint, snapshot=True, **options
            ),
        )
    return execution, error


def read_json(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_bytes())
    assert isinstance(loaded, dict)
    return loaded  # pyright: ignore[reportUnknownVariableType]


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


def system_reply(**changes: object) -> Reply:
    """A 200 whose body is `rank-get.json`'s, with `changes` to its fields."""
    payload = read_json(RESPONSES / "rank-get.json")
    return Reply(200, json.dumps({**payload, **changes}).encode())


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


# Reading a snapshot as a configuration's ranking


@pytest.fixture
def snapshot(tmp_path: Path, server: FakePortfolio123) -> Path:
    """`example.yaml`'s snapshot of `rank-get.json`'s system, whose definition is
    `value-momentum.xml`'s."""
    out = tmp_path / "ranking" / "value-momentum"
    _, error = take(server, out)
    assert error is None
    return out


def test_a_configuration_naming_a_snapshot_is_planned_from_it_offline(
    tmp_path: Path, snapshot: Path
) -> None:
    """The plan records the snapshot as the definition's source, by its system's name and its
    files' `artifact_id`s, and each case's `case_id` is the one the definition's file gives it:
    a case covers the definition and its ranking method, not where they came from. Building the
    plan reads nothing from the account: the network guard refuses every connection here."""
    versions = installed_versions()
    screen = naming(SCREEN, snapshot, tmp_path / "screen-configs")
    experiment = naming(EXAMPLE, snapshot, tmp_path / "experiment-configs")

    screen_read = read_screen_configuration_v1_1(screen.read_bytes(), screen.name, screen)
    experiment_read = read_experiment_configuration_v1_1(
        experiment.read_bytes(), experiment.name, experiment
    )
    screen_plan = build_plan_v1_1(screen_read, versions)
    experiment_plan = build_experiment_plan_v1_1(experiment_read, versions)

    from_files = (
        build_plan_v1_1(
            read_screen_configuration_v1_1(SCREEN.read_bytes(), SCREEN.name, SCREEN), versions
        ),
        build_experiment_plan_v1_1(
            read_experiment_configuration_v1_1(EXAMPLE.read_bytes(), EXAMPLE.name, EXAMPLE),
            versions,
        ),
    )
    assert isinstance(screen_plan, PlanV1_2) and isinstance(experiment_plan, PlanV1_3)
    assert isinstance(from_files[0], PlanV1_2) and isinstance(from_files[1], PlanV1_3)
    for plan, from_file in ((screen_plan, from_files[0]), (experiment_plan, from_files[1])):
        assert plan.ranking_source.model_dump() == {
            "form": "snapshot",
            "definition": from_file.ranking_source.definition,
            "system": "Value and momentum",
            "snapshot_record": artifact_id((snapshot / "snapshot.json").read_bytes()),
            "snapshot_definition": artifact_id((snapshot / "definition.xml").read_bytes()),
        }
        assert [c.case_id for c in plan.cases] == [c.case_id for c in from_file.cases]
        assert plan.plan_hash != from_file.plan_hash
    # The snapshot's ranking method is its system's: rank-get.json's 2.
    ranking = next(row for row in screen_plan.cases[0].settings if row.setting == "ranking")
    assert ranking.model_dump(mode="json")["value"]["ranking_method"] == "percentile_nas_negative"


def test_a_snapshot_directory_that_doesnt_exist_is_input_not_found(tmp_path: Path) -> None:
    path = naming(SCREEN, tmp_path / "nowhere", tmp_path / "screen-configs")

    with pytest.raises(TrialFolioError) as raised:
        read_screen_configuration_v1_1(path.read_bytes(), path.name, path)

    assert raised.value.code == "input.not_found"
    assert "`ranking.snapshot`" in raised.value.message
    # The logged message leaves out the path as the configuration gives it.
    assert "nowhere" in raised.value.message
    assert "nowhere" not in raised.value.log_message


def _break_listed(snapshot: Path, name: str) -> None:
    (snapshot / name).write_bytes((snapshot / name).read_bytes() + b"\n")


def _change_in_place(snapshot: Path, name: str) -> None:
    """Changes one weight's digit in the snapshot's file `name`, keeping its size, so only its
    `artifact_id` shows the change."""
    content = (snapshot / name).read_bytes()
    changed = content.replace(b'Weight="40"', b'Weight="41"', 1)
    assert changed != content and len(changed) == len(content)
    (snapshot / name).write_bytes(changed)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda s: (s / "snapshot.json").unlink(), "`snapshot.json`, which is missing."),
        (
            lambda s: _break_listed(s, "definition.xml"),
            "`definition.xml` doesn't match its artifact_id",
        ),
        (
            lambda s: _change_in_place(s, "definition.xml"),
            "`definition.xml` doesn't match its artifact_id",
        ),
        (lambda s: (s / "manifest.json").unlink(), "it has no manifest.json."),
    ],
    ids=["record-missing", "definition-changed", "definition-changed-same-size", "no-manifest"],
)
def test_a_snapshot_that_isnt_complete_is_input_not_a_run(
    tmp_path: Path, snapshot: Path, change: object, problem: str
) -> None:
    change(snapshot)  # pyright: ignore[reportCallIssue]
    path = naming(SCREEN, snapshot, tmp_path / "screen-configs")

    with pytest.raises(TrialFolioError) as raised:
        read_screen_configuration_v1_1(path.read_bytes(), path.name, path)

    assert raised.value.code == "input.not_a_run"
    assert "isn't a complete ranking snapshot" in raised.value.message
    assert problem in raised.value.message


def test_a_failed_snapshot_is_input_not_a_run(tmp_path: Path, server: FakePortfolio123) -> None:
    out = tmp_path / "failed"
    take(server, out, Reply(404, b""))
    path = naming(SCREEN, out, tmp_path / "screen-configs")

    with pytest.raises(TrialFolioError) as raised:
        read_screen_configuration_v1_1(path.read_bytes(), path.name, path)

    assert raised.value.code == "input.not_a_run"
    assert "its manifest's outcome is failed" in raised.value.message


def _rewrite_listed(snapshot: Path, name: str, content: bytes) -> None:
    """Writes `content` as the snapshot's file `name`, and its manifest's entry for it, so only
    a rule its manifest's hashes can't catch refuses it."""
    (snapshot / name).write_bytes(content)
    manifest = read_json(snapshot / "manifest.json")
    for entry in cast("list[dict[str, object]]", manifest["artifacts"]):
        if entry["path"] == name:
            entry["artifact_id"], entry["size"] = artifact_id(content), len(content)
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")


def test_a_snapshot_record_that_doesnt_name_its_definition_is_input_not_a_run(
    tmp_path: Path, snapshot: Path
) -> None:
    record = read_json(snapshot / "snapshot.json")
    record["definition"] = "sha256:" + "0" * 64
    _rewrite_listed(snapshot, "snapshot.json", json.dumps(record).encode())
    path = naming(SCREEN, snapshot, tmp_path / "screen-configs")

    with pytest.raises(TrialFolioError) as raised:
        read_screen_configuration_v1_1(path.read_bytes(), path.name, path)

    assert raised.value.code == "input.not_a_run"
    assert "doesn't name its definition.xml by that file's artifact_id" in raised.value.message


def test_a_snapshot_record_of_a_version_with_no_reader_is_unknown(
    tmp_path: Path, snapshot: Path
) -> None:
    record = read_json(snapshot / "snapshot.json")
    record["schema_version"] = "9.9.9"
    _rewrite_listed(snapshot, "snapshot.json", json.dumps(record).encode())
    path = naming(SCREEN, snapshot, tmp_path / "screen-configs")

    with pytest.raises(TrialFolioError) as raised:
        read_screen_configuration_v1_1(path.read_bytes(), path.name, path)

    assert raised.value.code == "artifact.unknown_schema_version"
    assert "`snapshot.json`" in raised.value.message


def test_a_snapshot_manifest_of_a_version_with_no_reader_is_unknown(
    tmp_path: Path, snapshot: Path
) -> None:
    manifest = read_json(snapshot / "manifest.json")
    manifest["schema_version"] = "9.9.9"
    (snapshot / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    path = naming(SCREEN, snapshot, tmp_path / "screen-configs")

    with pytest.raises(TrialFolioError) as raised:
        read_screen_configuration_v1_1(path.read_bytes(), path.name, path)

    assert raised.value.code == "artifact.unknown_schema_version"
    assert "9.9.9" not in raised.value.message


@pytest.mark.parametrize(
    ("name", "rule"),
    [
        ("rank-get-currency-cad.json", "whose system's currency isn't USD"),
        ("rank-get-type-etf.json", "whose system's type isn't Stock"),
        ("rank-get-method-1.json", "whose ranking method isn't one a ranking takes"),
        ("rank-get-not-a-definition.json", "whose definition Trial Folio can't read, at line 18"),
    ],
    ids=["currency", "etf", "method-1", "not-a-definition"],
)
@pytest.mark.parametrize("kind", ["screen", "experiment"])
def test_a_snapshot_that_cant_be_a_ranking_is_config_invalid(
    tmp_path: Path, server: FakePortfolio123, name: str, rule: str, kind: str
) -> None:
    out = tmp_path / "ranking" / "snapshot"
    _, error = take(server, out, response(name))
    assert error is None
    configuration, key = (
        (SCREEN, "ranking.snapshot") if kind == "screen" else (EXAMPLE, "baseline.ranking.snapshot")
    )
    path = naming(configuration, out, tmp_path / "configs")
    reader = (
        read_screen_configuration_v1_1 if kind == "screen" else read_experiment_configuration_v1_1
    )

    with pytest.raises(TrialFolioError) as raised:
        reader(path.read_bytes(), path.name, path)

    assert raised.value.code == "config.invalid"
    assert f"`{key}` names a snapshot {rule}" in raised.value.message
    # Nothing of the system, or its definition, is in the message.
    for value in ("Value and momentum", "104729", "CAD", "ETF", "Composite"):
        assert value not in raised.value.message


@pytest.mark.parametrize("kind", ["screen", "experiment"])
def test_a_synthetic_snapshot_is_config_invalid(tmp_path: Path, kind: str) -> None:
    """The demo's client invented its system, so a run that sent its definition would send an
    invented system's definition as one Portfolio123 returned (reading a snapshot, D-41)."""
    content, plan = snapshot_plan()
    out = tmp_path / "ranking" / "synthetic"
    system = (RESPONSES / "rank-get.json").read_bytes()
    with LocalArtifactStore(out) as store:
        SnapshotExecution(plan, plan.plan_hash, "not_required", store, None).run(
            content, lambda: SyntheticScreenBacktestClient(response_bytes(), system=system)
        )
    configuration, key = (
        (SCREEN, "ranking.snapshot") if kind == "screen" else (EXAMPLE, "baseline.ranking.snapshot")
    )
    path = naming(configuration, out, tmp_path / "configs")
    reader = (
        read_screen_configuration_v1_1 if kind == "screen" else read_experiment_configuration_v1_1
    )

    with pytest.raises(TrialFolioError) as raised:
        reader(path.read_bytes(), path.name, path)

    assert raised.value.code == "config.invalid"
    assert f"`{key}` names a snapshot that's synthetic" in raised.value.message


# The copies beside each plan's configuration.yaml


def snapshot_screen(tmp_path: Path, snapshot: Path) -> tuple[bytes, SnapshotFiles, PlanV1_2]:
    """`definition.yaml`, named by the snapshot in `snapshot`: its bytes, the snapshot's files,
    and its plan."""
    planned = ranked_screen(naming(SCREEN, snapshot, tmp_path / "screen-configs"))
    assert planned.snapshot is not None
    return planned.content, planned.snapshot, planned.plan


def test_a_run_copies_the_snapshots_two_files_beside_its_configuration(
    tmp_path: Path, server: FakePortfolio123, snapshot: Path
) -> None:
    """From the bytes read and checked when the configuration was validated, so the copies are
    the files the approved plan was built from, even when the snapshot's files change before the
    run writes them."""
    content, files, plan = snapshot_screen(tmp_path, snapshot)
    _break_listed(snapshot, "definition.xml")
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
    out = tmp_path / "run"

    with LocalArtifactStore(out) as store:
        error = Execution(
            plan,
            plan.plan_hash,
            "option",
            store,
            RUN_COMMAND,
            clock=FixedClock(),
            ranking_lock=tmp_path / LOCK_FILE,
            pause=no_wait(),
        ).run(
            content,
            lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint),
            snapshot=files,
        )

    assert error is None
    assert (out / "definition.xml").read_bytes() == files.definition
    assert (out / "snapshot.json").read_bytes() == files.record
    assert [r.request for r in server.received[-3:]] == [AUTH, RANK, BACKTEST]
    manifest = RunManifestV1_1.model_validate_json((out / "manifest.json").read_bytes())
    paths = [a.path for a in manifest.artifacts]
    assert paths[:4] == ["plan.json", "configuration.yaml", "definition.xml", "snapshot.json"]
    copy = next(a for a in manifest.artifacts if a.role == "ranking_definition")
    record = next(a for a in manifest.artifacts if a.role == "ranking_snapshot_record")
    snapshot_record = RankingSnapshotRecord.model_validate_json(files.record)
    assert copy.source is not None
    assert (copy.source.provenance, copy.source.operation, copy.source.acquired_at) == (
        "verified",
        "rank_get",
        snapshot_record.taken_at,
    )
    assert (record.schema_version, record.source) == ("1.0.0", None)
    # Each weight row's original is the snapshot's, named by `ranking.snapshot`.
    rows = read_settings_csv_v1_1(
        (out / "normalized" / "settings.csv").read_bytes(), "settings.csv"
    )
    weights = [row for row in rows if row.node is not None]
    assert {row.original_key for row in weights} == {"ranking.snapshot"}
    assert {row.source_artifact for row in weights} == {copy.artifact_id}
    # `trialfolio report` reads the run as complete.
    with LocalArtifactStore(out) as store:
        saved = read_run(store)
    assert saved.plan == plan


def test_a_run_is_given_its_snapshots_files_as_its_plan_has_them(
    tmp_path: Path, snapshot: Path
) -> None:
    content, files, plan = snapshot_screen(tmp_path, snapshot)
    other = SnapshotFiles(definition=files.definition, record=files.record + b"\n")

    with LocalArtifactStore(tmp_path / "run") as store:
        for given in (
            {"definition": files.definition},
            {"snapshot": other},
            {"definition": files.definition, "snapshot": files},
        ):
            execution = Execution(
                plan,
                plan.plan_hash,
                "option",
                store,
                RUN_COMMAND,
                ranking_lock=tmp_path / LOCK_FILE,
                pause=no_wait(),
            )
            with pytest.raises(ValueError):
                execution.run(
                    content,
                    lambda: SyntheticScreenBacktestClient(response_bytes()),
                    **given,  # pyright: ignore[reportArgumentType]
                )
    assert not (tmp_path / "run").exists()


def test_a_snapshots_files_given_whose_record_names_another_definition_are_refused(
    tmp_path: Path, snapshot: Path
) -> None:
    """Given a snapshot's two files' bytes in place of its directory, the configuration's reader
    checks that `snapshot.json` names `definition.xml`, though another definition that can be a
    ranking is given in its place (the executors)."""
    content, files, _ = snapshot_screen(tmp_path, snapshot)
    other = (DEFINITION.parent / "value-momentum-revised.xml").read_bytes()
    assert other != files.definition
    path = tmp_path / "screen-configs" / SCREEN.name

    with pytest.raises(ValueError, match="names another definition.xml"):
        read_screen_configuration_v1_1(
            content,
            path.name,
            path,
            snapshot=SnapshotFiles(definition=other, record=files.record),
        )


def test_a_runs_snapshot_that_isnt_its_plans_is_refused_as_not_a_run(
    tmp_path: Path, server: FakePortfolio123, snapshot: Path
) -> None:
    """A copy of another snapshot's record, listed with its own `artifact_id`, isn't the
    snapshot the plan's `ranking_source` names (a complete run)."""
    content, files, plan = snapshot_screen(tmp_path, snapshot)
    out = tmp_path / "run"
    with LocalArtifactStore(out) as store:
        Execution(
            plan, plan.plan_hash, "not_required", store, None, ranking_lock=tmp_path / LOCK_FILE
        ).run(content, lambda: SyntheticScreenBacktestClient(response_bytes()), snapshot=files)
    record = read_json(out / "snapshot.json")
    record["requested"] = "Another system"
    changed = (json.dumps(record, indent=2) + "\n").encode()
    (out / "snapshot.json").write_bytes(changed)
    manifest = read_json(out / "manifest.json")
    for entry in manifest["artifacts"]:  # pyright: ignore[reportGeneralTypeIssues]
        if entry["path"] == "snapshot.json":  # pyright: ignore[reportIndexIssue]
            entry["artifact_id"] = artifact_id(changed)  # pyright: ignore[reportIndexIssue]
            entry["size"] = len(changed)  # pyright: ignore[reportIndexIssue]
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with LocalArtifactStore(out) as store, pytest.raises(TrialFolioError) as raised:
        read_run(store)

    assert raised.value.code == "input.not_a_run"
    assert "aren't the snapshot its plan's ranking_source names" in raised.value.message
    del server


def test_an_experiment_copies_the_snapshot_into_its_plan_and_resumes_with_it(
    tmp_path: Path, snapshot: Path
) -> None:
    """A new experiment's `plans/1/` holds the snapshot's `definition.xml` and `snapshot.json`
    after its `configuration.yaml`; experiment manifest 1.1.0 lists both; and a resume reads and
    checks them, and reads the configuration again with them."""
    path = naming(EXAMPLE, snapshot, tmp_path / "experiment-configs")
    content = path.read_bytes()
    read = read_experiment_configuration_v1_1(content, path.name, path)
    plan = build_experiment_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_3) and read.snapshot is not None
    files = read.snapshot.files
    lab = Lab(tmp_path)
    out = lab.out

    ran = lab.new(path, synthetic=True)

    assert ran.error is None and ran.plan == plan
    assert (out / "plans" / "1" / "definition.xml").read_bytes() == files.definition
    assert (out / "plans" / "1" / "snapshot.json").read_bytes() == files.record
    manifest = ExperimentManifestV1_1.model_validate_json(
        (out / "sessions" / "1" / "manifest.json").read_bytes()
    )
    roles = [(a.path, a.role) for a in manifest.artifacts if a.path.startswith("plans/1/")]
    assert roles[:3] == [
        ("plans/1/configuration.yaml", "configuration"),
        ("plans/1/definition.xml", "ranking_definition"),
        ("plans/1/snapshot.json", "ranking_snapshot_record"),
    ]
    copy = next(a for a in manifest.artifacts if a.role == "ranking_definition")
    record = next(a for a in manifest.artifacts if a.role == "ranking_snapshot_record")
    assert copy.source is not None
    assert (copy.source.provenance, copy.source.operation, copy.source.acquired_at) == (
        "verified",
        "rank_get",
        read.snapshot.record.taken_at,
    )
    assert (record.schema_version, record.source) == ("1.0.0", None)
    # Each of the baseline's weight rows takes its original from the snapshot's copy, named by
    # `baseline.ranking.snapshot`.
    baseline = plan.cases[0]
    assert baseline.case_key == "baseline"
    settings = out / "cases" / baseline.case_id / "normalized" / "settings.csv"
    rows = read_settings_csv_v1_1(settings.read_bytes(), settings.name)
    weights = [row for row in rows if row.node is not None]
    assert weights
    assert {row.original_key for row in weights} == {"baseline.ranking.snapshot"}
    assert {row.source_artifact for row in weights} == {copy.artifact_id}
    with LocalArtifactStore(out) as store:
        saved = open_experiment(store, ranking=True)
    assert saved.current.snapshot is not None
    assert saved.current.read is not None and saved.current.read.snapshot is not None
    resumed = lab.resume(path, synthetic=True)
    assert resumed.error is None and resumed.plan == plan
    assert (out / "sessions" / "2" / "manifest.json").is_file()


def test_an_experiments_plan_whose_snapshot_record_is_missing_is_refused(
    tmp_path: Path, snapshot: Path
) -> None:
    path = naming(EXAMPLE, snapshot, tmp_path / "experiment-configs")
    # An incomplete copy: the plan's snapshot.json, and every manifest, which would catch it first.
    out = new_experiment(tmp_path, path)
    (out / "plans" / "1" / "snapshot.json").unlink()

    with LocalArtifactStore(out) as store, pytest.raises(TrialFolioError) as raised:
        open_experiment(store, ranking=True)

    assert raised.value.code == "input.not_a_run"
    assert "snapshot.json` is missing, though its plan's ranking is a snapshot" in (
        raised.value.message
    )


def test_an_unexpected_failure_at_a_runs_snapshot_json_leaves_no_manifest(
    tmp_path: Path, snapshot: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every manifest of a run whose ranking a snapshot names lists its `snapshot.json`, so a
    run that couldn't write it ends without one, as after a failure at `definition.xml`."""
    content, files, plan = snapshot_screen(tmp_path, snapshot)
    out = tmp_path / "run"
    with LocalArtifactStore(out) as real:
        store = StorageFaults(real, monkeypatch)
        store.fail_before("snapshot.json", RuntimeError("unexpected"))
        error = Execution(
            plan, plan.plan_hash, "not_required", store, None, ranking_lock=tmp_path / LOCK_FILE
        ).run(content, lambda: SyntheticScreenBacktestClient(response_bytes()), snapshot=files)

    assert error is not None and error.code == "internal.unexpected"
    assert (out / "definition.xml").is_file()
    assert not (out / "snapshot.json").exists()
    assert not (out / "manifest.json").exists()


def synthetic_run(
    tmp_path: Path, content: bytes, plan: PlanV1_2, **given: bytes | SnapshotFiles
) -> Path:
    """The run of `plan`, written through the core with the demo's client."""
    out = tmp_path / "run"
    with LocalArtifactStore(out) as store:
        error = Execution(
            plan, plan.plan_hash, "not_required", store, None, ranking_lock=tmp_path / LOCK_FILE
        ).run(
            content,
            lambda: SyntheticScreenBacktestClient(response_bytes()),
            **given,  # pyright: ignore[reportArgumentType]
        )
    assert error is None
    return out


def test_a_runs_snapshot_record_of_a_version_with_no_reader_is_unknown(
    tmp_path: Path, snapshot: Path
) -> None:
    content, files, plan = snapshot_screen(tmp_path, snapshot)
    out = synthetic_run(tmp_path, content, plan, snapshot=files)
    manifest = read_json(out / "manifest.json")
    for entry in cast("list[dict[str, object]]", manifest["artifacts"]):
        if entry["path"] == "snapshot.json":
            entry["schema_version"] = "9.9.9"
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")

    with LocalArtifactStore(out) as store, pytest.raises(TrialFolioError) as raised:
        read_run(store)

    assert raised.value.code == "artifact.unknown_schema_version"


def test_a_run_whose_ranking_is_a_file_lists_no_snapshot_record(
    tmp_path: Path, snapshot: Path
) -> None:
    content = SCREEN.read_bytes()
    read = read_screen_configuration_v1_1(content, SCREEN.name, SCREEN)
    plan = build_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_2) and read.definition is not None
    out = synthetic_run(tmp_path, content, plan, definition=read.definition.content)
    record = (snapshot / "snapshot.json").read_bytes()
    (out / "snapshot.json").write_bytes(record)
    manifest = read_json(out / "manifest.json")
    artifacts = cast("list[dict[str, object]]", manifest["artifacts"])
    artifacts.insert(
        3,
        {
            "path": "snapshot.json",
            "artifact_id": artifact_id(record),
            "size": len(record),
            "role": "ranking_snapshot_record",
            "schema_version": "1.0.0",
            "source": None,
        },
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")

    with LocalArtifactStore(out) as store, pytest.raises(TrialFolioError) as raised:
        read_run(store)

    assert raised.value.code == "input.not_a_run"
    assert "lists a snapshot.json, though its plan's ranking is a definition's file" in (
        raised.value.message
    )


def new_experiment(tmp_path: Path, path: Path) -> Path:
    """A new experiment of the configuration at `path`, written through the core with the demo's
    client, every case succeeded; with no session's manifest, so its records are checked
    without one, as after an incomplete copy that lost them."""
    lab = Lab(tmp_path)
    assert lab.new(path, synthetic=True).error is None
    shutil.rmtree(lab.out / "sessions" / "1")
    (lab.out / "sessions" / "1").mkdir()
    return lab.out


def test_an_experiments_plan_whose_ranking_is_a_file_holds_no_snapshot_record(
    tmp_path: Path, snapshot: Path
) -> None:
    out = new_experiment(tmp_path, EXAMPLE)
    shutil.copyfile(snapshot / "snapshot.json", out / "plans" / "1" / "snapshot.json")

    with LocalArtifactStore(out) as store, pytest.raises(TrialFolioError) as raised:
        open_experiment(store, ranking=True)

    assert raised.value.code == "input.not_a_run"
    assert "is there, though its plan's ranking is a definition's file" in raised.value.message


def test_an_experiments_snapshot_record_of_a_version_with_no_reader_is_unknown(
    tmp_path: Path, snapshot: Path
) -> None:
    out = new_experiment(tmp_path, naming(EXAMPLE, snapshot, tmp_path / "experiment-configs"))
    path = out / "plans" / "1" / "snapshot.json"
    record = read_json(path)
    record["schema_version"] = "9.9.9"
    path.write_text(json.dumps(record), encoding="utf-8")

    with LocalArtifactStore(out) as store, pytest.raises(TrialFolioError) as raised:
        open_experiment(store, ranking=True)

    assert raised.value.code == "artifact.unknown_schema_version"


def test_an_experiments_plan_whose_snapshot_isnt_its_plans_is_refused_as_not_a_run(
    tmp_path: Path, snapshot: Path
) -> None:
    """A valid snapshot record in `plans/1/` that, with the plan's `definition.xml`, isn't the
    snapshot the plan's `ranking_source` names (checking the records), as for a run's."""
    out = new_experiment(tmp_path, naming(EXAMPLE, snapshot, tmp_path / "experiment-configs"))
    path = out / "plans" / "1" / "snapshot.json"
    record = read_json(path)
    record["requested"] = "Another system"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    with LocalArtifactStore(out) as store, pytest.raises(TrialFolioError) as raised:
        open_experiment(store, ranking=True)

    assert raised.value.code == "input.not_a_run"
    assert "aren't the snapshot its plan's ranking_source names" in raised.value.message


def test_a_plan_records_the_system_by_the_name_its_snapshot_gives(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    """A `name` other than the one requested is recorded as it is, and the plan's
    `ranking_source` gives the record's `system.name`, not the name requested."""
    out = tmp_path / "ranking" / "renamed"
    _, error = take(server, out, system_reply(name="Value and momentum, renamed"))
    assert error is None
    path = naming(SCREEN, out, tmp_path / "screen-configs")

    read = read_screen_configuration_v1_1(path.read_bytes(), path.name, path)
    plan = build_plan_v1_1(read, installed_versions())

    assert isinstance(plan, PlanV1_2)
    assert read.snapshot is not None and read.snapshot.record.requested == "Value and momentum"
    assert plan.ranking_source.system == "Value and momentum, renamed"


def test_a_snapshot_record_its_manifest_gives_a_version_with_no_reader_is_unknown(
    tmp_path: Path, snapshot: Path
) -> None:
    manifest = read_json(snapshot / "manifest.json")
    for entry in cast("list[dict[str, object]]", manifest["artifacts"]):
        if entry["path"] == "snapshot.json":
            entry["schema_version"] = "9.9.9"
    (snapshot / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    path = naming(SCREEN, snapshot, tmp_path / "screen-configs")

    with pytest.raises(TrialFolioError) as raised:
        read_screen_configuration_v1_1(path.read_bytes(), path.name, path)

    assert raised.value.code == "artifact.unknown_schema_version"
    assert "its manifest gives it a schema version this version has no reader for" in (
        raised.value.message
    )
