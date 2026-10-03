"""The screen settings: the rows `settings.csv` and a plan's case hold for a screen run, in order
(docs/contracts.md, screen settings).

A value is checked with the same Pydantic types the configuration uses, so the configuration, the
plan, and `settings.csv` agree on what's valid.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Final, Literal, cast

from pydantic import ConfigDict, Field, TypeAdapter, ValidationError

from trialfolio.contracts.common import (
    CRITICAL_CATEGORIES,
    INTEGER_PATTERN,
    MAX_SAFE_INTEGER,
    DateText,
    FlagCode,
    Interpretation,
    NonEmptyText,
    Provenance,
    SettingCategory,
    SettingUnit,
)
from trialfolio.contracts.screen_configuration import (
    IdRanking,
    NameRanking,
    normalize_decimal,
    read_ranking,
)

SettingKind = Literal["text", "integer", "decimal", "date", "text_list", "ranking"]
"""How a setting's value is written: as text, an integer, a normalized decimal, a date, a list of
text, or a ranking mapping."""


@dataclass(frozen=True)
class ScreenSetting:
    """One row of the screen settings table."""

    name: str
    category: SettingCategory
    declarable: bool
    unit: SettingUnit | None
    kind: SettingKind
    allowed: tuple[str | int, ...] = ()
    """The only values the row takes in this release; empty when any value of its kind does."""
    interpretation: Interpretation = "interpreted"
    provenance: Provenance = "verified"
    """The provenance the value will have once the request is sent, which a plan records."""
    flags: tuple[FlagCode, ...] = ()
    """The flags the row always carries. A ranking by name or ID adds `not_snapshotted`, and a
    date in `settings.csv` may add `coverage_mismatch`."""
    inference_rule: str | None = None
    """For an inferred value, the rule and its source, with the date the documentation was
    checked. A plan and `settings.csv` both write it, so changing it changes the plan hash."""


def _not_sent(name: str, category: SettingCategory) -> ScreenSetting:
    """A provider parameter that isn't sent, and whose default isn't documented (rows 19-23)."""
    return ScreenSetting(
        name, category, False, None, "text", ("not_sent",), "not_interpreted", "unknown"
    )


def _inferred_default(
    name: str, category: SettingCategory, value: str, inference_rule: str
) -> ScreenSetting:
    """A value inferred from a documented default or a decision, and flagged so."""
    return ScreenSetting(
        name,
        category,
        False,
        None,
        "text",
        (value,),
        "interpreted",
        "inferred",
        ("inferred_default",),
        inference_rule,
    )


SCREEN_SETTINGS: Final = (
    ScreenSetting("universe", "universe", True, None, "text", flags=("not_snapshotted",)),
    ScreenSetting("screen_type", "universe", False, None, "text", ("stock",)),
    ScreenSetting("rules", "strategy", True, None, "text_list"),
    ScreenSetting("ranking", "strategy", True, None, "ranking"),
    ScreenSetting("max_holdings", "strategy", True, "count", "integer"),
    ScreenSetting("position_method", "strategy", False, None, "text", ("long",)),
    ScreenSetting("benchmark", "benchmark", True, None, "text"),
    ScreenSetting("currency", "currency", False, None, "text", ("USD",)),
    ScreenSetting("start_date", "dates", True, None, "date"),
    ScreenSetting("end_date", "dates", True, None, "date"),
    ScreenSetting("rebalance_weeks", "execution", True, "weeks", "integer", (1, 4)),
    ScreenSetting("transaction_price", "execution", True, None, "text", ("open",)),
    ScreenSetting("slippage_percent", "costs", True, "percent", "decimal"),
    ScreenSetting(
        "commission",
        "costs",
        False,
        None,
        "text",
        ("not_modeled",),
        provenance="inferred",
        inference_rule="Portfolio123's API: Screen page documents no commission parameter, and "
        "slippage is its only trading-cost input (checked 2026-10-01).",
    ),
    ScreenSetting("pit_method", "data_source", True, None, "text", ("complete",)),
    _inferred_default(
        "data_vendor",
        "data_source",
        "FactSet",
        "D-16: FactSet is the only supported data vendor. The endpoint documents no vendor "
        "parameter, so none is sent, and the response doesn't report the vendor.",
    ),
    ScreenSetting("precision", "other", True, None, "integer", (4,)),
    _inferred_default(
        "risk_stats_period",
        "other",
        "monthly",
        "Portfolio123's documented default: the API: Screen page lists riskStatsPeriod's values "
        "as ['Monthly'] | 'Weekly' | 'Daily' (checked 2026-10-01), and the wrapper's "
        "documentation says an optional parameter defaults to the first value.",
    ),
    _not_sent("max_pos_pct", "strategy"),
    _not_sent("rank_tolerance", "strategy"),
    _not_sent("carry_cost", "costs"),
    _not_sent("long_weight", "strategy"),
    _not_sent("short_weight", "strategy"),
)
"""The 23 screen settings, in `settings.csv`'s order."""

SCREEN_SETTINGS_BY_NAME: Final = {setting.name: setting for setting in SCREEN_SETTINGS}

