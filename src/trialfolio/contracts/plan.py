"""The plan, `plan.json`, schema version 1.0.0 (docs/contracts.md, plans and approval), and
version 1.2.0, a screen's whose ranking is a definition (plans with a ranking definition).

The model describes a plan. Building one, and computing `case_id` and `plan_hash`, is the
planner's job (R01-T10); the model doesn't recompute either.

A 1.2.0 plan has 1.0.0's fields, with `ranking_source`, a case's two requests, its `rank_update`
and its backtest, the weight rows, each setting's `node`, and a budget with each operation's
cost. Besides their shapes and each row's rules, the models check the consistency rules of plans
with a ranking definition (release 0.4.0's R04-T07): a case's `rank_update` writes the definition
its `ranking` setting names by hash, with its ranking method; its weight rows are that
definition's nodes and weights; its backtest ranks by `ApiRankingSystem`, and is otherwise what
its settings send; `ranking_source` gives the baseline's definition; and the budget's credits are
what its costs give. A case's definition is read by the rules of `trialfolio.ranking_definitions`.

The parts a screen's plans share with an experiment's and a ranking snapshot's are in
`trialfolio.contracts.plan_requests`, the requests, and `trialfolio.contracts.plan_parts`, the
rest, such as each resolved setting, the budget, and the data sent.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from trialfolio.contracts.common import (
    CaseId,
    ContractModel,
    IntegerOnly,
    Purpose,
    SemanticVersion,
    Sha256Digest,
    Title,
    TransportVersions,
    WrapperVersions,
    require_unique,
)
from trialfolio.contracts.plan_parts import (
    Budget,
    DataSent,
    DataSentV1_2,
    OperationCost,
    PlanSetting,
    PlanSettingV1_2,
    RankingSource,
    RetryPolicy,
    check_case,
    check_costs,
    check_ranking_case,
    check_ranking_source,
)
from trialfolio.contracts.plan_requests import PlanRequest, RankUpdateRequest


class PlanCase(ContractModel):
    """One fully resolved case. A 1.0.0 plan has exactly one."""

    case_id: CaseId
    requests: tuple[PlanRequest]
    settings: tuple[PlanSetting, ...]

    @model_validator(mode="after")
    def _screen_settings(self) -> Self:
        check_case(self.requests, self.settings)
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


class PlanCaseV1_2(ContractModel):
    """The one case of a screen whose ranking is a definition: its `rank_update`, then its
    backtest, ranked by `ApiRankingSystem`, and its settings, with a weight row for each node."""

    case_id: CaseId
    requests: tuple[RankUpdateRequest, PlanRequest]
    """The `rank_update` that writes the case's whole definition, then the backtest."""
    settings: tuple[PlanSettingV1_2, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        check_ranking_case(self.requests, self.settings)
        return self


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
        check_costs(self.costs, self.provider_requests, self.credits)
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
    def _consistent(self) -> Self:
        require_unique(tuple(entry.category for entry in self.data_sent), "data_sent categories")
        check_ranking_source(self.ranking_source, self.cases[0].settings)
        return self
