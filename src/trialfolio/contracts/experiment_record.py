"""An experiment's records of its plans and runs (docs/contracts.md, experiment output):

- `ExperimentRecord`: `plans/<n>/experiment.json`, schema version 1.0.0, the experiment as that
  plan declares it, and the history of its plans. The current plan's is the experiment's research
  record. It records no outcome.
- `SessionRecord`: `sessions/<s>/session.json`, schema version 1.0.0, written before any other
  record of a run, which it reserves the session's number for.
- `ExperimentRecordV1_1`: `experiment.json` 1.1.0, once the plan, or an earlier plan of the
  experiment, is plan 1.3.0: 1.0.0's, with a ranking variant's `set` and `remove` in each
  `variant`, and `ranking_source` among a revision's changed parts.

No field of `experiment.json` names its own plan, so whether its last entry is its directory's
plan, and whether its earlier entries are the previous plan's, is the records check's to say, on
resume. The model checks what one file can show.
"""

from collections.abc import Sequence
from itertools import pairwise
from typing import Annotated, Final, Literal, Self, get_args

from pydantic import Field, model_validator

from trialfolio.contracts.common import (
    BASELINE_CASE_KEY,
    Approval,
    CaseId,
    ContractModel,
    ExperimentKey,
    Ordinal,
    PackageVersion,
    Purpose,
    RevisionReason,
    SemanticVersion,
    Sha256Digest,
    ShortText,
    Title,
    UtcDatetime,
    require_unique,
)
from trialfolio.contracts.experiment_plan import (
    DeclaredPriorResearch,
    PlanVariant,
    PlanVariantV1_3,
)


class SessionRecord(ContractModel):
    """A session's record: one `run` of the experiment that passed its checks and its approval.
    Writing it reserves the session's number, which each attempt the session starts records."""

    schema_version: Literal["1.0.0"]
    trialfolio_version: SemanticVersion
    session: Ordinal
    started_at: UtcDatetime
    """When it was written."""


class RecordedCase(ContractModel):
    """A case as a plan holds it, without its settings and requests, which its `plan.json`
    holds."""

    case_key: ExperimentKey
    case_id: CaseId
    description: ShortText | None
    variant: PlanVariant | None
    """Null for the baseline."""

    @model_validator(mode="after")
    def _baseline(self) -> Self:
        _check_baseline(self)
        return self


def _check_baseline(case: "RecordedCase | RecordedCaseV1_1") -> None:
    if (case.case_key == BASELINE_CASE_KEY) != (case.variant is None):
        raise ValueError("the baseline, and only the baseline, has no variant")
    if case.variant is None and case.description is not None:
        raise ValueError("the baseline has no description")


class RetiredCase(RecordedCase):
    """A case an earlier plan included and this one doesn't, as the last plan that included it
    held it. It and its attempts stay in the record."""

    plan: Ordinal
    """The number of the last plan that included it."""


VersionedPackage = Literal["trialfolio", "p123api", "requests", "urllib3"]

VERSIONED_PACKAGES: Final[tuple[VersionedPackage, ...]] = get_args(VersionedPackage)


class VersionChange(ContractModel):
    """A version a revision changed: of Trial Folio, or of a package that sends its requests."""

    package: VersionedPackage
    previous: PackageVersion
    current: PackageVersion

    @model_validator(mode="after")
    def _changed(self) -> Self:
        if self.previous == self.current:
            raise ValueError("a changed version differs from the previous one")
        return self


class CaseChange(ContractModel):
    """A case a revision added or retired, by its `case_id`, and its key: in the revision for an
    added case, and in the plan before it for a retired one."""

    case_id: CaseId
    case_key: ExperimentKey


RevisedPart = Literal[
    "title",
    "purpose",
    "prior_research",
    "budget",
    "case_keys",
    "case_descriptions",
    "case_variants",
    "case_order",
]
"""A part of the plan a revision changed, other than its versions and its cases."""

REVISED_PARTS: Final[tuple[RevisedPart, ...]] = get_args(RevisedPart)


