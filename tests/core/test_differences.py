"""The comparison core compares each result's settings and metrics with the baseline's, as the
rows of `differences.csv` (docs/contracts.md, differences between screen runs).

Traces, at the core, to R02-AC03 (different benchmarks are flagged, and benchmark-relative
metrics aren't differenced across them), R02-AC04 (a missing metric is unavailable, never zero),
R02-AC07 (intended changes and unexplained mismatches), R02-AC08 (units, and never more precision
than the source), R02-AC11 (a declared change that isn't observed), R02-AC15 (a run without
tables), R02-AC17 (byte-identical responses), and R02-AC18 (the table's format, rows, order, and
counts). The interface checks are R02-T10's. From release 0.4.0, it also traces to R04-AC04 at
the core (docs/contracts.md, differences between screen runs, weight rows): a review of runs whose
ranking is a definition compares each node's weight, a declared `ranking` declares each weight
that differs, a node one run doesn't have is `absent` or unknown by its ranking's form, and a
removal that shifts a node's position compares it by its new path, the alignment's limit.
R04-T11 wrote those cases.

The run builder writes each run a review configuration names, with `trialfolio run` over the
fake server, and the input check reads them, as a review does. Every expected value is written
here by hand, never computed by the code under test.
"""

import csv
import dataclasses
import io
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support.run_builder import RunBuilder
from trialfolio.configuration import read_review_configuration
from trialfolio.contracts.review_configuration import ReviewConfiguration
from trialfolio.contracts.tables import DifferencesRow, DifferencesRowV1_1
from trialfolio.differences import AnyDifferencesRow, ComparedRun, Differences, compare
from trialfolio.review_inputs import check_review_inputs, local_run_stores
from trialfolio.tables import (
    differences_csv,
    differences_csv_v1_1,
    read_differences_csv,
    read_differences_csv_v1_1,
)

COLUMNS = (
    "label",
    "baseline_label",
    "kind",
    "name",
    "subject",
    "category",
    "critical",
    "baseline_value",
    "value",
    "unit",
    "classification",
    "difference",
    "difference_unit",
    "difference_decimals",
    "reason",
    "declared_reason",
    "flagged",
    "flags",
)
"""`differences.csv`'s documented columns, in order."""

SETTINGS = (
    "universe",
    "screen_type",
    "rules",
    "ranking",
    "max_holdings",
    "position_method",
    "benchmark",
    "currency",
    "start_date",
    "end_date",
    "rebalance_weeks",
    "transaction_price",
    "slippage_percent",
    "commission",
    "pit_method",
    "data_vendor",
    "precision",
    "risk_stats_period",
    "max_pos_pct",
    "rank_tolerance",
    "carry_cost",
    "long_weight",
    "short_weight",
)
"""The 23 screen settings, in their documented order."""

SETTING_UNITS = {"max_holdings": "count", "rebalance_weeks": "weeks", "slippage_percent": "percent"}
"""The settings with a unit; the others have none."""

METRICS = {
    1: ("strategy", "coverage_start", "date"),
    2: ("strategy", "coverage_end", "date"),
    3: ("strategy", "coverage_periods", "count"),
    4: ("strategy", "total_return", "percent"),
    5: ("strategy", "annualized_return", "percent"),
    6: ("strategy", "max_drawdown", "percent"),
    7: ("strategy", "standard_deviation", "percent"),
    8: ("strategy", "sharpe_ratio", "ratio"),
    9: ("strategy", "sortino_ratio", "ratio"),
    10: ("strategy", "correlation", "ratio"),
    11: ("strategy", "r_squared", "ratio"),
    12: ("strategy", "beta", "ratio"),
    13: ("strategy", "alpha", "percent"),
    14: ("strategy", "risk_samples", "count"),
    15: ("benchmark", "total_return", "percent"),
    16: ("benchmark", "annualized_return", "percent"),
    17: ("benchmark", "max_drawdown", "percent"),
    18: ("benchmark", "standard_deviation", "percent"),
    19: ("benchmark", "sharpe_ratio", "ratio"),
    20: ("benchmark", "sortino_ratio", "ratio"),
}
"""The layout's 20 metrics, by their row number in its table, with their units."""

BENCHMARK_RELATIVE = (10, 11, 12, 13)
BENCHMARKS_OWN = (15, 16, 17, 18, 19, 20)
INDEPENDENT_OF_THE_BENCHMARK = (4, 5, 6, 7, 8, 9, 14)
PERIOD_DEPENDENT = range(4, 21)

