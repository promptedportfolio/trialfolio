"""The repeats of an experiment's run: the check of each `--repeat` against the plan and the
records, and the confirmation of those named by their key alone, by typing `repeat` on a terminal
(docs/contracts.md, repeating a case). Each error's loggable message names a case by its
`case_id`, never by its key, which is the user's text.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Self, TextIO

from trialfolio.approval import counted, read_answer, write_shown
from trialfolio.case_state import confirmation_used, repeatable
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_approval.run import (
    AnySavedCase,
    ExperimentRun,
    RepeatOption,
    repeat_option,
)
from trialfolio.experiment_execution import Repeat
from trialfolio.experiment_records import SavedExperimentAttempt

REPEAT_ANSWER: Final = "repeat"
"""What the user types to confirm the repeats shown. Any other answer is a refusal."""


@dataclass(frozen=True)
class CheckedRepeats:
    """What the check of the `--repeat` options found, which the approval passes on."""

    confirmed: tuple[Repeat, ...] = ()
    """Repeats an attempt ID confirmed, those whose confirmation is used included, which the core
    reports and doesn't make."""
    made: bool = False
    """Whether one of `confirmed` is to be made: its confirmation isn't used."""
    to_ask: tuple[tuple[AnySavedCase, SavedExperimentAttempt], ...] = ()
    """Cases awaiting a repeat that `--repeat` names by key alone, for the CLI to confirm."""
    notes: tuple[str, ...] = ()
    """Why a repeat named isn't made, for each that doesn't fail."""

    @classmethod
    def joined(cls, checks: Sequence[Self]) -> Self:
        """What `checks`, each of one option, found together, in their order."""
        return cls(
            tuple(repeat for check in checks for repeat in check.confirmed),
            any(check.made for check in checks),
            tuple(case for check in checks for case in check.to_ask),
            tuple(note for check in checks for note in check.notes),
        )


def check_repeats(run: ExperimentRun, *, asks: bool) -> CheckedRepeats:
    """Checks each `--repeat` against the plan and the records (repeating a case), in the order
    given. Raises `TrialFolioError` with `plan.approval_required` for the first that can't
    apply."""
    if not run.repeats:
        return CheckedRepeats()
    if run.experiment is None:
        message = (
            "A new experiment has no attempt to repeat, so --repeat doesn't apply. Run the"
            " command without it."
        )
        raise not_repeated(run, message, message)
    cases = {saved.case.case_key: saved for saved in run.cases}
    return CheckedRepeats.joined(
        [
            _check_option(run, cases.get(option.case_key), option, asks=asks)
            for option in run.repeats
        ]
    )


def _check_option(
    run: ExperimentRun, saved: AnySavedCase | None, option: RepeatOption, *, asks: bool
) -> CheckedRepeats:
    """Checks one `--repeat`, which names `saved`, or no case of the plan."""
    if saved is None:
        plan = "revision" if run.revision else "plan"
        raise not_repeated(
            run,
            f"--repeat {option.case_key} names no case of the {plan} this run approves. A"
            " retired case can't be repeated.",
            f"A --repeat names a case key that no case of the {plan} has.",
        )
    if saved.state == "due":
        problem = (
            "Case {} isn't awaiting a repeat: none of its attempts may have reached"
            " Portfolio123, so running the experiment sends it without --repeat."
        )
        raise not_repeated(
            run, problem.format(saved.case.case_key), problem.format(saved.case.case_id)
        )
    if option.attempt_id is None:
        return _check_key_alone(run, saved, asks=asks)
    return _check_attempt(run, saved, option.attempt_id)


def _check_key_alone(run: ExperimentRun, saved: AnySavedCase, *, asks: bool) -> CheckedRepeats:
    """Checks a `--repeat` that names a complete case, or one awaiting a repeat, by its key
    alone: the CLI asks to confirm it only when it can ask."""
    key, case_id = saved.case.case_key, saved.case.case_id
    if saved.state == "complete":
        return CheckedRepeats(
            notes=(
                (
                    f"Case {key} isn't repeated: it's complete, since one of its attempts"
                    " succeeded. The run resumes the rest of the experiment."
                ),
            )
        )
    latest = saved.latest_charged
    assert latest is not None  # a case awaiting a repeat has one
    if not asks:
        # The options `not_repeated` adds give this case's, with its attempt ID.
        problem = (
            "Case {} awaits a repeat, but --repeat names it without an attempt ID, and"
            " Trial Folio asks to confirm a repeat only when stdin and stderr are both"
            " terminals and there's no --approve. An option with the attempt ID confirms"
            " the possible repeat charge."
        )
        raise not_repeated(run, problem.format(key), problem.format(case_id))
    return CheckedRepeats(to_ask=((saved, latest),))


