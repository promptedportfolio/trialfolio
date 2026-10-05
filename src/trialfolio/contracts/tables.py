"""Rows of the normalized tables `metrics.csv`, `settings.csv`, and `differences.csv`, schema
version 1.0.0 (docs/contracts.md, normalized tables).

Each model is one row, after a CSV adapter step has read its cells: an empty cell is `None`,
`critical` and `flagged` are booleans, `source_decimals` and `difference_decimals` integers, the
period dates are dates, and `flags` is a tuple of codes, which the CSV joins with semicolons. A
field's position is its column's.
"""

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Final, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from trialfolio.contracts.common import (
    CRITICAL_CATEGORIES,
    INTEGER_PATTERN,
    ContractModel,
    FlagCode,
    Interpretation,
    MetricUnit,
    NonEmptyText,
    Provenance,
    ResultLabel,
    ReviewLabel,
    SettingCategory,
    SettingName,
    SettingUnit,
    Sha256Digest,
    ShortText,
    UnavailableReason,
    require_unique,
    valid_date_text,
)
from trialfolio.contracts.screen_configuration import IdRanking, NameRanking, read_ranking
from trialfolio.contracts.screen_settings import (
    SCREEN_SETTINGS_BY_NAME,
    ScreenSetting,
    check_flags,
    check_row,
    check_value_text,
)

TABLES_SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of both tables. The manifest records it, because a CSV can't."""

_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.(?P<fraction>[0-9]+))?")
_COUNT = re.compile(INTEGER_PATTERN)
_METRIC_UNIT = re.compile(r"percent|ratio|count|days|date|currency:[A-Z]{3}")


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
        setting = check_row(
            self.setting,
            self.category,
            self.critical,
            self.unit,
            self.interpretation,
            self.provenance,
            self.inference_rule,
        )
        value = check_value_text(setting, self.value)
        if (self.original_key is None) != (self.original_value is None):
            raise ValueError("original_key and original_value must be given together")
        require_unique(self.flags, "flags")
        check_flags(setting, value, self.flags, executed=True)
        return self


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
        if self.label == self.baseline_label:
            raise ValueError("a row compares a result with the baseline, so the labels differ")
        require_unique(self.flags, "flags")
        if self.kind == "setting":
            self._check_setting()
        else:
            self._check_metric()
        if self.flagged != bool(FLAGGING.intersection(self.flags)):
            raise ValueError(
                "flagged must be true exactly when a row carries a flag that needs attention"
            )
        return self

    def _check_setting(self) -> None:
        setting = SCREEN_SETTINGS_BY_NAME.get(self.name)
        if setting is None:
            raise ValueError(f"{self.name} isn't one of the screen settings")
        if (self.category, self.unit) != (setting.category, setting.unit):
            raise ValueError(f"{self.name} must have its documented category and unit")
        if self.critical != (setting.category in CRITICAL_CATEGORIES):
            raise ValueError("critical must be true exactly for the critical categories")
        if self.subject is not None or self.reason is not None:
            raise ValueError("subject and reason are given only for metrics")
        if (self.difference, self.difference_unit, self.difference_decimals) != (None,) * 3:
            raise ValueError("a setting row has no difference")
        if self.classification not in (
            "same",
            "intended_change",
            "unexplained_mismatch",
            "unknown",
        ):
            raise ValueError(
                "a setting row is same, intended_change, unexplained_mismatch, or unknown"
            )
        values = (self.baseline_value, self.value)
        read = [None if text is None else check_value_text(setting, text) for text in values]
        # A value that can't be interpreted can't be written, so an unknown one is missing.
        if (None in values) != (self.classification == "unknown"):
            raise ValueError("a setting is unknown exactly when one of its values is missing")
        if self.classification != "unknown":
            same = read[0] == read[1]
            if same != (self.classification == "same"):
                raise ValueError("a setting is same exactly when its two values are the same")
        if self.declared_reason is not None and not setting.declarable:
            raise ValueError(f"{self.name} isn't a setting a review can declare")
        if (self.classification == "intended_change") and self.declared_reason is None:
            raise ValueError("an intended change gives its declared_reason")
        if self.classification == "unexplained_mismatch" and self.declared_reason is not None:
            raise ValueError("a declared change isn't unexplained")
        self._check_setting_flags(setting, read)

    def _check_setting_flags(self, setting: ScreenSetting, read: list[object]) -> None:
        flags = set[str](self.flags)
        critical = bool(self.critical)
        expected = {
            "critical_unexplained_mismatch": critical
            and self.classification == "unexplained_mismatch",
            "critical_unknown": critical and self.classification == "unknown",
            "intended_change_not_observed": self.classification == "same"
            and self.declared_reason is not None,
        }
        for flag, applies in expected.items():
            if (flag in flags) != applies:
                raise ValueError(f"{flag} must be given exactly when it applies")
        # The rest come from the two runs' rows, as check_flags allows them.
        external = setting.kind == "ranking" and any(
            isinstance(read_ranking(value), NameRanking | IdRanking)
            for value in read
            if value is not None
        )
        required = set[str](setting.flags) | ({"not_snapshotted"} if external else set[str]())
        optional = {"coverage_mismatch"} if setting.kind == "date" else set[str]()
        if not required <= flags - _COMPARISON_FLAGS <= required | optional:
            raise ValueError(f"{self.name}'s flags must be those its runs' rows carry")

    def _check_metric(self) -> None:
        if self.subject is None:
            raise ValueError("a metric row gives its subject")
        if (self.category, self.critical, self.declared_reason) != (None,) * 3:
            raise ValueError("category, critical, and declared_reason are given only for settings")
        unit = self.unit
        if unit is None or not _METRIC_UNIT.fullmatch(unit):
            raise ValueError("a metric row gives a metric's unit")
        if not set[str](self.flags) <= {"identical_source"}:
            raise ValueError("a metric row's only flag is identical_source")
        for text in (self.baseline_value, self.value):
            if text is not None:
                _check_metric_value(text, unit)
        given = (self.difference, self.difference_unit, self.difference_decimals)
        if self.classification != "differenced" and given != (None,) * 3:
            raise ValueError("only a differenced row has a difference, its unit, and its decimals")
        match self.classification:
            case "differenced":
                self._check_difference(unit)
            case "not_comparable":
                if None in (self.baseline_value, self.value):
                    raise ValueError("a row that isn't comparable shows both values")
                if self.reason in (None, "input_unavailable"):
                    raise ValueError("a row that isn't comparable gives why")
            case "unavailable":
                if None not in (self.baseline_value, self.value):
                    raise ValueError("a row is unavailable only when a value is")
                if self.reason != "input_unavailable":
                    raise ValueError("an unavailable row's reason is input_unavailable")
            case _:
                raise ValueError("a metric row is differenced, not_comparable, or unavailable")

    def _check_difference(self, unit: str) -> None:
        baseline, value, difference = self.baseline_value, self.value, self.difference
        if baseline is None or value is None or difference is None:
            raise ValueError("a differenced row has both values and their difference")
        if self.reason is not None:
            raise ValueError("a differenced row has no reason")
        expected_unit = {"percent": "pp", "date": "days"}.get(unit, unit)
        if self.difference_unit != expected_unit:
            raise ValueError("difference_unit is pp for percent, days for dates, else the unit")
        decimals = 0 if unit in ("date", "count") else min(_decimals(baseline), _decimals(value))
        if self.difference_decimals != decimals:
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