CHANGED_METRICS = {
    1: ("0", "days", 0),
    2: ("0", "days", 0),
    3: ("0", "count", 0),
    4: ("0.0", "pp", 1),
    5: ("0.3", "pp", 1),
    6: ("0.10", "pp", 2),
    7: ("-0.7", "pp", 1),
    8: ("0.02", "ratio", 2),
    9: ("0.0263", "ratio", 4),
    10: ("-0.02", "ratio", 2),
    11: ("-0.0357", "ratio", 4),
    12: ("0.1", "ratio", 1),
    13: ("0.6", "pp", 1),
    14: ("1", "count", 0),
    15: ("0.00", "pp", 2),
    16: ("0.0", "pp", 1),
    17: ("0.0", "pp", 1),
    18: ("0.0", "pp", 1),
    19: ("0.0000", "ratio", 4),
    20: ("0.0000", "ratio", 4),
}
"""`changed-metrics.json` against `complete.json`: each row's difference, its unit, and its
decimals, as `responses/README.md` gives them."""

MISSING_METRICS = (9, 12, 19)
"""`missing-metrics.json`'s missing values: the strategy's `sortino_ratio`, absent; `beta`,
`null`; and the benchmark's `sharpe_ratio`, a string."""

FLAGGING = {
    "critical_unexplained_mismatch",
    "critical_unknown",
    "intended_change_not_observed",
    "coverage_mismatch",
    "unsupported_value",
    "identical_source",
}
"""The flags that set `flagged`, as the open question on flags settled."""


@dataclass(frozen=True)
class Reviewed:
    """A review configuration's runs, read by the input check and compared."""

    configuration: ReviewConfiguration
    path: Path
    runs: tuple[ComparedRun, ...]
    differences: Differences

    def run(self, label: str) -> ComparedRun:
        (run,) = (run for run in self.runs if run.label == label)
        return run


type Review = Callable[[str], Reviewed]


def reviewed(path: Path) -> Reviewed:
    configuration = read_review_configuration(path.read_bytes(), path.name)
    inputs = check_review_inputs(configuration, local_run_stores(path))
    runs = tuple(ComparedRun.of(checked) for checked in inputs)
    return Reviewed(configuration, path, runs, compare(configuration.baseline, runs))


@pytest.fixture(scope="module")
def review(tmp_path_factory: pytest.TempPathFactory) -> Review:
    """Builds the runs a review configuration names, once for the module, and compares them."""
    root = tmp_path_factory.mktemp("reviews")
    built: dict[str, Reviewed] = {}
    builder = RunBuilder(root / "home")

    def get(name: str) -> Reviewed:
        if name not in built:
            built[name] = reviewed(builder.review(name, root / name.removesuffix(".yaml")))
        return built[name]

    return get


def unweighted(differences: Differences) -> list[DifferencesRow]:
    """The rows of a review without weight rows, as `differences.csv` 1.0.0 holds them."""
    rows = [row for row in differences.rows if isinstance(row, DifferencesRow)]
    assert len(rows) == len(differences.rows)
    return rows


def setting(differences: Differences, label: str, name: str) -> AnyDifferencesRow:
    (row,) = (
        row
        for row in differences.rows
        if (row.label, row.kind, row.name) == (label, "setting", name)
    )
    return row


def settings(differences: Differences, label: str) -> list[AnyDifferencesRow]:
    return [row for row in differences.rows if (row.label, row.kind) == (label, "setting")]


def metric(differences: Differences, label: str, number: int) -> AnyDifferencesRow:
    subject, name, _ = METRICS[number]
    (row,) = (
        row
        for row in differences.rows
        if (row.label, row.kind, row.subject, row.name) == (label, "metric", subject, name)
    )
    return row


def metrics(differences: Differences, label: str) -> list[AnyDifferencesRow]:
    return [row for row in differences.rows if (row.label, row.kind) == (label, "metric")]


# Settings (R02-AC03, R02-AC07, R02-AC11, R02-AC15)


def test_a_declared_change_is_an_intended_change_and_isnt_flagged(review: Review) -> None:
    differences = review("example.yaml").differences

    row = setting(differences, "hold50", "max_holdings")

    assert (row.baseline_value, row.value, row.unit) == ("25", "50", "count")
    assert row.classification == "intended_change"
    assert row.declared_reason == "Doubling holdings is the change under review."
    assert (row.flagged, row.flags) == (False, ())
    others = [row for row in settings(differences, "hold50") if row.name != "max_holdings"]
    assert {row.classification for row in others} == {"same"}


@pytest.mark.parametrize(
    ("label", "name", "values", "flags"),
    [
        ("slippage", "slippage_percent", ("0.25", "1"), ("critical_unexplained_mismatch",)),
        ("benchmark", "benchmark", ("SPY", "IWM"), ("critical_unexplained_mismatch",)),
        (
            "ranking-name",
            "ranking",
            (
                '{"formula": "EarnYield", "lower_is_better": false}',
                '{"name": "Synthetic Value Composite"}',
            ),
            ("critical_unexplained_mismatch", "not_snapshotted"),
        ),
    ],
)
def test_an_undeclared_critical_difference_is_a_flagged_unexplained_mismatch(
    review: Review, label: str, name: str, values: tuple[str, str], flags: tuple[str, ...]
) -> None:
    row = setting(review("undeclared.yaml").differences, label, name)

    assert (row.baseline_value, row.value) == values
    assert (row.classification, row.critical) == ("unexplained_mismatch", True)
    assert row.declared_reason is None
    assert (row.flagged, row.flags) == (True, flags)


