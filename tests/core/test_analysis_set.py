"""Analysis set 1.0.0: each value of methodology.md's hand-checkable example, as `analysis.csv`
writes it, with its unit, decimals, observations, dates, and flags; each row calculated, with
its method, the set's version, its inputs, and the Trial Folio version; and a result without
usable daily levels, or without period rows, with each value that needs them unavailable, and
the others given.

Traces, at the core, to R05-AC02 (each analysis that needs an unavailable series is unavailable
with `input_unavailable`, and no unavailable value is written as zero) and R05-AC03 (each value
agrees with a hand-checkable fixture, the rolling windows' counts included, and records that it's
calculated, with its method, the set's version, and the Trial Folio version); to
docs/contracts.md, analysis.csv (its rows, and reading it); and to methodology.md's analysis set
1.0.0, whose rules for a tie, for windows that overlap, for the rolling values' dates, and for the
50 significant digits are checked with values written by hand, since the reference calculation
follows the same rules. The example's values are written by hand in
`tests/support/hand_checkable.py`, from methodology.md's tables.
"""

import json
from dataclasses import replace
from datetime import date
from importlib.metadata import version

import pytest

from tests.support.hand_checkable import (
    EXAMPLE_FULL,
    EXAMPLE_SPLIT,
    LABEL,
    Expected,
    analysed,
    artifact_id,
    written,
)
from tests.support.paths import RESPONSES
from trialfolio.analysis_set import analysis_rows
from trialfolio.contracts.tables import ANALYSIS_SET_1_0_0, AnalysisRow
from trialfolio.errors import TrialFolioError
from trialfolio.normalization import metrics_rows, read_response, series_rows
from trialfolio.tables import analysis_csv, read_analysis_csv

EXAMPLE = (RESPONSES / "hand-checkable.json").read_bytes()
FULL = ("2024-01-01", "2024-01-12")
"""The example's first and last dates."""


def by_place(
    rows: tuple[AnalysisRow, ...],
) -> dict[tuple[str, str, str | None, int | None], Expected]:
    return {(row.segment, row.analysis, row.subject, row.window_days): written(row) for row in rows}


def test_the_example_gives_each_value_of_its_full_segment() -> None:
    rows = analysed("hand-checkable.json")

    assert tuple(written(row) for row in rows) == EXAMPLE_FULL
    assert {row.segment for row in rows} == {"full"}


def test_the_example_split_gives_each_value_of_its_segments() -> None:
    rows = analysed("hand-checkable.json", "hand-checkable-split.yaml")

    assert [row.segment for row in rows] == ["full"] * 94 + ["split-0"] * 31 + ["split-1"] * 31
    assert tuple(written(row) for row in rows) == (
        *EXAMPLE_FULL,
        *EXAMPLE_SPLIT["split-0"],
        *EXAMPLE_SPLIT["split-1"],
    )


def test_a_split_on_a_sunday_changes_only_the_segments_own_dates() -> None:
    """Declared on Sunday, 2024-01-07, the split gives the same values from the levels and the
    periods, with the same dates: only `coverage_share`, 6 days of 11 and 5, and the dates of it
    and of `spanning_period_count` change."""
    rows = analysed("hand-checkable.json", "hand-checkable-split-sunday.yaml")

    own = {
        ("split-0", "coverage_share"): ("54.5455", "2024-01-01", "2024-01-07"),
        ("split-0", "spanning_period_count"): ("1", "2024-01-01", "2024-01-07"),
        ("split-1", "coverage_share"): ("45.4545", "2024-01-07", "2024-01-12"),
        ("split-1", "spanning_period_count"): ("1", "2024-01-07", "2024-01-12"),
    }
    expected = [
        replace(
            row,
            value=own[(segment, row.analysis)][0],
            start=own[(segment, row.analysis)][1],
            end=own[(segment, row.analysis)][2],
        )
        if (segment, row.analysis) in own
        else row
        for segment in ("split-0", "split-1")
        for row in EXAMPLE_SPLIT[segment]
    ]
    assert [written(row) for row in rows[94:]] == expected


