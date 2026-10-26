"""An experiment's revisions, and its `experiment.json` (docs/contracts.md, experiment plans and
revisions, `experiment.json`, and plans with a ranking definition).

- `plan_revision` builds an experiment's plan again for a run into its own output directory, and
  gives the revision of its current plan, with what changed, or None when the configuration and
  the versions give the current plan, which the run resumes. `plan_changes` gives what a
  revision changed, which the executor records when it's given the revision's plan.
- `first_experiment_record` and `revised_experiment_record` give the `experiment.json` of a
  plan: the experiment as the plan declares it, its retired cases, and the history of its plans.
- `plan_revision_v1_1`, `plan_changes_v1_1`, and `retired_cases_v1_1` revise an experiment's plan
  1.1.0 or 1.3.0 by 0.3.0's rules, so a changed definition or ranking method is a changed
  setting, and a plan 1.1.0 can be revised into a 1.3.0, or back; and
  `first_experiment_record_v1_1` and `revised_experiment_record_v1_1` give its `experiment.json`,
  1.1.0 once a plan of the experiment is 1.3.0, and 1.0.0 otherwise.

Each of 0.3.0's functions and its 0.4.0 counterpart share their steps, and differ only in the
models they build, and in the form of a case's variant, which 1.1.0 gives with `set` and
`remove`. The 0.4.0 functions take either version, so a caller needn't choose between the two:
`revised_experiment_record_v1_1` records a revision's changes as 0.3.0's while the experiment's
`experiment.json` is 1.0.0, and the retired cases of `retired_cases_v1_1` are those of
`retired_cases`, one for one.
"""

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime

from trialfolio.configuration import ExperimentConfigurationRead
from trialfolio.contracts.common import Approval
from trialfolio.contracts.experiment_configuration import (
    ExperimentConfiguration,
    ExperimentConfigurationV1_1,
)
from trialfolio.contracts.experiment_plan import (
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanV1_1,
    PlanV1_3,
    PlanVariant,
    PlanVariantV1_3,
)
from trialfolio.contracts.experiment_record import (
    REVISED_PARTS,
    REVISED_PARTS_V1_1,
    VERSIONED_PACKAGES,
    CaseChange,
    ExperimentRecord,
    ExperimentRecordV1_1,
    PlanChanges,
    PlanChangesV1_1,
    PlanEntry,
    PlanEntryV1_1,
    RecordedCase,
    RecordedCaseV1_1,
    RetiredCase,
    RetiredCaseV1_1,
    RevisedPartV1_1,
    VersionChange,
)
from trialfolio.errors import TrialFolioError
from trialfolio.planning.experiment import build_experiment_plan, build_experiment_plan_v1_1
from trialfolio.planning.hashing import plan_hash
from trialfolio.planning.versions import Versions


@dataclass(frozen=True)
class PlanRevision:
    """A revision of an experiment's current plan: the plan a run approves in its place, and what
    changed from the current plan, which the revision's `experiment.json` records."""

    plan: PlanV1_1
    """Its `revises` is the current plan's hash."""
    changes: PlanChanges


@dataclass(frozen=True)
class PlanRevisionV1_1:
    """A revision of an experiment's current plan, 1.1.0 or 1.3.0, by release 0.4.0's rules: the
    plan a run approves in its place, 1.1.0 or 1.3.0, and what changed, as `experiment.json`
    1.1.0 records it, `ranking_source` among the parts."""

    plan: PlanV1_1 | PlanV1_3
    """Its `revises` is the current plan's hash."""
    changes: PlanChangesV1_1


def _another_experiment(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "output.not_empty",
        f"{problem} The directory's records stay as they are, and nothing was sent. Run the "
        "configuration into a new output directory.",
    )


def _universe(plan: PlanV1_1 | PlanV1_3) -> object:
    """The baseline's universe, which every case of the plan uses."""
    (universe,) = (row.value for row in plan.cases[0].settings if row.setting == "universe")
    return universe


def _check_experiment(
    configuration: ExperimentConfiguration | ExperimentConfigurationV1_1,
    current: PlanV1_1 | PlanV1_3,
) -> None:
    """Raises `TrialFolioError` with `output.not_empty` when the configuration's `experiment_id`,
    or its baseline's universe, isn't the current plan's: either makes another experiment."""
    if configuration.experiment_id != current.experiment_id:
        raise _another_experiment(
            "The configuration's `experiment_id` isn't that of the experiment in the output "
            "directory, so it's another experiment, which can't run there."
        )
    if configuration.baseline.universe != _universe(current):
        raise _another_experiment(
            "The configuration's baseline has another universe than the experiment in the output "
            "directory. Another universe is another experiment, not a revision of this one, so "
            "it can't run there."
        )


