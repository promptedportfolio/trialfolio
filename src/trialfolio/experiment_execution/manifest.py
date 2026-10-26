"""The builder of an experiment session's manifest, and of the evidence its report shows, which
give the same counts, parsers, capabilities, and files (docs/contracts.md, the experiment
manifest, the experiment report, and the resume's new manifest's entries).

`ManifestBuilder` lists each file of the experiment's records, as the ledger and the writer of
the session's records hold them: each plan's files, each attempt's, followed by its case's tables
once it succeeded, and the session's record, with the report last. A file the latest manifest
lists is listed as it lists it, its source record included, apart from a response whose case's
`metrics.csv` that manifest doesn't list. Each session of an experiment any of whose plans has a
ranking definition writes experiment manifest 1.1.0, and every other session 1.0.0. Nothing here
writes or logs: the executor writes the report and the manifest, and `trialfolio.manifests`
holds what a session's manifest shares with a run's and a review's.
"""

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Final, Literal, TypedDict, get_args

from trialfolio.attempts import AttemptFile, ExperimentAttemptResult
from trialfolio.contracts.common import Approval, ErrorDetail
from trialfolio.contracts.experiment_manifest import (
    EXPERIMENT_CONFIGURATION_FORMAT,
    ExperimentArtifact,
    ExperimentArtifactRole,
    ExperimentArtifactRoleV1_1,
    ExperimentArtifactV1_1,
    ExperimentCommandRecord,
    ExperimentManifest,
    ExperimentManifestCounts,
    ExperimentManifestV1_1,
)
from trialfolio.contracts.manifest_parts import (
    Capabilities,
    ParserVersion,
    Reproducibility,
    SourceRecord,
    SourceRecordV1_1,
)
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution.context import SessionContext
from trialfolio.experiment_execution.ledger import Ledger, LedgerAttempt
from trialfolio.experiment_execution.records import SCHEMA_VERSION, RecordedPlan, SessionRecords
from trialfolio.manifests import (
    PROVIDER_ROLES,
    attempt_source,
    capabilities,
    configuration_source,
    definition_source,
    parsers,
    provider_source,
    reproducibility,
    snapshot_definition_source,
    source_v1_1,
    utc,
)
from trialfolio.normalization import holds_series
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.provider import DecodedResponse
from trialfolio.report import ExperimentEvidence, RetiredCaseView
from trialfolio.storage import StoredFile

RANKING_SCHEMA_VERSION: Final = "1.1.0"
"""The schema version of the experiment manifests of an experiment with a ranking definition."""

_SCHEMA_VERSIONS: Final[dict[ExperimentArtifactRoleV1_1, str]] = {
    "plan": "1.1.0",
    "experiment_record": "1.0.0",
    "authentication_record": "1.0.0",
    "start_record": "1.1.0",
    "attempt_record": "1.1.0",
    "metrics": TABLES_SCHEMA_VERSION,
    "settings": TABLES_SCHEMA_VERSION,
    "session_record": "1.0.0",
}
"""The schema version the manifest records for each role whose files have one, apart from the
configuration, which gives its own."""

_FIXED_VERSIONS: Final[dict[ExperimentArtifactRoleV1_1, str]] = {
    "ranking_snapshot_record": "1.0.0",
    "authentication_record": "1.0.0",
    "metrics": TABLES_SCHEMA_VERSION,
    "session_record": "1.0.0",
}
"""The same, for an experiment with a ranking definition, for the roles whose files have one
version: each other file's is its plan's, its attempt's, or its table's (the experiment manifest's
version 1.1.0)."""

_ATTEMPT_RECORDS: Final[frozenset[ExperimentArtifactRoleV1_1]] = frozenset(
    {"update_record", "start_record", "attempt_record"}
)
"""The roles of an attempt's records whose version is its attempt's: 1.3.0 for an attempt that
sends a definition, and 1.1.0 otherwise."""

_ROLES_V1_0: Final[dict[str, ExperimentArtifactRole]] = {
    role: role for role in get_args(ExperimentArtifactRole)
}
"""Experiment manifest 1.0.0's roles, which every experiment without a ranking definition's files
have."""


