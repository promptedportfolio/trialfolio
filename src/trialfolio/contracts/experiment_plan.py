"""An experiment's plan, `plan.json`, schema version 1.1.0 (docs/contracts.md, experiment plans
and revisions), and version 1.3.0, an experiment's whose ranking is a definition (plans with a
ranking definition).

A 1.1.0 plan has a 1.0.0 plan's fields, with the experiment's research context, every case with
its `case_key`, `description`, and `variant`, and `revises`, the hash of the plan it revises. A
screen's plan stays 1.0.0. As for 1.0.0, the model describes a plan: building one, and computing
`case_id` and `plan_hash`, is the compiler's job, and the model recomputes neither.

A 1.3.0 plan has 1.1.0's fields, with plan 1.2.0's additions in each case, `ranking_source`, a
ranking variant's `set` and `remove` in every case's `variant`, and a budget with each
operation's cost. Its model applies 1.1.0's rules to every variant but a ranking variant, and
plan 1.2.0's consistency rules to each case. A ranking variant's case is checked against the
baseline's (release 0.4.0's R04-T07): its definition is the baseline's with exactly its change,
made by the rules of ranking variants, its `set` and `remove` name nodes by their canonical paths
in the baseline's definition, and it changes the `ranking` row's definition and the weight rows,
and nothing else. The budget is at least two requests a case.
"""

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated, Final, Literal, Self

from pydantic import AfterValidator, ConfigDict, Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    BASELINE_CASE_KEY,
    MAX_SAFE_INTEGER,
    CaseId,
    ContractModel,
    ExperimentKey,
    IntegerOnly,
    NodePathText,
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
    VARIANT_SETTINGS_V1_1,
    ChangeRefusals,
    RankingVariant,
    VariantSetting,
    VariantSettingV1_1,
    added_rules,
    changed_value,
    default_variant_key,
    replaced_rules,
)
from trialfolio.contracts.plan_parts import (
    DataSent,
    DataSentV1_2,
    DocumentedSource,
    OperationCost,
    PlanSetting,
    PlanSettingV1_2,
    RankingSource,
    RetryPolicy,
    check_case,
    check_costs,
    check_credits,
    check_ranking_case,
    check_ranking_source,
    read_nodes,
)
from trialfolio.contracts.plan_requests import PlanRequest, RankUpdateRequest
from trialfolio.contracts.screen_settings import (
    RANKING_WEIGHT,
    SCREEN_SETTINGS_BY_NAME,
    DefinitionRankingSetting,
    check_value,
)
from trialfolio.ranking_definitions import (
    RankingCase,
    RankingDefinition,
    VariantProblem,
    apply_ranking_variant,
)


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
        _check_change(self)
        return self


def _check_change(variant: "PlanVariant | PlanVariantV1_3") -> None:
    """Raises `ValueError` unless a variant of a value gives a value, a variant of rules gives an
    `add`, or a `replace` and its `with`, and nothing else, and only a variant of
    `rebalance_weeks` is the default."""
    rule_change = (variant.add, variant.replace, variant.with_)
    if variant.setting in _VALUE_SETTINGS:
        if variant.value is None or rule_change != (None, None, None):
            raise ValueError(f"a variant of {variant.setting} gives a value, and nothing else")
        check_value(SCREEN_SETTINGS_BY_NAME[variant.setting], variant.value)
    elif variant.setting == "rules":
        if variant.value is not None or (variant.add is None) == (variant.replace is None):
            raise ValueError("a variant of rules gives add, or replace and with, and nothing else")
        if (variant.replace is None) != (variant.with_ is None):
            raise ValueError("a variant of rules gives with exactly when it gives replace")
    if variant.default and variant.setting != "rebalance_weeks":
        raise ValueError("the default variant is a variant of rebalance_weeks")


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
        check_baseline(self.case_key, self.variant, self.description)
        return self


def check_baseline(
    case_key: str, variant: "PlanVariant | PlanVariantV1_3 | None", description: str | None
) -> None:
    """Raises `ValueError` unless a case has no variant exactly when it's the baseline, and the
    baseline has no description, as a plan and `experiment.json` hold it."""
    if (case_key == BASELINE_CASE_KEY) != (variant is None):
        raise ValueError("the baseline, and only the baseline, has no variant")
    if variant is None and description is not None:
        raise ValueError("the baseline has no description")


def check_revises(revises: str | None, plan_hash: str) -> None:
    """Raises `ValueError` when a plan revises itself, as a plan and `experiment.json` hold it."""
    if revises == plan_hash:
        raise ValueError("a plan doesn't revise itself")


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
        check_credits(self.credits, self.provider_requests, self.credits_per_request)
        _check_authentication_calls(self)
        return self


