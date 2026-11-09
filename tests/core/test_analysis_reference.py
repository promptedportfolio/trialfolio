"""The independent reference calculation, `tests/support/reference_analysis.py`: it gives each of
the example's values as the test writes them, and `four-years.json`'s annualized returns and
their difference; and it agrees with Trial Folio's: exactly, at each value's digits, on the
hand-checkable example, on those annualized returns, and on every other hand-checkable fixture,
and on the long response within one unit of each value's last digit, 0.0001 at the precision of
4, while counts, days, dates, observations, availability, and reason codes agree exactly
everywhere.

Traces, at the core, to R05-AC03 (each value agrees with an independent reference calculation)
and to the open question of how closely they must agree, whose default the owner confirmed at the
sign-off; and to methodology.md, verification of statistical methods. The long response, whose
ten years have windows of every length, checks the windows of 30 days or more, which no
hand-checkable fixture has. The demo's response is R05-T11's case.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from tests.support.hand_checkable import (
    EXAMPLE_FULL,
    EXAMPLE_SPLIT,
    Expected,
    analysed,
    splits_of,
)
from tests.support.long_response import END, START, long_response
from tests.support.paths import RESPONSES
from tests.support.reference_analysis import Expected as Reference
from tests.support.reference_analysis import reference
from trialfolio.contracts.tables import AnalysisRow

_PRECISION = 4
_ONE_UNIT = Decimal("0.0001")
_HAND_CHECKABLE = (date(2024, 1, 1), date(2024, 1, 12))


def text(value: float | date | None, unit: str) -> str | None:
    """A reference value at `analysis.csv`'s digits: a float rounded to 4 decimals, a zero without
    a sign; a whole number as its digits; a date as a date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if unit in ("count", "days"):
        return str(value)
    written = f"{value:.{_PRECISION}f}"
    return "0.0000" if written == "-0.0000" else written


def as_written(key: tuple[str, str, str | None, int | None], ref: Reference, unit: str) -> Expected:
    _, analysis, subject, window = key
    available = ref.value is not None
    flags = ("not_recovered",) if ref.not_recovered and available else ()
    return Expected(
        analysis,
        subject,
        window,
        text(ref.value, unit),
        unit,
        None if not available or unit == "date" else (0 if unit in ("count", "days") else 4),
        ref.observations,
        None if ref.start is None or not available else ref.start.isoformat(),
        None if ref.end is None or not available else ref.end.isoformat(),
        ref.reason,
        flags,
    )


def _without_named_flags(expected: Expected) -> Expected:
    """A row with only the flag a value gives, `not_recovered`: the reference doesn't name an
    analysis's own flags, `descriptive` and `overlapping_windows`, which aren't calculated."""
    return replace(
        expected, flags=tuple(flag for flag in expected.flags if flag == "not_recovered")
    )


def references(
    response: bytes, start: date, end: date, splits: tuple[date, ...]
) -> dict[tuple[str, str, str | None, int | None], Reference]:
    return reference(response, start=start, end=end, splits=splits)


def test_the_reference_gives_each_of_the_examples_values() -> None:
    content = (RESPONSES / "hand-checkable.json").read_bytes()
    refs = references(content, *_HAND_CHECKABLE, (date(2024, 1, 5),))

    for segment, rows in (("full", EXAMPLE_FULL), *EXAMPLE_SPLIT.items()):
        for row in rows:
            key = (segment, row.analysis, row.subject, row.window_days)
            assert as_written(key, refs[key], row.unit) == _without_named_flags(row), key


def test_the_reference_gives_four_years_annualized_returns() -> None:
    content = (RESPONSES / "four-years.json").read_bytes()
    refs = references(content, date(2020, 1, 1), date(2024, 1, 1), ())

    for subject, value in (("strategy", "10.0000"), ("benchmark", "-10.0000")):
        ref = refs[("full", "annualized_return", subject, None)]
        assert (text(ref.value, "percent"), ref.observations) == (value, 1044)
        assert (ref.start, ref.end) == (date(2020, 1, 1), date(2024, 1, 1))
    difference = refs[("full", "annualized_return_difference", "excess", None)]
    assert text(difference.value, "pp") == "20.0000"


def agreement(
    rows: tuple[AnalysisRow, ...],
    refs: dict[tuple[str, str, str | None, int | None], Reference],
    *,
    exactly: bool,
) -> list[str]:
    """Each disagreement between Trial Folio's rows and the reference's: a row the other hasn't,
    or a value, a reason, observations, or dates that differ. A decimal value agrees exactly, at
    its digits, when `exactly`, and otherwise within one unit of its last digit."""
    problems: list[str] = []
    keys = {(row.segment, row.analysis, row.subject, row.window_days) for row in rows}
    if keys != set(refs):
        problems.append(f"rows differ: {sorted(map(str, keys ^ set(refs)))[:3]}")
    for row in rows:
        key = (row.segment, row.analysis, row.subject, row.window_days)
        ref = refs.get(key)
        if ref is None:
            continue
        expected = as_written(key, ref, row.unit)
        if (row.unavailable_reason, row.observations) != (expected.reason, expected.observations):
            problems.append(f"{key}: {row.unavailable_reason}, {row.observations}")
        dates = (
            None if row.period_start is None else row.period_start.isoformat(),
            None if row.period_end is None else row.period_end.isoformat(),
        )
        if dates != (expected.start, expected.end):
            problems.append(f"{key}: dates {dates}")
        if not _same_value(row, ref, expected, exactly=exactly):
            problems.append(f"{key}: {row.value} against {ref.value}")
    return problems


