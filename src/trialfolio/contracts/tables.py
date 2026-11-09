"""Rows of the normalized tables `metrics.csv`, `settings.csv`, and `differences.csv`, schema
version 1.0.0 (docs/contracts.md, normalized tables), and the rows of `settings.csv` 1.1.0 and
`differences.csv` 1.1.0, which append one column, `node`, for the weight rows of a ranking given
as a definition (weight rows).

Each model is one row, after a CSV adapter step has read its cells: an empty cell is `None`,
`critical` and `flagged` are booleans, `source_decimals` and `difference_decimals` integers, the
period dates are dates, and `flags` is a tuple of codes, which the CSV joins with semicolons. A
field's position is its column's.

From release 0.5.0, the rows of three new tables, schema version 1.0.0: `series.csv`, each value
of a result's dated series; `analysis.csv`, each value of the analysis set, checked against the
set its `analysis_set` names, `ANALYSIS_SETS`; and an experiment session's `comparison.csv`, each
case's comparison with the baseline. They read the same way, with `inputs` a tuple of series, and
`window_days` and `observations` integers. Each model checks the rules one row shows; whether a
table is exactly what its response, its analysis set, or its comparison gives is the records
check's (series.csv, analysis.csv, comparison.csv).
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Final, Literal, Self, cast

from pydantic import Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    INTEGER_PATTERN,
    METRIC_UNIT_PATTERN,
    AnalysisUnavailableReason,
    AnalysisUnit,
    CaseId,
    ContractModel,
    FlagCode,
    Interpretation,
    MetricUnit,
    NodePathText,
    NonEmptyText,
    Provenance,
    ResultLabel,
    ReviewLabel,
    SemanticVersion,
    SeriesUnavailableReason,
    SettingCategory,
    SettingName,
    SettingUnit,
    Sha256Digest,
    ShortText,
    UnavailableReason,
    require_unique,
    valid_date_text,
)
from trialfolio.contracts.screen_configuration import IdRanking, NameRanking
from trialfolio.contracts.screen_settings import (
    RANKING_WEIGHT,
    SCREEN_SETTINGS_BY_NAME,
    SETTINGS_WITH_WEIGHTS_BY_NAME,
    RankingValues,
    ScreenSetting,
    check_critical,
    check_flags,
    check_row,
    check_value_text,
    documented_setting,
    read_ranking_setting,
)

TABLES_SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of both tables. The manifest records it, because a CSV can't."""

TABLES_SCHEMA_VERSION_V1_1: Final = "1.1.0"
"""The schema version of `settings.csv` and `differences.csv` with weight rows, and the column
`node`."""

ABSENT: Final = "absent"
"""A weight row's value in `differences.csv` for a node one run's definition doesn't have, or
for a run ranked by a formula, which has no nodes (differences between screen runs)."""

_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.(?P<fraction>[0-9]+))?")
_COUNT = re.compile(INTEGER_PATTERN)
_METRIC_UNIT = re.compile(METRIC_UNIT_PATTERN)


class MetricsRow(ContractModel):
    """One row of `metrics.csv`: one metric of one result."""

    label: ResultLabel
    subject: Literal["strategy", "benchmark"]
    metric_id: SettingName
    source_label: NonEmptyText | None
    value: NonEmptyText | None
    """A decimal with exactly its source's digits, or a date. Null when unavailable."""
    unit: MetricUnit
    source_decimals: Annotated[int, Field(ge=0)] | None
    """The digits after the decimal point, as reported. Null for dates, counts, and unavailable
    values."""
    availability: Literal["available", "unavailable"]
    unavailable_reason: UnavailableReason | None
    origin: Literal["reported", "calculated"]
    provenance: Provenance
    period_start: date | None
    period_end: date | None
    benchmark: NonEmptyText | None
    source_artifact: Sha256Digest
    source_location: NonEmptyText | None
    """The value's JSON path in the response. Null for calculated values."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        available = self.availability == "available"
        if (self.value is not None) != available:
            raise ValueError("value must be given exactly when the metric is available")
        if (self.unavailable_reason is None) != available:
            raise ValueError("unavailable_reason must be given exactly when it's unavailable")
        if self.value is not None:
            self._check_value(self.value)
        elif self.source_decimals is not None:
            raise ValueError("source_decimals must be null for an unavailable value")
        if (self.source_location is None) != (self.origin == "calculated"):
            raise ValueError("source_location must be given exactly for a reported value")
        if self.origin == "reported" and self.source_label is None:
            raise ValueError("a reported value has its source_label")
        start, end = self.period_start, self.period_end
        if start is not None and end is not None and start > end:
            raise ValueError("period_start must not be after period_end")
        return self

    def _check_value(self, value: str) -> None:
        if self.unit in ("date", "count"):
            if self.source_decimals is not None:
                raise ValueError("source_decimals must be null for dates and counts")
            if self.unit == "date":
                valid_date_text(value)
            elif not _COUNT.fullmatch(value):
                raise ValueError("a count must be a whole number")
            return
        match = _DECIMAL.fullmatch(value)
        if match is None:
            raise ValueError("value must be a decimal in plain notation")
        if self.source_decimals != len(match.group("fraction") or ""):
            raise ValueError("source_decimals must equal the digits after the decimal point")


class SettingsRow(ContractModel):
    """One row of `settings.csv`: one setting of one result."""

    label: ResultLabel
    setting: SettingName
    category: SettingCategory
    critical: bool
    value: NonEmptyText
    """The normalized value, as text: lists and mappings as JSON, and `not_sent` or
    `not_modeled` when the request gives none. Never empty."""
    unit: SettingUnit | None
    interpretation: Interpretation
    provenance: Provenance
    inference_rule: NonEmptyText | None
    original_key: NonEmptyText | None
    original_value: Annotated[str, Field(min_length=1)] | None
    """The value exactly as written in the configuration; null when absent."""
    source_artifact: Sha256Digest
    flags: tuple[FlagCode, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_settings_row(self, SCREEN_SETTINGS_BY_NAME, "forms")
        return self


def _check_settings_row(
    row: "SettingsRow | SettingsRowV1_1",
    settings: dict[str, ScreenSetting],
    rankings: RankingValues,
) -> ScreenSetting:
    setting = check_row(
        row.setting,
        row.category,
        row.critical,
        row.unit,
        row.interpretation,
        row.provenance,
        row.inference_rule,
        settings=settings,
    )
    value = check_value_text(setting, row.value, rankings)
    if (row.original_key is None) != (row.original_value is None):
        raise ValueError("original_key and original_value must be given together")
    require_unique(row.flags, "flags")
    check_flags(setting, value, row.flags, executed=True, rankings=rankings)
    return setting


METRICS_COLUMNS: Final = tuple(MetricsRow.model_fields)
"""`metrics.csv`'s columns, in order."""

