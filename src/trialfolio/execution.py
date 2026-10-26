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
too, unless an interrupt or a storage failure decided the error code, or the attempt ended before
`configuration.yaml` was saved, which every manifest lists, as after an unexpected exception
writing it: the output then stays visibly incomplete, without a manifest (endings that decide the
error code). `trialfolio.single_attempt` takes the steps a run shares with a ranking snapshot's
execution: the claim, the attempt, and the ending. `trialfolio.manifests` holds what a run shares
here with an experiment and a review: writing the manifest and discarding it, the endings without
one, and the parts of the manifest that a run and an experiment record alike.

From 0.4.0, a plan 1.2.0, whose ranking is a definition, runs the same steps, with these
differences (sending a definition, a run with a ranking definition):

- Before step 1, it takes the ranking lock, on the file its caller gives, and holds it until the
  execution ends, after the manifest (`experiment.locked`, `storage.write_failed`). So nothing is
  sent or written while another Trial Folio process writes `ApiRankingSystem`.
- Step 2 also writes `definition.xml`, right after `configuration.yaml`, from the definition's
  bytes the configuration was validated with, which a manifest of such a run lists too. For a
  ranking named by a snapshot, it's the snapshot's `definition.xml`, and `snapshot.json`, the
  snapshot's record, follows it, each from the bytes read and checked when the configuration was
  validated (reading a snapshot).
- Step 3's attempt (`RankingAttempt`) sends the case's `rank_update`, then, once at least 10
  seconds have passed since its 200 (D-45), its backtest, with start and attempt records 1.2.0.
- Step 4 writes `settings.csv` 1.1.0, with a weight row for each node, and step 6 run manifest
  1.1.0, with the roles and source records of the files a definition adds. A run the core writes
  with the demo's client, which no command writes, is synthetic, with no command, and needs no
  approval.

Nothing here prompts, reads the environment, or reads secrets: the command passes the approved
hash, a factory for the client, which holds any credentials, and the ranking lock's file.
"""

import logging
import os
from collections.abc import Callable
from datetime import datetime
from typing import Final, Literal, TypedDict, get_args

from trialfolio.attempts import (
    Attempt,
    AttemptResult,
    AttemptRole,
    Clock,
    RankingAttempt,
    utc_now,
)
from trialfolio.configuration import (
    ScreenConfigurationRead,
    original_values,
    read_screen_configuration_v1_1,
    screen_original_values_v1_1,
)
from trialfolio.contracts.attempt import (
    AttemptRecord,
    AttemptRecordV1_2,
    StartRecord,
    StartRecordV1_2,
)
from trialfolio.contracts.common import Approval, ErrorDetail
from trialfolio.contracts.manifest import (
    ArtifactRole,
    ArtifactRoleV1_1,
    CommandRecord,
    ManifestArtifact,
    ManifestArtifactV1_1,
    ManifestCounts,
    RunManifest,
    RunManifestV1_1,
)
from trialfolio.contracts.manifest_parts import (
    Capabilities,
    ParserVersion,
    Reproducibility,
    SourceRecord,
    SourceRecordV1_1,
)
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION
from trialfolio.errors import TrialFolioError
from trialfolio.manifests import (
    PROVIDER_ROLES,
    ManifestDetails,
    ManifestFile,
    attempt_source,
    capabilities,
    configuration_source,
    definition_source,
    parsers,
    provider_source,
    reproducibility,
    running_detail,
    snapshot_definition_source,
    source_v1_1,
    updating_detail,
    utc,
)
from trialfolio.normalization import NormalizedTables, RankingOriginals, holds_series, write_tables
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.pause import REAL_PAUSE, Pause
from trialfolio.planning import ranking_source
from trialfolio.provider import DecodedResponse
from trialfolio.ranking_lock import RankingLock
from trialfolio.report import HtmlReportRenderer, write_report
from trialfolio.runs import CONFIGURATION_PATH, MANIFEST_PATH, SavedAttempt, SavedRun
from trialfolio.single_attempt import ClientFactory, Kind, SingleAttemptExecution, single_counts
from trialfolio.snapshots import SnapshotFiles
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the run manifests this module writes for a run without a ranking
definition."""

RANKING_SCHEMA_VERSION: Final = "1.1.0"
"""The schema version of the run manifest of a run whose ranking is a definition."""

DEFINITION_PATH: Final = "definition.xml"
"""The copy of a ranking definition, beside `configuration.yaml` (ranking definitions)."""

SNAPSHOT_PATH: Final = "snapshot.json"
"""The copy of a ranking snapshot's record, beside its `definition.xml` (reading a snapshot)."""

