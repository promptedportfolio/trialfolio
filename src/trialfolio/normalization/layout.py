"""The response layout's adapter: a saved screen backtest response read as
`p123api-screen-backtest` version 1 (docs/contracts.md, normalized tables, and
`p123api-screen-backtest` version 1).

`read_response` reads a saved `response.json`, checks the required structure, and reads each
metric and the coverage from the saved text: numbers as decimals, never as binary floats, with
exactly the digits the file holds. `METRICS` gives the layout's metrics, in `metrics.csv`'s order,
and `holds_series` says whether a decoded response holds the per-period series that 0.1.0
preserves without interpreting, for the manifest's `return_series`.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final, Literal, cast

from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.common import DATE_PATTERN, UnavailableReason
from trialfolio.errors import TrialFolioError

LAYOUT: Final = "p123api-screen-backtest"
LAYOUT_VERSION: Final = 1
PARSER_VERSION: Final = 1
"""The version of this adapter, which the manifest records with the layout's (versioning)."""

type Subject = Literal["strategy", "benchmark"]
type Kind = Literal["decimal", "count", "date"]


@dataclass(frozen=True)
class Metric:
    """One row of the layout's metrics table."""

    metric_id: str
    subject: Subject
    unit: str
    path: tuple[str, ...] | None
    """The value's JSON path in the response; None for a value Trial Folio calculates."""
    benchmark_relative: bool = False
    """Whether the row compares the strategy with the benchmark, and so names it."""

    @property
    def kind(self) -> Kind:
        return "date" if self.unit == "date" else "count" if self.unit == "count" else "decimal"


_PER_SUBJECT: Final = (
    ("total_return", "total_return", "percent"),
    ("annualized_return", "annualized_return", "percent"),
    ("max_drawdown", "max_drawdown", "percent"),
    ("standard_deviation", "standard_dev", "percent"),
    ("sharpe_ratio", "sharpe_ratio", "ratio"),
    ("sortino_ratio", "sortino_ratio", "ratio"),
)
"""Rows 4-9, and 15-20 for the benchmark: each metric's identifier, key, and unit."""

METRICS: Final = (
    Metric("coverage_start", "strategy", "date", None),
    Metric("coverage_end", "strategy", "date", None),
    Metric("coverage_periods", "strategy", "count", None),
    *(Metric(name, "strategy", unit, ("stats", "port", key)) for name, key, unit in _PER_SUBJECT),
    Metric("correlation", "strategy", "ratio", ("stats", "correlation"), True),
    Metric("r_squared", "strategy", "ratio", ("stats", "r_squared"), True),
    Metric("beta", "strategy", "ratio", ("stats", "beta"), True),
    Metric("alpha", "strategy", "percent", ("stats", "alpha"), True),
    Metric("risk_samples", "strategy", "count", ("stats", "samples")),
    *(Metric(name, "benchmark", unit, ("stats", "bench", key)) for name, key, unit in _PER_SUBJECT),
)
"""`metrics.csv`'s 20 rows, in order."""

TRANSACTION_DATE: Final = "Tran Dt"
END_DATE: Final = "End Dt"


@dataclass(frozen=True)
class Value:
    """A value read from the response, or why it's unavailable."""

    text: str | None
    """A decimal in plain notation with exactly its source's digits, a count's digits, or a
    `YYYY-MM-DD` date. None when unavailable."""
    reason: UnavailableReason | None = None
    """Why it's unavailable; None when it's available."""

    @property
    def available(self) -> bool:
        return self.text is not None


@dataclass(frozen=True)
class Coverage:
    """The dates and number of periods the response covers (coverage)."""

    start: Value
    """The earliest `Tran Dt` in `results.rows`."""
    end: Value
    """The latest `End Dt` in `results.rows`."""
    periods: int
    """The number of rows, including zero."""


@dataclass(frozen=True)
class ScreenBacktestResult:
    """A response read as `p123api-screen-backtest` version 1."""

    coverage: Coverage
    values: Mapping[tuple[str, ...], Value]
    """Each reported metric's value, by JSON path."""


class _Number(str):
    """A JSON number's text, exactly as the saved file writes it."""

    __slots__ = ()


class _NotFinite:
    """`NaN`, `Infinity`, or `-Infinity`, which `json` writes but which aren't JSON numbers."""


_NOT_FINITE: Final = _NotFinite()
_DATE: Final = re.compile(DATE_PATTERN)


def _invalid(path: str, problem: str) -> TrialFolioError:
    return TrialFolioError(
        "provider.response_invalid",
        f"Portfolio123's response was saved, as {path}, but Trial Folio can't read it as "
        f"{LAYOUT} version {LAYOUT_VERSION}: {problem} So the normalized result is unavailable. "
        "The saved response is kept as it came; report the problem if it persists.",
    )


