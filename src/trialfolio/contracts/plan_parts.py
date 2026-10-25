"""The parts of a plan that a screen's plans, an experiment's, and a ranking snapshot's share
(docs/contracts.md, plan contents, budget and retries, data sent, and plans with a ranking
definition): each resolved setting, with a ranking definition's weight rows; the checks that a
case's requests are what its settings send; the budget, its documented costs, and the retry
policy; the data sent; and where a ranking definition came from.

A case's definition is read by the rules of `trialfolio.ranking_definitions`.
"""

from datetime import date
from typing import TYPE_CHECKING, Annotated, Final, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    API_RANKING_SYSTEM,
    MAX_SAFE_INTEGER,
    RANKING_METHOD_NUMBERS,
    ContractModel,
    IntegerOnly,
    Interpretation,
    NodePathText,
    NonEmptyText,
    Provenance,
    SettingCategory,
    SettingName,
    SettingUnit,
    Sha256Digest,
    require_unique,
)
from trialfolio.contracts.plan_requests import (
    PlanRequest,
    RankUpdateRequest,
    screen_backtest_params,
)
from trialfolio.contracts.screen_configuration import FormulaRanking, IdRanking, NameRanking
from trialfolio.contracts.screen_settings import (
    RANKING_WEIGHT,
    SCREEN_SETTINGS,
    SETTINGS_WITH_WEIGHTS_BY_NAME,
    DefinitionRankingSetting,
    check_flags,
    check_row,
    check_value,
)

if TYPE_CHECKING:
    from trialfolio.ranking_definitions import RankingDefinition

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


def check_case(requests: tuple[PlanRequest], settings: tuple[PlanSetting, ...]) -> None:
    """Raises `ValueError` unless `settings` are the screen settings, in their documented order,
    and the request is what they send (plan contents, consistency)."""
    names = tuple(row.setting for row in settings)
    if names != tuple(setting.name for setting in SCREEN_SETTINGS):
        raise ValueError("settings must be the screen settings, in their documented order")
    values = {row.setting: row.value for row in settings}
    if requests[0].params != screen_backtest_params(values):
        raise ValueError("the request's params must be what the settings send")


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


def read_nodes(nodes: str) -> "RankingDefinition":
    """The definition a `rank_update`'s `nodes` holds, read by the rules of ranking definitions,
    as a definition file's text is. Raises `ValueError` unless it's a definition Trial Folio
    reads, whose text, each line end a line feed, is `nodes` exactly."""
    # Imported here, not above: trialfolio.ranking_definitions applies an experiment
    # configuration's ranking variants, and that configuration's module imports this one.
    from trialfolio.ranking_definitions import DefinitionProblem, read_definition

    try:
        definition = read_definition(nodes.encode("utf-8"))
    except (DefinitionProblem, UnicodeEncodeError):
        raise ValueError(
            "a rank_update's nodes is a ranking definition that Trial Folio reads"
        ) from None
    if definition.text != nodes:
        raise ValueError("a rank_update's nodes ends each line with a line feed alone")
    return definition


def _definition_setting(settings: tuple[PlanSettingV1_2, ...]) -> DefinitionRankingSetting:
    """The `ranking` setting of a case whose settings are valid: a definition's hash and its
    ranking method."""
    (value,) = (row.value for row in settings if row.setting == "ranking")
    if not isinstance(value, DefinitionRankingSetting):  # each row's value is checked first
        raise ValueError("a ranking given as a definition holds its hash and its ranking method")
    return value


