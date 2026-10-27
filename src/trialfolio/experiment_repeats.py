"""A confirmed repeat, and the core's check of the confirmed repeats against a plan and an
experiment's records (docs/contracts.md, repeating a case, and the resume's checking the approval
in the core).

`Repeat` names a case to repeat, by its `case_id`, and the attempt whose possible charge the user
acknowledged. The CLI confirms each repeat, in `trialfolio.experiment_approval`, and passes them
to the executor, `trialfolio.experiment_execution`, which checks them again with
`confirmed_repeats` before anything is written. Both checks stay, with their own messages: only
the rules they apply, `repeatable` and `confirmation_used`, are written once, in `case_state.py`.

This module imports nothing that sends or writes, so the CLI's display and approval import
`Repeat` without the executor.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from trialfolio.case_state import confirmation_used, repeatable
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_records import SavedExperiment


@dataclass(frozen=True)
class Repeat:
    """A confirmed repeat (docs/contracts.md, repeating a case): the case to repeat, by its
    `case_id`, and the attempt whose possible charge the user acknowledged, the case's latest
    possibly charged attempt, by its `attempt_id`."""

    case_id: str
    attempt_id: uuid.UUID


def confirmed_repeats(
    plan: PlanV1_1 | PlanV1_3, experiment: SavedExperiment, repeats: Sequence[Repeat]
) -> tuple[dict[str, Repeat], tuple[Repeat, ...]]:
    """Checks each confirmed repeat against the plan and the records (repeating a case), and
    returns the repeats to make, by `case_id`, and those whose confirmation an earlier repeat
    used, which aren't made."""
    cases = {saved.case.case_id: saved for saved in experiment.cases(plan)}
    to_make: dict[str, Repeat] = {}
    used: list[Repeat] = []
    for repeat in repeats:
        if repeat.case_id in to_make or repeat.case_id in {r.case_id for r in used}:
            raise ValueError("a repeat names each case once")
        saved = cases.get(repeat.case_id)
        if saved is None:
            raise _not_repeated(
                f"A repeat names case {repeat.case_id}, which the plan doesn't include.",
                f"A repeat names case {repeat.case_id}, which the plan doesn't include.",
            )
        key = f"`{saved.case.case_key}`"
        if saved.state == "due":
            message = (
                "Case {} isn't awaiting a repeat: none of its attempts may have reached"
                " Portfolio123, so running the experiment sends it without one."
            )
            raise _not_repeated(message.format(key), message.format(saved.case.case_id))
        if not repeatable(saved.attempts, repeat.attempt_id, valid=saved.valid):
            message = (
                f"A repeat of case {{}} names attempt {repeat.attempt_id}, which isn't an attempt"
                " of the case whose request may have been charged and that didn't succeed, or"
                " succeeded with a response that failed validation. A repeat names the case's"
                " latest attempt whose request may have been charged."
            )
            raise _not_repeated(message.format(key), message.format(saved.case.case_id))
        if confirmation_used(saved.attempts, repeat.attempt_id):
            used.append(repeat)
        else:
            to_make[repeat.case_id] = repeat
    return to_make, tuple(used)


def _not_repeated(message: str, log_message: str) -> TrialFolioError:
    tail = " Nothing was sent."
    return TrialFolioError("plan.approval_required", message + tail, log_message + tail)
