"""An offline check of the dated series in saved screen-backtest responses (release 0.5.0, R05-T01).

Release 0.5.0 analyzes each case's daily levels of 100 invested, from a response's `chart`, and
each rebalance period's returns, from its `results.rows`. This script checks, in every saved
screen-backtest response it finds, what those analyses rely on, against the verified layout,
`p123api-screen-backtest` version 1 (docs/contracts.md):

- `chart`'s five arrays are parallel, with one entry per weekday from the start date to the end
  date, and both levels start at 100;
- how a market closure appears: which entries repeat the level before them, for the strategy and
  the benchmark, compared with the calendar below, and a start or an end on a closure;
- each period's `Ret%` and `Bench%` reproduce from the `chart` levels at its `Tran Dt` and
  `End Dt`, its `Excess%` from those two, and its two `100 USD` columns are the levels at its
  `End Dt`;
- whether `total_return`, `annualized_return`, `max_drawdown`, and `standard_dev`, for the strategy
  and the benchmark, reproduce from the levels, as the layout records they do for the reference
  response, and `total_return` from the period returns, compounded;
- the rolling windows of 7, 30, 90, 180, and 365 calendar days, by the release outline's proposed
  rule: a window ends at each `chart` date, and starts at the latest `chart` date at least that many
  days earlier. It counts them, and the windows longer than their length by more than 2 days, in
  every `chart` it reads, so that a gap shows, though a `chart` of every weekday can't have one.

It reads the responses under each `payloads/` and `exports/` folder of the reference directory
given, which hold the owner's runs, experiments, live checks, and walk-throughs, and, with
`--fixtures`, the committed synthetic responses under `tests/fixtures/`, the demo's packaged
`response.json`, and the ones beside this script, under `synthetic/`, which plant a failure for
each check (`synthetic/generate.py`). A response saved by a script, outside any attempt, is read
with the request beside it, `request-<x>.json` for `response-<x>.json`, or the `request.json` above
`payloads/`; or with the request `--request` names for its folder. It reads numbers as decimals,
never as binary floats, as Trial Folio does. It sends nothing, and writes nothing.

What it prints is dates, versions, counts, settings' kinds, and outcomes, and where it found each
response: its reference folder, its path below `payloads/`, and, for a run's or an experiment's,
its output directory and case ID. Those names were chosen when each was saved, so check them
before quoting any. Never a level, a return, a metric, a ranking system's name or ID, or anything else of a
response's or a request's contents.

Comparisons. Every saved value is read as rounded to the request's `precision`, though its text
can have fewer decimals, since saving drops only trailing zeros (docs/contracts.md, "Numbers and
precision"); or to its own decimals, where it has more, or where no request gives the precision.
Those are its digits. A value reproduced from the series is "equal at the precision" when it's
within half a unit of the request's `precision` of the reported value, and "equal at its digits"
when it's within half a unit of the reported value's digits, which differs only without a
precision. Where it isn't, it's "within the rounding" when the reported value is in the range the
inputs' rounding allows, each level, or each period return, to half a unit of its digits, widened
by half a unit of the reported value's digits; and otherwise "within one unit of its digits", or
"differs". The range is exact for a period's return, the total and annualized returns, and the
compounded period returns; for the maximum drawdown and the standard deviation, it's a bound that
holds the exact range. `Excess%` is `Ret%` minus `Bench%` "exactly", or "within the rounding" when
it's within the sum of the three values' half units. A `100 USD` value is compared exactly, then by
how many units of the precision it's apart.

The calendar. The script's own calendar of the New York Stock Exchange's full-day closures, for
2016 to 2025 only: New Year's Day (on a Sunday, the Monday after; on a Saturday, none); Martin
Luther King Jr. Day and Washington's Birthday, the third Mondays of January and February; Good
Friday; Memorial Day, the last Monday of May; Juneteenth, from 2022; Independence Day; Labor Day,
the first Monday of September; Thanksgiving, the fourth Thursday of November; and Christmas
(Juneteenth, Independence Day, and Christmas on a Saturday are closed the Friday before, and on a
Sunday the Monday after); and the national days of mourning of 2018-12-05 and 2025-01-09. A response
whose dates fall outside those years gets no comparison with it.

    uv run python reference/return-series/check_series.py REFERENCE_DIR [--fixtures REPO_ROOT]
        [--request FOLDER=PATH ...]

PATH is relative to REFERENCE_DIR.
"""

import argparse
import bisect
import hashlib
import json
import platform
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, getcontext
from itertools import pairwise
from pathlib import Path
from typing import Any

getcontext().prec = 50

ARRAYS = ("dates", "screenReturns", "benchReturns", "turnoverPct", "positionCnt")
LEVELS = {"port": "screenReturns", "bench": "benchReturns"}
PERIOD_RETURNS = {"port": "Ret%", "bench": "Bench%"}
METRICS = ("total_return", "annualized_return", "max_drawdown", "standard_dev")
WINDOWS = (7, 30, 90, 180, 365)
CALENDAR_YEARS = range(2016, 2026)
MOURNING = {date(2018, 12, 5), date(2025, 1, 9)}
HUNDRED = Decimal(100)
NOT_A_NUMBER = "not a number"
"""What a NaN or Infinity in the saved text reads as: a value that isn't a number."""

Outcome = dict[str, Any]


# Reading


def load(path: Path) -> Any:
    """A JSON file, or None when it's missing or isn't JSON."""
    try:
        return json.loads(
            path.read_bytes(), parse_float=Decimal, parse_constant=lambda _: NOT_A_NUMBER
        )
    except (OSError, ValueError):
        return None


