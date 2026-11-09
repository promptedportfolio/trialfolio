"""The segments: the `full` segment, and the split segments the declared dates divide the coverage
into, each with its first and last dates, its levels, its periods, and whether it's available
(methodology.md, segments).

`segments` gives a result's, `full` first, then `split-0` to `split-k`:

- **The coverage,** C₀ and C₁, is the result's `coverage_start` and `coverage_end`, or, when
  either is unavailable, its first and last `chart` dates; the segments' periods aren't known
  then, so a split segment's values from them are unavailable. Without the daily levels too,
  every split segment is unavailable.
- **Outside the coverage,** `split-0` is unavailable when d₁ is before C₀, `split-k` when d_k is
  after C₁, and a segment between two declared dates unless the coverage reaches both, so none
  is shortened to the part the coverage reaches.
- **A segment's levels** run from the latest `chart` date on or before its first date to the
  latest on or before its last, so the level that ends one segment begins the next; a segment
  whose dates the `chart` doesn't reach is unavailable.
- **A segment's periods** are those wholly within it, and a period that spans one of its declared
  dates is in neither segment beside it, which each counts.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from trialfolio.analysis_set.arithmetic import HUNDRED, days_between
from trialfolio.analysis_set.inputs import Levels, Period, Result
from trialfolio.contracts.common import AnalysisUnavailableReason


@dataclass(frozen=True)
class LevelSpan:
    """A segment's levels: positions `first` to `last` of the result's levels, both included."""

    levels: Levels
    first: int
    last: int

    @property
    def count(self) -> int:
        return self.last - self.first + 1

    @property
    def dates(self) -> tuple[date, ...]:
        return self.levels.dates[self.first : self.last + 1]


@dataclass(frozen=True)
class Segment:
    """One segment of a result, as the analysis set calculates over it."""

    name: str
    """`full`, or `split-<n>`."""
    reason: AnalysisUnavailableReason | None = None
    """Why the whole segment is unavailable, with every value of it; None when it's available."""
    levels: LevelSpan | None = None
    """None when the daily series is unavailable."""
    periods: tuple[Period, ...] | None = None
    """The periods wholly within it, in order; None when they aren't known."""
    first: date | None = None
    last: date | None = None
    """A split segment's own first and last dates."""
    share: Decimal | None = None
    """A split segment's `coverage_share`, in percent; None when C₀ and C₁ are the same date."""
    spanning: int | None = None
    """The periods that span one of a split segment's declared dates; None when the periods
    aren't known."""
    all_periods: int | None = None
    """The result's periods, every one of which is checked for whether it spans; None when they
    aren't known."""


def segments(result: Result, splits: Sequence[date]) -> tuple[Segment, ...]:
    """The `full` segment, then each split segment the declared dates `splits`, in increasing
    order, give."""
    full = Segment(
        name="full",
        levels=_span_all(result.levels),
        periods=result.periods,
    )
    if not splits:
        return (full,)
    return (full, *_split_segments(result, splits))


def _span_all(levels: Levels | None) -> LevelSpan | None:
    return None if levels is None else LevelSpan(levels, 0, len(levels.dates) - 1)


def _split_segments(result: Result, splits: Sequence[date]) -> tuple[Segment, ...]:
    coverage = result.coverage
    if coverage is None and result.levels is not None:
        coverage = (result.levels.dates[0], result.levels.dates[-1])
    names = [f"split-{n}" for n in range(len(splits) + 1)]
    if coverage is None:
        return tuple(Segment(name, reason="input_unavailable") for name in names)
    periods = result.periods if result.coverage is not None else None
    return tuple(
        _split_segment(result, names[n], n, splits, coverage, periods) for n in range(len(names))
    )


def _split_segment(
    result: Result,
    name: str,
    n: int,
    splits: Sequence[date],
    coverage: tuple[date, date],
    periods: tuple[Period, ...] | None,
) -> Segment:
    start, end = coverage
    declared = splits[max(n - 1, 0) : n + 1]
    first = start if n == 0 else max(splits[n - 1], start) if n == len(splits) else splits[n - 1]
    last = min(splits[0], end) if n == 0 else end if n == len(splits) else splits[n]
    if not start <= first <= last <= end or not _reaches(result.levels, first):
        return Segment(name, reason="outside_coverage", first=first, last=last)
    total = days_between(start, end)
    return Segment(
        name=name,
        levels=_span(result.levels, first, last),
        periods=None if periods is None else _within(periods, n, splits),
        first=first,
        last=last,
        share=None if total == 0 else Decimal(days_between(first, last)) * HUNDRED / total,
        spanning=None if periods is None else sum(_spans(period, declared) for period in periods),
        all_periods=None if periods is None else len(periods),
    )


def _reaches(levels: Levels | None, first: date) -> bool:
    """Whether the `chart` reaches a segment that starts on `first`: a `chart` date is on or
    before it. Without levels, nothing is read from them."""
    return levels is None or levels.dates[0] <= first


def _span(levels: Levels | None, first: date, last: date) -> LevelSpan | None:
    """The levels from the latest `chart` date on or before `first` to the latest on or before
    `last`; None without levels."""
    if levels is None:
        return None
    starting = max(at for at, day in enumerate(levels.dates) if day <= first)
    ending = max(at for at, day in enumerate(levels.dates) if day <= last)
    return LevelSpan(levels, starting, ending)


def _within(periods: Sequence[Period], n: int, splits: Sequence[date]) -> tuple[Period, ...]:
    """The periods wholly within segment `n`: `split-0`'s end on or before d₁, `split-k`'s start
    on or after d_k, and each other's start on or after its first declared date and end on or
    before its second."""
    after = splits[n - 1] if n > 0 else None
    before = splits[n] if n < len(splits) else None
    return tuple(
        period
        for period in periods
        if (after is None or _known(period.start) >= after)
        and (before is None or _known(period.end) <= before)
    )


def _spans(period: Period, declared: Sequence[date]) -> bool:
    """Whether a period starts before one of the declared dates and ends after it."""
    return any(_known(period.start) < day < _known(period.end) for day in declared)


def _known(day: date | None) -> date:
    # The periods are known only when the coverage is available, which needs every date.
    if day is None:
        raise ValueError("a period of a known coverage has both its dates")
    return day