def test_undeclared_differences_are_the_only_flagged_settings(review: Review) -> None:
    differences = review("undeclared.yaml").differences

    flagged = [(row.label, row.kind, row.name) for row in differences.rows if row.flagged]

    assert flagged == [
        ("slippage", "setting", "slippage_percent"),
        ("benchmark", "setting", "benchmark"),
        ("ranking-name", "setting", "ranking"),
    ]


def test_settings_written_differently_are_the_same(review: Review) -> None:
    differences = review("shared-response.yaml").differences

    rows = settings(differences, "written-differently")

    assert [row.name for row in rows] == list(SETTINGS)
    assert {row.classification for row in rows} == {"same"}
    slippage = setting(differences, "written-differently", "slippage_percent")
    assert (slippage.baseline_value, slippage.value) == ("0.25", "0.25")
    # The flags every screen run carries don't set flagged.
    assert setting(differences, "written-differently", "universe").flags == ("not_snapshotted",)
    for name in ("data_vendor", "risk_stats_period"):
        assert setting(differences, "written-differently", name).flags == ("inferred_default",)
    assert not any(row.flagged for row in rows)


def test_a_declared_change_whose_values_are_equal_is_flagged_not_observed(
    review: Review,
) -> None:
    differences = review("not-observed.yaml").differences

    holdings = setting(differences, "declared", "max_holdings")
    precision = setting(differences, "declared", "precision")

    assert (holdings.classification, holdings.baseline_value, holdings.value) == (
        "same",
        "25",
        "25",
    )
    assert holdings.declared_reason == "Doubling holdings was meant to be the change under review."
    assert (precision.classification, precision.baseline_value, precision.value) == (
        "same",
        "4",
        "4",
    )
    assert precision.declared_reason == "Another precision was meant to be requested."
    for row in (holdings, precision):
        assert (row.flagged, row.flags) == (True, ("intended_change_not_observed",))


def test_a_setting_missing_from_a_run_is_unknown(review: Review) -> None:
    """Two complete 1.0.0 screen runs can't give `unknown`, because each of their settings has a
    value or a token, so the runs' settings are built here."""
    original = review("example.yaml")
    base, run = original.runs
    missing = {"benchmark", "precision", "rules", "start_date"}
    lacking = dataclasses.replace(
        run,
        settings={name: row for name, row in run.settings.items() if name not in missing},
        intended_changes={
            **run.intended_changes,
            "benchmark": "Another benchmark was meant to be compared.",
            "precision": "Another precision was meant to be requested.",
        },
    )
    baseline_lacking = dataclasses.replace(
        base, settings={name: row for name, row in base.settings.items() if name != "end_date"}
    )

    differences = compare("hold25", (baseline_lacking, lacking))

    benchmark = setting(differences, "hold50", "benchmark")
    assert (benchmark.baseline_value, benchmark.value) == ("SPY", None)
    assert benchmark.classification == "unknown"
    # A declared change that can't be confirmed keeps its reason, and is flagged only in a
    # critical category (the owner's decision, 2026-10-05).
    assert benchmark.declared_reason == "Another benchmark was meant to be compared."
    assert (benchmark.flagged, benchmark.flags) == (True, ("critical_unknown",))
    precision = setting(differences, "hold50", "precision")
    assert (precision.classification, precision.critical) == ("unknown", False)
    assert precision.declared_reason == "Another precision was meant to be requested."
    assert (precision.flagged, precision.flags) == (False, ())
    rules = setting(differences, "hold50", "rules")
    assert (rules.classification, rules.flagged, rules.flags) == (
        "unknown",
        True,
        ("critical_unknown",),
    )
    end_date = setting(differences, "hold50", "end_date")
    assert (end_date.baseline_value, end_date.value) == (None, "2025-12-31")
    assert (end_date.classification, end_date.flags) == ("unknown", ("critical_unknown",))


def test_a_row_carries_the_baselines_flags_in_the_flag_codes_order(review: Review) -> None:
    """A row carries the flags either run's `settings.csv` row has (the open question on flags),
    written in the order of the flag codes table, where `coverage_mismatch` comes after
    `critical_unexplained_mismatch`, although it sorts before it. Every review configuration's
    baseline carries only each setting's own flags, so `coverage-mismatch` is the baseline here,
    and the other run's start date is built to differ."""
    runs = {run.label: run for run in review("coverage.yaml").runs}
    other = runs["baseline"]
    start = other.settings["start_date"]
    changed = dataclasses.replace(
        other,
        settings={**other.settings, "start_date": dataclasses.replace(start, value="2016-01-05")},
    )

    differences = compare("coverage-mismatch", (runs["coverage-mismatch"], changed))

    end_date = setting(differences, "baseline", "end_date")
    assert (end_date.baseline_value, end_date.value) == ("2025-12-31", "2025-12-31")
    assert end_date.classification == "same"
    assert (end_date.flagged, end_date.flags) == (True, ("coverage_mismatch",))
    start_date = setting(differences, "baseline", "start_date")
    assert (start_date.baseline_value, start_date.value) == ("2016-01-01", "2016-01-05")
    assert start_date.classification == "unexplained_mismatch"
    assert (start_date.flagged, start_date.flags) == (
        True,
        ("critical_unexplained_mismatch", "coverage_mismatch"),
    )


