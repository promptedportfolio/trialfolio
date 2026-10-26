"""The writer of an experiment session's records (docs/contracts.md, running an experiment,
experiment output, the resume, an experiment's normalized tables, and a stale backtest).

`SessionRecords` writes, as the session reaches each step:

- its session record, `sessions/<s>/session.json`, which reserves the session;
- a plan's directory, `plans/<n>/`, for the first plan or a revision, with the same steps: its
  `configuration.yaml`, the copies after it, its `plan.json`, and its `experiment.json` last, so
  nothing is sent under a plan before;
- step 8 of a resume: the attempt record of each attempt a stopped run left without one, which
  `completion` builds, then the tables of each complete case a stopped run didn't write;
- each succeeded case's tables, right after its attempt record, unless its response fails
  validation, which it records instead, with a stale backtest's flag (D-45).

It records each in the ledger as its write lands, a file the store published before its write
failed included, so the ledger holds what the records hold whatever ends the session. Two of its
answers depend on the order of its writes: `retired` reads the `experiment.json` a revision's
write sets, and `first_plan_recorded` the bytes of the first plan's, which its write builds
before writing them.
"""

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, Self

from trialfolio.attempts import ATTEMPT_RECORD, AttemptFile, ExperimentAttemptResult
from trialfolio.configuration import (
    ExperimentConfigurationRead,
    experiment_original_values,
    experiment_original_values_v1_1,
)
from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.experiment_manifest import ExperimentArtifactRoleV1_1
from trialfolio.contracts.experiment_plan import ExperimentPlanCaseV1_3, PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecordV1_1, SessionRecord
from trialfolio.contracts.plan_parts import RankingSource
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution.completion import completed_record
from trialfolio.experiment_execution.context import SessionContext
from trialfolio.experiment_execution.ledger import CaseTables, Ledger, keyed
from trialfolio.experiment_paths import (
    CONFIGURATION,
    EXPERIMENT_RECORD,
    PLAN,
    SESSION_RECORD,
    plan_path,
    session_path,
)
from trialfolio.experiment_records import (
    AnyExperimentRecord,
    AnyPlan,
    AnyPlanCase,
    MissingTables,
    SavedExperiment,
    SavedExperimentAttempt,
    SavedPlan,
)
from trialfolio.manifests import model_json, utc
from trialfolio.normalization import (
    METRICS_PATH,
    RankingOriginals,
    case_metrics_rows,
    case_tables_path,
    write_case_settings,
    write_case_tables,
)
from trialfolio.planning import (
    PlanRevisionV1_1,
    first_experiment_record_v1_1,
    retired_cases_v1_1,
    revised_experiment_record_v1_1,
)
from trialfolio.report import PlanRanking
from trialfolio.snapshots import SnapshotFiles
from trialfolio.stale_backtests import SentBacktest, stale, stale_error
from trialfolio.storage import StoredFile, published
from trialfolio.tables import read_metrics_csv

_logger = logging.getLogger("trialfolio.experiment_execution")

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the experiment manifests, `experiment.json` files, and session records
this package writes, without a ranking definition."""

DEFINITION_FILE: Final = "definition.xml"
"""The copy of a plan's ranking definition, in its `plans/<n>/` (ranking definitions)."""

SNAPSHOT_FILE: Final = "snapshot.json"
"""The copy of the record of the snapshot a plan's baseline names, after its `definition.xml`
(reading a snapshot)."""


type Copy = tuple[Literal["ranking_definition", "ranking_snapshot_record"], str, bytes]
"""A copy a plan with a ranking definition holds after its `configuration.yaml`: its role, its
file's name in `plans/<n>/`, and its bytes."""


def copies(definition: bytes | None, snapshot: SnapshotFiles | None) -> tuple[Copy, ...]:
    """The copies a plan's directory holds after its `configuration.yaml`, in order: the
    definition's, `definition.xml`, from its file's bytes, or from a snapshot's, and then, for a
    snapshot, its record's, `snapshot.json` (ranking definitions, reading a snapshot)."""
    if snapshot is not None:
        return (
            ("ranking_definition", DEFINITION_FILE, snapshot.definition),
            ("ranking_snapshot_record", SNAPSHOT_FILE, snapshot.record),
        )
    if definition is not None:
        return (("ranking_definition", DEFINITION_FILE, definition),)
    return ()


