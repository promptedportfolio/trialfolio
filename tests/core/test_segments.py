"""The split segments: each one's first and last dates, its `coverage_share`, and its
`spanning_period_count`; a declared date on the coverage's edge, within it, whose outer segment is
that one date; a date outside the coverage, whose segments the coverage doesn't reach, never
shortened to fit; a result without period rows, or with a coverage of one date; and the
segments' total returns, which compound to the whole.

Traces, at the core, to R05-AC08 (a split's values, with its dates and share of the coverage, and
a date outside a case's coverage flagged, with no window shortened to fit) and R05-AC02 (a result
without period rows keeps its split segments' analyses of its daily levels); and to
methodology.md, segments.
"""

import json
from datetime import date
from decimal import Decimal

import pytest

from tests.support.hand_checkable import Expected, analysed, written
from tests.support.paths import RESPONSES
from trialfolio.contracts.tables import ANALYSIS_SET_1_0_0, AnalysisRow

type Values = dict[tuple[str, str, str | None], Expected]


def values_of(rows: tuple[AnalysisRow, ...]) -> Values:
    return {
        (row.segment, row.analysis, row.subject): written(row)
        for row in rows
        if row.window_days is None
    }


def segment(rows: tuple[AnalysisRow, ...], name: str) -> list[AnalysisRow]:
    return [row for row in rows if row.segment == name]


def own_dates(values: Values, name: str) -> tuple[str | None, str | None, str | None, str | None]:
    """A split segment's `coverage_share` and `spanning_period_count`, with the segment's own
    dates."""
    share = values[(name, "coverage_share", None)]
    spanning = values[(name, "spanning_period_count", None)]
    assert (share.start, share.end) == (spanning.start, spanning.end)
    return (share.start, share.end, share.value, spanning.value)


def test_the_example_split_divides_the_coverage_at_its_date() -> None:
    values = values_of(analysed("hand-checkable.json", "hand-checkable-split.yaml"))

    assert own_dates(values, "split-0") == ("2024-01-01", "2024-01-05", "36.3636", "1")
    assert own_dates(values, "split-1") == ("2024-01-05", "2024-01-12", "63.6364", "1")


NEEDS_TWO_LEVELS = (
    "total_return",
    "annualized_return",
    "max_drawdown",
    "max_drawdown_recovery",
    "longest_drawdown_days",
)
NEEDS_A_PERIOD = (
    "mean_period_return",
    "median_period_return",
    "best_period_return",
    "worst_period_return",
    "positive_excess_share",
    "tracking_error",
    "information_ratio",
    "excess_t_value",
)


@pytest.mark.parametrize(
    ("name", "dates"),
    [("split-0", ("2024-01-01", "2024-01-01")), ("split-2", ("2024-01-12", "2024-01-12"))],
)
def test_a_date_on_the_coverages_edge_leaves_one_date_outside_it(
    name: str, dates: tuple[str, str]
) -> None:
    """Splits on 2024-01-01 and 2024-01-12, the coverage's first and last dates, are within it:
    the segment on each one's outer side is that one date, with a `coverage_share` of 0, one
    level, and no period, so each value that needs two levels or a period is
    `too_few_observations`."""
    rows = analysed("hand-checkable.json", "hand-checkable-split-edges.yaml")
    values = values_of(rows)

    assert own_dates(values, name) == (*dates, "0.0000", "0")
    assert values[(name, "period_count", None)].value == "0"
    for row in segment(rows, name):
        if row.analysis in NEEDS_TWO_LEVELS:
            assert (row.unavailable_reason, row.observations) == ("too_few_observations", 1)
        elif row.analysis in NEEDS_A_PERIOD:
            assert (row.unavailable_reason, row.observations) == ("too_few_observations", 0)
    assert own_dates(values, "split-1") == ("2024-01-01", "2024-01-12", "100.0000", "0")
    assert values[("split-1", "total_return", "strategy")].value == "10.0000"


def outside(rows: tuple[AnalysisRow, ...], name: str) -> bool:
    """Whether every row of a segment is unavailable, with `outside_coverage`."""
    return all(
        (row.value, row.unavailable_reason) == (None, "outside_coverage")
        for row in segment(rows, name)
    )


def test_a_date_before_the_coverage_isnt_shortened_to_fit() -> None:
    """Splits on 2023-12-29, before the coverage, and 2024-01-05: `split-0` is before the
    coverage, and `split-1`, from 2023-12-29 to 2024-01-05, is unavailable, rather than shortened
    to the part the coverage reaches; `split-2` holds what the coverage holds from 2024-01-05."""
    rows = analysed("hand-checkable.json", "hand-checkable-split-before.yaml")
    values = values_of(rows)

    assert outside(rows, "split-0")
    assert outside(rows, "split-1")
    assert len(segment(rows, "split-1")) == 31
    assert own_dates(values, "split-2") == ("2024-01-05", "2024-01-12", "63.6364", "1")
    assert values[("split-2", "total_return", "strategy")].value == "11.1111"


def test_a_date_after_the_coverage_isnt_shortened_to_fit() -> None:
    rows = analysed("hand-checkable.json", "hand-checkable-split-after.yaml")
    values = values_of(rows)

    assert own_dates(values, "split-0") == ("2024-01-01", "2024-01-05", "36.3636", "1")
    assert outside(rows, "split-1")
    assert outside(rows, "split-2")