def test_flat_levels_have_no_drawdown_and_no_ratio() -> None:
    """Every level 100, and every return 0: a `max_drawdown` of 0, without dates, whose recovery
    is `not_applicable`, and a tracking error of 0, so the information ratio and the t-value are
    `not_applicable`."""
    values = by_place(analysed("hand-checkable-flat.json"))

    for subject in ("strategy", "benchmark"):
        assert values[("full", "max_drawdown", subject, None)] == Expected(
            "max_drawdown", subject, None, "0.0000", "percent", 4, 10
        )
        assert values[("full", "max_drawdown_recovery", subject, None)] == Expected(
            "max_drawdown_recovery", subject, None, None, "date", None, 10, reason="not_applicable"
        )
        assert values[("full", "longest_drawdown_days", subject, None)] == Expected(
            "longest_drawdown_days", subject, None, "0", "days", 0, 10
        )
    assert values[("full", "tracking_error", "excess", None)].value == "0.0000"
    for analysis in ("information_ratio", "excess_t_value"):
        assert values[("full", analysis, "excess", None)] == Expected(
            analysis,
            "excess",
            None,
            None,
            "ratio",
            None,
            2,
            reason="not_applicable",
            flags=("descriptive",),
        )


def test_a_tie_is_the_earliest_period_and_isnt_above_zero() -> None:
    """Every return 0: an excess of 0 isn't positive, so `positive_excess_share` is 0; each best
    and worst return is the earliest period's, 2024-01-01 to 2024-01-08, though `results.rows`
    gives it second; and in each 7-day window the strategy's return ties the benchmark's, which
    isn't beating."""
    values = by_place(analysed("hand-checkable-flat.json"))

    assert values[("full", "positive_excess_share", "excess", None)] == Expected(
        "positive_excess_share", "excess", None, "0.0000", "percent", 4, 2, *FULL
    )
    for analysis in ("best_period_return", "worst_period_return"):
        for subject in ("strategy", "benchmark", "excess"):
            assert values[("full", analysis, subject, None)] == Expected(
                analysis, subject, None, "0.0000", "percent", 4, 2, "2024-01-01", "2024-01-08"
            )
    assert values[("full", "rolling_share_beating", "excess", 7)] == Expected(
        "rolling_share_beating",
        "excess",
        7,
        "0.0000",
        "percent",
        4,
        5,
        *FULL,
        flags=("overlapping_windows",),
    )


def test_an_annualized_return_over_four_years() -> None:
    """((146.41 / 100)^(365.25 / 1,461) − 1) × 100 is 10, since 1.4641 is 1.1 to the 4th, and
    the benchmark's, from 65.61, 0.9 to the 4th, −10, each over 1,044 levels; years of 365 days
    would give the strategy 9.9928."""
    values = by_place(analysed("four-years.json", "four-years.yaml"))

    dates = ("2020-01-01", "2024-01-01")
    assert values[("full", "annualized_return", "strategy", None)] == Expected(
        "annualized_return", "strategy", None, "10.0000", "percent", 4, 1044, *dates
    )
    assert values[("full", "annualized_return", "benchmark", None)] == Expected(
        "annualized_return", "benchmark", None, "-10.0000", "percent", 4, 1044, *dates
    )
    assert values[("full", "annualized_return_difference", "excess", None)] == Expected(
        "annualized_return_difference", "excess", None, "20.0000", "pp", 4, 1044, *dates
    )


def test_a_window_that_starts_where_another_ends_doesnt_overlap_it() -> None:
    """`four-years.json`'s 7-day windows end on each of its 1,044 weekdays but the 5 before
    2020-01-08, so there are 1,039. Counted from the earliest, the windows without overlap are
    the one from Wednesday 2020-01-01 to 2020-01-08, then each starting on the Wednesday the last
    one ended, one a week, to the one ending on 2023-12-27: 208."""
    values = by_place(analysed("four-years.json", "four-years.yaml"))

    assert values[("full", "rolling_non_overlapping_count", None, 7)] == Expected(
        "rolling_non_overlapping_count",
        None,
        7,
        "208",
        "count",
        0,
        1039,
        "2020-01-01",
        "2024-01-01",
    )


FIRST_WINDOWS_FROM_A_MONDAY = {
    7: date(2020, 1, 6),
    30: date(2020, 1, 6),
    90: date(2020, 1, 7),
    180: date(2020, 1, 8),
    365: date(2020, 1, 6),
}
"""The start of each length's first window, from Monday 2020-01-06: 90 days after it is a
Sunday, so the first 90-day window ends on Monday 2020-04-06, and starts 90 days before, on
Tuesday 2020-01-07; 180 days after it is a Saturday, so the first 180-day window ends on Monday
2020-07-06, and starts on Wednesday 2020-01-08. The others start on 2020-01-06."""


