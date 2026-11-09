"""The reconciliation with Portfolio123's metrics: each recalculated `total_return`,
`annualized_return`, and `max_drawdown` beside the metric `metrics.csv` gives, which agrees within
the range the rounding of its inputs, and of the reported value, allows, and differs beyond it;
and `not_compared` when either is unavailable.

Traces, at the core, to R05-AC04 (both values shown, and their difference flagged only beyond the
range the rounding allows: a fixture whose two values differ beyond it is flagged, and one whose
values differ within it isn't) and D-48; and to methodology.md, reconciliation with Portfolio123's
metrics, whose example's ranges are written here by hand.
"""

import json

import pytest

from tests.support.hand_checkable import analysed, tables_of
from tests.support.paths import RESPONSES
from trialfolio.contracts.tables import AnalysisRow

RECONCILED = ("total_return", "annualized_return", "max_drawdown")


def reconciled(rows: tuple[AnalysisRow, ...]) -> dict[tuple[str, str], tuple[str | None, ...]]:
    """Each reconciled value of the `full` segment: the recalculated value, the reported one, and
    whether they agree."""
    return {
        (row.analysis, str(row.subject)): (row.value, row.reported_value, row.reconciliation)
        for row in rows
        if row.segment == "full" and row.analysis in RECONCILED
    }


def test_the_examples_reported_metrics_agree_within_their_rounding() -> None:
    """The strategy's `max_drawdown`, reported as −4.8078 and recalculated as −4.8077, agrees:
    the range is about −4.807786 to −4.807598, widened by 0.00005; and its `total_return`, 10.0001
    against 10.0000, agrees with the range from 9.99995 to 10.00005, so widened, up to 10.0001
    exactly. An `annualized_return` over 11 days is `too_short`, so it's `not_compared`."""
    assert reconciled(analysed("hand-checkable.json")) == {
        ("total_return", "strategy"): ("10.0000", "10.0001", "agrees"),
        ("total_return", "benchmark"): ("1.0000", "1.0", "agrees"),
        ("annualized_return", "strategy"): (None, "2268.4127", "not_compared"),
        ("annualized_return", "benchmark"): (None, "39.1517", "not_compared"),
        ("max_drawdown", "strategy"): ("-4.8077", "-4.8078", "agrees"),
        ("max_drawdown", "benchmark"): ("-1.9608", "-1.9608", "agrees"),
    }


def test_reported_metrics_beyond_their_rounding_differ() -> None:
    values = reconciled(analysed("hand-checkable-differs.json"))

    assert values[("total_return", "strategy")] == ("10.0000", "10.0002", "differs")
    assert values[("max_drawdown", "strategy")] == ("-4.8077", "-4.8079", "differs")
    assert values[("total_return", "benchmark")][2] == "agrees"
    assert values[("max_drawdown", "benchmark")][2] == "agrees"


@pytest.mark.parametrize(
    ("reported", "agreement"),
    [
        (-4.8078, "agrees"),
        (-4.8079, "differs"),
        (-4.8076, "agrees"),
        (-4.8075, "differs"),
        (-4.80779, "agrees"),
        (-4.80781, "differs"),
    ],
)
def test_a_drawdown_agrees_exactly_within_its_range(reported: float, agreement: str) -> None:
    """The range runs from −4.8077862 to −4.8075985, widened by half a unit of the reported
    value's last digit, at the request's precision, 4, or at its own decimals, where it has more:
    to −4.8078362 and −4.8075485 at 4 decimals, and to −4.8077912 and −4.8075935 with the 5 that
    −4.80779 and −4.80781 have."""
    response = json.loads((RESPONSES / "hand-checkable.json").read_bytes())
    response["stats"]["port"]["max_drawdown"] = reported

    values = reconciled(analysed(json.dumps(response).encode()))
    assert values[("max_drawdown", "strategy")][2] == agreement


