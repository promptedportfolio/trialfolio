"""The ledger of an experiment's execution: what the experiment's records hold, as earlier
sessions left them and this session adds to them, which the session's budget, counts, report,
manifest, and ending messages read (docs/contracts.md, running an experiment, the budget across
runs, an experiment's normalized tables, and repeating a case).

`Ledger` holds each attempt of the experiment, an earlier session's or this one's, as a
`LedgerAttempt`; each case's normalized tables; the rows of each `metrics.csv` whose
`settings.csv` a failure kept the session from writing; and each case whose latest succeeded
attempt's response failed validation, with its `provider.response_invalid`. The rules of a case's
state and outcome, and the experiment's counts, are `case_state`'s, which the reader of an
experiment's records and the plan display share.

The writer of the session's records and its case runner record each change as the write it
follows lands, so whatever ends the session, an interrupt included, the ledger holds what the
records hold, and the caller can still read the session's counts and outcomes. Nothing here reads
or writes the store, or logs.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal, Self

from trialfolio.attempts import (
    AttemptFile,
    ExperimentAttemptResult,
    authentication_calls,
    provider_requests,
)
from trialfolio.case_state import (
    CaseOutcome,
    CaseState,
    case_outcome,
    case_state,
    described,
    described_by,
    experiment_counts,
    invalid_success,
    latest_charged,
    outcome_code,
    unavailable_metrics,
)
from trialfolio.contracts.attempt import AttemptRecordV1_1, AttemptRecordV1_3
from trialfolio.contracts.common import ErrorDetail
from trialfolio.contracts.experiment_manifest import ExperimentManifestCounts
from trialfolio.contracts.tables import (
    TABLES_SCHEMA_VERSION,
    TABLES_SCHEMA_VERSION_V1_1,
    MetricsRow,
    SettingsRowV1_1,
)
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_records import (
    AnyAttemptRecord,
    AnyPlan,
    AnyPlanCase,
    MissingTables,
    SavedExperiment,
    SavedExperimentAttempt,
    SavedTables,
)
from trialfolio.normalization import PARSER_VERSION, AnySettingsRows, NormalizedTables
from trialfolio.provider import provider_message_of
from trialfolio.report import CaseView
from trialfolio.stale_backtests import stale_error
from trialfolio.storage import StoredFile


@dataclass(frozen=True)
class LedgerAttempt:
    """An attempt of the experiment, an earlier session's or this one's, as the session's counts,
    budget, and manifest read it, and the rules of its case's state (`case_state.py`)."""

    case_id: str
    attempt_id: uuid.UUID
    session: int
    sequence: int
    outcome: Literal["running", "succeeded", "failed", "unknown"] | None
    """As its records read: `running` for a start record without an attempt record, and None for
    an attempt of this session that left no record. An earlier session's attempt without its
    attempt record reads as step 8 records it."""
    possibly_charged: bool
    error_code: str | None
    repeat_of: uuid.UUID | None
    provider_requests: int
    """The sends the budget counts."""
    authentication_calls: int
    """Trial Folio's own authentication calls the budget counts."""
    record: AttemptRecordV1_1 | AttemptRecordV1_3 | None
    """Its attempt record, once it's written."""
    files: tuple[AttemptFile, ...]
    version: str
    """The schema version of its start and attempt records: 1.3.0 for an attempt that sends a
    definition, and 1.1.0 otherwise."""

    @classmethod
    def saved(cls, attempt: SavedExperimentAttempt) -> Self:
        """An earlier session's attempt, as the records check read it."""
        return cls(
            case_id=attempt.case_id,
            attempt_id=attempt.attempt_id,
            session=attempt.session,
            sequence=attempt.sequence,
            outcome=attempt.outcome,
            possibly_charged=attempt.possibly_charged,
            error_code=attempt.error_code,
            repeat_of=attempt.repeat_of,
            provider_requests=attempt.provider_requests,
            authentication_calls=attempt.authentication_calls,
            record=attempt.record,
            files=attempt.files,
            version=attempt.version,
        )

    @classmethod
    def recorded(cls, record: AnyAttemptRecord, files: tuple[AttemptFile, ...]) -> Self:
        """An attempt whose attempt record is written."""
        return cls(
            case_id=record.case_id,
            attempt_id=record.attempt_id,
            session=record.session,
            sequence=record.sequence,
            outcome=record.outcome,
            possibly_charged=record.possibly_charged,
            error_code=None if record.error is None else record.error.code,
            repeat_of=record.repeat_of,
            provider_requests=provider_requests(record),
            authentication_calls=authentication_calls(record.exchanges),
            record=record,
            files=files,
            version=record.schema_version,
        )

    @classmethod
    def ended(cls, result: ExperimentAttemptResult) -> Self:
        """An attempt of this session, as its records read. Without its attempt record, which a
        resume writes, it reads as the resume will count it: `running` with its start record, and
        `failed`, not possibly charged, with only its authentication record. An attempt that
        sends a definition counts one request for each start record it wrote, and with only its
        update record, reads as `failed` with its `rank_update`'s response in its directory,
        saved or published before its write failed, and `unknown` without one, possibly charged
        either way (sending a definition)."""
        record = result.record
        if result.recorded:
            return cls.recorded(record, result.files)
        updated = int(result.update is not None)
        outcome: Literal["running", "failed", "unknown"] | None
        if result.start is not None:
            outcome, charged, requests = "running", True, 1 + updated
        elif result.update is not None:
            outcome = "failed" if result.update_saved else "unknown"
            charged, requests = True, 1
        elif any(file.role == "authentication_record" for file in result.files):
            outcome, charged, requests = "failed", False, 0
        else:
            outcome, charged, requests = None, False, 0
        return cls(
            case_id=record.case_id,
            attempt_id=record.attempt_id,
            session=record.session,
            sequence=record.sequence,
            outcome=outcome,
            possibly_charged=charged,
            error_code=None if record.error is None else record.error.code,
            repeat_of=record.repeat_of,
            provider_requests=requests,
            authentication_calls=int(result.authenticated),
            record=None,
            files=result.files,
            version=record.schema_version,
        )