def _same_value(row: AnalysisRow, ref: Reference, expected: Expected, *, exactly: bool) -> bool:
    if row.value is None or ref.value is None or row.unit not in ("percent", "pp", "ratio"):
        return row.value == expected.value
    if exactly:
        return row.value == expected.value
    return abs(Decimal(row.value) - Decimal(repr(ref.value))) <= _ONE_UNIT


EXAMPLE_CONFIGS = (
    "hand-checkable.yaml",
    "hand-checkable-split.yaml",
    "hand-checkable-split-sunday.yaml",
)


@pytest.mark.parametrize("config", EXAMPLE_CONFIGS)
def test_the_reference_agrees_exactly_on_the_example(config: str) -> None:
    content = (RESPONSES / "hand-checkable.json").read_bytes()

    rows = analysed(content, config)
    refs = references(content, *_HAND_CHECKABLE, splits_of(config))
    assert agreement(rows, refs, exactly=True) == []


def test_the_reference_agrees_exactly_on_four_years() -> None:
    content = (RESPONSES / "four-years.json").read_bytes()

    rows = analysed(content, "four-years.yaml")
    refs = references(content, date(2020, 1, 1), date(2024, 1, 1), ())
    assert agreement(rows, refs, exactly=True) == []


@pytest.mark.parametrize("splits", [(), (date(2019, 12, 31), date(2022, 6, 30))], ids=["", "split"])
def test_the_reference_agrees_on_the_long_response(splits: tuple[date, ...]) -> None:
    """The long response's ten years have windows of every length, so each window of 30 days or
    more is checked against the reference, which no hand-checkable fixture's are."""
    content = long_response()
    rows = analysed(content, "formula.yaml", splits)
    refs = references(content, START, END, splits)

    assert agreement(rows, refs, exactly=False) == []
    available = {row.window_days for row in rows if row.window_days and row.value is not None}
    assert available == {7, 30, 90, 180, 365}


WITH_A_DAILY_CHART = (
    ("hand-checkable-differs.json", "hand-checkable.yaml"),
    ("hand-checkable-variant.json", "hand-checkable-split.yaml"),
    ("hand-checkable-four-weekly.json", "hand-checkable-split.yaml"),
    ("hand-checkable-late-start.json", "hand-checkable-split.yaml"),
    ("hand-checkable-flat.json", "hand-checkable.yaml"),
    ("hand-checkable-canaries.json", "hand-checkable.yaml"),
    ("hand-checkable-no-periods.json", "hand-checkable-split.yaml"),
    ("hand-checkable-no-end-column.json", "hand-checkable.yaml"),
    ("hand-checkable-no-excess-column.json", "hand-checkable.yaml"),
    ("hand-checkable-period-null.json", "hand-checkable.yaml"),
    ("hand-checkable-period-not-a-number.json", "hand-checkable.yaml"),
    ("hand-checkable-period-bad-date.json", "hand-checkable-split.yaml"),
    ("hand-checkable.json", "hand-checkable-split-edges.yaml"),
    ("hand-checkable.json", "hand-checkable-split-before.yaml"),
    ("hand-checkable.json", "hand-checkable-split-after.yaml"),
    ("one-date.json", "one-date.yaml"),
)
"""Each other response the test pairing names with a daily `chart`, with a configuration that
reads it, and each configuration with splits of the example's. No value of theirs is a tie at
half a unit of its last digit, where a float could round either way, so they agree exactly."""


@pytest.mark.parametrize(("response", "config"), WITH_A_DAILY_CHART)
def test_the_reference_agrees_exactly_on_each_response_with_a_daily_chart(
    response: str, config: str
) -> None:
    content = (RESPONSES / response).read_bytes()
    start, end = (
        (date(2024, 1, 5), date(2024, 1, 6)) if response == "one-date.json" else _HAND_CHECKABLE
    )

    rows = analysed(content, config)
    refs = references(content, start, end, splits_of(config))
    assert agreement(rows, refs, exactly=True) == []


@pytest.mark.parametrize("change", ["no-chart", "chart-gap", "chart-not-at-100"])
def test_the_reference_agrees_without_usable_daily_levels(change: str) -> None:
    content = (RESPONSES / f"hand-checkable-{change}.json").read_bytes()

    rows = analysed(content, "hand-checkable-split.yaml")
    refs = references(content, *_HAND_CHECKABLE, (date(2024, 1, 5),))
    assert agreement(rows, refs, exactly=True) == []
