"""An experiment's plan display: the full plan, for a terminal, and the summary, which holds
nothing from the configuration. Each section of the full plan is a function of its own.
"""

from trialfolio.approval import (
    APPROVE_ANSWER,
    FULL_PLAN_HINT,
    OVERWRITES,
    SENDS_NO_CASE,
    budget_lines,
    counted,
    data_sent_lines,
    how_to_approve,
    most_credits,
    ranking_lines,
    request_lines,
    retry_lines,
    setting_lines,
    shown,
)
from trialfolio.case_state import case_outcome, described, invalid_success
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3, PlanVariant, PlanVariantV1_3
from trialfolio.contracts.experiment_record import PlanChanges, PlanChangesV1_1
from trialfolio.display import visible
from trialfolio.experiment_approval.run import AnySavedCase, ExperimentRun, repeat_option
from trialfolio.experiment_records import SavedExperiment, SavedRankingCase
from trialfolio.planning import plan_hash


def format_experiment_plan(run: ExperimentRun) -> str:
    """The full display of an experiment's plan: the research context; for a revision, what
    changed and the reason; the baseline's settings with their expected provenance and markings;
    every case with its key, `case_id`, change, description, and request exactly as it will be
    sent, and, for a resume, its outcome so far, with the option that repeats a case awaiting a
    repeat; the retired cases; the budget, with what's counted and what remains; the retry
    policy; the data sent; and the plan hash with how to approve it. It holds configuration
    values, so it's for a terminal only, never a log."""
    plan = run.plan
    shown_hash = plan_hash(plan)
    lines = [f"Experiment plan {shown_hash}", "", *_context_lines(plan), *_progress_lines(run)]
    if isinstance(plan, PlanV1_3):
        sends = run.experiment is None or run.sends_a_case()
        lines += ["", *ranking_lines(plan.ranking_source, run.snapshot, sends=sends)]
    lines += ["", "The baseline's settings, with the provenance each value will have once sent:"]
    for row in plan.cases[0].settings:
        lines += setting_lines(row)
    lines += _case_lines(run)
    if run.experiment is not None:
        lines += _retired_lines(run, run.experiment)
    lines += ["", *budget_lines(plan.budget), *_counted_lines(run)]
    lines += ["", *retry_lines(plan.retry_policy), ""]
    lines += data_sent_lines(
        plan.data_sent,
        "the experiment's ID, title, purpose, or prior research, a case's key or description, a"
        " revision's reason, data_vendor, the configuration file, file paths",
    )
    lines += ["", f"Plan hash: {shown_hash}", _how_to_approve(run)]
    return "\n".join(lines) + "\n"


def _context_lines(plan: PlanV1_1 | PlanV1_3) -> list[str]:
    """The experiment's research context: its ID, title, purpose, and prior research."""
    declared = plan.prior_research
    description = "" if declared.description is None else f" {shown(declared.description)}"
    return [
        f"Experiment: {plan.experiment_id}",
        f"Title: {shown(plan.title)}",
        f"Purpose: {shown(plan.purpose)}",
        f"Prior research, as declared: {declared.status}.{description}",
        "  Trial Folio can't verify the declaration.",
    ]


def _progress_lines(run: ExperimentRun) -> list[str]:
    """For a revision, what it changed from the current plan, and the reason; for a resume, that
    the plan is the current plan. Nothing for a new experiment."""
    experiment = run.experiment
    if experiment is None:
        return []
    current = experiment.current
    if run.changes is None:
        return [
            "",
            f"This is the experiment's current plan, plan {current.number}, which this run resumes.",
        ]
    reason = (
        "none given. A revision needs one, with --revision-reason."
        if run.reason is None
        else shown(run.reason)
    )
    return [
        "",
        (
            f"This plan revises the experiment's current plan, plan {current.number}"
            f" ({current.plan.plan_hash}). What changed:"
        ),
        *_changes_lines(run.changes),
        f"Reason for the revision: {reason}",
    ]


