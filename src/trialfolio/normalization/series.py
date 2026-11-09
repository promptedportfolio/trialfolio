"""The series' rows: `series.csv`'s rows from a saved response read as `p123api-screen-backtest`
version 1 (docs/contracts.md, series.csv).

`series_rows` gives a result's daily rows, then its period rows:

- **The daily rows,** each `chart` level of the strategy and the benchmark, in `chart`'s order,
  read only when `chart` has the verified layout's form: its `dates`, `screenReturns`, and
  `benchReturns` arrays, the same length, the dates increasing calendar dates, exactly the
  weekdays from the case's `start_date` to its `end_date`, and the levels numbers above 0, each
  series starting at 100. Otherwise the result has two daily rows, unavailable with the first
  reason that applies: `blank_in_source`, `unparseable_in_source`, or `not_daily`.
- **The period rows,** each rebalance period's `Ret%`, `Bench%`, and `Excess%`, earliest
  `Tran Dt` first, whatever order `results.rows` gives them in, with a period whose `Tran Dt`
  can't be read after every one whose can, in the response's order. Without a period, or without
  `Tran Dt` or `End Dt` among the columns, the result has three period rows, unavailable with
  `blank_in_source`.

Each value is read from the saved text as a decimal, with the digits it has there, never as a
binary float, and none is calculated, filled in, or carried from another row. `turnoverPct` and
`positionCnt` aren't read, so they aren't checked.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Final, Literal, cast

from trialfolio.contracts.common import SeriesUnavailableReason
from trialfolio.contracts.tables import SeriesRow
from trialfolio.normalization.layout import (
    END_DATE,
    TRANSACTION_DATE,
    calendar_date,
    decode_response,
    number_text,
)

type SeriesSubject = Literal["strategy", "benchmark", "excess"]

_LEVELS: Final = (("strategy", "screenReturns"), ("benchmark", "benchReturns"))
"""Each daily series' subject and its array in `chart`, in the rows' order."""

_RETURNS: Final = (("strategy", "Ret%"), ("benchmark", "Bench%"), ("excess", "Excess%"))
"""Each period series' subject and its column in `results.rows`, in the rows' order."""

_START_LEVEL: Final = Decimal(100)
"""Every series of levels of 100 invested starts here (series.csv)."""


@dataclass(frozen=True)
class _Source:
    """What every row of one result shares."""

    label: str
    source_artifact: str


def series_rows(
    content: bytes,
    path: str,
    *,
    label: str,
    source_artifact: str,
    start_date: date,
    end_date: date,
) -> tuple[SeriesRow, ...]:
    """`series.csv`'s rows for one result, in order: its daily rows, then its period rows.

    `content` is the saved `response.json`, named by its `path` in messages; `label` is the case's
    `case_id`, and `source_artifact` the saved response's `artifact_id`. `start_date` and
    `end_date` are the case's settings, whose weekdays a `chart` must hold exactly.

    Raises `TrialFolioError` with `provider.response_invalid` when the response doesn't have the
    layout's required structure, as `metrics.csv` does: neither table is written then.
    """
    top = decode_response(content, path)
    source = _Source(label, source_artifact)
    results = cast("dict[str, object]", top["results"])
    columns = cast("list[str]", results["columns"])
    rows = cast("list[list[object]]", results["rows"])
    return (
        *_daily_rows(top.get("chart"), source, start_date, end_date),
        *_period_rows(columns, rows, source),
    )


def _daily_rows(
    chart: object, source: _Source, start_date: date, end_date: date
) -> tuple[SeriesRow, ...]:
    reason = _chart_reason(chart, start_date, end_date)
    if reason is not None:
        return tuple(
            _unavailable_level(subject, array, reason, source) for subject, array in _LEVELS
        )
    arrays = cast("dict[str, list[object]]", chart)
    dates = [cast("date", calendar_date(entry)) for entry in arrays["dates"]]
    rows: list[SeriesRow] = []
    for position, on in enumerate(dates):
        for subject, array in _LEVELS:
            text = cast("str", number_text(arrays[array][position]))
            rows.append(
                SeriesRow(
                    label=source.label,
                    series="daily",
                    subject=cast("SeriesSubject", subject),
                    date=on,
                    period_start=None,
                    value=text,
                    unit="index",
                    source_decimals=_decimals(text),
                    availability="available",
                    unavailable_reason=None,
                    origin="reported",
                    provenance="verified",
                    source_label=cast("Literal['screenReturns', 'benchReturns']", array),
                    source_artifact=source.source_artifact,
                    source_location=f"chart.{array}[{position}]",
                )
            )
    return tuple(rows)


def _chart_reason(
    chart: object, start_date: date, end_date: date
) -> SeriesUnavailableReason | None:
    """Why the daily series can't be read, the first of the three reasons that applies, or None
    when it can. A `chart`, or one of its arrays, that's `null` is missing, as a metric's `null`
    is."""
    if _missing(chart):
        return "blank_in_source"
    if not _readable(chart):
        return "unparseable_in_source"
    dates = [calendar_date(entry) for entry in cast("dict[str, list[object]]", chart)["dates"]]
    if dates != _weekdays(start_date, end_date):
        return "not_daily"
    return None


def _missing(chart: object) -> bool:
    """Whether there's no `chart`, or it lacks `dates`, `screenReturns`, or `benchReturns`."""
    if chart is None:
        return True
    if not isinstance(chart, dict):
        return False
    arrays = cast("dict[str, object]", chart)
    return any(arrays.get(key) is None for key in ("dates", "screenReturns", "benchReturns"))


