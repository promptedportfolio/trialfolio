"""The reference calculation of analysis set 1.0.0: each of its values for a response's `chart` and
`results.rows`, read with `json`, in binary floating point, with Python's `statistics` for means,
medians, standard deviations, and percentiles (release 0.5.0, test pairing; docs/methodology.md,
verification of statistical methods).

It imports nothing from `trialfolio`, and repeats none of its code: it reads the response's JSON
itself, finds the segments by their dates rather than by positions, and calculates each value
with floats and `statistics`, so it's the independent reference calculation methodology.md asks
for, not a double. A percentile is `statistics.quantiles` with `method="inclusive"`, or the
window's return when there's one window, since Python 3.12's `quantiles` raises an error there.

`reference` gives a value for each row `analysis.csv` has, by its segment, analysis, subject, and
window: the value, a float, a whole number, or a date, or the reason it's unavailable, with its
observations and dates. The reconciliation isn't part of it: its ranges meet the reported value
at their ends, where a float can fall either side, so `tests/core/test_reconciliation.py` checks
them by hand.

R05-T06 wrote it, for R05-AC03.
"""

import bisect
import itertools
import json
import math
import re
import statistics
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, cast

type Key = tuple[str, str, str | None, int | None]
"""A row's segment, analysis, subject, and window length."""

WINDOWS: Final = (7, 30, 90, 180, 365)
_DATE_TEXT: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_RETURN_COLUMNS: Final = {"strategy": "Ret%", "benchmark": "Bench%", "excess": "Excess%"}


@dataclass(frozen=True)
class Expected:
    """One value as the reference calculates it, or why it's unavailable."""

    value: float | int | date | None
    reason: str | None = None
    observations: int | None = None
    start: date | None = None
    end: date | None = None
    not_recovered: bool = False


def reference(
    response: bytes, *, start: date, end: date, splits: Sequence[date] = ()
) -> dict[Key, Expected]:
    """Each value of analysis set 1.0.0 for `response`, a saved `response.json`, requested from
    `start` to `end`, with the declared split dates `splits`."""
    loaded = json.loads(response)
    daily = _daily(loaded.get("chart"), start, end)
    columns = loaded["results"]["columns"]
    rows = loaded["results"]["rows"]
    periods = _periods(columns, rows)
    coverage = _coverage(columns, rows)
    values: dict[Key, Expected] = {}
    values.update(_segment_values("full", daily, periods, coverage is not None))
    values.update(_rolling(daily))
    if splits:
        values.update(_split_values(daily, periods, coverage, list(splits)))
    return values


# Reading the response.


@dataclass(frozen=True)
class _Daily:
    days: list[date]
    strategy: list[float]
    benchmark: list[float]


@dataclass(frozen=True)
class _Period:
    start: date | None
    end: date | None
    returns: dict[str, float | None]


def _a_date(text: object) -> date | None:
    if not isinstance(text, str) or not _DATE_TEXT.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _a_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _daily(chart: object, start: date, end: date) -> _Daily | None:
    if not isinstance(chart, dict):
        return None
    arrays = [chart.get(key) for key in ("dates", "screenReturns", "benchReturns")]
    if not all(isinstance(array, list) and array for array in arrays):
        return None
    texts, *series = cast("list[list[object]]", arrays)
    days = [day for day in map(_a_date, texts) if day is not None]
    strategy, benchmark = (
        [level for level in map(_a_number, s) if level is not None] for s in series
    )
    if {len(days), len(strategy), len(benchmark)} != {len(texts)} or any(
        len(s) != len(texts) for s in series
    ):
        return None
    if strategy[0] != 100 or benchmark[0] != 100 or min(strategy + benchmark) <= 0:
        return None
    weekdays = [
        start + timedelta(n)
        for n in range((end - start).days + 1)
        if (start + timedelta(n)).isoweekday() <= 5
    ]
    if days != weekdays:
        return None
    return _Daily(days, strategy, benchmark)


def _periods(columns: list[str], rows: list[list[object]]) -> list[_Period] | None:
    if not rows or "Tran Dt" not in columns or "End Dt" not in columns:
        return None
    read = []
    for row in rows:
        starts, ends = _a_date(row[columns.index("Tran Dt")]), _a_date(row[columns.index("End Dt")])
        returns = {
            subject: (
                _a_number(row[columns.index(name)]) if name in columns and starts and ends else None
            )
            for subject, name in _RETURN_COLUMNS.items()
        }
        read.append(_Period(starts, ends, returns))
    with_dates = sorted((p for p in read if p.start), key=lambda p: p.start)
    return with_dates + [p for p in read if not p.start]