def check_ranking_case(
    requests: tuple[RankUpdateRequest, PlanRequest], settings: tuple[PlanSettingV1_2, ...]
) -> "RankingDefinition":
    """Raises `ValueError` unless a case with a ranking definition is consistent (plans with a
    ranking definition): its settings are the screen settings, in order, with its weight rows
    right after `ranking`; its `rank_update` writes the definition whose hash its `ranking`
    setting holds, with that setting's ranking method; its weight rows are the weights that
    definition gives its nodes, in its order, by their canonical paths; and its backtest ranks by
    `ApiRankingSystem`, and is otherwise what its settings send. Returns its definition."""
    check_ranking_settings(settings)
    ranking = _definition_setting(settings)
    update = requests[0].params
    definition = read_nodes(update.nodes)
    if definition.hash != ranking.definition:
        raise ValueError(
            "a rank_update's nodes is the definition whose hash its case's ranking setting holds"
        )
    if update.rankingMethod != RANKING_METHOD_NUMBERS[ranking.ranking_method]:
        raise ValueError("a rank_update's rankingMethod is the number of its case's ranking method")
    weights = [(row.node, row.value) for row in settings if row.setting == RANKING_WEIGHT.name]
    if weights != [(node.path, format(node.weight, "f")) for node in definition.nodes]:
        raise ValueError(
            "a case's weight rows are the weights its definition gives its nodes, in the "
            "definition's order, by their canonical paths"
        )
    backtest = requests[1].params
    if backtest.screen.ranking != API_RANKING_SYSTEM:
        raise ValueError(f"a backtest with a ranking definition ranks by {API_RANKING_SYSTEM}")
    values = {row.setting: row.value for row in settings if row.node is None}
    if backtest != screen_backtest_params(values):
        raise ValueError("the backtest's params must be what the settings send")
    return definition


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
        check_credits(self.credits, self.provider_requests, self.credits_per_request)
        return self


def check_credits(credits: int, provider_requests: int, credits_per_request: int) -> None:
    """Raises `ValueError` unless a budget of one documented cost a request gives the credits
    its requests cost at that cost."""
    if credits != provider_requests * credits_per_request:
        raise ValueError("credits must equal provider_requests times credits_per_request")


class RetryPolicy(ContractModel):
    """The retry policy: no automatic retries, and one exchange per wrapper call."""

    automatic_retries: Annotated[Literal[0], IntegerOnly]
    wrapper_attempts_per_call: Annotated[Literal[1], IntegerOnly]
    exchanges_per_call: Annotated[Literal[1], IntegerOnly]


class OperationCost(ContractModel):
    """One operation's documented cost, in credits, when the plan was made, and its source."""

    operation: Literal["rank_update", "screen_backtest"]
    credits_per_request: Annotated[int, Field(ge=0)]
    source: DocumentedSource


def ranking_credits(provider_requests: int, costs: tuple[OperationCost, OperationCost]) -> int:
    """The most `provider_requests` can cost at `costs`, the `rank_update`'s and then the
    backtest's, sent as a plan with a ranking definition sends them: each backtest follows its
    case's `rank_update` in the same attempt, so at most half of them, rounded down, are
    backtests, and the rest cost what a `rank_update` does (plans with a ranking definition)."""
    rank_update, backtest = costs
    backtests = provider_requests // 2
    return (
        backtests * backtest.credits_per_request
        + (provider_requests - backtests) * rank_update.credits_per_request
    )


def check_costs(
    costs: tuple[OperationCost, OperationCost], provider_requests: int, credits: int
) -> None:
    """Raises `ValueError` unless `costs` gives the `rank_update`'s cost, then the backtest's,
    and `credits` is the most `provider_requests` can cost at them."""
    if tuple(cost.operation for cost in costs) != ("rank_update", "screen_backtest"):
        raise ValueError("costs gives rank_update's cost, then screen_backtest's")
    if credits != ranking_credits(provider_requests, costs):
        raise ValueError(
            "credits is the most the provider requests can cost at the costs given, with half of "
            "them, rounded down, backtests, and the rest rank_updates"
        )


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

    @model_validator(mode="after")
    def _follows_its_form(self) -> Self:
        snapshot = (self.system, self.snapshot_record, self.snapshot_definition)
        if self.form == "definition" and snapshot != (None, None, None):
            raise ValueError("a file's ranking_source gives no system or snapshot files")
        if self.form == "snapshot" and None in snapshot:
            raise ValueError(
                "a snapshot's ranking_source gives its system's name and its files' artifact_ids"
            )
        return self


def check_ranking_source(source: RankingSource, baseline: tuple[PlanSettingV1_2, ...]) -> None:
    """Raises `ValueError` unless `source` gives the definition the baseline's `ranking` setting
    names by hash (plans with a ranking definition)."""
    if source.definition != _definition_setting(baseline).definition:
        raise ValueError("ranking_source's definition is the hash of the baseline's definition")