def test_a_rolling_value_is_dated_from_its_first_windows_start() -> None:
    """`four-years.json` from Monday 2020-01-06, without its first three weekdays, whose levels
    are all 100: each rolling value is dated from its first window's start to its last window's
    end, 2024-01-01, so the 90-day and the 180-day ones start after the first level."""
    response = json.loads((RESPONSES / "four-years.json").read_bytes())
    chart = response["chart"]
    for key in chart:
        chart[key] = chart[key][3:]
    assert (chart["dates"][0], chart["screenReturns"][0], chart["benchReturns"][0]) == (
        "2020-01-06",
        100,
        100,
    )
    rows = analysed_over(json.dumps(response).encode(), date(2020, 1, 6), date(2024, 1, 1))

    rolling = [row for row in rows if row.window_days is not None]
    assert len(rolling) == 5 * 13
    assert {(row.window_days, row.period_start, row.period_end) for row in rolling} == {
        (length, start, date(2024, 1, 1)) for length, start in FIRST_WINDOWS_FROM_A_MONDAY.items()
    }


def test_every_row_records_how_it_was_calculated() -> None:
    rows = analysed("hand-checkable.json", "hand-checkable-split.yaml")

    assert {
        (row.label, row.analysis_set, row.origin, row.provenance, row.trialfolio_version)
        for row in rows
    } == {(LABEL, "1.0.0", "calculated", "inferred", version("trialfolio"))}
    assert {row.source_artifact for row in rows} == {artifact_id(EXAMPLE)}
    inputs = {(row.analysis, row.subject): row.inputs for row in rows}
    assert inputs[("coverage_share", None)] == ()
    assert inputs[("period_count", None)] == ("period",)
    assert inputs[("spanning_period_count", None)] == ("period",)
    assert inputs[("mean_period_return", "excess")] == ("period/excess",)
    assert inputs[("total_return", "benchmark")] == ("daily/benchmark",)
    assert inputs[("total_return_difference", "excess")] == ("daily/strategy", "daily/benchmark")
    assert inputs[("rolling_window_count", None)] == ("daily",)
    assert inputs[("rolling_share_beating", "excess")] == ("daily/strategy", "daily/benchmark")
    assert not [row.value for row in rows if row.value is not None and row.value.startswith("-0.0")]


def test_a_value_that_rounds_to_zero_has_no_sign() -> None:
    """With the first period's `Excess%` −0.0001 and the second's 0, the excess's mean is −0.00005,
    which rounds half to even to zero at 4 decimals, and is written `0.0000`, never `-0.0000`,
    though `decimal` keeps the sign; the worst period's −0.0001 keeps its own."""
    response = json.loads(EXAMPLE)
    rows = response["results"]["rows"]
    rows[1][11], rows[0][11] = -0.0001, 0
    values = by_place(analysed(json.dumps(response).encode()))

    assert values[("full", "mean_period_return", "excess", None)].value == "0.0000"
    assert values[("full", "median_period_return", "excess", None)].value == "0.0000"
    assert values[("full", "worst_period_return", "excess", None)].value == "-0.0001"


def test_a_value_is_calculated_with_50_significant_digits() -> None:
    """A trough of 98.99994000000000000000000000000104 after the peak of 104 is a decline of
    (98.99994000000000000000000000000104 / 104 − 1) × 100, −4.807749999999999999999999999999,
    just above −4.80775, so −4.8077 at 4 decimals. The quotient,
    0.95192250000000000000000000000001, takes 32 significant digits: at `decimal`'s default of 28,
    it's 0.9519225, and the decline −4.80775, which rounds half to even to −4.8078."""
    trough = "98.99994000000000000000000000000104"
    response = json.loads(EXAMPLE)
    response["chart"]["screenReturns"][4] = 12345.5
    text = json.dumps(response)
    assert text.count("12345.5") == 1
    values = by_place(analysed(text.replace("12345.5", trough).encode()))

    assert values[("full", "max_drawdown", "strategy", None)] == Expected(
        "max_drawdown", "strategy", None, "-4.8077", "percent", 4, 10, "2024-01-04", "2024-01-05"
    )


DAILY_UNAVAILABLE = ("no-chart", "chart-not-parallel", "chart-gap")


@pytest.mark.parametrize("change", DAILY_UNAVAILABLE)
def test_without_usable_daily_levels_each_value_from_them_is_unavailable(change: str) -> None:
    rows = analysed(f"hand-checkable-{change}.json", "hand-checkable-split.yaml")

    for row, expected in zip(
        rows, (*EXAMPLE_FULL, *EXAMPLE_SPLIT["split-0"], *EXAMPLE_SPLIT["split-1"]), strict=True
    ):
        series = ANALYSIS_SET_1_0_0[row.analysis].series
        if series == "daily":
            assert (row.availability, row.unavailable_reason, row.observations) == (
                "unavailable",
                "input_unavailable",
                None,
            ), row.analysis
            assert row.value is None
        else:
            assert written(row) == expected


