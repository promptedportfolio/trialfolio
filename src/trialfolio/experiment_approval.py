"""An experiment's plan display, its approval, and the confirmation of its repeats: the CLI's side
of running an experiment (docs/contracts.md, running an experiment, experiment plans and
revisions, and repeating a case).

The core builds the plan, reads and checks the experiment's records, and checks the approval and
the repeats again, and never prompts. This module, as `trialfolio.approval` does for a screen:

- **Shows the plan** on stderr directly, never through logging, because it holds configuration
  values: the full plan only when stderr is a terminal, when it asks for approval and when
  approval fails, and otherwise only the plan hash and the budget. For a resume, the full plan
  shows the experiment's progress too: each case's outcome so far, each case awaiting a repeat
  with the option that repeats it, the retired cases, and the budget counted so far. For a
  revision, it shows what changed from the current plan, and the reason.
- **Checks the reason and the repeats** against the plan and the records (step 5): a reason
  needs a revision, and each `--repeat` a case of the plan that can be repeated.
- **Obtains the approval** (step 6): the plan's hash, from `--approve` or by typing `approve` on
  a terminal; for a revision, with a reason, or the command fails with `plan.changed`.
- **Confirms the repeats** that `--repeat` names without an attempt ID, by typing `repeat` on a
  terminal, and passes on the attempts it showed.

Text from the configuration, and the reason, is shown with its control and formatting
characters escaped. Each error's loggable message names a case by its `case_id`, never by its
key, which is the user's text.

From release 0.4.0, a plan 1.3.0, whose baseline's ranking is a definition, shows more (plans with
a ranking definition, the display): that the run overwrites `ApiRankingSystem`, what the ranking
lock does and doesn't exclude, the definition's source, each node's weight among the baseline's
settings, each ranking variant's change, each case's `rank_update` with its whole definition as
text, and the budget with each operation's documented cost, what a case's attempt costs, and, in
a resume, the most the requests counted so far can have cost apart from the most the remaining
ones can cost. Each case's attempt sends two requests, so the budget the display and the repeat's
prompt count covers half as many cases (R04-T12).

It imports the modules that read an experiment's records, which import `p123api`, so the CLI
imports it only once `installed_versions` has checked them.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, TextIO

from trialfolio.approval import (
    APPROVE_ANSWER,
    OVERWRITES,
    Approval,
    budget_lines,
    counted,
    data_sent_lines,
    most_credits,
    ranking_lines,
    read_answer,
    request_lines,
    retry_lines,
    setting_lines,
    shown,
    write_shown,
)
from trialfolio.case_state import case_outcome, confirmation_used, described, repeatable
from trialfolio.contracts.experiment_plan import (
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanV1_1,
    PlanV1_3,
    PlanVariant,
    PlanVariantV1_3,
)
from trialfolio.contracts.experiment_record import PlanChanges, PlanChangesV1_1, RetiredCaseV1_1
from trialfolio.contracts.ranking_snapshot import RankingSnapshotRecord
from trialfolio.display import visible
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution import Repeat
from trialfolio.experiment_records import (
    SavedCase,
    SavedExperiment,
    SavedExperimentAttempt,
    SavedRankingCase,
)
from trialfolio.planning import plan_hash, retired_cases_v1_1

type AnySavedCase = SavedCase | SavedRankingCase
"""A case of the plan, 1.1.0's or 1.3.0's, and what the experiment's records say of it."""