def _coverage(columns: list[str], rows: list[list[object]]) -> tuple[date, date] | None:
    if not rows or "Tran Dt" not in columns or "End Dt" not in columns:
        return None
    starts = [_a_date(row[columns.index("Tran Dt")]) for row in rows]
    ends = [_a_date(row[columns.index("End Dt")]) for row in rows]
    known_starts = [day for day in starts if day is not None]
    known_ends = [day for day in ends if day is not None]
    if len(known_starts) < len(rows) or len(known_ends) < len(rows):
        return None
    if min(known_starts) > max(known_ends):
        return None
    return (min(known_starts), max(known_ends))


# The segments.


def _split_values(
    daily: _Daily | None,
    periods: list[_Period] | None,
    coverage: tuple[date, date] | None,
    splits: list[date],
) -> dict[Key, Expected]:
    known = coverage
    if known is None and daily is not None:
        known = (daily.days[0], daily.days[-1])
    values: dict[Key, Expected] = {}
    bounds = [None, *splits, None]
    for n in range(len(splits) + 1):
        name = f"split-{n}"
        if known is None:
            values.update(_whole(name, Expected(None, "input_unavailable")))
            continue
        c0, c1 = known
        lower, upper = bounds[n], bounds[n + 1]
        first = c0 if lower is None else (max(lower, c0) if upper is None else lower)
        last = c1 if upper is None else (min(upper, c1) if lower is None else upper)
        if first > last or first < c0 or last > c1 or (daily and daily.days[0] > first):
            values.update(_whole(name, Expected(None, "outside_coverage")))
            continue
        span = _span(daily, first, last)
        known_periods = periods if coverage is not None else None
        inside = _inside(known_periods, lower, upper)
        values.update(_segment_values(name, span, inside, True))
        total = (c1 - c0).days
        share = (
            Expected(None, "not_applicable")
            if total == 0
            else Expected((last - first).days / total * 100, None, None, first, last)
        )
        values[(name, "coverage_share", None, None)] = share
        values[(name, "spanning_period_count", None, None)] = (
            Expected(None, "input_unavailable")
            if known_periods is None
            else Expected(
                sum(_spanning(p, lower, upper) for p in known_periods),
                None,
                len(known_periods),
                first,
                last,
            )
        )
    return values


def _inside(
    periods: list[_Period] | None, lower: date | None, upper: date | None
) -> list[_Period] | None:
    """The periods wholly between the segment's declared dates, where they're known; each has both
    its dates then, since the coverage is available."""
    if periods is None:
        return None
    return [
        p
        for p in periods
        if (lower is None or cast("date", p.start) >= lower)
        and (upper is None or cast("date", p.end) <= upper)
    ]


def _spanning(period: _Period, lower: date | None, upper: date | None) -> bool:
    start, end = cast("date", period.start), cast("date", period.end)
    return any(start < day < end for day in (lower, upper) if day is not None)


def _span(daily: _Daily | None, first: date, last: date) -> _Daily | None:
    if daily is None:
        return None
    begin = max(d for d in daily.days if d <= first)
    finish = max(d for d in daily.days if d <= last)
    kept = [i for i, d in enumerate(daily.days) if begin <= d <= finish]
    return _Daily(
        [daily.days[i] for i in kept],
        [daily.strategy[i] for i in kept],
        [daily.benchmark[i] for i in kept],
    )


def _whole(name: str, expected: Expected) -> dict[Key, Expected]:
    """Every row of a split segment, each with the same unavailable value."""
    keys = [("coverage_share", None), ("period_count", None), ("spanning_period_count", None)]
    keys += _PERIOD_KEYS + _LEVEL_KEYS
    return {(name, analysis, subject, None): expected for analysis, subject in keys}


_PERIOD_KEYS: Final = [
    (analysis, subject)
    for analysis in (
        "mean_period_return",
        "median_period_return",
        "best_period_return",
        "worst_period_return",
    )
    for subject in ("strategy", "benchmark", "excess")
] + [
    ("positive_excess_share", "excess"),
    ("tracking_error", "excess"),
    ("information_ratio", "excess"),
    ("excess_t_value", "excess"),
]
_LEVEL_KEYS: Final = [
    (analysis, subject)
    for analysis in (
        "total_return",
        "annualized_return",
        "max_drawdown",
        "max_drawdown_recovery",
        "longest_drawdown_days",
    )
    for subject in ("strategy", "benchmark")
] + [("total_return_difference", "excess"), ("annualized_return_difference", "excess")]


def _segment_values(
    name: str, daily: _Daily | None, periods: list[_Period] | None, dated: bool
) -> dict[Key, Expected]:
    values: dict[Key, Expected] = {}
    for (analysis, subject), expected in _period_values(periods, dated).items():
        values[(name, analysis, subject, None)] = expected
    for (analysis, subject), expected in _level_values(daily).items():
        values[(name, analysis, subject, None)] = expected
    return values