DECLARABLE_SETTINGS: Final = tuple(
    setting.name for setting in SCREEN_SETTINGS if setting.declarable
)
"""The settings a review configuration's `intended_changes` may name (0.2.0)."""

_STRICT = ConfigDict(strict=True)
_TEXT: TypeAdapter[str] = TypeAdapter(NonEmptyText, config=_STRICT)
_INTEGER: TypeAdapter[int] = TypeAdapter(
    Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)], config=_STRICT
)
_DATE: TypeAdapter[str] = TypeAdapter(DateText, config=_STRICT)
_TEXT_LIST: TypeAdapter[tuple[str, ...]] = TypeAdapter(
    Annotated[tuple[NonEmptyText, ...], Field(min_length=1)], config=_STRICT
)
_NORMALIZED_DECIMAL = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")
_INTEGER_TEXT = re.compile(INTEGER_PATTERN)

_EXPECTED: Final[dict[SettingKind, str]] = {
    "text": "non-blank text",
    "integer": f"an integer from 1 to {MAX_SAFE_INTEGER}",
    "decimal": "a normalized decimal within the configuration's limits",
    "date": "a calendar date written YYYY-MM-DD",
    "text_list": "a non-empty list of non-blank text",
    "ranking": "one ranking form, with valid fields",
}


def check_row(
    name: str,
    category: str,
    critical: bool,
    unit: str | None,
    interpretation: str,
    provenance: Provenance,
    inference_rule: str | None,
) -> ScreenSetting:
    """Returns the documented setting `name`. Raises `ValueError` when there's none; when the
    row's category, unit, interpretation, or provenance differs from the documented row; when
    `critical` doesn't follow the category; or when an inference rule is given for a value that
    isn't inferred, or missing for one that is."""
    setting = SCREEN_SETTINGS_BY_NAME.get(name)
    if setting is None:
        raise ValueError(f"{name} isn't one of the screen settings")
    if (category, unit) != (setting.category, setting.unit):
        raise ValueError(f"{name} must have its documented category and unit")
    if interpretation != setting.interpretation:
        raise ValueError(f"{name} must be {setting.interpretation}")
    if provenance != setting.provenance:
        raise ValueError(f"{name} must have {setting.provenance} provenance")
    if critical != (setting.category in CRITICAL_CATEGORIES):
        raise ValueError("critical must be true exactly for the critical categories")
    if (inference_rule is None) == (provenance == "inferred"):
        raise ValueError("inference_rule must be given exactly for inferred values")
    return setting


def check_value(setting: ScreenSetting, value: object) -> None:
    """Raises `ValueError` unless `value` is a valid value of the setting in its JSON type, as a
    plan holds it, and one of its `allowed` values when it has any."""
    try:
        match setting.kind:
            case "text":
                _TEXT.validate_python(value)
            case "integer":
                _INTEGER.validate_python(value)
            case "date":
                _DATE.validate_python(value)
            case "text_list":
                items = tuple(cast("list[object]", value)) if isinstance(value, list) else value
                _TEXT_LIST.validate_python(items)
            case "ranking":
                read_ranking(value)
            case "decimal":
                if not isinstance(value, str) or not _NORMALIZED_DECIMAL.fullmatch(value):
                    raise ValueError
                normalize_decimal(Decimal(value))
    except (ValidationError, ValueError):
        raise ValueError(f"{setting.name}'s value must be {_EXPECTED[setting.kind]}") from None
    if setting.allowed and value not in setting.allowed:
        allowed = ", ".join(str(item) for item in setting.allowed)
        raise ValueError(f"{setting.name}'s value must be one of: {allowed}")


def check_value_text(setting: ScreenSetting, text: str) -> object:
    """Raises `ValueError` unless `text` is how `settings.csv` writes a valid value of the
    setting: an integer in decimal digits, a list or a ranking as JSON, and anything else as is.
    Returns the value it read."""
    value: object = text
    if setting.kind == "integer":
        if not _INTEGER_TEXT.fullmatch(text) or len(text) > len(str(MAX_SAFE_INTEGER)):
            raise ValueError(f"{setting.name}'s value must be {_EXPECTED['integer']}")
        value = int(text)
    elif setting.kind in ("text_list", "ranking"):
        try:
            value = json.loads(text)
        except (ValueError, RecursionError):
            raise ValueError(f"{setting.name}'s value must be JSON") from None
    check_value(setting, value)
    return value


def check_flags(
    setting: ScreenSetting, value: object, flags: tuple[str, ...], *, executed: bool
) -> None:
    """Raises `ValueError` unless `flags` are the row's documented flags: its own, and
    `not_snapshotted` for a ranking by name or ID. With `executed`, as in `settings.csv`, a date
    may also carry `coverage_mismatch`. `value` must already be valid."""
    expected = set[str](setting.flags)
    if setting.kind == "ranking" and isinstance(read_ranking(value), NameRanking | IdRanking):
        expected.add("not_snapshotted")
    optional = {"coverage_mismatch"} if executed and setting.kind == "date" else set[str]()
    if not expected <= set(flags) <= expected | optional:
        documented = ", ".join(sorted(expected)) or "none"
        raise ValueError(f"{setting.name}'s flags must be its documented ones: {documented}")