def _revised[P: (PlanV1_1, PlanV1_1 | PlanV1_3)](
    build: Callable[[str | None], P], current: PlanV1_1 | PlanV1_3
) -> P | None:
    """The plan `build` gives, with its `revises` set to the hash of `current`, the experiment's
    current plan, recomputed from its contents; or None when `build` gives the current plan, with
    the current plan's own `revises`."""
    current_hash = plan_hash(current)
    if build(current.revises).plan_hash == current_hash:
        return None
    return build(current_hash)


def plan_revision(
    configuration: ExperimentConfiguration, versions: Versions, current: PlanV1_1
) -> PlanRevision | None:
    """Builds the experiment's plan again, for a run of its configuration into its own output
    directory, and compares it with `current`, the experiment's current plan (docs/contracts.md,
    experiment plans and revisions).

    Returns None when the configuration and the versions give the current plan, which the run
    then resumes. That's so even when the file is written differently, in a way no plan records.
    Anything else is a revision: that plan, with its `revises` set to the current plan's hash,
    recomputed from its contents, and what changed.

    Raises `TrialFolioError` with `output.not_empty` when the configuration's `experiment_id`, or
    its baseline's universe, isn't the current plan's: either makes another experiment, not a
    revision. Raises it with `environment.unsupported` as `build_experiment_plan` does.
    """
    _check_experiment(configuration, current)
    revision = _revised(
        lambda revises: build_experiment_plan(configuration, versions, revises), current
    )
    return None if revision is None else PlanRevision(revision, plan_changes(current, revision))


def plan_revision_v1_1(
    read: ExperimentConfigurationRead, versions: Versions, current: PlanV1_1 | PlanV1_3
) -> PlanRevisionV1_1 | None:
    """Builds the experiment's plan again, as `build_experiment_plan_v1_1` builds it from what
    release 0.4.0's reader read, and compares it with `current`, the experiment's current plan,
    1.1.0 or 1.3.0, by the rules `plan_revision` follows (plans with a ranking definition,
    revisions).

    A changed definition, or ranking method, is a changed setting of the baseline, so its cases
    are new, and the cases it no longer gives are retired; a ranking variant whose definition
    stays the same, byte for byte, keeps its case. A ranking given another way, such as a
    definition in place of a formula, revises a plan 1.1.0 into a 1.3.0, or back.

    Returns None when the configuration and the versions give the current plan, and otherwise
    the revision, with what changed, as `experiment.json` 1.1.0 records it. Raises
    `TrialFolioError` as `plan_revision` does, and `TypeError` as `build_experiment_plan_v1_1`
    does.
    """
    _check_experiment(read.configuration, current)
    revision = _revised(
        lambda revises: build_experiment_plan_v1_1(read, versions, revises), current
    )
    return (
        None
        if revision is None
        else PlanRevisionV1_1(revision, plan_changes_v1_1(current, revision))
    )


def _variant_v1_3(variant: PlanVariant | PlanVariantV1_3 | None) -> PlanVariantV1_3 | None:
    """A case's `variant` as plan 1.3.0 and `experiment.json` 1.1.0 hold it: a 1.1.0 plan's, or
    a 1.0.0 `experiment.json`'s, with `set` and `remove` null, and otherwise unchanged."""
    if variant is None or isinstance(variant, PlanVariantV1_3):
        return variant
    return PlanVariantV1_3.model_validate(
        variant.model_dump(mode="json") | {"set": None, "remove": None}
    )


def _source_changed(previous: PlanV1_1 | PlanV1_3, revision: PlanV1_1 | PlanV1_3) -> bool:
    """Whether the definition's source changed, other than by its definition, whose change the
    cases record: so a change of its form, such as a snapshot of the definition a file held. A
    ranking given another way, which one of the plans gives no source, changes the cases
    instead."""
    if not (isinstance(previous, PlanV1_3) and isinstance(revision, PlanV1_3)):
        return False
    before, after = previous.ranking_source, revision.ranking_source
    return before.model_dump(exclude={"definition"}) != after.model_dump(exclude={"definition"})