# The period returns.


def _period_values(
    periods: list[_Period] | None, dated: bool
) -> dict[tuple[str, str | None], Expected]:
    if periods is None:
        keys = [("period_count", None), *_PERIOD_KEYS]
        return dict.fromkeys(keys, Expected(None, "input_unavailable"))
    n = len(periods)
    span: tuple[date | None, date | None] = (None, None)
    if periods and dated:
        span = (
            min(cast("date", p.start) for p in periods),
            max(cast("date", p.end) for p in periods),
        )
    values: dict[tuple[str, str | None], Expected] = {
        ("period_count", None): Expected(n, None, n, *span)
    }
    for subject in ("strategy", "benchmark", "excess"):
        returns = [p.returns[subject] for p in periods]
        values[("mean_period_return", subject)] = _of(returns, statistics.fmean, span)
        values[("median_period_return", subject)] = _of(returns, statistics.median, span)
        for analysis, pick in (("best_period_return", max), ("worst_period_return", min)):
            known = [value for value in returns if value is not None]
            if len(known) < len(returns) or not known:
                values[(analysis, subject)] = _of(returns, pick, span)
                continue
            chosen = next(p for p in periods if p.returns[subject] == pick(known))
            values[(analysis, subject)] = Expected(pick(known), None, n, chosen.start, chosen.end)
    excess = [p.returns["excess"] for p in periods]
    values[("positive_excess_share", "excess")] = _of(
        excess, lambda xs: 100 * len([x for x in xs if x > 0]) / len(xs), span
    )
    values[("tracking_error", "excess")] = _of(excess, statistics.stdev, span, needs=2)
    values[("information_ratio", "excess")] = _of(
        excess, lambda xs: statistics.fmean(xs) / statistics.stdev(xs), span, needs=2, ratio=True
    )
    values[("excess_t_value", "excess")] = _of(
        excess,
        lambda xs: statistics.fmean(xs) / (statistics.stdev(xs) / math.sqrt(len(xs))),
        span,
        needs=2,
        ratio=True,
    )
    return values


def _of(
    returns: list[float | None],
    statistic: Callable[[list[float]], float],
    span: tuple[date | None, date | None],
    *,
    needs: int = 1,
    ratio: bool = False,
) -> Expected:
    known = [value for value in returns if value is not None]
    if len(known) < len(returns):
        return Expected(None, "input_unavailable")
    if len(known) < needs:
        return Expected(None, "too_few_observations", len(known))
    if ratio and statistics.stdev(known) == 0:
        return Expected(None, "not_applicable", len(known))
    return Expected(statistic(known), None, len(known), *span)


# The daily levels.


def _level_values(daily: _Daily | None) -> dict[tuple[str, str], Expected]:
    if daily is None:
        return dict.fromkeys(_LEVEL_KEYS, Expected(None, "input_unavailable"))
    values: dict[tuple[str, str], Expected] = {}
    count = len(daily.days)
    for subject, levels in (("strategy", daily.strategy), ("benchmark", daily.benchmark)):
        if count < 2:
            for analysis in (
                "total_return",
                "annualized_return",
                "max_drawdown",
                "max_drawdown_recovery",
                "longest_drawdown_days",
            ):
                values[(analysis, subject)] = Expected(None, "too_few_observations", count)
            continue
        first, last = daily.days[0], daily.days[-1]
        values[("total_return", subject)] = Expected(
            (levels[-1] / levels[0] - 1) * 100, None, count, first, last
        )
        days = (last - first).days
        values[("annualized_return", subject)] = (
            Expected(None, "too_short", count)
            if days < 365
            else Expected(
                ((levels[-1] / levels[0]) ** (365.25 / days) - 1) * 100, None, count, first, last
            )
        )
        values.update(_drawdowns(subject, daily.days, levels))
    for analysis, of in (
        ("total_return_difference", "total_return"),
        ("annualized_return_difference", "annualized_return"),
    ):
        strategy, benchmark = values[(of, "strategy")], values[(of, "benchmark")]
        values[(analysis, "excess")] = (
            Expected(None, "input_unavailable")
            if strategy.value is None or benchmark.value is None
            else Expected(
                round(cast("float", strategy.value), 4) - round(cast("float", benchmark.value), 4),
                None,
                count,
                strategy.start,
                strategy.end,
            )
        )
    return values


