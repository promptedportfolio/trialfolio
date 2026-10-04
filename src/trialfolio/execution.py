"""Executing an approved plan into a new output directory: the steps of `trialfolio run` after
approval, which `trialfolio demo` takes too (docs/contracts.md, approval's order of steps,
artifact storage, and reports).

`Execution.run`:

1. Claims the output directory with `plan.json` (`output.not_empty`). Nothing is written before.
2. Writes `configuration.yaml`, the configuration's bytes. That's the first atomic write, so a file
   system that can't take one fails here, before any request (`storage.write_failed`).
3. Runs the attempt (`trialfolio.attempts`): authenticates, writes the start record, sends the
   request at most once, saves the response, and writes the attempt record. An ending after the
   claim and before authenticating writes a `failed` attempt record.
4. Normalizes a response that was saved into `normalized/metrics.csv` and `normalized/settings.csv`.
   A response that fails validation is flagged `provider.response_invalid`, without tables.
5. Writes `report.html`, rendered from the manifest as it will be written, without the report.
6. Writes `manifest.json` last, listing every file. Without it, the output is incomplete. A write
   of it that fails, an interrupt included, discards it if the store had published it already, so
   a run the command reports as failed never reads as complete.

Steps 4 to 6 follow any attempt whose record was written, so a failed attempt is accounted for
too, unless an interrupt or a storage failure decided the error code: the output then stays
visibly incomplete, without a manifest (endings that decide the error code).

Nothing here prompts, reads the environment, or reads secrets: the command passes the approved
hash, and a factory for the client, which holds any credentials.
"""

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Final, Literal

from trialfolio.attempts import (
    Attempt,
    AttemptResult,
    Clock,
    prevailing,
    provider_requests,
    request_detail,
    utc_now,
)
from trialfolio.configuration import original_values, read_screen_configuration
from trialfolio.contracts.attempt import AttemptRecord, StartRecord
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
from trialfolio.normalization import (
    LAYOUT,
    LAYOUT_VERSION,
    PARSER_VERSION,
    NormalizedTables,
    holds_series,
    write_tables,
)
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.planning import check_approval
from trialfolio.provider import DecodedResponse, ScreenBacktestClient
from trialfolio.report import HtmlReportRenderer, write_report
from trialfolio.runs import CONFIGURATION_PATH, MANIFEST_PATH, PLAN_PATH, SavedAttempt, SavedRun
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger(__name__)

type ClientFactory = Callable[[], ScreenBacktestClient]
"""Makes the attempt's new client, once the configuration is saved."""

