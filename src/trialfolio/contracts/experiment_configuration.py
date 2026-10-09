"""The experiment configuration, `kind: experiment`, schema version 1.0.0 (docs/contracts.md,
experiment configuration).

`trialfolio.configuration` reads it from YAML, applying the rules for every configuration file,
and checks that the text Portfolio123 receives is quoted. This model applies the rest: the
research context; the baseline, to which a screen configuration's rules apply; the variants; and
the budget. A message from a rule that spans keys names a variant by its place in the file, such
as `variants.max_holdings[0]`, never by its key, which is the user's text.

`configured_variants` gives an experiment's variants, the default included, in the order of its
cases, each with its case's settings: the baseline's, with the variant's one change.
"""

from dataclasses import dataclass
from typing import Annotated, Final, Literal, Self, get_args

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    Strict,
    model_validator,
)

from trialfolio.contracts.common import (
    BASELINE_CASE_KEY,
    MAX_SAFE_INTEGER,
    ContractModel,
    ExperimentKey,
    NonEmptyText,
    PriorResearchStatus,
    PriorResearchText,
    Purpose,
    ShortText,
    Title,
    optional_key,
    ordered,
    present,
)
from trialfolio.contracts.plan import CREDITS_PER_REQUEST
from trialfolio.contracts.screen_configuration import (
    ConfigDecimal,
    MaxHoldings,
    RebalanceWeeks,
    ScreenFields,
)

ExperimentSchemaVersion = Literal["1.0.0"]

EXPERIMENT_SCHEMA_VERSIONS: Final = get_args(ExperimentSchemaVersion)
"""The experiment configuration versions this release reads."""

VariantSetting = Literal["rules", "max_holdings", "rebalance_weeks", "slippage_percent"]
"""A setting a variant may change: the types R03-T01 verified."""

VARIANT_SETTINGS: Final[tuple[VariantSetting, ...]] = get_args(VariantSetting)
"""The settings a variant may change, in the screen settings' order, which orders the cases."""

DEFAULT_REBALANCE_WEEKS: Final = (1, 4)
"""P-13's default variant set for screens: rebalancing every 1 week and every 4 weeks."""


def default_variant_key(rebalance_weeks: int) -> str:
    """The `case_key` Trial Folio gives the default rebalance variant of that value."""
    return f"rebalance-weeks-{rebalance_weeks}"


