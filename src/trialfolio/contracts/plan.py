"""The plan, `plan.json`, schema version 1.0.0 (docs/contracts.md, plans and approval), and
version 1.2.0, a screen's whose ranking is a definition (plans with a ranking definition).

The model describes a plan. Building one, and computing `case_id` and `plan_hash`, is the
planner's job (R01-T10); the model doesn't recompute either.

A 1.2.0 plan has 1.0.0's fields, with `ranking_source`, a case's two requests, its `rank_update`
and its backtest, the weight rows, each setting's `node`, and a budget with each operation's
cost. The models give their shapes and each row's rules; whether a case's requests and weight
rows are what its definition gives is checked across the plan (release 0.4.0's R04-T07).
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
    NodePathText,
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
    RANKING_WEIGHT,
    SCREEN_SETTINGS,
    SETTINGS_WITH_WEIGHTS_BY_NAME,
    DefinitionRankingSetting,
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


PlanFlag = Literal["inferred_default", "not_snapshotted"]
"""The flags known before execution (plan contents, settings in the plan)."""


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
    flags: tuple[PlanFlag, ...]

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


def check_case(requests: tuple[PlanRequest], settings: tuple[PlanSetting, ...]) -> None:
    """Raises `ValueError` unless `settings` are the screen settings, in their documented order,
    and the request is what they send (plan contents, consistency)."""
    names = tuple(row.setting for row in settings)
    if names != tuple(setting.name for setting in SCREEN_SETTINGS):
        raise ValueError("settings must be the screen settings, in their documented order")
    values = {row.setting: row.value for row in settings}
    if requests[0].params != screen_backtest_params(values):
        raise ValueError("the request's params must be what the settings send")


class PlanCase(ContractModel):
    """One fully resolved case. A 1.0.0 plan has exactly one."""

    case_id: CaseId
    requests: tuple[PlanRequest]
    settings: tuple[PlanSetting, ...]

    @model_validator(mode="after")
    def _screen_settings(self) -> Self:
        check_case(self.requests, self.settings)
        return self


class DocumentedSource(ContractModel):
    """Where a documented value comes from, and the date the documentation was checked."""

    title: NonEmptyText
    url: Annotated[str, StringConstraints(pattern=r"^https://[^\s]+$")]
    checked: date


CREDITS_PER_REQUEST: Final = 5
"""Portfolio123's documented cost of one screen backtest, in credits (budget and retries). The
planner records it in each plan's budget, and an experiment configuration's budget is bounded by
it, so that the plan's credits can be hashed."""

CREDITS_PER_REQUEST_SOURCE: Final = DocumentedSource(
    title="API: Screen",
    url="https://portfolio123.customerly.help/en/articles/43324-api-screen",
    checked=date(2026, 10, 1),
)


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


# Version 1.2.0: a screen whose ranking is a definition.


class RankUpdateParams(ContractModel):
    """The params passed to p123api's `rank_update`, exactly as they're sent, in this order: the
    fixed type, the case's whole definition, its ranking method's number, and the fixed currency.
    There's no `id`, so the call writes `ApiRankingSystem` (sending a definition)."""

    type: Literal["stock"]
    nodes: Annotated[str, StringConstraints(min_length=1)]
    """The case's whole definition, as its file's text reads, each line end a line feed."""
    rankingMethod: Annotated[Literal[2, 4], IntegerOnly]
    """2 for `percentile_nas_negative`, and 4 for `percentile_nas_neutral`."""
    currency: Literal["USD"]


class RankUpdateRequest(ContractModel):
    """A case's first request: the `rank_update` that writes its definition into
    `ApiRankingSystem`."""

    operation: Literal["rank_update"]
    params: RankUpdateParams


type SettingValueV1_2 = (
    Annotated[int, Field(ge=0, le=MAX_SAFE_INTEGER)]
    | NonEmptyText
    | tuple[NonEmptyText, ...]
    | DefinitionRankingSetting
)
"""A resolved value of a plan with a ranking definition, in its JSON type: 1.0.0's, with the
`ranking` row's a definition's hash and its ranking method, and a weight as its normalized
decimal's text."""


class PlanSettingV1_2(ContractModel):
    """One resolved setting of a plan with a ranking definition: 1.0.0's row, with `node` after
    `setting`: a weight row's canonical path, and null on every other row."""

    setting: SettingName
    node: NodePathText | None
    """A weight row's node, by its canonical path; null on every other row."""
    category: SettingCategory
    critical: bool
    value: SettingValueV1_2
    unit: SettingUnit | None
    interpretation: Interpretation
    expected_provenance: Provenance
    inference_rule: NonEmptyText | None
    flags: tuple[PlanFlag, ...]

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
            settings=SETTINGS_WITH_WEIGHTS_BY_NAME,
        )
        if (self.node is None) == (setting is RANKING_WEIGHT):
            raise ValueError("node is given on a weight row, and only there")
        check_value(setting, self.value, "definition")
        require_unique(self.flags, "flags")
        check_flags(setting, self.value, self.flags, executed=False, rankings="definition")
        return self


_RANKING_INDEX: Final = next(
    index for index, setting in enumerate(SCREEN_SETTINGS) if setting.name == "ranking"
)