@dataclass(frozen=True)
class CaseTables:
    """A case's normalized tables, their rows, and the parser that wrote its `metrics.csv`."""

    metrics: StoredFile
    settings: StoredFile
    parser_version: int
    metrics_rows: tuple[MetricsRow, ...]
    settings_rows: AnySettingsRows

    @classmethod
    def written(cls, tables: NormalizedTables) -> Self:
        """The tables this session wrote, both of them, with the installed parser."""
        return cls(
            tables.metrics,
            tables.settings,
            PARSER_VERSION,
            tables.metrics_rows,
            tables.settings_rows,
        )

    @classmethod
    def completed(
        cls, saved: SavedTables, settings: StoredFile, settings_rows: AnySettingsRows
    ) -> Self:
        """A `metrics.csv` the records hold, with `settings`, the `settings.csv` beside it: the
        records' own, or the one a resume wrote to complete the pair."""
        return cls(saved.metrics, settings, saved.parser_version, saved.metrics_rows, settings_rows)

    @property
    def settings_version(self) -> str:
        """`settings.csv`'s schema version: 1.1.0 for a case whose ranking is a definition."""
        rows = self.settings_rows
        if rows and isinstance(rows[0], SettingsRowV1_1):
            return TABLES_SCHEMA_VERSION_V1_1
        return TABLES_SCHEMA_VERSION