def number(value: Any) -> Decimal | None:
    """A JSON number as a decimal, or None for anything else: null, text, a boolean, or NaN."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal) and value.is_finite():
        return value
    return None


def decimals(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) and exponent < 0 else 0


def half_unit(places: int) -> Decimal:
    return Decimal(5).scaleb(-places - 1)


def digits(value: Decimal, precision: int | None) -> int:
    """The decimals a saved value was rounded to: the request's precision, since saving drops only
    trailing zeros (docs/contracts.md, "Numbers and precision"), or its own, where it has more, or
    where the precision isn't known."""
    return max(decimals(value), precision or 0)


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def has_structure(payload: Any) -> bool:
    """Layout version 1's required structure (docs/contracts.md)."""
    if not isinstance(payload, dict):
        return False
    stats, results = payload.get("stats"), payload.get("results")
    if not isinstance(stats, dict) or not isinstance(results, dict):
        return False
    if not isinstance(stats.get("port"), dict) or not isinstance(stats.get("bench"), dict):
        return False
    columns, rows = results.get("columns"), results.get("rows")
    return (
        isinstance(columns, list)
        and all(isinstance(c, str) for c in columns)
        and isinstance(rows, list)
        and all(isinstance(r, list) and len(r) == len(columns) for r in rows)
    )


# The calendar


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def observed(day: date) -> date:
    return day + timedelta(days={5: -1, 6: 1}.get(day.weekday(), 0))


def good_friday(year: int) -> date:
    """Two days before Easter Sunday, by the anonymous Gregorian algorithm."""
    golden = year % 19
    century, rest = divmod(year, 100)
    leap_c, leap_r = divmod(century, 4)
    correction = (century + 8) // 25
    moon = (19 * golden + century - leap_c - (century - correction + 1) // 3 + 15) % 30
    weeks, years_left = divmod(rest, 4)
    sunday = (32 + 2 * leap_r + 2 * weeks - moon - years_left) % 7
    shift = (golden + 11 * moon + 22 * sunday) // 451
    month, day = divmod(moon + sunday - 7 * shift + 114, 31)
    return date(year, month, day + 1) - timedelta(days=2)


def closures(year: int) -> set[date]:
    new_year = date(year, 1, 1)
    days = {new_year + timedelta(days=1)} if new_year.weekday() == 6 else set()
    if new_year.weekday() < 5:
        days.add(new_year)
    days |= {
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        good_friday(year),
        last_weekday(year, 5, 0),
        observed(date(year, 7, 4)),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 11, 3, 4),
        observed(date(year, 12, 25)),
    }
    if year >= 2022:
        days.add(observed(date(year, 6, 19)))
    return days | {d for d in MOURNING if d.year == year}


def weekdays(start: date, end: date) -> list[date]:
    count = (end - start).days + 1
    return [d for d in (start + timedelta(days=i) for i in range(count)) if d.weekday() < 5]


# Checking one response


@dataclass
class Series:
    """A response's `chart`, read: its dates, both levels, and the dates each level repeats the
    entry before it."""

    dates: list[date]
    levels: dict[str, list[Decimal]]
    index: dict[date, int]
    repeats: dict[str, set[date]]
    half: Decimal
    """Half a unit of the levels' digits: of the precision, where it's known."""


@dataclass
class Checked:
    outcome: Outcome = field(default_factory=Outcome)
    exceptions: list[str] = field(default_factory=list)


