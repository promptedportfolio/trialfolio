"""What a plan's cases are built of, which a screen's plans and an experiment's share (docs/
contracts.md, plan contents, settings in the plan, and plans with a ranking definition): the
retry policy, the data sent, and the documented costs; the settings a configuration resolves to,
with a ranking definition's weight rows; a case's `case_id`; and the requests a case sends.
"""

from collections.abc import Sequence
from typing import Final, cast

from trialfolio.canonical import canonical_json, sha256_hex
from trialfolio.contracts.common import CRITICAL_CATEGORIES, RANKING_METHOD_NUMBERS
from trialfolio.contracts.plan_parts import (
    CREDITS_PER_REQUEST,
    CREDITS_PER_REQUEST_SOURCE,
    DATA_SENT_SETTINGS,
    DATA_SENT_SETTINGS_V1_2,
    DataSent,
    DataSentV1_2,
    OperationCost,
    PlanFlag,
    PlanSetting,
    PlanSettingV1_2,
    RankingSource,
    RetryPolicy,
    SettingValue,
    SettingValueV1_2,
)
from trialfolio.contracts.plan_requests import (
    PlanRequest,
    RankUpdateRequest,
    screen_backtest_params,
)
from trialfolio.contracts.ranking_snapshot import RANK_GET_COST_SOURCE
from trialfolio.contracts.screen_configuration import (
    DefinitionRanking,
    IdRanking,
    NameRanking,
    Ranking,
    RankingV1_1,
    ScreenFields,
    ScreenFieldsV1_1,
    SnapshotRanking,
)
from trialfolio.contracts.screen_settings import (
    RANKING_WEIGHT,
    SCREEN_SETTINGS,
    DefinitionRankingSetting,
    ScreenSetting,
)
from trialfolio.ranking_definitions import RankingDefinition
from trialfolio.snapshots import SnapshotRead

RETRY_POLICY: Final = RetryPolicy(
    automatic_retries=0, wrapper_attempts_per_call=1, exchanges_per_call=1
)

DATA_SENT: Final = tuple(
    DataSent(
        category=category,
        recipient="Portfolio123",
        via="p123api",
        # In the screen settings' order, never a set's, which varies between processes.
        settings=tuple(setting.name for setting in SCREEN_SETTINGS if setting.name in carried),
    )
    for category, carried in DATA_SENT_SETTINGS.items()
)
"""The three categories of data that leave the machine, in the order data sent lists them."""

RANKING_COSTS: Final = (
    # The Rank page documents rank_update's cost beside rank_get's, and was checked for both.
    OperationCost(operation="rank_update", credits_per_request=1, source=RANK_GET_COST_SOURCE),
    OperationCost(
        operation="screen_backtest",
        credits_per_request=CREDITS_PER_REQUEST,
        source=CREDITS_PER_REQUEST_SOURCE,
    ),
)
"""The documented cost of each operation a plan with a ranking definition sends, `rank_update`
and then the backtest, with the one date each source was checked, which the plan hash covers
(plans with a ranking definition)."""

_SETTINGS_WITH_WEIGHTS: Final = tuple(
    name
    for setting in SCREEN_SETTINGS
    for name in (
        (setting.name, RANKING_WEIGHT.name) if setting.name == "ranking" else (setting.name,)
    )
)
"""The screen settings' names, with the weight rows' right after `ranking`, as they come."""

DATA_SENT_V1_2: Final = tuple(
    DataSentV1_2(
        category=category,
        recipient="Portfolio123",
        via="p123api",
        settings=tuple(name for name in _SETTINGS_WITH_WEIGHTS if name in carried),
    )
    for category, carried in DATA_SENT_SETTINGS_V1_2.items()
)
"""The data sent of a plan with a ranking definition: 1.0.0's, with each `rank_update`'s weights
among the strategy's definition."""