_SCREEN_CONFIGURATION_FORMAT: Final = "screen-configuration"

_SCHEMA_VERSIONS: Final[dict[ArtifactRoleV1_1, str]] = {
    "plan": "1.0.0",
    "start_record": "1.0.0",
    "attempt_record": "1.0.0",
    "metrics": TABLES_SCHEMA_VERSION,
    "settings": TABLES_SCHEMA_VERSION,
}
"""The schema version the manifest records for each role whose files have one, apart from the
configuration, which gives its own."""

_RANKING_SCHEMA_VERSIONS: Final[dict[ArtifactRoleV1_1, str]] = {
    "plan": "1.2.0",
    "ranking_snapshot_record": "1.0.0",
    "update_record": "1.2.0",
    "start_record": "1.2.0",
    "attempt_record": "1.2.0",
    "metrics": TABLES_SCHEMA_VERSION,
    "settings": "1.1.0",
}
"""The same, for a run whose ranking is a definition."""

_ROLES_V1_0: Final[dict[str, ArtifactRole]] = {role: role for role in get_args(ArtifactRole)}
"""Run manifest 1.0.0's roles, which every run without a ranking definition's files have."""

_MANIFEST: Final = ManifestDetails(
    written="The run's manifest was written, so its output is complete.",
    left=(
        "The run's manifest.json was published before the failure, and couldn't be removed, so"
        " the run reads as complete although the command failed."
    ),
    missing="The run has no manifest, so its output is incomplete.",
)

_RUN: Final = Kind("run", "case.completed", _logger)


class _ManifestFields(TypedDict):
    """The fields run manifests 1.0.0 and 1.1.0 share, but the schema version, the command, and
    the artifacts."""

    artifact_type: Literal["run"]
    trialfolio_version: str
    created_at: datetime
    synthetic: bool
    plan_hash: str
    approval: Approval
    outcome: Literal["completed", "failed"]
    error: ErrorDetail | None
    parsers: tuple[ParserVersion, ...]
    license_id: str
    notice_version: str
    capabilities: Capabilities
    reproducibility: Reproducibility
    counts: ManifestCounts