def _check_authentication_calls(budget: "PlanBudgetV1_1 | PlanBudgetV1_3") -> None:
    """Raises `ValueError` unless a budget across runs allows an authentication call for each
    provider request."""
    if budget.authentication_calls != budget.provider_requests:
        raise ValueError("authentication_calls must equal provider_requests")


_REFUSALS: Final = ChangeRefusals(
    same_value="a variant's value differs from the baseline's",
    rule_present="a variant adds a rule the baseline doesn't have",
    replace_not_one="a variant replaces exactly one of the baseline's rules",
    with_present="a variant replaces a rule with a formula the baseline doesn't have",
)
"""How a plan words a variant's change that changes nothing, or isn't one."""


def _changed_value(
    baseline: PlanSetting | PlanSettingV1_2, variant: "PlanVariant | PlanVariantV1_3"
) -> object:
    """The value the variant gives its setting, from the baseline's value. Raises `ValueError`
    when the change changes nothing, or a `replace` isn't exactly one of the baseline's
    rules."""
    if variant.value is not None:
        return changed_value(baseline.value, variant.value, _REFUSALS)
    rules = baseline.value
    if not isinstance(rules, tuple):  # the baseline's rules are valid, so a list of text
        raise ValueError("the baseline's rules must be a list")
    if variant.add is not None:
        return added_rules(rules, variant.add, _REFUSALS)
    # A variant of rules gives with exactly when it gives replace, which its own check requires.
    if variant.replace is None or variant.with_ is None:
        raise ValueError(_REFUSALS.replace_not_one)
    return replaced_rules(rules, variant.replace, variant.with_, _REFUSALS)


def _check_variant(
    baseline: "ExperimentPlanCase | ExperimentPlanCaseV1_3",
    case: "ExperimentPlanCase | ExperimentPlanCaseV1_3",
) -> str:
    """Raises `ValueError` unless the case's settings are the baseline's with exactly the change
    its variant gives. Returns the changed value's JSON text, which tells cases apart."""
    variant = case.variant
    if variant is None:
        raise ValueError("only the first case is the baseline")
    changed_text = ""
    own_rows: tuple[PlanSetting | PlanSettingV1_2, ...] = case.settings
    base_rows: tuple[PlanSetting | PlanSettingV1_2, ...] = baseline.settings
    # Each case's rows are the screen settings, in order, so only weight rows can differ in number.
    if len(own_rows) != len(base_rows):
        raise ValueError(f"a variant of {variant.setting} keeps the baseline's weight rows")
    for own, base in zip(own_rows, base_rows, strict=True):
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
        _check_plan(self)
        baseline, *variants = self.cases
        changes = [_check_variant(baseline, case) for case in variants]
        settings = [case.variant.setting for case in variants if case.variant is not None]
        require_unique(tuple(zip(settings, changes, strict=True)), "the cases' settings")
        _check_order(variants, settings, VARIANT_SETTINGS)
        if self.budget.provider_requests < len(self.cases):
            raise ValueError("the budget's provider_requests is at least the number of cases")
        return self


def _check_plan(plan: "PlanV1_1 | PlanV1_3") -> None:
    """Raises `ValueError` unless a plan 1.1.0 or 1.3.0 gives each category of data sent once,
    doesn't revise itself, and gives the baseline first, and each case's key and ID once."""
    require_unique(tuple(entry.category for entry in plan.data_sent), "data_sent categories")
    check_revises(plan.revises, plan.plan_hash)
    if plan.cases[0].variant is not None:
        raise ValueError("the first case is the baseline")
    require_unique(tuple(case.case_key for case in plan.cases), "case keys")
    require_unique(tuple(case.case_id for case in plan.cases), "case IDs")


def _check_order(
    variants: "Sequence[ExperimentPlanCase | ExperimentPlanCaseV1_3]",
    settings: Sequence[str],
    documented: Sequence[str],
) -> None:
    """Raises `ValueError` unless the variants come in the `documented` order of the settings
    they change, and the default variant, when there's one, is as Trial Folio adds it."""
    order = [documented.index(setting) for setting in settings]
    if order != sorted(order):
        raise ValueError("the variants come in the order of their settings")
    _check_default(variants, settings)


# Version 1.3.0: an experiment whose ranking is a definition.


def _weight_text(value: str) -> str:
    check_value(RANKING_WEIGHT, value)
    return value


WeightText = Annotated[
    str,
    StringConstraints(pattern=r"^(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$"),
    AfterValidator(_weight_text),
]
"""A node's weight, as a normalized decimal's text, greater than 0."""


class WeightChange(ContractModel):
    """One entry of a ranking variant's `set`: a node, by its canonical path in the baseline's
    definition, and the weight the variant gives it."""

    node: NodePathText
    weight: WeightText


