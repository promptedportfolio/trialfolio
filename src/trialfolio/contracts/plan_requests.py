"""The requests a plan's cases send, exactly as they're sent (docs/contracts.md, plan contents,
and sending a definition): a screen backtest's params, which `screen_backtest_params` builds from
a case's settings, and a `rank_update`'s. A screen's plans and an experiment's, of every version,
hold them.
"""

import math
from collections.abc import Mapping
from typing import Annotated, Final, Literal, Self, cast

from pydantic import AfterValidator, BeforeValidator, Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    API_RANKING_SYSTEM,
    MAX_SAFE_INTEGER,
    ContractModel,
    DateText,
    IntegerOnly,
    NonEmptyText,
)
from trialfolio.contracts.screen_configuration import (
    FormulaRanking,
    IdRanking,
    NameRanking,
    Ranking,
)
from trialfolio.contracts.screen_settings import DefinitionRankingSetting, read_ranking_setting

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


TRANSACTION_PRICES: Final = {"open": 1}
"""`transaction_price` to `transPrice`."""

PIT_METHODS: Final = {"complete": "Complete"}
"""`pit_method` to `pitMethod`."""

REBALANCE_FREQUENCIES: Final = {1: "Every Week", 4: "Every 4 Weeks"}
"""`rebalance_weeks` to `rebalFreq`."""


def screen_backtest_params(values: Mapping[str, object]) -> ScreenBacktestParams:
    """Builds the request the resolved settings send, by the screen configuration's "Sent as"
    mapping (docs/contracts.md). `values` holds each sent setting's value as a plan holds it,
    by setting name, already valid. A ranking given as a definition is sent as the name
    `ApiRankingSystem`, which the case's `rank_update` writes it into (sending a definition)."""

    def text(name: str) -> str:
        return cast("str", values[name])

    def integer(name: str) -> int:
        return cast("int", values[name])

    ranking: Ranking | DefinitionRankingSetting = read_ranking_setting(values["ranking"], "any")
    sent: object
    match ranking:
        case FormulaRanking():
            sent = {"formula": ranking.formula, "lowerIsBetter": ranking.lower_is_better}
        case NameRanking():
            sent = ranking.name
        case IdRanking():
            sent = ranking.id
        case DefinitionRankingSetting():
            sent = API_RANKING_SYSTEM
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