class Execution(SingleAttemptExecution[Plan | PlanV1_2, Attempt | RankingAttempt]):
    """One execution of an approved plan's case into the output directory of `store`.

    Its properties stay readable whatever happens, so a command interrupted while it runs still
    knows what it wrote: whether it claimed the directory, the attempt, and each file.
    """

    def __init__(
        self,
        plan: Plan | PlanV1_2,
        approved_hash: str,
        approval: Approval,
        store: ArtifactStore,
        command: CommandRecord | None,
        *,
        clock: Clock = utc_now,
        ranking_lock: str | os.PathLike[str] | None = None,
        pause: Pause = REAL_PAUSE,
    ) -> None:
        """Writes nothing.

        `approval` is how the plan was approved, as the manifest records it: `not_required`
        exactly for a synthetic run, the one `trialfolio demo` writes, which is `command`'s
        `demo`, or one with a ranking definition that the core writes with the demo's client,
        whose `command` is None, since no command writes it. `ranking_lock` is the ranking lock's
        file, which an execution of a plan 1.2.0, whose ranking is a definition, takes, and no
        other does. `pause` is the wait between the `rank_update`'s 200 and the backtest of such
        a plan's attempt (D-45), which tests inject, as they do the clock.

        Raises `TrialFolioError` with `plan.approval_required` unless `approved_hash` is the
        plan's hash, recomputed from its contents (approval), and `ValueError` if `approval` and
        `command` disagree about whether the run is synthetic, if `command` is None for a plan
        without a ranking definition, or if `ranking_lock` is given for a plan without one, or
        not given for a plan with one.
        """
        super().__init__(
            plan,
            approved_hash,
            store,
            ManifestFile(store, MANIFEST_PATH, _MANIFEST),
            command_started=None if command is None else command.started_at,
            clock=clock,
            kind=_RUN,
        )
        ranking = isinstance(plan, PlanV1_2)
        synthetic = command is None or command.name == "demo"
        if (approval == "not_required") != synthetic:
            raise ValueError("only a synthetic run needs no approval")
        if command is None and not ranking:
            raise ValueError("only a run with a ranking definition that the core writes has none")
        if (ranking_lock is not None) != ranking:
            raise ValueError(
                "a run with a ranking definition, and only one, takes the ranking lock"
            )
        self._approval: Approval = approval
        self._command = command
        self._pause = pause
        self._lock = None if ranking_lock is None else RankingLock(ranking_lock)
        self._copies: tuple[_Copy, ...] = ()
        self._definition: StoredFile | None = None
        self._snapshot: StoredFile | None = None
        """The copy of the snapshot's record, `snapshot.json`, for a ranking named by one."""
        self._read: ScreenConfigurationRead | None = None
        self._tables: NormalizedTables | None = None
        self._report: StoredFile | None = None
        self._files: list[tuple[ArtifactRoleV1_1, StoredFile]] = []
        self._configuration_version = ""

    @property
    def tables(self) -> NormalizedTables | None:
        return self._tables

    @property
    def report(self) -> StoredFile | None:
        return self._report

    def run(
        self,
        configuration: bytes,
        client: ClientFactory,
        *,
        definition: bytes | None = None,
        snapshot: SnapshotFiles | None = None,
        on_claimed: Callable[[], object] | None = None,
    ) -> TrialFolioError | None:
        """Takes the steps the module lists. `configuration` is the configuration file's bytes,
        as the plan was built from them, and, for a plan 1.2.0, `definition` the bytes of the
        definition file it names, or `snapshot` those of the snapshot's two files it names, read
        when it was validated. `on_claimed` is called once the directory is claimed, before
        anything else is written into it, such as to start writing logs there.

        Returns the error the command reports, or None when the run completed. Raises the claim's
        `TrialFolioError`, `output.not_empty` or `storage.write_failed`, the ranking lock's,
        `experiment.locked` or `storage.write_failed`, and a `KeyboardInterrupt` during the lock
        or the claim, which removes what the claim created, so nothing is left. Raises
        `ValueError`, before anything else, when a plan 1.2.0 isn't given its definition, or its
        snapshot's files, or is given ones that aren't the plan's, or another plan is given
        either. A run without a command is
        synthetic, so `client` makes the demo's client: another one is closed unused, and is a
        `ValueError` once it's made, before anything is sent, which leaves the output without an
        attempt record or a manifest. After the claim, every ending
        is returned, except a second interrupt while the attempt record is written once more,
        and an unexpected exception after the attempt ended, which leave the output without a
        manifest. `ending_detail` says what such an ending means for the run.
        """
        self._check_unrun()
        self._check_configuration(configuration, definition, snapshot)
        self._copies = _copies(definition, snapshot)
        self._begin()
        if self._lock is None:
            return self._run_claimed(configuration, client, on_claimed)
        with self._lock:
            return self._run_claimed(configuration, client, on_claimed)

    @property
    def _version(self) -> str:
        return self._plan.trialfolio_version

    @property
    def _synthetic(self) -> bool:
        """Whether this is a synthetic run: the one `trialfolio demo` writes, or one with a
        ranking definition that the core writes with the demo's client."""
        return self._command is None or self._command.name == "demo"

    @property
    def _ranking(self) -> bool:
        return isinstance(self._plan, PlanV1_2)

    @property
    def _snapshot_named(self) -> bool:
        """Whether the plan's ranking is named by a snapshot, whose record the run copies."""
        return isinstance(self._plan, PlanV1_2) and self._plan.ranking_source.form == "snapshot"

    @property
    def _case_id(self) -> str:
        return self._plan.cases[0].case_id

    def _check_configuration(
        self, configuration: bytes, definition: bytes | None, snapshot: SnapshotFiles | None
    ) -> None:
        """Reads the configuration's schema version. For a plan 1.2.0, it reads the
        configuration with the definition's bytes, or the snapshot's files', which it checks are
        the plan's definition, and its snapshot, so `definition.xml` and `snapshot.json` hold
        what the plan was built from."""
        # Validated already, when the plan was built from it. A configuration 1.1.0 whose ranking
        # is a formula, a name, or an ID gives a plan 1.0.0 too, so release 0.4.0's reader, which
        # reads either version, reads it (R04-T12).
        if not isinstance(self._plan, PlanV1_2):
            if definition is not None or snapshot is not None:
                raise ValueError("only a run with a ranking definition is given one")
            read = read_screen_configuration_v1_1(
                configuration, CONFIGURATION_PATH, CONFIGURATION_PATH, files=False
            )
            self._configuration_version = read.configuration.schema_version
            return
        source = self._plan.ranking_source
        if (definition is None) == (snapshot is None) or (snapshot is None) != (
            source.form == "definition"
        ):
            raise ValueError(
                "a run with a ranking definition is given its definition's bytes, or its"
                " snapshot's files, as its plan's ranking_source gives"
            )
        ranked = read_screen_configuration_v1_1(
            configuration,
            CONFIGURATION_PATH,
            CONFIGURATION_PATH,
            definition=definition,
            snapshot=snapshot,
        )
        if ranked.definition is None or (
            ranking_source(ranked.definition, ranked.snapshot) != source
        ):
            raise ValueError("the definition isn't the plan's")
        self._read = ranked
        self._configuration_version = ranked.configuration.schema_version

    def _new_attempt(self) -> Attempt | RankingAttempt:
        if isinstance(self._plan, PlanV1_2):
            return RankingAttempt(
                self._plan,
                self._approved_hash,
                self._store,
                clock=self._clock,
                synthetic=self._synthetic,
                pause=self._pause,
            )
        return Attempt(
            self._plan,
            self._approved_hash,
            self._store,
            clock=self._clock,
            synthetic=self._synthetic,
        )

    def _list(self, role: Literal["plan", "configuration"] | AttemptRole, file: StoredFile) -> None:
        self._files.append((_run_role(role), file))

    def _write_copies(self) -> None:
        """Writes the copies of a run with a ranking definition, right after
        `configuration.yaml`."""
        for role, path, data in self._copies:
            stored = self._store.write(path, data)
            self._files.append((role, stored))
            if role == "ranking_definition":
                self._definition = stored
            else:
                self._snapshot = stored

    def _copies_written(self) -> bool:
        """Whether a run with a ranking definition wrote its definition's copy, with a snapshot's
        record for a snapshot."""
        return not (
            (self._ranking and self._definition is None)
            or (self._snapshot_named and self._snapshot is None)
        )

    def _write_from_response(
        self, configuration: bytes, result: AttemptResult, error: TrialFolioError | None
    ) -> TrialFolioError | None:
        """Step 4: writes the tables from a response that was saved. Returns the run's error,
        which is `provider.response_invalid` when the response fails validation."""
        response = result.record.response
        if error is not None or response is None or self._configuration is None:
            return error
        originals = original_values(configuration, CONFIGURATION_PATH)
        ranking = None
        if self._read is not None and self._definition is not None:
            originals, weights = screen_original_values_v1_1(
                configuration, CONFIGURATION_PATH, self._read
            )
            ranking = RankingOriginals(weights, self._definition)
        try:
            self._tables = write_tables(
                self._store,
                self._plan,
                originals,
                configuration=self._configuration,
                response=response,
                ranking=ranking,
            )
        except TrialFolioError as failure:
            if failure.code != "provider.response_invalid":
                raise
            return failure
        self._files.extend((("metrics", self._tables.metrics), ("settings", self._tables.settings)))
        return None

    def _write_ending(
        self, record: AttemptRecord | AttemptRecordV1_2, error: TrialFolioError | None
    ) -> None:
        """Steps 5 and 6: writes `report.html`, rendered from the manifest as it will be written,
        without the report, then `manifest.json`, which lists the report too. `record` is the
        attempt's record, and `error` the run's."""
        created_at = utc(self._clock())
        snapshot = None if self._read is None else self._read.snapshot
        saved = SavedRun(
            manifest=self._build_manifest(record, error, created_at),
            plan=self._plan,
            attempts=(SavedAttempt(start=self._started(), record=record),),
            metrics=None if self._tables is None else self._tables.metrics_rows,
            settings=None if self._tables is None else self._tables.settings_rows,
            snapshot=None if snapshot is None else snapshot.record,
        )
        report = write_report(self._store, saved, HtmlReportRenderer(self._version))
        self._report = report
        self._files.append(("report", report))
        self._manifest.write(self._build_manifest(record, error, created_at))

    def _started(self) -> StartRecord | StartRecordV1_2 | None:
        return None if self._attempt is None else self._attempt.start_record

    def _running_detail(self, attempt: Attempt | RankingAttempt) -> str:
        return running_detail(ranking=isinstance(attempt, RankingAttempt))

    def _unsent_detail(self, attempt: Attempt | RankingAttempt | None) -> str:
        if isinstance(attempt, RankingAttempt) and attempt.update_record is not None:
            return updating_detail()
        if self._ranking:
            return "Neither the rank_update request nor the screen backtest request was sent."
        return "The screen backtest request wasn't sent."

    def _build_manifest(
        self,
        record: AttemptRecord | AttemptRecordV1_2,
        error: TrialFolioError | None,
        created_at: datetime,
    ) -> RunManifest | RunManifestV1_1:
        """The manifest of the files written so far, for the attempt `record` ended: once the
        report is written, it's listed too. It's version 1.1.0 for a run with a ranking
        definition."""
        saved = None if self._result is None else self._result.response
        series = isinstance(saved, DecodedResponse) and holds_series(saved.payload)
        fields = _ManifestFields(
            artifact_type="run",
            trialfolio_version=self._version,
            created_at=created_at,
            synthetic=self._synthetic,
            plan_hash=self._plan.plan_hash,
            approval=self._approval,
            outcome="completed" if error is None else "failed",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            # Every run lists the installed parser, which wrote its tables, if it has any.
            parsers=parsers(),
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            capabilities=capabilities(series=series),
            reproducibility=reproducibility(self._plan.cases),
            counts=self._counts(record),
        )
        if isinstance(record, AttemptRecordV1_2):
            return RunManifestV1_1(
                **fields,
                schema_version=RANKING_SCHEMA_VERSION,
                command=self._command,
                artifacts=tuple(
                    self._listed_v1_1(role, file, record) for role, file in self._files
                ),
            )
        if self._command is None:  # only a run with a ranking definition has none
            raise RuntimeError("a run without a ranking definition records its command")
        return RunManifest(
            **fields,
            schema_version=SCHEMA_VERSION,
            command=self._command,
            artifacts=tuple(self._listed(role, file, record) for role, file in self._files),
        )

    def _counts(self, record: AttemptRecord | AttemptRecordV1_2) -> ManifestCounts:
        return ManifestCounts(
            results=0 if self._tables is None else 1, cases=1, **single_counts(record)
        )

    def _listed(
        self, role: ArtifactRoleV1_1, stored: StoredFile, record: AttemptRecord | AttemptRecordV1_2
    ) -> ManifestArtifact:
        return ManifestArtifact(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=_ROLES_V1_0[role],
            schema_version=(
                self._configuration_version
                if role == "configuration"
                else _SCHEMA_VERSIONS.get(role)
            ),
            source=self._source(role, record),
        )

    def _listed_v1_1(
        self, role: ArtifactRoleV1_1, stored: StoredFile, record: AttemptRecordV1_2
    ) -> ManifestArtifactV1_1:
        return ManifestArtifactV1_1(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=role,
            schema_version=(
                self._configuration_version
                if role == "configuration"
                else _RANKING_SCHEMA_VERSIONS.get(role)
            ),
            source=self._source_v1_1(role, record),
        )

    def _source(
        self, role: ArtifactRoleV1_1, record: AttemptRecord | AttemptRecordV1_2
    ) -> SourceRecord | None:
        """The source record of a source artifact 1.0.0 names: the configuration, the request,
        and the response (INV-04, source artifacts). None for any other role."""
        if role == "configuration":
            return self._configuration_source()
        if role in PROVIDER_ROLES:
            return provider_source(role, started_at=record.started_at, ended_at=record.ended_at)
        return None

    def _source_v1_1(
        self, role: ArtifactRoleV1_1, record: AttemptRecordV1_2
    ) -> SourceRecordV1_1 | None:
        """The source record of a source artifact of a run with a ranking definition: 1.0.0's,
        and those of a definition's copy, acquired with the configuration, and of the
        `rank_update`'s request and response (a run with a ranking definition)."""
        if role == "configuration":
            return source_v1_1(self._configuration_source())
        if role == "ranking_definition":
            snapshot = None if self._read is None else self._read.snapshot
            if snapshot is not None:
                return snapshot_definition_source(snapshot.record.taken_at)
            return definition_source(self._acquired())
        return attempt_source(role, lambda: (record.started_at, record.ended_at))

    def _configuration_source(self) -> SourceRecord:
        return configuration_source(
            _SCREEN_CONFIGURATION_FORMAT, self._configuration_version, self._acquired()
        )


type _Copy = tuple[Literal["ranking_definition", "ranking_snapshot_record"], str, bytes]
"""A copy a run with a ranking definition writes beside `configuration.yaml`: its role, its path,
and its bytes."""


def _copies(definition: bytes | None, snapshot: SnapshotFiles | None) -> tuple[_Copy, ...]:
    """The copies a run writes right after `configuration.yaml`, in order: the definition's,
    `definition.xml`, from its file's bytes, or from a snapshot's, and then, for a snapshot, its
    record's, `snapshot.json` (ranking definitions, reading a snapshot)."""
    if snapshot is not None:
        return (
            ("ranking_definition", DEFINITION_PATH, snapshot.definition),
            ("ranking_snapshot_record", SNAPSHOT_PATH, snapshot.record),
        )
    if definition is not None:
        return (("ranking_definition", DEFINITION_PATH, definition),)
    return ()


def _run_role(role: Literal["plan", "configuration"] | AttemptRole) -> ArtifactRoleV1_1:
    """The role of a file a screen run wrote, whose attempt never writes an authentication
    record: only an experiment's attempts do."""
    if role == "authentication_record":
        raise ValueError("a screen run's attempt writes no authentication record")
    return role
