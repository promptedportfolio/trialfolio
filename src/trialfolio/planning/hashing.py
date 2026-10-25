"""A plan's hash, and the check of its approval (docs/contracts.md, plan hashing, and approval),
for a plan of any kind and version.

`plan_hash` recomputes a plan's hash from its contents, never from its stored `plan_hash`, and
`check_approval` passes only exactly that hash. `hashed` gives a plan built with `UNHASHED` its
hash.
"""

from typing import Final

from trialfolio.canonical import canonical_json, sha256_hex
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotPlan
from trialfolio.errors import TrialFolioError

type AnyPlan = Plan | PlanV1_1 | PlanV1_2 | PlanV1_3 | RankingSnapshotPlan
"""A screen's or an experiment's plan, of any version, or a ranking snapshot's."""


def plan_hash(plan: AnyPlan) -> str:
    """`sha256:` and the SHA-256 of the canonical form of `plan` without its `plan_hash` field
    (plan hashing). It's computed from the contents, so a stored `plan_hash` is never trusted."""
    content = plan.model_dump(mode="json", exclude={"plan_hash"})
    return "sha256:" + sha256_hex(canonical_json(content))


UNHASHED: Final = "sha256:" + "0" * 64
"""A placeholder, replaced by the plan's hash before the plan leaves the function that builds
it."""


def hashed[P: (Plan, PlanV1_1, PlanV1_2, PlanV1_3, RankingSnapshotPlan)](draft: P) -> P:
    # The draft was validated whole. Its hash is well formed, so the copy needs no validation.
    return draft.model_copy(update={"plan_hash": plan_hash(draft)})


def check_approval(plan: AnyPlan, approved_hash: str | None) -> str:
    """Returns the plan's hash when `approved_hash` is exactly that hash, recomputed from the
    plan's contents: the full hash, `sha256:` and 64 lowercase hex digits (approval).

    Raises `TrialFolioError` with `plan.approval_required` otherwise, including for an
    abbreviated or uppercase hash, or none.
    """
    expected = plan_hash(plan)
    if approved_hash != expected:
        given = (
            "No approval was given."
            if approved_hash is None
            else "The hash given isn't this plan's hash."
        )
        raise TrialFolioError(
            "plan.approval_required",
            f"Running this plan needs its approval: its full hash, {expected}, exactly as "
            f"shown. {given} Nothing was sent.",
        )
    return expected
