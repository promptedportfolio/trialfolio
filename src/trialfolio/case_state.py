"""The rules of a case's state and outcome, and the experiment's counts, which the reader of an
experiment's records, the executor, and the plan display share (docs/contracts.md, running an
experiment: the cases that are due; repeating a case; and the experiment manifest's counts).

Each function reads a case's attempts, or the experiment's, by session and then sequence, as
both kinds of attempt hold them: `SavedExperimentAttempt`, in `experiment_records.py`, an
attempt as the records read it, and the executor's own, to which each attempt of its session is
added as it ends. So a case's latest attempt is its last. An attempt without its attempt record
reads as the resume's step 8 will record it, or, for one of the executor's session, as `running`,
which a case's outcome counts as `unknown`. An attempt whose outcome is None is one of the
executor's session that left no record: it counts only for the budget.

Nothing here writes, sends, or logs.
"""

import uuid
from collections.abc import Container, Mapping, Sequence
from typing import Final, Literal, Protocol

from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.experiment_manifest import (
    BudgetLimits,
    CaseCounts,
    ExperimentAttemptCounts,
    ExperimentManifestCounts,
)
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.contracts.tables import MetricsRow

type CaseOutcome = Literal["succeeded", "failed", "unknown", "not_yet_run"]
type CaseState = Literal["complete", "due", "awaiting_repeat"]

_INVALID_RESPONSE: Final = "provider.response_invalid"
"""The error code that gives the outcome of a case whose succeeded attempt's response failed
validation."""


class _CaseAttempt(Protocol):
    """What a case's state and outcome read of one of its attempts. Its `outcome` is `running`
    for a start record without an attempt record, and None for an attempt that left no record."""

    @property
    def attempt_id(self) -> uuid.UUID: ...
    @property
    def outcome(self) -> Literal["running", "succeeded", "failed", "unknown"] | None: ...
    @property
    def possibly_charged(self) -> bool: ...
    @property
    def error_code(self) -> str | None: ...


class _CountedAttempt(_CaseAttempt, Protocol):
    """What the experiment's counts read of one of its attempts, besides its case's rules: its
    `provider_requests` and `authentication_calls` are those the budget counts, and its `record`
    is its attempt record, once it's written."""

    @property
    def case_id(self) -> str: ...
    @property
    def repeat_of(self) -> uuid.UUID | None: ...
    @property
    def provider_requests(self) -> int: ...
    @property
    def authentication_calls(self) -> int: ...
    @property
    def record(self) -> AttemptRecordV1_1 | None: ...


# A case's state and outcome


def case_state(attempts: Sequence[_CaseAttempt]) -> CaseState:
    """`complete` when one of the case's attempts succeeded; `awaiting_repeat` when one is
    possibly charged and none succeeded, so only a confirmed repeat sends it; and `due`
    otherwise, so a resume sends it. One whose response failed validation succeeded, so it's
    complete."""
    if any(attempt.outcome == "succeeded" for attempt in attempts):
        return "complete"
    if any(attempt.possibly_charged for attempt in attempts):
        return "awaiting_repeat"
    return "due"


def case_outcome(attempts: Sequence[_CaseAttempt], *, valid: bool) -> CaseOutcome:
    """The case's outcome, as the manifest counts it: `succeeded` when one of its attempts
    succeeded, and `failed` when its response failed validation, as `valid` gives; otherwise the
    outcome of its latest possibly charged attempt, with a `running` one counted as `unknown`;
    `failed` when it has attempts and none is possibly charged; and `not_yet_run` when it has
    none."""
    made = [attempt for attempt in attempts if attempt.outcome is not None]
    if any(attempt.outcome == "succeeded" for attempt in made):
        return "succeeded" if valid else "failed"
    latest = latest_charged(made)
    if latest is not None:
        return "failed" if latest.outcome == "failed" else "unknown"
    return "failed" if made else "not_yet_run"


def latest_charged[A: _CaseAttempt](attempts: Sequence[A]) -> A | None:
    """The case's latest possibly charged attempt, whose `attempt_id` confirms a repeat of it."""
    charged = [attempt for attempt in attempts if attempt.possibly_charged]
    return charged[-1] if charged else None