class _SessionManifestFields(TypedDict):
    """The fields experiment manifests 1.0.0 and 1.1.0 share, but the schema version and the
    artifacts."""

    artifact_type: Literal["experiment"]
    trialfolio_version: str
    created_at: datetime
    experiment_id: str
    session: int
    command: ExperimentCommandRecord | None
    synthetic: bool
    plan: int
    plan_hash: str
    approval: Approval
    outcome: Literal["completed", "partial"]
    error: ErrorDetail | None
    parsers: tuple[ParserVersion, ...]
    license_id: str
    notice_version: str
    capabilities: Capabilities
    reproducibility: Reproducibility
    counts: ExperimentManifestCounts


class ManifestBuilder:
    """Builds the session's manifest, and its report's evidence, from what the session's records
    hold when the session reaches its end."""

    def __init__(
        self,
        context: SessionContext,
        ledger: Ledger,
        records: SessionRecords,
        results: Sequence[ExperimentAttemptResult],
    ) -> None:
        """`results` are the session's attempts, as they end, whose saved responses the
        capabilities read."""
        self._context = context
        self._ledger = ledger
        self._records = records
        self._results = results

    def counts(self) -> ExperimentManifestCounts:
        """The experiment's counts, over the plan the session runs."""
        return self._ledger.counts(self._context.plan, retired=self._records.retired())

    def evidence(self, error: TrialFolioError | None) -> ExperimentEvidence:
        """What the session's report shows, `error` being the session's, if it has one."""
        context, ledger, plan = self._context, self._ledger, self._context.plan
        record = self._records.experiment_record()
        ranked = self._records.ranked
        return ExperimentEvidence(
            plan=plan,
            plan_number=self._records.plan_number,
            record=record,
            session=context.session,
            synthetic=context.synthetic,
            approval=context.approval,
            command=context.command,
            outcome="completed" if error is None else "partial",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            cases=tuple(ledger.case_view(case) for case in plan.cases),
            retired=tuple(
                RetiredCaseView(
                    case=retired,
                    outcome=ledger.outcome(retired.case_id),
                    attempts=ledger.records_of(retired.case_id),
                )
                for retired in record.retired_cases
            ),
            counts=self.counts(),
            parsers=self._parsers(),
            capabilities=capabilities(series=self._holds_series()),
            reproducibility=reproducibility(plan.cases),
            artifacts=(self._artifacts_v1_1() if ranked else self._artifacts()),
            rankings=tuple(recorded.ranking for recorded in self._records.plans) if ranked else (),
        )

    def manifest(
        self, error: TrialFolioError | None, created_at: datetime, report: StoredFile | None
    ) -> ExperimentManifest | ExperimentManifestV1_1:
        """The session's manifest, listing `report` last: version 1.1.0 for an experiment with a
        ranking definition, and 1.0.0 otherwise."""
        context, plan = self._context, self._context.plan
        fields = _SessionManifestFields(
            artifact_type="experiment",
            trialfolio_version=plan.trialfolio_version,
            created_at=created_at,
            experiment_id=plan.experiment_id,
            session=context.session,
            command=context.command,
            synthetic=context.synthetic,
            plan=self._records.plan_number,
            plan_hash=plan.plan_hash,
            approval=context.approval,
            outcome="completed" if error is None else "partial",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            parsers=self._parsers(),
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            capabilities=capabilities(series=self._holds_series()),
            reproducibility=reproducibility(plan.cases),
            counts=self.counts(),
        )
        if self._records.ranked:
            ranked = self._artifacts_v1_1()
            if report is not None:
                ranked = (*ranked, self._listed_v1_1("report", report))
            return ExperimentManifestV1_1(
                **fields, schema_version=RANKING_SCHEMA_VERSION, artifacts=ranked
            )
        artifacts = self._artifacts()
        if report is not None:
            artifacts = (*artifacts, self._listed("report", report))
        return ExperimentManifest(**fields, schema_version=SCHEMA_VERSION, artifacts=artifacts)

    def _parsers(self) -> tuple[ParserVersion, ...]:
        """Each parser that wrote a case's `metrics.csv`, or the installed one when none did."""
        return parsers(self._ledger.parser_versions())

    def _holds_series(self) -> bool:
        """Whether a saved response of the experiment holds per-period series: each decoded
        response the manifest lists, one whose write failed after the store published it
        included, though no attempt record references it."""
        responses = [r for result in self._results for r in (result.response, result.published)]
        if any(isinstance(r, DecodedResponse) and holds_series(r.payload) for r in responses):
            return True
        experiment = self._context.experiment
        if experiment is None:
            return False
        for attempt in experiment.attempts:
            if attempt.decoded_response is None:
                continue
            try:
                payload: object = json.loads(attempt.decoded_response)
            except (UnicodeDecodeError, ValueError, RecursionError):
                continue
            if holds_series(payload):
                return True
        return False

    def _artifacts(self) -> tuple[ExperimentArtifact, ...]:
        """Each file of the experiment's records so far, as the manifest lists it, apart from
        the report: each plan's files, each attempt's, followed by its case's tables once it
        succeeded, and the session's record. A file the latest manifest lists is listed as it
        lists it, its source record included."""
        listed = [
            self._earlier(stored.path) or self._listed(_ROLES_V1_0[role], stored, plan=recorded)
            for recorded in self._records.plans
            for role, stored in recorded.files
        ]
        for attempt in self._ledger.attempts:
            listed.extend(self._attempt_file(file, attempt) for file in attempt.files)
            tables = self._ledger.tables_of(attempt)
            if tables is not None:
                metrics, settings = tables.metrics, tables.settings
                listed.append(self._earlier(metrics.path) or self._listed("metrics", metrics))
                listed.append(self._earlier(settings.path) or self._listed("settings", settings))
        session_record = self._records.session_record
        if session_record is not None:
            listed.append(self._listed("session_record", session_record))
        return tuple(listed)

    def _artifacts_v1_1(self) -> tuple[ExperimentArtifactV1_1, ...]:
        """Each file of the records of an experiment with a ranking definition, as experiment
        manifest 1.1.0 lists it, in `_artifacts`' order, a plan's `definition.xml` and each
        attempt's update record and `rank_update` files included. A file the latest manifest
        lists is listed as it lists it, as `_artifacts` lists one, an entry of a manifest 1.0.0
        as version 1.1.0 lists it; and each other file with its own version, its plan's, its
        attempt's, or its table's."""
        listed = [
            self._earlier_v1_1(stored.path) or self._listed_v1_1(role, stored, plan=recorded)
            for recorded in self._records.plans
            for role, stored in recorded.files
        ]
        for attempt in self._ledger.attempts:
            listed.extend(self._attempt_file_v1_1(file, attempt) for file in attempt.files)
            tables = self._ledger.tables_of(attempt)
            if tables is not None:
                metrics, settings = tables.metrics, tables.settings
                listed.append(
                    self._earlier_v1_1(metrics.path) or self._listed_v1_1("metrics", metrics)
                )
                listed.append(
                    self._earlier_v1_1(settings.path)
                    or self._listed_v1_1("settings", settings, version=tables.settings_version)
                )
        session_record = self._records.session_record
        if session_record is not None:
            listed.append(self._listed_v1_1("session_record", session_record))
        return tuple(listed)

    def _attempt_file_v1_1(
        self, file: AttemptFile, attempt: LedgerAttempt
    ) -> ExperimentArtifactV1_1:
        """The file as experiment manifest 1.1.0 lists it, by `_attempt_file`'s rule."""
        earlier = self._earlier_v1_1(file.file.path)
        tables = self._ledger.tables_of(attempt)
        if earlier is not None and not (
            file.role == "provider_response"
            and tables is not None
            and self._earlier_v1_1(tables.metrics.path) is None
        ):
            return earlier
        return self._listed_v1_1(file.role, file.file, attempt=attempt)

    def _attempt_file(self, file: AttemptFile, attempt: LedgerAttempt) -> ExperimentArtifact:
        """The file as the manifest lists it: as the latest manifest does, unless it's a
        response whose case's `metrics.csv` that manifest doesn't list, which the installed
        parser wrote since, and which its source record then names (which parser wrote them)."""
        role = _ROLES_V1_0[file.role]
        earlier = self._earlier(file.file.path)
        tables = self._ledger.tables_of(attempt)
        if earlier is not None and not (
            role == "provider_response"
            and tables is not None
            and self._earlier(tables.metrics.path) is None
        ):
            return earlier
        source = None
        if role in PROVIDER_ROLES:
            started, ended = self._attempt_times(attempt)
            source = provider_source(role, started_at=started, ended_at=ended)
        return self._listed(role, file.file, source)

    def _attempt_times(self, attempt: LedgerAttempt) -> tuple[datetime, datetime]:
        """When the attempt started and ended, as its record gives them, which date its
        request's and its response's source records; without a record, the clock's time."""
        record = attempt.record
        started = record.started_at if record is not None else utc(self._context.clock())
        ended = record.ended_at if record is not None else started
        return started, ended

    def _earlier(self, path: str) -> ExperimentArtifact | None:
        """The latest manifest's entry for a file of the experiment's records, which the new
        manifest lists as it is, its source record included. A manifest 1.0.0 follows only
        manifests 1.0.0: once a plan has a ranking definition, every session writes 1.1.0."""
        experiment = self._context.experiment
        entry = None if experiment is None else experiment.listed(path)
        if entry is not None and not isinstance(entry, ExperimentArtifact):
            raise RuntimeError("an experiment manifest 1.0.0 never follows a 1.1.0")
        return entry

    def _earlier_v1_1(self, path: str) -> ExperimentArtifactV1_1 | None:
        """The latest manifest's entry for a file, as `_earlier` gives it, as experiment
        manifest 1.1.0 lists it: an entry of a manifest 1.0.0, written before a plan of the
        experiment had a ranking definition, has the same fields, and its source record a
        version 1.1.0's."""
        experiment = self._context.experiment
        entry = None if experiment is None else experiment.listed(path)
        if entry is None or isinstance(entry, ExperimentArtifactV1_1):
            return entry
        return ExperimentArtifactV1_1.model_validate_json(entry.model_dump_json())

    def _listed(
        self,
        role: ExperimentArtifactRole,
        stored: StoredFile,
        source: SourceRecord | None = None,
        *,
        plan: RecordedPlan | None = None,
    ) -> ExperimentArtifact:
        schema_version = _SCHEMA_VERSIONS.get(role)
        if role == "configuration" and plan is not None:
            schema_version = plan.configuration_version
            # Acquired when its plan was recorded, so every session's manifest gives it the
            # same time: the plan's `experiment.json` records when.
            source = configuration_source(
                EXPERIMENT_CONFIGURATION_FORMAT, schema_version, plan.record.created_at
            )
        return ExperimentArtifact(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=role,
            schema_version=schema_version,
            source=source,
        )

    def _listed_v1_1(
        self,
        role: ExperimentArtifactRoleV1_1,
        stored: StoredFile,
        *,
        plan: RecordedPlan | None = None,
        attempt: LedgerAttempt | None = None,
        version: str | None = None,
    ) -> ExperimentArtifactV1_1:
        """A file as experiment manifest 1.1.0 lists it: with its schema version, and the source
        record of a source artifact. A plan's `configuration.yaml` and `definition.xml` are
        acquired when the plan is recorded, as its `experiment.json` records; an attempt's
        requests and responses, at its times (a run with a ranking definition). Its version is
        its plan's, for a plan's file, its attempt's, for an attempt's records, `version`, for
        `settings.csv`, and otherwise its role's."""
        schema_version = _FIXED_VERSIONS.get(role, version)
        if plan is not None and role == "plan":
            schema_version = plan.plan_version
        elif plan is not None and role == "experiment_record":
            schema_version = plan.record.schema_version
        elif attempt is not None and role in _ATTEMPT_RECORDS:
            schema_version = attempt.version
        source: SourceRecordV1_1 | None = None
        if plan is not None and role == "configuration":
            schema_version = plan.configuration_version
            source = source_v1_1(
                configuration_source(
                    EXPERIMENT_CONFIGURATION_FORMAT, schema_version, plan.record.created_at
                )
            )
        elif plan is not None and role == "ranking_definition":
            snapshot = None if plan.read is None else plan.read.snapshot
            source = (
                definition_source(plan.record.created_at)
                if snapshot is None
                else snapshot_definition_source(snapshot.record.taken_at)
            )
        elif attempt is not None:
            source = attempt_source(role, lambda: self._attempt_times(attempt))
        return ExperimentArtifactV1_1(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=role,
            schema_version=schema_version,
            source=source,
        )