class PlanVariantV1_3(ContractModel):
    """A case's variant in plan 1.3.0: 1.1.0's, with a ranking variant's change, `set` and
    `remove`. Each key is always written, null where it doesn't apply."""

    model_config = ConfigDict(serialize_by_alias=True)

    setting: VariantSettingV1_1
    value: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)] | NonEmptyText | None
    add: NonEmptyText | None
    replace: NonEmptyText | None
    with_: Annotated[NonEmptyText | None, Field(alias="with")]
    set: Annotated[tuple[WeightChange, ...], Field(min_length=1)] | None
    """A ranking variant's weights, for each entry of the configuration's `set`, each node by
    its canonical path, in the baseline definition's order; null in a variant of another
    setting."""
    remove: NodePathText | None
    """The canonical path of the factor a ranking variant removes; null when it removes none,
    and in a variant of another setting."""
    default: bool
    """True for P-13's default rebalance variant, and false otherwise."""

    @model_validator(mode="after")
    def _one_change(self) -> Self:
        if self.setting == "ranking":
            if (self.value, self.add, self.replace, self.with_) != (None,) * 4:
                raise ValueError("a ranking variant gives set, and remove, and nothing else")
            if self.set is None:
                raise ValueError("a ranking variant gives set: the weights it gives its nodes")
        elif (self.set, self.remove) != (None, None):
            raise ValueError("only a ranking variant gives set and remove")
        _check_change(self)
        if self.set is not None:
            nodes = tuple(entry.node for entry in self.set)
            require_unique(nodes, "the nodes of set")
            if self.remove in nodes:
                raise ValueError("the factor a variant removes gets no weight")
        return self


class ExperimentPlanCaseV1_3(ContractModel):
    """One case of an experiment whose ranking is a definition: a 1.1.0 case, with plan 1.2.0's
    two requests, and its settings with a weight row for each node."""

    case_key: ExperimentKey
    case_id: CaseId
    description: ShortText | None
    """The variant's description, with `user_supplied` provenance; null when there's none, and
    for the baseline."""
    variant: PlanVariantV1_3 | None
    """Null for the baseline."""
    requests: tuple[RankUpdateRequest, PlanRequest]
    """The `rank_update` that writes the case's whole definition, then its backtest."""
    settings: tuple[PlanSettingV1_2, ...]

    @model_validator(mode="after")
    def _screen_settings(self) -> Self:
        check_ranking_case(self.requests, self.settings)
        check_baseline(self.case_key, self.variant, self.description)
        return self


class PlanBudgetV1_3(ContractModel):
    """The budget across runs of an experiment whose ranking is a definition: 1.1.0's, with each
    operation's documented cost in place of the one cost a request had."""

    provider_requests: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
    """The configuration's `budget.provider_requests`."""
    costs: tuple[OperationCost, OperationCost]
    """`rank_update`'s documented cost, then the backtest's."""
    credits: Annotated[int, Field(ge=0)]
    authentication_calls: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
    """Equal to `provider_requests`."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        check_costs(self.costs, self.provider_requests, self.credits)
        _check_authentication_calls(self)
        return self


class PlanV1_3(ContractModel):
    """An experiment's plan whose ranking is a definition: plan 1.1.0's, with each case's
    `rank_update` and its whole definition, the weight rows, the definition's source, and each
    operation's cost. Execution requires its `plan_hash` as approval (plans with a ranking
    definition)."""

    schema_version: Literal["1.3.0"]
    trialfolio_version: SemanticVersion
    canonicalization_version: Annotated[Literal[1], IntegerOnly]
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    experiment_id: ExperimentKey
    title: Title
    purpose: Purpose
    """An experiment's purpose is required, so it's never null."""
    prior_research: DeclaredPriorResearch
    ranking_source: RankingSource
    """The baseline's definition's source: every case's definition is the baseline's, or a
    ranking variant's change of it."""
    revises: Sha256Digest | None
    """The `plan_hash` of the plan this one revises; null for the experiment's first plan."""
    cases: Annotated[tuple[ExperimentPlanCaseV1_3, ...], Field(min_length=2)]
    """Every case, in the order of cases: the baseline first, then the variants of `rules`,
    `ranking`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`."""
    budget: PlanBudgetV1_3
    retry_policy: RetryPolicy
    data_sent: Annotated[tuple[DataSentV1_2, ...], Field(min_length=3, max_length=3)]
    plan_hash: Sha256Digest

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_plan(self)
        baseline, *variants = self.cases
        check_ranking_source(self.ranking_source, baseline.settings)
        definition = read_nodes(baseline.requests[0].params.nodes)
        # A ranking variant's case is its definition, which its change of the baseline's gives.
        changes = [
            (
                case.variant.setting,
                _check_ranking_variant(definition, baseline, case, number)
                if case.variant.setting == "ranking"
                else _check_variant(baseline, case),
            )
            for number, case in enumerate(variants, start=1)
            if case.variant is not None
        ]
        require_unique(tuple(changes), "the cases' settings")
        settings = [case.variant.setting for case in variants if case.variant is not None]
        _check_order(variants, settings, VARIANT_SETTINGS_V1_1)
        if self.budget.provider_requests < 2 * len(self.cases):
            raise ValueError(
                "the budget's provider_requests is at least twice the number of cases: each "
                "case sends a rank_update and a backtest"
            )
        return self