def check_ranking_settings(settings: tuple[PlanSettingV1_2, ...]) -> None:
    """Raises `ValueError` unless `settings` are the screen settings, in their documented order,
    with at least one weight row right after `ranking` (weight rows). Whether the weight rows are
    the definition's nodes, in its order, is checked against the definition."""
    names = [row.setting for row in settings]
    weights = len(names) - len(SCREEN_SETTINGS)
    screen = [setting.name for setting in SCREEN_SETTINGS]
    after = _RANKING_INDEX + 1
    expected = [*screen[:after], *[RANKING_WEIGHT.name] * weights, *screen[after:]]
    if weights < 1 or names != expected:
        raise ValueError(
            "settings must be the screen settings, in their documented order, with a weight row "
            "for each node right after ranking"
        )


class PlanCaseV1_2(ContractModel):
    """The one case of a screen whose ranking is a definition: its `rank_update`, then its
    backtest, ranked by `ApiRankingSystem`, and its settings, with a weight row for each node."""

    case_id: CaseId
    requests: tuple[RankUpdateRequest, PlanRequest]
    """The `rank_update` that writes the case's whole definition, then the backtest."""
    settings: tuple[PlanSettingV1_2, ...]

    @model_validator(mode="after")
    def _screen_settings(self) -> Self:
        check_ranking_settings(self.settings)
        return self


class OperationCost(ContractModel):
    """One operation's documented cost, in credits, when the plan was made, and its source."""

    operation: Literal["rank_update", "screen_backtest"]
    credits_per_request: Annotated[int, Field(ge=0)]
    source: DocumentedSource


def check_costs(costs: tuple[OperationCost, OperationCost]) -> None:
    """Raises `ValueError` unless `costs` gives the `rank_update`'s cost, then the backtest's."""
    if tuple(cost.operation for cost in costs) != ("rank_update", "screen_backtest"):
        raise ValueError("costs gives rank_update's cost, then screen_backtest's")


class PlanBudgetV1_2(ContractModel):
    """The budget of a screen whose ranking is a definition: its two requests, the `rank_update`
    and the backtest, each operation's documented cost, and the most they can cost."""

    provider_requests: Annotated[Literal[2], IntegerOnly]
    """The case's `rank_update` and its backtest, each sent at most once."""
    costs: tuple[OperationCost, OperationCost]
    """`rank_update`'s documented cost, then the backtest's, in place of 1.0.0's
    `credits_per_request` and its source."""
    credits: Annotated[int, Field(ge=0)]
    authentication_calls: Annotated[Literal[1], IntegerOnly]

    @model_validator(mode="after")
    def _costs(self) -> Self:
        check_costs(self.costs)
        return self


class RankingSource(ContractModel):
    """Where the plan's ranking definition came from, which the plan hash covers and no `case_id`
    does: a file, by the definition's hash, or a snapshot, by its system's name and the
    `artifact_id`s of its `snapshot.json` and `definition.xml` (ranking definitions). Each field
    is always written, null where the form has none."""

    form: Literal["definition", "snapshot"]
    definition: Sha256Digest
    """The definition's hash, which the baseline's `ranking` setting holds too."""
    system: str | None
    """A snapshot's system's name, as its record gives it in `system.name`; null for a file."""
    snapshot_record: Sha256Digest | None
    """The `artifact_id` of a snapshot's `snapshot.json`; null for a file."""
    snapshot_definition: Sha256Digest | None
    """The `artifact_id` of a snapshot's `definition.xml`; null for a file."""


DATA_SENT_SETTINGS_V1_2: Final[dict[DataCategory, frozenset[str]]] = {
    **DATA_SENT_SETTINGS,
    "strategy_definition": _STRATEGY_DEFINITION | {RANKING_WEIGHT.name},
}
"""The settings each `data_sent` category carries in a plan with a ranking definition: 1.0.0's,
with the weights in `strategy_definition`, since each `rank_update` sends them."""


class DataSentV1_2(ContractModel):
    """A category of data that leaves the machine, in a plan with a ranking definition."""

    category: DataCategory
    recipient: Literal["Portfolio123"]
    via: Literal["p123api"]
    settings: tuple[SettingName, ...]

    @model_validator(mode="after")
    def _known_settings(self) -> Self:
        if frozenset(self.settings) != DATA_SENT_SETTINGS_V1_2[self.category]:
            raise ValueError(f"{self.category} must carry exactly its documented settings")
        require_unique(self.settings, "settings")
        return self


class PlanV1_2(ContractModel):
    """A screen's plan whose ranking is a definition: its one case's `rank_update` and backtest,
    with the whole definition, the definition's source, the budget with each operation's cost,
    the retry policy, and the data sent. Execution requires its `plan_hash` as approval (plans
    with a ranking definition)."""

    schema_version: Literal["1.2.0"]
    trialfolio_version: SemanticVersion
    canonicalization_version: Annotated[Literal[1], IntegerOnly]
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    title: Title
    purpose: Purpose | None
    ranking_source: RankingSource
    cases: tuple[PlanCaseV1_2]
    budget: PlanBudgetV1_2
    retry_policy: RetryPolicy
    data_sent: Annotated[tuple[DataSentV1_2, ...], Field(min_length=3, max_length=3)]
    plan_hash: Sha256Digest

    @model_validator(mode="after")
    def _unique_categories(self) -> Self:
        require_unique(tuple(entry.category for entry in self.data_sent), "data_sent categories")
        return self
