"""Boundaries for the core tests: what the store syncs, failures injected into its file
operations (AGENTS.md, verification expectations: injected storage failures), an attempt run
over the fake Portfolio123 server, below `urllib3`, whose saved response the normalization tests
read, a complete run, with its report and manifest, for the report tests, and a run executed
as `trialfolio run` executes it, through `Execution`."""

import itertools
import json
import os
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.attempts import Attempt, provider_requests
from trialfolio.configuration import original_values, read_screen_configuration
from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.common import ErrorDetail
from trialfolio.contracts.manifest import (
    ArtifactRole,
    AttemptCounts,
    Capabilities,
    CommandRecord,
    ExternalReference,
    ManifestArtifact,
    ManifestCounts,
    ParserVersion,
    Reproducibility,
    RunManifest,
    SourceRecord,
)
from trialfolio.contracts.plan import Plan
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.normalization import (
    LAYOUT,
    LAYOUT_VERSION,
    PARSER_VERSION,
    NormalizedTables,
    write_tables,
)
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.planning import VERIFIED_VERSIONS, Versions, build_plan
from trialfolio.provider import Credentials, P123ScreenBacktestClient
from trialfolio.report import HtmlReportRenderer, write_report
from trialfolio.runs import SavedAttempt, SavedRun
from trialfolio.storage import LocalArtifactStore, StoredFile

type Identity = tuple[int, int]


def identity(path: Path) -> Identity:
    """The device and inode of a file or directory, which outlast any one descriptor."""
    status = os.stat(path)
    return (status.st_dev, status.st_ino)


class SyncLog:
    """Each file and directory the store synced, by identity, in order."""

    def __init__(self) -> None:
        self.synced: list[Identity] = []

    def take(self) -> set[Identity]:
        """What was synced since the last call."""
        synced = set(self.synced)
        self.synced.clear()
        return synced