def _drawdowns(
    subject: str, days: list[date], levels: list[float]
) -> dict[tuple[str, str], Expected]:
    count = len(days)
    peaks = list(itertools.accumulate(levels, max))
    declines = [(level / peak - 1) * 100 for level, peak in zip(levels, peaks, strict=True)]
    deepest = min(declines)
    values: dict[tuple[str, str], Expected] = {}
    if deepest >= 0:
        values[("max_drawdown", subject)] = Expected(0.0, None, count)
        values[("max_drawdown_recovery", subject)] = Expected(None, "not_applicable", count)
    else:
        trough = declines.index(deepest)
        peak = levels.index(peaks[trough])
        values[("max_drawdown", subject)] = Expected(deepest, None, count, days[peak], days[trough])
        back = [j for j in range(trough + 1, count) if levels[j] >= levels[peak]]
        values[("max_drawdown_recovery", subject)] = (
            Expected(days[back[0]], None, count, days[0], days[-1])
            if back
            else Expected(None, "not_recovered", count)
        )
    values[("longest_drawdown_days", subject)] = _longest(days, levels, peaks)
    return values


def _longest(days: list[date], levels: list[float], peaks: list[float]) -> Expected:
    below = [level < peak for level, peak in zip(levels, peaks, strict=True)]
    times = []
    j = 0
    while j < len(days):
        if not below[j]:
            j += 1
            continue
        run_end = j
        while run_end + 1 < len(days) and below[run_end + 1]:
            run_end += 1
        recovered = run_end + 1 < len(days)
        finish = run_end + 1 if recovered else run_end
        times.append(((days[finish] - days[j - 1]).days, days[j - 1], days[finish], not recovered))
        j = run_end + 1
    if not times:
        return Expected(0, None, len(days))
    longest = max(times, key=lambda time: time[0])
    length, first, last, unrecovered = longest
    return Expected(length, None, len(days), first, last, unrecovered)


# The rolling returns.


def _rolling(daily: _Daily | None) -> dict[Key, Expected]:
    values: dict[Key, Expected] = {}
    for window in WINDOWS:
        keys = [("rolling_window_count", None), ("rolling_non_overlapping_count", None)]
        keys += [
            (analysis, subject)
            for analysis in (
                "rolling_mean",
                "rolling_median",
                "rolling_p10",
                "rolling_p90",
                "rolling_worst",
            )
            for subject in ("strategy", "benchmark")
        ]
        keys += [("rolling_share_beating", "excess")]
        if daily is None:
            for analysis, subject in keys:
                values[("full", analysis, subject, window)] = Expected(None, "input_unavailable")
            continue
        for (analysis, subject), expected in _windows(daily, window).items():
            values[("full", analysis, subject, window)] = expected
    return values


def _windows(daily: _Daily, window: int) -> dict[tuple[str, str | None], Expected]:
    pairs = []
    for j, ends in enumerate(daily.days):
        if ends - timedelta(window) < daily.days[0]:
            continue
        # The latest date on or before the window's earliest, by bisection over the dates.
        i = bisect.bisect_right(daily.days, ends - timedelta(window)) - 1
        pairs.append((i, j))
    m = len(pairs)
    span = (daily.days[pairs[0][0]], daily.days[pairs[-1][1]]) if pairs else (None, None)
    counted, last = 0, None
    for i, j in pairs:
        if last is None or daily.days[i] >= daily.days[last]:
            counted, last = counted + 1, j
    values: dict[tuple[str, str | None], Expected] = {
        ("rolling_window_count", None): Expected(m, None, m, *span),
        ("rolling_non_overlapping_count", None): Expected(counted, None, m, *span),
    }
    returns = {
        subject: [(levels[j] / levels[i] - 1) * 100 for i, j in pairs]
        for subject, levels in (("strategy", daily.strategy), ("benchmark", daily.benchmark))
    }
    for subject, xs in returns.items():
        summaries = {
            "rolling_mean": statistics.fmean,
            "rolling_median": statistics.median,
            "rolling_p10": lambda xs: _percentile(xs, 0),
            "rolling_p90": lambda xs: _percentile(xs, 8),
            "rolling_worst": min,
        }
        for analysis, summary in summaries.items():
            values[(analysis, subject)] = (
                Expected(summary(xs), None, m, *span)
                if xs
                else Expected(None, "too_few_observations", 0)
            )
    beaten = [s > b for s, b in zip(returns["strategy"], returns["benchmark"], strict=True)]
    values[("rolling_share_beating", "excess")] = (
        Expected(100 * sum(beaten) / m, None, m, *span)
        if m
        else Expected(None, "too_few_observations", 0)
    )
    return values


def _percentile(xs: list[float], decile: int) -> float:
    """The 10th or 90th percentile: `statistics.quantiles`' first or ninth decile, inclusive, or
    the window's return when there's one window."""
    if len(xs) == 1:
        return xs[0]
    return statistics.quantiles(xs, n=10, method="inclusive")[decile]
