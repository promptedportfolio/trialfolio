"""An experiment's plan, `plan.json`, schema version 1.1.0 (docs/contracts.md, experiment plans
and revisions).

A 1.1.0 plan has a 1.0.0 plan's fields, with the experiment's research context, every case with
its `case_key`, `description`, and `variant`, and `revises`, the hash of the plan it revises. A
screen's plan stays 1.0.0. As for 1.0.0, the model describes a plan: building one, and computing
`case_id` and `plan_hash`, is the compiler's job, and the model recomputes neither.
"""

import json
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from trialfolio.contracts.common import (
    BASELINE_CASE_KEY,
    MAX_SAFE_INTEGER,
    CaseId,
    ContractModel,
    ExperimentKey,
    IntegerOnly,
    NonEmptyText,
    PriorResearchStatus,
    PriorResearchText,
    Purpose,
    SemanticVersion,
    Sha256Digest,
    ShortText,
    Title,
    TransportVersions,
    WrapperVersions,
    require_unique,
)
from trialfolio.contracts.experiment_configuration import (
    VARIANT_SETTINGS,
    VariantSetting,
    default_variant_key,
)
from trialfolio.contracts.plan import (
    DataSent,
    DocumentedSource,
    PlanRequest,
    PlanSetting,
    RetryPolicy,
    check_case,
)
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS_BY_NAME, check_value


class DeclaredPriorResearch(ContractModel):
    """The prior-research declaration as the configuration gives it, with `user_supplied`
    provenance. Trial Folio can't verify it."""

    status: PriorResearchStatus
    description: PriorResearchText | None
    """Given with `complete` or `partial`, and optionally with `unknown`; null when it isn't."""

    @model_validator(mode="after")
    def _described(self) -> Self:
        if self.status != "unknown" and self.description is None:
            raise ValueError("a declaration that's complete or partial has a description")
        return self


_VALUE_SETTINGS = frozenset({"max_holdings", "rebalance_weeks", "slippage_percent"})


class PlanVariant(ContractModel):
    """A case's variant: the setting it changes, and its change as the configuration gives it: a
    `value`, in the setting's JSON type, with a decimal as its normalized text; an `add`; or a
    `replace` and its `with`. Each key is always written, null where it doesn't apply."""

    model_config = ConfigDict(serialize_by_alias=True)

    setting: VariantSetting
    value: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)] | NonEmptyText | None
    add: NonEmptyText | None
    replace: NonEmptyText | None
    with_: Annotated[NonEmptyText | None, Field(alias="with")]
    default: bool
    """True for P-13's default rebalance variant, and false otherwise."""

    @model_validator(mode="after")
    def _one_change(self) -> Self:
        rule_change = (self.add, self.replace, self.with_)
        if self.setting in _VALUE_SETTINGS:
            if self.value is None or rule_change != (None, None, None):
                raise ValueError(f"a variant of {self.setting} gives a value, and nothing else")
            check_value(SCREEN_SETTINGS_BY_NAME[self.setting], self.value)
        elif self.value is not None or (self.add is None) == (self.replace is None):
            raise ValueError("a variant of rules gives add, or replace and with, and nothing else")
        elif (self.replace is None) != (self.with_ is None):
            raise ValueError("a variant of rules gives with exactly when it gives replace")
        if self.default and self.setting != "rebalance_weeks":
            raise ValueError("the default variant is a variant of rebalance_weeks")
        return self


class ExperimentPlanCase(ContractModel):
    """One case of an experiment: a 1.0.0 case, with its key, description, and variant. Its
    `case_id` covers only its settings, so it doesn't change with its key, description, or
    plan."""

    case_key: ExperimentKey
    case_id: CaseId
    description: ShortText | None
    """The variant's description, with `user_supplied` provenance; null when there's none, and
    for the baseline."""
    variant: PlanVariant | None
    """Null for the baseline."""
    requests: tuple[PlanRequest]
    settings: tuple[PlanSetting, ...]

    @model_validator(mode="after")
    def _screen_settings(self) -> Self:
        check_case(self.requests, self.settings)
        if (self.case_key == BASELINE_CASE_KEY) != (self.variant is None):
            raise ValueError("the baseline, and only the baseline, has no variant")
        if self.variant is None and self.description is not None:
            raise ValueError("the baseline has no description")
        return self