class PriorResearch(ContractModel):
    """The prior-research declaration: earlier work on the same idea whose outcomes the user saw,
    in Trial Folio or anywhere else. Trial Folio can't verify it, and records it as written."""

    status: PriorResearchStatus
    """`complete`: the description accounts for all of it, or says there was none. `partial`:
    for some of it. `unknown`: the user can't say what earlier work there was."""
    description: Annotated[
        PriorResearchText | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    """Required with `complete` or `partial`: 1 to 5,000 characters."""

    @model_validator(mode="after")
    def _described(self) -> Self:
        if self.status != "unknown" and self.description is None:
            raise ValueError(
                "`description` is required with the status complete or partial: it says what "
                "the earlier work was, or that there was none"
            )
        return self


class _Variant(ContractModel):
    key: ExperimentKey
    """The case's `case_key`: unique among the experiment's cases, the default's included, and
    not `baseline`."""
    description: Annotated[
        ShortText | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    """Up to 500 characters, shown in the report."""


class RuleVariant(_Variant):
    """A variant of the rules: one of the baseline's rules replaced, with `replace` and `with`,
    or a rule added, with `add`."""

    # `with` is a Python keyword, so the field takes another name. Only `with` is accepted.
    model_config = ConfigDict(serialize_by_alias=True)

    add: Annotated[
        NonEmptyText | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    """A screening formula, added after the baseline's rules."""
    replace: Annotated[
        NonEmptyText | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    """One of the baseline's rules, the same text, character for character."""
    with_: Annotated[
        NonEmptyText | None,
        BeforeValidator(present),
        Field(alias="with", json_schema_extra=optional_key),
    ] = None
    """The formula that takes `replace`'s place, so the rules keep their order."""

    @model_validator(mode="after")
    def _one_change(self) -> Self:
        if self.add is not None and (self.replace is not None or self.with_ is not None):
            raise ValueError(
                "holds `add` beside `replace` or `with`. A variant makes one change: it adds a "
                "rule, or replaces one"
            )
        if self.replace is not None and self.with_ is None:
            raise ValueError("`with` is required with `replace`: it's the rule's replacement")
        if self.with_ is not None and self.replace is None:
            raise ValueError(
                "`replace` is required with `with`: it's the baseline's rule the formula replaces"
            )
        if self.add is None and self.replace is None:
            raise ValueError("needs `add`, or `replace` and `with`: the rule it adds or replaces")
        return self


class HoldingsVariant(_Variant):
    """A variant of the maximum holdings."""

    value: MaxHoldings


class RebalanceVariant(_Variant):
    """A variant of the rebalance frequency."""

    value: RebalanceWeeks


class SlippageVariant(_Variant):
    """A variant of the slippage, in percent: a decimal, read and normalized by the decimals
    rules."""

    value: ConfigDecimal


type AnyVariant = RuleVariant | HoldingsVariant | RebalanceVariant | SlippageVariant


RuleVariants = Annotated[
    tuple[RuleVariant, ...], Field(min_length=1), Strict(False), BeforeValidator(ordered)
]
HoldingsVariants = Annotated[
    tuple[HoldingsVariant, ...], Field(min_length=1), Strict(False), BeforeValidator(ordered)
]
RebalanceVariants = Annotated[tuple[RebalanceVariant, ...], Strict(False), BeforeValidator(ordered)]
"""May be empty, which turns the default rebalance variant off."""
SlippageVariants = Annotated[
    tuple[SlippageVariant, ...], Field(min_length=1), Strict(False), BeforeValidator(ordered)
]


class Variants(ContractModel):
    """The variants, by the setting each one changes, in lists whose order is kept. Each list
    holds at least one variant, except `rebalance_weeks`'s, where an empty list turns the default
    variant off."""

    rules: Annotated[
        RuleVariants | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    max_holdings: Annotated[
        HoldingsVariants | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    rebalance_weeks: Annotated[
        RebalanceVariants | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    """Replaces the default rebalance variant. An empty list turns it off."""
    slippage_percent: Annotated[
        SlippageVariants | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None


MAX_PROVIDER_REQUESTS: Final = MAX_SAFE_INTEGER // CREDITS_PER_REQUEST
"""The largest budget, 1801439850948198 requests: the plan's credits, `provider_requests` times
the documented cost of a request, are then at most 2^53 - 1, the largest integer canonical
hashing keeps exactly (docs/contracts.md, the experiment's budget)."""


class ExperimentBudget(ContractModel):
    """The experiment's request budget, across every `run` that resumes it."""

    provider_requests: Annotated[int, Field(ge=1, le=MAX_PROVIDER_REQUESTS)]
    """The most provider requests the experiment may send: at least the number of cases, and few
    enough that the plan's credits can be hashed."""


class ExperimentConfiguration(ContractModel):
    """An experiment configuration, `kind: experiment`: one baseline screen and a small set of
    variants, each changing one setting of the baseline (docs/contracts.md, experiment
    configuration)."""

    kind: Literal["experiment"]
    schema_version: ExperimentSchemaVersion
    experiment_id: ExperimentKey
    """The experiment's identity."""
    title: Title
    purpose: Purpose
    """The question the experiment addresses. Required: it's part of the research history."""
    prior_research: PriorResearch
    baseline: ScreenFields
    variants: Annotated[
        Variants | None,
        BeforeValidator(present),
        Field(json_schema_extra=optional_key),
    ] = None
    """When it's absent, the only variant is the default."""
    budget: ExperimentBudget

    @model_validator(mode="after")
    def _cases(self) -> Self:
        if self.variants is not None and not self.variants.model_fields_set:
            raise ValueError(
                "`variants` lists no setting. List at least one, or leave `variants` out for the "
                "default rebalance variant alone"
            )
        variants = configured_variants(self)
        cases = 1 + len(variants)
        if cases == 1:
            raise ValueError(
                "`variants.rebalance_weeks` is empty, and `variants` lists no other variant, so "
                "the experiment's only case would be its baseline. List a variant, or leave "
                "`rebalance_weeks` out for the default. A screen configuration runs one screen"
            )
        if self.budget.provider_requests < cases:
            raise ValueError(
                f"`budget.provider_requests` is less than the experiment's {cases} cases. It "
                "must be at least the number of cases, so that each can be sent once"
            )
        return self


@dataclass(frozen=True)
class ConfiguredVariant:
    """One variant of an experiment, with its case's settings."""

    place: str | None
    """Where the file writes it, such as `variants.max_holdings[0]`; None for the default."""
    setting: VariantSetting
    key: str
    description: str | None
    variant: AnyVariant | None
    """The variant as the file gives it; None for the default."""
    default: bool
    """True for P-13's default rebalance variant."""
    screen: ScreenFields
    """The case's settings: the baseline's, with this variant's one change."""


def _changed(baseline: ScreenFields, setting: VariantSetting, value: object) -> ScreenFields:
    # The value was validated with the setting's own type, so the copy needs no validation.
    return baseline.model_copy(update={setting: value})


def _rules_of(baseline: ScreenFields, place: str, variant: RuleVariant) -> tuple[str, ...]:
    rules = baseline.rules
    if variant.add is not None:
        if variant.add in rules:
            raise ValueError(
                f"`{place}.add` is one of the baseline's rules already. A variant adds a rule the "
                "baseline doesn't have"
            )
        return (*rules, variant.add)
    replace, with_ = variant.replace, variant.with_
    if replace is None or with_ is None:  # the variant's own validator requires both
        raise ValueError(f"`{place}` needs `add`, or `replace` and `with`")
    if rules.count(replace) != 1:
        raise ValueError(
            f"`{place}.replace` isn't one of the baseline's rules. It must be the same text as "
            "exactly one of them, character for character"
        )
    if with_ in rules:
        raise ValueError(
            f"`{place}.with` is one of the baseline's rules. A variant changes one rule to "
            "a formula the baseline doesn't have"
        )
    return tuple(with_ if rule == replace else rule for rule in rules)


def _value_of(baseline: ScreenFields, place: str, setting: VariantSetting, value: object) -> object:
    # Decimals are normalized, so 0.250 equals the baseline's 0.25.
    if value == getattr(baseline, setting):
        raise ValueError(
            f"`{place}.value` is the baseline's value, so the variant changes nothing. A "
            "variant's value differs from the baseline's"
        )
    return value


def configured_variants(configuration: ExperimentConfiguration) -> tuple[ConfiguredVariant, ...]:
    """The experiment's variants, in the order of its cases, after the baseline's: those of
    `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, each list in its order,
    with P-13's default in `rebalance_weeks`' place when `variants` has no `rebalance_weeks` key
    (docs/contracts.md, cases and their order).

    Raises `ValueError` when a variant breaks a rule that spans keys: a key that's `baseline` or
    repeats another case's; a change that changes nothing; a `replace` that isn't exactly one of
    the baseline's rules; or two variants that give one case.
    """
    baseline = configuration.baseline
    variants = configuration.variants or Variants()
    configured: list[ConfiguredVariant] = []
    for setting in VARIANT_SETTINGS:
        listed: tuple[AnyVariant, ...] | None = getattr(variants, setting)
        if setting == "rebalance_weeks" and listed is None:
            (value,) = (
                weeks for weeks in DEFAULT_REBALANCE_WEEKS if weeks != baseline.rebalance_weeks
            )
            configured.append(
                ConfiguredVariant(
                    None,
                    setting,
                    default_variant_key(value),
                    None,
                    None,
                    True,
                    _changed(baseline, setting, value),
                )
            )
            continue
        for index, variant in enumerate(listed or ()):
            place = f"variants.{setting}[{index}]"
            if isinstance(variant, RuleVariant):
                value: object = _rules_of(baseline, place, variant)
            else:
                value = _value_of(baseline, place, setting, variant.value)
            configured.append(
                ConfiguredVariant(
                    place,
                    setting,
                    variant.key,
                    variant.description,
                    variant,
                    False,
                    _changed(baseline, setting, value),
                )
            )
    _check_keys(configured)
    _check_cases(configured)
    return tuple(configured)


def _check_keys(variants: list[ConfiguredVariant]) -> None:
    seen: dict[str, ConfiguredVariant] = {}
    for variant in variants:
        if variant.key == BASELINE_CASE_KEY:
            raise ValueError(
                f"`{variant.place}.key` is the key of the experiment's first case. Give the "
                "variant a key of its own"
            )
        first = seen.get(variant.key)
        if first is not None:
            if first.default or variant.default:
                own = variant if first.default else first
                raise ValueError(
                    f"`{own.place}.key` is the key of the default rebalance variant, which Trial "
                    "Folio adds when `variants` has no `rebalance_weeks` list. Choose another "
                    "key, or list `rebalance_weeks`"
                )
            raise ValueError(
                f"`{variant.place}.key` repeats the key of `{first.place}`. Give each case its "
                "own key"
            )
        seen[variant.key] = variant


def _check_cases(variants: list[ConfiguredVariant]) -> None:
    # Each variant changes one setting of the baseline to something else, so two cases share
    # their settings exactly when two variants change one setting to the same value.
    seen: dict[tuple[str, object], ConfiguredVariant] = {}
    for variant in variants:
        changed: object = getattr(variant.screen, variant.setting)
        first = seen.get((variant.setting, changed))
        if first is not None:
            raise ValueError(
                f"`{variant.place}` gives the same settings as `{first.place}`, so the two would "
                "be one case. Each case has settings of its own"
            )
        seen[(variant.setting, changed)] = variant