def _changes_lines(changes: PlanChanges | PlanChangesV1_1) -> list[str]:
    lines = [
        f"  {change.package} from {change.previous} to {change.current}"
        for change in changes.versions
    ]
    for cases, verb in ((changes.cases_added, "added"), (changes.cases_retired, "retired")):
        if cases:
            named = ", ".join(f"{case.case_key} ({case.case_id})" for case in cases)
            lines.append(f"  Cases {verb}: {named}")
    if changes.parts:
        lines.append(f"  Other parts changed: {', '.join(changes.parts)}")
    return lines


def _case_lines(run: ExperimentRun) -> list[str]:
    """Each case, in the order it runs: its key, `case_id`, change, and description; for a
    resume, its outcome so far; and its requests, exactly as they'll be sent."""
    lines = [
        "",
        (
            f"The {len(run.plan.cases)} cases, in the order they run. Each is the baseline with"
            " exactly its change:"
        ),
    ]
    for saved in run.cases:
        case = saved.case
        lines += ["", f"Case {case.case_key} ({case.case_id}): {_change(case.variant)}"]
        if case.description is not None:
            lines.append(f"  Description: {shown(case.description)}")
        if run.experiment is not None:
            lines.append(f"  So far: {_so_far(saved)}")
        lines += request_lines(case.requests, "  ")
    return lines


def _change(variant: PlanVariant | PlanVariantV1_3 | None) -> str:
    if variant is None:
        return "the baseline"
    if isinstance(variant, PlanVariantV1_3) and variant.setting == "ranking":
        weights = ", ".join(
            f"{visible(change.node)} to {change.weight}" for change in variant.set or ()
        )
        removed = (
            "" if variant.remove is None else f"removes the factor {visible(variant.remove)}, and "
        )
        return f"ranking: {removed}sets the weights of {weights}"
    if variant.value is not None:
        default = ", the default rebalance variant" if variant.default else ""
        return f"{variant.setting} set to {shown(str(variant.value))}{default}"
    if variant.add is not None:
        return f"adds the rule {shown(variant.add)}"
    return f"replaces the rule {shown(variant.replace or '')} with {shown(variant.with_ or '')}"


def _so_far(saved: AnySavedCase) -> str:
    """The case's outcome so far, and what this run does with it."""
    outcome = described(saved.attempts, valid=saved.valid)
    tried = counted(len(saved.attempts), "attempt")
    if saved.state == "complete":
        return f"{outcome}, after {tried}. It's complete, so it isn't sent again."
    if saved.state == "due":
        if not saved.attempts:
            return "not yet run. This run sends it."
        return (
            f"{outcome}, after {tried}, none of whose requests could have reached Portfolio123."
            " This run sends it."
        )
    attempt = saved.latest_charged
    assert attempt is not None  # a case awaiting a repeat has one
    ranked = isinstance(saved, SavedRankingCase)
    if invalid_success(saved.attempts, valid=saved.valid):
        again = (
            "a repeat, which sends its rank_update and its backtest again"
            if ranked
            else "a repeat, which sends its request again"
        )
        requests = (
            "Its attempt succeeded, but its saved response failed validation, so it wasn't"
            f" normalized, and it's sent again only by {again}, and may be charged again"
        )
    elif ranked:
        requests = (
            "Its rank_update, or its backtest, may have reached Portfolio123, and may have been"
            " charged, so it's sent again only by a repeat, which sends both again, and may be"
            " charged again"
        )
    else:
        requests = (
            "Its request may have reached Portfolio123, and may have been charged, so it's sent"
            " again only by a repeat, which may be charged again"
        )
    return f"{outcome}, after {tried}. {requests}: {repeat_option(saved, attempt)}"