REPEAT_ANSWER: Final = "repeat"
"""What the user types to confirm the repeats shown. Any other answer is a refusal."""


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
        budget = self.plan.budget
        if self.authentication_calls >= budget.authentication_calls:
            return sends
        remaining = max(0, budget.provider_requests - self.provider_requests)
        return sends[remaining // self.requests_per_case :]

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


@dataclass(frozen=True)
class ExperimentApproval:
    """An experiment's approved plan, how it was approved, and the confirmed repeats, each by its
    case's `case_id` and the attempt whose possible charge the user acknowledged."""

    approval: Approval
    repeats: tuple[Repeat, ...]
    """Those whose confirmation an earlier repeat used included, which the execution reports and
    doesn't make."""
    sends: bool
    """Whether a case is due or to be repeated, and the remaining budget covers the first of
    them, so the run needs credentials."""


# The display


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


def _option(saved: AnySavedCase, attempt: SavedExperimentAttempt) -> str:
    return f"--repeat {saved.case.case_key}:{attempt.attempt_id}"


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
    requests = (
        "Its rank_update, or its backtest, may have reached Portfolio123, and may have been"
        " charged, so it's sent again only by a repeat, which sends both again, and may be"
        " charged again"
        if isinstance(saved, SavedRankingCase)
        else "Its request may have reached Portfolio123, and may have been charged, so it's sent"
        " again only by a repeat, which may be charged again"
    )
    return f"{outcome}, after {tried}. {requests}: {_option(saved, attempt)}"


def _retired_outcome(experiment: SavedExperiment, case_id: str) -> str:
    attempts = experiment.attempts_of(case_id)
    outcome = case_outcome(attempts, valid=experiment.valid(case_id))
    return f"{outcome.replace('_', ' ')}, after {counted(len(attempts), 'attempt')}"


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


def _counted_lines(run: ExperimentRun) -> list[str]:
    """The budget counted so far, what remains, and the cases it can't cover."""
    budget = run.plan.budget
    requests = run.provider_requests
    calls = run.authentication_calls
    lines = [
        (
            "  The budget covers the whole experiment, every run that resumes it included."
            f" Counted so far: {counted(requests, 'provider request')} and"
            f" {counted(calls, 'authentication call')}, which leaves"
            f" {counted(max(0, budget.provider_requests - requests), 'provider request')} and"
            f" {counted(max(0, budget.authentication_calls - calls), 'authentication call')}."
        )
    ]
    spent = run.counted_credits()
    if spent is not None and isinstance(run.plan, PlanV1_3):
        remaining = max(0, budget.provider_requests - requests)
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
    declared = plan.prior_research
    description = "" if declared.description is None else f" {shown(declared.description)}"
    lines = [
        f"Experiment plan {shown_hash}",
        "",
        f"Experiment: {plan.experiment_id}",
        f"Title: {shown(plan.title)}",
        f"Purpose: {shown(plan.purpose)}",
        f"Prior research, as declared: {declared.status}.{description}",
        "  Trial Folio can't verify the declaration.",
    ]
    experiment = run.experiment
    if experiment is not None and run.changes is not None:
        current = experiment.current
        reason = (
            "none given. A revision needs one, with --revision-reason."
            if run.reason is None
            else shown(run.reason)
        )
        lines += [
            "",
            (
                f"This plan revises the experiment's current plan, plan {current.number}"
                f" ({current.plan.plan_hash}). What changed:"
            ),
            *_changes_lines(run.changes),
            f"Reason for the revision: {reason}",
        ]
    elif experiment is not None:
        lines += [
            "",
            (
                f"This is the experiment's current plan, plan {experiment.current.number}, which"
                " this run resumes."
            ),
        ]
    if isinstance(plan, PlanV1_3):
        lines += ["", *ranking_lines(plan.ranking_source, run.snapshot)]
    baseline = plan.cases[0]
    lines += ["", "The baseline's settings, with the provenance each value will have once sent:"]
    for row in baseline.settings:
        lines += setting_lines(row)
    lines += [
        "",
        (
            f"The {len(plan.cases)} cases, in the order they run. Each is the baseline with"
            " exactly its change:"
        ),
    ]
    for saved in run.cases:
        case = saved.case
        lines += ["", f"Case {case.case_key} ({case.case_id}): {_change(case.variant)}"]
        if case.description is not None:
            lines.append(f"  Description: {shown(case.description)}")
        if experiment is not None:
            lines.append(f"  So far: {_so_far(saved)}")
        lines += request_lines(case.requests, "  ")
    if experiment is not None:
        retired = run.retired
        lines += ["", "Retired cases, kept with their attempts, which the budget still counts:"]
        lines += [
            f"  {case.case_key} ({case.case_id}), last in plan {case.plan}:"
            f" {_retired_outcome(experiment, case.case_id)}"
            for case in retired
        ] or ["  None."]
    lines += ["", *budget_lines(plan.budget), *_counted_lines(run)]
    lines += ["", *retry_lines(plan.retry_policy), ""]
    lines += data_sent_lines(
        plan.data_sent,
        "the experiment's ID, title, purpose, or prior research, a case's key or description, a"
        " revision's reason, data_vendor, the configuration file, file paths",
    )
    lines += ["", f"Plan hash: {shown_hash}", _how_to_approve(run)]
    return "\n".join(lines) + "\n"


def _how_to_approve(run: ExperimentRun) -> str:
    shown_hash = plan_hash(run.plan)
    if run.revision:
        return (
            f"Approve the revision with --revision-reason and your reason for it: by typing"
            f" {APPROVE_ANSWER} when asked in a terminal, or with --approve {shown_hash}"
        )
    return (
        f"Approve it by typing {APPROVE_ANSWER} when asked in a terminal, or with --approve"
        f" {shown_hash}"
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
        budget = plan.budget
        requests, calls = run.provider_requests, run.authentication_calls
        lines.append(
            f"  Counted so far, across every run of the experiment:"
            f" {counted(requests, 'provider request')} and"
            f" {counted(calls, 'authentication call')}, which leaves"
            f" {counted(max(0, budget.provider_requests - requests), 'provider request')} and"
            f" {counted(max(0, budget.authentication_calls - calls), 'authentication call')}."
        )
    # After the whole budget, what's counted so far included, so it doesn't split the budget.
    if isinstance(plan, PlanV1_3):
        lines.append(OVERWRITES)
    if full_plan_hint:
        lines.append("Run the command in a terminal to see the full plan.")
    return "\n".join(lines) + "\n"


# Approval


def approve_experiment(
    run: ExperimentRun, approve: str | None, *, stdin: TextIO, stderr: TextIO
) -> ExperimentApproval:
    """Shows the plan on `stderr`, checks the reason and the repeats, obtains the approval, and
    confirms the repeats, in the order of steps 5 and 6 of running an experiment.

    - **The reason** needs a revision, unless it's the reason the current plan recorded, which
      resumes it.
    - **Each repeat** names a case of the plan. A case awaiting a repeat is repeated with the
      attempt ID that names its latest possibly charged attempt; or, named by its key alone,
      once the user confirms by typing `repeat`, when the CLI asks: stdin and stderr are
      terminals, and there's no `--approve`. A repeat whose confirmation an earlier repeat used,
      and a complete case named by its key alone, aren't repeated, and the run resumes the rest:
      it says so on `stderr`.
    - **The approval** is the plan's hash, from `approve` or by typing `approve`, as for a
      screen. A revision needs a reason too.

    Raises `TrialFolioError` with `plan.approval_required` when the reason has no revision, a
    repeat can't apply or isn't confirmed, or the plan isn't approved; and with `plan.changed`
    when a revision isn't approved with a reason; once the plan has been shown, with the full
    plan when `stderr` is a terminal. A `KeyboardInterrupt` while it asks is left to the caller.
    """
    on_terminal = stderr.isatty()
    asks = approve is None and on_terminal and stdin.isatty()
    checked = _CheckedRepeats()
    problem = _reason_problem(run)
    if problem is None:
        try:
            checked = _check_repeats(run, asks=asks)
        except TrialFolioError as refused:
            problem = refused
    if problem is None:
        problem = _approval_problem(run, approve, asks)
    if problem is not None:
        write_shown(
            stderr,
            format_experiment_plan(run)
            if on_terminal
            else format_experiment_summary(run, full_plan_hint=True),
        )
        raise problem
    shown_hash = plan_hash(run.plan)
    if asks:
        write_shown(stderr, format_experiment_plan(run))
        what = "this revision of the experiment's plan" if run.revision else "this plan"
        write_shown(stderr, f"\nType {APPROVE_ANSWER} to run {what}, or anything else to stop: ")
        if read_answer(stdin) != APPROVE_ANSWER:
            refused = f"The plan wasn't approved: the answer wasn't {APPROVE_ANSWER}."
            raise _changed(run, refused) if run.revision else _not_approved(run, refused)
        approval = Approval(shown_hash, "interactive")
    else:
        write_shown(stderr, format_experiment_summary(run, full_plan_hint=False))
        approval = Approval(shown_hash, "option")
    asked = _ask_repeats(run, checked.to_ask, stdin=stdin, stderr=stderr) if checked.to_ask else []
    if checked.notes:
        write_shown(stderr, "".join(f"{note}\n" for note in checked.notes))
    due = any(saved.state == "due" for saved in run.cases)
    # A run whose remaining budget covers none of its sends starts none, so it needs no
    # credentials (the 0.3.0 walk-through).
    covered = len(run.sends()) > len(run.uncovered())
    return ExperimentApproval(
        approval, (*checked.confirmed, *asked), (due or bool(asked) or checked.made) and covered
    )


def _reason_problem(run: ExperimentRun) -> TrialFolioError | None:
    """`plan.approval_required` for a reason with no revision, unless it's the one the current
    plan recorded, which resumes it."""
    if run.reason is None or run.revision:
        return None
    if run.experiment is None:
        problem = "A new experiment has no plan to revise."
    elif run.reason == run.experiment.current.record.plans[-1].reason:
        return None
    else:
        problem = (
            "The configuration gives the experiment's current plan, so there's no revision to"
            " give a reason for. If you changed the configuration, check that this is the file"
            " you changed."
        )
    return _not_approved(
        run,
        f"A reason for a revision was given, but there's no revision. {problem} Run the command"
        " without --revision-reason.",
    )


def _approval_problem(
    run: ExperimentRun, approve: str | None, asks: bool
) -> TrialFolioError | None:
    """The approval's problem before any prompt: a hash that isn't the plan's, no approval
    without a terminal, and a revision without a reason."""
    shown_hash = plan_hash(run.plan)
    if run.revision:
        if run.reason is None:
            return _changed(run, "No reason for the revision was given, with --revision-reason.")
        if approve is not None and approve != shown_hash:
            return _changed(run, "The hash given with --approve isn't the revision's hash.")
        if approve is None and not asks:
            return _changed(
                run,
                "Without --approve, Trial Folio asks for the approval only when stdin and stderr"
                " are both terminals.",
            )
        return None
    if approve is not None and approve != shown_hash:
        return _not_approved(
            run,
            "The hash given with --approve isn't this plan's hash. Approval takes the full hash,"
            " exactly as shown.",
        )
    if approve is None and not asks:
        return _not_approved(
            run,
            "Running a plan needs its approval. Without --approve, Trial Folio asks for it only"
            " when stdin and stderr are both terminals.",
        )
    return None


def _nothing(run: ExperimentRun) -> str:
    if run.experiment is None:
        return "Nothing was sent, and no output was created."
    return "Nothing was sent or written."


def _not_approved(run: ExperimentRun, reason: str) -> TrialFolioError:
    shown_hash = plan_hash(run.plan)
    return TrialFolioError(
        "plan.approval_required",
        f"{reason} {_nothing(run)} To approve this plan, run the command again with --approve"
        f" {shown_hash}, or run it without --approve in a terminal and type {APPROVE_ANSWER}.",
    )


def _changed(run: ExperimentRun, why: str) -> TrialFolioError:
    """`plan.changed`, with the revision's hash and the options that approve it."""
    shown_hash = plan_hash(run.plan)
    number = "" if run.experiment is None else f", plan {run.experiment.current.number}"
    return TrialFolioError(
        "plan.changed",
        f"The configuration, or the installed versions, changed since the experiment's current"
        f" plan{number}, so running it revises the plan, and a revision needs a reason and the"
        f" approval of its hash. {why} Nothing was sent or written. To approve the revision, run"
        f" the command again with --revision-reason and your reason for it, and --approve"
        f" {shown_hash}; or with --revision-reason, without --approve, in a terminal, and type"
        f" {APPROVE_ANSWER}.",
    )


# Repeats


@dataclass(frozen=True)
class _CheckedRepeats:
    confirmed: tuple[Repeat, ...] = ()
    """Repeats an attempt ID confirmed, those whose confirmation is used included, which the core
    reports and doesn't make."""
    made: bool = False
    """Whether one of `confirmed` is to be made: its confirmation isn't used."""
    to_ask: tuple[tuple[AnySavedCase, SavedExperimentAttempt], ...] = ()
    """Cases awaiting a repeat that `--repeat` names by key alone, for the CLI to confirm."""
    notes: tuple[str, ...] = ()
    """Why a repeat named isn't made, for each that doesn't fail."""


def _check_repeats(run: ExperimentRun, *, asks: bool) -> _CheckedRepeats:  # noqa: C901 - RF-T10 shortens it.
    """Checks each `--repeat` against the plan and the records (repeating a case). Raises
    `TrialFolioError` with `plan.approval_required` for one that can't apply."""
    if not run.repeats:
        return _CheckedRepeats()
    if run.experiment is None:
        message = (
            "A new experiment has no attempt to repeat, so --repeat doesn't apply. Run the"
            " command without it."
        )
        raise _not_repeated(run, message, message)
    cases = {saved.case.case_key: saved for saved in run.cases}
    confirmed: list[Repeat] = []
    made = False
    to_ask: list[tuple[AnySavedCase, SavedExperimentAttempt]] = []
    notes: list[str] = []
    for option in run.repeats:
        saved = cases.get(option.case_key)
        plan = "revision" if run.revision else "plan"
        if saved is None:
            raise _not_repeated(
                run,
                f"--repeat {option.case_key} names no case of the {plan} this run approves. A"
                " retired case can't be repeated.",
                f"A --repeat names a case key that no case of the {plan} has.",
            )
        key, case_id = saved.case.case_key, saved.case.case_id
        if saved.state == "due":
            problem = (
                "Case {} isn't awaiting a repeat: none of its attempts may have reached"
                " Portfolio123, so running the experiment sends it without --repeat."
            )
            raise _not_repeated(run, problem.format(key), problem.format(case_id))
        latest = saved.latest_charged
        if option.attempt_id is None:
            if saved.state == "complete":
                notes.append(
                    f"Case {key} isn't repeated: it's complete, since one of its attempts"
                    " succeeded. The run resumes the rest of the experiment."
                )
                continue
            assert latest is not None  # a case awaiting a repeat has one
            if not asks:
                # The options `_not_repeated` adds give this case's, with its attempt ID.
                problem = (
                    "Case {} awaits a repeat, but --repeat names it without an attempt ID, and"
                    " Trial Folio asks to confirm a repeat only when stdin and stderr are both"
                    " terminals and there's no --approve. An option with the attempt ID confirms"
                    " the possible repeat charge."
                )
                raise _not_repeated(run, problem.format(key), problem.format(case_id))
            to_ask.append((saved, latest))
            continue
        named = [a for a in saved.attempts if a.attempt_id == option.attempt_id]
        if not named or not repeatable(named[0]):
            problem = (
                "The repeat of case {} names attempt {}, which isn't an attempt of the case whose"
                " request may have been charged and that didn't succeed. A repeat names the"
                " case's latest attempt whose request may have been charged."
            )
            raise _not_repeated(
                run,
                problem.format(key, option.attempt_id),
                problem.format(case_id, option.attempt_id),
            )
        confirmed.append(Repeat(case_id, option.attempt_id))
        if not confirmation_used(saved.attempts, option.attempt_id):
            made = True
            continue
        again = (
            f" A new repeat needs a new confirmation, which names the repeat's own attempt:"
            f" {_option(saved, latest)}."
            if saved.state == "awaiting_repeat" and latest is not None
            else ""
        )
        notes.append(
            f"Case {key} isn't repeated: the repeat confirmed for its attempt"
            f" {option.attempt_id} was made already, and may have reached Portfolio123.{again}"
            " The run resumes the rest of the experiment."
        )
    return _CheckedRepeats(tuple(confirmed), made, tuple(to_ask), tuple(notes))


def _awaiting_options(run: ExperimentRun) -> tuple[str, str]:
    """The exact option for each case awaiting a repeat, and, for the log, how many there are."""
    awaiting = run.awaiting_repeat()
    if not awaiting:
        return "No case of the plan awaits a repeat.", "No case of the plan awaits a repeat."
    options = "; ".join(_option(saved, attempt) for saved, attempt in awaiting)
    each = "The case awaiting a repeat" if len(awaiting) == 1 else "Each case awaiting a repeat"
    return (
        f"{each}, with the option that repeats it: {options}.",
        (
            f"{counted(len(awaiting), 'case')} of the plan"
            f" {'awaits' if len(awaiting) == 1 else 'await'} a repeat."
        ),
    )


def _not_repeated(run: ExperimentRun, message: str, log_message: str) -> TrialFolioError:
    options, logged = _awaiting_options(run)
    tail = f" {_nothing(run)}"
    return TrialFolioError(
        "plan.approval_required",
        f"{message} {options}{tail}",
        f"{log_message} {logged}{tail}",
    )


def _ask_repeats(
    run: ExperimentRun,
    cases: Sequence[tuple[AnySavedCase, SavedExperimentAttempt]],
    *,
    stdin: TextIO,
    stderr: TextIO,
) -> list[Repeat]:
    """Lists each case to repeat with its latest possibly charged attempt, says what a repeat
    costs, and asks the user to type `repeat`. Returns the repeats of the attempts it showed."""
    lines = ["", "Repeat these cases? Each one's request may already have been charged:"]
    for saved, attempt in cases:
        code = "" if attempt.error_code is None else f" ({attempt.error_code})"
        lines.append(
            f"  {saved.case.case_key} ({saved.case.case_id}): its attempt {attempt.attempt_id}"
            f" is {attempt.outcome}{code}, and its request may already have been charged."
        )
    budget = run.plan.budget
    remaining = max(0, budget.provider_requests - run.provider_requests)
    # Every send of the run: these repeats, the cases that are due, and the repeats an attempt
    # ID confirmed, as the core runs them, each case with its requests: two for a case with a
    # ranking definition.
    sends = len(run.sends()) * run.requests_per_case
    left = remaining - sends
    leaves = (
        f"which leaves {counted(left, 'provider request')}"
        if left >= 0
        else "more than remain, so the cases the budget can't cover won't start"
    )
    what = (
        "the case's rank_update and its backtest again, two requests,"
        if run.requests_per_case == 2
        else "the case's request again,"
    )
    lines += [
        (
            f"A repeat sends {what} as a new attempt of the case. It may be"
            f" charged again, and it counts against the experiment's budget: of its"
            f" {counted(budget.provider_requests, 'provider request')},"
            f" {remaining} {'remains' if remaining == 1 else 'remain'}, and this run sends"
            f" {counted(sends, 'request')}, with the cases that are due and the repeats an"
            f" attempt ID confirmed, {leaves}."
        ),
        "",
        (
            f"Type {REPEAT_ANSWER} to repeat {'it' if len(cases) == 1 else 'them'}, or anything"
            " else to stop: "
        ),
    ]
    write_shown(stderr, "\n".join(lines))
    if read_answer(stdin) != REPEAT_ANSWER:
        keys = ", ".join(f"{saved.case.case_key}" for saved, _ in cases)
        ids = ", ".join(f"{saved.case.case_id}" for saved, _ in cases)
        problem = f"The repeat of {{}} wasn't confirmed: the answer wasn't {REPEAT_ANSWER}."
        raise _not_repeated(run, problem.format(keys), problem.format(ids))
    return [Repeat(saved.case.case_id, attempt.attempt_id) for saved, attempt in cases]