@pytest.mark.parametrize("label", ["rejected", "invalid-structure", "not-json"])
def test_a_run_without_tables_is_compared_from_its_plan(review: Review, label: str) -> None:
    reviewed = review("without-tables.yaml")
    assert reviewed.run(label).metrics == {}

    rows = settings(reviewed.differences, label)

    assert [row.name for row in rows] == list(SETTINGS)
    assert {row.classification for row in rows} == {"same"}
    assert all(row.value == row.baseline_value for row in rows)
    # Its plan's flags, which never include coverage_mismatch.
    assert {row.name: row.flags for row in rows if row.flags} == {
        "universe": ("not_snapshotted",),
        "data_vendor": ("inferred_default",),
        "risk_stats_period": ("inferred_default",),
    }
    assert {(row.classification, row.reason) for row in metrics(reviewed.differences, label)} == {
        ("unavailable", "input_unavailable")
    }


def test_a_baseline_without_tables_leaves_every_metric_unavailable(review: Review) -> None:
    reviewed = review("without-tables.yaml")

    differences = compare("rejected", reviewed.runs)

    rows = metrics(differences, "baseline")
    assert len(rows) == 20
    assert {(row.classification, row.reason) for row in rows} == {
        ("unavailable", "input_unavailable")
    }
    assert all(row.baseline_value is None and row.value is not None for row in rows)


# Metrics (R02-AC03, R02-AC04, R02-AC08)


@pytest.mark.parametrize(
    ("name", "classification", "declared_reason", "flags"),
    [
        ("undeclared.yaml", "unexplained_mismatch", None, ("critical_unexplained_mismatch",)),
        (
            "declared-benchmark.yaml",
            "intended_change",
            "Compare the strategy with another benchmark.",
            (),
        ),
    ],
)
def test_metrics_that_depend_on_the_benchmark_arent_differenced_across_benchmarks(
    review: Review,
    name: str,
    classification: str,
    declared_reason: str | None,
    flags: tuple[str, ...],
) -> None:
    differences = review(name).differences

    benchmark = setting(differences, "benchmark", "benchmark")
    assert (benchmark.baseline_value, benchmark.value) == ("SPY", "IWM")
    assert (benchmark.classification, benchmark.declared_reason) == (
        classification,
        declared_reason,
    )
    assert benchmark.flags == flags
    for number in (*BENCHMARK_RELATIVE, *BENCHMARKS_OWN):
        row = metric(differences, "benchmark", number)
        assert (row.classification, row.reason) == ("not_comparable", "different_benchmark")
        assert None not in (row.baseline_value, row.value)
        assert (row.difference, row.difference_unit, row.difference_decimals) == (None,) * 3
    for number in (1, 2, 3, *INDEPENDENT_OF_THE_BENCHMARK):
        row = metric(differences, "benchmark", number)
        assert (row.classification, row.reason) == ("differenced", None)
        assert row.difference == CHANGED_METRICS[number][0]


@pytest.mark.parametrize("baseline", ["baseline", "missing"])
def test_a_missing_metric_is_unavailable_and_never_zero(review: Review, baseline: str) -> None:
    reviewed = review("missing-metrics.yaml")
    differences = compare(baseline, reviewed.runs)
    (label,) = {"baseline", "missing"} - {baseline}

    for number in MISSING_METRICS:
        row = metric(differences, label, number)
        assert (row.classification, row.reason) == ("unavailable", "input_unavailable")
        missing = row.value if baseline == "baseline" else row.baseline_value
        present = row.baseline_value if baseline == "baseline" else row.value
        assert missing is None
        assert present is not None
        assert (row.difference, row.difference_unit, row.difference_decimals) == (None,) * 3
    others = [n for n in METRICS if n not in MISSING_METRICS]
    assert {metric(differences, label, n).classification for n in others} == {"differenced"}


def test_differences_have_their_units_and_never_more_decimals_than_the_source(
    review: Review,
) -> None:
    differences = review("example.yaml").differences

    found = {
        number: (row.difference, row.difference_unit, row.difference_decimals)
        for number in METRICS
        for row in [metric(differences, "hold50", number)]
    }

    assert found == CHANGED_METRICS
    for number, (_, _, unit) in METRICS.items():
        row = metric(differences, "hold50", number)
        assert row.unit == unit
        assert row.classification == "differenced"
        assert (row.flagged, row.flags) == (False, ())