@pytest.mark.parametrize("change", ["no-periods", "no-end-column"])
def test_without_period_rows_each_value_from_them_is_unavailable(change: str) -> None:
    """Each period value is unavailable with `input_unavailable`, and the daily levels' values are
    given, the split segments' too, since the coverage is then the first and last `chart`
    dates."""
    rows = analysed(f"hand-checkable-{change}.json", "hand-checkable-split.yaml")

    for row, expected in zip(
        rows, (*EXAMPLE_FULL, *EXAMPLE_SPLIT["split-0"], *EXAMPLE_SPLIT["split-1"]), strict=True
    ):
        if row.analysis == "coverage_share":
            assert written(row) == expected
        elif ANALYSIS_SET_1_0_0[row.analysis].series == "period":
            assert (row.value, row.unavailable_reason, row.observations) == (
                None,
                "input_unavailable",
                None,
            ), (row.segment, row.analysis)
        else:
            assert written(row) == expected


def test_a_period_date_that_cant_be_read_leaves_the_counts_without_dates() -> None:
    """The coverage is unavailable, so the `full` segment's `period_count` is given without dates,
    and each value of a subject, whose period can't be placed in time, is `input_unavailable`."""
    values = by_place(analysed("hand-checkable-period-bad-date.json"))

    assert values[("full", "period_count", None, None)] == Expected(
        "period_count", None, None, "2", "count", 0, 2
    )
    for subject in ("strategy", "benchmark", "excess"):
        assert values[("full", "mean_period_return", subject, None)].reason == "input_unavailable"
    assert values[("full", "total_return", "strategy", None)].value == "10.0000"


def test_a_missing_return_leaves_out_no_period() -> None:
    """The first period's `Ret%` is `null`, so each strategy value from the periods is
    unavailable, rather than calculated from the second alone, and the benchmark's are given."""
    values = by_place(analysed("hand-checkable-period-null.json"))

    for analysis in ("mean_period_return", "best_period_return"):
        assert values[("full", analysis, "strategy", None)].reason == "input_unavailable"
        assert values[("full", analysis, "excess", None)].value is not None
    assert values[("full", "mean_period_return", "benchmark", None)].value == "0.5000"


def test_no_unavailable_value_is_written_as_zero() -> None:
    for change in ("no-chart", "no-periods", "period-null", "chart-gap"):
        lines = analysis_csv(analysed(f"hand-checkable-{change}.json")).decode().splitlines()
        header = lines[0].split(",")
        value, availability = header.index("value"), header.index("availability")
        for line in lines[1:]:
            cells = line.split(",")
            if cells[availability] == "unavailable":
                assert cells[value] == "", line


def test_the_table_reads_back_as_it_was_written() -> None:
    rows = analysed("hand-checkable.json", "hand-checkable-split.yaml")

    content = analysis_csv(rows)
    assert read_analysis_csv(content, "analysis.csv") == rows
    assert b',"[""daily/strategy"", ""daily/benchmark""]",' in content
    assert b",[]," in content


@pytest.mark.parametrize(
    ("old", "new"),
    [(",10.0000,percent,4,", ",10.000,percent,4,"), (",1.0.0,full,", ",9.9.9,full,")],
    ids=["value-without-its-decimals", "unknown-analysis-set"],
)
def test_a_row_its_model_refuses_isnt_a_table(old: str, new: str) -> None:
    text = analysis_csv(analysed("hand-checkable.json")).decode()
    assert old in text

    with pytest.raises(TrialFolioError) as raised:
        read_analysis_csv(text.replace(old, new, 1).encode(), "analysis.csv")

    assert raised.value.code == "input.not_a_run"


def with_levels(strategy: list[float], benchmark: list[float] | None = None) -> bytes:
    """The example's response with its strategy's levels, and its benchmark's, changed."""
    response = json.loads(EXAMPLE)
    response["chart"]["screenReturns"] = strategy
    if benchmark is not None:
        response["chart"]["benchReturns"] = benchmark
    return json.dumps(response).encode()


