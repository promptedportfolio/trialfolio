"""The row builders: `metrics.csv`'s rows from a response read as the layout, and `settings.csv`'s
from the plan's resolved settings (docs/contracts.md, normalized tables).

- `metrics_rows` gives `metrics.csv`'s 20 rows, and `settings_rows` `settings.csv`'s 23, in
  their documented order.
- From 0.4.0, `settings_rows_v1_1` gives `settings.csv` 1.1.0's, for a run or a case whose
  ranking is a definition (weight rows): 1.0.0's rows, with a row for each node's weight right
  after `ranking`, as its plan holds them, and the column `node`. Each weight row's
  `original_key` and `original_value` come from the definition, whose copy, `definition.xml`, is
  its `source_artifact`, or from the ranking variant's `set` entry that changes it, whose source
  is the configuration, as the configuration's reader gives them (`RankingOriginals`).
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import TypedDict

from trialfolio.configuration import WeightOriginal
from trialfolio.contracts.common import (
    FlagCode,
    Interpretation,
    Provenance,
    SettingCategory,
    SettingUnit,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, ExperimentPlanCaseV1_3
from trialfolio.contracts.plan import (
    PlanCase,
    PlanCaseV1_2,
    PlanSetting,
    PlanSettingV1_2,
    SettingValue,
    SettingValueV1_2,
)
from trialfolio.contracts.screen_configuration import FormulaRanking, IdRanking, NameRanking
from trialfolio.contracts.screen_settings import DefinitionRankingSetting
from trialfolio.contracts.tables import MetricsRow, SettingsRow, SettingsRowV1_1
from trialfolio.normalization.layout import METRICS, Coverage, Metric, ScreenBacktestResult, Value
from trialfolio.storage import StoredFile

type AnySettingsRows = tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...]
"""`settings.csv`'s rows: 1.0.0's, or 1.1.0's, for a run or a case whose ranking is a
definition."""


@dataclass(frozen=True)
class RankingOriginals:
    """Where the weight rows of a run or a case whose ranking is a definition take their
    `original_key`, `original_value`, and `source_artifact` from (weight rows)."""

    weights: Mapping[str, WeightOriginal]
    """Each node's, by its canonical path in the case's definition."""
    definition: StoredFile
    """The copy of the definition, `definition.xml`, beside the configuration the plan was built
    from: the `source_artifact` of each weight the definition gives."""


def metrics_rows(
    result: ScreenBacktestResult, *, label: str, benchmark: str, source_artifact: str
) -> tuple[MetricsRow, ...]:
    """`metrics.csv`'s rows for one result, in order: the coverage, then each reported metric.

    `benchmark` is the request's `screen.benchmark`, which the benchmark-relative rows name, and
    `source_artifact` the saved response's `artifact_id`.
    """
    coverage = result.coverage
    calculated = {
        "coverage_start": coverage.start,
        "coverage_end": coverage.end,
        "coverage_periods": Value(str(coverage.periods)),
    }
    period_start = date.fromisoformat(coverage.start.text) if coverage.start.text else None
    period_end = date.fromisoformat(coverage.end.text) if coverage.end.text else None
    rows: list[MetricsRow] = []
    for metric in METRICS:
        value = calculated[metric.metric_id] if metric.path is None else result.values[metric.path]
        rows.append(
            MetricsRow(
                label=label,
                subject=metric.subject,
                metric_id=metric.metric_id,
                source_label=metric.path[-1] if metric.path else None,
                value=value.text,
                unit=metric.unit,
                source_decimals=_decimals(metric, value),
                availability="available" if value.available else "unavailable",
                unavailable_reason=value.reason,
                origin="reported" if metric.path else "calculated",
                provenance="verified" if metric.path else "inferred",
                period_start=period_start,
                period_end=period_end,
                benchmark=benchmark if metric.benchmark_relative else None,
                source_artifact=source_artifact,
                source_location=".".join(metric.path) if metric.path else None,
            )
        )
    return tuple(rows)


def _decimals(metric: Metric, value: Value) -> int | None:
    if value.text is None or metric.kind != "decimal":
        return None
    return len(value.text.partition(".")[2])


def settings_rows(
    case: PlanCase | ExperimentPlanCase,
    originals: Mapping[str, str],
    *,
    label: str,
    source_artifact: str,
    coverage: Coverage,
    original_keys: Mapping[str, str] | None = None,
) -> tuple[SettingsRow, ...]:
    """`settings.csv`'s rows for one result, in order, from the plan's resolved settings.

    The request was sent, so each value has the provenance the plan expected. `originals` holds
    each setting's value as the configuration file writes it, by the setting's name: for a
    screen, each top-level value (`original_values`). `original_keys` gives the key that writes
    each one, when it isn't the setting's name, as in an experiment's configuration.
    `source_artifact` is the saved configuration's `artifact_id`. A date setting is flagged
    `coverage_mismatch` when its coverage date is available and differs from it.
    """
    compared = {"start_date": coverage.start.text, "end_date": coverage.end.text}
    rows: list[SettingsRow] = []
    for setting in case.settings:
        original = originals.get(setting.setting)
        key = setting.setting if original_keys is None else original_keys.get(setting.setting)
        rows.append(
            SettingsRow(
                **_row_fields(setting, label=label, compared=compared),
                original_key=None if original is None else key,
                original_value=original,
                source_artifact=source_artifact,
            )
        )
    return tuple(rows)


def settings_rows_v1_1(
    case: PlanCaseV1_2 | ExperimentPlanCaseV1_3,
    originals: Mapping[str, str],
    ranking: RankingOriginals,
    *,
    label: str,
    source_artifact: str,
    coverage: Coverage,
    original_keys: Mapping[str, str] | None = None,
) -> tuple[SettingsRowV1_1, ...]:
    """`settings.csv` 1.1.0's rows for a run or a case whose ranking is a definition, in order,
    as `settings_rows` gives 1.0.0's, with `node`, and a weight row for each node of the case's
    definition, whose original comes from `ranking` (weight rows)."""
    compared = {"start_date": coverage.start.text, "end_date": coverage.end.text}
    rows: list[SettingsRowV1_1] = []
    for setting in case.settings:
        fields = _row_fields(setting, label=label, compared=compared)
        if setting.node is not None:
            weight = ranking.weights.get(setting.node)
            source = source_artifact
            if weight is not None and weight.in_definition:
                source = ranking.definition.artifact_id
            key, text = (None, None) if weight is None else (weight.key, weight.text)
        else:
            text = originals.get(setting.setting)
            key = setting.setting if original_keys is None else original_keys.get(setting.setting)
            key, source = (None if text is None else key), source_artifact
        rows.append(
            SettingsRowV1_1(
                **fields,
                original_key=key,
                original_value=text,
                source_artifact=source,
                node=setting.node,
            )
        )
    return tuple(rows)


class _RowFields(TypedDict):
    """The columns of a row of `settings.csv` that the plan gives."""

    label: str
    setting: str
    category: SettingCategory
    critical: bool
    value: str
    unit: SettingUnit | None
    interpretation: Interpretation
    provenance: Provenance
    inference_rule: str | None
    flags: tuple[FlagCode, ...]


def _row_fields(
    setting: PlanSetting | PlanSettingV1_2, *, label: str, compared: Mapping[str, str | None]
) -> _RowFields:
    """The columns of a row of `settings.csv`, of either version, that the plan gives: all but
    the original key and value, the source, and `node`. The request was sent, so each value has
    the provenance the plan expected, and a date is flagged `coverage_mismatch` when its
    coverage date is available and differs from it."""
    flags: tuple[FlagCode, ...] = setting.flags
    covered = compared.get(setting.setting)
    if covered is not None and covered != setting.value:
        flags = (*flags, "coverage_mismatch")
    return _RowFields(
        label=label,
        setting=setting.setting,
        category=setting.category,
        critical=setting.critical,
        value=setting_text(setting.value),
        unit=setting.unit,
        interpretation=setting.interpretation,
        provenance=setting.expected_provenance,
        inference_rule=setting.inference_rule,
        flags=flags,
    )


def setting_text(value: SettingValue | SettingValueV1_2) -> str:
    """A resolved value as `settings.csv` writes it: an integer in decimal digits, a list or a
    ranking as JSON with the configuration's keys, or a definition's hash and ranking method,
    and text as it is, a weight's normalized decimal included."""
    match value:
        case int():
            return str(value)
        case str():
            return value
        case FormulaRanking() | NameRanking() | IdRanking() | DefinitionRankingSetting():
            return json.dumps(value.model_dump(mode="json"), ensure_ascii=False)
        case _:
            return json.dumps(list(value), ensure_ascii=False)
