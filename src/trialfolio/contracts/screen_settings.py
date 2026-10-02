"""The screen settings: the rows `settings.csv` and a plan's case hold for a screen run, in order
(docs/contracts.md, screen settings).
"""

import json
import re
from dataclasses import dataclass
from typing import Final, Literal, cast

from trialfolio.contracts.common import SettingCategory, SettingUnit

SettingKind = Literal["text", "integer", "decimal", "date", "text_list", "ranking", "token"]
"""How a setting's value is written: as text, an integer, a normalized decimal, a date, a list of
text, a ranking mapping, or a token such as `not_sent`."""


@dataclass(frozen=True)
class ScreenSetting:
    """One row of the screen settings table."""

    name: str
    category: SettingCategory
    declarable: bool
    unit: SettingUnit | None
    kind: SettingKind


SCREEN_SETTINGS: Final = (
    ScreenSetting("universe", "universe", True, None, "text"),
    ScreenSetting("screen_type", "universe", False, None, "text"),
    ScreenSetting("rules", "strategy", True, None, "text_list"),
    ScreenSetting("ranking", "strategy", True, None, "ranking"),
    ScreenSetting("max_holdings", "strategy", True, "count", "integer"),
    ScreenSetting("position_method", "strategy", False, None, "text"),
    ScreenSetting("benchmark", "benchmark", True, None, "text"),
    ScreenSetting("currency", "currency", False, None, "text"),
    ScreenSetting("start_date", "dates", True, None, "date"),
    ScreenSetting("end_date", "dates", True, None, "date"),
    ScreenSetting("rebalance_weeks", "execution", True, "weeks", "integer"),
    ScreenSetting("transaction_price", "execution", True, None, "text"),
    ScreenSetting("slippage_percent", "costs", True, "percent", "decimal"),
    ScreenSetting("commission", "costs", False, None, "token"),
    ScreenSetting("pit_method", "data_source", True, None, "text"),
    ScreenSetting("data_vendor", "data_source", False, None, "text"),
    ScreenSetting("precision", "other", True, None, "integer"),
    ScreenSetting("risk_stats_period", "other", False, None, "text"),
    ScreenSetting("max_pos_pct", "strategy", False, None, "token"),
    ScreenSetting("rank_tolerance", "strategy", False, None, "token"),
    ScreenSetting("carry_cost", "costs", False, None, "token"),
    ScreenSetting("long_weight", "strategy", False, None, "token"),
    ScreenSetting("short_weight", "strategy", False, None, "token"),
)
"""The 23 screen settings, in `settings.csv`'s order."""

SCREEN_SETTINGS_BY_NAME: Final = {setting.name: setting for setting in SCREEN_SETTINGS}

DECLARABLE_SETTINGS: Final = tuple(
    setting.name for setting in SCREEN_SETTINGS if setting.declarable
)
"""The settings a review configuration's `intended_changes` may name (0.2.0)."""

TOKENS: Final = ("not_sent", "not_modeled")
"""The values a setting takes when the request gives it none."""

_INTEGER = re.compile(r"0|[1-9][0-9]*")
_DECIMAL = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_RANKING_KEYS: Final = (
    frozenset({"formula", "lower_is_better"}),
    frozenset({"name"}),
    frozenset({"id"}),
)


def check_value_text(setting: ScreenSetting, text: str) -> None:
    """Raises `ValueError` when `text` isn't how `settings.csv` writes this setting's value."""
    match setting.kind:
        case "integer" if not _INTEGER.fullmatch(text):
            raise ValueError(f"{setting.name}'s value must be an integer")
        case "decimal" if not _DECIMAL.fullmatch(text):
            raise ValueError(f"{setting.name}'s value must be a normalized decimal")
        case "date" if not _DATE.fullmatch(text):
            raise ValueError(f"{setting.name}'s value must be a date written YYYY-MM-DD")
        case "token" if text not in TOKENS:
            raise ValueError(f"{setting.name}'s value must be one of {', '.join(TOKENS)}")
        case "text_list":
            check_text_list(setting, _json(setting, text))
        case "ranking":
            check_ranking(setting, _json(setting, text))
        case _:
            pass


def check_text_list(setting: ScreenSetting, value: object) -> None:
    """Raises `ValueError` unless `value` is a non-empty list of non-empty text."""
    items = cast("list[object]", value) if isinstance(value, list | tuple) else None
    if not items or not all(isinstance(item, str) and item for item in items):
        raise ValueError(f"{setting.name}'s value must be a non-empty list of non-empty text")


def check_ranking(setting: ScreenSetting, value: object) -> None:
    """Raises `ValueError` unless `value` is a mapping with one ranking form's keys."""
    if not isinstance(value, dict):
        raise ValueError(f"{setting.name}'s value must be a mapping with one ranking form's keys")
    keys = frozenset(cast("dict[object, object]", value))
    if keys not in _RANKING_KEYS:
        raise ValueError(f"{setting.name}'s value must be a mapping with one ranking form's keys")


def _json(setting: ScreenSetting, text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        raise ValueError(f"{setting.name}'s value must be JSON") from None