@dataclass(frozen=True)
class CheckedConfiguration:
    """The configuration the session's plan was built from, once the executor checked that it
    gives the plan, as a plan's directory records it."""

    content: bytes
    """Its bytes, which `configuration.yaml` holds."""
    copies: tuple[Copy, ...]
    version: str
    """Its schema version, which its manifest entry records."""
    read: ExperimentConfigurationRead | None
    """The configuration, as 0.4.0's reader read it, for a plan with a ranking definition, or a
    configuration 1.1.0's: its cases' original values come from it."""


@dataclass(frozen=True)
class RecordedPlan:
    """A plan of the experiment, with its files, as the manifest lists them."""

    number: int
    record: AnyExperimentRecord
    files: tuple[tuple[ExperimentArtifactRoleV1_1, StoredFile], ...]
    configuration: bytes
    """Its `configuration.yaml`'s bytes, from which its cases' tables take their original
    values."""
    configuration_version: str
    plan_version: str
    """Its `plan.json`'s schema version: 1.3.0 for a plan with a ranking definition."""
    read: ExperimentConfigurationRead | None = None
    """The configuration as 0.4.0's reader read it, with its definition, for a plan with a
    ranking definition, from which its cases' weight rows take their original values."""
    source: RankingSource | None = None
    """Its `ranking_source`, for a plan with a ranking definition, which its report shows."""

    @classmethod
    def saved(cls, saved: SavedPlan) -> Self:
        """A plan of a resumed experiment, as the records hold it."""
        return cls(
            saved.number,
            saved.record,
            saved.files,
            saved.configuration_content,
            saved.configuration_version,
            saved.plan.schema_version,
            saved.read,
            ranking_source(saved.plan),
        )

    @property
    def ranking(self) -> PlanRanking:
        """Where its ranking definition came from, as the session's report shows it."""
        snapshot = None if self.read is None else self.read.snapshot
        return PlanRanking(self.number, self.source, None if snapshot is None else snapshot.record)


def ranking_source(plan: AnyPlan) -> RankingSource | None:
    """A plan's `ranking_source`: where its ranking definition came from, or None for a plan
    without one."""
    return plan.ranking_source if isinstance(plan, PlanV1_3) else None


@dataclass(frozen=True)
class ApprovedRevision:
    """A revision of the experiment's current plan, approved by its hash, with its reason."""

    revision: PlanRevisionV1_1
    reason: str


