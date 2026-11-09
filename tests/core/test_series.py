"""The series table: `series.csv`'s rows from a saved response, each daily level and each period's
return as the response holds it, with its date, its source location, its provenance, and the
response's digits; and each change to the response, unavailable with the reason its rule gives.

Traces, at the core, to R05-AC01 (the series table holds every daily level and every period's
return the response holds) and R05-AC02 (a response without usable daily levels, or without period
rows, says which is unavailable and why); and to docs/contracts.md, series.csv (its rows, when the
daily series can be read, the period series, and reading it). Each response is a fixture's bytes,
read as the core reads a saved `response.json`, with `hand-checkable.yaml`'s dates.
"""

import json
from dataclasses import dataclass, replace
from datetime import date

import pytest

from tests.support.hand_checkable import LABEL, artifact_id, tables_of
from tests.support.long_response import long_response
from tests.support.paths import RESPONSES
from trialfolio.contracts.tables import SeriesRow
from trialfolio.errors import TrialFolioError
from trialfolio.tables import read_series_csv, series_csv

EXAMPLE = (RESPONSES / "hand-checkable.json").read_bytes()

DATES = (
    "2024-01-01",
    "2024-01-02",
    "2024-01-03",
    "2024-01-04",
    "2024-01-05",
    "2024-01-08",
    "2024-01-09",
    "2024-01-10",
    "2024-01-11",
    "2024-01-12",
)
STRATEGY = ("100", "102", "101", "104", "99", "100", "103", "105", "102", "110")
BENCHMARK = ("100", "101", "101", "102", "100", "101", "102", "103", "102", "101")


@dataclass(frozen=True)
class Cells:
    """A row's cells, as the test writes them."""

    series: str
    subject: str
    date: str | None
    period_start: str | None
    value: str | None
    unit: str
    source_decimals: int | None
    reason: str | None
    source_label: str
    source_location: str | None


def cells(row: SeriesRow) -> Cells:
    return Cells(
        row.series,
        row.subject,
        None if row.date is None else row.date.isoformat(),
        None if row.period_start is None else row.period_start.isoformat(),
        row.value,
        row.unit,
        row.source_decimals,
        row.unavailable_reason,
        row.source_label,
        row.source_location,
    )


def level(subject: str, at: int, value: str) -> Cells:
    source = "screenReturns" if subject == "strategy" else "benchReturns"
    return Cells(
        "daily", subject, DATES[at], None, value, "index", 0, None, source, f"chart.{source}[{at}]"
    )


EXAMPLE_LEVELS = tuple(
    cell
    for at in range(10)
    for cell in (level("strategy", at, STRATEGY[at]), level("benchmark", at, BENCHMARK[at]))
)
"""The example's 20 daily rows: for each date, the strategy's level, then the benchmark's, as the
response's text gives it."""

_SOURCES = (("strategy", "Ret%", 9), ("benchmark", "Bench%", 10), ("excess", "Excess%", 11))


def returns(
    row: int, dates: tuple[str | None, str], values: tuple[str, str, str]
) -> tuple[Cells, ...]:
    """A period's three rows: its `Tran Dt` and `End Dt`, its values, and its row's position in
    `results.rows`, whose columns `Ret%`, `Bench%`, and `Excess%` are the 10th to 12th."""
    start, end = dates
    return tuple(
        Cells(
            "period",
            subject,
            end,
            start,
            value,
            "percent",
            len(value.partition(".")[2]),
            None,
            label,
            f"results.rows[{row}][{column}]",
        )
        for (subject, label, column), value in zip(_SOURCES, values, strict=True)
    )


FIRST_PERIOD = returns(1, ("2024-01-01", "2024-01-08"), ("0", "1", "-1"))
SECOND_PERIOD = returns(0, ("2024-01-08", "2024-01-12"), ("10", "0", "10"))
EXAMPLE_PERIODS = (*FIRST_PERIOD, *SECOND_PERIOD)
"""The example's 6 period rows, earliest first, though `results.rows` gives them newest first."""


