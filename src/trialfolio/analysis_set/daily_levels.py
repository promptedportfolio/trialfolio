"""The daily-level analyses, over a segment's levels L_a to L_b, on the dates t_a to t_b
(methodology.md, daily-level analyses).

`level_values` gives each of a segment's values from its levels, by analysis and subject. Its
observations are the number of levels; without the daily series, each value is unavailable with
`input_unavailable`, and with fewer levels than it needs, with `too_few_observations`. A
difference is the strategy's value minus the benchmark's, each as rounded, so it's exact at their
digits. `drawdown` finds the maximum drawdown's peak and trough, which the reconciliation reads
too.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from trialfolio.analysis_set.arithmetic import (
    Calculated,
    days_between,
    percent,
    rounded,
    unavailable,
)
from trialfolio.analysis_set.inputs import LevelSubject
from trialfolio.analysis_set.segments import LevelSpan, Segment
from trialfolio.contracts.tables import AnalysisSubject

_SUBJECTS: tuple[LevelSubject, ...] = ("strategy", "benchmark")
_YEAR = Decimal("365.25")
_SHORTEST_DAYS = 365
"""A return over fewer calendar days isn't stated at an annual rate (`too_short`)."""

_NAMES = (
    "total_return",
    "annualized_return",
    "max_drawdown",
    "max_drawdown_recovery",
    "longest_drawdown_days",
)
_DIFFERENCES = {
    "total_return_difference": "total_return",
    "annualized_return_difference": "annualized_return",
}


def level_values(
    segment: Segment, precision: int
) -> dict[tuple[str, AnalysisSubject | None], Calculated]:
    """Each of `segment`'s values from its levels, for the strategy and the benchmark, and the
    differences between them, the excess's; a percent rounded to `precision` decimals before it's
    differenced."""
    span = segment.levels
    if span is None:
        of_levels: list[tuple[str, AnalysisSubject | None]] = [
            (name, subject) for name in _NAMES for subject in _SUBJECTS
        ]
        differences: list[tuple[str, AnalysisSubject | None]] = [
            (name, "excess") for name in _DIFFERENCES
        ]
        return dict.fromkeys([*of_levels, *differences], unavailable("input_unavailable"))
    values: dict[tuple[str, AnalysisSubject | None], Calculated] = {}
    dates = span.dates
    for subject in _SUBJECTS:
        levels = span_levels(span, subject)
        values[("total_return", subject)] = _total_return(levels, dates)
        values[("annualized_return", subject)] = _annualized_return(levels, dates)
        found = drawdown(levels)
        values[("max_drawdown", subject)] = _max_drawdown(found, levels, dates)
        values[("max_drawdown_recovery", subject)] = _recovery(found, levels, dates)
        values[("longest_drawdown_days", subject)] = _longest(levels, dates)
    for name, of in _DIFFERENCES.items():
        values[(name, "excess")] = _difference(
            values[(of, "strategy")], values[(of, "benchmark")], precision
        )
    return values


def span_levels(span: LevelSpan, subject: LevelSubject) -> tuple[Decimal, ...]:
    """A segment's levels of one subject."""
    return span.levels.values[subject][span.first : span.last + 1]


def _total_return(levels: Sequence[Decimal], dates: Sequence[date]) -> Calculated:
    """(L_b / L_a − 1) × 100."""
    if len(levels) < 2:
        return unavailable("too_few_observations", len(levels))
    return Calculated(percent(levels[-1] / levels[0]), None, len(levels), (dates[0], dates[-1]))


def _annualized_return(levels: Sequence[Decimal], dates: Sequence[date]) -> Calculated:
    """((L_b / L_a)^(365.25 / D) − 1) × 100, with D the calendar days from t_a to t_b, and
    `too_short` for D under 365."""
    if len(levels) < 2:
        return unavailable("too_few_observations", len(levels))
    days = days_between(dates[0], dates[-1])
    if days < _SHORTEST_DAYS:
        return Calculated(None, "too_short", len(levels))
    growth = (levels[-1] / levels[0]) ** (_YEAR / days)
    return Calculated(percent(growth), None, len(levels), (dates[0], dates[-1]))


