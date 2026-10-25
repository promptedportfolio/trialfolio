"""An experiment's approval: the plan shown, the reason and the repeats checked, the plan's hash
obtained, from `--approve` or by typing `approve` on a terminal, and the repeats confirmed, in the
order of steps 5 and 6 of running an experiment (docs/contracts.md, running an experiment).
"""

from dataclasses import dataclass
from typing import TextIO

from trialfolio.approval import (
    APPROVE_ANSWER,
    NOT_ASKED,
    NOT_TYPED,
    WRONG_HASH,
    Approval,
    approval_prompt,
    not_approved,
    read_answer,
    write_shown,
)
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_approval.display import format_experiment_plan, format_experiment_summary
from trialfolio.experiment_approval.repeats import CheckedRepeats, ask_repeats, check_repeats
from trialfolio.experiment_approval.run import ExperimentRun
from trialfolio.experiment_execution import Repeat
from trialfolio.planning import plan_hash


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
    checked, problem = _checked(run, approve, asks=asks)
    if problem is not None:
        write_shown(
            stderr,
            format_experiment_plan(run)
            if on_terminal
            else format_experiment_summary(run, full_plan_hint=True),
        )
        raise problem
    approval = _approval(run, asks=asks, stdin=stdin, stderr=stderr)
    asked = ask_repeats(run, checked.to_ask, stdin=stdin, stderr=stderr) if checked.to_ask else []
    if checked.notes:
        write_shown(stderr, "".join(f"{note}\n" for note in checked.notes))
    due = any(saved.state == "due" for saved in run.cases)
    # A run whose remaining budget covers none of its sends starts none, so it needs no
    # credentials (the 0.3.0 walk-through).
    covered = run.sends_a_case()
    return ExperimentApproval(
        approval, (*checked.confirmed, *asked), (due or bool(asked) or checked.made) and covered
    )


def _checked(
    run: ExperimentRun, approve: str | None, *, asks: bool
) -> tuple[CheckedRepeats, TrialFolioError | None]:
    """The repeats checked, and the first problem before any prompt, of the reason, then the
    repeats, then the approval, or None."""
    problem = _reason_problem(run)
    if problem is not None:
        return CheckedRepeats(), problem
    try:
        checked = check_repeats(run, asks=asks)
    except TrialFolioError as refused:
        return CheckedRepeats(), refused
    return checked, _approval_problem(run, approve, asks)


def _approval(run: ExperimentRun, *, asks: bool, stdin: TextIO, stderr: TextIO) -> Approval:
    """The approval of a plan whose problems were checked: from `--approve`, which matches the
    plan's hash, or, when the CLI asks, by typing `approve` after the full plan."""
    shown_hash = plan_hash(run.plan)
    if not asks:
        write_shown(stderr, format_experiment_summary(run, full_plan_hint=False))
        return Approval(shown_hash, "option")
    write_shown(stderr, format_experiment_plan(run))
    what = "this revision of the experiment's plan" if run.revision else "this plan"
    write_shown(stderr, approval_prompt(what))
    if read_answer(stdin) != APPROVE_ANSWER:
        raise _changed(run, NOT_TYPED) if run.revision else _not_approved(run, NOT_TYPED)
    return Approval(shown_hash, "interactive")


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
        return _not_approved(run, WRONG_HASH)
    if approve is None and not asks:
        return _not_approved(run, NOT_ASKED)
    return None


def _not_approved(run: ExperimentRun, reason: str) -> TrialFolioError:
    """`plan.approval_required`, with the options that approve the plan."""
    return not_approved(plan_hash(run.plan), reason, run.nothing_done)


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
