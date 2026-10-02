"""Rows of the normalized tables `metrics.csv` and `settings.csv`, schema version 1.0.0
(docs/contracts.md, normalized tables).

Each model is one row, after a CSV adapter step has read its cells: an empty cell is `None`,
`critical` is a boolean, `source_decimals` an integer, the period dates are dates, and `flags`
is a tuple of codes, which the CSV joins with semicolons. A field's position is its column's.
"""

import re
from datetime import date
from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from trialfolio.contracts.common import (
    CRITICAL_CATEGORIES,
    ContractModel,
    FlagCode,
    Interpretation,
    MetricUnit,
    NonEmptyText,
    Provenance,
    ResultLabel,
    SettingCategory,
    SettingName,
    SettingUnit,
    Sha256Digest,
    UnavailableReason,
    require_unique,
)
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS_BY_NAME, check_value_text

TABLES_SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of both tables. The manifest records it, because a CSV can't."""

_DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.(?P<fraction>[0-9]+))?")
_COUNT = re.compile(r"0|[1-9][0-9]*")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


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
        if self.origin == "calculated" and self.source_location is not None:
            raise ValueError("source_location must be null for a calculated value")
        return self

    def _check_value(self, value: str) -> None:
        if self.unit in ("date", "count"):
            if self.source_decimals is not None:
                raise ValueError("source_decimals must be null for dates and counts")
            if self.unit == "date":
                if not _DATE.fullmatch(value):
                    raise ValueError("a date must be written YYYY-MM-DD")
                date.fromisoformat(value)
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
    original_value: str | None
    """The value exactly as written in the configuration; null when absent."""
    source_artifact: Sha256Digest
    flags: tuple[FlagCode, ...]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        setting = SCREEN_SETTINGS_BY_NAME.get(self.setting)
        if setting is None:
            raise ValueError("setting must be one of the screen settings")
        if (self.category, self.unit) != (setting.category, setting.unit):
            raise ValueError(f"{self.setting} must have its documented category and unit")
        if self.critical != (self.category in CRITICAL_CATEGORIES):
            raise ValueError("critical must be true exactly for the critical categories")
        check_value_text(setting, self.value)
        if (self.inference_rule is None) == (self.provenance == "inferred"):
            raise ValueError("inference_rule must be given exactly for inferred values")
        if (self.original_key is None) != (self.original_value is None):
            raise ValueError("original_key and original_value must be given together")
        require_unique(self.flags, "flags")
        return self


METRICS_COLUMNS: Final = tuple(MetricsRow.model_fields)
"""`metrics.csv`'s columns, in order."""

SETTINGS_COLUMNS: Final = tuple(SettingsRow.model_fields)
"""`settings.csv`'s columns, in order."""