SETTINGS_COLUMNS: Final = tuple(SettingsRow.model_fields)
"""`settings.csv`'s columns, in order."""


SettingClassification = Literal["same", "intended_change", "unexplained_mismatch", "unknown"]

MetricClassification = Literal["differenced", "not_comparable", "unavailable"]

DifferenceReason = Literal[
    "different_benchmark",
    "different_period",
    "unknown_period",
    "different_unit",
    "input_unavailable",
]

DifferenceUnit = Annotated[
    str, StringConstraints(pattern=r"^(pp|ratio|count|days|currency:[A-Z]{3})$")
]
"""A difference's unit: `pp` for percent metrics, `days` for dates, otherwise the metric's."""

FLAGGING: Final[frozenset[str]] = frozenset(
    {
        "critical_unexplained_mismatch",
        "critical_unknown",
        "intended_change_not_observed",
        "coverage_mismatch",
        "unsupported_value",
        "identical_source",
    }
)
"""The flags that set `flagged`. `not_snapshotted` and `inferred_default` don't, because every
screen run's universe, data vendor, and risk statistics period carry them."""

_COMPARISON_FLAGS: Final = frozenset(
    {"critical_unexplained_mismatch", "critical_unknown", "intended_change_not_observed"}
)
"""The flags a setting row's comparison gives it, besides those its runs' rows carry."""


def _decimals(text: str) -> int:
    return len(text.partition(".")[2])