def test_without_usable_daily_levels_nothing_is_compared() -> None:
    values = reconciled(analysed("hand-checkable-no-chart.json"))

    assert {agreement for _, _, agreement in values.values()} == {"not_compared"}
    assert values[("max_drawdown", "strategy")] == (None, "-4.8078", "not_compared")


def test_an_unavailable_reported_metric_isnt_compared() -> None:
    response = json.loads((RESPONSES / "hand-checkable.json").read_bytes())
    del response["stats"]["port"]["total_return"]

    values = reconciled(analysed(json.dumps(response).encode()))
    assert values[("total_return", "strategy")] == ("10.0000", None, "not_compared")


def test_an_annualized_return_over_four_years_is_reconciled() -> None:
    """`four-years.json`'s annualized returns, reported as they're recalculated, agree, so an
    annualized return is reconciled where it's available."""
    values = reconciled(analysed("four-years.json", "four-years.yaml"))

    assert values[("annualized_return", "strategy")] == ("10.0000", "10.0", "agrees")
    assert values[("annualized_return", "benchmark")] == ("-10.0000", "-10.0", "agrees")
    assert values[("max_drawdown", "strategy")] == ("0.0000", "0.0", "agrees")


@pytest.mark.parametrize(
    ("reported", "agreement"),
    [(10.00001, "agrees"), (10.00002, "differs"), (9.99999, "agrees"), (9.99998, "differs")],
)
def test_an_annualized_return_agrees_exactly_within_its_range(
    reported: float, agreement: str
) -> None:
    """Over 1,461 days, 365.25 / D is 1/4, so the range runs from each end of the last level's
    rounding, ((146.41 ∓ 0.00005) / 100)^(1/4) − 1, times 100: 10 ∓ 0.0000094, since the fourth
    root's slope at 1.4641 is 1 / (4 × 1.1³). Widened by half a unit of a reported value with 5
    decimals, 0.000005, it runs from about 9.9999856 to 10.0000144, so 10.00001 and 9.99999 agree,
    and 10.00002 and 9.99998 differ; a range of the recalculated 10 alone would have 10.00001
    differ too."""
    response = json.loads((RESPONSES / "four-years.json").read_bytes())
    response["stats"]["port"]["annualized_return"] = reported

    values = reconciled(analysed(json.dumps(response).encode(), "four-years.yaml"))
    assert values[("annualized_return", "strategy")] == ("10.0000", str(reported), agreement)


def test_the_reported_value_is_the_metric_as_metrics_csv_writes_it() -> None:
    tables = tables_of("hand-checkable.json")
    metrics = {
        (row.metric_id, row.subject): row.value
        for row in tables.metrics
        if row.metric_id in RECONCILED
    }

    values = reconciled(analysed("hand-checkable.json"))
    assert {key: reported for key, (_, reported, _) in values.items()} == metrics
    assert all(
        (row.reported_value, row.reconciliation) == (None, None)
        for row in analysed("hand-checkable.json", "hand-checkable-split.yaml")
        if row.segment != "full" or row.analysis not in RECONCILED
    )


@pytest.mark.parametrize(
    ("reported", "text", "agreement"), [(0, "0", "agrees"), (0.00004, "0.00004", "differs")]
)
def test_a_drawdowns_range_never_rises_above_zero(
    reported: float, text: str, agreement: str
) -> None:
    """Levels of 100 but a trough of 99.99999, a decline of 0.00001 percent, which its rounding
    could make a rise: (99.999995 / 99.99995 − 1) × 100 is above 0. A drawdown is never above 0,
    so the range's high is 0, and a reported 0.00004 is beyond it, by more than its own half
    unit."""
    response = json.loads((RESPONSES / "hand-checkable.json").read_bytes())
    response["chart"]["screenReturns"] = [100, 99.99999] + [100] * 8
    response["stats"]["port"]["max_drawdown"] = reported

    values = reconciled(analysed(json.dumps(response).encode()))
    assert values[("max_drawdown", "strategy")] == ("0.0000", text, agreement)