class PlanChanges(ContractModel):
    """What a revision changed from the plan before it. One whose only change is of versions
    records nothing else: it's a change of versions, not of the configuration."""

    versions: tuple[VersionChange, ...]
    """Each version that changed, with both values, in the order Trial Folio, `p123api`,
    `requests`, `urllib3`."""
    cases_added: tuple[CaseChange, ...]
    cases_retired: tuple[CaseChange, ...]
    parts: tuple[RevisedPart, ...]
    """In the documented order: `title`, `purpose`, `prior_research`, `budget`, `case_keys`,
    `case_descriptions`, `case_variants`, `case_order`."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_changes(self, REVISED_PARTS)
        return self


def _check_changes(changes: "PlanChanges | PlanChangesV1_1", documented: Sequence[str]) -> None:
    packages = [VERSIONED_PACKAGES.index(change.package) for change in changes.versions]
    if packages != sorted(set(packages)):
        raise ValueError("each package's version change appears once, in the documented order")
    parts = [documented.index(part) for part in changes.parts]
    if parts != sorted(set(parts)):
        raise ValueError("each part appears once, in the documented order")
    added = tuple(case.case_id for case in changes.cases_added)
    retired = tuple(case.case_id for case in changes.cases_retired)
    require_unique(added + retired, "the cases added and retired")
    if not (changes.versions or added or retired or changes.parts):
        raise ValueError("a revision changes something a plan holds")


class PlanEntry(ContractModel):
    """One plan of the experiment, in the history of its plans."""

    plan: Ordinal
    """Its number: its directory's, `plans/<n>/`."""
    plan_hash: Sha256Digest
    revises: Sha256Digest | None
    """The hash of the plan before it; null for the first plan."""
    plan_artifact_id: Sha256Digest
    """The `artifact_id` of its `plan.json`."""
    configuration_artifact_id: Sha256Digest
    """The `artifact_id` of its `configuration.yaml`."""
    approval: Approval
    """`not_required` for each plan of a synthetic experiment, and for no other plan."""
    reason: RevisionReason | None
    """The revision's reason, as `--revision-reason` gave it, with `user_supplied` provenance;
    null for the first plan."""
    changes: PlanChanges | None
    """What the revision changed from the plan before it; null for the first plan."""

    @model_validator(mode="after")
    def _revision(self) -> Self:
        _check_entry(self)
        return self


def _check_entry(entry: "PlanEntry | PlanEntryV1_1") -> None:
    if not (entry.revises is None) == (entry.reason is None) == (entry.changes is None):
        raise ValueError("a revision, and only a revision, has revises, a reason, and changes")
    if entry.revises == entry.plan_hash:
        raise ValueError("a plan doesn't revise itself")