def _check_attempt(
    run: ExperimentRun, saved: AnySavedCase, attempt_id: uuid.UUID
) -> CheckedRepeats:
    """Checks a `--repeat` that names a complete case, or one awaiting a repeat, with an attempt
    ID, which must name the case's latest possibly charged attempt: a repeat whose confirmation
    an earlier repeat used isn't made again."""
    key, case_id = saved.case.case_key, saved.case.case_id
    if not repeatable(saved.attempts, attempt_id, valid=saved.valid):
        problem = (
            "The repeat of case {} names attempt {}, which isn't an attempt of the case whose"
            " request may have been charged and that didn't succeed, or succeeded with a"
            " response that failed validation. A repeat names the case's latest attempt whose"
            " request may have been charged."
        )
        raise not_repeated(
            run, problem.format(key, attempt_id), problem.format(case_id, attempt_id)
        )
    confirmed = (Repeat(case_id, attempt_id),)
    if not confirmation_used(saved.attempts, attempt_id):
        return CheckedRepeats(confirmed, made=True)
    latest = saved.latest_charged
    again = (
        f" A new repeat needs a new confirmation, which names the repeat's own attempt:"
        f" {repeat_option(saved, latest)}."
        if saved.state == "awaiting_repeat" and latest is not None
        else ""
    )
    return CheckedRepeats(
        confirmed,
        notes=(
            (
                f"Case {key} isn't repeated: the repeat confirmed for its attempt"
                f" {attempt_id} was made already, and may have reached Portfolio123.{again}"
                " The run resumes the rest of the experiment."
            ),
        ),
    )


def _awaiting_options(run: ExperimentRun) -> tuple[str, str]:
    """The exact option for each case awaiting a repeat, and, for the log, how many there are."""
    awaiting = run.awaiting_repeat()
    if not awaiting:
        return "No case of the plan awaits a repeat.", "No case of the plan awaits a repeat."
    options = "; ".join(repeat_option(saved, attempt) for saved, attempt in awaiting)
    each = "The case awaiting a repeat" if len(awaiting) == 1 else "Each case awaiting a repeat"
    return (
        f"{each}, with the option that repeats it: {options}.",
        (
            f"{counted(len(awaiting), 'case')} of the plan"
            f" {'awaits' if len(awaiting) == 1 else 'await'} a repeat."
        ),
    )


def not_repeated(run: ExperimentRun, message: str, log_message: str) -> TrialFolioError:
    """`plan.approval_required`, for a repeat that can't apply or isn't confirmed, with the exact
    option for each case awaiting a repeat."""
    options, logged = _awaiting_options(run)
    tail = f" {run.nothing_done}"
    return TrialFolioError(
        "plan.approval_required",
        f"{message} {options}{tail}",
        f"{log_message} {logged}{tail}",
    )


def ask_repeats(
    run: ExperimentRun,
    cases: Sequence[tuple[AnySavedCase, SavedExperimentAttempt]],
    *,
    stdin: TextIO,
    stderr: TextIO,
) -> list[Repeat]:
    """Lists each case to repeat with its latest possibly charged attempt, says what a repeat
    costs, and asks the user to type `repeat`. Returns the repeats of the attempts it showed."""
    lines = [
        "",
        "Repeat these cases? Each one's request may already have been charged:",
        *_repeated_lines(cases),
        _repeat_cost(run),
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
        raise not_repeated(run, problem.format(keys), problem.format(ids))
    return [Repeat(saved.case.case_id, attempt.attempt_id) for saved, attempt in cases]


def _repeated_lines(cases: Sequence[tuple[AnySavedCase, SavedExperimentAttempt]]) -> list[str]:
    """Each case to repeat, with its latest possibly charged attempt and how it ended."""
    lines: list[str] = []
    for saved, attempt in cases:
        if attempt.outcome == "succeeded":  # its response failed validation (D-45)
            state = (
                "succeeded, but its saved response failed validation (provider.response_invalid)"
            )
        else:
            code = "" if attempt.error_code is None else f" ({attempt.error_code})"
            state = f"is {attempt.outcome}{code}"
        lines.append(
            f"  {saved.case.case_key} ({saved.case.case_id}): its attempt {attempt.attempt_id}"
            f" {state}, and its request may already have been charged."
        )
    return lines


def _repeat_cost(run: ExperimentRun) -> str:
    """What a repeat sends, and what it, with the run's other sends, counts against the budget."""
    budget = run.plan.budget
    remaining = run.remaining_requests
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
    return (
        f"A repeat sends {what} as a new attempt of the case. It may be"
        f" charged again, and it counts against the experiment's budget: of its"
        f" {counted(budget.provider_requests, 'provider request')},"
        f" {remaining} {'remains' if remaining == 1 else 'remain'}, and this run sends"
        f" {counted(sends, 'request')}, with the cases that are due and the repeats an"
        f" attempt ID confirmed, {leaves}."
    )