def _changes(
    previous: PlanV1_1 | PlanV1_3, revision: PlanV1_1 | PlanV1_3, parts: Sequence[RevisedPartV1_1]
) -> dict[str, object]:
    """What the revision changed from the plan before it, with the changed parts of `parts`, as
    `experiment.json` records them."""
    before, after = asdict(Versions.of(previous)), asdict(Versions.of(revision))
    earlier = {case.case_id: case for case in previous.cases}
    later = {case.case_id: case for case in revision.cases}
    kept = [(earlier[case.case_id], case) for case in revision.cases if case.case_id in earlier]
    changed: dict[RevisedPartV1_1, bool] = {
        "title": previous.title != revision.title,
        "purpose": previous.purpose != revision.purpose,
        "prior_research": previous.prior_research != revision.prior_research,
        # Another version of the budget, with each operation's cost, is another budget too.
        "budget": previous.budget != revision.budget,
        "ranking_source": _source_changed(previous, revision),
        "case_keys": any(old.case_key != new.case_key for old, new in kept),
        "case_descriptions": any(old.description != new.description for old, new in kept),
        "case_variants": any(
            _variant_v1_3(old.variant) != _variant_v1_3(new.variant) for old, new in kept
        ),
        "case_order": [case.case_id for case in previous.cases if case.case_id in later]
        != [new.case_id for _, new in kept],
    }
    # Everything else a plan holds follows from these and Trial Folio's own code, so a plan that
    # differs in none of them was built by other code under the same version: the model refuses
    # a revision that records no change.
    return {
        "versions": tuple(
            VersionChange(package=package, previous=before[package], current=after[package])
            for package in VERSIONED_PACKAGES
            if before[package] != after[package]
        ),
        "cases_added": tuple(
            CaseChange(case_id=case.case_id, case_key=case.case_key)
            for case in revision.cases
            if case.case_id not in earlier
        ),
        "cases_retired": tuple(
            CaseChange(case_id=case.case_id, case_key=case.case_key)
            for case in previous.cases
            if case.case_id not in later
        ),
        "parts": tuple(part for part in parts if changed[part]),
    }


def plan_changes(previous: PlanV1_1, revision: PlanV1_1) -> PlanChanges:
    """What the revision changed from the plan before it: each version that changed, with both
    values; the cases it added, in its order, and those it retired, in the previous plan's; and
    which other parts changed.

    A case is its `case_id`, so a case whose settings didn't change is kept. `case_keys`,
    `case_descriptions`, and `case_variants` are changes to a kept case, and `case_order` a new
    order of the kept cases. An added or retired case is recorded as that alone, even when it has
    a retired case's key.
    """
    return PlanChanges.model_validate(_changes(previous, revision, REVISED_PARTS))


def plan_changes_v1_1(
    previous: PlanV1_1 | PlanV1_3, revision: PlanV1_1 | PlanV1_3
) -> PlanChangesV1_1:
    """What the revision changed from the plan before it, 1.1.0 or 1.3.0, as `plan_changes`
    gives it, and as `experiment.json` 1.1.0 records it: with `ranking_source` among the parts
    when the definition's source changed, other than by its definition, as when a snapshot of the
    definition a file held takes the file's place, which keeps every case. A changed definition,
    and a ranking given another way, change the cases instead (`experiment.json`)."""
    return PlanChangesV1_1.model_validate(_changes(previous, revision, REVISED_PARTS_V1_1))


# experiment.json


def _recorded(
    case: ExperimentPlanCase | ExperimentPlanCaseV1_3 | RecordedCase | RecordedCaseV1_1,
) -> dict[str, object]:
    """A case as `experiment.json` 1.0.0 records it."""
    return {
        "case_key": case.case_key,
        "case_id": case.case_id,
        "description": case.description,
        "variant": case.variant,
    }


def _recorded_v1_1(
    case: ExperimentPlanCase | ExperimentPlanCaseV1_3 | RecordedCase | RecordedCaseV1_1,
) -> dict[str, object]:
    """A case as `experiment.json` 1.1.0 records it: as 1.0.0 does, with its variant in plan
    1.3.0's form."""
    return _recorded(case) | {"variant": _variant_v1_3(case.variant)}


def _record_fields(
    plan: PlanV1_1 | PlanV1_3,
    planned: Sequence[RecordedCase] | Sequence[RecordedCaseV1_1],
    retired: Sequence[RetiredCase] | Sequence[RetiredCaseV1_1],
    plans: Sequence[PlanEntry] | Sequence[PlanEntryV1_1],
    at: datetime,
) -> dict[str, object]:
    """What `experiment.json` holds, but its schema version: the experiment as `plan` declares
    it, its planned and retired cases, and the history of its plans, written at `at`."""
    return {
        # Written in the run that built the plan, so by the Trial Folio the plan records.
        "trialfolio_version": plan.trialfolio_version,
        "created_at": at,
        "experiment_id": plan.experiment_id,
        "title": plan.title,
        "purpose": plan.purpose,
        "prior_research": plan.prior_research,
        "planned_cases": tuple(planned),
        "retired_cases": tuple(retired),
        "plans": tuple(plans),
    }