def check_response(payload: dict[str, Any], request: dict[str, Any] | None) -> Checked:
    checked = Checked()
    out = checked.outcome
    precision = request.get("precision") if request else None
    out["precision"] = precision if isinstance(precision, int) else None
    screen = request.get("screen") if request else None
    benchmark = screen.get("benchmark") if isinstance(screen, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    out["benchmark"] = benchmark if isinstance(benchmark, str) else None
    currency = screen.get("currency") if isinstance(screen, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    out["currency"] = currency if isinstance(currency, str) else None
    out["over_precision"] = count_over_precision(payload, out["precision"])
    series = read_chart(payload.get("chart"), out["precision"], checked)
    rows = period_rows(payload["results"], checked)
    check_dates(series, rows, request, checked)
    if series is not None and out.get("every_weekday") and out.get("in_calendar"):
        check_closures(series, rows or [], checked)
    if series is not None and rows is not None:
        check_periods(series, rows, out["precision"], checked)
    if series is not None and out.get("every_weekday"):
        check_metrics(series, payload["stats"], out["precision"], checked)
    if series is not None:
        check_windows(series, checked)
    if rows is not None:
        check_compounded(rows, payload["stats"], out["precision"], checked)
    return checked


def count_over_precision(payload: Any, precision: int | None) -> int | None:
    if precision is None:
        return None
    count = 0
    stack = [payload]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.values())  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        elif isinstance(item, list):
            stack.extend(item)  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(item, Decimal) and item.is_finite() and decimals(item) > precision:
            count += 1
    return count


def read_chart(chart: Any, precision: int | None, checked: Checked) -> Series | None:
    out = checked.outcome
    out["chart"] = isinstance(chart, dict)
    if not isinstance(chart, dict):
        return None
    arrays: list[Any] = [chart.get(name) for name in ARRAYS]  # pyright: ignore[reportUnknownMemberType]
    lengths = {len(a) for a in arrays if isinstance(a, list)}  # pyright: ignore[reportUnknownArgumentType]
    out["parallel"] = all(isinstance(a, list) for a in arrays) and len(lengths) == 1
    out["points"] = len(arrays[0]) if isinstance(arrays[0], list) else 0  # pyright: ignore[reportUnknownArgumentType]
    if not out["parallel"] or not out["points"]:
        return None
    dates = [parse_date(d) for d in arrays[0]]  # pyright: ignore[reportUnknownVariableType]
    levels = {s: [number(v) for v in chart[name]] for s, name in LEVELS.items()}
    read = [d for d in dates if d is not None]
    out["dates_valid"] = len(read) == len(dates) and all(a < b for a, b in pairwise(read))
    out["levels_numbers"] = all(v is not None and v > 0 for s in levels for v in levels[s])
    if not out["dates_valid"] or not out["levels_numbers"]:
        return None
    values = {s: [v for v in levels[s] if v is not None] for s in levels}
    out["start_100"] = all(values[s][0] == HUNDRED for s in values)
    for subject, series in values.items():
        text = ",".join(str(v.normalize()) for v in series)
        out[f"{subject}.series"] = hashlib.sha256(text.encode()).hexdigest()
    repeats = {
        s: {read[i] for i in range(1, len(read)) if values[s][i] == values[s][i - 1]}
        for s in values
    }
    for subject in values:
        out[f"{subject}.second_repeats"] = len(read) > 1 and read[1] in repeats[subject]
    places = (
        precision if precision is not None else max(decimals(v) for s in values for v in values[s])
    )
    return Series(read, values, {d: i for i, d in enumerate(read)}, repeats, half_unit(places))


def period_rows(results: dict[str, Any], checked: Checked) -> list[dict[str, Any]] | None:
    columns: list[str] = results["columns"]
    rows = [dict(zip(columns, row)) for row in results["rows"]]
    checked.outcome["periods"] = len(rows)
    needed = ("Tran Dt", "End Dt", "Ret%", "Bench%", "Excess%")
    if not rows or any(c not in columns for c in needed):
        return None
    for row in rows:
        row["tran"], row["end"] = parse_date(row["Tran Dt"]), parse_date(row["End Dt"])
    if any(row["tran"] is None or row["end"] is None for row in rows):
        checked.exceptions.append("a period's Tran Dt or End Dt isn't a date")
        return None
    rows.sort(key=lambda row: row["tran"])
    return rows


def check_dates(
    series: Series | None,
    rows: list[dict[str, Any]] | None,
    request: dict[str, Any] | None,
    checked: Checked,
) -> None:
    out = checked.outcome
    requested = (
        (parse_date(request.get("startDt")), parse_date(request.get("endDt")))
        if request
        else (None, None)
    )
    coverage = (rows[0]["tran"], rows[-1]["end"]) if rows else (None, None)
    out["requested"] = requested
    out["coverage_is_request"] = None if requested[0] is None else coverage == requested
    if rows:
        lengths = sorted((row["end"] - row["tran"]).days for row in rows)
        out["median_days"] = lengths[len(lengths) // 2]
        out["contiguous"] = all(a["end"] == b["tran"] for a, b in pairwise(rows))
    if series is None:
        return
    first, last = series.dates[0], series.dates[-1]
    out["first"], out["last"] = first, last
    out["weekdays_only"] = all(d.weekday() < 5 for d in series.dates)
    start, end = requested if requested[0] is not None else coverage
    out["dates_from"] = "the request" if requested[0] is not None else "the coverage"
    out["every_weekday"] = (
        start is not None and end is not None and series.dates == weekdays(start, end)
    )
    out["max_gap"] = max((b - a).days for a, b in pairwise(series.dates)) if last > first else 0
    out["in_calendar"] = {first.year, last.year} <= set(CALENDAR_YEARS)


def check_closures(series: Series, rows: list[dict[str, Any]], checked: Checked) -> None:
    """Which entries repeat the level before them, against the calendar's closures and the
    weekday after each closure, for each level."""
    out = checked.outcome
    first, last = series.dates[0], series.dates[-1]
    shut = sorted(
        d for y in range(first.year, last.year + 1) for d in closures(y) if first <= d <= last
    )
    after = {
        series.dates[series.index[d] + 1] for d in shut if series.index[d] + 1 < len(series.dates)
    }
    trans = {row["tran"] for row in rows}
    out["closures"] = len(shut)
    out["after_closures"] = len(after)
    out["starts_on_closure"] = first in shut
    out["ends_on_closure"] = last in shut
    for subject, repeats in series.repeats.items():
        out[f"{subject}.repeats"] = len(repeats)
        out[f"{subject}.repeat_on_closure"] = len(repeats & set(shut))
        out[f"{subject}.repeat_on_closure_dates"] = tuple(
            str(d) for d in sorted(repeats & set(shut))
        )
        out[f"{subject}.repeat_after"] = len(repeats & after)
        out[f"{subject}.repeat_elsewhere"] = tuple(str(d) for d in sorted(repeats - after))
        moves = sorted(after - repeats)
        out[f"{subject}.moves_after"] = len(moves)
        out[f"{subject}.moves_after_kind"] = Counter(
            "the closure before it is a Tran Dt"
            if series.dates[series.index[d] - 1] in trans
            else ("it's a Tran Dt" if d in trans else "neither is a Tran Dt")
            for d in moves
        )


def check_periods(
    series: Series, rows: list[dict[str, Any]], precision: int | None, checked: Checked
) -> None:
    out = checked.outcome
    in_chart = [row for row in rows if row["tran"] in series.index and row["end"] in series.index]
    out["periods_in_chart"] = len(in_chart)
    every = {d for y in CALENDAR_YEARS for d in closures(y)}
    out["tran_on_closure"] = sum(row["tran"] in every for row in rows)
    out["end_on_closure"] = sum(row["end"] in every for row in rows)
    for subject, column in PERIOD_RETURNS.items():
        counts: Counter[str] = Counter()
        for row in in_chart:
            reported = number(row[column])
            if reported is None:
                continue
            start = series.levels[subject][series.index[row["tran"]]]
            end = series.levels[subject][series.index[row["end"]]]
            mid = (end / start - 1) * HUNDRED
            low = ((end - series.half) / (start + series.half) - 1) * HUNDRED
            high = ((end + series.half) / (start - series.half) - 1) * HUNDRED
            counts[compare(mid, reported, precision, (low, high))] += 1
        out[f"{column}.from_levels"] = counts
    counts = Counter()
    for row in rows:
        values = [number(row[c]) for c in ("Ret%", "Bench%", "Excess%")]
        if any(v is None for v in values):
            counts["not numbers"] += 1
            continue
        ret, bench, excess = (v for v in values if v is not None)
        allowed = sum(half_unit(digits(v, precision)) for v in (ret, bench, excess))
        counts[
            "exactly"
            if ret - bench == excess
            else ("within the rounding" if abs(ret - bench - excess) <= allowed else "differs")
        ] += 1
    out["excess"] = counts
    usd = [c for c in rows[0] if isinstance(c, str) and c.startswith("100 ")]
    out["usd_columns"] = len(usd)
    if len(usd) == 2:
        for subject, column in zip(LEVELS, usd):
            out[f"usd.{subject}"] = usd_counts(series, in_chart, subject, column, every)


def usd_counts(
    series: Series, rows: list[dict[str, Any]], subject: str, column: str, shut: set[date]
) -> Counter[str]:
    """How far each period's `100 USD` value is from the `chart` level at its `End Dt`, in units
    of the levels' last digit, and whether an `End Dt` where they differ is a closure."""
    counts: Counter[str] = Counter()
    levels, unit = series.levels[subject], 2 * series.half
    for row in rows:
        value = number(row[column])
        if value is None:
            counts["not a number"] += 1
            continue
        units = abs(value - levels[series.index[row["end"]]]) / unit
        if not units:
            counts["equal"] += 1
            continue
        size = "1 unit" if units <= 1 else ("2 to 10 units" if units <= 10 else "over 10 units")
        counts[
            f"{size} apart, End Dt {'a closure' if row['end'] in shut else 'not a closure'}"
        ] += 1
    return counts


def compare(
    value: Decimal | None,
    reported: Decimal | None,
    precision: int | None,
    bounds: tuple[Decimal, Decimal] | None = None,
) -> str:
    if value is None or reported is None:
        return "unavailable"
    difference = abs(value - reported)
    own = half_unit(digits(reported, precision))
    if precision is not None and difference <= half_unit(precision):
        return "equal at the precision"
    if difference <= own:
        return "equal at its digits"
    if bounds is not None and bounds[0] - own <= reported <= bounds[1] + own:
        return "within the rounding"
    if difference <= 2 * own:
        return "within one unit of its digits"
    return "differs"


def check_metrics(
    series: Series, stats: dict[str, Any], precision: int | None, checked: Checked
) -> None:
    out = checked.outcome
    days = Decimal((series.dates[-1] - series.dates[0]).days)
    month_ends = [i for i in range(len(series.dates)) if is_month_end(series.dates, i)]
    monthly = month_ends[:-1]
    out["months"] = len(monthly) - 1
    samples = number(stats.get("samples"))
    out["samples_equal"] = samples is not None and samples == out["months"]
    h = series.half
    for subject, levels in series.levels.items():
        last = levels[-1]
        drawdown, bounds = max_drawdown(levels, h)
        reproduced = {
            "total_return": (last - HUNDRED, (last - h - HUNDRED, last + h - HUNDRED)),
            "annualized_return": (
                annualized(last, days),
                (annualized(last - h, days), annualized(last + h, days)),
            ),
            "max_drawdown": (drawdown, bounds),
            "standard_dev": monthly_deviation([levels[i] for i in monthly], h),
        }
        for metric, (value, range_) in reproduced.items():
            reported = number(stats[subject].get(metric))
            out[f"{subject}.{metric}"] = compare(value, reported, precision, range_)


def is_month_end(dates: list[date], i: int) -> bool:
    return i == len(dates) - 1 or dates[i + 1].month != dates[i].month


def annualized(last: Decimal, days: Decimal) -> Decimal:
    return ((last / HUNDRED) ** (Decimal("365.25") / days) - 1) * HUNDRED


def max_drawdown(levels: list[Decimal], h: Decimal) -> tuple[Decimal, tuple[Decimal, Decimal]]:
    """The largest decline from a peak, in percent, and the range the levels' rounding allows:
    every trough lower and every peak higher by `h`, and the deepest pair's the other way."""
    peak, worst, low = levels[0], Decimal(0), Decimal(0)
    pair = (levels[0], levels[0])
    for level in levels:
        peak = max(peak, level)
        drawdown = (level / peak - 1) * HUNDRED
        if drawdown < worst:
            worst, pair = drawdown, (peak, level)
        low = min(low, ((level - h) / (peak + h) - 1) * HUNDRED)
    high = min(Decimal(0), ((pair[1] + h) / (pair[0] - h) - 1) * HUNDRED)
    return worst, (low, high)


def monthly_deviation(
    levels: list[Decimal], h: Decimal
) -> tuple[Decimal | None, tuple[Decimal, Decimal] | None]:
    """The sample standard deviation of the monthly changes, in percent, times the square root of
    12, and the range the levels' rounding allows. Each change moves at most as far as its two
    levels' rounding allows, and the standard deviation at most by the length of those moves over
    the square root of n - 1, since centering doesn't lengthen a vector."""
    changes = [(b / a - 1) * HUNDRED for a, b in pairwise(levels)]
    if len(changes) < 2:
        return None, None
    root = Decimal(12).sqrt()
    mean = sum(changes, Decimal(0)) / len(changes)
    variance = sum(((c - mean) ** 2 for c in changes), Decimal(0)) / (len(changes) - 1)
    deviation = variance.sqrt() * root
    moves = [
        max((b + h) / (a - h) - b / a, b / a - (b - h) / (a + h)) * HUNDRED
        for a, b in pairwise(levels)
    ]
    bound = sum((m * m for m in moves), Decimal(0)).sqrt() / Decimal(len(changes) - 1).sqrt()
    return deviation, (deviation - bound * root, deviation + bound * root)


def check_compounded(
    rows: list[dict[str, Any]], stats: dict[str, Any], precision: int | None, checked: Checked
) -> None:
    for subject, column in PERIOD_RETURNS.items():
        values = [number(row[column]) for row in rows]
        reported = number(stats[subject].get("total_return"))
        known = [v for v in values if v is not None]
        if reported is None or len(known) < len(values):
            checked.outcome[f"{subject}.compounded"] = "unavailable"
            continue
        low = mid = high = Decimal(1)
        for value in known:
            half = half_unit(digits(value, precision))
            mid *= 1 + value / HUNDRED
            low *= 1 + (value - half) / HUNDRED
            high *= 1 + (value + half) / HUNDRED
        checked.outcome[f"{subject}.compounded"] = compare(
            (mid - 1) * HUNDRED, reported, precision, ((low - 1) * HUNDRED, (high - 1) * HUNDRED)
        )


def check_windows(series: Series, checked: Checked) -> None:
    """The outline's rule: a window ends at each `chart` date, and starts at the latest `chart`
    date at least its length earlier. Counts the windows, those over the length by more than 2
    days, the most days over it, and the windows whose start or end repeats a level."""
    ordinals = [d.toordinal() for d in series.dates]
    repeating = series.repeats["port"] | series.repeats["bench"]
    for length in WINDOWS:
        count = longer = longest = touching = 0
        for end, last in enumerate(ordinals):
            start = bisect.bisect_right(ordinals, last - length) - 1
            if start < 0:
                continue
            count += 1
            extra = last - ordinals[start] - length
            longest = max(longest, extra)
            longer += extra > 2
            touching += series.dates[start] in repeating or series.dates[end] in repeating
        checked.outcome[f"windows.{length}"] = (count, longer, longest, touching)


# Finding the responses


@dataclass
class Found:
    """One saved file with a backtest response, and where it came from."""

    folder: str
    location: str
    container: str | None
    case_id: str | None
    attempt: dict[str, Any] | None
    request: dict[str, Any] | None
    ranking: str


@dataclass
class Response:
    payload: dict[str, Any]
    found: list[Found]
    checked: Checked = field(default_factory=Checked)


def ranking_form(request: dict[str, Any] | None, definition_sent: bool) -> str:
    """The kind of ranking, never its value."""
    if definition_sent:
        return "a definition, sent with rank_update"
    screen = request.get("screen") if request else None
    ranking = screen.get("ranking") if isinstance(screen, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if isinstance(ranking, dict):
        return "a formula"
    if ranking == "ApiRankingSystem":
        return "ApiRankingSystem, after a rank_update"
    if isinstance(ranking, (str, int)):
        return "a saved ranking system"
    return "unknown"


def find_saved(
    reference: Path, requests: dict[str, Path]
) -> tuple[list[tuple[Found, Path]], Counter[str]]:
    found: list[tuple[Found, Path]] = []
    without: Counter[str] = Counter()
    for folder in sorted(p for p in reference.iterdir() if p.is_dir()):
        for kind in ("payloads", "exports"):
            base = folder / kind
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*.json")):
                item = describe(folder.name, base, path, without, requests.get(folder.name))
                if item is not None:
                    found.append((item, path))
    return found, without


def describe(
    folder: str, base: Path, path: Path, without: Counter[str], request_path: Path | None
) -> Found | None:
    """A run's or an experiment's attempt, `<root>/cases/<case_id>/attempts/<attempt_id>/`, or a
    script's saved response, outside any attempt. A snapshot's attempts hold no backtest."""
    parts = path.relative_to(base).parts
    in_case = len(parts) >= 5 and parts[-5] == "cases" and parts[-3] == "attempts"
    if path.name == "request.json" and in_case:
        if not (path.parent / "response.json").exists():
            attempt = load(path.parent / "attempt.json")
            outcome = attempt.get("outcome") if isinstance(attempt, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            without[f"{folder}: {outcome or 'no attempt record'}"] += 1
        return None
    if "attempts" in parts and not in_case:
        return None
    if path.name == "response.json" and in_case:
        container = "/".join(parts[:-5]) or "."
        attempt, request = load(path.parent / "attempt.json"), load(path.parent / "request.json")
        request = request if isinstance(request, dict) else None
        sent = (path.parent / "rank-update-request.json").exists()
        case_id = path.parents[2].name
        return Found(
            folder,
            f"{container}, {case_id}",
            container,
            case_id,
            attempt if isinstance(attempt, dict) else None,
            request,  # pyright: ignore[reportUnknownArgumentType]
            ranking_form(request, sent),  # pyright: ignore[reportUnknownArgumentType]
        )
    if path.name.startswith("response") or path.name.endswith("-backtest.json"):
        request = script_request(base, path, request_path)
        sent = (
            path.name.endswith("-backtest.json")
            and path.with_name(path.name.replace("-backtest.json", "-rank-update.json")).exists()
        )
        return Found(
            folder, "/".join(parts), None, None, None, request, ranking_form(request, sent)
        )
    return None


def script_request(base: Path, path: Path, given: Path | None) -> dict[str, Any] | None:
    """A script's request: the one `--request` names for its folder, `request-<x>.json` beside
    `response-<x>.json`, or the committed `request.json` above `payloads/`, as R01-T01's run
    record gives it."""
    candidates = [given] if given else []
    candidates += [path.with_name(path.name.replace("response", "request", 1))]
    candidates += [base.parent / "request.json"]
    for candidate in candidates:
        if candidate != path and candidate.exists():
            request = load(candidate)
            if isinstance(request, dict):
                return request  # pyright: ignore[reportUnknownVariableType]
    return None


def find_fixtures(root: Path) -> list[tuple[Found, Path]]:
    """The committed synthetic responses: the tests' fixtures, the demo's packaged response, and
    the ones beside this script, under `synthetic/`, each with the request beside it."""
    paths = sorted((root / "tests" / "fixtures").rglob("*.json"))
    paths.append(root / "src" / "trialfolio" / "demo_data" / "response.json")
    paths += sorted((root / "reference" / "return-series" / "synthetic").rglob("*.json"))
    found: list[tuple[Found, Path]] = []
    for path in paths:
        payload = load(path)
        if not isinstance(payload, dict) or not ({"stats", "chart"} & set(payload)):  # pyright: ignore[reportUnknownArgumentType]
            continue
        request = load(path.parent / "request.json")
        request = request if isinstance(request, dict) else None
        sent = (path.parent / "rank-update-request.json").exists()
        relative = path.relative_to(root).as_posix()
        form = ranking_form(request, sent)  # pyright: ignore[reportUnknownArgumentType]
        found.append((Found("fixtures", relative, None, None, None, request, form), path))  # pyright: ignore[reportUnknownArgumentType]
    return found


def gather(items: list[tuple[Found, Path]]) -> tuple[dict[str, Response], list[Found]]:
    """The distinct responses, by their bytes' hash, checked, and the files without the
    required structure."""
    responses: dict[str, Response] = {}
    invalid: list[Found] = []
    for item, path in items:
        payload = load(path)
        if not has_structure(payload):
            invalid.append(item)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        responses.setdefault(digest, Response(payload, [])).found.append(item)
    for response in responses.values():
        response.checked = check_response(response.payload, response.found[0].request)
    return responses, invalid


# Printing


def rebalance(outcome: Outcome) -> str:
    days = outcome.get("median_days")
    return {7: "1-week", 28: "4-week"}.get(days, f"median {days}-day")  # pyright: ignore[reportCallIssue, reportArgumentType]


def tally(outcomes: list[Outcome], key: str, expected: Any = True) -> str:
    values = [o.get(key) for o in outcomes]
    return f"{sum(v == expected for v in values)} of {len(values)}"


def spread(values: Iterable[Any]) -> str:
    """Each distinct value, with how many responses have it."""
    counts = Counter(str(v) for v in values)
    return ", ".join(f"{value} ({n})" for value, n in sorted(counts.items()))


def summed(outcomes: list[Outcome], key: str) -> str:
    total: Counter[str] = Counter()
    for o in outcomes:
        total.update(o.get(key) or {})
    return ", ".join(f"{kind} {n}" for kind, n in sorted(total.items())) or "none"


def show_group(name: str, outcomes: list[Outcome]) -> None:
    periods = sum(o.get("periods", 0) for o in outcomes)
    print(f"\n== {name}: {len(outcomes)} distinct responses, {periods} periods")
    print(
        f"  Has a chart, with its five arrays parallel: {tally(outcomes, 'chart')}, {tally(outcomes, 'parallel')}"
    )
    print(
        f"  Dates valid and increasing; levels positive numbers: {tally(outcomes, 'dates_valid')}, {tally(outcomes, 'levels_numbers')}"
    )
    print(f"  Only weekdays: {tally(outcomes, 'weekdays_only')}")
    print(
        f"  Every weekday from the start date to the end date: {tally(outcomes, 'every_weekday')}; the dates from {spread(o.get('dates_from') for o in outcomes)}"
    )
    print(f"  Coverage equals the requested dates: {tally(outcomes, 'coverage_is_request')}")
    print(f"  Each End Dt is the next period's Tran Dt: {tally(outcomes, 'contiguous')}")
    print(f"  Both levels start at 100: {tally(outcomes, 'start_100')}")
    print(
        f"  No value has more decimals than the precision: {tally(outcomes, 'over_precision', 0)}"
    )
    print(f"  Points: {spread(o.get('points') for o in outcomes)}")
    print(
        f"  First and last chart dates: {spread((str(o.get('first')), str(o.get('last'))) for o in outcomes)}"
    )
    print(f"  Requested dates: {spread(tuple(map(str, o.get('requested', ()))) for o in outcomes)}")
    print(f"  Precision: {spread(o.get('precision') for o in outcomes)}")
    print(f"  Benchmark: {spread(o.get('benchmark') for o in outcomes)}")
    print(f"  Currency: {spread(o.get('currency') for o in outcomes)}")
    print(
        "  Distinct level series, by their values: strategy "
        f"{len({o.get('port.series') for o in outcomes})}, benchmark "
        f"{len({o.get('bench.series') for o in outcomes})}"
    )
    print(
        f"  Largest gap between chart dates, in days: {spread(o.get('max_gap') for o in outcomes)}"
    )
    print(
        f"  Closures from the first to the last date, and the weekdays after them: {spread((o.get('closures'), o.get('after_closures')) for o in outcomes)}"
    )
    print(
        f"  Starts on a closure: {tally(outcomes, 'starts_on_closure')}; ends on one: {tally(outcomes, 'ends_on_closure')}"
    )
    print(
        f"  The second chart entry repeats the first: port {tally(outcomes, 'port.second_repeats')}, bench {tally(outcomes, 'bench.second_repeats')}"
    )
    for subject in LEVELS:
        print(
            f"  {subject} repeats the entry before: in all {spread(o.get(f'{subject}.repeats') for o in outcomes)}; "
            f"on a closure {spread(o.get(f'{subject}.repeat_on_closure') for o in outcomes)}; "
            f"on the weekday after one {spread(o.get(f'{subject}.repeat_after') for o in outcomes)}; "
            f"elsewhere {spread(o.get(f'{subject}.repeat_elsewhere') for o in outcomes)}"
        )
        print(
            f"  {subject} moves on the weekday after a closure: {spread(o.get(f'{subject}.moves_after') for o in outcomes)}; {summed(outcomes, f'{subject}.moves_after_kind')}"
        )
    print(
        f"  Periods with a closure as Tran Dt, as End Dt: {sum(o.get('tran_on_closure', 0) for o in outcomes)}, {sum(o.get('end_on_closure', 0) for o in outcomes)}"
    )
    print(
        f"  Periods with both dates in chart: {sum(o.get('periods_in_chart', 0) for o in outcomes)} of {periods}"
    )
    for column in PERIOD_RETURNS.values():
        print(f"  {column} from the levels: {summed(outcomes, f'{column}.from_levels')}")
    print(f"  Excess% from Ret% and Bench%: {summed(outcomes, 'excess')}")
    print(
        "  bench repeats elsewhere, by benchmark: "
        f"{spread((o.get('benchmark'), o.get('bench.repeat_elsewhere')) for o in outcomes)}"
    )
    print(f"  100 USD columns: {spread(o.get('usd_columns') for o in outcomes)}")
    for subject in LEVELS:
        print(f"  100 USD for {subject} is {summed(outcomes, f'usd.{subject}')}")
    print(
        f"  stats.samples is the monthly returns' count: {tally(outcomes, 'samples_equal')}; months {spread(o.get('months') for o in outcomes)}"
    )
    for subject in LEVELS:
        for metric in (*METRICS, "compounded"):
            key = f"{subject}.{metric}"
            print(f"  {key}: {spread(o.get(key, 'not checked') for o in outcomes)}")
    for length in WINDOWS:
        values = [o[f"windows.{length}"] for o in outcomes if f"windows.{length}" in o]
        if values:
            print(
                f"  {length}-day windows: {spread(v[0] for v in values)}; over {length + 2} days: "
                f"{sum(v[1] for v in values)}; the most days over {length}: "
                f"{max(v[2] for v in values)}; starting or ending on a repeat: "
                f"{spread(v[3] for v in values)}"
            )


def show_exceptions(responses: dict[str, Response]) -> None:
    """Each response where a 100 USD value isn't the level, a metric isn't equal at the
    precision, or a level repeats on a closure, with where it was found."""
    print("\n== Responses where something isn't exact")
    for response in responses.values():
        o = response.checked.outcome
        notes = [
            f"100 USD {subject}: {summed([o], f'usd.{subject}')}"
            for subject in LEVELS
            if set(o.get(f"usd.{subject}") or {}) - {"equal"}
        ]
        notes += [
            f"{subject}.{metric} {o.get(f'{subject}.{metric}')}"
            for subject in LEVELS
            for metric in (*METRICS, "compounded")
            if o.get(f"{subject}.{metric}") not in ("equal at the precision", None)
        ]
        notes += [
            f"{subject} repeats on closures {o[f'{subject}.repeat_on_closure_dates']}"
            for subject in LEVELS
            if o.get(f"{subject}.repeat_on_closure_dates")
        ]
        notes += response.checked.exceptions
        if notes:
            item = response.found[0]
            print(
                f"  {item.folder}: {item.location} ({rebalance(o)}, {o.get('benchmark')}, "
                f"{item.ranking}; {len(response.found)} file(s)): {'; '.join(notes)}"
            )


def show_experiments(responses: dict[str, Response], reference: Path) -> None:
    cases: dict[tuple[str, str], list[tuple[Found, Response]]] = defaultdict(list)
    for response in responses.values():
        for item in response.found:
            if item.container and item.case_id:
                cases[(item.folder, item.container)].append((item, response))
    print("\n== Saved experiments")
    for (folder, container), entries in sorted(cases.items()):
        record = latest_record(reference / folder / "payloads" / container)
        if record is None:
            continue
        planned = [c.get("case_id") for c in record.get("planned_cases", [])]
        retired = [c.get("case_id") for c in record.get("retired_cases", [])]
        print(f"  {folder}: {container}: {len(planned)} planned cases, {len(retired)} retired")
        for case_id in [*planned, *retired]:
            role = "retired" if case_id in retired else "variant"
            role = "baseline" if case_id == planned[0] else role
            succeeded = [
                (item, response)
                for item, response in entries
                if item.case_id == case_id and (item.attempt or {}).get("outcome") == "succeeded"
            ]
            if not succeeded:
                print(f"    {case_id} ({role}): no succeeded attempt with a response")
                continue
            item, response = max(succeeded, key=lambda e: str((e[0].attempt or {}).get("ended_at")))
            o = response.checked.outcome
            windows = ", ".join(
                f"{n} days {o[f'windows.{n}'][0]}" for n in WINDOWS if f"windows.{n}" in o
            )
            print(
                f"    {case_id} ({role}; {item.ranking}): {o.get('periods')} periods, "
                f"{rebalance(o)}; {o.get('points')} chart dates, {o.get('first')} to "
                f"{o.get('last')}, every weekday {o.get('every_weekday')}; succeeded attempts "
                f"{len(succeeded)}; windows: {windows}"
            )


def latest_record(root: Path) -> dict[str, Any] | None:
    plans = [p for p in (root / "plans").glob("*") if (p / "experiment.json").exists()]
    if not plans:
        return None
    record = load(max(plans, key=lambda p: int(p.name)) / "experiment.json")
    return record if isinstance(record, dict) else None  # pyright: ignore[reportUnknownVariableType]


def show_fixtures(responses: dict[str, Response], invalid: list[Found]) -> None:
    """Every check's outcome for each committed synthetic response, so that a check a response
    plants a failure for shows it."""
    print("\n== Committed synthetic responses")
    for response in responses.values():
        o = response.checked.outcome
        print(f"  {len(response.found)} file(s): {', '.join(i.location for i in response.found)}")
        print(
            f"    chart {o.get('chart')}, parallel {o.get('parallel')}, {o.get('points')} dates "
            f"from {o.get('first')} to {o.get('last')}, dates valid {o.get('dates_valid')}, "
            f"levels positive numbers {o.get('levels_numbers')}, only weekdays "
            f"{o.get('weekdays_only')}, every weekday {o.get('every_weekday')}, largest gap "
            f"{o.get('max_gap')} days, starts at 100 {o.get('start_100')}, the second entry "
            f"repeats the first {o.get('port.second_repeats')} and {o.get('bench.second_repeats')}, "
            f"values with more decimals than the precision {o.get('over_precision')}"
        )
        print(
            f"    {o.get('periods')} periods; coverage equals the requested dates "
            f"{o.get('coverage_is_request')}; each End Dt is the next Tran Dt "
            f"{o.get('contiguous')}; Ret% {summed([o], 'Ret%.from_levels')}; Bench% "
            f"{summed([o], 'Bench%.from_levels')}; Excess% {summed([o], 'excess')}; 100 USD for "
            f"port {summed([o], 'usd.port')}; for bench {summed([o], 'usd.bench')}"
        )
        metrics = ", ".join(
            f"{subject}.{metric} {o.get(f'{subject}.{metric}', 'not checked')}"
            for subject in LEVELS
            for metric in (*METRICS, "compounded")
        )
        print(f"    {metrics}; stats.samples is the months' count {o.get('samples_equal')}")
        if "closures" in o:
            for subject in LEVELS:
                print(
                    f"    {subject}: of {o['closures']} closures, repeats the entry before on "
                    f"{o[f'{subject}.repeat_on_closure_dates'] or 'none'}; repeats on "
                    f"{o[f'{subject}.repeat_after']} of the {o['after_closures']} weekdays after "
                    f"them; elsewhere {o[f'{subject}.repeat_elsewhere'] or 'none'}; moves on "
                    f"{o[f'{subject}.moves_after']}: {summed([o], f'{subject}.moves_after_kind')}"
                )
        else:
            print("    Closures not checked")
        windows = "; ".join(
            f"{n} days {o[f'windows.{n}'][0]}, over {n + 2} days {o[f'windows.{n}'][1]}, "
            f"the most days over {o[f'windows.{n}'][2]}"
            for n in WINDOWS
            if f"windows.{n}" in o
        )
        print(f"    Windows: {windows or 'not checked'}")
    for item in invalid:
        print(f"  Without the required structure: {item.location}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("reference", type=Path)
    parser.add_argument("--fixtures", type=Path, metavar="REPO_ROOT")
    parser.add_argument("--request", action="append", default=[], metavar="FOLDER=PATH")
    args = parser.parse_args()
    requests = {
        folder: args.reference / path
        for folder, path in (given.split("=", 1) for given in args.request)
    }
    print(f"Python {platform.python_version()}, {platform.system()} {platform.release()}")
    items, without = find_saved(args.reference, requests)
    responses, invalid = gather(items)
    print(f"\n== Saved files with a backtest response: {len(items)}")
    folders: dict[str, list[str]] = defaultdict(list)
    for digest, response in responses.items():
        for item in response.found:
            folders[item.folder].append(digest)
    for folder, digests in sorted(folders.items()):
        print(f"  {folder}: {len(digests)} files, {len(set(digests))} distinct")
    print(f"  Distinct in all: {len(responses)}")
    print(f"  Without the required structure: {spread(i.folder for i in invalid) or 'none'}")
    print(f"  Attempts without a response: {spread(without.elements()) or 'none'}")
    print(
        f"  Without a request: {spread(r.found[0].folder for r in responses.values() if r.found[0].request is None) or 'none'}"
    )
    groups: dict[str, list[Outcome]] = defaultdict(list)
    for response in responses.values():
        outcome = response.checked.outcome
        groups[f"{rebalance(outcome)} rebalancing, ranked by {response.found[0].ranking}"].append(
            outcome
        )
    for name in sorted(groups):
        show_group(name, groups[name])
    show_group("Every saved response", [r.checked.outcome for r in responses.values()])
    show_exceptions(responses)
    show_experiments(responses, args.reference)
    if args.fixtures:
        fixtures, invalid_fixtures = gather(find_fixtures(args.fixtures))
        show_fixtures(fixtures, invalid_fixtures)


if __name__ == "__main__":
    sys.exit(main())