def test_coverage_is_differenced_in_days_and_a_different_period_isnt_compared(
    review: Review,
) -> None:
    differences = review("coverage.yaml").differences

    start, end, periods = (metric(differences, "coverage-mismatch", n) for n in (1, 2, 3))

    assert (start.baseline_value, start.value, start.difference) == (
        "2016-01-01",
        "2016-01-04",
        "3",
    )
    assert (end.baseline_value, end.value, end.difference) == ("2025-12-31", "2025-12-26", "-5")
    assert {(row.difference_unit, row.difference_decimals) for row in (start, end)} == {("days", 0)}
    assert (periods.difference, periods.difference_unit) == ("0", "count")
    for number in PERIOD_DEPENDENT:
        row = metric(differences, "coverage-mismatch", number)
        assert (row.classification, row.reason) == ("not_comparable", "different_period")
        assert row.difference is None
    # Its date settings carry its own settings.csv's coverage_mismatch.
    for name in ("start_date", "end_date"):
        row = setting(differences, "coverage-mismatch", name)
        assert (row.classification, row.flags, row.flagged) == (
            "same",
            ("coverage_mismatch",),
            True,
        )


def test_coverage_that_couldnt_be_established_is_never_shown_as_matching(
    review: Review,
) -> None:
    differences = review("coverage.yaml").differences

    for number in (1, 2):
        row = metric(differences, "no-periods", number)
        assert (row.classification, row.reason, row.value) == (
            "unavailable",
            "input_unavailable",
            None,
        )
    periods = metric(differences, "no-periods", 3)
    assert (periods.baseline_value, periods.value, periods.difference) == ("4", "0", "-4")
    for number in PERIOD_DEPENDENT:
        row = metric(differences, "no-periods", number)
        assert (row.classification, row.reason) == ("not_comparable", "unknown_period")
    # Nothing was compared with its coverage, so its date settings aren't flagged.
    for name in ("start_date", "end_date"):
        assert setting(differences, "no-periods", name).flags == ()


@pytest.mark.parametrize("lacking", [("hold25", "hold50"), ("hold25",), ("hold50",)])
def test_a_period_with_one_unknown_date_is_unknown(
    review: Review, lacking: tuple[str, ...]
) -> None:
    """A period is known only when both its dates are. A run whose every `Tran Dt` parses but
    one `End Dt` doesn't has a known start and an unknown end. No response fixture gives one, so
    the runs' rows are built here, as normalization would give them."""
    original = review("example.yaml")

    def without_end(run: ComparedRun) -> ComparedRun:
        rows = {
            key: row.model_copy(update={"period_end": None}) for key, row in run.metrics.items()
        }
        end = ("strategy", "coverage_end")
        rows[end] = rows[end].model_copy(
            update={
                "value": None,
                "availability": "unavailable",
                "unavailable_reason": "unparseable_in_source",
            }
        )
        return dataclasses.replace(run, metrics=rows)

    runs = tuple(without_end(run) if run.label in lacking else run for run in original.runs)

    differences = compare("hold25", runs)

    for number in PERIOD_DEPENDENT:
        row = metric(differences, "hold50", number)
        assert (row.classification, row.reason) == ("not_comparable", "unknown_period")
        assert row.difference is None
    end = metric(differences, "hold50", 2)
    assert (end.classification, end.reason) == ("unavailable", "input_unavailable")
    assert [metric(differences, "hold50", n).difference for n in (1, 3)] == ["0", "0"]


def test_the_first_reason_that_applies_is_given(review: Review) -> None:
    differences = review("coverage-and-benchmark.yaml").differences

    for number in (*BENCHMARK_RELATIVE, *BENCHMARKS_OWN):
        assert metric(differences, "benchmark", number).reason == "different_benchmark"
    for number in INDEPENDENT_OF_THE_BENCHMARK:
        assert metric(differences, "benchmark", number).reason == "different_period"
    assert [metric(differences, "benchmark", n).difference for n in (1, 2, 3)] == ["3", "-5", "0"]


def test_a_different_unit_comes_before_every_other_reason(review: Review) -> None:
    """Layout version 1 fixes each metric's unit, and the input check refuses a run whose
    `metrics.csv` changes one, so the run's rows are built here, as a later layout could give
    them."""
    original = review("coverage-and-benchmark.yaml")
    base, run = original.runs
    key = ("strategy", "alpha")
    changed = dataclasses.replace(
        run, metrics={**run.metrics, key: run.metrics[key].model_copy(update={"unit": "ratio"})}
    )

    differences = compare("baseline", (base, changed))

    row = metric(differences, "benchmark", 13)
    assert (row.classification, row.reason) == ("not_comparable", "different_unit")


# Identical responses (R02-AC17)