def _record(
    plan: PlanV1_1, retired: tuple[RetiredCase, ...], plans: tuple[PlanEntry, ...], at: datetime
) -> ExperimentRecord:
    planned = [RecordedCase.model_validate(_recorded(case)) for case in plan.cases]
    return ExperimentRecord.model_validate(
        {"schema_version": "1.0.0", **_record_fields(plan, planned, retired, plans, at)}
    )


def _record_v1_1(
    plan: PlanV1_1 | PlanV1_3,
    retired: tuple[RetiredCaseV1_1, ...],
    plans: tuple[PlanEntryV1_1, ...],
    at: datetime,
) -> ExperimentRecordV1_1:
    planned = [RecordedCaseV1_1.model_validate(_recorded_v1_1(case)) for case in plan.cases]
    return ExperimentRecordV1_1.model_validate(
        {"schema_version": "1.1.0", **_record_fields(plan, planned, retired, plans, at)}
    )


def _entry[E: (PlanEntry, PlanEntryV1_1)](
    model: type[E],
    number: int,
    plan: PlanV1_1 | PlanV1_3,
    *,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    reason: str | None = None,
    changes: PlanChanges | PlanChangesV1_1 | None = None,
) -> E:
    """The entry of `plan`, the experiment's plan `number`, in the history of its plans, as
    `model`, 1.0.0's or 1.1.0's: with no reason or changes for the first plan."""
    return model.model_validate(
        {
            "plan": number,
            "plan_hash": plan_hash(plan),
            "revises": plan.revises,
            "plan_artifact_id": plan_artifact_id,
            "configuration_artifact_id": configuration_artifact_id,
            "approval": approval,
            "reason": reason,
            "changes": changes,
        }
    )


def first_experiment_record(
    plan: PlanV1_1,
    *,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    created_at: datetime,
) -> ExperimentRecord:
    """The `experiment.json` of an experiment's first plan, in `plans/1/` (docs/contracts.md,
    `experiment.json`): the experiment as the plan declares it, its planned cases, no retired
    case, and the plan's entry, with no reason or changes.

    `plan_artifact_id` and `configuration_artifact_id` are those of the plan's `plan.json` and
    `configuration.yaml`, and `approval` is how the plan was approved, `not_required` only for a
    synthetic experiment.

    Raises `ValueError` when `plan` revises another plan.
    """
    entry = _entry(
        PlanEntry,
        1,
        plan,
        plan_artifact_id=plan_artifact_id,
        configuration_artifact_id=configuration_artifact_id,
        approval=approval,
    )
    return _record(plan, (), (entry,), created_at)


def first_experiment_record_v1_1(
    plan: PlanV1_1 | PlanV1_3,
    *,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    created_at: datetime,
) -> ExperimentRecord | ExperimentRecordV1_1:
    """The `experiment.json` of an experiment's first plan, 1.1.0 or 1.3.0, as
    `first_experiment_record` gives it: version 1.1.0 for a plan 1.3.0, whose cases' variants
    hold `set` and `remove`, and 1.0.0 for a plan 1.1.0 (`experiment.json`).

    Raises `ValueError` when `plan` revises another plan.
    """
    if isinstance(plan, PlanV1_1):
        return first_experiment_record(
            plan,
            plan_artifact_id=plan_artifact_id,
            configuration_artifact_id=configuration_artifact_id,
            approval=approval,
            created_at=created_at,
        )
    entry = _entry(
        PlanEntryV1_1,
        1,
        plan,
        plan_artifact_id=plan_artifact_id,
        configuration_artifact_id=configuration_artifact_id,
        approval=approval,
    )
    return _record_v1_1(plan, (), (entry,), created_at)


def _retired(
    previous: ExperimentRecord | ExperimentRecordV1_1, plan: PlanV1_1 | PlanV1_3
) -> list[tuple[RecordedCase | RecordedCaseV1_1, int]]:
    """Each retired case of the experiment once `plan` is its current plan, with the number of
    the last plan that included it: `previous`'s retired cases, without each case `plan` includes
    again, followed by each case the current plan included and `plan` doesn't, as the current plan
    held it, with its number."""
    planned = {case.case_id for case in plan.cases}
    current = previous.plans[-1].plan
    return [
        *((case, case.plan) for case in previous.retired_cases if case.case_id not in planned),
        *((case, current) for case in previous.planned_cases if case.case_id not in planned),
    ]


