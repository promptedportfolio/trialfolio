"""What a run of an experiment's configuration builds, before its approval: `ExperimentRun`, with
the `--repeat` options as given, which the display, the approval, and the confirmation of the
repeats each read.
"""

import uuid
from dataclasses import dataclass

from trialfolio.approval import NOTHING_CREATED
from trialfolio.case_state import confirmation_used
from trialfolio.contracts.experiment_plan import (
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanV1_1,
    PlanV1_3,
)
from trialfolio.contracts.experiment_record import PlanChanges, PlanChangesV1_1, RetiredCaseV1_1
from trialfolio.contracts.ranking_snapshot import RankingSnapshotRecord
from trialfolio.experiment_records import (
    SavedCase,
    SavedExperiment,
    SavedExperimentAttempt,
    SavedRankingCase,
)
from trialfolio.planning import retired_cases_v1_1

type AnySavedCase = SavedCase | SavedRankingCase
"""A case of the plan, 1.1.0's or 1.3.0's, and what the experiment's records say of it."""


@dataclass(frozen=True)
class RepeatOption:
    """A `--repeat` as given: a case key, and the attempt whose possible charge it acknowledges,
    or None when the CLI is to ask."""

    case_key: str
    attempt_id: uuid.UUID | None


@dataclass(frozen=True)
class ExperimentRun:
    """What a run of an experiment's configuration builds, before its approval: the plan, and,
    for a resume, the experiment's records, with what changed when the plan revises the current
    one. `reason` and `repeats` are `--revision-reason` and `--repeat`, as given."""

    plan: PlanV1_1 | PlanV1_3
    experiment: SavedExperiment | None
    changes: PlanChanges | PlanChangesV1_1 | None
    """What the plan changed from the current plan; None for a new experiment, or when the plan
    is the current plan, which the run resumes."""
    reason: str | None
    repeats: tuple[RepeatOption, ...]
    snapshot: RankingSnapshotRecord | None = None
    """The record of the snapshot the baseline's ranking names, for a plan 1.3.0 whose
    `ranking_source` is a snapshot, which the full display gives as the definition's source."""

    @property
    def revision(self) -> bool:
        return self.changes is not None

    @property
    def requests_per_case(self) -> int:
        """The requests each attempt sends: a `rank_update` and a backtest for a plan with a
        ranking definition, and a backtest alone otherwise."""
        return 2 if isinstance(self.plan, PlanV1_3) else 1

    @property
    def cases(self) -> tuple[AnySavedCase, ...]:
        """Each case of the plan, in its order, with what the records say of it."""
        plan = self.plan
        if self.experiment is None:
            if isinstance(plan, PlanV1_3):
                return tuple(SavedRankingCase(case, (), True) for case in plan.cases)
            return tuple(SavedCase(case, (), True) for case in plan.cases)
        if isinstance(plan, PlanV1_3):
            return self.experiment.cases(plan)
        return self.experiment.cases(plan)

    @property
    def retired(self) -> tuple[RetiredCaseV1_1, ...]:
        """The experiment's retired cases once the plan is its current plan."""
        if self.experiment is None:
            return ()
        return retired_cases_v1_1(self.experiment.current.record, self.plan)

    @property
    def provider_requests(self) -> int:
        """The sends counted against the budget so far, across every run of the experiment."""
        return 0 if self.experiment is None else self.experiment.provider_requests

    @property
    def authentication_calls(self) -> int:
        return 0 if self.experiment is None else self.experiment.authentication_calls

    @property
    def remaining_requests(self) -> int:
        """The provider requests the budget leaves, after those counted so far."""
        return max(0, self.plan.budget.provider_requests - self.provider_requests)

    @property
    def nothing_done(self) -> str:
        """What a run that stops before its approval leaves: no output, for a new experiment,
        and the records as they were, for a resume."""
        if self.experiment is None:
            return NOTHING_CREATED
        return "Nothing was sent or written."

    def awaiting_repeat(self) -> list[tuple[AnySavedCase, SavedExperimentAttempt]]:
        """Each case of the plan awaiting a repeat, with its latest possibly charged attempt,
        whose `attempt_id` confirms the repeat."""
        return [
            (saved, attempt)
            for saved in self.cases
            if saved.state == "awaiting_repeat" and (attempt := saved.latest_charged) is not None
        ]

    def sends(self) -> list[ExperimentPlanCase | ExperimentPlanCaseV1_3]:
        """The cases this run would send, in the plan's order, as the core picks them: each
        that's due, and each awaiting a repeat that `--repeat` names, by its key alone or with
        an attempt ID whose confirmation isn't used. A used one repeats nothing (repeating a
        case)."""
        named = {option.case_key: option.attempt_id for option in self.repeats}
        return [
            saved.case
            for saved in self.cases
            if saved.state == "due"
            or (
                saved.state == "awaiting_repeat"
                and saved.case.case_key in named
                and not confirmation_used(saved.attempts, named[saved.case.case_key])
            )
        ]

    def uncovered(self) -> list[ExperimentPlanCase | ExperimentPlanCaseV1_3]:
        """The cases this run would send that the remaining budget can't cover, in the plan's
        order, each with its requests: two for a case with a ranking definition, whose attempt
        starts only when both fit. The run authenticates before its first send, so with no
        authentication call left, it covers none."""
        sends = self.sends()
        if self.authentication_calls >= self.plan.budget.authentication_calls:
            return sends
        return sends[self.remaining_requests // self.requests_per_case :]

    def sends_a_case(self) -> bool:
        """Whether this run would send a case: one is due, or to be repeated, and the remaining
        budget covers the first of them. A run that sends none doesn't write `ApiRankingSystem`,
        and needs no credentials."""
        return len(self.sends()) > len(self.uncovered())

    def counted_credits(self) -> int | None:
        """For a plan with a ranking definition, the most the requests counted so far can have
        cost, each at its operation's documented cost in the plan: an attempt that sends a
        definition counts its `rank_update` first, and then its backtest, and any other attempt's
        requests are backtests. None for any other plan (plans with a ranking definition, the
        display)."""
        plan = self.plan
        if not isinstance(plan, PlanV1_3):
            return None
        rank_update, backtest = plan.budget.costs
        total = 0
        for attempt in () if self.experiment is None else self.experiment.attempts:
            sent = attempt.provider_requests
            if attempt.version == "1.3.0":
                total += min(sent, 1) * rank_update.credits_per_request
                total += max(0, sent - 1) * backtest.credits_per_request
            else:
                total += sent * backtest.credits_per_request
        return total


def repeat_option(saved: AnySavedCase, attempt: SavedExperimentAttempt) -> str:
    """The exact `--repeat` that repeats the case awaiting a repeat, by its latest possibly
    charged attempt."""
    return f"--repeat {saved.case.case_key}:{attempt.attempt_id}"
