"""The executor: executing an approved experiment plan, in the core (docs/contracts.md, running
an experiment, experiment output, the lock, the budget across runs, and progress and
cancellation).

`ExperimentExecution.run` executes a new experiment into an output directory that's absent or
empty:

1. It claims the directory with `experiment.lock`, and takes the experiment lock on it
   (`output.not_empty`, `experiment.locked`). The store holds the lock until its owner closes
   it, so no other process can run the experiment meanwhile.
2. It writes `sessions/1/session.json`, which reserves the session. That's the first atomic
   write, so a file system that can't take one fails here, before any request
   (`storage.write_failed`).
3. It writes `plans/1/configuration.yaml`, `plan.json`, and then `experiment.json`. Nothing is
   sent under a plan before its `experiment.json` is written.
4. It runs the cases in the plan's order, one attempt each, with one client, so the session
   authenticates once, and again only after a 401 or 403 drops its token. Before each attempt,
   it checks the cancellation, and that the budget covers one more request, and one more
   authentication call when the attempt authenticates. A case the budget can't cover isn't
   started, and neither is any case after it. So it is after Trial Folio's own authentication
   call fails, whatever its result, or after a request gets `provider.quota_exceeded`, since
   every later case would end the same way (D-32), and after a cancellation.
5. It writes each succeeded case's tables, `cases/<case_id>/normalized/metrics.csv` and
   `settings.csv`, right after its attempt record. A response that fails validation leaves the
   case `failed`, with `provider.response_invalid`, and the session goes on.
6. It writes the session's report, `sessions/1/report.html`, and then its manifest,
   `sessions/1/manifest.json`, last.

A case that fails is recorded, and the session goes on to the next one. An interrupt or a storage
failure ends the session at once, without its manifest, so the experiment's output reads as
incomplete until a later run resumes it; resuming is R03-T09's. So does an attempt whose attempt
record wasn't written, such as after an unexpected exception while writing it, as for a run: a
manifest couldn't account for it. Every attempt written so far stays, and is never replaced.

Execution with the demo's client, which sends nothing, writes a synthetic experiment: its plan
and manifest record the approval `not_required`, and its report says its values are invented.

Nothing here prompts, prints, reads the environment, or reads secrets: the caller passes the
approved hash, and the client, which holds any credentials. Progress goes to the caller's
callback, as events that name each case by its `case_id` and hold no text from the
configuration, and the caller may cancel from any thread. Logs name the plan by its hash and
each case by its `case_id`, never by its key.
"""

import logging
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from pydantic import BaseModel