@pytest.fixture
def sync_log(monkeypatch: pytest.MonkeyPatch) -> SyncLog:
    """Records every sync, whether `os.fsync` or, on macOS, `fcntl.F_FULLFSYNC`."""
    log = SyncLog()

    def record(descriptor: int) -> None:
        status = os.fstat(descriptor)
        log.synced.append((status.st_dev, status.st_ino))

    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        record(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    if sys.platform == "darwin":
        import fcntl

        real_fcntl = fcntl.fcntl

        def full_sync(descriptor: int, command: int, argument: int = 0) -> int:
            if command == fcntl.F_FULLFSYNC:
                record(descriptor)
            return real_fcntl(descriptor, command, argument)

        monkeypatch.setattr(fcntl, "fcntl", full_sync)
    return log


type Effect = Callable[[], object]


class Faults:
    """Injects a failure, or another process's action, into the store's file operations on one
    file or directory: the one whose name contains `name`, which includes a file's temporary
    file."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._before_open: dict[str, Effect] = {}
        self._after_open: dict[str, Effect] = {}
        self._before_write: dict[str, Effect] = {}
        self._after_close: dict[str, Effect] = {}
        self._after_mkdir: dict[str, Effect] = {}
        self._before_sync: dict[str, Effect] = {}
        self._writing: dict[int, Effect] = {}
        self._syncing: dict[int, Effect] = {}
        self._closing: dict[int, Effect] = {}
        real_open, real_write, real_close, real_mkdir = os.open, os.write, os.close, os.mkdir

        def matching(effects: dict[str, Effect], path: str | os.PathLike[str]) -> list[Effect]:
            name = Path(path).name
            return [effect for target, effect in effects.items() if target in name]

        def open_(
            path: str | os.PathLike[str],
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            for effect in matching(self._before_open, path):
                effect()
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            for effect in matching(self._before_write, path):
                self._writing[descriptor] = effect
            for effect in matching(self._before_sync, path):
                self._syncing[descriptor] = effect
            for effect in matching(self._after_close, path):
                self._closing[descriptor] = effect
            try:
                for effect in matching(self._after_open, path):
                    effect()  # As if an interrupt arrived as the call returned.
            except BaseException:
                close(descriptor)  # The store never got it; the file stays.
                raise
            return descriptor

        def write(descriptor: int, data: bytes | memoryview) -> int:
            effect = self._writing.get(descriptor)
            if effect is not None:
                effect()
            return real_write(descriptor, data)

        def sync(descriptor: int) -> None:
            effect = self._syncing.get(descriptor)
            if effect is not None:
                effect()

        real_fsync = os.fsync

        def fsync(descriptor: int) -> None:
            sync(descriptor)
            real_fsync(descriptor)

        def close(descriptor: int) -> None:
            self._writing.pop(descriptor, None)
            self._syncing.pop(descriptor, None)
            effect = self._closing.pop(descriptor, None)
            real_close(descriptor)
            if effect is not None:
                effect()

        def mkdir(path: str | os.PathLike[str], mode: int = 0o777) -> None:
            real_mkdir(path, mode)
            for effect in matching(self._after_mkdir, path):
                effect()

        monkeypatch.setattr(os, "open", open_)
        monkeypatch.setattr(os, "write", write)
        monkeypatch.setattr(os, "close", close)
        monkeypatch.setattr(os, "mkdir", mkdir)
        monkeypatch.setattr(os, "fsync", fsync)
        if sys.platform == "darwin":
            import fcntl

            real_fcntl = fcntl.fcntl

            def full_sync(descriptor: int, command: int, argument: int = 0) -> int:
                if command == fcntl.F_FULLFSYNC:
                    sync(descriptor)
                return real_fcntl(descriptor, command, argument)

            monkeypatch.setattr(fcntl, "fcntl", full_sync)

    def on_open(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before the file is opened."""
        self._before_open[name] = effect

    def after_open(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the file is open, before the store gets its descriptor."""
        self._after_open[name] = effect

    def on_write(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before each write to the file."""
        self._before_write[name] = effect

    def on_sync(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before each sync of the file, whether `os.fsync` or, on macOS,
        `fcntl.F_FULLFSYNC`."""
        self._before_sync[name] = effect

    def after_close(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the file is closed, as if closing it reported an error."""
        self._after_close[name] = effect

    def after_mkdir(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the directory is created, before the store learns it was."""
        self._after_mkdir[name] = effect


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> Faults:
    return Faults(monkeypatch)


def raises(error: BaseException) -> Effect:
    """An effect that raises `error`."""

    def effect() -> None:
        raise error

    return effect


def once(effect: Effect) -> Effect:
    """`effect` the first time, and nothing after."""
    done = False

    def first() -> object:
        nonlocal done
        if done:
            return None
        done = True
        return effect()

    return first


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Every file and directory under `root`, hidden ones included: a file's bytes, or None for a
    directory."""
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


CONFIGS = Path(__file__).resolve().parents[1] / "fixtures" / "screen-configs"
RESPONSES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"

VERSIONS = Versions(
    trialfolio="0.1.0",
    p123api=VERIFIED_VERSIONS["p123api"][0],
    requests=VERIFIED_VERSIONS["requests"][0],
    urllib3=VERIFIED_VERSIONS["urllib3"][0],
)


@dataclass(frozen=True)
class Normalized:
    """A run's attempt over the fake server, and what normalizing its saved response wrote."""

    store: LocalArtifactStore
    plan: Plan
    configuration: StoredFile
    response: SavedResponse
    sent: dict[str, object]
    """The backtest request's body, as the fake server received it."""

    def write_tables(self) -> NormalizedTables:
        content = self.store.read(self.configuration.path)
        return write_tables(
            self.store,
            self.plan,
            original_values(content, "configuration.yaml"),
            configuration=self.configuration,
            response=self.response,
        )


type Execute = Callable[[bytes, bytes], Normalized]


@pytest.fixture
def execute(tmp_path: Path) -> Iterator[Execute]:
    """Runs one attempt as `run` does: plans the configuration's bytes, claims a new output
    directory with `plan.json`, saves `configuration.yaml`, and sends the request with the real
    client, `requests`, and `urllib3` to the fake server, which answers it with a 200 and the
    body given. The attempt saves the response; normalizing it is left to the test."""
    server = FakePortfolio123()
    outputs = itertools.count(1)

    def run(content: bytes, body: bytes) -> Normalized:
        plan = build_plan(read_screen_configuration(content, "configuration.yaml"), VERSIONS)
        store = LocalArtifactStore(tmp_path / f"out-{next(outputs)}")
        store.claim("plan.json", plan.model_dump_json(indent=2).encode())
        configuration = store.write("configuration.yaml", content)
        server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
        server.reply("/screen/backtest", Reply(200, body))
        credentials = Credentials(canaries.API_ID, canaries.API_KEY)
        with P123ScreenBacktestClient(credentials, endpoint=server.endpoint) as client:
            result = Attempt(plan, plan.plan_hash, store).run(client)
        assert result.record.outcome == "succeeded"
        assert result.record.response is not None
        sent = json.loads(server.received[-1].body)
        return Normalized(store, plan, configuration, result.record.response, sent)

    yield run
    server.close()


def execute_run(content: bytes, out: Path, body: bytes) -> Plan:
    """Runs the configuration's bytes as `trialfolio run` does once it's approved with `--approve`,
    through `Execution`, into the new output directory `out`. The real client, `requests`, and
    `urllib3` send the request to the fake server, which answers it with a 200 and the body given.
    Returns the plan; the run's files are under `out`."""
    plan = build_plan(read_screen_configuration(content, "configuration.yaml"), VERSIONS)
    command = CommandRecord(
        name="run", options={"approve": plan.plan_hash, "json": False}, started_at=RUN_STARTED
    )
    server = FakePortfolio123()
    server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
    server.reply("/screen/backtest", Reply(200, body))
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    try:
        error = Execution(plan, plan.plan_hash, "option", LocalArtifactStore(out), command).run(
            content, lambda: P123ScreenBacktestClient(credentials, endpoint=server.endpoint)
        )
    finally:
        server.close()
    assert error is None
    return plan


RUN_STARTED = datetime(2026, 10, 3, 14, 0, 0, tzinfo=UTC)
"""When the runs `write_run` writes start; their attempts start and end a second later."""

_SCHEMA_VERSIONS: dict[ArtifactRole, str] = {
    "plan": "1.0.0",
    "configuration": "1.0.0",
    "start_record": "1.0.0",
    "attempt_record": "1.0.0",
    "metrics": TABLES_SCHEMA_VERSION,
    "settings": TABLES_SCHEMA_VERSION,
}


def _source(role: ArtifactRole) -> SourceRecord | None:
    """A source record for the test runs' manifests. The CLI (R01-T14) decides the real ones."""
    if role == "configuration":
        return SourceRecord(
            acquired_at=RUN_STARTED,
            format="screen-configuration",
            format_version="1.0.0",
            parser_version=None,
            provenance="user_supplied",
            operation=None,
        )
    if role in ("provider_request", "provider_response", "provider_response_undecoded"):
        read = role == "provider_response"
        return SourceRecord(
            acquired_at=RUN_STARTED,
            format=LAYOUT if read else f"{LAYOUT}-{role.removeprefix('provider_')}",
            format_version=str(LAYOUT_VERSION),
            parser_version=PARSER_VERSION if read else None,
            provenance="verified",
            operation="screen_backtest",
        )
    return None


def listed(role: ArtifactRole, stored: StoredFile) -> ManifestArtifact:
    """`stored` as a run manifest lists it."""
    return ManifestArtifact(
        path=stored.path,
        artifact_id=stored.artifact_id,
        size=stored.size,
        role=role,
        schema_version=_SCHEMA_VERSIONS.get(role),
        source=_source(role),
    )


def manifest_json(manifest: RunManifest) -> bytes:
    return (manifest.model_dump_json(indent=2) + "\n").encode()


@dataclass(frozen=True)
class Written:
    """A run written as `run` writes one: its directory, and what its report rendered."""

    out: Path
    saved: SavedRun
    """The run as the report rendered it: its manifest is without the report."""
    report: StoredFile
    manifest: RunManifest
    """The manifest as written, the report included."""
    received: tuple[str, ...]
    """The requests the fake server received, as their method and path."""

    @property
    def html(self) -> str:
        return (self.out / self.report.path).read_text(encoding="utf-8")


type WriteRun = Callable[..., Written]


@pytest.fixture
def write_run(tmp_path: Path) -> Iterator[WriteRun]:
    """Writes a complete run as `run` does, ahead of the CLI (R01-T14): plans the configuration's
    bytes, claims a new output directory with `plan.json`, saves `configuration.yaml`, runs the
    attempt with the real client over the fake server, normalizes a response that succeeded,
    writes the report, and then the manifest. `backtest` is the fake server's reply to the
    request, and `authentication` its reply to Trial Folio's authentication call.

    The manifest is built here, as the test's stand-in for the command's. `synthetic` labels the
    run as `trialfolio demo` writes it, although the attempt still reaches the fake server."""
    server = FakePortfolio123()
    outputs = itertools.count(1)

    def run(
        content: bytes,
        backtest: Reply | None = None,
        *,
        authentication: Reply | None = None,
        synthetic: bool = False,
    ) -> Written:
        plan = build_plan(read_screen_configuration(content, "configuration.yaml"), VERSIONS)
        store = LocalArtifactStore(tmp_path / f"run-{next(outputs)}")
        claim = store.claim("plan.json", plan.model_dump_json(indent=2).encode())
        files: list[tuple[ArtifactRole, StoredFile]] = [("plan", claim)]
        configuration = store.write("configuration.yaml", content)
        files.append(("configuration", configuration))
        server.reply("/auth", authentication or Reply(200, canaries.TOKEN.encode()))
        if backtest is not None:
            server.reply("/screen/backtest", backtest)
        before = len(server.received)
        credentials = Credentials(canaries.API_ID, canaries.API_KEY)
        moments = iter((RUN_STARTED + timedelta(seconds=1), RUN_STARTED + timedelta(seconds=2)))
        with P123ScreenBacktestClient(credentials, endpoint=server.endpoint) as client:
            result = Attempt(plan, plan.plan_hash, store, clock=lambda: next(moments)).run(client)
        files.extend((file.role, file.file) for file in result.files)
        error = result.error
        tables: NormalizedTables | None = None
        if result.record.response is not None and error is None:
            try:
                tables = write_tables(
                    store,
                    plan,
                    original_values(content, "configuration.yaml"),
                    configuration=configuration,
                    response=result.record.response,
                )
            except TrialFolioError as failure:
                error = failure
        if tables is not None:
            files.extend((("metrics", tables.metrics), ("settings", tables.settings)))
        record = result.record
        flagged = {row.setting: "not_snapshotted" in row.flags for row in plan.cases[0].settings}
        references = tuple(
            ExternalReference(setting=name, snapshotted=False)
            for name, not_snapshotted in flagged.items()
            if not_snapshotted
        )
        manifest = RunManifest(
            schema_version="1.0.0",
            artifact_type="run",
            trialfolio_version=VERSIONS.trialfolio,
            created_at=RUN_STARTED + timedelta(seconds=3),
            command=CommandRecord(
                name="demo" if synthetic else "run",
                options={"out": "out", "approve": None if synthetic else plan.plan_hash},
                started_at=RUN_STARTED,
            ),
            synthetic=synthetic,
            plan_hash=plan.plan_hash,
            approval="not_required" if synthetic else "option",
            outcome="completed" if error is None else "failed",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            artifacts=tuple(listed(role, stored) for role, stored in files),
            parsers=(
                ParserVersion(
                    layout=LAYOUT, layout_version=LAYOUT_VERSION, parser_version=PARSER_VERSION
                ),
            ),
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            capabilities=Capabilities(
                return_series="source_only"
                if record.response is not None and record.response.form == "decoded"
                else "absent",
                statistical_validation="not_assessed",
                trading_readiness="not_assessed",
            ),
            reproducibility=Reproducibility(
                status="incomplete" if references else "complete",
                external_references=references,
            ),
            counts=ManifestCounts(
                results=1 if tables is not None else 0,
                cases=1,
                attempts=AttemptCounts(
                    succeeded=int(record.outcome == "succeeded"),
                    failed=int(record.outcome == "failed"),
                    unknown=int(record.outcome == "unknown"),
                    running=0,
                ),
                provider_requests=provider_requests(record),
                retries=0,
                cost=record.provider_metadata.cost,
            ),
        )
        saved = SavedRun(
            manifest=manifest,
            plan=plan,
            attempts=(SavedAttempt(start=None, record=record),),
            metrics=None if tables is None else tables.metrics_rows,
            settings=None if tables is None else tables.settings_rows,
        )
        report = write_report(store, saved, HtmlReportRenderer(VERSIONS.trialfolio))
        complete = RunManifest.model_validate_json(
            manifest.model_copy(
                update={"artifacts": (*manifest.artifacts, listed("report", report))}
            ).model_dump_json()
        )
        store.write("manifest.json", manifest_json(complete))
        received = tuple(server.requests()[before:])
        return Written(store.root, saved, report, complete, received)

    yield run
    server.close()