def test_results_that_share_a_response_are_flagged_identical_source(review: Review) -> None:
    reviewed = review("shared-response.yaml")
    differences = reviewed.differences

    for label in ("written-differently", "hold50-first", "hold50-second"):
        rows = metrics(differences, label)
        assert len(rows) == 20
        assert all(row.flags == ("identical_source",) and row.flagged for row in rows)
    # The baseline's metrics, from a response no other result has.
    slippage = metrics(differences, "slippage")
    assert all(row.flags == () and not row.flagged for row in slippage)
    assert all(row.value == row.baseline_value for row in slippage)
    assert not any(
        "identical_source" in row.flags for row in differences.rows if row.kind == "setting"
    )
    shared = [(group.labels, group.positions) for group in differences.shared_responses]
    assert shared == [
        (("baseline", "written-differently"), (1, 2)),
        (("hold50-first", "hold50-second"), (3, 4)),
    ]
    responses = [group.response for group in differences.shared_responses]
    assert responses == [
        reviewed.run("baseline").response,
        reviewed.run("hold50-first").response,
    ]
    assert reviewed.run("written-differently").response == responses[0]


def test_two_runs_without_a_response_dont_share_one(review: Review) -> None:
    reviewed = review("without-tables.yaml")
    rejected = reviewed.run("rejected")
    assert rejected.response is None
    again = dataclasses.replace(rejected, label="rejected-again")

    differences = compare("baseline", (*reviewed.runs, again))

    assert differences.shared_responses == ()
    assert not any("identical_source" in row.flags for row in differences.rows)


# The table (R02-AC18)


REVIEWS = ["example.yaml", "coverage.yaml", "shared-response.yaml", "without-tables.yaml"]


@pytest.mark.parametrize("name", REVIEWS)
def test_differences_csv_follows_the_format_rules(review: Review, name: str) -> None:
    content = differences_csv(unweighted(review(name).differences))

    assert not content.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in content
    assert content.endswith(b"\n")
    records = list(csv.reader(io.StringIO(content.decode("utf-8"), newline="")))
    assert tuple(records[0]) == COLUMNS
    assert all(len(record) == len(COLUMNS) for record in records)


@pytest.mark.parametrize("name", REVIEWS)
def test_each_result_has_its_setting_rows_then_its_metric_rows_in_order(
    review: Review, name: str
) -> None:
    reviewed = review(name)
    records = list(
        csv.DictReader(io.StringIO(differences_csv(unweighted(reviewed.differences)).decode()))
    )

    labels = [result.label for result in reviewed.configuration.results]
    compared = [label for label in labels if label != reviewed.configuration.baseline]
    expected = [
        (label, kind, subject, name)
        for label in compared
        for kind, subject, name in [
            *(("setting", "", setting) for setting in SETTINGS),
            *(("metric", subject, name) for subject, name, _ in METRICS.values()),
        ]
    ]
    assert [(r["label"], r["kind"], r["subject"], r["name"]) for r in records] == expected
    assert {r["baseline_label"] for r in records} == {reviewed.configuration.baseline}


@pytest.mark.parametrize("name", REVIEWS)
def test_a_cell_is_empty_only_where_its_column_allows(review: Review, name: str) -> None:
    content = differences_csv(unweighted(review(name).differences))

    for record in csv.DictReader(io.StringIO(content.decode())):
        setting_row = record["kind"] == "setting"
        classification = record["classification"]
        differenced = classification == "differenced"
        must_be_empty = {
            "subject": setting_row,
            "category": not setting_row,
            "critical": not setting_row,
            "difference": not differenced,
            "difference_unit": not differenced,
            "difference_decimals": not differenced,
            "reason": classification not in ("not_comparable", "unavailable"),
        }
        may_be_empty = {
            "baseline_value": classification in ("unknown", "unavailable"),
            "value": classification in ("unknown", "unavailable"),
            "unit": setting_row and record["name"] not in SETTING_UNITS,
            "declared_reason": True,
            "flags": True,
        }
        for column in COLUMNS:
            empty = record[column] == ""
            if must_be_empty.get(column):
                assert empty, column
            elif column in must_be_empty or not may_be_empty.get(column, False):
                assert not empty, column
        if not setting_row:
            assert record["declared_reason"] == ""
        if record["unit"] and setting_row:
            assert record["unit"] == SETTING_UNITS[record["name"]]


@pytest.mark.parametrize(
    "name", [*REVIEWS, "undeclared.yaml", "not-observed.yaml", "coverage-and-benchmark.yaml"]
)
def test_flagged_follows_the_flags_that_need_attention(review: Review, name: str) -> None:
    content = differences_csv(unweighted(review(name).differences))

    for record in csv.DictReader(io.StringIO(content.decode())):
        flags = set(record["flags"].split(";")) if record["flags"] else set[str]()
        assert record["flagged"] == ("true" if flags & FLAGGING else "false")


@pytest.mark.parametrize("name", REVIEWS)
def test_reviewing_the_same_runs_again_gives_the_same_table(review: Review, name: str) -> None:
    first = review(name)

    again = reviewed(first.path)

    assert differences_csv(unweighted(again.differences)) == differences_csv(
        unweighted(first.differences)
    )


