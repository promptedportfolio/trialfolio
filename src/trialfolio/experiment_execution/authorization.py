"""The authorization of an experiment's session, in the core, before anything is written
(docs/contracts.md, approval, the resume's checking the approval in the core, approving a
revision, and repeating a case).

`authorize` checks, in the order of a resume's steps 5 and 6: for a new experiment, that it's
given no reason and no repeat, and that its plan is approved by its hash; for a resume, that the
client is the kind the experiment's attempts were made with, each confirmed repeat, and then the
approval of the current plan, or of a revision, with its reason. It gives what the session runs:
the repeats it makes, those whose confirmation an earlier repeat used, and the approved revision,
if there is one. The CLI checks the same before it asks for approval, with its own messages.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from pydantic import TypeAdapter, ValidationError

from trialfolio.contracts.common import RevisionReason
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution.records import ApprovedRevision
from trialfolio.experiment_records import AnyPlan, SavedExperiment
from trialfolio.experiment_repeats import Repeat, confirmed_repeats
from trialfolio.planning import PlanRevisionV1_1, check_approval, plan_changes_v1_1, plan_hash

_REASON: Final = TypeAdapter[str](RevisionReason)


@dataclass(frozen=True)
class Authorization:
    """What an authorized session runs, beside its plan."""

    revision: ApprovedRevision | None
    """The revision it records before its cases, for a resume that revises the current plan."""
    repeats: Mapping[str, Repeat]
    """The confirmed repeats it makes, by `case_id`."""
    used: tuple[Repeat, ...]
    """The confirmed repeats it doesn't make, because an earlier repeat used their
    confirmation."""


def authorize(
    plan: AnyPlan,
    approved_hash: str,
    experiment: SavedExperiment | None,
    *,
    synthetic: bool,
    reason: str | None,
    repeats: Sequence[Repeat],
) -> Authorization:
    """Checks that the session may run `plan`, approved by `approved_hash`: for a new
    experiment, when `experiment` is None, or a resume of its records. `synthetic` is whether
    the session's client is the demo's. Raises the errors `ExperimentExecution` gives."""
    if experiment is None:
        if reason is not None:
            raise _no_revision("A new experiment has no plan to revise.")
        if repeats:
            raise TrialFolioError(
                "plan.approval_required",
                "A new experiment has no attempt to repeat, so no repeat applies. Nothing was"
                " sent.",
            )
        check_approval(plan, approved_hash)
        if plan.revises is not None:
            raise ValueError("a new experiment's first plan revises none")
        return Authorization(revision=None, repeats={}, used=())
    if synthetic != experiment.synthetic:
        raise _another_kind(synthetic=experiment.synthetic)
    to_make, used = confirmed_repeats(plan, experiment, repeats)
    revision = _approved(plan, approved_hash, experiment, reason)
    return Authorization(revision=revision, repeats=to_make, used=used)


def _approved(
    plan: AnyPlan, approved_hash: str, experiment: SavedExperiment, reason: str | None
) -> ApprovedRevision | None:
    """Checks the approval of a resumed experiment's plan: the current plan's, as a new plan's
    is, or a revision's, with its reason (approving a revision). Returns the revision, if it's
    one."""
    current = experiment.current.plan
    if plan == current:
        if reason is not None and reason != experiment.current.record.plans[-1].reason:
            raise _no_revision(
                "The configuration gives the experiment's current plan, so there's no"
                " revision to give a reason for: run it without a reason to resume it."
            )
        check_approval(plan, approved_hash)
        return None
    if plan.revises != current.plan_hash:
        raise ValueError("the plan is neither the experiment's current plan nor a revision")
    expected = plan_hash(plan)
    if reason is None or approved_hash != expected:
        missing = "a reason" if reason is None else "the approval of its hash"
        raise TrialFolioError(
            "plan.changed",
            "The configuration, or the installed versions, changed since the experiment's"
            f" current plan, and the revision wasn't approved: it needs {missing}. Approving"
            f" it takes its full hash, {expected}, and a reason for the revision. Nothing was"
            " sent.",
        )
    try:
        valid = _REASON.validate_python(reason)
    except ValidationError:
        raise ValueError("the reason isn't a valid revision reason") from None
    # Release 0.4.0's rules give what changed, which `revised_experiment_record_v1_1` records
    # as 0.3.0's while no plan of the experiment has a ranking definition.
    return ApprovedRevision(PlanRevisionV1_1(plan, plan_changes_v1_1(current, plan)), valid)


def _no_revision(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "plan.approval_required",
        f"A reason for a revision was given, but there's no revision. {problem} Nothing was sent.",
    )


def _another_kind(*, synthetic: bool) -> TrialFolioError:
    """The demo's client for an experiment that isn't synthetic, or another client for one
    that is: invented and real attempts never share an experiment."""
    if synthetic:
        problem = (
            "The output directory holds a synthetic experiment, whose values are invented, and"
            " only the demo's client resumes it."
        )
    else:
        problem = (
            "The output directory holds an experiment whose attempts are real, and the demo's"
            " client, which sends nothing, can't add invented ones to it."
        )
    return TrialFolioError(
        "output.not_empty",
        f"{problem} Nothing was sent or written. Run the configuration into another output"
        " directory.",
    )