class Ledger:
    """What the experiment's records hold so far, as the session's counts, budget, report,
    manifest, and ending messages read them."""

    def __init__(self, plan: AnyPlan, experiment: SavedExperiment | None) -> None:
        """Holds nothing for a new experiment. For a resume, it holds what the records check
        found in `experiment`, with each stale backtest's message made again with the keys `plan`
        gives its cases."""
        self._experiment = experiment
        self._attempts: list[LedgerAttempt] = []
        self._tables: dict[str, CaseTables] = {}
        self._metrics_alone: dict[str, tuple[MetricsRow, ...]] = {}
        """The rows of each `metrics.csv` this session published whose `settings.csv` it didn't
        write, because a failure came between them: a resume completes the pair."""
        self._invalid: dict[str, TrialFolioError] = {}
        """The `provider.response_invalid` each case's latest succeeded attempt's saved response
        got, by `case_id`: in a resume, from the start, those the records check found, so the
        outcomes are the records' before step 8 logs them, and after a failure that ends the
        session before it does. A repeat whose response passes validation removes its case."""
        self._identical: dict[str, str] = {}
        """For each case whose latest succeeded attempt is a stale backtest, the `case_id` of the
        case whose response it repeats (D-45)."""
        if experiment is None:
            return
        self._attempts = [LedgerAttempt.saved(attempt) for attempt in experiment.attempts]
        for case_id, tables in experiment.tables.items():
            if tables.settings is not None and tables.settings_rows is not None:
                self._tables[case_id] = CaseTables.completed(
                    tables, tables.settings, tables.settings_rows
                )
        for case_id, missing in experiment.missing.items():
            if missing.invalid is not None:
                self._invalid[case_id] = keyed(missing.invalid, missing, plan, experiment)
        for case_id, missing in experiment.missing.items():
            if missing.identical_to is not None:
                self._identical[case_id] = missing.identical_to

    # What the records hold

    @property
    def attempts(self) -> tuple[LedgerAttempt, ...]:
        """Every attempt of the experiment, by session and then sequence."""
        return tuple(self._attempts)

    def of(self, case_id: str) -> list[LedgerAttempt]:
        """The case's attempts, by session and then sequence."""
        return [attempt for attempt in self._attempts if attempt.case_id == case_id]

    def outcome(self, case_id: str) -> CaseOutcome:
        return case_outcome(self.of(case_id), valid=case_id not in self._invalid)

    def state(self, case_id: str) -> CaseState:
        """The case's state, as the records now give it: one whose latest succeeded attempt's
        response failed validation awaits a repeat (D-45)."""
        return case_state(self.of(case_id), valid=case_id not in self._invalid)

    def described(self, case_id: str) -> str:
        """The case's outcome, with the error code that gives it."""
        return described(self.of(case_id), valid=case_id not in self._invalid)

    def outcome_code(self, case_id: str) -> str | None:
        """The error code that gives the case's outcome, when one does."""
        return outcome_code(self.of(case_id), valid=case_id not in self._invalid)

    def flagged(self, case_id: str) -> TrialFolioError | None:
        """The stale backtest's `provider.response_invalid`, when it gives the case's outcome:
        its latest possibly charged attempt is the succeeded one that's stale (D-45)."""
        if case_id not in self._identical:
            return None
        valid = case_id not in self._invalid
        if not invalid_success(self.of(case_id), valid=valid):
            return None
        return self._invalid.get(case_id)

    def provider_said(self, case_id: str) -> str | None:
        """Portfolio123's own message in the error a case that didn't succeed is described by,
        when it has one."""
        giving = described_by(self.of(case_id))
        if giving is None or giving.record is None or giving.record.error is None:
            return None
        return provider_message_of(giving.record.error.message)

    def records_of(self, case_id: str) -> tuple[AttemptRecordV1_1 | AttemptRecordV1_3, ...]:
        """The case's attempt records, by session and then sequence. Once the session reaches
        its end, every attempt has one: step 8 wrote those a stopped run left, and an attempt of
        this session that left none ended the session before its end."""
        records: list[AttemptRecordV1_1 | AttemptRecordV1_3] = []
        for attempt in self.of(case_id):
            if attempt.outcome is None:
                continue
            if attempt.record is None:
                raise RuntimeError("every attempt has its record before the session's report")
            records.append(attempt.record)
        return tuple(records)

    def tables_of(self, attempt: LedgerAttempt) -> CaseTables | None:
        """The tables drawn from `attempt`'s response: its case's, when it's the case's latest
        succeeded attempt. An earlier one's response failed validation (D-45)."""
        tables = self._tables.get(attempt.case_id)
        if tables is None or attempt.outcome != "succeeded":
            return None
        succeeded = [a for a in self.of(attempt.case_id) if a.outcome == "succeeded"]
        return tables if succeeded[-1] is attempt else None

    def parser_versions(self) -> Iterator[int]:
        """The parser that wrote each case's `metrics.csv`, of each case with both tables."""
        return (tables.parser_version for tables in self._tables.values())

    def repeat_attempts(self, plan: AnyPlan) -> dict[str, uuid.UUID]:
        """Each of `plan`'s cases awaiting a repeat, by its `case_id`, with its latest possibly
        charged attempt's `attempt_id`, which confirms a repeat of it (repeating a case)."""
        repeats: dict[str, uuid.UUID] = {}
        for case in plan.cases:
            attempts = self.of(case.case_id)
            latest = latest_charged(attempts)
            if self.state(case.case_id) == "awaiting_repeat" and latest is not None:
                repeats[case.case_id] = latest.attempt_id
        return repeats

    def counts(self, plan: AnyPlan, *, retired: int) -> ExperimentManifestCounts:
        """The experiment's counts over `plan`, as its manifest gives them, with `retired`, how
        many cases revisions retired."""
        return experiment_counts(plan, self._attempts, invalid=self._invalid, retired=retired)

    def metrics_unavailable(self, plan: AnyPlan) -> int:
        """The `unavailable` rows of `plan`'s cases' `metrics.csv` files, as written so far,
        those whose `settings.csv` a failure kept this session from writing included, so the
        count agrees with the records however the session ends."""
        rows = {case_id: tables.metrics_rows for case_id, tables in self._tables.items()}
        for case_id, metrics in self._metrics_alone.items():
            rows.setdefault(case_id, metrics)
        if self._experiment is not None:
            for case_id, saved in self._experiment.tables.items():
                rows.setdefault(case_id, saved.metrics_rows)
        return unavailable_metrics(plan, rows)

    def case_view(self, case: AnyPlanCase) -> CaseView:
        """The case as the session's report shows it."""
        tables = self._tables.get(case.case_id)
        invalid = self._invalid.get(case.case_id)
        return CaseView(
            case=case,
            outcome=self.outcome(case.case_id),
            attempts=self.records_of(case.case_id),
            metrics=None if tables is None else tables.metrics_rows,
            settings=None if tables is None else tables.settings_rows,
            invalid=(
                None if invalid is None else ErrorDetail(code=invalid.code, message=invalid.message)
            ),
            identical_to=self._identical.get(case.case_id) if invalid is not None else None,
        )

    # What the session records

    def record_ended(self, result: ExperimentAttemptResult) -> None:
        """Adds an attempt of this session, once it ends."""
        self._attempts.append(LedgerAttempt.ended(result))

    def record_completed(
        self, place: int, record: AnyAttemptRecord, files: tuple[AttemptFile, ...]
    ) -> None:
        """Gives the earlier session's attempt at `place`, in the experiment's order, the attempt
        record a resume wrote for it, or that the store published before its write failed."""
        self._attempts[place] = LedgerAttempt.recorded(record, files)

    def keep_tables(self, case_id: str, tables: CaseTables) -> None:
        """Records the case's tables, once both are written."""
        self._tables[case_id] = tables

    def keep_metrics(self, case_id: str, rows: tuple[MetricsRow, ...]) -> None:
        """Records the rows of a `metrics.csv` the store published without its `settings.csv`."""
        self._metrics_alone[case_id] = rows

    def mark_invalid(
        self, case_id: str, failure: TrialFolioError, *, identical_to: str | None = None
    ) -> None:
        """Records that the case's latest succeeded attempt's response failed validation.
        `identical_to` is, for a stale backtest, the case whose response it repeats."""
        self._invalid[case_id] = failure
        if identical_to is None:
            self._identical.pop(case_id, None)
        else:
            self._identical[case_id] = identical_to

    def mark_valid(self, case_id: str) -> None:
        """Records that the case's latest succeeded attempt's response passed validation."""
        self._invalid.pop(case_id, None)
        self._identical.pop(case_id, None)


def keyed(
    failure: TrialFolioError,
    missing: MissingTables,
    plan: AnyPlan,
    experiment: SavedExperiment,
) -> TrialFolioError:
    """`failure`, the `provider.response_invalid` the records check found for a case's response,
    as the session running `plan` reports it: a stale backtest's message is made again with the
    keys `plan` gives the case and the one before it, since a revision can rename a case's key
    and keep its attempts. A case that `plan` retired keeps its key in the plan the attempt ran
    under, which the attempt before it in its session ran under too (D-45)."""
    previous = missing.identical_to
    if previous is None:
        return failure
    keys = {case.case_id: case.case_key for case in plan.cases}
    ran_under = experiment.saved_plan(missing.attempt.plan)

    def key(case_id: str) -> str:
        return keys[case_id] if case_id in keys else ran_under.case(case_id).case_key

    attempt = missing.attempt
    return stale_error(attempt, previous, key=key(attempt.case_id), previous_key=key(previous))
