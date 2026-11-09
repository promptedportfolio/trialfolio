"""The analysis set's arithmetic: decimal, never binary floating point, with 50 significant digits,
rounded half to even, and each value rounded once, at the end (methodology.md, arithmetic and
digits).

`CONTEXT` is the context every calculation runs in, which `analysis_rows` enters once for a
result. `Calculated` is one value before it's written: the exact decimal, a whole number, or a
date, or why it's unavailable, with its observations and dates. `rounded` rounds a decimal to a
number of places, and `written` writes it, a zero without a sign.
"""

from dataclasses import dataclass
from datetime import date
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
)
from typing import Final

from trialfolio.contracts.common import AnalysisUnavailableReason

CONTEXT: Final = Context(
    prec=50, rounding=ROUND_HALF_EVEN, traps=[InvalidOperation, DivisionByZero, Overflow]
)
"""50 significant digits, half to even, as R05-T01's checks used; a square root and a power with
a fractional exponent are `decimal`'s own, at this precision."""

HUNDRED: Final = Decimal(100)


@dataclass(frozen=True)
class Calculated:
    """One value of the analysis set, before it's rounded and written, or why it's unavailable."""

    value: Decimal | int | date | None
    """The exact decimal of a value in percent, percentage points, or a ratio; a whole number of
    a count or of days; or a date. None when unavailable."""
    reason: AnalysisUnavailableReason | None = None
    observations: int | None = None
    """The periods, levels, or windows behind it, or, when there were too few, the number there
    were. None when an input is unavailable."""
    dates: tuple[date, date] | None = None
    """The first and last dates it covers, as the analysis set gives them; None where it gives
    none."""
    not_recovered: bool = False
    """A time below a peak that runs to the segment's last date (`longest_drawdown_days`)."""


def unavailable(reason: AnalysisUnavailableReason, observations: int | None = None) -> Calculated:
    """A value that's unavailable, with the observations there were where the reason gives them,
    such as too few; none for an input that's unavailable."""
    return Calculated(None, reason, observations)


def covering(first: date | None, last: date | None) -> tuple[date, date] | None:
    """A value's dates, from its inputs' first and last: none when either isn't known, or when they
    run backwards, from a period whose `Tran Dt` is after its `End Dt`, since a value's dates
    never do."""
    if first is None or last is None or first > last:
        return None
    return (first, last)


def rounded(value: Decimal, places: int) -> Decimal:
    """`value` rounded once, half to even, to `places` decimals, and a zero without its sign."""
    result = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN, context=CONTEXT)
    return result.copy_abs() if result.is_zero() else result


def written(value: Decimal, places: int) -> str:
    """`value` as `analysis.csv` writes it: rounded to `places` decimals, in plain notation, with
    exactly that many digits after its point, and a zero without a sign: `0.0000`, never
    `-0.0000`."""
    return format(rounded(value, places), "f")


def percent(ratio: Decimal) -> Decimal:
    """The return of a ratio of two levels, in percent: (ratio − 1) × 100."""
    return (ratio - 1) * HUNDRED


def days_between(first: date, last: date) -> int:
    """The calendar days from `first` to `last`."""
    return (last - first).days