def series_of(name: str) -> tuple[SeriesRow, ...]:
    return tables_of(name).series


def test_the_example_gives_every_level_and_return_as_its_response_holds_them() -> None:
    rows = series_of("hand-checkable.json")

    assert tuple(cells(row) for row in rows) == (*EXAMPLE_LEVELS, *EXAMPLE_PERIODS)
    assert {(row.availability, row.origin, row.provenance) for row in rows} == {
        ("available", "reported", "verified")
    }
    assert {(row.label, row.source_artifact) for row in rows} == {(LABEL, artifact_id(EXAMPLE))}


def test_a_period_keeps_its_own_excess() -> None:
    """`hand-checkable-variant.json`'s second period's `Excess%` is one unit of its last digit
    from `Ret%` minus `Bench%`, and the table holds it as reported, never calculated again
    (D-47)."""
    rows = series_of("hand-checkable-variant.json")

    second = [row for row in rows if row.series == "period" and str(row.date) == "2024-01-12"]
    assert [(row.subject, row.value) for row in second] == [
        ("strategy", "-0.9901"),
        ("benchmark", "0"),
        ("excess", "-0.99"),
    ]


def test_the_long_response_gives_a_row_for_each_level_and_each_period() -> None:
    rows = tables_of(long_response(), "formula.yaml").series

    daily = [row for row in rows if row.series == "daily"]
    periods = [row for row in rows if row.series == "period"]
    assert (len(daily), len(periods)) == (5218, 393)
    assert all(row.availability == "available" for row in rows)
    starts = [row.period_start for row in periods[::3] if row.period_start is not None]
    assert len(starts) == 131
    assert starts == sorted(starts)
    assert starts[0] == date(2016, 1, 1)


DAILY_CHANGES = {
    "no-chart": "blank_in_source",
    "chart-without-dates": "blank_in_source",
    "chart-not-object": "unparseable_in_source",
    "chart-not-parallel": "unparseable_in_source",
    "chart-bad-date": "unparseable_in_source",
    "chart-date-repeated": "unparseable_in_source",
    "chart-level-zero": "unparseable_in_source",
    "chart-level-string": "unparseable_in_source",
    "chart-not-at-100": "unparseable_in_source",
    "chart-gap": "not_daily",
    "chart-weekend": "not_daily",
    "chart-short": "not_daily",
    "chart-faults": "blank_in_source",
}
"""Each change to the daily series, and the reason its rule gives, the first that applies:
`chart-faults` lacks `benchReturns` and has a date that can't be read."""


@pytest.mark.parametrize(("change", "reason"), DAILY_CHANGES.items(), ids=DAILY_CHANGES)
def test_a_chart_that_cant_be_read_gives_two_unavailable_rows(change: str, reason: str) -> None:
    rows = series_of(f"hand-checkable-{change}.json")

    unavailable = tuple(
        Cells("daily", subject, None, None, None, "index", None, reason, source, None)
        for subject, source in (("strategy", "screenReturns"), ("benchmark", "benchReturns"))
    )
    assert tuple(cells(row) for row in rows) == (*unavailable, *EXAMPLE_PERIODS)


def _no_period() -> tuple[Cells, ...]:
    return tuple(
        Cells("period", subject, None, None, None, "percent", None, "blank_in_source", label, None)
        for subject, label, _ in _SOURCES
    )


def _changed(period: tuple[Cells, ...], subject: str, **changes: object) -> tuple[Cells, ...]:
    """A period's rows, with one subject's cells changed."""
    return tuple(replace(row, **changes) if row.subject == subject else row for row in period)


def _blank(period: tuple[Cells, ...], subject: str, reason: str) -> tuple[Cells, ...]:
    """A period's rows, with one subject's value unavailable, its location kept."""
    return _changed(period, subject, value=None, source_decimals=None, reason=reason)


def _without_column(period: tuple[Cells, ...]) -> tuple[Cells, ...]:
    """A period's rows without `Excess%` among the columns: its excess unavailable, with its
    dates, and no location."""
    return _changed(_blank(period, "excess", "blank_in_source"), "excess", source_location=None)