class SessionRecords:
    """The writer of a session's records, which keeps what it wrote: the session record, the
    plans, and the `experiment.json` of the plan the session runs."""

    def __init__(self, context: SessionContext, ledger: Ledger) -> None:
        """Writes nothing. For a resume, it holds the experiment's plans as the records hold
        them, and the current plan's `experiment.json`."""
        experiment = context.experiment
        self._context = context
        self._ledger = ledger
        self._session_record: StoredFile | None = None
        self._plan_number = 1 if experiment is None else experiment.current.number
        self._record: AnyExperimentRecord | None = (
            None if experiment is None else experiment.current.record
        )
        self._plans: list[RecordedPlan] = (
            [] if experiment is None else [RecordedPlan.saved(saved) for saved in experiment.plans]
        )
        self._record_data = b""
        """The first plan's `experiment.json`, once it's built."""
        self._previous: SentBacktest | None = None
        """The session's latest attempt that sent a definition and saved its backtest's decoded
        response, against which the next one's is compared (D-45)."""

    @property
    def session_record(self) -> StoredFile | None:
        """The session's record, once it's written, or published whole before its write
        failed."""
        return self._session_record

    @property
    def plan_number(self) -> int:
        """The number of the plan the session runs: the current plan's, and a revision's once
        its `experiment.json` is written."""
        return self._plan_number

    @property
    def plans(self) -> tuple[RecordedPlan, ...]:
        """Each plan of the experiment recorded so far, in order."""
        return tuple(self._plans)

    def next_plan(self) -> int:
        """The number a revision's directory takes, after every plan of the experiment."""
        return 1 if self._context.experiment is None else self._context.experiment.next_plan

    def experiment_record(self) -> AnyExperimentRecord:
        """The `experiment.json` of the plan the session runs."""
        if self._record is None:  # written before any case runs
            raise RuntimeError("the plan is recorded before the session ends")
        return self._record

    @property
    def ranked(self) -> bool:
        """Whether a plan of the experiment has a ranking definition, so its sessions write
        experiment manifest 1.1.0: the current plan's `experiment.json` is 1.1.0, or the plan
        the session runs is 1.3.0 (the experiment manifest's version 1.1.0)."""
        return isinstance(self._record, ExperimentRecordV1_1) or isinstance(
            self._context.plan, PlanV1_3
        )

    def retired(self) -> int:
        """How many cases revisions retired, once the plan the session runs is current: the
        current plan's, or a revision's before its `plans/<n>/` is written."""
        record = self._record
        if record is None:  # a new experiment's, before its first plan is recorded
            return 0
        return len(retired_cases_v1_1(record, self._context.plan))

    def first_plan_recorded(self) -> bool:
        """Whether the experiment's first plan is recorded, so a later run can resume its
        directory: its `experiment.json` is written, or published whole before an interrupt
        stopped its write."""
        if self._record is not None:
            return True
        return bool(self._record_data) and (
            published(self._context.store, plan_path(1, EXPERIMENT_RECORD), self._record_data)
            is not None
        )

    # The session and its plan

    def write_session(self) -> None:
        """Writes the session's record, `sessions/<s>/session.json`, which reserves the
        session."""
        context = self._context
        record = SessionRecord(
            schema_version=SCHEMA_VERSION,
            trialfolio_version=context.plan.trialfolio_version,
            session=context.session,
            started_at=utc(context.clock()),
        )
        path, data = session_path(context.session, SESSION_RECORD), model_json(record)
        try:
            self._session_record = context.store.write(path, data)
        except BaseException:
            # A record the store published before its write failed reserves the session, as an
            # attempt record published so counts as written (R03-T11).
            self._session_record = published(context.store, path, data)
            raise

    def write_first_plan(self, checked: CheckedConfiguration) -> None:
        """Writes the first plan's `plans/1/`."""
        plan, number = self._context.plan, self._plan_number
        files, configuration, stored_plan = self._write_plan_files(number, plan, checked)
        record = first_experiment_record_v1_1(
            plan,
            plan_artifact_id=stored_plan.artifact_id,
            configuration_artifact_id=configuration.artifact_id,
            approval=self._context.approval,
            created_at=utc(self._context.clock()),
        )
        self._record_data = model_json(record)
        self._record_plan(number, plan, checked, files, record, self._record_data)
        _logger.info(
            "Recorded plan %d.", number, extra=self._context.log_fields("experiment.plan.recorded")
        )

    def write_revision(self, approved: ApprovedRevision, checked: CheckedConfiguration) -> None:
        """Writes the revision's `plans/<n>/`, as for the first plan, with the reason in its
        `experiment.json`: 1.0.0 by 0.3.0's rules while no plan of the experiment has a ranking
        definition, and 1.1.0 by release 0.4.0's once one has, as every one after a plan 1.3.0
        is. A revision into a plan 1.3.0 writes its `definition.xml` right after its
        `configuration.yaml`, and, for a snapshot, its `snapshot.json` after that."""
        revision = approved.revision
        number = self.next_plan()
        previous = self.experiment_record()
        files, configuration, stored_plan = self._write_plan_files(number, revision.plan, checked)
        record = revised_experiment_record_v1_1(
            previous,
            revision,
            number=number,
            reason=approved.reason,
            plan_artifact_id=stored_plan.artifact_id,
            configuration_artifact_id=configuration.artifact_id,
            approval=self._context.approval,
            created_at=utc(self._context.clock()),
        )
        self._record_plan(number, revision.plan, checked, files, record, model_json(record))
        _logger.info(
            "Recorded plan %d, which revises plan %d.",
            number,
            previous.plans[-1].plan,
            extra=self._context.log_fields("experiment.plan.recorded"),
        )

    def _write_plan_files(
        self, number: int, plan: AnyPlan, checked: CheckedConfiguration
    ) -> tuple[list[tuple[ExperimentArtifactRoleV1_1, StoredFile]], StoredFile, StoredFile]:
        """Writes `plans/<number>/`'s `configuration.yaml`, the copies after it, and `plan.json`,
        in that order. Returns the files written, with the configuration's and the plan's."""
        store = self._context.store
        files: list[tuple[ExperimentArtifactRoleV1_1, StoredFile]] = []
        configuration = store.write(plan_path(number, CONFIGURATION), checked.content)
        files.append(("configuration", configuration))
        for role, name, data in checked.copies:
            files.append((role, store.write(plan_path(number, name), data)))
        stored_plan = store.write(plan_path(number, PLAN), model_json(plan))
        files.append(("plan", stored_plan))
        return files, configuration, stored_plan

    def _record_plan(
        self,
        number: int,
        plan: AnyPlan,
        checked: CheckedConfiguration,
        files: list[tuple[ExperimentArtifactRoleV1_1, StoredFile]],
        record: AnyExperimentRecord,
        data: bytes,
    ) -> None:
        """Writes the plan's `experiment.json`, `data`, last, and then holds the plan as recorded,
        and as the one the session runs."""
        written = self._context.store.write(plan_path(number, EXPERIMENT_RECORD), data)
        files.append(("experiment_record", written))
        self._record = record
        self._plan_number = number
        self._plans.append(
            RecordedPlan(
                number,
                record,
                tuple(files),
                checked.content,
                checked.version,
                plan.schema_version,
                checked.read,
                ranking_source(plan),
            )
        )

    # Step 8 of a resume

    def complete_records(self, experiment: SavedExperiment) -> None:
        """Step 8 of a resume: writes the attempt record of each attempt a stopped run left
        without one, then the tables of each complete case that a stopped run didn't write."""
        _logger.info(
            "Session %d resumes the experiment under plan %d.",
            self._context.session,
            experiment.current.number,
            extra=self._context.log_fields("experiment.resumed"),
        )
        for place, saved in enumerate(experiment.attempts):
            if saved.record is None:
                self._complete_attempt(place, saved, experiment)
        for case_id, missing in experiment.missing.items():
            self._write_missing(case_id, missing, experiment)

    def _complete_attempt(
        self, place: int, saved: SavedExperimentAttempt, experiment: SavedExperiment
    ) -> None:
        """Writes the attempt record of the attempt at `place`, which a stopped run left without
        one."""
        store = self._context.store
        plan = experiment.saved_plan(saved.plan).plan
        record = completed_record(saved, plan, utc(self._context.clock()))
        path, data = f"{saved.directory}/{ATTEMPT_RECORD}", model_json(record)
        try:
            stored = store.write(path, data)
        except BaseException:
            # The store may publish the record and still fail its write, as when the directory's
            # sync fails. The records then hold it, so the counts read it.
            whole = published(store, path, data)
            if whole is not None:
                files = (*saved.files, AttemptFile("attempt_record", whole))
                self._ledger.record_completed(place, record, files)
            raise
        files = (*saved.files, AttemptFile("attempt_record", stored))
        self._ledger.record_completed(place, record, files)
        _logger.warning(
            "Recorded the attempt a stopped run left without its attempt record: %s; possibly"
            " charged: %s.",
            record.outcome,
            "yes" if record.possibly_charged else "no",
            extra={
                **self._context.log_fields("experiment.attempt.recorded", saved.case_id),
                "attempt_id": str(saved.attempt_id),
            },
        )

    def _write_missing(
        self, case_id: str, missing: MissingTables, experiment: SavedExperiment
    ) -> None:
        store = self._context.store
        if missing.invalid is not None:
            failure = keyed(missing.invalid, missing, self._context.plan, experiment)
            self._case_invalid(case_id, failure, identical_to=missing.identical_to)
            return
        if missing.metrics_rows is not None:
            try:
                tables = write_case_tables(
                    store,
                    missing.case,
                    missing.originals,
                    configuration=missing.configuration,
                    response=missing.response,
                    content=missing.content,
                    ranking=missing.ranking,
                )
            except BaseException:
                self._keep_published_metrics(case_id)
                raise
            self._ledger.keep_tables(case_id, CaseTables.written(tables))
            return
        saved = experiment.tables[case_id]
        settings, rows = write_case_settings(
            store,
            missing.case,
            missing.originals,
            configuration=missing.configuration,
            metrics=saved.metrics_rows,
            ranking=missing.ranking,
        )
        self._ledger.keep_tables(case_id, CaseTables.completed(saved, settings, rows))

    # A case's tables

    def write_tables(self, case: AnyPlanCase, result: ExperimentAttemptResult) -> None:
        """Writes the case's tables from its saved response, right after its attempt record. A
        response that fails validation leaves the case `failed`, awaiting a repeat: one the
        installed parser can't read, as the layout's required structure needs, and a stale
        backtest (D-45). A response that passes it makes a case awaiting a repeat complete, from
        then, as the records read it: a failure that keeps its tables from being written leaves
        them to a resume (an experiment's normalized tables)."""
        response = result.record.response
        if not result.recorded or response is None:
            return
        configuration, originals, ranking = self._originals(case)
        content = self._context.store.read(response.path)
        try:
            stale_after = self._validated(case, result, response, content)
        except TrialFolioError as failure:
            if failure.code != "provider.response_invalid":
                raise
            self._case_invalid(case.case_id, failure)
            return
        if stale_after is not None:
            failure, previous = stale_after
            self._case_invalid(case.case_id, failure, identical_to=previous)
            return
        # The response passed validation, so the case's outcome and state are the records' before
        # its tables are written, and stay so if a failure stops their writes.
        self._ledger.mark_valid(case.case_id)
        try:
            tables = write_case_tables(
                self._context.store,
                case,
                originals,
                configuration=configuration,
                response=response,
                content=content,
                ranking=ranking,
            )
        except BaseException:
            self._keep_published_metrics(case.case_id)
            raise
        self._ledger.keep_tables(case.case_id, CaseTables.written(tables))

    def _originals(
        self, case: AnyPlanCase
    ) -> tuple[StoredFile, Mapping[str, tuple[str, str]], RankingOriginals | None]:
        """The case's saved configuration, each setting's key path and text in it, and, for a
        case ranked by a definition, where its weight rows take their originals."""
        # The session's attempts run under the current plan, and its saved configuration gives
        # the original values, however the configuration given to this run is written.
        plan = self._plans[-1]
        files = dict(plan.files)
        configuration_file = files["configuration"]
        ranking = None
        if plan.read is None:
            originals = experiment_original_values(
                plan.configuration, configuration_file.path, case.case_key
            )
        else:
            originals, weights = experiment_original_values_v1_1(
                plan.configuration, configuration_file.path, plan.read, case.case_key
            )
            if plan.read.definition is not None:
                ranking = RankingOriginals(weights, files["ranking_definition"])
        return configuration_file, originals, ranking

    def _validated(
        self,
        case: AnyPlanCase,
        result: ExperimentAttemptResult,
        response: SavedResponse,
        content: bytes,
    ) -> tuple[TrialFolioError, str] | None:
        """Checks the case's saved response, whose bytes are `content`, and raises its
        `provider.response_invalid` when the installed parser can't read it, as the layout's
        required structure needs. An attempt that sent a definition and saved its backtest's
        decoded response first becomes the session's latest such attempt, whatever its structure;
        for one with the structure, unless the experiment is synthetic, gives the stale backtest's
        `provider.response_invalid`, and the case whose response it repeats, when it's one
        against the one before it (`stale_backtests.py`, D-45)."""
        previous, sent = self._previous, None
        if isinstance(case, ExperimentPlanCaseV1_3) and response.form == "decoded":
            files = {file.role: file.file for file in result.files}
            sent = SentBacktest(
                case_id=case.case_id,
                attempt_id=result.record.attempt_id,
                session=self._context.session,
                update_request=files["rank_update_request"].artifact_id,
                request=files["provider_request"].artifact_id,
                response=content,
            )
            self._previous = sent
        case_metrics_rows(content, case, response)
        if sent is None or self._context.synthetic or previous is None or not stale(sent, previous):
            return None
        before = next(c for c in self._context.plan.cases if c.case_id == previous.case_id)
        failure = stale_error(
            sent, previous.case_id, key=case.case_key, previous_key=before.case_key
        )
        return failure, previous.case_id

    def _keep_published_metrics(self, case_id: str) -> None:
        """After a failed write of the case's tables, keeps the rows of its `metrics.csv` if the
        store published it, as when `settings.csv`'s write fails, or an interrupt comes between
        them. The records then hold it, so `metrics_unavailable` counts it. It's read back, as
        an attempt's file published before its write failed is, because the store may publish
        a file and still fail its write."""
        path = case_tables_path(case_id, METRICS_PATH)
        try:
            self._ledger.keep_metrics(
                case_id, read_metrics_csv(self._context.store.read(path), path)
            )
        except (OSError, TrialFolioError):
            return  # Never published, or not readable: a resume's records check reads it.

    def _case_invalid(
        self, case_id: str, failure: TrialFolioError, *, identical_to: str | None = None
    ) -> None:
        """Records that the case's latest succeeded attempt's response failed validation, and
        logs it. `identical_to` is, for a stale backtest, the case whose response it repeats."""
        self._ledger.mark_invalid(case_id, failure, identical_to=identical_to)
        _logger.error(
            "The case's response failed validation: %s.",
            failure.code,
            extra=self._context.log_fields("experiment.case.invalid", case_id),
        )