def _difference(strategy: Calculated, benchmark: Calculated, precision: int) -> Calculated:
    """The strategy's value minus the benchmark's, each as rounded, with both values' levels and
    dates; `input_unavailable` unless both are available."""
    if not isinstance(strategy.value, Decimal) or not isinstance(benchmark.value, Decimal):
        return unavailable("input_unavailable")
    difference = rounded(strategy.value, precision) - rounded(benchmark.value, precision)
    return Calculated(difference, None, strategy.observations, strategy.dates)


@dataclass(frozen=True)
class Drawdown:
    """The largest decline from a running peak: (L_j / M_j − 1) × 100 at its trough, and its peak,
    by their positions among the levels; no trough when the level never falls below its running
    peak."""

    value: Decimal
    peak: int | None
    trough: int | None


def drawdown(levels: Sequence[Decimal]) -> Drawdown:
    """The maximum drawdown of `levels`: the smallest of (L_j / M_j − 1) × 100, where M_j is the
    highest level from the first to L_j. Its peak is the first position the level reached the
    peak it fell from, and its trough the first position of the largest decline."""
    deepest = Decimal(0)
    peak_at = trough_at = None
    running = 0
    for at, level in enumerate(levels):
        if level > levels[running]:
            running = at
        decline = percent(level / levels[running])
        if decline < deepest:
            deepest, peak_at, trough_at = decline, running, at
    return Drawdown(deepest, peak_at, trough_at)


def _max_drawdown(found: Drawdown, levels: Sequence[Decimal], dates: Sequence[date]) -> Calculated:
    """The maximum drawdown, as a negative number, dated by its peak and its trough; 0, with no
    dates, when the level never falls below its running peak."""
    if len(levels) < 2:
        return unavailable("too_few_observations", len(levels))
    if found.peak is None or found.trough is None:
        return Calculated(Decimal(0), None, len(levels))
    return Calculated(found.value, None, len(levels), (dates[found.peak], dates[found.trough]))


def _recovery(found: Drawdown, levels: Sequence[Decimal], dates: Sequence[date]) -> Calculated:
    """The first date after the trough whose level is at least the peak's; `not_applicable` when
    the maximum drawdown is 0, and `not_recovered` when the level never returns to the peak within
    the segment. Like the maximum drawdown, it's dated by its segment's first and last levels."""
    if len(levels) < 2:
        return unavailable("too_few_observations", len(levels))
    if found.peak is None or found.trough is None:
        return Calculated(None, "not_applicable", len(levels))
    peak = levels[found.peak]
    for at in range(found.trough + 1, len(levels)):
        if levels[at] >= peak:
            return Calculated(dates[at], None, len(levels), (dates[0], dates[-1]))
    return Calculated(None, "not_recovered", len(levels))


def _longest(levels: Sequence[Decimal], dates: Sequence[date]) -> Calculated:
    """The longest time below a peak, in calendar days: from the date before a run of levels below
    their running peak, the last at that peak, to the first date after it at or above the peak,
    or the segment's last date, flagged `not_recovered`; the earliest on a tie; 0, with no dates,
    when the level is never below its running peak."""
    if len(levels) < 2:
        return unavailable("too_few_observations", len(levels))
    longest: tuple[int, int, bool] | None = None
    peak = levels[0]
    start: int | None = None
    for at, level in enumerate(levels):
        if level >= peak:
            if start is not None:
                longest = _longer(longest, (start, at, False), dates)
                start = None
            peak = level
        elif start is None:
            start = at - 1
    if start is not None:
        longest = _longer(longest, (start, len(levels) - 1, True), dates)
    if longest is None:
        return Calculated(0, None, len(levels))
    first, last, unrecovered = longest
    days = days_between(dates[first], dates[last])
    return Calculated(days, None, len(levels), (dates[first], dates[last]), unrecovered)


def _longer(
    longest: tuple[int, int, bool] | None, run: tuple[int, int, bool], dates: Sequence[date]
) -> tuple[int, int, bool]:
    """The longer of two times below a peak, the earlier on a tie."""
    if longest is None:
        return run
    length = days_between(dates[run[0]], dates[run[1]])
    return run if length > days_between(dates[longest[0]], dates[longest[1]]) else longest