@pytest.mark.parametrize("name", [*REVIEWS, "undeclared.yaml", "not-observed.yaml"])
def test_the_counts_are_the_tables(review: Review, name: str) -> None:
    differences = review(name).differences
    records = list(csv.DictReader(io.StringIO(differences_csv(unweighted(differences)).decode())))

    counted = Counter((r["kind"], r["classification"]) for r in records)
    flagged = Counter(r["kind"] for r in records if r["flagged"] == "true")
    settings_counts = differences.setting_counts
    metric_counts = differences.metric_counts
    assert settings_counts.model_dump() == {
        "same": counted["setting", "same"],
        "intended_change": counted["setting", "intended_change"],
        "unexplained_mismatch": counted["setting", "unexplained_mismatch"],
        "unknown": counted["setting", "unknown"],
        "flagged": flagged["setting"],
    }
    assert metric_counts.model_dump() == {
        "differenced": counted["metric", "differenced"],
        "not_comparable": counted["metric", "not_comparable"],
        "unavailable": counted["metric", "unavailable"],
        "flagged": flagged["metric"],
    }


def test_the_undeclared_reviews_counts(review: Review) -> None:
    """R02-AC13's JSON summary counts: the three undeclared critical changes, and
    `missing-metrics.json`'s three missing values."""
    differences = review("undeclared.yaml").differences

    assert differences.setting_counts.flagged == 3
    assert differences.metric_counts.unavailable == 3


@pytest.mark.parametrize("name", REVIEWS)
def test_differences_csv_reads_back_as_its_rows(review: Review, name: str) -> None:
    rows = unweighted(review(name).differences)

    assert read_differences_csv(differences_csv(rows), "differences.csv") == tuple(rows)


# Weight rows (R04-AC04)

NODES = (
    "Value",
    "Value/Earnings Yield",
    "Value/Sales Yield",
    "Momentum",
    "Momentum/Six-Month Return",
    "Momentum/Year Return",
    "Quality",
    "Quality/Return on Equity",
    "Quality/Gross Margin",
)
"""`value-momentum.xml`'s nodes, by their canonical paths, in its order."""

EXAMPLE_WEIGHTS = ("40", "50", "50", "30", "50", "50", "30", "50", "50")
VALUE_HEAVY_WEIGHTS = ("60", "50", "50", "20", "50", "50", "20", "50", "50")
"""`value-momentum.xml`'s and `value-heavy.xml`'s weights, node by node."""

VALUE_HEAVY_REASON = "More weight on value, taken equally from momentum and quality."
"""`ranking-weights.yaml`'s reason for `value-heavy`'s change to `ranking`."""


def weights(differences: Differences, label: str) -> list[DifferencesRowV1_1]:
    """A result's weight rows, in order."""
    return [
        row
        for row in differences.rows
        if isinstance(row, DifferencesRowV1_1) and row.label == label and row.node is not None
    ]


def test_a_declared_ranking_declares_each_weight_that_differs(review: Review) -> None:
    differences = review("ranking-weights.yaml").differences

    rows = weights(differences, "value-heavy")

    assert [(row.node, row.baseline_value, row.value) for row in rows] == list(
        zip(NODES, EXAMPLE_WEIGHTS, VALUE_HEAVY_WEIGHTS, strict=True)
    )
    for row in rows:
        assert (row.name, row.category, row.critical, row.unit) == (
            "ranking_weight",
            "strategy",
            True,
            None,
        )
        if row.baseline_value != row.value:
            assert (row.classification, row.declared_reason) == (
                "intended_change",
                VALUE_HEAVY_REASON,
            )
        else:
            # The declaration is of the ranking, which its own row shows: a weight that's the
            # same isn't a declared change that wasn't observed.
            assert (row.classification, row.declared_reason) == ("same", None)
        assert (row.flags, row.flagged) == ((), False)
    assert sum(row.classification == "intended_change" for row in rows) == 3
    ranking = setting(differences, "value-heavy", "ranking")
    assert (ranking.classification, ranking.declared_reason) == (
        "intended_change",
        VALUE_HEAVY_REASON,
    )


def test_the_weight_rows_follow_ranking_and_only_they_have_a_node(review: Review) -> None:
    differences = review("ranking-weights.yaml").differences

    rows = settings(differences, "value-heavy")

    assert [row.name for row in rows] == [
        *SETTINGS[:4],
        *(["ranking_weight"] * len(NODES)),
        *SETTINGS[4:],
    ]
    assert all(isinstance(row, DifferencesRowV1_1) for row in differences.rows)
    assert [row.node for row in differences.rows if isinstance(row, DifferencesRowV1_1)] == [
        *([None] * 4),
        *NODES,
        *([None] * (len(SETTINGS) - 4 + len(METRICS))),
    ]


def test_an_undeclared_weight_that_differs_is_a_flagged_unexplained_mismatch(
    review: Review,
) -> None:
    differences = review("ranking-undeclared.yaml").differences

    rows = weights(differences, "value-heavy")

    for row, before, after in zip(rows, EXAMPLE_WEIGHTS, VALUE_HEAVY_WEIGHTS, strict=True):
        assert row.declared_reason is None
        if before != after:
            assert (row.classification, row.flags, row.flagged) == (
                "unexplained_mismatch",
                ("critical_unexplained_mismatch",),
                True,
            )
        else:
            assert (row.classification, row.flags, row.flagged) == ("same", (), False)