class ExperimentRecord(ContractModel):
    """`experiment.json`: the experiment as its plan declares it, and every plan so far, oldest
    first, ending with its own. It records no outcome: attempts end after it's written."""

    schema_version: Literal["1.0.0"]
    trialfolio_version: SemanticVersion
    created_at: UtcDatetime
    experiment_id: ExperimentKey
    title: Title
    purpose: Purpose
    prior_research: DeclaredPriorResearch
    """As the user declared it. Trial Folio can't verify it."""
    planned_cases: Annotated[tuple[RecordedCase, ...], Field(min_length=2)]
    """The plan's cases, in its order, the baseline first."""
    retired_cases: tuple[RetiredCase, ...]
    plans: Annotated[tuple[PlanEntry, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_record(self)
        return self


def _check_record(record: "ExperimentRecord | ExperimentRecordV1_1") -> None:
    """Raises `ValueError` unless the record is consistent, by what one file can show: its plans'
    history, its planned and retired cases, and its last revision's changes."""
    _check_plans(record.plans)
    if record.planned_cases[0].case_key != BASELINE_CASE_KEY:
        raise ValueError("the first planned case is the baseline")
    require_unique(tuple(case.case_key for case in record.planned_cases), "planned case keys")
    planned = tuple(case.case_id for case in record.planned_cases)
    retired = tuple(case.case_id for case in record.retired_cases)
    require_unique(planned + retired, "the planned and retired cases' IDs")
    numbers = [entry.plan for entry in record.plans]
    if any(case.plan not in numbers[:-1] for case in record.retired_cases):
        raise ValueError("a retired case's plan is an earlier plan of the history")
    _check_last_revision(record)


def _check_plans(plans: "Sequence[PlanEntry | PlanEntryV1_1]") -> None:
    if plans[0].plan != 1:
        raise ValueError("the plans are numbered from 1")
    for previous, entry in pairwise(plans):
        if entry.plan <= previous.plan:
            raise ValueError("the plans come oldest first, each numbered after the last")
        if entry.revises != previous.plan_hash:
            raise ValueError("each revision revises the plan before it")
    if plans[0].revises is not None:
        raise ValueError("the first plan revises none")
    require_unique(tuple(entry.plan_hash for entry in plans), "plan hashes")
    synthetic = [entry.approval == "not_required" for entry in plans]
    if any(synthetic) and not all(synthetic):
        raise ValueError("every plan records the approval not_required, or none does")


def _check_last_revision(record: "ExperimentRecord | ExperimentRecordV1_1") -> None:
    # A first plan has retired no case: none has an earlier plan.
    if len(record.plans) < 2:
        return
    changes = record.plans[-1].changes
    if changes is None:  # every entry after the first is a revision
        raise ValueError("a revision records its changes")
    planned = {(case.case_id, case.case_key) for case in record.planned_cases}
    if any((case.case_id, case.case_key) not in planned for case in changes.cases_added):
        raise ValueError("each case the revision added is a planned case, with its key")
    previous = record.plans[-2].plan
    retired_now = {
        (case.case_id, case.case_key) for case in record.retired_cases if case.plan == previous
    }
    if {(case.case_id, case.case_key) for case in changes.cases_retired} != retired_now:
        raise ValueError(
            "the cases the revision retired are the retired cases the plan before it included"
        )


# Version 1.1.0: an experiment whose plan, or an earlier plan, is plan 1.3.0.


class RecordedCaseV1_1(ContractModel):
    """A case as a plan holds it, in `experiment.json` 1.1.0: its `variant` holds a ranking
    variant's `set` and `remove`, null in a variant of another setting, and in an entry taken from
    a 1.0.0 `experiment.json`."""

    case_key: ExperimentKey
    case_id: CaseId
    description: ShortText | None
    variant: PlanVariantV1_3 | None
    """Null for the baseline."""

    @model_validator(mode="after")
    def _baseline(self) -> Self:
        _check_baseline(self)
        return self


class RetiredCaseV1_1(RecordedCaseV1_1):
    """A case an earlier plan included and this one doesn't, as the last plan that included it
    held it. It and its attempts stay in the record."""

    plan: Ordinal
    """The number of the last plan that included it."""


RevisedPartV1_1 = Literal[
    "title",
    "purpose",
    "prior_research",
    "budget",
    "ranking_source",
    "case_keys",
    "case_descriptions",
    "case_variants",
    "case_order",
]
"""A part of the plan a revision changed, in `experiment.json` 1.1.0: 1.0.0's, with
`ranking_source`, the definition's source, which changes no case."""

REVISED_PARTS_V1_1: Final[tuple[RevisedPartV1_1, ...]] = get_args(RevisedPartV1_1)


class PlanChangesV1_1(ContractModel):
    """What a revision changed from the plan before it, in `experiment.json` 1.1.0: 1.0.0's, and
    a change of the definition's source alone."""

    versions: tuple[VersionChange, ...]
    """Each version that changed, with both values, in the order Trial Folio, `p123api`,
    `requests`, `urllib3`."""
    cases_added: tuple[CaseChange, ...]
    cases_retired: tuple[CaseChange, ...]
    parts: tuple[RevisedPartV1_1, ...]
    """In the documented order: `title`, `purpose`, `prior_research`, `budget`,
    `ranking_source`, `case_keys`, `case_descriptions`, `case_variants`, `case_order`."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_changes(self, REVISED_PARTS_V1_1)
        return self


class PlanEntryV1_1(ContractModel):
    """One plan of the experiment, in the history of its plans, in `experiment.json` 1.1.0."""

    plan: Ordinal
    """Its number: its directory's, `plans/<n>/`."""
    plan_hash: Sha256Digest
    revises: Sha256Digest | None
    """The hash of the plan before it; null for the first plan."""
    plan_artifact_id: Sha256Digest
    """The `artifact_id` of its `plan.json`."""
    configuration_artifact_id: Sha256Digest
    """The `artifact_id` of its `configuration.yaml`."""
    approval: Approval
    """`not_required` for each plan of a synthetic experiment, and for no other plan."""
    reason: RevisionReason | None
    """The revision's reason, as `--revision-reason` gave it, with `user_supplied` provenance;
    null for the first plan."""
    changes: PlanChangesV1_1 | None
    """What the revision changed from the plan before it; null for the first plan."""

    @model_validator(mode="after")
    def _revision(self) -> Self:
        _check_entry(self)
        return self


class ExperimentRecordV1_1(ContractModel):
    """`experiment.json` 1.1.0: the experiment as its plan declares it, and every plan so far,
    oldest first, ending with its own, once a plan of the experiment is plan 1.3.0. It records no
    outcome: attempts end after it's written."""

    schema_version: Literal["1.1.0"]
    trialfolio_version: SemanticVersion
    created_at: UtcDatetime
    experiment_id: ExperimentKey
    title: Title
    purpose: Purpose
    prior_research: DeclaredPriorResearch
    """As the user declared it. Trial Folio can't verify it."""
    planned_cases: Annotated[tuple[RecordedCaseV1_1, ...], Field(min_length=2)]
    """The plan's cases, in its order, the baseline first."""
    retired_cases: tuple[RetiredCaseV1_1, ...]
    plans: Annotated[tuple[PlanEntryV1_1, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_record(self)
        return self