def _screen_values(
    configuration: ScreenFields | ScreenFieldsV1_1,
) -> dict[str, int | str | tuple[str, ...]]:
    """The settings the configuration gives but its ranking, in their JSON types as a plan holds
    them: dates as `YYYY-MM-DD`, and decimals as normalized text."""
    return {
        "universe": configuration.universe,
        "rules": configuration.rules,
        "max_holdings": configuration.max_holdings,
        "benchmark": configuration.benchmark,
        "start_date": configuration.start_date.isoformat(),
        "end_date": configuration.end_date.isoformat(),
        "rebalance_weeks": configuration.rebalance_weeks,
        "transaction_price": configuration.transaction_price,
        # The model normalized it, so its text is the normalized form, in plain notation.
        "slippage_percent": str(configuration.slippage_percent),
        "pit_method": configuration.pit_method,
        "precision": configuration.precision,
    }


def _ranking_form(ranking: RankingV1_1) -> Ranking:
    """A ranking by formula, name, or ID, which a plan 1.0.0 or 1.1.0 holds as it's configured.
    Raises `TypeError` for a definition or a snapshot, which a plan holds by its definition."""
    if isinstance(ranking, DefinitionRanking | SnapshotRanking):
        raise TypeError(
            "a ranking given as a definition is planned with the definition read with it, and a "
            "snapshot with its definition and its record"
        )
    return ranking


def _configured_values(configuration: ScreenFields | ScreenFieldsV1_1) -> dict[str, SettingValue]:
    """The settings the configuration gives, in their JSON types as a plan holds them, its
    ranking by formula, name, or ID."""
    return {**_screen_values(configuration), "ranking": _ranking_form(configuration.ranking)}


def _plan_setting(setting: ScreenSetting, value: SettingValue) -> PlanSetting:
    # A row's own flags are known before execution; the model checks they're its documented ones.
    flags = cast("tuple[PlanFlag, ...]", setting.flags)
    if isinstance(value, NameRanking | IdRanking):
        flags = (*flags, "not_snapshotted")
    return PlanSetting(
        setting=setting.name,
        category=setting.category,
        critical=setting.category in CRITICAL_CATEGORIES,
        value=value,
        unit=setting.unit,
        interpretation=setting.interpretation,
        expected_provenance=setting.provenance,
        inference_rule=setting.inference_rule,
        flags=flags,
    )


def resolve_settings(configuration: ScreenFields | ScreenFieldsV1_1) -> tuple[PlanSetting, ...]:
    """Every screen setting, in order, resolved from the configuration, or from an experiment's
    case (settings in the plan), whose ranking is by formula, name, or ID.

    A setting the configuration doesn't give takes the one value its row allows: a fixed value,
    an inferred default, `not_modeled`, or `not_sent`. So `data_vendor` is FactSet, inferred,
    whether the configuration omits it or gives it, and how the file is written leaves no trace.
    Raises `TypeError` for a ranking given as a definition or a snapshot.
    """
    configured = _configured_values(configuration)
    resolved: list[PlanSetting] = []
    for setting in SCREEN_SETTINGS:
        value = configured.get(setting.name)
        if value is None:
            (value,) = setting.allowed
        resolved.append(_plan_setting(setting, value))
    return tuple(resolved)


def case_id(settings: Sequence[PlanSetting] | Sequence[PlanSettingV1_2]) -> str:
    """`case-` and the first 16 hex digits of the SHA-256 of the canonical form of `settings`,
    each row reduced to its `setting`, `value`, and `unit`, and a weight row's to its `node` too,
    which tells the weight rows apart, so a case without a ranking definition keeps the
    `case_id` 0.3.0 gave it (plan hashing)."""
    rows = [
        row.model_dump(
            mode="json",
            include={"setting", "node", "value", "unit"}
            if row.setting == RANKING_WEIGHT.name
            else {"setting", "value", "unit"},
        )
        for row in settings
    ]
    return "case-" + sha256_hex(canonical_json(rows))[:16]


def screen_requests(settings: Sequence[PlanSetting]) -> tuple[PlanRequest]:
    """A case's one request: the screen backtest its settings send, by the "Sent as" mapping."""
    params = screen_backtest_params({row.setting: row.value for row in settings})
    return (PlanRequest(operation="screen_backtest", params=params),)


