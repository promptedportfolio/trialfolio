"""The reconciliation with Portfolio123's metrics: over the `full` segment, `total_return`,
`annualized_return`, and `max_drawdown`, for the strategy and the benchmark, each beside the
metric `metrics.csv` gives with the same `metric_id` and subject (methodology.md, reconciliation
with Portfolio123's metrics).

`reconciled` says whether the reported value agrees: whether it's within the range that the
rounding of the recalculated value's inputs allows, widened by its own rounding. Each level is
read as rounded to half a unit of its last digit, the request's `precision` or its own decimals
where it has more, and so is the reported value; L₀ is 100, as the layout gives it. When either
value is unavailable, the pair is `not_compared` (D-48).
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Literal

from trialfolio.analysis_set.arithmetic import HUNDRED, Calculated, days_between, percent
from trialfolio.analysis_set.daily_levels import drawdown, span_levels
from trialfolio.analysis_set.inputs import LevelSubject
from trialfolio.analysis_set.segments import LevelSpan

type Reconciliation = Literal["agrees", "differs", "not_compared"]

_YEAR = Decimal("365.25")


def reconciled(
    analysis: str,
    subject: LevelSubject,
    recalculated: Calculated,
    reported: str | None,
    span: LevelSpan | None,
    precision: int,
) -> Reconciliation:
    """Whether `reported`, Portfolio123's value of `analysis` for `subject`, as `metrics.csv`
    writes it, agrees with the recalculated value from the `full` segment's levels, `span`."""
    if recalculated.value is None or reported is None or span is None:
        return "not_compared"
    low, high = _range(analysis, subject, span, precision)
    value = Decimal(reported)
    half = _half_unit(_places(reported), precision)
    return "agrees" if low - half <= value <= high + half else "differs"


def _range(
    analysis: str, subject: LevelSubject, span: LevelSpan, precision: int
) -> tuple[Decimal, Decimal]:
    levels = span_levels(span, subject)
    halves = [
        _half_unit(places, precision)
        for places in span.levels.decimals[subject][span.first : span.last + 1]
    ]
    last, half = levels[-1], halves[-1]
    if analysis == "total_return":
        return (last - half - HUNDRED, last + half - HUNDRED)
    if analysis == "annualized_return":
        exponent = _YEAR / days_between(span.dates[0], span.dates[-1])
        return (
            percent(((last - half) / HUNDRED) ** exponent),
            percent(((last + half) / HUNDRED) ** exponent),
        )
    return _drawdown_range(levels, halves)


def _drawdown_range(
    levels: Sequence[Decimal], halves: Sequence[Decimal]
) -> tuple[Decimal, Decimal]:
    """A range that holds the exact maximum drawdown: its low, the smallest of
    ((L_j − h_j) / max(Lᵢ + hᵢ, for i ≤ j) − 1) × 100, every trough as low as its rounding allows
    against every earlier level as high; and its high, the smaller of 0 and
    ((L_t + h_t) / (L_p − h_p) − 1) × 100, the recalculated drawdown's own trough and peak, the
    other way."""
    low = Decimal(0)
    highest: Decimal | None = None
    for level, half in zip(levels, halves, strict=True):
        highest = level + half if highest is None else max(highest, level + half)
        low = min(low, percent((level - half) / highest))
    found = drawdown(levels)
    if found.peak is None or found.trough is None:
        return (low, Decimal(0))
    peak, trough = found.peak, found.trough
    high = percent((levels[trough] + halves[trough]) / (levels[peak] - halves[peak]))
    return (low, min(Decimal(0), high))


def _places(text: str) -> int:
    return len(text.partition(".")[2])


def _half_unit(places: int, precision: int) -> Decimal:
    """Half a unit of a value's last digit: at the request's `precision`, since saving drops only
    trailing zeros, or at its own decimals, where it has more."""
    return Decimal(5).scaleb(-max(places, precision) - 1)