def test_without_period_rows_the_segments_keep_their_daily_levels() -> None:
    """Without period rows, the coverage is the `chart`'s first and last dates, so the split
    segments' values from the levels are given, and their values from the periods,
    `period_count` and `spanning_period_count` included, are `input_unavailable`, since the
    segments' periods aren't known."""
    rows = analysed("hand-checkable-no-periods.json", "hand-checkable-split.yaml")
    values = values_of(rows)

    assert values[("split-0", "coverage_share", None)].value == "36.3636"
    for name in ("split-0", "split-1"):
        for row in segment(rows, name):
            if row.analysis == "coverage_share":
                continue
            if ANALYSIS_SET_1_0_0[row.analysis].series == "period":
                assert (row.value, row.unavailable_reason) == (None, "input_unavailable")
    assert values[("split-1", "total_return", "strategy")].value == "11.1111"
    assert values[("split-0", "max_drawdown", "benchmark")].value == "-1.9608"


def test_without_levels_or_periods_every_split_segment_is_unavailable() -> None:
    response = json.loads((RESPONSES / "hand-checkable-no-chart.json").read_bytes())
    response["results"]["rows"] = []
    rows = analysed(json.dumps(response).encode(), "hand-checkable-split.yaml")

    for name in ("split-0", "split-1"):
        assert all(
            (row.value, row.unavailable_reason) == (None, "input_unavailable")
            for row in segment(rows, name)
        )


def test_a_coverage_of_one_date_has_no_share() -> None:
    """`one-date.json` has one `chart` date, 2024-01-05, and no period, so the coverage is that
    date: each segment's `coverage_share` has no days to divide by, and is `not_applicable`."""
    values = values_of(analysed("one-date.json", "one-date.yaml"))

    for name in ("split-0", "split-1"):
        assert values[(name, "coverage_share", None)] == Expected(
            "coverage_share", None, None, None, "percent", None, None, reason="not_applicable"
        )
        assert values[(name, "total_return", "strategy")].reason == "too_few_observations"


def test_a_segment_the_chart_doesnt_reach_is_unavailable() -> None:
    """With the first period's `Tran Dt` 2023-12-29, the coverage starts before the `chart`, so
    `split-0`, from 2023-12-29, has no level on or before its first date."""
    response = json.loads((RESPONSES / "hand-checkable.json").read_bytes())
    response["results"]["rows"][1][3] = "2023-12-29"
    rows = analysed(json.dumps(response).encode(), "hand-checkable-split.yaml")

    assert outside(rows, "split-0")
    assert values_of(rows)[("split-1", "total_return", "strategy")].value == "11.1111"


@pytest.mark.parametrize(
    "config",
    [
        "hand-checkable-split.yaml",
        "hand-checkable-split-sunday.yaml",
        "hand-checkable-split-edges.yaml",
    ],
)
def test_no_rolling_return_in_a_split_segment(config: str) -> None:
    rows = analysed("hand-checkable.json", config)

    rolling = {row.segment for row in rows if row.window_days is not None}
    assert rolling == {"full"}
    splits = (len(rows) - 94) // 31
    assert len(rows) == 94 + 31 * splits
    assert all(len(segment(rows, f"split-{n}")) == 31 for n in range(splits))


@pytest.mark.parametrize("config", ["hand-checkable-split.yaml", "hand-checkable-split-edges.yaml"])
@pytest.mark.parametrize("subject", ["strategy", "benchmark"])
def test_the_segments_total_returns_compound_to_the_whole(config: str, subject: str) -> None:
    """The level that ends one segment begins the next, so the segments' total returns compound
    to the `full` segment's, within their rounding: 0.99 × 1.111111 is 1.1 for the strategy. A
    segment of one date, with one level, has no return, and changes nothing."""
    values = values_of(analysed("hand-checkable.json", config))

    names = sorted({name for name, _, _ in values if name != "full"})
    growth = Decimal(1)
    for name in names:
        total = values[(name, "total_return", subject)]
        if total.value is None:
            assert total.observations == 1
            continue
        growth *= 1 + Decimal(total.value) / 100
    whole = 1 + Decimal(str(values[("full", "total_return", subject)].value)) / 100
    assert len(names) > 1
    assert abs(growth - whole) < Decimal("0.000002")


@pytest.mark.parametrize(
    ("split", "available", "unreached"),
    [(date(2023, 12, 29), "split-1", "split-0"), (date(2024, 1, 15), "split-0", "split-1")],
    ids=["before", "after"],
)
def test_one_date_outside_the_coverage_leaves_the_whole_coverage_on_its_side(
    split: date, available: str, unreached: str
) -> None:
    """With one declared date, before the coverage, `split-1` holds what the coverage holds from
    C₀; after it, `split-0` holds it to C₁. The other segment is outside the coverage."""
    rows = analysed("hand-checkable.json", "hand-checkable.yaml", (split,))
    values = values_of(rows)

    assert own_dates(values, available) == ("2024-01-01", "2024-01-12", "100.0000", "0")
    assert values[(available, "total_return", "strategy")].value == "10.0000"
    assert outside(rows, unreached)


def test_a_segment_between_dates_outside_the_coverage_is_unavailable_without_levels() -> None:
    """Without usable daily levels, the periods still give the coverage, which doesn't reach
    `split-1`, from 2023-12-29 to 2024-01-05."""
    rows = analysed("hand-checkable-no-chart.json", "hand-checkable-split-before.yaml")

    assert outside(rows, "split-0")
    assert outside(rows, "split-1")
    assert values_of(rows)[("split-2", "coverage_share", None)].value == "63.6364"