def test_a_drawdown_is_dated_by_the_first_peak_and_the_first_trough() -> None:
    """The strategy reaches 102 on 2024-01-02, and again on 2024-01-04, then falls to 91.8 twice:
    the peak is the first date the level reached the peak it fell from, the trough the first date
    of the largest decline, and the recovery the first date back at the peak."""
    content = with_levels([100, 102, 101, 102, 91.8, 95, 91.8, 102, 103, 104])
    values = by_place(analysed(content))

    assert values[("full", "max_drawdown", "strategy", None)] == Expected(
        "max_drawdown", "strategy", None, "-10.0000", "percent", 4, 10, "2024-01-02", "2024-01-05"
    )
    assert values[("full", "max_drawdown_recovery", "strategy", None)].value == "2024-01-10"


def test_the_longest_time_below_a_peak_is_the_earliest_on_a_tie() -> None:
    """Levels of 100, 90, 100, 90, and 100 have two times below a peak, of 2 days each, the first
    from 2024-01-01 to 2024-01-03; each starts on the date before its run, the last at the peak."""
    content = with_levels([100, 90, 100, 90, 100, 100, 100, 100, 100, 100])
    values = by_place(analysed(content))

    assert values[("full", "longest_drawdown_days", "strategy", None)] == Expected(
        "longest_drawdown_days", "strategy", None, "2", "days", 0, 10, "2024-01-01", "2024-01-03"
    )


def test_a_difference_is_of_the_two_values_as_rounded() -> None:
    """The strategy's `total_return` of 0.00006 is 0.0001 at 4 decimals, and the benchmark's of
    0.00004 is 0.0000, so their difference is 0.0001, exact at their digits, where the difference
    calculated before rounding, 0.00002, would be 0.0000."""
    content = with_levels([100] * 9 + [100.00006], [100] * 9 + [100.00004])
    values = by_place(analysed(content))

    assert values[("full", "total_return", "strategy", None)].value == "0.0001"
    assert values[("full", "total_return", "benchmark", None)].value == "0.0000"
    assert values[("full", "total_return_difference", "excess", None)].value == "0.0001"


def test_a_period_whose_dates_run_backwards_gives_no_dates() -> None:
    """The second period's `Tran Dt`, 2024-01-13, is after its `End Dt`, so its best return, its
    own, gives no dates, since a value's dates never run backwards; the coverage, from the
    earliest `Tran Dt` to the latest `End Dt`, is still known."""
    response = json.loads(EXAMPLE)
    response["results"]["rows"][0][3] = "2024-01-13"
    values = by_place(analysed(json.dumps(response).encode()))

    best = values[("full", "best_period_return", "strategy", None)]
    assert (best.value, best.start, best.end) == ("10.0000", None, None)
    mean = values[("full", "mean_period_return", "strategy", None)]
    assert (mean.start, mean.end) == ("2024-01-01", "2024-01-12")


def analysed_over(content: bytes, start: date, end: date) -> tuple[AnalysisRow, ...]:
    """`content`'s `analysis.csv` rows, requested from `start` to `end`, with `four-years.yaml`'s
    other settings: the benchmark SPY, the precision 4, and no split."""
    source = artifact_id(content)
    series = series_rows(
        content,
        "response.json",
        label=LABEL,
        source_artifact=source,
        start_date=start,
        end_date=end,
    )
    metrics = metrics_rows(
        read_response(content, "response.json"),
        label=LABEL,
        benchmark="SPY",
        source_artifact=source,
    )
    return analysis_rows(
        series, metrics, precision=4, splits=(), trialfolio_version=version("trialfolio")
    )


@pytest.mark.parametrize(
    ("end", "annualized"), [(date(2020, 12, 31), "10.0000"), (date(2020, 12, 30), None)]
)
def test_an_annualized_return_needs_a_year_of_365_days(end: date, annualized: str | None) -> None:
    """From 2020-01-01, 2020-12-31 is 365 days later, enough for an annualized return, and
    2020-12-30, 364 days later, isn't: `too_short`."""
    response = json.loads((RESPONSES / "four-years.json").read_bytes())
    chart = response["chart"]
    count = sum(1 for day in chart["dates"] if date.fromisoformat(day) <= end)
    for key in chart:
        chart[key] = chart[key][:count]
    days = (end - date(2020, 1, 1)).days
    chart["screenReturns"][-1] = round(100 * 1.1 ** (days / 365.25), 4)
    rows = analysed_over(json.dumps(response).encode(), date(2020, 1, 1), end)

    value = by_place(rows)[("full", "annualized_return", "strategy", None)]
    assert (value.value, value.reason) == (annualized, None if annualized else "too_short")