def _retired_lines(run: ExperimentRun, experiment: SavedExperiment) -> list[str]:
    """The experiment's retired cases, each with the last plan that included it, and its
    outcome."""
    return [
        "",
        "Retired cases, kept with their attempts, which the budget still counts:",
        *(
            [
                f"  {case.case_key} ({case.case_id}), last in plan {case.plan}:"
                f" {_retired_outcome(experiment, case.case_id)}"
                for case in run.retired
            ]
            or ["  None."]
        ),
    ]


def _retired_outcome(experiment: SavedExperiment, case_id: str) -> str:
    attempts = experiment.attempts_of(case_id)
    outcome = case_outcome(attempts, valid=experiment.valid(case_id))
    return f"{outcome.replace('_', ' ')}, after {counted(len(attempts), 'attempt')}"


def _counted_so_far(run: ExperimentRun) -> str:
    """The requests and authentication calls the budget has counted so far, across every run of
    the experiment, and what it leaves of each."""
    budget = run.plan.budget
    requests, calls = run.provider_requests, run.authentication_calls
    return (
        f"{counted(requests, 'provider request')} and {counted(calls, 'authentication call')},"
        f" which leaves {counted(run.remaining_requests, 'provider request')} and"
        f" {counted(max(0, budget.authentication_calls - calls), 'authentication call')}."
    )


def _counted_lines(run: ExperimentRun) -> list[str]:
    """The budget counted so far, what remains, and the cases it can't cover."""
    lines = [
        (
            "  The budget covers the whole experiment, every run that resumes it included."
            f" Counted so far: {_counted_so_far(run)}"
        )
    ]
    spent = run.counted_credits()
    if spent is not None and isinstance(run.plan, PlanV1_3):
        remaining = run.remaining_requests
        lines.append(
            "  At the documented costs, the requests counted so far can have cost at most"
            f" {counted(spent, 'credit')}, and the"
            f" {counted(remaining, 'provider request')}"
            f" {'that remains' if remaining == 1 else 'that remain'} at most"
            f" {counted(most_credits(run.plan.budget, remaining), 'credit')}."
        )
    uncovered = run.uncovered()
    if uncovered:
        named = ", ".join(case.case_key for case in uncovered)
        lines.append(
            f"  The remaining budget can't cover {named}, so this run won't start"
            f" {'it' if len(uncovered) == 1 else 'them'}. A revision that raises"
            f" budget.provider_requests lets {'it' if len(uncovered) == 1 else 'them'} run."
        )
    return lines


def _how_to_approve(run: ExperimentRun) -> str:
    if not run.revision:
        return how_to_approve(plan_hash(run.plan))
    return (
        f"Approve the revision with --revision-reason and your reason for it: by typing"
        f" {APPROVE_ANSWER} when asked in a terminal, or with --approve {plan_hash(run.plan)}"
    )


def format_experiment_summary(run: ExperimentRun, *, full_plan_hint: bool) -> str:
    """The plan hash and the budget, with what's counted so far, and nothing from the
    configuration. With `full_plan_hint`, it also says how to see the full plan."""
    plan = run.plan
    lines = [f"Plan hash: {plan_hash(plan)}"]
    if run.experiment is not None:
        number = run.experiment.current.number
        lines.append(
            f"It revises the experiment's current plan, plan {number}."
            if run.revision
            else f"It's the experiment's current plan, plan {number}, which this run resumes."
        )
    lines += budget_lines(plan.budget)
    if run.experiment is not None:
        lines.append(
            f"  Counted so far, across every run of the experiment: {_counted_so_far(run)}"
        )
    # After the whole budget, what's counted so far included, so it doesn't split the budget.
    if isinstance(plan, PlanV1_3):
        sends = run.experiment is None or run.sends_a_case()
        lines.append(OVERWRITES if sends else SENDS_NO_CASE)
    if full_plan_hint:
        lines.append(FULL_PLAN_HINT)
    return "\n".join(lines) + "\n"
