"""The core tests' fixtures: what the store syncs, failures injected into its file operations
(AGENTS.md, verification expectations: injected storage failures), an attempt run over the fake
Portfolio123 server, below `urllib3`, whose saved response the normalization tests read, and a
complete run, with its report and manifest, for the report tests.

TS-T04 moved the helpers the tests import to modules under `tests/support/`: `SyncLog`, `Faults`,
and their effects to `file_faults.py`, the runs' types and `execute_run` to `screen_runs.py`, the
fixtures' paths to `paths.py`, and `snapshot` to `directories.py`, which held the same function. So
this file keeps the fixtures, and the helpers only `write_run` uses.
"""

import itertools
import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import cast, get_args

import pytest

from tests.support.fake_portfolio123 import AUTHENTICATED, CREDENTIALS, FakePortfolio123, Reply
from tests.support.file_faults import Faults, SyncLog
from tests.support.screen_runs import (
    RUN_STARTED,
    VERSIONS,
    Execute,
    Normalized,
    WriteRun,
    Written,
    manifest_json,
)
from trialfolio.attempts import Attempt, AttemptRole, provider_requests
from trialfolio.configuration import original_values, read_screen_configuration
from trialfolio.contracts.common import ErrorDetail
from trialfolio.contracts.manifest import (
    ArtifactRole,
    CommandRecord,
    ManifestArtifact,
    ManifestCounts,
    RunManifest,
)
from trialfolio.contracts.manifest_parts import (
    AttemptCounts,
    Capabilities,
    ExternalReference,
    ParserVersion,
    Reproducibility,
    SourceRecord,
)
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION
from trialfolio.errors import TrialFolioError
from trialfolio.normalization import (
    LAYOUT,
    LAYOUT_VERSION,
    PARSER_VERSION,
    NormalizedTables,
    write_tables,
)
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.planning import build_plan
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.report import HtmlReportRenderer, write_report
from trialfolio.runs import SavedAttempt, SavedRun
from trialfolio.storage import LocalArtifactStore, StoredFile


@pytest.fixture
def sync_log(monkeypatch: pytest.MonkeyPatch) -> SyncLog:
    """Records every sync, whether `os.fsync` or, on macOS, `fcntl.F_FULLFSYNC`."""
    return SyncLog(monkeypatch)


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> Faults:
    return Faults(monkeypatch)


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
        server.reply("/auth", AUTHENTICATED)
        server.reply("/screen/backtest", Reply(200, body))
        with P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint) as client:
            result = Attempt(plan, plan.plan_hash, store).run(client)
        assert result.record.outcome == "succeeded"
        assert result.record.response is not None
        sent = json.loads(server.received[-1].body)
        return Normalized(store, plan, configuration, result.record.response, sent)

    yield run
    server.close()


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


def run_role(role: AttemptRole) -> ArtifactRole:
    """The role of a file a screen run's attempt wrote, without a ranking definition: never an
    authentication record, which only an experiment's attempts write, or a `rank_update`'s
    file."""
    assert role in get_args(ArtifactRole)
    return cast("ArtifactRole", role)


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
        server.reply("/auth", authentication or AUTHENTICATED)
        if backtest is not None:
            server.reply("/screen/backtest", backtest)
        before = len(server.received)
        moments = iter((RUN_STARTED + timedelta(seconds=1), RUN_STARTED + timedelta(seconds=2)))
        with P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint) as client:
            result = Attempt(plan, plan.plan_hash, store, clock=lambda: next(moments)).run(client)
        files.extend((run_role(file.role), file.file) for file in result.files)
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