def _readable(chart: object) -> bool:
    """Whether `chart`'s three arrays can be read: an object whose `dates`, `screenReturns`, and
    `benchReturns` are arrays of the same length, with calendar dates, each later than the one
    before, and levels that are numbers above 0, each series starting at 100. An empty array has
    no first level of 100."""
    if not isinstance(chart, dict):
        return False
    arrays = cast("dict[str, object]", chart)
    dates, *levels = (arrays[key] for key in ("dates", "screenReturns", "benchReturns"))
    if not all(isinstance(array, list) for array in (dates, *levels)):
        return False
    dates = cast("list[object]", dates)
    series = cast("list[list[object]]", levels)
    if any(len(array) != len(dates) for array in series) or not dates:
        return False
    read = [calendar_date(entry) for entry in dates]
    if None in read or any(
        later <= earlier
        for earlier, later in zip(cast("list[date]", read), cast("list[date]", read[1:]))
    ):
        return False
    for array in series:
        texts = [number_text(entry) for entry in array]
        if any(text is None or Decimal(text) <= 0 for text in texts):
            return False
        if Decimal(cast("str", texts[0])) != _START_LEVEL:
            return False
    return True


def _weekdays(start_date: date, end_date: date) -> list[date]:
    """Every weekday, Monday to Friday, from `start_date` to `end_date`, both included."""
    days = (start_date + timedelta(days) for days in range((end_date - start_date).days + 1))
    return [day for day in days if day.weekday() < 5]


def _unavailable_level(
    subject: str, array: str, reason: SeriesUnavailableReason, source: _Source
) -> SeriesRow:
    return SeriesRow(
        label=source.label,
        series="daily",
        subject=cast("SeriesSubject", subject),
        date=None,
        period_start=None,
        value=None,
        unit="index",
        source_decimals=None,
        availability="unavailable",
        unavailable_reason=reason,
        origin="reported",
        provenance="verified",
        source_label=cast("Literal['screenReturns', 'benchReturns']", array),
        source_artifact=source.source_artifact,
        source_location=None,
    )


@dataclass(frozen=True)
class _Period:
    """One row of `results.rows`, with its position, and its two dates where they can be read."""

    position: int
    row: Sequence[object]
    start: date | None
    end: date | None


def _period_rows(
    columns: Sequence[str], rows: Sequence[Sequence[object]], source: _Source
) -> tuple[SeriesRow, ...]:
    if not rows or TRANSACTION_DATE not in columns or END_DATE not in columns:
        return tuple(
            _period_row(source, subject, label, None, None, None, None, "blank_in_source")
            for subject, label in _RETURNS
        )
    starts, ends = columns.index(TRANSACTION_DATE), columns.index(END_DATE)
    periods = [
        _Period(position, row, calendar_date(row[starts]), calendar_date(row[ends]))
        for position, row in enumerate(rows)
    ]
    # Sorted by `Tran Dt`, earliest first; a period whose `Tran Dt` can't be read comes after
    # every one whose can, in the response's order, since the sort is stable.
    periods.sort(key=lambda period: (period.start is None, period.start or date.min))
    where = {label: columns.index(label) for _, label in _RETURNS if label in columns}
    return tuple(
        _period_value(source, period, subject, label, where.get(label))
        for period in periods
        for subject, label in _RETURNS
    )


def _period_value(
    source: _Source, period: _Period, subject: str, label: str, column: int | None
) -> SeriesRow:
    """A period's row for one subject: its value, or why it's unavailable. A missing column gives
    no value to place; a date that can't be read leaves the period's values unplaced in time; and
    otherwise the value is its own: `null` is blank, and anything but a JSON number can't be
    read."""
    if column is None:
        return _period_row(source, subject, label, period, None, None, None, "blank_in_source")
    location = f"results.rows[{period.position}][{column}]"
    cell = period.row[column]
    if period.start is None or period.end is None:
        reason: SeriesUnavailableReason = "unparseable_in_source"
        return _period_row(source, subject, label, period, location, None, None, reason)
    if cell is None:
        return _period_row(source, subject, label, period, location, None, None, "blank_in_source")
    text = number_text(cell)
    if text is None:
        reason = "unparseable_in_source"
        return _period_row(source, subject, label, period, location, None, None, reason)
    return _period_row(source, subject, label, period, location, text, _decimals(text), None)


def _period_row(
    source: _Source,
    subject: str,
    label: str,
    period: _Period | None,
    location: str | None,
    value: str | None,
    decimals: int | None,
    reason: SeriesUnavailableReason | None,
) -> SeriesRow:
    return SeriesRow(
        label=source.label,
        series="period",
        subject=cast("SeriesSubject", subject),
        date=None if period is None else period.end,
        period_start=None if period is None else period.start,
        value=value,
        unit="percent",
        source_decimals=decimals,
        availability="unavailable" if value is None else "available",
        unavailable_reason=reason,
        origin="reported",
        provenance="verified",
        source_label=cast("Literal['Ret%', 'Bench%', 'Excess%']", label),
        source_artifact=source.source_artifact,
        source_location=location,
    )


def _decimals(text: str) -> int:
    return len(text.partition(".")[2])