def read_response(content: bytes, path: str) -> ScreenBacktestResult:
    """Reads a saved `response.json`, named by its `path` in messages, as `p123api-screen-backtest`
    version 1.

    Raises `TrialFolioError` with `provider.response_invalid` when the file doesn't have the
    layout's required structure. A metric or coverage date that's missing or can't be read is
    unavailable, with its reason, and doesn't make the response invalid.
    """
    try:
        loaded: object = json.loads(
            content.decode("utf-8"),
            parse_float=_Number,
            parse_int=_Number,
            parse_constant=lambda _: _NOT_FINITE,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _invalid(path, "it isn't JSON.") from None
    top = _object(loaded, "The top level", path)
    stats = _object(top.get("stats"), "`stats`", path)
    results = _object(top.get("results"), "`results`", path)
    for subject in ("port", "bench"):
        _object(stats.get(subject), f"`stats.{subject}`", path)
    columns = results.get("columns")
    # A number's text is a `str` too, so the type is checked exactly.
    if not isinstance(columns, list) or not all(
        type(column) is str for column in cast("list[object]", columns)
    ):
        raise _invalid(path, "`results.columns` isn't an array of strings.")
    rows = results.get("rows")
    if not isinstance(rows, list):
        raise _invalid(path, "`results.rows` isn't an array.")
    width = len(cast("list[str]", columns))
    for row in cast("list[object]", rows):
        if not isinstance(row, list) or len(cast("list[object]", row)) != width:
            raise _invalid(path, "a row of `results.rows` isn't an array as long as `columns`.")
    values = {metric.path: _reported(top, metric) for metric in METRICS if metric.path is not None}
    coverage = _coverage(cast("list[str]", columns), cast("list[list[object]]", rows))
    return ScreenBacktestResult(coverage=coverage, values=values)


def holds_series(payload: object) -> bool:
    """Whether a decoded response holds per-period series, which 0.1.0 preserves without
    interpreting (the manifest's `return_series`): a `results.rows` array with a row, or a
    `chart` object holding an array with an entry. A response without either, such as `{}`,
    holds none, whether or not it has the required structure."""
    if not isinstance(payload, dict):
        return False
    top = cast("dict[str, object]", payload)
    results = top.get("results")
    if isinstance(results, dict):
        rows = cast("dict[str, object]", results).get("rows")
        if _non_empty_array(rows):
            return True
    chart = top.get("chart")
    if not isinstance(chart, dict):
        return False
    return any(_non_empty_array(series) for series in cast("dict[str, object]", chart).values())


def _non_empty_array(value: object) -> bool:
    return isinstance(value, list) and len(cast("list[object]", value)) > 0


def _object(value: object, name: str, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _invalid(path, f"{name} isn't an object.")
    return cast("dict[str, object]", value)


def _reported(top: Mapping[str, object], metric: Metric) -> Value:
    value: object = top
    for key in cast("tuple[str, ...]", metric.path):
        value = cast("dict[str, object]", value).get(key)
        if value is None:
            # Missing, or null: the response has the field but no value.
            return Value(None, "blank_in_source")
    if type(value) is not _Number:
        return Value(None, "unparseable_in_source")
    number = Decimal(value)
    if metric.kind == "count":
        return _count(number)
    return Value(format(number, "f"))


def _count(number: Decimal) -> Value:
    """A count is a whole number, 0 or more. One written with a decimal point, such as `118.0`, is
    written with its digits alone."""
    if number < 0 or number != number.to_integral_value():
        return Value(None, "unparseable_in_source")
    return Value(format(number.copy_abs().to_integral_value(), "f"))


def _coverage(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> Coverage:
    periods = len(rows)
    if not rows or TRANSACTION_DATE not in columns or END_DATE not in columns:
        blank = Value(None, "blank_in_source")
        return Coverage(blank, blank, periods)
    starts = _dates(rows, columns.index(TRANSACTION_DATE))
    ends = _dates(rows, columns.index(END_DATE))
    start = Value(min(starts).isoformat()) if starts else Value(None, "unparseable_in_source")
    end = Value(max(ends).isoformat()) if ends else Value(None, "unparseable_in_source")
    if starts and ends and min(starts) > max(ends):
        # The dates contradict each other, so neither can be the coverage.
        contradicted = Value(None, "unparseable_in_source")
        return Coverage(contradicted, contradicted, periods)
    return Coverage(start, end, periods)


def _dates(rows: Sequence[Sequence[object]], column: int) -> list[date]:
    """Every row's date in the column; empty when any of them isn't a `YYYY-MM-DD` date, so the
    earliest or latest can't be known."""
    dates: list[date] = []
    for row in rows:
        value = row[column]
        if type(value) is not str or not _DATE.fullmatch(value):
            return []
        try:
            dates.append(date.fromisoformat(value))
        except ValueError:
            return []
    return dates


def check_decoded(response: SavedResponse) -> None:
    """Raises `TrialFolioError` with `provider.response_invalid` when the response was saved
    undecoded, as it came, so it can't be read as the layout."""
    if response.form == "undecoded":
        raise TrialFolioError(
            "provider.response_invalid",
            f"Portfolio123's response couldn't be decoded as JSON, so it was saved as it came, as "
            f"{response.path}, and the normalized result is unavailable. Report the problem if "
            "it persists.",
        )
