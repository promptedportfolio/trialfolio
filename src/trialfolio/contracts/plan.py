"""The plan, `plan.json`, schema version 1.0.0 (docs/contracts.md, plans and approval).

The model describes a plan. Building one, and computing `case_id` and `plan_hash`, is the
planner's job (R01-T10); the model doesn't recompute either.
"""

import math
from collections.abc import Mapping
from datetime import date
from typing import Annotated, Final, Literal, Self, cast

from pydantic import AfterValidator, BeforeValidator, Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
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
from trialfolio.contracts.screen_configuration import (
    FormulaRanking,
    IdRanking,
    NameRanking,
    Ranking,
    read_ranking,
)
from trialfolio.contracts.screen_settings import (
    SCREEN_SETTINGS,
    check_flags,
    check_row,
    check_value,
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


def _float_only(value: object) -> object:
    if not isinstance(value, float):
        raise ValueError("must be a JSON float, such as 1.0, never an integer")
    return value


def _unsigned(value: float) -> float:
    if math.copysign(1.0, value) < 0:
        raise ValueError("must not be negative, not even -0.0")
    return value


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
    slippage: Annotated[
        float, BeforeValidator(_float_only), Field(allow_inf_nan=False), AfterValidator(_unsigned)
    ]
    rebalFreq: Literal["Every Week", "Every 4 Weeks"]

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.endDt <= self.startDt:
            raise ValueError("endDt must be later than startDt")
        return self


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
    def _documented(self) -> Self:
        setting = check_row(
            self.setting,
            self.category,
            self.critical,
            self.unit,
            self.interpretation,
            self.expected_provenance,
            self.inference_rule,
        )
        check_value(setting, self.value)
        require_unique(self.flags, "flags")
        check_flags(setting, self.value, self.flags, executed=False)
        return self


TRANSACTION_PRICES: Final = {"open": 1}
"""`transaction_price` to `transPrice`."""

PIT_METHODS: Final = {"complete": "Complete"}
"""`pit_method` to `pitMethod`."""

REBALANCE_FREQUENCIES: Final = {1: "Every Week", 4: "Every 4 Weeks"}
"""`rebalance_weeks` to `rebalFreq`."""


def screen_backtest_params(values: Mapping[str, object]) -> ScreenBacktestParams:
    """Builds the request the resolved settings send, by the screen configuration's "Sent as"
    mapping (docs/contracts.md). `values` holds each sent setting's value as a plan holds it,
    by setting name, already valid."""

    def text(name: str) -> str:
        return cast("str", values[name])

    def integer(name: str) -> int:
        return cast("int", values[name])

    ranking: Ranking = read_ranking(values["ranking"])
    sent: object
    match ranking:
        case FormulaRanking():
            sent = {"formula": ranking.formula, "lowerIsBetter": ranking.lower_is_better}
        case NameRanking():
            sent = ranking.name
        case IdRanking():
            sent = ranking.id
    rules = cast("tuple[str, ...]", values["rules"])
    return ScreenBacktestParams.model_validate(
        {
            "screen": {
                "type": text("screen_type"),
                "universe": text("universe"),
                "maxNumHoldings": integer("max_holdings"),
                "method": text("position_method"),
                "currency": text("currency"),
                "benchmark": text("benchmark"),
                "ranking": sent,
                "rules": tuple({"formula": rule} for rule in rules),
            },
            "startDt": text("start_date"),
            "endDt": text("end_date"),
            "pitMethod": PIT_METHODS[text("pit_method")],
            "precision": integer("precision"),
            "transPrice": TRANSACTION_PRICES[text("transaction_price")],
            "slippage": float(text("slippage_percent")),
            "rebalFreq": REBALANCE_FREQUENCIES[integer("rebalance_weeks")],
        }
    )


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
        values = {row.setting: row.value for row in self.settings}
        if self.requests[0].params != screen_backtest_params(values):
            raise ValueError("the request's params must be what the settings send")
        return self


class DocumentedSource(ContractModel):
    """Where a documented value comes from, and the date the documentation was checked."""

    title: NonEmptyText
    url: Annotated[str, StringConstraints(pattern=r"^https://[^\s]+$")]
    checked: date


class Budget(ContractModel):
    """The request budget (budget and retries)."""

    provider_requests: Annotated[Literal[1], IntegerOnly]
    """A 1.0.0 plan has one request, sent at most once."""
    credits_per_request: Annotated[int, Field(ge=0)]
    """Portfolio123's documented cost of one request when the plan was made. It isn't fixed,
    because Portfolio123 can change it."""
    credits_per_request_source: DocumentedSource
    credits: Annotated[int, Field(ge=0)]
    authentication_calls: Annotated[Literal[1], IntegerOnly]

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


DataCategory = Literal["credentials", "strategy_definition", "backtest_settings"]

_SENT: Final = frozenset(
    setting.name for setting in SCREEN_SETTINGS if setting.provenance == "verified"
)
"""The settings the request sends: a value is verified exactly when it's sent (screen settings)."""

_STRATEGY_DEFINITION: Final = frozenset({"universe", "rules", "ranking"})

DATA_SENT_SETTINGS: Final[dict[DataCategory, frozenset[str]]] = {
    "credentials": frozenset(),
    "strategy_definition": _STRATEGY_DEFINITION,
    "backtest_settings": _SENT - _STRATEGY_DEFINITION,
}
"""The settings each `data_sent` category carries (data sent). Together, they're every setting
the request sends, each once."""


class DataSent(ContractModel):
    """A category of data that leaves the machine, its recipient, and the settings it carries."""

    category: DataCategory
    recipient: Literal["Portfolio123"]
    via: Literal["p123api"]
    settings: tuple[SettingName, ...]

    @model_validator(mode="after")
    def _known_settings(self) -> Self:
        if frozenset(self.settings) != DATA_SENT_SETTINGS[self.category]:
            raise ValueError(f"{self.category} must carry exactly its documented settings")
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
    data_sent: Annotated[tuple[DataSent, ...], Field(min_length=3, max_length=3)]
    plan_hash: Sha256Digest

    @model_validator(mode="after")
    def _unique_categories(self) -> Self:
        require_unique(tuple(entry.category for entry in self.data_sent), "data_sent categories")
        return self