def described_by[A: _CaseAttempt](attempts: Sequence[A]) -> A | None:
    """The attempt whose error describes a case that didn't succeed: its latest possibly charged
    attempt, or else its latest attempt."""
    made = [attempt for attempt in attempts if attempt.outcome is not None]
    latest = latest_charged(made)
    if latest is not None:
        return latest
    return made[-1] if made else None


def outcome_code(attempts: Sequence[_CaseAttempt], *, valid: bool) -> str | None:
    """The error code that gives the case's outcome: `provider.response_invalid` when its
    response failed validation, as `valid` gives, or else the error code of the attempt that
    describes it."""
    if not valid:
        return _INVALID_RESPONSE
    attempt = described_by(attempts)
    return None if attempt is None else attempt.error_code


def described(attempts: Sequence[_CaseAttempt], *, valid: bool) -> str:
    """The case's outcome, with the error code that gives it, or `not yet run`."""
    outcome = case_outcome(attempts, valid=valid)
    if outcome == "not_yet_run":
        return "not yet run"
    code = outcome_code(attempts, valid=valid)
    return outcome if code is None else f"{outcome} ({code})"


# Repeats


def repeatable(attempt: _CaseAttempt) -> bool:
    """Whether a repeat may name the attempt: its request may have been charged, and it didn't
    succeed (repeating a case)."""
    return attempt.possibly_charged and attempt.outcome != "succeeded"


def confirmation_used(attempts: Sequence[_CaseAttempt], attempt_id: uuid.UUID | None) -> bool:
    """Whether the confirmation of a repeat that names the case's attempt `attempt_id` is used:
    a later attempt of the case may have reached Portfolio123. A key alone names no attempt, so
    it has none to use."""
    named = [index for index, attempt in enumerate(attempts) if attempt.attempt_id == attempt_id]
    return bool(named) and any(attempt.possibly_charged for attempt in attempts[named[0] + 1 :])


# The experiment's counts


def experiment_counts(
    plan: PlanV1_1,
    attempts: Sequence[_CountedAttempt],
    *,
    invalid: Container[str],
    retired: int,
) -> ExperimentManifestCounts:
    """The experiment's counts, as its manifest gives them, over `plan`: each planned case by its
    outcome, with `invalid` holding the `case_id` of each whose response failed validation;
    `retired`, how many cases revisions retired; every attempt of the experiment, a retired
    case's included, by its outcome, and the repeats; the sends and authentication calls the
    budget counts, beside the plan's budget; and the credits Portfolio123 reported."""
    outcomes = [
        case_outcome(
            [attempt for attempt in attempts if attempt.case_id == case.case_id],
            valid=case.case_id not in invalid,
        )
        for case in plan.cases
    ]
    made = [attempt for attempt in attempts if attempt.outcome is not None]
    records = [attempt.record for attempt in made if attempt.record is not None]
    costs = [r.provider_metadata.cost for r in records if r.provider_metadata.cost is not None]
    return ExperimentManifestCounts(
        cases=CaseCounts(
            planned=len(outcomes),
            succeeded=outcomes.count("succeeded"),
            failed=outcomes.count("failed"),
            skipped=0,
            unknown=outcomes.count("unknown"),
            not_yet_run=outcomes.count("not_yet_run"),
        ),
        retired_cases=retired,
        attempts=ExperimentAttemptCounts(
            succeeded=sum(a.outcome == "succeeded" for a in made),
            failed=sum(a.outcome == "failed" for a in made),
            unknown=sum(a.outcome == "unknown" for a in made),
            running=sum(a.outcome == "running" for a in made),
            repeats=sum(a.repeat_of is not None for a in made),
        ),
        retries=0,
        provider_requests=sum(attempt.provider_requests for attempt in attempts),
        authentication_calls=sum(attempt.authentication_calls for attempt in attempts),
        budget=BudgetLimits(
            provider_requests=plan.budget.provider_requests,
            authentication_calls=plan.budget.authentication_calls,
        ),
        cost=sum(costs) if costs else None,
    )


def unavailable_metrics(plan: PlanV1_1, metrics: Mapping[str, Sequence[MetricsRow]]) -> int:
    """The `unavailable` rows of the planned cases' `metrics.csv` files, given each case's rows
    by its `case_id`: the JSON summary's `metrics_unavailable`."""
    return sum(
        row.availability == "unavailable"
        for case in plan.cases
        for row in metrics.get(case.case_id, ())
    )
