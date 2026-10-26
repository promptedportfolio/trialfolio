"""The case runner of an experiment's session: which cases it sends, and their attempts, one at a
time, with one client (docs/contracts.md, running an experiment, the executor, the budget across
runs, repeating a case, and sending a definition).

`CaseRunner` runs each case to send in the plan's order: every case of a new experiment, and, in
a resume, each case that's due, and each awaiting a repeat that a confirmed repeat names. Before
each attempt, it checks the cancellation, and that the budget, which counts every attempt of the
experiment, covers its requests, and an authentication call when it authenticates; the case
that can't start, and every case after it, isn't started. So it is after Trial Folio's own
authentication call fails, or after a request gets `provider.quota_exceeded`, since every later
case would end the same way (D-32). The session's attempts share its client, so one sends with
the token an earlier attempt obtained, until a 401 or 403 drops it.

After each attempt, the writer of the session's records writes its case's tables. An attempt
whose attempt record wasn't written, or that an interrupt or a storage failure ended, ends the
session, and the runner returns its error.
"""

import logging
import uuid
from collections.abc import Sequence
from typing import Final, Literal

from trialfolio.attempts import (
    ExperimentAttempt,
    ExperimentAttemptResult,
    RankingExperimentAttempt,
)
from trialfolio.case_state import counted_authentications, counted_requests
from trialfolio.contracts.experiment_plan import (
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanV1_1,
    PlanV1_3,
)
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution.authorization import Authorization
from trialfolio.experiment_execution.context import SessionContext
from trialfolio.experiment_execution.ledger import Ledger
from trialfolio.experiment_execution.progress import (
    AttemptEnded,
    AttemptStarted,
    Cancellation,
    Progress,
    emit,
)
from trialfolio.experiment_execution.records import SessionRecords
from trialfolio.experiment_records import AnyPlanCase
from trialfolio.manifests import ends_without_manifest
from trialfolio.pause import Pause
from trialfolio.provider import ScreenBacktestClient

_logger = logging.getLogger("trialfolio.experiment_execution")

type StopReason = Literal["budget", "authentication_budget", "authentication", "quota", "cancelled"]

type Send = tuple[AnyPlanCase, uuid.UUID | None]
"""A case the session sends, with the attempt a repeat of it repeats, or None."""

_STOPS: Final[dict[StopReason, str]] = {
    "budget": "the budget can't cover the next case",
    "authentication_budget": "the budget's authentication calls are spent",
    "authentication": "Trial Folio's own authentication call failed",
    "quota": "a request got provider.quota_exceeded",
    "cancelled": "the run was cancelled",
}
"""Why no later case starts, for the log."""


