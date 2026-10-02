"""The screen settings: the rows `settings.csv` and a plan's case hold for a screen run, in order
(docs/contracts.md, screen settings).
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Literal, cast

from pydantic import ValidationError

from trialfolio.contracts.common import (
    MAX_SAFE_INTEGER,
    Interpretation,
    SettingCategory,
    SettingUnit,
    valid_date_text,
)
from trialfolio.contracts.screen_configuration import normalize_decimal, read_ranking

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


SCREEN_SETTINGS: Final = (
    ScreenSetting("universe", "universe", True, None, "text"),
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
    ScreenSetting("commission", "costs", False, None, "text", ("not_modeled",)),
    ScreenSetting("pit_method", "data_source", True, None, "text", ("complete",)),
    ScreenSetting("data_vendor", "data_source", False, None, "text", ("FactSet",)),
    ScreenSetting("precision", "other", True, None, "integer", (4,)),
    ScreenSetting("risk_stats_period", "other", False, None, "text", ("monthly",)),
    ScreenSetting("max_pos_pct", "strategy", False, None, "text", ("not_sent",), "not_interpreted"),
    ScreenSetting(
        "rank_tolerance", "strategy", False, None, "text", ("not_sent",), "not_interpreted"
    ),
    ScreenSetting("carry_cost", "costs", False, None, "text", ("not_sent",), "not_interpreted"),
    ScreenSetting("long_weight", "strategy", False, None, "text", ("not_sent",), "not_interpreted"),
    ScreenSetting(
        "short_weight", "strategy", False, None, "text", ("not_sent",), "not_interpreted"
    ),
)
"""The 23 screen settings, in `settings.csv`'s order."""

SCREEN_SETTINGS_BY_NAME: Final = {setting.name: setting for setting in SCREEN_SETTINGS}

DECLARABLE_SETTINGS: Final = tuple(
    setting.name for setting in SCREEN_SETTINGS if setting.declarable
)
"""The settings a review configuration's `intended_changes` may name (0.2.0)."""

_INTEGER = re.compile(r"0|[1-9][0-9]*")
_DECIMAL = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_NOT_BLANK = re.compile(r"\S")


def check_row(name: str, category: str, unit: str | None, interpretation: str) -> ScreenSetting:
    """Returns the documented setting `name`, or raises `ValueError` when there's none, or when
    its category, unit, or interpretation differs from the documented row."""
    setting = SCREEN_SETTINGS_BY_NAME.get(name)
    if setting is None:
        raise ValueError(f"{name} isn't one of the screen settings")
    if (category, unit) != (setting.category, setting.unit):
        raise ValueError(f"{name} must have its documented category and unit")
    if interpretation != setting.interpretation:
        raise ValueError(f"{name} must be {setting.interpretation}")
    return setting


def check_value(setting: ScreenSetting, value: object) -> None:
    """Raises `ValueError` unless `value` is a valid value of the setting in its JSON type, as a
    plan holds it: an integer from 1 to 2^53 - 1, a normalized decimal or a date as text, a
    non-empty list of non-blank text, a ranking mapping, or non-blank text. A value must also be
    one of the setting's `allowed` values, when it has any."""
    name = setting.name
    match setting.kind:
        case "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name}'s value must be an integer")
            if not 1 <= value <= MAX_SAFE_INTEGER:
                raise ValueError(f"{name}'s value must be from 1 to {MAX_SAFE_INTEGER}")
        case "decimal":
            if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
                raise ValueError(f"{name}'s value must be a normalized decimal")
            try:
                normalize_decimal(Decimal(value))
            except ValueError as error:
                raise ValueError(f"{name}'s value {error}") from None
        case "date":
            if not isinstance(value, str) or not _DATE.fullmatch(value):
                raise ValueError(f"{name}'s value must be a date written YYYY-MM-DD")
            try:
                valid_date_text(value)
            except ValueError:
                raise ValueError(f"{name}'s value isn't a calendar date") from None
        case "text_list":
            items = cast("list[object]", value) if isinstance(value, list | tuple) else []
            if not items or not all(isinstance(i, str) and _NOT_BLANK.search(i) for i in items):
                raise ValueError(f"{name}'s value must be a non-empty list of non-blank text")
        case "ranking":
            try:
                read_ranking(value)
            except ValidationError:
                raise ValueError(
                    f"{name}'s value must be one ranking form, with valid fields"
                ) from None
        case "text":
            if not isinstance(value, str) or not _NOT_BLANK.search(value):
                raise ValueError(f"{name}'s value must be non-blank text")
    if setting.allowed and value not in setting.allowed:
        allowed = ", ".join(str(item) for item in setting.allowed)
        raise ValueError(f"{name}'s value must be one of: {allowed}")


def check_value_text(setting: ScreenSetting, text: str) -> None:
    """Raises `ValueError` unless `text` is how `settings.csv` writes a valid value of the
    setting: an integer in decimal digits, a list or a ranking as JSON, and anything else as is.
    """
    value: object = text
    if setting.kind == "integer":
        if not _INTEGER.fullmatch(text) or len(text) > len(str(MAX_SAFE_INTEGER)):
            raise ValueError(f"{setting.name}'s value must be an integer")
        value = int(text)
    elif setting.kind in ("text_list", "ranking"):
        try:
            value = json.loads(text)
        except ValueError:
            raise ValueError(f"{setting.name}'s value must be JSON") from None
    check_value(setting, value)