class PlanBudgetV1_1(ContractModel):
    """The experiment's request budget (docs/contracts.md, the budget across runs). It bounds the
    whole experiment: every attempt of every case, under every plan, in every run."""

    provider_requests: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
    """The configuration's `budget.provider_requests`: at least the number of cases."""
    credits_per_request: Annotated[int, Field(ge=0)]
    """Portfolio123's documented cost of one request when the plan was made."""
    credits_per_request_source: DocumentedSource
    credits: Annotated[int, Field(ge=0)]
    authentication_calls: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
    """Equal to `provider_requests`."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.credits != self.provider_requests * self.credits_per_request:
            raise ValueError("credits must equal provider_requests times credits_per_request")
        if self.authentication_calls != self.provider_requests:
            raise ValueError("authentication_calls must equal provider_requests")
        return self


def _changed_value(baseline: PlanSetting, variant: PlanVariant) -> object:
    """The value the variant gives its setting, from the baseline's value. Raises `ValueError`
    when the change changes nothing, or a `replace` isn't exactly one of the baseline's
    rules."""
    if variant.value is not None:
        if variant.value == baseline.value:
            raise ValueError("a variant's value differs from the baseline's")
        return variant.value
    rules = baseline.value
    if not isinstance(rules, tuple):  # the baseline's rules are valid, so a list of text
        raise ValueError("the baseline's rules must be a list")
    if variant.add is not None:
        if variant.add in rules:
            raise ValueError("a variant adds a rule the baseline doesn't have")
        return (*rules, variant.add)
    if rules.count(variant.replace) != 1:
        raise ValueError("a variant replaces exactly one of the baseline's rules")
    if variant.with_ in rules:
        raise ValueError("a variant replaces a rule with a formula the baseline doesn't have")
    return tuple(variant.with_ if rule == variant.replace else rule for rule in rules)


def _check_variant(baseline: ExperimentPlanCase, case: ExperimentPlanCase) -> str:
    """Raises `ValueError` unless the case's settings are the baseline's with exactly the change
    its variant gives. Returns the changed value's JSON text, which tells cases apart."""
    variant = case.variant
    if variant is None:
        raise ValueError("only the first case is the baseline")
    changed_text = ""
    for own, base in zip(case.settings, baseline.settings, strict=True):
        if own.setting != variant.setting:
            if own != base:
                raise ValueError(
                    f"a variant of {variant.setting} keeps the baseline's {own.setting}"
                )
            continue
        changed = _changed_value(base, variant)
        if own != base.model_copy(update={"value": changed}):
            raise ValueError(
                f"a variant's {own.setting} is the baseline's with exactly the variant's change"
            )
        changed_text = json.dumps(own.model_dump(mode="json")["value"])
    return changed_text


class PlanV1_1(ContractModel):
    """An experiment's plan: every case, the baseline first, its research context, the budget
    across runs, and the plan it revises. Execution requires its `plan_hash` as approval.
    """

    schema_version: Literal["1.1.0"]
    trialfolio_version: SemanticVersion
    canonicalization_version: Annotated[Literal[1], IntegerOnly]
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    experiment_id: ExperimentKey
    title: Title
    purpose: Purpose
    """An experiment's purpose is required, so it's never null."""
    prior_research: DeclaredPriorResearch
    revises: Sha256Digest | None
    """The `plan_hash` of the plan this one revises; null for the experiment's first plan."""
    cases: Annotated[tuple[ExperimentPlanCase, ...], Field(min_length=2)]
    """Every case, in the order of cases: the baseline first, then the variants of `rules`,
    `max_holdings`, `rebalance_weeks`, and `slippage_percent`."""
    budget: PlanBudgetV1_1
    retry_policy: RetryPolicy
    data_sent: Annotated[tuple[DataSent, ...], Field(min_length=3, max_length=3)]
    plan_hash: Sha256Digest

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        require_unique(tuple(entry.category for entry in self.data_sent), "data_sent categories")
        if self.revises == self.plan_hash:
            raise ValueError("a plan doesn't revise itself")
        baseline, *variants = self.cases
        if baseline.variant is not None:
            raise ValueError("the first case is the baseline")
        require_unique(tuple(case.case_key for case in self.cases), "case keys")
        require_unique(tuple(case.case_id for case in self.cases), "case IDs")
        changes = [_check_variant(baseline, case) for case in variants]
        settings = [case.variant.setting for case in variants if case.variant is not None]
        require_unique(tuple(zip(settings, changes, strict=True)), "the cases' settings")
        order = [VARIANT_SETTINGS.index(setting) for setting in settings]
        if order != sorted(order):
            raise ValueError("the variants come in the order of their settings")
        defaults = [case for case in variants if case.variant and case.variant.default]
        if defaults:
            if len(defaults) > 1 or settings.count("rebalance_weeks") > 1:
                raise ValueError("the default is an experiment's only rebalance variant")
            (default,) = defaults
            if default.variant is None or not isinstance(default.variant.value, int):
                raise ValueError("the default variant gives rebalance_weeks a value")
            if default.case_key != default_variant_key(default.variant.value):
                raise ValueError("the default variant has the key Trial Folio gives it")
            if default.description is not None:
                raise ValueError("the default variant has no description")
        if self.budget.provider_requests < len(self.cases):
            raise ValueError("the budget's provider_requests is at least the number of cases")
        return self
