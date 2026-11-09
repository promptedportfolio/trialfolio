"""The period-return analyses, over a segment's periods (methodology.md, period-return analyses).

`period_values` gives each of a segment's values from its periods, by analysis and subject. A
value of a subject needs every one of the segment's periods to have that subject's return:
otherwise it's unavailable, with `input_unavailable`, and no period is left out. Its observations
are n, the segment's periods, and with fewer than it needs, it's unavailable with
`too_few_observations`. The standard deviation is the sample's, per rebalance period, not
annualized, and the information ratio and the t-value are descriptive.
"""

from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal

from trialfolio.analysis_set.arithmetic import HUNDRED, Calculated, covering, unavailable
from trialfolio.analysis_set.inputs import Period, PeriodSubject
from trialfolio.analysis_set.segments import Segment

type Key = tuple[str, PeriodSubject | None]
type Dates = tuple[date, date] | None

_SUBJECTS: tuple[PeriodSubject, ...] = ("strategy", "benchmark", "excess")


def period_values(segment: Segment) -> dict[Key, Calculated]:
    """Each of `segment`'s values from its periods: in a split segment `coverage_share` and
    `spanning_period_count`, and in every segment `period_count`, each subject's mean, median,
    best, and worst, and the excess's own analyses."""
    values: dict[Key, Calculated] = {}
    split = segment.name != "full"
    if split:
        values[("coverage_share", None)] = _share(segment)
    periods = segment.periods
    counts: list[Key] = [("period_count", None), ("spanning_period_count", None)]
    summaries: list[Key] = [(name, subject) for name in _SUMMARIES for subject in _SUBJECTS]
    of_excess: list[Key] = [(name, "excess") for name in _EXCESS]
    keys = [*counts[: 2 if split else 1], *summaries, *of_excess]
    if periods is None:
        values.update(dict.fromkeys(keys, unavailable("input_unavailable")))
        return values
    dates = _summary_dates(periods)
    values[("period_count", None)] = Calculated(len(periods), None, len(periods), dates)
    if split:
        own = covering(segment.first, segment.last)
        values[("spanning_period_count", None)] = Calculated(
            segment.spanning, None, segment.all_periods, own
        )
    for subject in _SUBJECTS:
        returns = [period.returns[subject] for period in periods]
        for name, summary in _SUMMARIES.items():
            values[(name, subject)] = _summarized(summary, returns, periods, dates)
    excess = [period.returns["excess"] for period in periods]
    for name, statistic in _EXCESS.items():
        values[(name, "excess")] = _of_excess(statistic, excess, dates)
    return values


def _share(segment: Segment) -> Calculated:
    """A split segment's `coverage_share`, from dates alone, so without observations: dated by
    the segment's own first and last dates, or `not_applicable` when C₀ and C₁ are the same
    date."""
    if segment.share is None:
        return Calculated(None, "not_applicable")
    return Calculated(segment.share, dates=covering(segment.first, segment.last))


def _summary_dates(periods: Sequence[Period]) -> Dates:
    """A summary's dates: the earliest `Tran Dt` and the latest `End Dt` of the segment's
    periods, when they're known, and none when it has none. When the coverage is unavailable,
    a period's date can't be read, or the earliest `Tran Dt` is after the latest `End Dt`, so the
    `full` segment's values from its periods give none."""
    if not periods:
        return None
    starts = [period.start for period in periods]
    ends = [period.end for period in periods]
    if None in starts or None in ends:
        return None
    return covering(min(day for day in starts if day), max(day for day in ends if day))


def median(values: Sequence[Decimal]) -> Decimal:
    """The middle value of the sorted values, or the mean of the two middle values when there's
    an even number of them."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal(0)) / len(values)


_SUMMARIES: dict[str, Callable[[list[Decimal]], tuple[Decimal, int | None]]] = {
    "mean_period_return": lambda returns: (_mean(returns), None),
    "median_period_return": lambda returns: (median(returns), None),
    # max and min give the first of equal values, so the earliest period on a tie.
    "best_period_return": lambda returns: (
        max(returns),
        max(range(len(returns)), key=returns.__getitem__),
    ),
    "worst_period_return": lambda returns: (
        min(returns),
        min(range(len(returns)), key=returns.__getitem__),
    ),
}
"""Each subject's summaries, in the rows' order: each one's value, and for the best and the worst,
the position of the period whose return it is, which dates it."""


def _summarized(
    summary: Callable[[list[Decimal]], tuple[Decimal, int | None]],
    returns: Sequence[Decimal | None],
    periods: Sequence[Period],
    dates: Dates,
) -> Calculated:
    known = [value for value in returns if value is not None]
    if len(known) < len(returns):
        return unavailable("input_unavailable")
    if not known:
        return unavailable("too_few_observations", 0)
    value, at = summary(known)
    if at is not None:
        dates = covering(periods[at].start, periods[at].end)
    return Calculated(value, None, len(known), dates)


def _positive_share(excess: list[Decimal]) -> Calculated:
    """The share of periods whose excess is above 0, times 100: an excess of 0 isn't positive."""
    return Calculated(Decimal(sum(value > 0 for value in excess)) * HUNDRED / len(excess))


def _deviation(excess: list[Decimal]) -> Decimal:
    """The sample standard deviation of the excess, √(Σ(eᵢ − ē)² / (n − 1))."""
    mean = _mean(excess)
    squares = sum(((value - mean) ** 2 for value in excess), Decimal(0))
    return (squares / (len(excess) - 1)).sqrt()


def _tracking_error(excess: list[Decimal]) -> Calculated:
    if len(excess) < 2:
        return unavailable("too_few_observations", len(excess))
    return Calculated(_deviation(excess))


def _ratio(excess: list[Decimal], *, t_value: bool) -> Calculated:
    """The mean excess per unit of tracking error, ē / s; or the t-value of the mean excess,
    ē / (s / √n), the information ratio times √n. With a tracking error of 0, it's
    `not_applicable`."""
    n = len(excess)
    if n < 2:
        return unavailable("too_few_observations", n)
    deviation = _deviation(excess)
    if deviation.is_zero():
        return Calculated(None, "not_applicable", n)
    ratio = _mean(excess) / deviation
    return Calculated(ratio * Decimal(n).sqrt() if t_value else ratio)


_EXCESS: dict[str, Callable[[list[Decimal]], Calculated]] = {
    "positive_excess_share": _positive_share,
    "tracking_error": _tracking_error,
    "information_ratio": lambda excess: _ratio(excess, t_value=False),
    "excess_t_value": lambda excess: _ratio(excess, t_value=True),
}
"""The excess's own analyses, in the rows' order. Each gives its value alone, or why it's
unavailable, with its observations."""


def _of_excess(
    statistic: Callable[[list[Decimal]], Calculated],
    excess: Sequence[Decimal | None],
    dates: Dates,
) -> Calculated:
    known = [value for value in excess if value is not None]
    if len(known) < len(excess):
        return unavailable("input_unavailable")
    if not known:
        return unavailable("too_few_observations", 0)
    calculated = statistic(known)
    if calculated.value is None:
        return calculated
    return Calculated(calculated.value, None, len(known), dates)
