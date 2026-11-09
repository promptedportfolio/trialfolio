"""The rolling returns, over the `full` segment's levels, for each window length of the analysis
set (methodology.md, rolling returns).

`rolling_values` gives each window length's values. A window ends at each `chart` date t_j, and
starts at the latest `chart` date on or before t_j − w days, so none is shorter than its length;
none ends less than w days after t₀. Each summary of the windows' returns is flagged as
overlapping, with its counts: the windows, and the most of them no two of which overlap, counted
from the earliest. Each is dated by the first window's start and the last window's end.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from trialfolio.analysis_set.arithmetic import HUNDRED, Calculated, percent, unavailable
from trialfolio.analysis_set.daily_levels import span_levels
from trialfolio.analysis_set.inputs import LevelSubject
from trialfolio.analysis_set.period_returns import median
from trialfolio.analysis_set.segments import LevelSpan

_SUBJECTS: tuple[LevelSubject, ...] = ("strategy", "benchmark")
_COUNTS = ("rolling_window_count", "rolling_non_overlapping_count")
_SUMMARIES = ("rolling_mean", "rolling_median", "rolling_p10", "rolling_p90", "rolling_worst")
_P10 = Decimal("0.1")
_P90 = Decimal("0.9")


def rolling_values(
    span: LevelSpan | None, windows: Sequence[int]
) -> dict[tuple[str, str | None, int], Calculated]:
    """Each value of the rolling returns, by analysis, subject, and window length: for each length
    in `windows`, the two counts, each summary of the strategy's and the benchmark's returns, and
    the excess's `rolling_share_beating`."""
    values: dict[tuple[str, str | None, int], Calculated] = {}
    for length in windows:
        keys = [(name, None, length) for name in _COUNTS]
        keys += [(name, subject, length) for name in _SUMMARIES for subject in _SUBJECTS]
        keys += [("rolling_share_beating", "excess", length)]
        if span is None:
            values.update(dict.fromkeys(keys, unavailable("input_unavailable")))
            continue
        values.update(_windows_values(span, length))
    return values


def windows_of(dates: Sequence[date], length: int) -> list[tuple[int, int]]:
    """Each window of `length` calendar days, as the positions of its first and last levels, in
    the order of their ends."""
    windows: list[tuple[int, int]] = []
    start = 0
    for end, day in enumerate(dates):
        earliest = day - timedelta(days=length)
        if earliest < dates[0]:
            continue
        while start + 1 < len(dates) and dates[start + 1] <= earliest:
            start += 1
        windows.append((start, end))
    return windows


def non_overlapping(windows: Sequence[tuple[int, int]]) -> int:
    """The most windows no two of which overlap, counted from the earliest: the window that ends
    first, then each, in the order of their ends, that starts on or after the end of the last one
    counted. A window that starts on the date another ends doesn't overlap it."""
    count = 0
    last_end: int | None = None
    for start, end in windows:
        if last_end is None or start >= last_end:
            count += 1
            last_end = end
    return count


def percentile(ordered: Sequence[Decimal], p: Decimal) -> Decimal:
    """The p-th percentile of sorted values x₍₀₎ to x₍ₘ₋₁₎, by linear interpolation: with
    h = (m − 1)p, x₍h₎ when h is a whole number, and otherwise
    x₍⌊h⌋₎ + (h − ⌊h⌋)(x₍⌊h⌋₊₁₎ − x₍⌊h⌋₎), Hyndman and Fan's definition 7. One value's
    percentiles are that value."""
    h = (len(ordered) - 1) * p
    below = int(h)
    fraction = h - below
    if fraction.is_zero():
        return ordered[below]
    return ordered[below] + fraction * (ordered[below + 1] - ordered[below])


def _windows_values(span: LevelSpan, length: int) -> dict[tuple[str, str | None, int], Calculated]:
    dates = span.dates
    windows = windows_of(dates, length)
    count = len(windows)
    covered = (dates[windows[0][0]], dates[windows[-1][1]]) if windows else None
    values: dict[tuple[str, str | None, int], Calculated] = {
        ("rolling_window_count", None, length): Calculated(count, None, count, covered),
        ("rolling_non_overlapping_count", None, length): Calculated(
            non_overlapping(windows), None, count, covered
        ),
    }
    returns: dict[LevelSubject, list[Decimal]] = {}
    for subject in _SUBJECTS:
        levels = span_levels(span, subject)
        returns[subject] = [percent(levels[end] / levels[start]) for start, end in windows]
    for subject in _SUBJECTS:
        for name, value in _summaries(returns[subject]).items():
            values[(name, subject, length)] = (
                Calculated(value, None, count, covered)
                if value is not None
                else unavailable("too_few_observations", 0)
            )
    beating = sum(
        strategy > benchmark
        for strategy, benchmark in zip(returns["strategy"], returns["benchmark"], strict=True)
    )
    values[("rolling_share_beating", "excess", length)] = (
        Calculated(Decimal(beating) * HUNDRED / count, None, count, covered)
        if count
        else unavailable("too_few_observations", 0)
    )
    return values


def _summaries(returns: Sequence[Decimal]) -> dict[str, Decimal | None]:
    """Each summary of the windows' returns, in the rows' order; None for each without a
    window."""
    if not returns:
        return dict.fromkeys(_SUMMARIES)
    ordered = sorted(returns)
    return {
        "rolling_mean": sum(returns, Decimal(0)) / len(returns),
        "rolling_median": median(returns),
        "rolling_p10": percentile(ordered, _P10),
        "rolling_p90": percentile(ordered, _P90),
        "rolling_worst": ordered[0],
    }