from trialfolio.attempts import (
    AttemptFile,
    Clock,
    ExperimentAttempt,
    ExperimentAttemptResult,
    provider_requests,
    request_detail,
    utc_now,
)
from trialfolio.configuration import experiment_original_values, read_experiment_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.common import AUTHENTICATION_REQUEST, Approval, ErrorDetail
from trialfolio.contracts.experiment_manifest import (
    EXPERIMENT_CONFIGURATION_FORMAT,
    BudgetLimits,
    CaseCounts,
    ExperimentArtifact,
    ExperimentArtifactRole,
    ExperimentAttemptCounts,
    ExperimentCommandRecord,
    ExperimentManifest,
    ExperimentManifestCounts,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord, SessionRecord
from trialfolio.contracts.manifest import (
    Capabilities,
    ExternalReference,
    ParserVersion,
    Reproducibility,
    SourceRecord,
)
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION
from trialfolio.demo import SyntheticScreenBacktestClient
from trialfolio.errors import TrialFolioError
from trialfolio.normalization import (
    LAYOUT,
    LAYOUT_VERSION,
    PARSER_VERSION,
    NormalizedTables,
    holds_series,
    write_case_tables,
)
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.planning import (
    Versions,
    build_experiment_plan,
    check_approval,
    first_experiment_record,
)
from trialfolio.provider import DecodedResponse, ScreenBacktestClient
from trialfolio.report import (
    CaseView,
    ExperimentEvidence,
    HtmlReportRenderer,
    write_experiment_report,
)
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger(__name__)

LOCK_PATH: Final = "experiment.lock"
"""The file that claims an experiment's output directory, and on which the lock is taken."""

LOCK_LINE: Final = b"Trial Folio experiment lock: it claims this directory for one experiment.\n"
"""The lock file's one fixed line, so the file is never empty (docs/contracts.md, the lock)."""

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the experiment manifests, `experiment.json` files, and session records
this module writes."""

_SCHEMA_VERSIONS: Final[dict[ExperimentArtifactRole, str]] = {
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

type CaseOutcome = Literal["succeeded", "failed", "unknown", "not_yet_run"]
type StopReason = Literal["budget", "authentication", "quota", "cancelled"]


def plan_path(plan: int, name: str) -> str:
    """`plans/<plan>/<name>`, relative to the output root."""
    return f"plans/{plan}/{name}"


def session_path(session: int, name: str) -> str:
    """`sessions/<session>/<name>`, relative to the output root."""
    return f"sessions/{session}/{name}"


# Progress events (docs/contracts.md, progress and cancellation)


@dataclass(frozen=True)
class SessionStarted:
    """The session has reserved its number and recorded its plan, and is about to run its cases."""

    session: int
    cases: tuple[str, ...]
    """The `case_id`s it will send or repeat, in the plan's order."""


@dataclass(frozen=True)
class AttemptStarted:
    case_id: str
    attempt_id: uuid.UUID


@dataclass(frozen=True)
class AttemptEnded:
    """An attempt ended, its attempt record was written, and so were its case's tables, if it
    succeeded."""

    case_id: str
    attempt_id: uuid.UUID
    outcome: Literal["succeeded", "failed", "unknown"]
    possibly_charged: bool


@dataclass(frozen=True)
class SessionEnded:
    """The session wrote its report and its manifest, whose counts these are."""

    session: int
    counts: ExperimentManifestCounts


type ProgressEvent = SessionStarted | AttemptStarted | AttemptEnded | SessionEnded

type Progress = Callable[[ProgressEvent], object]
"""Receives each progress event, in order, in the thread that runs the execution. An exception
it raises ends the session as an unexpected exception would, without its manifest."""


class Cancellation:
    """A request, from any thread, that an execution stop between attempts. Execution checks it
    before each attempt starts, never during one: a send in flight finishes, and is recorded."""

    def __init__(self) -> None:
        self._requested = threading.Event()

    def cancel(self) -> None:
        self._requested.set()

    @property
    def requested(self) -> bool:
        return self._requested.is_set()


# Case outcomes (docs/contracts.md, the experiment manifest)


@dataclass(frozen=True)
class CaseAttempt:
    """What a case's outcome reads of one of its attempts."""

    session: int
    sequence: int
    outcome: Literal["running", "succeeded", "failed", "unknown"]
    """`running` for a start record without an attempt record."""
    possibly_charged: bool
    valid: bool
    """For a succeeded attempt, whether its response passed validation."""


def case_outcome(attempts: Sequence[CaseAttempt]) -> CaseOutcome:
    """A case's outcome, as the manifest counts it: `succeeded` when one of its attempts
    succeeded with a valid response, and `failed` when that response failed validation;
    otherwise the outcome of its latest possibly charged attempt, by session and then sequence,
    with a `running` one counted as `unknown`; `failed` when it has attempts and none is
    possibly charged; and `not_yet_run` when it has none."""
    succeeded = [attempt for attempt in attempts if attempt.outcome == "succeeded"]
    if succeeded:
        return "succeeded" if any(attempt.valid for attempt in succeeded) else "failed"
    charged = [attempt for attempt in attempts if attempt.possibly_charged]
    if charged:
        latest = max(charged, key=lambda attempt: (attempt.session, attempt.sequence))
        return "failed" if latest.outcome == "failed" else "unknown"
    return "failed" if attempts else "not_yet_run"


@dataclass
class _Case:
    """A planned case, and what this session did with it."""

    case: ExperimentPlanCase
    result: ExperimentAttemptResult | None = None
    tables: NormalizedTables | None = None
    invalid: TrialFolioError | None = None
    """The `provider.response_invalid` its saved response got."""

    @property
    def outcome(self) -> CaseOutcome:
        if self.result is None:
            return "not_yet_run"
        record = self.result.record
        return case_outcome(
            (
                CaseAttempt(
                    session=record.session,
                    sequence=record.sequence,
                    outcome=record.outcome,
                    possibly_charged=record.possibly_charged,
                    valid=self.invalid is None,
                ),
            )
        )


class ExperimentExecution:
    """One execution of an approved experiment plan into the output directory of `store`.

    Its properties stay readable whatever happens, so a caller whose execution was interrupted
    still knows what was written: whether the directory was claimed, the session, each attempt,
    and the manifest.
    """

    def __init__(
        self,
        plan: PlanV1_1,
        approved_hash: str,
        approval: Approval,
        store: ArtifactStore,
        client: ScreenBacktestClient,
        *,
        command: ExperimentCommandRecord | None,
        clock: Clock = utc_now,
        progress: Progress | None = None,
        cancellation: Cancellation | None = None,
    ) -> None:
        """Writes nothing.

        `approval` is how the plan was approved, as the records give it: `not_required` exactly
        for the demo's client, `SyntheticScreenBacktestClient`, which makes the experiment
        synthetic. `client` sends every request of the session; its caller closes it. `command`
        is the `trialfolio` command that runs the session, or None when the core runs it for
        another interface, and always for a synthetic experiment.

        Raises `TrialFolioError` with `plan.approval_required` unless `approved_hash` is the
        plan's hash, recomputed from its contents (approval); and `ValueError` when the plan
        revises another, which only a resume can approve, or `approval` or `command` doesn't fit
        whether the experiment is synthetic.
        """
        check_approval(plan, approved_hash)
        if plan.revises is not None:
            raise ValueError("a new experiment's first plan revises none")
        synthetic = isinstance(client, SyntheticScreenBacktestClient)
        if (approval == "not_required") != synthetic:
            raise ValueError("only an experiment executed with the demo's client needs no approval")
        if synthetic and command is not None:
            raise ValueError("no trialfolio command writes a synthetic experiment")
        self._plan = plan
        self._approval: Approval = approval
        self._store = store
        self._client = client
        self._command = command
        self._clock = clock
        self._progress = progress
        self._cancellation = cancellation
        self._synthetic = synthetic
        self._session = 1
        self._plan_number = 1
        self._claimed = False
        self._session_record: StoredFile | None = None
        self._record: ExperimentRecord | None = None
        self._plan_files: list[tuple[ExperimentArtifactRole, StoredFile]] = []
        self._cases = [_Case(case) for case in plan.cases]
        self._attempts: list[ExperimentAttemptResult] = []
        self._current: ExperimentAttempt | None = None
        self._stopped: tuple[StopReason, TrialFolioError | None] | None = None
        self._report: StoredFile | None = None
        self._manifest: ExperimentManifest | None = None
        self._manifest_file: StoredFile | None = None
        self._manifest_left = False
        """Whether a manifest whose write failed couldn't be discarded."""
        self._configuration_version = ""
        self._record_data = b""
        """The first plan's `experiment.json`, once it's built."""

    @property
    def claimed(self) -> bool:
        """Whether the output directory was claimed. Before then, nothing was written."""
        return self._claimed

    @property
    def session(self) -> int | None:
        """The session's number, once its session record is written."""
        return None if self._session_record is None else self._session

    @property
    def synthetic(self) -> bool:
        return self._synthetic

    @property
    def attempts(self) -> tuple[ExperimentAttemptResult, ...]:
        """Each attempt that ended in this session, in order."""
        return tuple(self._attempts)

    @property
    def outcomes(self) -> tuple[tuple[ExperimentPlanCase, CaseOutcome], ...]:
        """Each planned case, in the plan's order, with its outcome as the records now give it."""
        return tuple((case.case, case.outcome) for case in self._cases)

    @property
    def manifest(self) -> ExperimentManifest | None:
        """The session's manifest, once it's written: the session is then complete."""
        return self._manifest

    @property
    def report(self) -> StoredFile | None:
        return self._report

    def run(
        self, configuration: bytes, *, on_claimed: Callable[[], object] | None = None
    ) -> TrialFolioError | None:
        """Takes the steps the module lists. `configuration` is the bytes of the experiment
        configuration the plan was built from. `on_claimed` is called once the directory is
        claimed, before anything else is written into it, such as to start writing logs there.

        Returns the error the caller reports, or None when every planned case succeeded:
        `execution.partial` when the session reached its end with a case that didn't succeed;
        `command.interrupted` or `storage.write_failed` when an interrupt or a storage failure
        ended the session without its manifest; and the attempt's error, such as
        `internal.unexpected`, when an attempt's record wasn't written, which ends the session
        the same way. Raises `ValueError` before writing
        anything when `configuration` doesn't give the plan; the claim's `TrialFolioError`,
        `output.not_empty`, `experiment.locked`, or `storage.write_failed`, and a
        `KeyboardInterrupt` during the claim, which removes what the claim created, so nothing
        is left; and any unexpected exception, which leaves the session without its manifest.
        """
        if self._claimed:
            raise RuntimeError("an execution runs once")
        self._check_configuration(configuration)
        self._store.claim(LOCK_PATH, LOCK_LINE, lock=True)
        self._claimed = True
        try:
            if on_claimed is not None:
                on_claimed()
            self._write_session()
            self._write_plan(configuration)
        except KeyboardInterrupt:
            return self._before_cases(
                TrialFolioError("command.interrupted", "Trial Folio was interrupted.")
            )
        except TrialFolioError as failure:
            if failure.code != "storage.write_failed":
                raise
            return self._before_cases(failure)
        _logger.info(
            "Session %d started, under plan %d.",
            self._session,
            self._plan_number,
            extra=self._log_fields("experiment.session.started"),
        )
        try:
            self._emit(SessionStarted(self._session, tuple(c.case.case_id for c in self._cases)))
            ending = self._run_cases(configuration)
            if ending is not None:
                return self._incomplete(ending)
            error = self._partial()
            self._write_ending(error)
        except KeyboardInterrupt:
            return self._incomplete(
                TrialFolioError("command.interrupted", "Trial Folio was interrupted.")
            )
        except TrialFolioError as failure:
            if failure.code != "storage.write_failed":
                raise
            return self._incomplete(failure)
        manifest = self._manifest
        if manifest is not None:
            self._emit(SessionEnded(self._session, manifest.counts))
        return error

    def ending_detail(self) -> str:
        """What the session's records say, for the message of an ending the session didn't
        record itself, such as an unexpected exception: whether the request of the attempt under
        way may have been sent, and whether the session has its manifest."""
        return f"{self._attempt_detail()} {self._manifest_detail()}"

    # The session's records

    def _check_configuration(self, configuration: bytes) -> None:
        plan = self._plan
        versions = Versions(
            trialfolio=plan.trialfolio_version,
            p123api=plan.provider_wrapper.p123api,
            requests=plan.transport.requests,
            urllib3=plan.transport.urllib3,
        )
        read = read_experiment_configuration(configuration, plan_path(1, "configuration.yaml"))
        if build_experiment_plan(read, versions) != plan:
            raise ValueError("the configuration doesn't give the plan")
        self._configuration_version = read.schema_version

    def _write_session(self) -> None:
        record = SessionRecord(
            schema_version=SCHEMA_VERSION,
            trialfolio_version=self._plan.trialfolio_version,
            session=self._session,
            started_at=_utc(self._clock()),
        )
        self._session_record = self._store.write(
            session_path(self._session, "session.json"), _model_json(record)
        )

    def _write_plan(self, configuration: bytes) -> None:
        number = self._plan_number
        saved = self._store.write(plan_path(number, "configuration.yaml"), configuration)
        self._plan_files.append(("configuration", saved))
        plan = self._store.write(plan_path(number, "plan.json"), _model_json(self._plan))
        self._plan_files.append(("plan", plan))
        record = first_experiment_record(
            self._plan,
            plan_artifact_id=plan.artifact_id,
            configuration_artifact_id=saved.artifact_id,
            approval=self._approval,
            created_at=_utc(self._clock()),
        )
        self._record_data = _model_json(record)
        written = self._store.write(plan_path(number, "experiment.json"), self._record_data)
        self._plan_files.append(("experiment_record", written))
        self._record = record
        _logger.info(
            "Recorded plan %d.", number, extra=self._log_fields("experiment.plan.recorded")
        )

    # The cases

    def _run_cases(self, configuration: bytes) -> TrialFolioError | None:
        """Runs each case in the plan's order, until one can't start. Returns the error of an
        attempt that an interrupt or a storage failure ended, or whose attempt record wasn't
        written, which ends the session."""
        token_from: uuid.UUID | None = None
        for place, case in enumerate(self._cases, 1):
            later = place < len(self._cases)
            stop = self._stop_before(token_from is None)
            if stop is not None:
                self._stop(stop, None)
                break
            attempt = ExperimentAttempt(
                self._plan,
                case.case,
                self._store,
                session=self._session,
                # The session starts its attempts one at a time, so this is its next one.
                sequence=len(self._attempts) + 1,
                clock=self._clock,
                synthetic=self._synthetic,
            )
            self._current = attempt
            self._emit(AttemptStarted(case.case.case_id, attempt.attempt_id))
            result = attempt.run(self._client, token_from)
            self._current = None
            self._attempts.append(result)
            case.result = result
            error = result.error
            # A manifest can't account for an attempt without its attempt record, whose start
            # record reads as running, so that ends the session too, whatever stopped the write.
            if not result.recorded or (
                error is not None and error.code in ("command.interrupted", "storage.write_failed")
            ):
                return error
            self._write_tables(case, result, configuration)
            record = result.record
            self._emit(
                AttemptEnded(
                    case.case.case_id,
                    attempt.attempt_id,
                    record.outcome,
                    record.possibly_charged,
                )
            )
            if not self._client.authenticated:
                token_from = None
            elif result.authenticated and not result.authentication_failed:
                token_from = attempt.attempt_id
            # Every later case would end the same way (D-32).
            if later and result.authentication_failed:
                self._stop("authentication", error)
                break
            quota = record.error is not None and record.error.code == "provider.quota_exceeded"
            if later and quota:
                self._stop("quota", error)
                break
        return None

    def _stop_before(self, authenticates: bool) -> StopReason | None:
        """Why the next attempt can't start, if it can't: a cancellation, or a budget that
        doesn't cover one more request, or one more authentication call when it authenticates."""
        if self._cancellation is not None and self._cancellation.requested:
            return "cancelled"
        budget = self._plan.budget
        if self._provider_requests() + 1 > budget.provider_requests:
            return "budget"
        if authenticates and self._authentication_calls() + 1 > budget.authentication_calls:
            return "budget"
        return None

    def _stop(self, reason: StopReason, error: TrialFolioError | None) -> None:
        self._stopped = (reason, error)
        _logger.warning(
            "No later case starts: %s.",
            _STOPS[reason],
            extra=self._log_fields("experiment.stopped"),
        )

    def _write_tables(
        self, case: _Case, result: ExperimentAttemptResult, configuration: bytes
    ) -> None:
        """Writes the case's tables from its saved response, right after its attempt record. A
        response that fails validation leaves the case `failed`."""
        response = result.record.response
        if not result.recorded or response is None:
            return
        configuration_file = dict(self._plan_files)["configuration"]
        originals = experiment_original_values(
            configuration, configuration_file.path, case.case.case_key
        )
        try:
            case.tables = write_case_tables(
                self._store,
                case.case,
                originals,
                configuration=configuration_file,
                response=response,
            )
        except TrialFolioError as failure:
            if failure.code != "provider.response_invalid":
                raise
            case.invalid = failure
            _logger.error(
                "The case's response failed validation: %s.",
                failure.code,
                extra=self._log_fields("experiment.case.invalid", case.case.case_id),
            )

    # The end of the session

    def _write_ending(self, error: TrialFolioError | None) -> None:
        """Writes the session's report, then its manifest. A write of the manifest that fails,
        an interrupt included, discards it if the store had published it."""
        created_at = _utc(self._clock())
        evidence = ExperimentEvidence(
            plan=self._plan,
            plan_number=self._plan_number,
            record=self._experiment_record(),
            session=self._session,
            synthetic=self._synthetic,
            outcome="completed" if error is None else "partial",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            cases=tuple(
                CaseView(
                    case=case.case,
                    outcome=case.outcome,
                    attempts=0 if case.result is None else 1,
                    tables=case.tables is not None,
                )
                for case in self._cases
            ),
            counts=self._counts(),
            artifacts=self._artifacts(),
        )
        self._report = write_experiment_report(
            self._store, evidence, HtmlReportRenderer(self._plan.trialfolio_version)
        )
        manifest = self._build_manifest(error, created_at)
        data = _model_json(manifest)
        path = session_path(self._session, "manifest.json")
        try:
            self._manifest_file = self._store.write(path, data)
        except BaseException:
            try:
                self._store.discard(path, data)
            except TrialFolioError:
                self._manifest_left = True
            raise
        self._manifest = manifest
        _logger.log(
            logging.INFO if error is None else logging.WARNING,
            "Session %d ended %s: %s.",
            self._session,
            manifest.outcome,
            "no error" if error is None else error.code,
            extra=self._log_fields("experiment.session.ended"),
        )

    def _partial(self) -> TrialFolioError | None:
        """`execution.partial` when a planned case didn't succeed, with what happened to each,
        and why the session stopped, if it did."""
        missed = [case for case in self._cases if case.outcome != "succeeded"]
        if not missed:
            return None
        planned = len(self._cases)

        def listing(named: Callable[[_Case], str]) -> str:
            return "; ".join(f"{named(case)}, {_described(case)}" for case in missed)

        lead = f"{len(missed)} of the {planned} planned cases didn't succeed:"
        why = ""
        if self._stopped is not None:
            reason, error = self._stopped
            why = " " + _STOP_MESSAGES[reason]
            if error is not None:
                why += f" The error was {error.code}."
        charged = (
            " A case whose request may have reached Portfolio123 is never sent again"
            " automatically: a confirmed repeat sends it."
            if any(_awaiting_repeat(case) for case in missed)
            else ""
        )
        tail = f"{why}{charged} Every planned case is accounted for in the session's manifest."
        return TrialFolioError(
            "execution.partial",
            f"{lead} {listing(lambda c: f'`{c.case.case_key}`')}.{tail}",
            f"{lead} {listing(lambda c: c.case.case_id)}.{tail}",
        )

    def _build_manifest(
        self, error: TrialFolioError | None, created_at: datetime
    ) -> ExperimentManifest:
        artifacts = self._artifacts()
        if self._report is not None:
            artifacts = (*artifacts, self._listed("report", self._report))
        references: dict[str, ExternalReference] = {}
        for case in self._plan.cases:
            for row in case.settings:
                if "not_snapshotted" in row.flags:
                    references.setdefault(
                        row.setting, ExternalReference(setting=row.setting, snapshotted=False)
                    )
        series = any(
            isinstance(result.response, DecodedResponse) and holds_series(result.response.payload)
            for result in self._attempts
        )
        return ExperimentManifest(
            schema_version=SCHEMA_VERSION,
            artifact_type="experiment",
            trialfolio_version=self._plan.trialfolio_version,
            created_at=created_at,
            experiment_id=self._plan.experiment_id,
            session=self._session,
            command=self._command,
            synthetic=self._synthetic,
            plan=self._plan_number,
            plan_hash=self._plan.plan_hash,
            approval=self._approval,
            outcome="completed" if error is None else "partial",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            artifacts=artifacts,
            parsers=(
                ParserVersion(
                    layout=LAYOUT, layout_version=LAYOUT_VERSION, parser_version=PARSER_VERSION
                ),
            ),
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            capabilities=Capabilities(
                return_series="source_only" if series else "absent",
                statistical_validation="not_assessed",
                trading_readiness="not_assessed",
            ),
            reproducibility=Reproducibility(
                status="incomplete" if references else "complete",
                external_references=tuple(references.values()),
            ),
            counts=self._counts(),
        )

    def _counts(self) -> ExperimentManifestCounts:
        outcomes = [case.outcome for case in self._cases]
        records = [result.record for result in self._attempts]
        costs = [r.provider_metadata.cost for r in records if r.provider_metadata.cost is not None]
        budget = self._plan.budget
        return ExperimentManifestCounts(
            cases=CaseCounts(
                planned=len(outcomes),
                succeeded=outcomes.count("succeeded"),
                failed=outcomes.count("failed"),
                skipped=0,
                unknown=outcomes.count("unknown"),
                not_yet_run=outcomes.count("not_yet_run"),
            ),
            retired_cases=0,
            attempts=ExperimentAttemptCounts(
                succeeded=sum(r.outcome == "succeeded" for r in records),
                failed=sum(r.outcome == "failed" for r in records),
                unknown=sum(r.outcome == "unknown" for r in records),
                running=0,
                repeats=sum(r.repeat_of is not None for r in records),
            ),
            retries=0,
            provider_requests=self._provider_requests(),
            authentication_calls=self._authentication_calls(),
            budget=BudgetLimits(
                provider_requests=budget.provider_requests,
                authentication_calls=budget.authentication_calls,
            ),
            cost=sum(costs) if costs else None,
        )

    def _provider_requests(self) -> int:
        """The sends counted against the budget: each that may have reached Portfolio123."""
        return sum(provider_requests(result.record) for result in self._attempts)

    def _authentication_calls(self) -> int:
        """Trial Folio's own authentication calls counted against the budget, whatever their
        result: an attempt's `POST /auth` exchange, or its authentication record alone."""
        return sum(_authentication_calls(result) for result in self._attempts)

    def _experiment_record(self) -> ExperimentRecord:
        if self._record is None:  # written before any case runs
            raise RuntimeError("the plan is recorded before the session ends")
        return self._record

    def _artifacts(self) -> tuple[ExperimentArtifact, ...]:
        """Each file of the experiment's records so far, as the manifest lists it, apart from
        the report: the plan's files, each attempt's, each case's tables, and the session's
        record."""
        listed = [self._listed(role, stored) for role, stored in self._plan_files]
        tables = {case.case.case_id: case.tables for case in self._cases}
        for result in self._attempts:
            listed.extend(self._attempt_file(file, result.record) for file in result.files)
            case_tables = tables.get(result.record.case_id)
            if case_tables is not None and result.record.outcome == "succeeded":
                listed.append(self._listed("metrics", case_tables.metrics))
                listed.append(self._listed("settings", case_tables.settings))
        if self._session_record is not None:
            listed.append(self._listed("session_record", self._session_record))
        return tuple(listed)

    def _attempt_file(self, file: AttemptFile, record: AttemptRecordV1_1) -> ExperimentArtifact:
        role: ExperimentArtifactRole = file.role
        source = None
        if role in ("provider_request", "provider_response", "provider_response_undecoded"):
            decoded = role == "provider_response"
            source = SourceRecord(
                # The request was written just before the attempt's start record, and the
                # response was saved just before its attempt record.
                acquired_at=record.started_at if role == "provider_request" else record.ended_at,
                format=LAYOUT if decoded else f"{LAYOUT}-{role.removeprefix('provider_')}",
                format_version=str(LAYOUT_VERSION),
                parser_version=PARSER_VERSION if decoded else None,
                provenance="verified",
                operation="screen_backtest",
            )
        return self._listed(role, file.file, source)

    def _listed(
        self,
        role: ExperimentArtifactRole,
        stored: StoredFile,
        source: SourceRecord | None = None,
    ) -> ExperimentArtifact:
        schema_version = _SCHEMA_VERSIONS.get(role)
        if role == "configuration":
            record = self._experiment_record()
            schema_version = self._configuration_version
            # Acquired when its plan was recorded, so every session's manifest gives it the
            # same time: the plan's `experiment.json` records when.
            source = SourceRecord(
                acquired_at=record.created_at,
                format=EXPERIMENT_CONFIGURATION_FORMAT,
                format_version=schema_version,
                parser_version=None,
                provenance="user_supplied",
                operation=None,
            )
        return ExperimentArtifact(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=role,
            schema_version=schema_version,
            source=source,
        )

    # Endings without a manifest

    def _before_cases(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped before its first case: nothing was sent. Its
        directory can be resumed only once its first plan's `experiment.json` is written, which
        an interrupt may have stopped just after the store published it."""
        if self._record is None and self._record_data:
            try:
                published = self._store.read(plan_path(1, "experiment.json")) == self._record_data
            except OSError:
                published = False
            if not published:
                return self._unrecorded(failure)
        elif self._record is None:
            return self._unrecorded(failure)
        detail = (
            "Nothing was sent. The session has no manifest, so the experiment's output reads as"
            " incomplete until running the same command again resumes it."
        )
        return TrialFolioError(
            failure.code, f"{failure.message} {detail}", f"{failure.log_message} {detail}"
        )

    def _unrecorded(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped before its first plan was recorded."""
        detail = (
            "Nothing was sent. The experiment's first plan wasn't recorded, so its output"
            " directory can't be resumed: remove the directory, and run the command again."
        )
        return TrialFolioError(
            failure.code, f"{failure.message} {detail}", f"{failure.log_message} {detail}"
        )

    def _incomplete(self, failure: TrialFolioError) -> TrialFolioError:
        """The error of a session that stopped without its manifest, with what its records say."""
        detail = self.ending_detail()
        if failure.message.endswith(detail):
            return failure
        return TrialFolioError(
            failure.code, f"{failure.message} {detail}", f"{failure.log_message} {detail}"
        )

    def _attempt_detail(self) -> str:
        current = self._current
        if current is not None and current.start_record is not None:
            return (
                "The screen backtest request of the attempt under way may have been sent, and may"
                " have been charged: its start record reads as running. Trial Folio never"
                " retries it automatically."
            )
        if self._attempts:
            last = self._attempts[-1]
            record = last.record
            if not last.recorded:
                if last.start is not None:
                    return (
                        "The screen backtest request of the last attempt may have been sent, and"
                        " may have been charged: its start record reads as running. Trial Folio"
                        " never retries it automatically."
                    )
                return "The last attempt's request wasn't sent."
            detail = request_detail(record.outcome, possibly_charged=record.possibly_charged)
            return f"Of the last attempt: {detail}"
        return "No case's request was sent."

    def _manifest_detail(self) -> str:
        if self._manifest is not None:
            return "The session's manifest was written, so the experiment's output is complete."
        if self._manifest_left:
            return (
                "The session's manifest.json was published before the failure, and couldn't be"
                " removed, so the experiment reads as complete although the run failed."
            )
        return (
            "The attempts recorded so far are kept. The session has no manifest, so the"
            " experiment's output reads as incomplete until running the same command again"
            " resumes it."
        )

    # Progress and logs

    def _emit(self, event: ProgressEvent) -> None:
        if self._progress is not None:
            self._progress(event)

    def _log_fields(self, event: str, case_id: str | None = None) -> dict[str, str]:
        fields = {"event": event, "plan_hash": self._plan.plan_hash}
        if case_id is not None:
            fields["case_id"] = case_id
        return fields


_STOPS: Final[dict[StopReason, str]] = {
    "budget": "the budget can't cover the next case",
    "authentication": "Trial Folio's own authentication call failed",
    "quota": "a request got provider.quota_exceeded",
    "cancelled": "the run was cancelled",
}
"""Why no later case starts, for the log."""

_STOP_MESSAGES: Final[dict[StopReason, str]] = {
    "budget": (
        "The experiment's budget couldn't cover the next case, so it and the cases after it"
        " weren't started. A revision that raises budget.provider_requests lets them run."
    ),
    "authentication": (
        "Trial Folio's own authentication call failed, so no later case started: each would"
        " have failed the same way. Once the cause is fixed, running the same command again"
        " resumes the experiment, and runs the cases not started."
    ),
    "quota": (
        "Portfolio123 refused a request because the account's API quota or credits are"
        " exhausted, so no later case started: each would have been refused the same way. Once"
        " the account has credits again, running the same command again resumes the"
        " experiment, and runs the cases not started."
    ),
    "cancelled": (
        "The run was cancelled, so no later case started. Running it again, approved by the"
        " same hash, resumes the experiment, and runs the cases not started."
    ),
}


def _described(case: _Case) -> str:
    outcome = case.outcome
    if outcome == "not_yet_run":
        return "not yet run"
    if case.invalid is not None:
        return f"failed ({case.invalid.code})"
    error = None if case.result is None else case.result.record.error
    return outcome if error is None else f"{outcome} ({error.code})"


def _awaiting_repeat(case: _Case) -> bool:
    """Whether the case awaits a repeat: its attempt may have reached Portfolio123, and didn't
    succeed. One whose response failed validation succeeded, so it's complete."""
    if case.result is None:
        return False
    record = case.result.record
    return record.possibly_charged and record.outcome != "succeeded"


def _authentication_calls(result: ExperimentAttemptResult) -> int:
    """An attempt's authentication calls: the `POST /auth` exchanges its attempt record holds,
    or one when its authentication record was written and the attempt record wasn't."""
    if result.recorded:
        return sum(e.request == AUTHENTICATION_REQUEST for e in result.record.exchanges)
    return int(result.authenticated)


def _model_json(model: BaseModel) -> bytes:
    return (model.model_dump_json(indent=2) + "\n").encode("utf-8")


def _utc(moment: datetime) -> datetime:
    if moment.utcoffset() != timedelta(0):
        raise ValueError("the clock must give UTC times")
    return moment
