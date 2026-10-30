"""Screen runs, for the core's tests: one attempt run over the fake Portfolio123 server, below
`urllib3`, whose saved response the normalization tests read (`Normalized`, which the core's
`execute` fixture gives); a run executed as `trialfolio run` executes it, through `Execution`
(`execute_run`); and a complete run, with its report and manifest, for the report tests
(`Written`, which the core's `write_run` fixture gives).

TS-T04 moved them here from the core's conftest, which keeps its two fixtures. TS-T05 added the
command each records (`run_command`), and `Written.of`, which reads what an execution wrote, once
`write_run` wrote its run through `Execution`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from tests.support.fake_portfolio123 import AUTHENTICATED, CREDENTIALS, FakePortfolio123, Reply
from tests.support.plans import verified_versions
from trialfolio.configuration import original_values, read_screen_configuration
from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.manifest import CommandRecord, RunManifest
from trialfolio.contracts.plan import Plan
from trialfolio.execution import Execution
from trialfolio.normalization import NormalizedTables, write_tables
from trialfolio.planning import build_plan
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.runs import MANIFEST_PATH, SavedAttempt, SavedRun
from trialfolio.storage import LocalArtifactStore, StoredFile

VERSIONS: Final = verified_versions("0.1.0")
"""The versions the core's screen runs are planned with: 0.1.0's, and the wrapper's verified
ones."""

RUN_STARTED: Final = datetime(2026, 10, 3, 14, 0, 0, tzinfo=UTC)
"""When the runs `write_run` and `execute_run` write start, as their command records it. The clock
of `write_run`'s runs reads a second later, and a second later at each reading after it."""


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


def run_command(plan: Plan, *, synthetic: bool = False) -> CommandRecord:
    """The command a run's manifest records, as `trialfolio run` records it once the plan is
    approved with `--approve`, or, for a run labeled synthetic, as `trialfolio demo` does."""
    if synthetic:
        return CommandRecord(name="demo", options={"json": False}, started_at=RUN_STARTED)
    return CommandRecord(
        name="run", options={"approve": plan.plan_hash, "json": False}, started_at=RUN_STARTED
    )


def execute_run(content: bytes, out: Path, body: bytes) -> Plan:
    """Runs the configuration's bytes as `trialfolio run` does once it's approved with `--approve`,
    through `Execution`, into the new output directory `out`. The real client, `requests`, and
    `urllib3` send the request to the fake server, which answers it with a 200 and the body given.
    Returns the plan; the run's files are under `out`."""
    plan = build_plan(read_screen_configuration(content, "configuration.yaml"), VERSIONS)
    command = run_command(plan)
    server = FakePortfolio123()
    server.reply("/auth", AUTHENTICATED)
    server.reply("/screen/backtest", Reply(200, body))
    try:
        error = Execution(plan, plan.plan_hash, "option", LocalArtifactStore(out), command).run(
            content, lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint)
        )
    finally:
        server.close()
    assert error is None
    return plan


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

    @classmethod
    def of(
        cls, out: Path, plan: Plan, execution: Execution, received: tuple[str, ...]
    ) -> "Written":
        """What the execution of `plan` into `out` wrote, and the run as its report rendered it:
        the manifest as written, without the report's entry, which the execution listed only
        after the report."""
        attempt, result, report = execution.attempt, execution.result, execution.report
        assert attempt is not None and result is not None and report is not None
        manifest = RunManifest.model_validate_json((out / MANIFEST_PATH).read_bytes())
        listed = tuple(artifact for artifact in manifest.artifacts if artifact.role != "report")
        tables = execution.tables
        saved = SavedRun(
            manifest=manifest.model_copy(update={"artifacts": listed}),
            plan=plan,
            attempts=(SavedAttempt(start=attempt.start_record, record=result.record),),
            metrics=None if tables is None else tables.metrics_rows,
            settings=None if tables is None else tables.settings_rows,
        )
        return cls(out, saved, report, manifest, received)

    @property
    def html(self) -> str:
        return (self.out / self.report.path).read_text(encoding="utf-8")


type WriteRun = Callable[..., Written]