def test_a_formulas_run_has_no_node_and_a_named_systems_weights_are_unknown(
    review: Review,
) -> None:
    """A formula's run records its ranking in full, without nodes, so each node is `absent`
    there; a ranking system named by name wasn't captured, so each weight is unknown."""
    differences = review("ranking-other-forms.yaml").differences

    formula = weights(differences, "formula")
    named = weights(differences, "ranking-name")

    assert [(row.node, row.baseline_value, row.value) for row in formula] == [
        (node, weight, "absent") for node, weight in zip(NODES, EXAMPLE_WEIGHTS, strict=True)
    ]
    for row in formula:
        assert (row.classification, row.declared_reason, row.flagged) == (
            "intended_change",
            "One formula in place of the ranking system.",
            False,
        )
    assert [(row.node, row.baseline_value, row.value) for row in named] == [
        (node, weight, None) for node, weight in zip(NODES, EXAMPLE_WEIGHTS, strict=True)
    ]
    for row in named:
        assert (row.classification, row.declared_reason, row.flags, row.flagged) == (
            "unknown",
            None,
            ("critical_unknown",),
            True,
        )


def test_a_removal_that_shifts_a_nodes_position_compares_it_by_its_new_path(
    review: Review,
) -> None:
    """The alignment's limit: removing the first of `Value P/E`'s two Yield factors leaves the
    second the only one, named `Value P\\/E/Yield`, where the baseline names it by its position,
    `#2`. So the review compares `#2` with `absent`, and gives the node a row of its own, after
    the baseline's nodes."""
    differences = review("ranking-removal.yaml").differences

    rows = weights(differences, "without-first-yield")

    assert [(row.node, row.baseline_value, row.value) for row in rows] == [
        (r"Value P\/E", "25", "25"),
        (r"Value P\/E/#1", "40", "absent"),
        (r"Value P\/E/#2", "40", "absent"),
        (r"Value P\/E/Cash Flow", "20", "40"),
        ("#2", "10", "10"),
        ("#3", "10", "10"),
        (r"Price\\Book", "20", "20"),
        (r"Price\\Book/Book Yield", "100", "100"),
        (r"\#Momentum", "15", "15"),
        (r"\#Momentum/Short Return", "50", "50"),
        (r"\#Momentum/Long Return", "50", "50"),
        ("Secret Sauce", "20", "20"),
        ("Secret Sauce/Margin", "60", "60"),
        ("Secret Sauce/Turnover", "40", "40"),
        (r"Value P\/E/Yield", "absent", "60"),
    ]
    changed = [row.node for row in rows if row.classification == "intended_change"]
    assert changed == [
        r"Value P\/E/#1",
        r"Value P\/E/#2",
        r"Value P\/E/Cash Flow",
        r"Value P\/E/Yield",
    ]


def test_a_run_without_tables_is_compared_by_its_plans_weights(review: Review) -> None:
    differences = review("ranking-without-tables.yaml").differences

    rows = weights(differences, "value-heavy")

    assert [(row.node, row.baseline_value, row.value) for row in rows] == list(
        zip(NODES, EXAMPLE_WEIGHTS, VALUE_HEAVY_WEIGHTS, strict=True)
    )
    assert sum(row.classification == "intended_change" for row in rows) == 3


@pytest.mark.parametrize("name", ["ranking-weights.yaml", "ranking-other-forms.yaml"])
def test_a_review_with_weight_rows_is_differences_csv_1_1_0_and_version_2(
    review: Review, name: str
) -> None:
    differences = review(name).differences
    rows = [row for row in differences.rows if isinstance(row, DifferencesRowV1_1)]

    content = differences_csv_v1_1(rows)

    assert (differences.schema_version, differences.method_version) == ("1.1.0", 2)
    records = list(csv.reader(io.StringIO(content.decode("utf-8"), newline="")))
    assert tuple(records[0]) == (*COLUMNS, "node")
    for record in records[1:]:
        assert (record[-1] != "") == (record[2:4] == ["setting", "ranking_weight"])
    assert read_differences_csv_v1_1(content, "differences.csv") == tuple(rows)


def test_a_review_without_weight_rows_is_differences_csv_1_0_0_and_version_1(
    review: Review,
) -> None:
    differences = review("example.yaml").differences

    assert all(type(row) is DifferencesRow for row in differences.rows)
    assert (differences.schema_version, differences.method_version) == ("1.0.0", 1)


def test_the_counts_count_the_weight_rows(review: Review) -> None:
    differences = review("ranking-undeclared.yaml").differences

    # The `ranking` row and the three weights that differ, each a flagged unexplained mismatch,
    # and the other 22 settings and 6 weights, the same.
    assert differences.setting_counts.model_dump() == {
        "same": 28,
        "intended_change": 0,
        "unexplained_mismatch": 4,
        "unknown": 0,
        "flagged": 4,
    }