def _unplaced(period: tuple[Cells, ...]) -> tuple[Cells, ...]:
    """A period whose `Tran Dt` can't be read: its cell empty, and its three values
    `unparseable_in_source`, since they can't be placed in time."""
    return tuple(
        replace(
            row, period_start=None, value=None, source_decimals=None, reason="unparseable_in_source"
        )
        for row in period
    )


PERIOD_CHANGES = {
    "no-periods": _no_period(),
    "no-end-column": _no_period(),
    "no-excess-column": (*_without_column(FIRST_PERIOD), *_without_column(SECOND_PERIOD)),
    "period-null": (*_blank(FIRST_PERIOD, "strategy", "blank_in_source"), *SECOND_PERIOD),
    "period-not-a-number": (
        *FIRST_PERIOD,
        *_blank(SECOND_PERIOD, "benchmark", "unparseable_in_source"),
    ),
    # The second period, first in `results.rows`, comes after every period whose `Tran Dt` can be
    # read.
    "period-bad-date": (*FIRST_PERIOD, *_unplaced(SECOND_PERIOD)),
}
"""Each change to the period series, and its period rows."""


@pytest.mark.parametrize(("change", "periods"), PERIOD_CHANGES.items(), ids=PERIOD_CHANGES)
def test_a_period_that_cant_be_read_is_unavailable_with_its_reason(
    change: str, periods: tuple[Cells, ...]
) -> None:
    rows = series_of(f"hand-checkable-{change}.json")

    assert tuple(cells(row) for row in rows) == (*EXAMPLE_LEVELS, *periods)


def test_a_value_is_read_from_its_text_in_plain_notation() -> None:
    """A JSON number with an exponent is written in plain notation, with the digits that gives,
    and one with a decimal point keeps its digits, trailing zeros included."""
    response = json.loads(EXAMPLE)
    response["results"]["rows"][0][9] = 1e-05
    response["chart"]["screenReturns"][1] = 102.5
    text = json.dumps(response, indent=2)
    assert text.count("102.5,") == 1
    read = tables_of(text.replace("102.5,", "102.50,").encode()).series

    located = {(row.source_location, row.value, row.source_decimals) for row in read}
    assert ("chart.screenReturns[1]", "102.50", 2) in located
    assert ("results.rows[0][9]", "0.00001", 5) in located


def test_a_response_without_the_required_structure_has_no_series() -> None:
    content = (RESPONSES / "invalid-structure.json").read_bytes()

    with pytest.raises(TrialFolioError) as raised:
        tables_of(content)

    assert raised.value.code == "provider.response_invalid"


def test_the_table_reads_back_as_it_was_written() -> None:
    rows = series_of("hand-checkable-period-bad-date.json")

    assert read_series_csv(series_csv(rows), "series.csv") == rows


def test_an_available_value_without_its_date_isnt_a_table() -> None:
    written = series_csv(series_of("hand-checkable.json")).decode()
    header, first, *rest = written.splitlines(keepends=True)
    broken = header + first.replace("2024-01-01", "", 1) + "".join(rest)

    with pytest.raises(TrialFolioError) as raised:
        read_series_csv(broken.encode(), "series.csv")

    assert raised.value.code == "input.not_a_run"
    assert "line 2" in str(raised.value)


def test_a_period_whose_end_cant_be_read_keeps_its_start() -> None:
    """The first period's `End Dt` is 2024-01-32: its `date` is empty, its `period_start` kept,
    and its three values `unparseable_in_source`, since they can't be placed in time."""
    response = json.loads(EXAMPLE)
    response["results"]["rows"][1][4] = "2024-01-32"
    rows = tables_of(json.dumps(response).encode()).series

    first = tuple(
        replace(row, date=None, value=None, source_decimals=None, reason="unparseable_in_source")
        for row in FIRST_PERIOD
    )
    assert tuple(cells(row) for row in rows) == (*EXAMPLE_LEVELS, *first, *SECOND_PERIOD)