class CaseRunner:
    """Runs the session's cases, and keeps what an interface reads of them: each attempt that
    ended, the attempt under way, and why the session stopped before its last case, if it
    did."""

    def __init__(
        self,
        context: SessionContext,
        ledger: Ledger,
        records: SessionRecords,
        client: ScreenBacktestClient,
        authorization: Authorization,
        *,
        pause: Pause,
        progress: Progress | None,
        cancellation: Cancellation | None,
    ) -> None:
        self._context = context
        self._ledger = ledger
        self._records = records
        self._client = client
        self._authorization = authorization
        self._pause = pause
        self._progress = progress
        self._cancellation = cancellation
        self.results: list[ExperimentAttemptResult] = []
        """Each attempt that ended in this session, in order."""
        self.current: ExperimentAttempt | RankingExperimentAttempt | None = None
        """The attempt under way."""
        self.stopped: tuple[StopReason, TrialFolioError | None] | None = None
        """Why no later case started, and the error that stopped them, if any."""

    def sends(self) -> list[Send]:
        """The cases this session sends, in the plan's order, each with the attempt a repeat of
        it repeats, as `to_send` gives them, once the repeats whose confirmation is used are
        logged."""
        for repeat in self._authorization.used:
            _logger.info(
                "The case isn't repeated: the repeat confirmed for its attempt %s was made"
                " already.",
                repeat.attempt_id,
                # The CLI says so on stderr itself, by the case's key, before the session starts.
                extra={
                    **self._context.log_fields("experiment.repeat.used", repeat.case_id),
                    "terminal": False,
                },
            )
        return self.to_send()

    def to_send(self) -> list[Send]:
        """The cases this session sends, in the plan's order, each with the attempt a repeat of
        it repeats: every case of a new experiment; and in a resume, each case that's due, and
        each awaiting a repeat that a confirmed repeat names."""
        plan, experiment = self._context.plan, self._context.experiment
        if experiment is None:
            return [(case, None) for case in plan.cases]
        sends: list[Send] = []
        for saved in experiment.cases(plan):
            repeat = self._authorization.repeats.get(saved.case.case_id)
            if saved.state == "due":
                sends.append((saved.case, None))
            elif saved.state == "awaiting_repeat" and repeat is not None:
                sends.append((saved.case, repeat.attempt_id))
        return sends

    def stop_before(self, authenticates: bool) -> StopReason | None:
        """Why the next attempt can't start, if it can't: a cancellation, or a budget that
        doesn't cover one more case's requests, one or, for a case with a ranking definition, two
        (sending a definition), or one more authentication call when it authenticates. The
        budget counts every attempt of the experiment, earlier sessions' included."""
        if self._cancellation is not None and self._cancellation.requested:
            return "cancelled"
        plan, attempts = self._context.plan, self._ledger.attempts
        budget = plan.budget
        sends = 2 if isinstance(plan, PlanV1_3) else 1
        if counted_requests(attempts) + sends > budget.provider_requests:
            return "budget"
        if authenticates and counted_authentications(attempts) + 1 > budget.authentication_calls:
            return "authentication_budget"
        return None

    def run(self, sends: Sequence[Send]) -> TrialFolioError | None:
        """Runs each case to send in the plan's order, until one can't start. Returns the error
        of an attempt that an interrupt or a storage failure ended, or whose attempt record
        wasn't written, which ends the session."""
        token_from: uuid.UUID | None = None
        for place, (case, repeat_of) in enumerate(sends, 1):
            stop = self.stop_before(token_from is None)
            if stop is not None:
                self._stop(stop, None)
                break
            attempt = self._start(case, repeat_of, place, len(sends))
            result = attempt.run(self._client, token_from)
            self.current = None
            self.results.append(result)
            self._ledger.record_ended(result)
            if ends_without_manifest(recorded=result.recorded, error=result.error):
                return result.error
            self._records.write_tables(case, result)
            record = result.record
            emit(
                self._progress,
                AttemptEnded(
                    case.case_id, attempt.attempt_id, record.outcome, record.possibly_charged
                ),
            )
            token_from = self._token_after(attempt.attempt_id, result, token_from)
            stop = self._stop_after(result) if place < len(sends) else None
            if stop is not None:
                self._stop(stop, result.error)
                break
        return None

    def _start(
        self, case: AnyPlanCase, repeat_of: uuid.UUID | None, place: int, cases: int
    ) -> ExperimentAttempt | RankingExperimentAttempt:
        """Starts the session's next attempt, of `case`, its `place` of `cases`, once it's
        logged, and tells the caller."""
        _logger.info(
            "Case %d of %d this session: %s.",
            place,
            cases,
            case.case_id,
            extra=self._context.log_fields("experiment.case.started", case.case_id),
        )
        if repeat_of is not None:
            _logger.info(
                "Repeating the case's request, as confirmed for its attempt %s.",
                repeat_of,
                extra=self._context.log_fields("experiment.repeat.started", case.case_id),
            )
        attempt = self._new_attempt(case, repeat_of)
        self.current = attempt
        emit(self._progress, AttemptStarted(case.case_id, attempt.attempt_id))
        return attempt

    def _new_attempt(
        self, case: AnyPlanCase, repeat_of: uuid.UUID | None
    ) -> ExperimentAttempt | RankingExperimentAttempt:
        """The next attempt of the session, of `case`: one that sends the case's definition,
        then its backtest, under a plan 1.3.0, and one that sends its backtest otherwise."""
        context = self._context
        plan = context.plan
        # The session starts its attempts one at a time, so this is its next one.
        sequence = len(self.results) + 1
        if isinstance(plan, PlanV1_3) and isinstance(case, ExperimentPlanCaseV1_3):
            return RankingExperimentAttempt(
                plan,
                case,
                context.store,
                session=context.session,
                sequence=sequence,
                repeat_of=repeat_of,
                clock=context.clock,
                synthetic=context.synthetic,
                pause=self._pause,
            )
        if isinstance(plan, PlanV1_1) and isinstance(case, ExperimentPlanCase):
            return ExperimentAttempt(
                plan,
                case,
                context.store,
                session=context.session,
                sequence=sequence,
                repeat_of=repeat_of,
                clock=context.clock,
                synthetic=context.synthetic,
            )
        raise TypeError("a case is one of its plan's")

    def _token_after(
        self, attempt_id: uuid.UUID, result: ExperimentAttemptResult, token_from: uuid.UUID | None
    ) -> uuid.UUID | None:
        """The attempt whose authentication gave the token the next attempt sends with, or None
        when the client holds none, after the attempt `attempt_id` ended with `result`."""
        if not self._client.authenticated:
            return None
        if result.authenticated and not result.authentication_failed:
            return attempt_id
        return token_from

    def _stop_after(self, result: ExperimentAttemptResult) -> StopReason | None:
        """Why no later case starts after an attempt that ended with `result`, if none does:
        every later case would end the same way (D-32)."""
        if result.authentication_failed:
            return "authentication"
        error = result.record.error
        if error is not None and error.code == "provider.quota_exceeded":
            return "quota"
        return None

    def _stop(self, reason: StopReason, error: TrialFolioError | None) -> None:
        self.stopped = (reason, error)
        _logger.warning(
            "No later case starts: %s.",
            _STOPS[reason],
            extra=self._context.log_fields("experiment.stopped"),
        )