class DifferencesRow(ContractModel):
    """One row of `differences.csv`: one setting or one metric of one result, compared with the
    baseline's (docs/contracts.md, differences between screen runs)."""

    label: ReviewLabel
    baseline_label: ReviewLabel
    kind: Literal["setting", "metric"]
    name: SettingName
    """The setting, or the `metric_id`."""
    subject: Literal["strategy", "benchmark"] | None
    """For metrics. Null for settings."""
    category: SettingCategory | None
    """For settings, as in `settings.csv`. Null for metrics."""
    critical: bool | None
    """For settings, as in `settings.csv`. Null for metrics."""
    baseline_value: NonEmptyText | None
    value: NonEmptyText | None
    """The two values compared, as their tables write them. Null when unavailable."""
    unit: MetricUnit | SettingUnit | None
    classification: SettingClassification | MetricClassification
    difference: NonEmptyText | None
    """For `differenced` metrics, `value - baseline_value`, with exactly `difference_decimals`
    digits after the decimal point, and never a signed zero. Null otherwise."""
    difference_unit: DifferenceUnit | None
    difference_decimals: Annotated[int, Field(ge=0)] | None
    reason: DifferenceReason | None
    """For `not_comparable` and `unavailable` metrics. Null otherwise."""
    declared_reason: ShortText | None
    """For a setting declared as an intended change, its reason, whatever the classification.
    Only a declarable setting has one."""
    flagged: bool
    """True exactly when a flag in `FLAGGING` applies."""
    flags: tuple[FlagCode, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_differences_row(self)
        return self


def _check_differences_row(row: "DifferencesRow | DifferencesRowV1_1") -> None:
    if row.label == row.baseline_label:
        raise ValueError("a row compares a result with the baseline, so the labels differ")
    require_unique(row.flags, "flags")
    if row.kind == "setting":
        _check_setting(row)
    else:
        _check_metric(row)
    if row.flagged != bool(FLAGGING.intersection(row.flags)):
        raise ValueError(
            "flagged must be true exactly when a row carries a flag that needs attention"
        )


def _check_setting(row: "DifferencesRow | DifferencesRowV1_1") -> None:
    weights = isinstance(row, DifferencesRowV1_1)
    settings = SETTINGS_WITH_WEIGHTS_BY_NAME if weights else SCREEN_SETTINGS_BY_NAME
    setting = documented_setting(row.name, row.category, row.unit, settings)
    check_critical(setting, row.critical)
    if row.subject is not None or row.reason is not None:
        raise ValueError("subject and reason are given only for metrics")
    if (row.difference, row.difference_unit, row.difference_decimals) != (None,) * 3:
        raise ValueError("a setting row has no difference")
    if row.classification not in ("same", "intended_change", "unexplained_mismatch", "unknown"):
        raise ValueError("a setting row is same, intended_change, unexplained_mismatch, or unknown")
    values = (row.baseline_value, row.value)
    if setting is RANKING_WEIGHT and values == (ABSENT, ABSENT):
        raise ValueError("a weight row's node is a node of one run's definition, at least")
    rankings: RankingValues = "any" if weights else "forms"
    read = [_read_compared(setting, text, rankings) for text in values]
    _check_compared(row, values, read)
    _check_declared(row, setting)
    _check_setting_flags(row, setting, read, rankings)


def _check_compared(
    row: "DifferencesRow | DifferencesRowV1_1",
    values: tuple[str | None, str | None],
    read: list[object],
) -> None:
    """Raises `ValueError` unless a setting row's classification follows its two values: unknown
    exactly when one is missing, and otherwise same exactly when they're the same."""
    # A value that can't be interpreted can't be written, so an unknown one is missing.
    if (None in values) != (row.classification == "unknown"):
        raise ValueError("a setting is unknown exactly when one of its values is missing")
    if row.classification != "unknown":
        same = read[0] == read[1]
        if same != (row.classification == "same"):
            raise ValueError("a setting is same exactly when its two values are the same")


def _read_compared(setting: ScreenSetting, text: str | None, rankings: RankingValues) -> object:
    """A compared value, as its table writes it: None when it's missing, and for a weight row,
    `absent` for a node the run doesn't have."""
    if text is None:
        return None
    if setting is RANKING_WEIGHT and text == ABSENT:
        return ABSENT
    return check_value_text(setting, text, rankings)


def _check_declared(row: "DifferencesRow | DifferencesRowV1_1", setting: ScreenSetting) -> None:
    """Raises `ValueError` unless the row's declared reason follows its classification. A weight
    row takes its reason from `ranking`'s declaration: only one that differs gives it, as an
    intended change."""
    if setting is RANKING_WEIGHT:
        if (row.classification == "intended_change") != (row.declared_reason is not None):
            raise ValueError(
                "a weight row gives ranking's declared reason exactly when it's an intended change"
            )
        return
    if row.declared_reason is not None and not setting.declarable:
        raise ValueError(f"{row.name} isn't a setting a review can declare")
    if (row.classification == "intended_change") and row.declared_reason is None:
        raise ValueError("an intended change gives its declared_reason")
    if row.classification == "unexplained_mismatch" and row.declared_reason is not None:
        raise ValueError("a declared change isn't unexplained")


def _check_setting_flags(
    row: "DifferencesRow | DifferencesRowV1_1",
    setting: ScreenSetting,
    read: list[object],
    rankings: RankingValues,
) -> None:
    flags = set[str](row.flags)
    critical = bool(row.critical)
    expected = {
        "critical_unexplained_mismatch": critical and row.classification == "unexplained_mismatch",
        # Only in a critical category, even for a declared change that can't be confirmed
        # (owner's decision, 2026-10-05): no flag covers precision, the one declarable
        # setting outside them.
        "critical_unknown": critical and row.classification == "unknown",
        "intended_change_not_observed": row.classification == "same"
        and row.declared_reason is not None,
    }
    for flag, applies in expected.items():
        if (flag in flags) != applies:
            raise ValueError(f"{flag} must be given exactly when it applies")
    # The rest come from the two runs' rows, as check_flags allows them.
    external = setting.kind == "ranking" and any(
        isinstance(read_ranking_setting(value, rankings), NameRanking | IdRanking)
        for value in read
        if value is not None
    )
    required = set[str](setting.flags) | ({"not_snapshotted"} if external else set[str]())
    optional = {"coverage_mismatch"} if setting.kind == "date" else set[str]()
    if not required <= flags - _COMPARISON_FLAGS <= required | optional:
        raise ValueError(f"{row.name}'s flags must be those its runs' rows carry")


def _check_metric(row: "DifferencesRow | DifferencesRowV1_1") -> None:
    if row.subject is None:
        raise ValueError("a metric row gives its subject")
    if (row.category, row.critical, row.declared_reason) != (None,) * 3:
        raise ValueError("category, critical, and declared_reason are given only for settings")
    unit = row.unit
    if unit is None or not _METRIC_UNIT.fullmatch(unit):
        raise ValueError("a metric row gives a metric's unit")
    if not set[str](row.flags) <= {"identical_source"}:
        raise ValueError("a metric row's only flag is identical_source")
    for text in (row.baseline_value, row.value):
        if text is not None:
            _check_metric_value(text, unit)
    given = (row.difference, row.difference_unit, row.difference_decimals)
    if row.classification != "differenced" and given != (None,) * 3:
        raise ValueError("only a differenced row has a difference, its unit, and its decimals")
    _check_metric_classification(row, unit)


def _check_metric_classification(
    row: "DifferencesRow | DifferencesRowV1_1 | ComparisonRow", unit: str
) -> None:
    """Raises `ValueError` unless a metric row's classification follows its values: a difference
    for a differenced row, both values and why for one that isn't comparable, and a missing value
    for an unavailable one. A row of `comparison.csv` follows the same rules."""
    match row.classification:
        case "differenced":
            _check_difference(row, unit)
        case "not_comparable":
            if None in (row.baseline_value, row.value):
                raise ValueError("a row that isn't comparable shows both values")
            if row.reason in (None, "input_unavailable"):
                raise ValueError("a row that isn't comparable gives why")
        case "unavailable":
            if None not in (row.baseline_value, row.value):
                raise ValueError("a row is unavailable only when a value is")
            if row.reason != "input_unavailable":
                raise ValueError("an unavailable row's reason is input_unavailable")
        case _:
            raise ValueError("a metric row is differenced, not_comparable, or unavailable")


def _check_difference(
    row: "DifferencesRow | DifferencesRowV1_1 | ComparisonRow", unit: str
) -> None:
    baseline, value, difference = row.baseline_value, row.value, row.difference
    if baseline is None or value is None or difference is None:
        raise ValueError("a differenced row has both values and their difference")
    if row.reason is not None:
        raise ValueError("a differenced row has no reason")
    expected_unit = {"percent": "pp", "date": "days"}.get(unit, unit)
    if row.difference_unit != expected_unit:
        raise ValueError("difference_unit is pp for percent, days for dates, else the unit")
    decimals = 0 if unit in ("date", "count") else min(_decimals(baseline), _decimals(value))
    if row.difference_decimals != decimals:
        raise ValueError(
            "difference_decimals is the smaller source decimals, 0 for dates and counts"
        )
    if not _DECIMAL.fullmatch(difference) or _decimals(difference) != decimals:
        raise ValueError("a difference has exactly difference_decimals digits after the point")
    if difference.startswith("-") and Decimal(difference).is_zero():
        raise ValueError("a difference of zero is written without a sign")


def _check_metric_value(text: str, unit: str) -> None:
    if unit == "date":
        valid_date_text(text)
    elif unit == "count":
        if not _COUNT.fullmatch(text):
            raise ValueError("a count must be a whole number")
    elif not _DECIMAL.fullmatch(text):
        raise ValueError("a metric's value must be a decimal in plain notation")


DIFFERENCES_COLUMNS: Final = tuple(DifferencesRow.model_fields)
"""`differences.csv`'s columns, in order."""


# Version 1.1.0 of settings.csv and differences.csv: the weight rows, and `node`.


class SettingsRowV1_1(ContractModel):
    """One row of `settings.csv` 1.1.0, a run's or a case's whose ranking is a definition: 1.0.0's
    columns, then `node`, the canonical path of a weight row's node, and empty on every other row
    (weight rows)."""

    label: ResultLabel
    setting: SettingName
    category: SettingCategory
    critical: bool
    value: NonEmptyText
    """The normalized value, as text: lists and mappings as JSON, a weight as its normalized
    decimal, and `not_sent` or `not_modeled` when the request gives none. Never empty."""
    unit: SettingUnit | None
    interpretation: Interpretation
    provenance: Provenance
    inference_rule: NonEmptyText | None
    original_key: NonEmptyText | None
    original_value: Annotated[str, Field(min_length=1)] | None
    """The value exactly as written in its source: the configuration, or for a weight the
    definition gives, the definition's `Weight` attribute; null when absent."""
    source_artifact: Sha256Digest
    """The `artifact_id` of the saved configuration, or of the saved definition, `definition.xml`,
    for a weight row whose value the definition gives."""
    flags: tuple[FlagCode, ...]
    node: NodePathText | None
    """A weight row's node, by its canonical path; null on every other row."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        setting = _check_settings_row(self, SETTINGS_WITH_WEIGHTS_BY_NAME, "definition")
        if (self.node is None) == (setting is RANKING_WEIGHT):
            raise ValueError("node is given on a weight row, and only there")
        return self


SETTINGS_COLUMNS_V1_1: Final = tuple(SettingsRowV1_1.model_fields)
"""`settings.csv` 1.1.0's columns, in order."""


class DifferencesRowV1_1(ContractModel):
    """One row of `differences.csv` 1.1.0, a review's in which any result has weight rows: 1.0.0's
    columns, then `node`, which names a weight's setting row with `name`, and is empty on every
    other row (differences between screen runs, weight rows)."""

    label: ReviewLabel
    baseline_label: ReviewLabel
    kind: Literal["setting", "metric"]
    name: SettingName
    """The setting, `ranking_weight` for a weight, or the `metric_id`."""
    subject: Literal["strategy", "benchmark"] | None
    """For metrics. Null for settings."""
    category: SettingCategory | None
    """For settings, as in `settings.csv`. Null for metrics."""
    critical: bool | None
    """For settings, as in `settings.csv`. Null for metrics."""
    baseline_value: NonEmptyText | None
    value: NonEmptyText | None
    """The two values compared, as their tables write them, or `absent` for a node a run's
    definition doesn't have. Null when unavailable, or unknown."""
    unit: MetricUnit | SettingUnit | None
    classification: SettingClassification | MetricClassification
    difference: NonEmptyText | None
    """For `differenced` metrics, `value - baseline_value`, with exactly `difference_decimals`
    digits after the decimal point, and never a signed zero. Null otherwise."""
    difference_unit: DifferenceUnit | None
    difference_decimals: Annotated[int, Field(ge=0)] | None
    reason: DifferenceReason | None
    """For `not_comparable` and `unavailable` metrics. Null otherwise."""
    declared_reason: ShortText | None
    """For a setting declared as an intended change, its reason, whatever the classification;
    for a weight that differs, `ranking`'s."""
    flagged: bool
    """True exactly when a flag in `FLAGGING` applies."""
    flags: tuple[FlagCode, ...]
    node: NodePathText | None
    """A weight's node, by its canonical path; null on every other row."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_differences_row(self)
        if (self.node is None) == (self.kind == "setting" and self.name == RANKING_WEIGHT.name):
            raise ValueError("node is given on a weight's setting row, and only there")
        return self


DIFFERENCES_COLUMNS_V1_1: Final = tuple(DifferencesRowV1_1.model_fields)
"""`differences.csv` 1.1.0's columns, in order."""


# Release 0.5.0's tables, schema version 1.0.0: series.csv, analysis.csv, and comparison.csv.

SERIES_TABLES_SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of `series.csv`, `analysis.csv`, and `comparison.csv`, which the manifest
records, because a CSV can't."""

_INDEX = r"(0|[1-9][0-9]*)"

SourceLocation = Annotated[
    str,
    StringConstraints(
        pattern=rf"^(chart\.(screenReturns|benchReturns)\[{_INDEX}\]"
        rf"|results\.rows\[{_INDEX}\]\[{_INDEX}\])$"
    ),
]
"""A series value's JSON path in the response: a `chart` level's, or a period's cell's, each
position counted from 0 (series.csv)."""

_DAILY_SOURCES: Final = {"strategy": "screenReturns", "benchmark": "benchReturns"}
_PERIOD_SOURCES: Final = {"strategy": "Ret%", "benchmark": "Bench%", "excess": "Excess%"}


def _check_decimal(value: str, decimals: int | None, what: str) -> Decimal:
    """`value` as a decimal, once checked: plain notation, with exactly `decimals` digits after
    its point. Raises `ValueError` otherwise."""
    match = _DECIMAL.fullmatch(value)
    if match is None:
        raise ValueError(f"{what} must be a decimal in plain notation")
    if decimals != len(match.group("fraction") or ""):
        raise ValueError(f"{what} has exactly its decimals' digits after the decimal point")
    return Decimal(value)


CalendarDate = date
"""`date`, by a name `SeriesRow`'s field `date` doesn't hide from the fields after it."""


class SeriesRow(ContractModel):
    """One row of `series.csv`: a `chart` level of the strategy or the benchmark, or a rebalance
    period's return of the strategy, the benchmark, or the excess, as the saved response gives
    it, with the digits its text has (series.csv)."""

    label: ResultLabel
    """The case's `case_id`, as in `metrics.csv`."""
    series: Literal["daily", "period"]
    subject: Literal["strategy", "benchmark", "excess"]
    """`excess`, the period's `Excess%`, on a period row only."""
    date: CalendarDate | None
    """A daily row's `chart` date, or a period row's `End Dt`. Null when the series is
    unavailable, or the date can't be read."""
    period_start: CalendarDate | None
    """A period row's `Tran Dt`. Null on a daily row, and when it can't be read."""
    value: NonEmptyText | None
    """The level, or the return in percent, as a normalized decimal with the digits the saved text
    has. Null when unavailable."""
    unit: Literal["index", "percent"]
    """`index` on a daily row, `percent` on a period row."""
    source_decimals: Annotated[int, Field(ge=0)] | None
    """The digits after the decimal point, as saved. Null when unavailable."""
    availability: Literal["available", "unavailable"]
    unavailable_reason: SeriesUnavailableReason | None
    origin: Literal["reported"]
    provenance: Literal["verified"]
    source_label: Literal["screenReturns", "benchReturns", "Ret%", "Bench%", "Excess%"]
    source_artifact: Sha256Digest
    """The `artifact_id` of the saved response."""
    source_location: SourceLocation | None
    """The value's JSON path in the response. Null when the whole series is unavailable, or the
    column is missing."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        available = self.availability == "available"
        if (self.value is not None) != available:
            raise ValueError("value must be given exactly when the value is available")
        if (self.unavailable_reason is None) != available:
            raise ValueError("unavailable_reason must be given exactly when it's unavailable")
        if self.value is None:
            if self.source_decimals is not None:
                raise ValueError("source_decimals must be null for an unavailable value")
        elif self.source_location is None or self.date is None:
            raise ValueError("an available value gives its date and its source_location")
        if self.series == "daily":
            self._check_daily()
        else:
            self._check_period()
        return self

    def _check_daily(self) -> None:
        if self.subject == "excess" or self.unit != "index" or self.period_start is not None:
            raise ValueError(
                "a daily row is the strategy's or the benchmark's level, in index, with no "
                "period_start"
            )
        source = _DAILY_SOURCES[self.subject]
        if self.source_label != source:
            raise ValueError(f"the {self.subject}'s daily row's source_label is {source}")
        if self.value is None:
            if (self.date, self.source_location) != (None, None):
                raise ValueError("an unavailable daily row has no date and no source_location")
            return
        if self.source_location is not None and not self.source_location.startswith(
            f"chart.{source}["
        ):
            raise ValueError(f"the {self.subject}'s daily row's source_location is in {source}")
        if _check_decimal(self.value, self.source_decimals, "value") <= 0:
            raise ValueError("a level is greater than 0")

    def _check_period(self) -> None:
        if self.unit != "percent" or self.unavailable_reason == "not_daily":
            raise ValueError("a period row's return is in percent, and never not_daily")
        source = _PERIOD_SOURCES[self.subject]
        if self.source_label != source:
            raise ValueError(f"the {self.subject}'s period row's source_label is {source}")
        if self.source_location is not None and not self.source_location.startswith("results."):
            raise ValueError("a period row's source_location is a cell of results.rows")
        if self.value is not None:
            if self.period_start is None:
                raise ValueError("an available period row gives its period_start")
            _check_decimal(self.value, self.source_decimals, "value")


SERIES_COLUMNS: Final = tuple(SeriesRow.model_fields)
"""`series.csv`'s columns, in order."""


AnalysisSubject = Literal["strategy", "benchmark", "excess"]
"""The series a value of the analysis set describes: `excess` is the strategy against the
benchmark."""

InputSeries = Literal[
    "daily",
    "period",
    "daily/strategy",
    "daily/benchmark",
    "period/strategy",
    "period/benchmark",
    "period/excess",
]
"""A series a value of the analysis set reads, as `<series>/<subject>`, or a series alone for a
value that reads its dates and none of its values (analysis.csv)."""

AnalysisFlag = Literal["descriptive", "overlapping_windows", "not_recovered"]
"""`analysis.csv`'s flags, in the order its table gives them."""

AnalysisName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
"""An analysis's identifier in its set, in snake_case, such as `max_drawdown`."""

Segment = Annotated[str, StringConstraints(pattern=r"^(full|split-([0-9]|10))$")]
"""`full`, the whole series, or a split segment, `split-0` to `split-10`, since a configuration
declares at most 10 splits (segments)."""

NamedReason = Literal["not_applicable", "too_short", "not_recovered"]
"""A reason the analysis set gives only the analyses whose definition names it, when what they
need doesn't hold (analysis.csv, a row's rules)."""

NAMED_REASONS: Final[tuple[NamedReason, ...]] = ("not_applicable", "too_short", "not_recovered")
"""Each named reason."""


@dataclass(frozen=True)
class AnalysisDefinition:
    """One analysis of an analysis set, as `analysis.csv`'s rows give it: its unit, the subjects
    it has a row for, in their order, or None for a value about the segment or the windows, the
    series it reads, where it's calculated, the flag each of its rows carries, and the reasons
    its definition names."""

    unit: AnalysisUnit
    subjects: tuple[AnalysisSubject | None, ...]
    series: Literal["period", "daily"]
    segments: Literal["any", "full", "split"]
    """Where it has rows: every segment, the `full` segment alone, or split segments alone."""
    flag: Literal["descriptive", "overlapping_windows"] | None = None
    """The flag every row of it carries, whatever its availability."""
    windows: bool = False
    """A rolling return's, with a row for each window length."""
    reasons: tuple[NamedReason, ...] = ()
    """The named reasons it may be unavailable with: an analysis whose definition names none is
    never unavailable with one."""

    def inputs(self, name: str, subject: AnalysisSubject | None) -> tuple[InputSeries, ...]:
        """The `inputs` of its row for `subject`: none for `coverage_share`, from dates alone;
        the series for a value without a subject; both daily series for the excess of the
        daily levels; and otherwise its series of `subject`."""
        if name == "coverage_share":
            return ()
        if subject is None:
            return (self.series,)
        if subject == "excess" and self.series == "daily":
            return ("daily/strategy", "daily/benchmark")
        return (cast("InputSeries", f"{self.series}/{subject}"),)


_SBE: Final[tuple[AnalysisSubject, ...]] = ("strategy", "benchmark", "excess")
_SB: Final[tuple[AnalysisSubject, ...]] = ("strategy", "benchmark")
_E: Final[tuple[AnalysisSubject, ...]] = ("excess",)
_NONE: Final[tuple[None]] = (None,)
_NOT_APPLICABLE: Final[tuple[NamedReason, ...]] = ("not_applicable",)

ANALYSIS_SET_1_0_0: Final[dict[str, AnalysisDefinition]] = {
    # The period-return analyses (methodology.md, period-return analyses).
    "coverage_share": AnalysisDefinition(
        "percent", _NONE, "period", "split", reasons=_NOT_APPLICABLE
    ),
    "period_count": AnalysisDefinition("count", _NONE, "period", "any"),
    "spanning_period_count": AnalysisDefinition("count", _NONE, "period", "split"),
    "mean_period_return": AnalysisDefinition("percent", _SBE, "period", "any"),
    "median_period_return": AnalysisDefinition("percent", _SBE, "period", "any"),
    "best_period_return": AnalysisDefinition("percent", _SBE, "period", "any"),
    "worst_period_return": AnalysisDefinition("percent", _SBE, "period", "any"),
    "positive_excess_share": AnalysisDefinition("percent", _E, "period", "any"),
    "tracking_error": AnalysisDefinition("percent", _E, "period", "any", "descriptive"),
    "information_ratio": AnalysisDefinition(
        "ratio", _E, "period", "any", "descriptive", reasons=_NOT_APPLICABLE
    ),
    "excess_t_value": AnalysisDefinition(
        "ratio", _E, "period", "any", "descriptive", reasons=_NOT_APPLICABLE
    ),
    # The daily-level analyses (methodology.md, daily-level analyses).
    "total_return": AnalysisDefinition("percent", _SB, "daily", "any"),
    "total_return_difference": AnalysisDefinition("pp", _E, "daily", "any"),
    "annualized_return": AnalysisDefinition("percent", _SB, "daily", "any", reasons=("too_short",)),
    "annualized_return_difference": AnalysisDefinition("pp", _E, "daily", "any"),
    "max_drawdown": AnalysisDefinition("percent", _SB, "daily", "any"),
    "max_drawdown_recovery": AnalysisDefinition(
        "date", _SB, "daily", "any", reasons=("not_applicable", "not_recovered")
    ),
    "longest_drawdown_days": AnalysisDefinition("days", _SB, "daily", "any"),
    # The rolling returns, for each window length (methodology.md, rolling returns).
    "rolling_window_count": AnalysisDefinition("count", _NONE, "daily", "full", windows=True),
    "rolling_non_overlapping_count": AnalysisDefinition(
        "count", _NONE, "daily", "full", windows=True
    ),
    **{
        name: AnalysisDefinition(
            "percent", _SB, "daily", "full", "overlapping_windows", windows=True
        )
        for name in ("rolling_mean", "rolling_median", "rolling_p10", "rolling_p90")
    },
    "rolling_worst": AnalysisDefinition(
        "percent", _SB, "daily", "full", "overlapping_windows", windows=True
    ),
    "rolling_share_beating": AnalysisDefinition(
        "percent", _E, "daily", "full", "overlapping_windows", windows=True
    ),
}
"""Analysis set 1.0.0's 26 analyses, by identifier, in the order of `analysis.csv`'s rows within
a segment: the period returns', then the daily levels', then the rolling returns', each analysis's
subjects in the order strategy, benchmark, excess (analysis set 1.0.0, analysis.csv)."""

ROLLING_WINDOWS_1_0_0: Final = (7, 30, 90, 180, 365)
"""Analysis set 1.0.0's window lengths, in calendar days, shortest first (rolling returns)."""

RECONCILED_1_0_0: Final = frozenset({"total_return", "annualized_return", "max_drawdown"})
"""The analyses whose `full` segment's values, for the strategy and the benchmark, are
reconciled with the metric Portfolio123 reports with the same `metric_id` (reconciliation)."""


@dataclass(frozen=True)
class AnalysisSet:
    """An analysis set's analyses, window lengths, and reconciled analyses."""

    analyses: dict[str, AnalysisDefinition]
    windows: tuple[int, ...]
    reconciled: frozenset[str]


ANALYSIS_SETS: Final = {
    "1.0.0": AnalysisSet(ANALYSIS_SET_1_0_0, ROLLING_WINDOWS_1_0_0, RECONCILED_1_0_0)
}
"""Each analysis set this version knows, by its version. A row of any other is refused."""


def _analysis_definition(
    analysis_set: AnalysisSet, segment: str, name: str, subject: str | None, window: int | None
) -> AnalysisDefinition:
    """The definition of the analysis a row names, once its segment, subject, and window are
    checked against it. Raises `ValueError` otherwise."""
    definition = analysis_set.analyses.get(name)
    if definition is None:
        raise ValueError("analysis isn't one of its analysis set's")
    if subject not in definition.subjects:
        raise ValueError(f"{name} has a row for each of its subjects, and no other")
    if definition.segments == "full" and segment != "full":
        raise ValueError(f"{name} is calculated over the full segment only")
    if definition.segments == "split" and segment == "full":
        raise ValueError(f"{name} is calculated over split segments only")
    if (window is not None) != definition.windows or (
        window is not None and window not in analysis_set.windows
    ):
        raise ValueError("window_days is a rolling return's window length, and given only there")
    return definition


class AnalysisRow(ContractModel):
    """One row of `analysis.csv`: one value of the analysis set for a result, calculated from its
    `series.csv`, settings, `metrics.csv`, and its plan's period splits (analysis.csv)."""

    label: ResultLabel
    """The case's `case_id`, as in `series.csv`."""
    analysis_set: SemanticVersion
    """The analysis set's version, `1.0.0`, independent of the table's schema version."""
    segment: Segment
    analysis: AnalysisName
    subject: AnalysisSubject | None
    """Null on a value about the segment or the windows rather than a series."""
    window_days: Annotated[int, Field(ge=1)] | None
    """A rolling return's window length, in calendar days. Null otherwise."""
    value: NonEmptyText | None
    """A decimal with exactly `decimals` digits after its point, a whole number, or a date. A
    decimal that rounds to zero is written without a sign. Null when unavailable."""
    unit: AnalysisUnit
    decimals: Annotated[int, Field(ge=0)] | None
    """The result's `precision` for `percent`, `pp`, and `ratio`, and 0 for `count` and `days`.
    Null for a date, and when unavailable."""
    availability: Literal["available", "unavailable"]
    unavailable_reason: AnalysisUnavailableReason | None
    observations: Annotated[int, Field(ge=0)] | None
    """The observations behind the value, or, with too few, the number there were. Null when an
    input is unavailable, and on `coverage_share`."""
    period_start: date | None
    period_end: date | None
    """The dates the value covers, as the analysis set gives them. Null when unavailable, and
    where the analysis set gives none."""
    reported_value: NonEmptyText | None
    """On a reconciled value, the metric's `value` in `metrics.csv`, as written there. Null
    otherwise, and when that metric is unavailable."""
    reconciliation: Literal["agrees", "differs", "not_compared"] | None
    """On a reconciled value; null on every other."""
    flags: tuple[AnalysisFlag, ...]
    inputs: tuple[InputSeries, ...]
    """The series it's calculated from."""
    origin: Literal["calculated"]
    provenance: Literal["inferred"]
    trialfolio_version: SemanticVersion
    """The version that calculated it."""
    source_artifact: Sha256Digest
    """The `artifact_id` of the saved response its series came from."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        analysis_set = ANALYSIS_SETS.get(self.analysis_set)
        if analysis_set is None:
            raise ValueError("analysis_set isn't one this version of Trial Folio knows")
        definition = _analysis_definition(
            analysis_set, self.segment, self.analysis, self.subject, self.window_days
        )
        if self.unit != definition.unit:
            raise ValueError(f"{self.analysis}'s unit is {definition.unit}")
        if self.inputs != definition.inputs(self.analysis, self.subject):
            raise ValueError(f"{self.analysis}'s inputs are the series it's calculated from")
        self._check_flags(definition)
        self._check_value()
        self._check_reason(definition)
        self._check_dates()
        # A reconciled analysis's subjects are the strategy and the benchmark, each a metric's.
        reconciled = self.segment == "full" and self.analysis in analysis_set.reconciled
        _check_reconciliation(self, reconciled)
        return self

    def _check_flags(self, definition: AnalysisDefinition) -> None:
        require_unique(self.flags, "flags")
        expected = {definition.flag} - {None}
        if self.analysis == "longest_drawdown_days" and "not_recovered" in self.flags:
            if self.value is None:
                raise ValueError("not_recovered flags a time below a peak that has a value")
            expected.add("not_recovered")
        if set[str](self.flags) != expected:
            raise ValueError(
                "descriptive and overlapping_windows are on every row of their analyses, and "
                "not_recovered only on longest_drawdown_days"
            )

    def _check_value(self) -> None:
        available = self.availability == "available"
        if (self.value is not None) != available:
            raise ValueError("value must be given exactly when the value is available")
        if (self.unavailable_reason is None) != available:
            raise ValueError("unavailable_reason must be given exactly when it's unavailable")
        if self.analysis == "coverage_share" or self.unavailable_reason == "input_unavailable":
            if self.observations is not None:
                raise ValueError(
                    "observations is null on coverage_share, and when an input is unavailable"
                )
        elif (available or self.unavailable_reason == "too_few_observations") and (
            self.observations is None
        ):
            raise ValueError(
                "observations gives the count behind a value, or the too few there were"
            )
        if self.value is None:
            if self.decimals is not None:
                raise ValueError("decimals must be null for an unavailable value")
            return
        _check_analysis_value(self.value, self.unit, self.decimals)

    def _check_reason(self, definition: AnalysisDefinition) -> None:
        """A named reason only on an analysis whose definition names it, and `outside_coverage`
        only on a split segment, which the coverage may not reach."""
        reason = self.unavailable_reason
        if reason in NAMED_REASONS and reason not in definition.reasons:
            raise ValueError(f"{reason} isn't a reason {self.analysis}'s definition gives")
        if reason == "outside_coverage" and self.segment == "full":
            raise ValueError("outside_coverage is a split segment's reason")

    def _check_dates(self) -> None:
        start, end = self.period_start, self.period_end
        if (start is None) != (end is None):
            raise ValueError("period_start and period_end are given together")
        if start is not None and self.value is None:
            raise ValueError("an unavailable value has no dates")
        if start is not None and end is not None and start > end:
            raise ValueError("period_start must not be after period_end")


def _check_analysis_value(value: str, unit: str, decimals: int | None) -> None:
    """Raises `ValueError` unless an available value is written in its unit's form: a date with
    no decimals; a whole number of 0 or more with 0 decimals; or a decimal with exactly its
    decimals' digits, a zero without a sign."""
    if unit == "date":
        if decimals is not None:
            raise ValueError("decimals must be null for a date")
        valid_date_text(value)
        return
    if unit in ("count", "days"):
        if decimals != 0 or not _COUNT.fullmatch(value):
            raise ValueError("a count or a number of days is a whole number, with 0 decimals")
        return
    # A value in percent, pp, or a ratio without its decimals has digits they don't give.
    if _check_decimal(value, decimals, "value").is_zero() and value.startswith("-"):
        raise ValueError("a value that rounds to zero is written without a sign")


def _check_reconciliation(row: AnalysisRow, reconciled: bool) -> None:
    """Raises `ValueError` unless a reconciled value gives the reported metric's value, when
    it's available, and whether the two agree, or that they weren't compared, when either is
    unavailable; and every other value gives neither."""
    if not reconciled:
        if (row.reported_value, row.reconciliation) != (None, None):
            raise ValueError("only a reconciled value gives reported_value and reconciliation")
        return
    if row.reconciliation is None:
        raise ValueError("a reconciled value gives its reconciliation")
    compared = row.value is not None and row.reported_value is not None
    if compared != (row.reconciliation != "not_compared"):
        raise ValueError(
            "a reconciliation is not_compared exactly when either value is unavailable"
        )
    if row.reported_value is not None and not _DECIMAL.fullmatch(row.reported_value):
        raise ValueError("reported_value is the metric's value, a decimal in plain notation")


ANALYSIS_COLUMNS: Final = tuple(AnalysisRow.model_fields)
"""`analysis.csv`'s columns, in order."""


ComparisonReason = Literal[
    "input_unavailable",
    "different_unit",
    "different_benchmark",
    "different_period",
    "unknown_period",
    "different_rebalance",
]
"""Why a pair isn't differenced: a review's metric rows' reasons, and `different_rebalance`, for a
value from period returns of two cases whose `rebalance_weeks` differ (comparing a case with the
baseline)."""

_PAIR_REASON_RULES: Final = {
    "different_unit": "an analysis row's two values are in its analysis's unit, so they're never "
    "different_unit",
    "different_benchmark": "different_benchmark is a reason of a value whose inputs include the "
    "benchmark or the excess",
    "unknown_period": "unknown_period is a reason of a value from period returns",
    "different_rebalance": "different_rebalance is a reason of a value from period returns",
}
"""Each reason only some analysis values' pairs give, with its rule (comparing a case with the
baseline)."""


def _pair_reasons(
    definition: AnalysisDefinition, name: str, subject: AnalysisSubject | None
) -> set[str]:
    """The reasons a pair of the analysis's values may give: `input_unavailable` and
    `different_period` for any; `different_benchmark` for a value whose inputs include the
    benchmark or the excess; and `unknown_period` and `different_rebalance` for a value from
    period returns. Never `different_unit`, since both are in the analysis's unit."""
    reasons = {"input_unavailable", "different_period"}
    if any(
        series.endswith(("/benchmark", "/excess")) for series in definition.inputs(name, subject)
    ):
        reasons.add("different_benchmark")
    if definition.series == "period":
        reasons |= {"unknown_period", "different_rebalance"}
    return reasons


class ComparisonRow(ContractModel):
    """One row of `comparison.csv`: one metric or one analysis value of a case, compared with the
    baseline's, by `baseline-comparison` version 1 (comparing a case with the baseline,
    comparison.csv)."""

    label: CaseId
    """The compared case's `case_id`, as its tables label its rows."""
    baseline_label: CaseId
    """The baseline's `case_id`."""
    kind: Literal["metric", "analysis"]
    """A row of `metrics.csv`, or of `analysis.csv`."""
    segment: Segment | None
    """An analysis row's `segment`. Null on a metric row."""
    name: AnalysisName
    """The metric's `metric_id`, or the analysis row's `analysis`."""
    subject: AnalysisSubject | None
    """The two rows' `subject`. Null where `analysis.csv`'s is."""
    window_days: Annotated[int, Field(ge=1)] | None
    """An analysis row's `window_days`. Null otherwise."""
    baseline_value: NonEmptyText | None
    value: NonEmptyText | None
    """The baseline's and the case's values, as their tables write them. Null when unavailable."""
    unit: MetricUnit | AnalysisUnit
    """The two rows' unit."""
    classification: MetricClassification
    difference: NonEmptyText | None
    """For `differenced`, `value - baseline_value`, with exactly `difference_decimals` digits
    after its point, and without a sign when it's zero. Null otherwise."""
    difference_unit: DifferenceUnit | None
    difference_decimals: Annotated[int, Field(ge=0)] | None
    reason: ComparisonReason | None
    """For `not_comparable` and `unavailable`, the first reason that applies. Null otherwise."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.label == self.baseline_label:
            raise ValueError("a row compares a case with the baseline, so the labels differ")
        if self.kind == "metric":
            self._check_metric()
        else:
            self._check_analysis()
        for text in (self.baseline_value, self.value):
            if text is not None:
                _check_compared_value(text, self.unit)
        given = (self.difference, self.difference_unit, self.difference_decimals)
        if self.classification != "differenced" and given != (None,) * 3:
            raise ValueError("only a differenced row has a difference, its unit, and its decimals")
        _check_metric_classification(self, self.unit)
        return self

    def _check_metric(self) -> None:
        if (self.segment, self.window_days) != (None, None):
            raise ValueError("a metric row has no segment and no window_days")
        if self.subject not in ("strategy", "benchmark") or not _METRIC_UNIT.fullmatch(self.unit):
            raise ValueError("a metric row gives a metric's subject and unit")
        if self.reason == "different_rebalance":
            raise ValueError("different_rebalance is a reason of a value from period returns")

    def _check_analysis(self) -> None:
        if self.segment is None:
            raise ValueError("an analysis row gives its segment")
        # The table doesn't hold the analysis set's version, so the row is one of any set's.
        definitions: list[AnalysisDefinition] = []
        for analysis_set in ANALYSIS_SETS.values():
            try:
                definition = _analysis_definition(
                    analysis_set, self.segment, self.name, self.subject, self.window_days
                )
            except ValueError:
                continue
            if self.unit == definition.unit:
                definitions.append(definition)
        if not definitions:
            raise ValueError("an analysis row is a row of an analysis set, with its unit")
        reason = self.reason
        if reason is not None and not any(
            reason in _pair_reasons(definition, self.name, self.subject)
            for definition in definitions
        ):
            raise ValueError(_PAIR_REASON_RULES[reason])


def _check_compared_value(text: str, unit: str) -> None:
    """Raises `ValueError` unless a compared value is written as its table writes a value of its
    unit."""
    if unit == "days":
        if not _COUNT.fullmatch(text):
            raise ValueError("a number of days is a whole number")
        return
    _check_metric_value(text, unit)


COMPARISON_COLUMNS: Final = tuple(ComparisonRow.model_fields)
"""`comparison.csv`'s columns, in order."""