def retired_cases(previous: ExperimentRecord, plan: PlanV1_1) -> tuple[RetiredCase, ...]:
    """The retired cases of the experiment once `plan` is its current plan, from `previous`, the
    current plan's `experiment.json`: `previous`'s retired cases, without each case `plan`
    includes again, followed by each case the current plan included and `plan` doesn't, as the
    current plan held it, with its number. With the current plan itself, they're `previous`'s."""
    return tuple(
        RetiredCase.model_validate({**_recorded(case), "plan": number})
        for case, number in _retired(previous, plan)
    )


def retired_cases_v1_1(
    previous: ExperimentRecord | ExperimentRecordV1_1, plan: PlanV1_1 | PlanV1_3
) -> tuple[RetiredCaseV1_1, ...]:
    """The retired cases of the experiment once `plan`, 1.1.0 or 1.3.0, is its current plan, as
    `retired_cases` gives them, as `experiment.json` 1.1.0 holds them: an entry taken from a
    1.0.0 `experiment.json` with its variant's `set` and `remove` null."""
    return tuple(
        RetiredCaseV1_1.model_validate({**_recorded_v1_1(case), "plan": number})
        for case, number in _retired(previous, plan)
    )


def revised_experiment_record(
    previous: ExperimentRecord,
    revision: PlanRevision,
    *,
    number: int,
    reason: str,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    created_at: datetime,
) -> ExperimentRecord:
    """The `experiment.json` of a revision, in `plans/<number>/`, from the current plan's,
    `previous` (docs/contracts.md, `experiment.json`).

    It holds the experiment as the revision declares it, and its planned cases. Its retired cases
    are `previous`'s, without each case the revision includes again, followed by each case the
    current plan included and the revision doesn't, as the current plan held it, with its number.
    Its plans are `previous`'s, unchanged, followed by the revision's entry, with `reason`, the
    revision's `--revision-reason`, and what changed.

    Raises `ValueError` when the records don't fit together: when `number` isn't above the
    current plan's, the revision doesn't revise it, or `previous` isn't its record, as the
    revision's changes show; or when `reason` isn't a valid reason.
    """
    retired = retired_cases(previous, revision.plan)
    entry = _entry(
        PlanEntry,
        number,
        revision.plan,
        plan_artifact_id=plan_artifact_id,
        configuration_artifact_id=configuration_artifact_id,
        approval=approval,
        reason=reason,
        changes=revision.changes,
    )
    return _record(revision.plan, retired, (*previous.plans, entry), created_at)


def revised_experiment_record_v1_1(
    previous: ExperimentRecord | ExperimentRecordV1_1,
    revision: PlanRevisionV1_1,
    *,
    number: int,
    reason: str,
    plan_artifact_id: str,
    configuration_artifact_id: str,
    approval: Approval,
    created_at: datetime,
) -> ExperimentRecord | ExperimentRecordV1_1:
    """The `experiment.json` of a revision, 1.1.0 or 1.3.0, as `revised_experiment_record` gives
    it, from the current plan's, `previous`, 1.0.0 or 1.1.0 (`experiment.json`).

    It's version 1.1.0 once the revision, or an earlier plan of the experiment, is plan 1.3.0,
    which `previous` being 1.1.0 shows: its cases' variants hold `set` and `remove`, null in a
    variant of another setting, and an entry taken from a 1.0.0 `experiment.json` is written with
    them null, and is otherwise unchanged, so the history can still be checked one plan at a
    time. Otherwise it's 1.0.0, as `revised_experiment_record` gives it.

    Raises `ValueError` as `revised_experiment_record` does.
    """
    plan = revision.plan
    if isinstance(previous, ExperimentRecord) and isinstance(plan, PlanV1_1):
        # No plan of the experiment is 1.3.0, so no part names the definition's source.
        changes = PlanChanges.model_validate_json(revision.changes.model_dump_json())
        return revised_experiment_record(
            previous,
            PlanRevision(plan, changes),
            number=number,
            reason=reason,
            plan_artifact_id=plan_artifact_id,
            configuration_artifact_id=configuration_artifact_id,
            approval=approval,
            created_at=created_at,
        )
    entry = _entry(
        PlanEntryV1_1,
        number,
        plan,
        plan_artifact_id=plan_artifact_id,
        configuration_artifact_id=configuration_artifact_id,
        approval=approval,
        reason=reason,
        changes=revision.changes,
    )
    plans = tuple(
        PlanEntryV1_1.model_validate_json(earlier.model_dump_json()) for earlier in previous.plans
    )
    return _record_v1_1(plan, retired_cases_v1_1(previous, plan), (*plans, entry), created_at)