def definition_setting(
    ranking: RankingV1_1, definition: RankingDefinition | None, snapshot: SnapshotRead | None
) -> DefinitionRankingSetting | None:
    """The `ranking` setting of a ranking given as a definition, read with it, or named by a
    snapshot, read with it: the definition's hash, and its ranking method, the configuration's or
    the snapshot's system's. None for any other ranking, which `resolve_settings` plans as it's
    configured, or refuses with `TypeError`: a definition or a snapshot without what was read
    with it."""
    if isinstance(ranking, DefinitionRanking) and definition is not None:
        return DefinitionRankingSetting(
            definition=definition.hash, ranking_method=ranking.ranking_method
        )
    if isinstance(ranking, SnapshotRanking) and snapshot is not None:
        return DefinitionRankingSetting(
            definition=snapshot.definition.hash, ranking_method=snapshot.ranking_method
        )
    return None


def _plan_setting_v1_2(
    setting: ScreenSetting, node: str | None, value: SettingValueV1_2
) -> PlanSettingV1_2:
    return PlanSettingV1_2(
        setting=setting.name,
        node=node,
        category=setting.category,
        critical=setting.category in CRITICAL_CATEGORIES,
        value=value,
        unit=setting.unit,
        interpretation=setting.interpretation,
        expected_provenance=setting.provenance,
        inference_rule=setting.inference_rule,
        # A definition is captured whole, so its `ranking` row isn't flagged not_snapshotted.
        flags=cast("tuple[PlanFlag, ...]", setting.flags),
    )


def ranking_settings(
    screen: ScreenFields | ScreenFieldsV1_1,
    ranking: DefinitionRankingSetting,
    definition: RankingDefinition,
) -> tuple[PlanSettingV1_2, ...]:
    """Every screen setting, in order, as `resolve_settings` resolves them, with `ranking`, the
    definition's hash and its ranking method, followed by a weight row for each of the
    definition's nodes, in its order, by its canonical path (weight rows)."""
    configured: dict[str, SettingValueV1_2] = {**_screen_values(screen), "ranking": ranking}
    resolved: list[PlanSettingV1_2] = []
    for setting in SCREEN_SETTINGS:
        value = configured.get(setting.name)
        if value is None:
            (value,) = setting.allowed
        resolved.append(_plan_setting_v1_2(setting, None, value))
        if setting.name == "ranking":
            resolved.extend(
                _plan_setting_v1_2(RANKING_WEIGHT, node.path, format(node.weight, "f"))
                for node in definition.nodes
            )
    return tuple(resolved)


def ranking_requests(
    settings: Sequence[PlanSettingV1_2], definition: RankingDefinition
) -> tuple[RankUpdateRequest, PlanRequest]:
    """A case's two requests: the `rank_update` that writes its whole definition into
    `ApiRankingSystem`, with its ranking method, then the backtest its settings send, ranked by
    that system (sending a definition)."""
    values = {row.setting: row.value for row in settings if row.node is None}
    ranking = values["ranking"]
    if not isinstance(ranking, DefinitionRankingSetting):  # the settings give a definition
        raise TypeError("a case with a ranking definition holds its hash and its ranking method")
    update = RankUpdateRequest.model_validate(
        {
            "operation": "rank_update",
            "params": {
                "type": "stock",
                "nodes": definition.text,
                "rankingMethod": RANKING_METHOD_NUMBERS[ranking.ranking_method],
                "currency": "USD",
            },
        }
    )
    backtest = PlanRequest(operation="screen_backtest", params=screen_backtest_params(values))
    return update, backtest


def ranking_source(definition: RankingDefinition, snapshot: SnapshotRead | None) -> RankingSource:
    """Where the definition came from (ranking definitions, its source): a file, by the
    definition's hash, not the file's `artifact_id`, which its line endings would change; or a
    snapshot, by its system's name, as its record gives it, and the `artifact_id`s of its
    `snapshot.json` and `definition.xml`."""
    if snapshot is None:
        return RankingSource(
            form="definition",
            definition=definition.hash,
            system=None,
            snapshot_record=None,
            snapshot_definition=None,
        )
    return RankingSource(
        form="snapshot",
        definition=definition.hash,
        system=snapshot.record.system.name,
        snapshot_record=snapshot.record_id,
        snapshot_definition=snapshot.definition_id,
    )
