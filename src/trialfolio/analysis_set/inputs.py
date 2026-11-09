"""The analysis set's inputs: a result's `series.csv` rows, read as its daily levels and its
periods, and its `metrics.csv` coverage and reported metrics (methodology.md, inputs;
docs/contracts.md, analysis.csv).

`read_result` reads them. The daily levels are unavailable when its two daily rows are, since a
level is never unavailable on its own; the periods are unavailable when the result has no period,
the three period rows `series.csv` gives a result without one. Each value is its decimal, read
from the table's text, never from a binary float.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final, Literal

from trialfolio.contracts.tables import MetricsRow, SeriesRow

type LevelSubject = Literal["strategy", "benchmark"]
type PeriodSubject = Literal["strategy", "benchmark", "excess"]

RECONCILED_METRICS: Final = ("total_return", "annualized_return", "max_drawdown")
"""The metrics the analysis set reconciles, each `metrics.csv`'s by its `metric_id`."""


@dataclass(frozen=True)
class Levels:
    """The daily levels of 100 invested, on the `chart` dates t₀ to t_N."""

    dates: tuple[date, ...]
    values: Mapping[LevelSubject, tuple[Decimal, ...]]
    decimals: Mapping[LevelSubject, tuple[int, ...]]
    """Each level's decimal places, as saved, which its rounding is read from."""


@dataclass(frozen=True)
class Period:
    """One rebalance period: its `Tran Dt` and `End Dt`, where they can be read, and each
    subject's return in percent, None where it's unavailable."""

    start: date | None
    end: date | None
    returns: Mapping[PeriodSubject, Decimal | None]


@dataclass(frozen=True)
class Result:
    """What the analysis set reads of one result."""

    label: str
    source_artifact: str
    levels: Levels | None
    """None when the daily series is unavailable."""
    periods: tuple[Period, ...] | None
    """In `series.csv`'s order, earliest `Tran Dt` first; None when the result has no period."""
    coverage: tuple[date, date] | None
    """`coverage_start` and `coverage_end`, C₀ and C₁, from `metrics.csv`; None when either is
    unavailable."""
    reported: Mapping[tuple[str, LevelSubject], str | None]
    """Each reconciled metric's `value`, as `metrics.csv` writes it, by its `metric_id` and
    subject; None when it's unavailable."""


def read_result(series: Sequence[SeriesRow], metrics: Sequence[MetricsRow]) -> Result:
    """One result's inputs, from its `series.csv` and `metrics.csv` rows, both in their tables'
    order. Raises `ValueError` when the series' rows aren't one result's, in that order."""
    if not series:
        raise ValueError("a result's series.csv has its daily and period rows")
    first = series[0]
    if any(
        (row.label, row.source_artifact) != (first.label, first.source_artifact) for row in series
    ):
        raise ValueError("the series' rows are one result's, from one response")
    daily = [row for row in series if row.series == "daily"]
    period = [row for row in series if row.series == "period"]
    return Result(
        label=first.label,
        source_artifact=first.source_artifact,
        levels=_levels(daily),
        periods=_periods(period),
        coverage=_coverage(metrics),
        reported=_reported(metrics),
    )


def _levels(rows: Sequence[SeriesRow]) -> Levels | None:
    if any(row.value is None for row in rows):
        return None
    strategy, benchmark = rows[0::2], rows[1::2]
    if len(strategy) != len(benchmark) or any(
        (s.subject, b.subject, s.date) != ("strategy", "benchmark", b.date)
        for s, b in zip(strategy, benchmark, strict=True)
    ):
        raise ValueError("each date's daily rows are the strategy's, then the benchmark's")
    return Levels(
        dates=tuple(_known(row.date) for row in strategy),
        values={
            "strategy": tuple(Decimal(_known(row.value)) for row in strategy),
            "benchmark": tuple(Decimal(_known(row.value)) for row in benchmark),
        },
        decimals={
            "strategy": tuple(_known(row.source_decimals) for row in strategy),
            "benchmark": tuple(_known(row.source_decimals) for row in benchmark),
        },
    )


def _periods(rows: Sequence[SeriesRow]) -> tuple[Period, ...] | None:
    if len(rows) % 3 or any(
        row.subject != subject
        for row, subject in zip(rows, ("strategy", "benchmark", "excess") * (len(rows) // 3))
    ):
        raise ValueError("each period's rows are the strategy's, the benchmark's, and the excess")
    groups = [rows[at : at + 3] for at in range(0, len(rows), 3)]
    if len(groups) == 1 and all(_without_a_period(row) for row in groups[0]):
        return None
    return tuple(
        Period(
            start=group[0].period_start,
            end=group[0].date,
            returns={
                "strategy": _return(group[0]),
                "benchmark": _return(group[1]),
                "excess": _return(group[2]),
            },
        )
        for group in groups
    )


def _without_a_period(row: SeriesRow) -> bool:
    """A row of a result without a period: no date, value, or source, and blank in the source."""
    return (row.date, row.period_start, row.source_location, row.unavailable_reason) == (
        None,
        None,
        None,
        "blank_in_source",
    )


def _return(row: SeriesRow) -> Decimal | None:
    return None if row.value is None else Decimal(row.value)


def _coverage(metrics: Sequence[MetricsRow]) -> tuple[date, date] | None:
    values = {row.metric_id: row.value for row in metrics if row.subject == "strategy"}
    start, end = values.get("coverage_start"), values.get("coverage_end")
    if start is None or end is None:
        return None
    return (date.fromisoformat(start), date.fromisoformat(end))


def _reported(metrics: Sequence[MetricsRow]) -> dict[tuple[str, LevelSubject], str | None]:
    reported: dict[tuple[str, LevelSubject], str | None] = {}
    for row in metrics:
        if row.metric_id in RECONCILED_METRICS:
            reported[(row.metric_id, row.subject)] = row.value
    return reported


def _known[T](value: T | None) -> T:
    if value is None:
        raise ValueError("an available level gives its date, value, and decimals")
    return value