def _check_ranking_variant(
    definition: RankingDefinition,
    baseline: ExperimentPlanCaseV1_3,
    case: ExperimentPlanCaseV1_3,
    number: int,
) -> str:
    """Raises `ValueError` unless the ranking variant `case`, the plan's case `number`, counted
    from 0, is the baseline's with exactly its change: its settings but the `ranking` row's
    definition and the weight rows are the baseline's, and its definition is the baseline's,
    `definition`, with its `set` and `remove`, made by the rules of ranking variants, which name
    each node by its canonical path in the baseline's definition, `set` in that definition's
    order. Returns its definition's hash, which tells cases apart."""
    variant = case.variant
    if variant is None or variant.set is None:  # a ranking variant's own rules require set
        raise ValueError("a ranking variant gives set: the weights it gives its nodes")
    _check_kept_settings(baseline, case)
    applied = _applied(definition, case.case_key, variant.set, variant.remove, number)
    written = [(entry.node, entry.weight) for entry in variant.set]
    if written != [(entry.node.path, format(entry.weight, "f")) for entry in applied.set]:
        raise ValueError(
            "a ranking variant's set names each node by its canonical path in the baseline's "
            "definition, in that definition's order"
        )
    if variant.remove != (None if applied.remove is None else applied.remove.path):
        raise ValueError(
            "a ranking variant's remove names the factor by its canonical path in the "
            "baseline's definition"
        )
    if case.requests[0].params.nodes != applied.definition.text:
        raise ValueError("a ranking variant's definition is the baseline's with exactly its change")
    return applied.definition.hash


def _check_kept_settings(baseline: ExperimentPlanCaseV1_3, case: ExperimentPlanCaseV1_3) -> None:
    """Raises `ValueError` unless a ranking variant's case keeps each of the baseline's settings
    but its definition and the weight rows, the ranking method included."""
    own_rows = [row for row in case.settings if row.setting != RANKING_WEIGHT.name]
    base_rows = [row for row in baseline.settings if row.setting != RANKING_WEIGHT.name]
    # Each case's rows are the screen settings, in order, with weight rows after `ranking`.
    for own, base in zip(own_rows, base_rows, strict=True):
        if own.setting == "ranking":
            if _method(own) != _method(base):
                raise ValueError("a ranking variant keeps the baseline's ranking method")
        elif own != base:
            raise ValueError(f"a ranking variant keeps the baseline's {own.setting}")


def _applied(
    definition: RankingDefinition,
    key: str,
    weights: tuple[WeightChange, ...],
    remove: str | None,
    number: int,
) -> RankingCase:
    """The case a ranking variant, the plan's case `number`, counted from 0, gives from the
    baseline's `definition`, by the rules of ranking variants: its `set`, `weights`, and its
    `remove`. Raises `ValueError` when the change breaks them."""
    given: dict[str, object] = {
        "key": key,
        "set": {entry.node: Decimal(entry.weight) for entry in weights},
    }
    if remove is not None:
        given["remove"] = remove
    place = f"cases[{number}].variant"
    try:
        return apply_ranking_variant(definition, RankingVariant.model_validate(given), place)
    except VariantProblem as problem:
        raise ValueError(
            f"a ranking variant's change follows the rules of ranking variants, and "
            f"`{problem.where}` {problem.problem}"
        ) from None


def _method(row: PlanSettingV1_2) -> object:
    """A `ranking` row's ranking method."""
    value = row.value
    return value.ranking_method if isinstance(value, DefinitionRankingSetting) else value


def _check_default(
    variants: "Sequence[ExperimentPlanCase | ExperimentPlanCaseV1_3]", settings: Sequence[str]
) -> None:
    """Raises `ValueError` unless the default variant, when there's one, is the plan's only
    rebalance variant, gives `rebalance_weeks` a value, and has the key Trial Folio gives it and
    no description."""
    defaults = [case for case in variants if case.variant and case.variant.default]
    if not defaults:
        return
    if len(defaults) > 1 or list(settings).count("rebalance_weeks") > 1:
        raise ValueError("the default is an experiment's only rebalance variant")
    (default,) = defaults
    if default.variant is None or not isinstance(default.variant.value, int):
        raise ValueError("the default variant gives rebalance_weeks a value")
    if default.case_key != default_variant_key(default.variant.value):
        raise ValueError("the default variant has the key Trial Folio gives it")
    if default.description is not None:
        raise ValueError("the default variant has no description")
