"""The plan, `plan.json`, schema version 1.0.0 (docs/contracts.md, plans and approval).

The model describes a plan. Building one, and computing `case_id` and `plan_hash`, is the
planner's job (R01-T10); the model doesn't recompute either.
"""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    CRITICAL_CATEGORIES,
    MAX_SAFE_INTEGER,
    CaseId,
    ContractModel,
    DateText,
    IntegerOnly,
    Interpretation,
    NonEmptyText,
    Provenance,
    Purpose,
    SemanticVersion,
    SettingCategory,
    SettingName,
    SettingUnit,
    Sha256Digest,
    Title,
    TransportVersions,
    WrapperVersions,
    require_unique,
)
from trialfolio.contracts.screen_configuration import FormulaRanking, IdRanking, NameRanking
from trialfolio.contracts.screen_settings import (
    SCREEN_SETTINGS,
    SCREEN_SETTINGS_BY_NAME,
    ScreenSetting,
    check_ranking,
    check_text_list,
    check_value_text,
)

# The request's parameters keep Portfolio123's own names, so the model reads like the request.


class ScreenRuleParams(ContractModel):
    """One screening rule, as sent. It has no `type` field: Portfolio123 rejects one."""

    formula: NonEmptyText


class FormulaRankingParams(ContractModel):
    """A single-formula ranking, as sent."""

    formula: NonEmptyText
    lowerIsBetter: bool


class ScreenParams(ContractModel):
    """The `screen` object of a screen backtest request."""

    type: Literal["stock"]
    universe: NonEmptyText
    maxNumHoldings: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
    method: Literal["long"]
    currency: Literal["USD"]
    benchmark: NonEmptyText
    ranking: FormulaRankingParams | NonEmptyText | Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
    rules: Annotated[tuple[ScreenRuleParams, ...], Field(min_length=1)]


class ScreenBacktestParams(ContractModel):
    """The JSON object passed to p123api's `screen_backtest`, exactly as it will be sent.

    `slippage` is always a JSON float, and every other number an integer (plan contents).
    """

    screen: ScreenParams
    startDt: DateText
    endDt: DateText
    pitMethod: Literal["Complete"]
    precision: Annotated[Literal[4], IntegerOnly]
    transPrice: Annotated[Literal[1], IntegerOnly]
    slippage: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    rebalFreq: Literal["Every Week", "Every 4 Weeks"]


class PlanRequest(ContractModel):
    """One provider request a case needs."""

    operation: Literal["screen_backtest"]
    params: ScreenBacktestParams


type SettingValue = (
    Annotated[int, Field(ge=0, le=MAX_SAFE_INTEGER)]
    | NonEmptyText
    | tuple[NonEmptyText, ...]
    | FormulaRanking
    | NameRanking
    | IdRanking
)
"""A resolved value, in its JSON type: an integer; text, which holds normalized decimals, dates,
and tokens too; a list of text; or a ranking mapping (plan contents, settings in the plan)."""


class PlanSetting(ContractModel):
    """One resolved setting: a `settings.csv` row without `label`, `original_key`,
    `original_value`, and `source_artifact`, with `expected_provenance` for `provenance`.
    """

    setting: SettingName
    category: SettingCategory
    critical: bool
    value: SettingValue
    unit: SettingUnit | None
    interpretation: Interpretation
    expected_provenance: Provenance
    inference_rule: NonEmptyText | None
    flags: tuple[Literal["inferred_default", "not_snapshotted"], ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.critical != (self.category in CRITICAL_CATEGORIES):
            raise ValueError("critical must be true exactly for the critical categories")
        if (self.inference_rule is None) == (self.expected_provenance == "inferred"):
            raise ValueError("inference_rule must be given exactly for inferred values")
        require_unique(self.flags, "flags")
        return self


def _check_plan_value(setting: ScreenSetting, value: object) -> None:
    match setting.kind:
        case "integer":
            if not isinstance(value, int):
                raise ValueError(f"{setting.name}'s value must be an integer")
        case "text_list":
            check_text_list(setting, value)
        case "ranking":
            ranking = value.model_dump() if isinstance(value, ContractModel) else value
            check_ranking(setting, ranking)
        case _:
            if not isinstance(value, str):
                raise ValueError(f"{setting.name}'s value must be text")
            check_value_text(setting, value)


class PlanCase(ContractModel):
    """One fully resolved case. A 1.0.0 plan has exactly one."""

    case_id: CaseId
    requests: tuple[PlanRequest]
    settings: tuple[PlanSetting, ...]

    @model_validator(mode="after")
    def _screen_settings(self) -> Self:
        names = tuple(row.setting for row in self.settings)
        if names != tuple(setting.name for setting in SCREEN_SETTINGS):
            raise ValueError("settings must be the screen settings, in their documented order")
        for row in self.settings:
            setting = SCREEN_SETTINGS_BY_NAME[row.setting]
            if (row.category, row.unit) != (setting.category, setting.unit):
                raise ValueError(f"{row.setting} must have its documented category and unit")
            _check_plan_value(setting, row.value)
        return self


class DocumentedSource(ContractModel):
    """Where a documented value comes from, and the date the documentation was checked."""

    title: NonEmptyText
    url: Annotated[str, StringConstraints(pattern=r"^https://[^\s]+$")]
    checked: date


class Budget(ContractModel):
    """The request budget (budget and retries)."""

    provider_requests: Annotated[int, Field(ge=1)]
    credits_per_request: Annotated[int, Field(ge=0)]
    credits_per_request_source: DocumentedSource
    credits: Annotated[int, Field(ge=0)]
    authentication_calls: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _credits(self) -> Self:
        if self.credits != self.provider_requests * self.credits_per_request:
            raise ValueError("credits must equal provider_requests times credits_per_request")
        return self


class RetryPolicy(ContractModel):
    """The retry policy: no automatic retries, and one exchange per wrapper call."""

    automatic_retries: Annotated[Literal[0], IntegerOnly]
    wrapper_attempts_per_call: Annotated[Literal[1], IntegerOnly]
    exchanges_per_call: Annotated[Literal[1], IntegerOnly]


class DataSent(ContractModel):
    """A category of data that leaves the machine, its recipient, and the settings it carries."""

    category: Literal["credentials", "strategy_definition", "backtest_settings"]
    recipient: Literal["Portfolio123"]
    via: Literal["p123api"]
    settings: tuple[SettingName, ...]

    @model_validator(mode="after")
    def _known_settings(self) -> Self:
        if self.category == "credentials" and self.settings:
            raise ValueError("credentials carry no settings")
        if any(name not in SCREEN_SETTINGS_BY_NAME for name in self.settings):
            raise ValueError("settings must name screen settings")
        require_unique(self.settings, "settings")
        return self


class Plan(ContractModel):
    """A plan: every resolved case, its requests, the budget, the retry policy, and the data
    sent. Execution requires its `plan_hash` as approval (plans and approval).
    """

    schema_version: Literal["1.0.0"]
    trialfolio_version: SemanticVersion
    canonicalization_version: Annotated[Literal[1], IntegerOnly]
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    title: Title
    purpose: Purpose | None
    cases: tuple[PlanCase]
    budget: Budget
    retry_policy: RetryPolicy
    data_sent: tuple[DataSent, ...]
    plan_hash: Sha256Digest

    @model_validator(mode="after")
    def _unique_categories(self) -> Self:
        require_unique(tuple(entry.category for entry in self.data_sent), "data_sent categories")
        return self