type ApprovalMethod = Literal["interactive", "option", "not_required"]

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the run manifests this module writes."""

_SCREEN_CONFIGURATION_FORMAT: Final = "screen-configuration"

_SCHEMA_VERSIONS: Final[dict[ArtifactRole, str]] = {
    "plan": "1.0.0",
    "start_record": "1.0.0",
    "attempt_record": "1.0.0",
    "metrics": TABLES_SCHEMA_VERSION,
    "settings": TABLES_SCHEMA_VERSION,
}
"""The schema version the manifest records for each role whose files have one, apart from the
configuration, which gives its own."""


class Execution:
    """One execution of an approved plan's case into the output directory of `store`.

    Its properties stay readable whatever happens, so a command interrupted while it runs still
    knows what it wrote: whether it claimed the directory, the attempt, and each file.
    """

    def __init__(
        self,
        plan: Plan,
        approved_hash: str,
        approval: ApprovalMethod,
        store: ArtifactStore,
        command: CommandRecord,
        *,
        clock: Clock = utc_now,
    ) -> None:
        """Writes nothing.

        `approval` is how the plan was approved, as the manifest records it: `not_required`
        exactly for the synthetic run `trialfolio demo` writes, which is `command`'s `demo`.
        Raises `TrialFolioError` with `plan.approval_required` unless `approved_hash` is the
        plan's hash, recomputed from its contents, and `ValueError` if `approval` and `command`
        disagree about whether the run is synthetic.
        """
        check_approval(plan, approved_hash)
        if (approval == "not_required") != (command.name == "demo"):
            raise ValueError("only the synthetic run trialfolio demo writes needs no approval")
        self._plan = plan
        self._approved_hash = approved_hash
        self._approval: ApprovalMethod = approval
        self._store = store
        self._command = command
        self._clock = clock
        self._claimed = False
        self._attempt: Attempt | None = None
        self._result: AttemptResult | None = None
        self._configuration: StoredFile | None = None
        self._tables: NormalizedTables | None = None
        self._report: StoredFile | None = None
        self._manifest: StoredFile | None = None
        self._manifest_left = False
        """Whether a manifest whose write failed couldn't be discarded."""
        self._files: list[tuple[ArtifactRole, StoredFile]] = []
        self._configuration_version = ""

    @property
    def claimed(self) -> bool:
        """Whether the output directory was claimed. Before then, nothing was written."""
        return self._claimed

    @property
    def attempt(self) -> Attempt | None:
        """The attempt, once the directory is claimed."""
        return self._attempt

    @property
    def result(self) -> AttemptResult | None:
        """How the attempt ended, once it has."""
        return self._result

    @property
    def tables(self) -> NormalizedTables | None:
        return self._tables

    @property
    def report(self) -> StoredFile | None:
        return self._report

    @property
    def manifest(self) -> StoredFile | None:
        """The manifest, once it's written: the run is then complete."""
        return self._manifest

    def run(
        self,
        configuration: bytes,
        client: ClientFactory,
        *,
        on_claimed: Callable[[], object] | None = None,
    ) -> TrialFolioError | None:
        """Takes the steps the module lists. `configuration` is the configuration file's bytes,
        as the plan was built from them. `on_claimed` is called once the directory is claimed,
        before anything else is written into it, such as to start writing logs there.

        Returns the error the command reports, or None when the run completed. Raises the claim's
        `TrialFolioError`, `output.not_empty` or `storage.write_failed`, and a `KeyboardInterrupt`
        during the claim, which removes what the claim created, so nothing is left. After the
        claim, every ending is returned, except a second interrupt while the attempt record is
        written once more, and an unexpected exception after the attempt ended, which leave the
        output without a manifest. `ending_detail` says what such an ending means for the run.
        """
        if self._claimed:
            raise RuntimeError("an execution runs once")
        # Validated already, when the plan was built from it; read here for its schema version.
        self._configuration_version = read_screen_configuration(
            configuration, CONFIGURATION_PATH
        ).schema_version
        plan_file = self._store.claim(PLAN_PATH, _model_json(self._plan))
        self._claimed = True
        self._files.append(("plan", plan_file))
        result = self._attempt_run(configuration, client, on_claimed)
        self._result = result
        self._files.extend((file.role, file.file) for file in result.files)
        error = result.error
        if not result.recorded or (
            error is not None and error.code in ("command.interrupted", "storage.write_failed")
        ):
            return error
        try:
            error = self._normalize(configuration, result, error)
            created_at = _utc(self._clock())
            saved = SavedRun(
                manifest=self._build_manifest(result.record, error, created_at),
                plan=self._plan,
                attempts=(SavedAttempt(start=self._started(), record=result.record),),
                metrics=None if self._tables is None else self._tables.metrics_rows,
                settings=None if self._tables is None else self._tables.settings_rows,
            )
            report = write_report(self._store, saved, HtmlReportRenderer(self._version))
            self._report = report
            self._files.append(("report", report))
            self._write_manifest(self._build_manifest(result.record, error, created_at))
        except KeyboardInterrupt:
            return prevailing(
                TrialFolioError(
                    "command.interrupted",
                    f"Trial Folio was interrupted after the attempt ended. {self.ending_detail()}",
                ),
                error,
            )
        except TrialFolioError as failure:
            if failure.code != "storage.write_failed":
                raise
            ending = self.ending_detail()
            return prevailing(
                TrialFolioError(
                    failure.code,
                    f"{failure.message} {ending}",
                    f"{failure.log_message} {ending}",
                ),
                error,
            )
        _logger.log(
            logging.INFO if error is None else logging.ERROR,
            "Run ended %s: %s.",
            "completed" if error is None else "failed",
            "no error" if error is None else error.code,
            extra=self._log_fields("case.completed"),
        )
        return error

    def ending_detail(self) -> str:
        """What the run's records say, for the message of an ending after the claim that the run
        didn't record itself: whether the screen backtest request was sent and may have been
        charged, as the attempt's records read, and whether the run has its manifest."""
        return f"{self._request_detail()} {self._manifest_detail()}"

    @property
    def _version(self) -> str:
        return self._plan.trialfolio_version

    def _attempt_run(
        self,
        configuration: bytes,
        client: ClientFactory,
        on_claimed: Callable[[], object] | None,
    ) -> AttemptResult:
        made: ScreenBacktestClient | None = None
        try:
            if on_claimed is not None:
                on_claimed()
            self._attempt = Attempt(self._plan, self._approved_hash, self._store, clock=self._clock)
            self._configuration = self._store.write(CONFIGURATION_PATH, configuration)
            self._files.append(("configuration", self._configuration))
            made = client()
        except (KeyboardInterrupt, Exception) as ending:  # noqa: BLE001 - every ending is recorded.
            if made is not None:
                made.close()
            if self._attempt is None:
                self._attempt = Attempt(
                    self._plan, self._approved_hash, self._store, clock=self._clock
                )
            return self._attempt.end_before_authenticating(ending)
        try:
            return self._attempt.run(made)
        finally:
            made.close()

    def _normalize(
        self, configuration: bytes, result: AttemptResult, error: TrialFolioError | None
    ) -> TrialFolioError | None:
        """Writes the tables from a response that was saved. Returns the run's error, which is
        `provider.response_invalid` when the response fails validation."""
        response = result.record.response
        if error is not None or response is None or self._configuration is None:
            return error
        try:
            self._tables = write_tables(
                self._store,
                self._plan,
                original_values(configuration, CONFIGURATION_PATH),
                configuration=self._configuration,
                response=response,
            )
        except TrialFolioError as failure:
            if failure.code != "provider.response_invalid":
                raise
            return failure
        self._files.extend((("metrics", self._tables.metrics), ("settings", self._tables.settings)))
        return None

    def _started(self) -> StartRecord | None:
        return None if self._attempt is None else self._attempt.start_record

    def _request_detail(self) -> str:
        result = self._result
        if result is not None and result.recorded:
            record = result.record
            return request_detail(record.outcome, possibly_charged=record.possibly_charged)
        if self._attempt is not None and self._attempt.start_record is not None:
            return (
                "The screen backtest request may have been sent, and may have been charged: the"
                " attempt's start record reads as running. Trial Folio never retries it"
                " automatically."
            )
        return "The screen backtest request wasn't sent."

    def _manifest_detail(self) -> str:
        if self._manifest is not None:
            return "The run's manifest was written, so its output is complete."
        if self._manifest_left:
            return (
                "The run's manifest.json was published before the failure, and couldn't be"
                " removed, so the run reads as complete although the command failed."
            )
        return "The run has no manifest, so its output is incomplete."

    def _write_manifest(self, manifest: RunManifest) -> None:
        """Writes the manifest. A write that fails, an interrupt or an unexpected exception
        included, discards the file if the store published it before the failure."""
        data = _model_json(manifest)
        try:
            self._manifest = self._store.write(MANIFEST_PATH, data)
        except BaseException:
            self._manifest = None
            try:
                self._store.discard(MANIFEST_PATH, data)
            except TrialFolioError:
                self._manifest_left = True
            raise

    def _build_manifest(
        self, record: AttemptRecord, error: TrialFolioError | None, created_at: datetime
    ) -> RunManifest:
        """The manifest of the files written so far, for the attempt `record` ended: once the
        report is written, it's listed too."""
        (case,) = self._plan.cases
        references = tuple(
            ExternalReference(setting=row.setting, snapshotted=False)
            for row in case.settings
            if "not_snapshotted" in row.flags
        )
        saved = None if self._result is None else self._result.response
        series = isinstance(saved, DecodedResponse) and holds_series(saved.payload)
        return RunManifest(
            schema_version=SCHEMA_VERSION,
            artifact_type="run",
            trialfolio_version=self._version,
            created_at=created_at,
            command=self._command,
            synthetic=self._command.name == "demo",
            plan_hash=self._plan.plan_hash,
            approval=self._approval,
            outcome="completed" if error is None else "failed",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            artifacts=tuple(self._listed(role, stored, record) for role, stored in self._files),
            parsers=(
                ParserVersion(
                    layout=LAYOUT, layout_version=LAYOUT_VERSION, parser_version=PARSER_VERSION
                ),
            ),
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            capabilities=Capabilities(
                # The per-period series, `results.rows` and `chart`, which 0.1.0 preserves
                # without normalizing, when the saved response holds them.
                return_series="source_only" if series else "absent",
                statistical_validation="not_assessed",
                trading_readiness="not_assessed",
            ),
            reproducibility=Reproducibility(
                status="incomplete" if references else "complete",
                external_references=references,
            ),
            counts=ManifestCounts(
                results=0 if self._tables is None else 1,
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

    def _listed(
        self, role: ArtifactRole, stored: StoredFile, record: AttemptRecord
    ) -> ManifestArtifact:
        return ManifestArtifact(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=role,
            schema_version=(
                self._configuration_version
                if role == "configuration"
                else _SCHEMA_VERSIONS.get(role)
            ),
            source=self._source(role, record),
        )

    def _source(self, role: ArtifactRole, record: AttemptRecord) -> SourceRecord | None:
        """The source record of a source artifact: the configuration, the request, and the
        response (INV-04, source artifacts). None for any other role."""
        if role == "configuration":
            return SourceRecord(
                acquired_at=self._command.started_at,
                format=_SCREEN_CONFIGURATION_FORMAT,
                format_version=self._configuration_version,
                parser_version=None,
                provenance="user_supplied",
                operation=None,
            )
        if role not in ("provider_request", "provider_response", "provider_response_undecoded"):
            return None
        decoded = role == "provider_response"
        return SourceRecord(
            # The request was written just before the attempt's start record, and the response
            # was saved just before its attempt record.
            acquired_at=record.started_at if role == "provider_request" else record.ended_at,
            format=LAYOUT if decoded else f"{LAYOUT}-{role.removeprefix('provider_')}",
            format_version=str(LAYOUT_VERSION),
            parser_version=PARSER_VERSION if decoded else None,
            provenance="verified",
            operation="screen_backtest",
        )

    def _log_fields(self, event: str) -> dict[str, str]:
        fields = {
            "event": event,
            "plan_hash": self._plan.plan_hash,
            "case_id": self._plan.cases[0].case_id,
        }
        if self._attempt is not None:
            fields["attempt_id"] = str(self._attempt.attempt_id)
        return fields


def _model_json(model: Plan | RunManifest) -> bytes:
    return (model.model_dump_json(indent=2) + "\n").encode("utf-8")


def _utc(moment: datetime) -> datetime:
    if moment.utcoffset() != timedelta(0):
        raise ValueError("the clock must give UTC times")
    return moment
