"""Normalization turns a saved response and the plan into `metrics.csv`'s and `settings.csv`'s
rows: the documented rows, in order, with their values, units, provenance, and flags; a missing
metric unavailable with its reason, never zero; each value with exactly the digits the saved
response holds; and the coverage, compared with the requested dates.

Traces, at the core, to R01-AC10 (a ranking by name or ID is sent as text or an integer and
flagged `not_snapshotted`; a formula is recorded whole), R01-AC12 (unavailable metrics and
precision), R01-AC30 (the 23 settings rows and the 20 metrics rows), and R01-AC31 (coverage and
`coverage_mismatch`); and to docs/contracts.md, `p123api-screen-backtest` version 1 (required
structure, numbers and precision, coverage), and settings.csv (`original_key` and
`original_value`). The attempt runs the real client, `requests`, and `urllib3` over the fake
server, and the real store saves the response, so each value is read from the text the attempt
saved. For R01-AC10, a run executed through `Execution`, as `trialfolio run` executes one, also
writes the manifest, which labels reproducibility incomplete for each reference not snapshotted.
"""

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pytest

from tests.core.conftest import CONFIGS, RESPONSES, Execute, execute_run
from tests.support.deep_json import DEEP, on_a_fixed_stack
from trialfolio.configuration import original_values
from trialfolio.contracts.manifest import ExternalReference, RunManifest
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS_BY_NAME
from trialfolio.contracts.tables import MetricsRow, SettingsRow
from trialfolio.errors import TrialFolioError
from trialfolio.normalization import Value, read_response

FORMULA = (CONFIGS / "formula.yaml").read_bytes()
COMPLETE = (RESPONSES / "complete.json").read_bytes()

# Each settings row as docs/contracts.md's screen settings give it for the documented example:
# setting, category, critical, value, unit, interpretation, provenance, original value, flags.
DOCUMENTED_SETTINGS = (
    ("universe", "universe", True, "SP500", None, "interpreted", "verified", "'SP500'",
     ("not_snapshotted",)),
    ("screen_type", "universe", True, "stock", None, "interpreted", "verified", None, ()),
    ("rules", "strategy", True, '["AvgDailyTot(30) > 1000000"]', None, "interpreted",
     "verified", "- 'AvgDailyTot(30) > 1000000'", ()),
    ("ranking", "strategy", True, '{"formula": "EarnYield", "lower_is_better": false}', None,
     "interpreted", "verified", "formula: 'EarnYield'\n  lower_is_better: false", ()),
    ("max_holdings", "strategy", True, "25", "count", "interpreted", "verified", "25", ()),
    ("position_method", "strategy", True, "long", None, "interpreted", "verified", None, ()),
    ("benchmark", "benchmark", True, "SPY", None, "interpreted", "verified", "'SPY'", ()),
    ("currency", "currency", True, "USD", None, "interpreted", "verified", None, ()),
    ("start_date", "dates", True, "2016-01-01", None, "interpreted", "verified", "2016-01-01",
     ()),
    ("end_date", "dates", True, "2025-12-31", None, "interpreted", "verified", "2025-12-31", ()),
    ("rebalance_weeks", "execution", True, "4", "weeks", "interpreted", "verified", "4", ()),
    ("transaction_price", "execution", True, "open", None, "interpreted", "verified", "open",
     ()),
    ("slippage_percent", "costs", True, "0.25", "percent", "interpreted", "verified", "0.25",
     ()),
    ("commission", "costs", True, "not_modeled", None, "interpreted", "inferred", None, ()),
    ("pit_method", "data_source", True, "complete", None, "interpreted", "verified", "complete",
     ()),
    ("data_vendor", "data_source", True, "FactSet", None, "interpreted", "inferred", None,
     ("inferred_default",)),
    ("precision", "other", False, "4", None, "interpreted", "verified", "4", ()),
    ("risk_stats_period", "other", False, "monthly", None, "interpreted", "inferred", None,
     ("inferred_default",)),
    ("max_pos_pct", "strategy", True, "not_sent", None, "not_interpreted", "unknown", None, ()),
    ("rank_tolerance", "strategy", True, "not_sent", None, "not_interpreted", "unknown", None,
     ()),
    ("carry_cost", "costs", True, "not_sent", None, "not_interpreted", "unknown", None, ()),
    ("long_weight", "strategy", True, "not_sent", None, "not_interpreted", "unknown", None, ()),
    ("short_weight", "strategy", True, "not_sent", None, "not_interpreted", "unknown", None, ()),
)  # fmt: skip

# Each metrics row as `p123api-screen-backtest` version 1 gives it, with complete.json's values:
# metric_id, subject, value, unit, source_decimals, source_location, benchmark.
DOCUMENTED_METRICS = (
    ("coverage_start", "strategy", "2016-01-01", "date", None, None, None),
    ("coverage_end", "strategy", "2025-12-31", "date", None, None, None),
    ("coverage_periods", "strategy", "4", "count", None, None, None),
    ("total_return", "strategy", "151.7", "percent", 1, "stats.port.total_return", None),
    ("annualized_return", "strategy", "9.6643", "percent", 4, "stats.port.annualized_return",
     None),
    ("max_drawdown", "strategy", "-33.12", "percent", 2, "stats.port.max_drawdown", None),
    ("standard_deviation", "strategy", "18.217", "percent", 3, "stats.port.standard_dev", None),
    ("sharpe_ratio", "strategy", "0.61", "ratio", 2, "stats.port.sharpe_ratio", None),
    ("sortino_ratio", "strategy", "0.8842", "ratio", 4, "stats.port.sortino_ratio", None),
    ("correlation", "strategy", "0.8123", "ratio", 4, "stats.correlation", "SPY"),
    ("r_squared", "strategy", "0.6598", "ratio", 4, "stats.r_squared", "SPY"),
    ("beta", "strategy", "1.04", "ratio", 2, "stats.beta", "SPY"),
    ("alpha", "strategy", "-2.517", "percent", 3, "stats.alpha", "SPY"),
    ("risk_samples", "strategy", "119", "count", None, "stats.samples", None),
    ("total_return", "benchmark", "238.05", "percent", 2, "stats.bench.total_return", None),
    ("annualized_return", "benchmark", "12.3", "percent", 1, "stats.bench.annualized_return",
     None),
    ("max_drawdown", "benchmark", "-24.5", "percent", 1, "stats.bench.max_drawdown", None),
    ("standard_deviation", "benchmark", "15.4", "percent", 1, "stats.bench.standard_dev", None),
    ("sharpe_ratio", "benchmark", "0.7712", "ratio", 4, "stats.bench.sharpe_ratio", None),
    ("sortino_ratio", "benchmark", "1.0398", "ratio", 4, "stats.bench.sortino_ratio", None),
)  # fmt: skip


def by_setting(rows: tuple[SettingsRow, ...]) -> dict[str, SettingsRow]:
    return {row.setting: row for row in rows}


def by_metric(rows: tuple[MetricsRow, ...]) -> dict[tuple[str, str], MetricsRow]:
    return {(row.subject, row.metric_id): row for row in rows}


# The documented rows (R01-AC30)


def test_settings_csv_has_the_23_documented_rows_in_order(execute: Execute) -> None:
    run = execute(FORMULA, COMPLETE)
    rows = run.write_tables().settings_rows

    observed = tuple(
        (
            row.setting,
            row.category,
            row.critical,
            row.value,
            row.unit,
            row.interpretation,
            row.provenance,
            row.original_value,
            row.flags,
        )
        for row in rows
    )
    assert observed == DOCUMENTED_SETTINGS
    case_id = run.plan.cases[0].case_id
    for row in rows:
        assert row.label == case_id
        assert row.source_artifact == run.configuration.artifact_id
        assert row.original_key == (None if row.original_value is None else row.setting)
        # Only the inferred rows cite a rule: the fixed text, which the plan holds too.
        expected_rule = SCREEN_SETTINGS_BY_NAME[row.setting].inference_rule
        assert row.inference_rule == expected_rule
        assert (expected_rule is not None) == (row.provenance == "inferred")
    rules = by_setting(rows)
    assert "checked 2026-10-01" in str(rules["commission"].inference_rule)
    assert "D-16" in str(rules["data_vendor"].inference_rule)
    assert "checked 2026-10-01" in str(rules["risk_stats_period"].inference_rule)


def test_metrics_csv_has_the_20_documented_rows_in_order(execute: Execute) -> None:
    run = execute(FORMULA, COMPLETE)
    rows = run.write_tables().metrics_rows

    observed = tuple(
        (
            row.metric_id,
            row.subject,
            row.value,
            row.unit,
            row.source_decimals,
            row.source_location,
            row.benchmark,
        )
        for row in rows
    )
    assert observed == DOCUMENTED_METRICS
    case_id = run.plan.cases[0].case_id
    for row in rows:
        calculated = row.source_location is None
        assert row.label == case_id
        assert row.availability == "available"
        assert row.unavailable_reason is None
        assert (row.origin, row.provenance) == (
            ("calculated", "inferred") if calculated else ("reported", "verified")
        )
        assert row.source_label == (None if calculated else str(row.source_location).split(".")[-1])
        assert (str(row.period_start), str(row.period_end)) == ("2016-01-01", "2025-12-31")
        assert row.source_artifact == run.response.artifact_id


# Rankings by name and by ID (R01-AC10)


@pytest.mark.parametrize(
    ("config", "sent", "value", "original"),
    [
        pytest.param(
            "ranking-name.yaml",
            "Synthetic Value Composite",
            '{"name": "Synthetic Value Composite"}',
            "name: 'Synthetic Value Composite'",
            id="name",
        ),
        pytest.param("ranking-id.yaml", 424242, '{"id": 424242}', "id: 424242", id="ID"),
    ],
)
def test_a_ranking_system_is_sent_as_given_and_flagged_not_snapshotted(
    execute: Execute, config: str, sent: object, value: str, original: str
) -> None:
    run = execute((CONFIGS / config).read_bytes(), COMPLETE)
    rows = by_setting(run.write_tables().settings_rows)

    screen = run.sent["screen"]
    assert isinstance(screen, dict)
    ranking: object = screen["ranking"]  # pyright: ignore[reportUnknownVariableType]
    assert ranking == sent
    assert type(ranking) is type(sent)
    assert rows["ranking"].value == value
    assert rows["ranking"].original_value == original
    assert rows["ranking"].flags == ("not_snapshotted",)
    assert rows["universe"].flags == ("not_snapshotted",)


def test_a_formula_ranking_is_recorded_whole_without_a_flag(execute: Execute) -> None:
    rows = by_setting(execute(FORMULA, COMPLETE).write_tables().settings_rows)

    assert json.loads(rows["ranking"].value) == {"formula": "EarnYield", "lower_is_better": False}
    assert rows["ranking"].flags == ()


@pytest.mark.parametrize(
    ("config", "references"),
    [
        pytest.param("ranking-name.yaml", ("universe", "ranking"), id="name"),
        pytest.param("ranking-id.yaml", ("universe", "ranking"), id="ID"),
        # Recorded whole, the formula isn't a reference. The universe still names an object in
        # the account.
        pytest.param("formula.yaml", ("universe",), id="formula"),
    ],
)
def test_the_manifest_labels_reproducibility_incomplete_for_each_reference_not_snapshotted(
    tmp_path: Path, config: str, references: tuple[str, ...]
) -> None:
    execute_run((CONFIGS / config).read_bytes(), tmp_path / "out", COMPLETE)
    manifest = RunManifest.model_validate_json((tmp_path / "out" / "manifest.json").read_bytes())

    assert manifest.reproducibility.status == "incomplete"
    assert manifest.reproducibility.external_references == tuple(
        ExternalReference(setting=name, snapshotted=False) for name in references
    )


# Unavailable values and precision (R01-AC12)


def test_a_missing_metric_is_unavailable_with_its_reason_never_zero(execute: Execute) -> None:
    run = execute(FORMULA, (RESPONSES / "missing-metrics.json").read_bytes())
    tables = run.write_tables()
    rows = by_metric(tables.metrics_rows)

    unavailable = {
        key: row.unavailable_reason
        for key, row in rows.items()
        if row.availability == "unavailable"
    }
    assert unavailable == {
        ("strategy", "sortino_ratio"): "blank_in_source",  # absent
        ("strategy", "beta"): "blank_in_source",  # null
        ("benchmark", "sharpe_ratio"): "unparseable_in_source",  # a string
    }
    assert tables.metrics_unavailable == 3
    for key in unavailable:
        assert rows[key].value is None
        assert rows[key].source_decimals is None
    # The table's cells are empty, with the reason beside them.
    lines = run.store.read("normalized/metrics.csv").decode().splitlines()
    beta = next(line for line in lines if ",beta," in line)
    assert ",beta,beta,,ratio,,unavailable,blank_in_source," in beta


def test_each_value_keeps_exactly_the_digits_of_the_saved_response(execute: Execute) -> None:
    run = execute(FORMULA, COMPLETE)
    rows = run.write_tables().metrics_rows
    saved = json.loads(run.store.read(run.response.path))

    for row in rows:
        if row.source_location is None or row.unit == "count":
            continue
        value: object = saved
        for key in row.source_location.split("."):
            value = value[key]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
        # json writes a float in its shortest round-trip form, which is its repr.
        assert row.value == repr(value)
        assert row.source_decimals == len(repr(value).partition(".")[2])
    # 12.3 was requested at 4 decimal places, and stays 12.3.
    assert by_metric(rows)[("benchmark", "annualized_return")].value == "12.3"


# Coverage (R01-AC31)


def test_coverage_that_equals_the_requested_dates_flags_nothing(execute: Execute) -> None:
    tables = execute(FORMULA, COMPLETE).write_tables()

    metrics = by_metric(tables.metrics_rows)
    settings = by_setting(tables.settings_rows)
    assert metrics[("strategy", "coverage_start")].value == "2016-01-01"
    assert metrics[("strategy", "coverage_end")].value == "2025-12-31"
    assert metrics[("strategy", "coverage_periods")].value == "4"
    assert settings["start_date"].flags == ()
    assert settings["end_date"].flags == ()


def test_coverage_that_differs_from_the_requested_dates_flags_both(execute: Execute) -> None:
    tables = execute(FORMULA, (RESPONSES / "coverage-mismatch.json").read_bytes()).write_tables()

    metrics = by_metric(tables.metrics_rows)
    settings = by_setting(tables.settings_rows)
    assert metrics[("strategy", "coverage_start")].value == "2016-01-04"
    assert metrics[("strategy", "coverage_end")].value == "2025-12-26"
    assert settings["start_date"].value == "2016-01-01"
    assert settings["end_date"].value == "2025-12-31"
    assert settings["start_date"].flags == ("coverage_mismatch",)
    assert settings["end_date"].flags == ("coverage_mismatch",)
    for row in tables.metrics_rows:
        assert (str(row.period_start), str(row.period_end)) == ("2016-01-04", "2025-12-26")


def with_dates(changes: Mapping[tuple[int, str], str | None]) -> bytes:
    """complete.json, with each date given by its row's index and its column changed."""
    response = json.loads(COMPLETE)
    results = response["results"]
    for (row, column), value in changes.items():
        results["rows"][row][results["columns"].index(column)] = value
    return json.dumps(response).encode()


# complete.json's earliest Tran Dt, 2016-01-01, is in its last row, and its latest End Dt,
# 2025-12-31, in its first. A date that's null makes its coverage date unavailable.
@pytest.mark.parametrize(
    ("changes", "start", "end", "flagged"),
    [
        pytest.param(
            {(0, "End Dt"): "2025-12-26"},
            "2016-01-01",
            "2025-12-26",
            {"end_date"},
            id="only the end differs",
        ),
        pytest.param(
            {(3, "Tran Dt"): "2016-01-04"},
            "2016-01-04",
            "2025-12-31",
            {"start_date"},
            id="only the start differs",
        ),
        pytest.param(
            {(1, "Tran Dt"): None, (0, "End Dt"): "2025-12-26"},
            None,
            "2025-12-26",
            {"end_date"},
            id="no start, and the end differs",
        ),
        pytest.param(
            {(2, "End Dt"): None, (3, "Tran Dt"): "2016-01-04"},
            "2016-01-04",
            None,
            {"start_date"},
            id="no end, and the start differs",
        ),
    ],
)
def test_each_date_setting_is_compared_with_its_own_coverage_date(
    execute: Execute,
    changes: Mapping[tuple[int, str], str | None],
    start: str | None,
    end: str | None,
    flagged: set[str],
) -> None:
    tables = execute(FORMULA, with_dates(changes)).write_tables()

    metrics = by_metric(tables.metrics_rows)
    settings = by_setting(tables.settings_rows)
    assert metrics[("strategy", "coverage_start")].value == start
    assert metrics[("strategy", "coverage_end")].value == end
    for setting in ("start_date", "end_date"):
        expected = ("coverage_mismatch",) if setting in flagged else ()
        assert settings[setting].flags == expected
    # Each period date is its own coverage date, and empty only when that one is unavailable.
    for row in tables.metrics_rows:
        assert row.period_start == (None if start is None else date.fromisoformat(start))
        assert row.period_end == (None if end is None else date.fromisoformat(end))


def test_a_response_with_no_periods_has_no_coverage_dates_and_flags_nothing(
    execute: Execute,
) -> None:
    tables = execute(FORMULA, (RESPONSES / "no-periods.json").read_bytes()).write_tables()

    metrics = by_metric(tables.metrics_rows)
    settings = by_setting(tables.settings_rows)
    for metric_id in ("coverage_start", "coverage_end"):
        row = metrics[("strategy", metric_id)]
        assert (row.value, row.unavailable_reason) == (None, "blank_in_source")
    assert metrics[("strategy", "coverage_periods")].value == "0"
    assert settings["start_date"].flags == ()
    assert settings["end_date"].flags == ()
    for row in tables.metrics_rows:
        assert (row.period_start, row.period_end) == (None, None)


# Responses without the layout's structure write no table


def test_a_response_without_the_required_structure_writes_no_table(execute: Execute) -> None:
    run = execute(FORMULA, (RESPONSES / "invalid-structure.json").read_bytes())

    with pytest.raises(TrialFolioError) as raised:
        run.write_tables()
    assert raised.value.code == "provider.response_invalid"
    assert "`stats` isn't an object" in raised.value.message
    assert run.response.path in raised.value.message
    assert not (run.store.root / "normalized").exists()


def test_an_undecoded_response_writes_no_table(execute: Execute) -> None:
    run = execute(FORMULA, b"<html>not JSON</html>")

    assert run.response.form == "undecoded"
    with pytest.raises(TrialFolioError) as raised:
        run.write_tables()
    assert raised.value.code == "provider.response_invalid"
    assert run.response.path in raised.value.message
    assert not (run.store.root / "normalized").exists()


# How the configuration was written (settings.csv's original_key and original_value)


def test_original_values_are_as_the_file_writes_them(execute: Execute) -> None:
    written = (CONFIGS / "written-differently.yaml").read_bytes()
    rows = by_setting(execute(written, COMPLETE).write_tables().settings_rows)

    assert (rows["slippage_percent"].value, rows["slippage_percent"].original_value) == (
        "0.25",
        "0.250",
    )
    assert (rows["start_date"].value, rows["start_date"].original_value) == (
        "2016-01-01",
        "'2016-01-01'",
    )
    assert rows["ranking"].original_value == "lower_is_better: false\n  formula: 'EarnYield'"
    vendor = rows["data_vendor"]
    assert (vendor.original_key, vendor.original_value) == ("data_vendor", "FactSet")
    assert (vendor.value, vendor.provenance, vendor.flags) == (
        "FactSet",
        "inferred",
        ("inferred_default",),
    )


def test_an_original_value_keeps_quotes_indicators_and_comments() -> None:
    text = (
        "\ufeffkind: screen\n"
        "rules:  # before the list\n"
        "  - 'A > 1'   # first\n"
        '  - "B < 2"\n'
        "# after the list\n"
        "flow: [1, 'two']   # after the bracket\n"
        "block: |\n"
        "  line one\n"
        "  line two\n"
        "\n"
        "plain: SP500\n"
    )

    originals = original_values(text.encode(), "c.yaml")

    assert originals == {
        "kind": "screen",
        "rules": "- 'A > 1'   # first\n  - \"B < 2\"",
        "flow": "[1, 'two']",
        "block": "|\n  line one\n  line two",
        "plain": "SP500",
    }


# Reading the saved text (p123api-screen-backtest version 1, numbers and precision)


def saved(
    alpha: str = "1.5", samples: str = "12", rows: str = '[["2016-01-01", "2016-02-01"]]'
) -> bytes:
    """A saved response with the required structure, as text, with the values given."""
    return (
        '{"stats": {"port": {}, "bench": {}, "alpha": ' + alpha + ', "samples": ' + samples + "}, "
        '"results": {"columns": ["Tran Dt", "End Dt"], "rows": ' + rows + "}}"
    ).encode()


@pytest.mark.parametrize(
    ("text", "value"),
    [
        pytest.param("1e-05", Value("0.00001"), id="exponent below 0.0001"),
        pytest.param("1.5e+16", Value("15000000000000000"), id="exponent from 10^16"),
        pytest.param("12.0", Value("12.0"), id="a whole number written as a float"),
        pytest.param("12", Value("12"), id="an integer"),
        pytest.param("-0.0", Value("-0.0"), id="negative zero"),
        pytest.param("123456789.123456789", Value("123456789.123456789"), id="many digits"),
        pytest.param("NaN", Value(None, "unparseable_in_source"), id="NaN"),
        pytest.param("-Infinity", Value(None, "unparseable_in_source"), id="infinity"),
        pytest.param("true", Value(None, "unparseable_in_source"), id="a boolean"),
        pytest.param('"1.5"', Value(None, "unparseable_in_source"), id="a string"),
        pytest.param("[1.5]", Value(None, "unparseable_in_source"), id="an array"),
        pytest.param("null", Value(None, "blank_in_source"), id="null"),
    ],
)
def test_a_decimal_is_read_from_the_saved_text(text: str, value: Value) -> None:
    result = read_response(saved(alpha=text), "response.json")

    assert result.values[("stats", "alpha")] == value


@pytest.mark.parametrize(
    ("text", "value"),
    [
        pytest.param("118", Value("118"), id="an integer"),
        pytest.param("118.0", Value("118"), id="a whole number with a point"),
        pytest.param("1.18e2", Value("118"), id="a whole number with an exponent"),
        pytest.param("0", Value("0"), id="zero"),
        pytest.param("-0.0", Value("0"), id="negative zero"),
        pytest.param("118.5", Value(None, "unparseable_in_source"), id="a fraction"),
        pytest.param("-1", Value(None, "unparseable_in_source"), id="negative"),
    ],
)
def test_a_count_is_a_whole_number_of_zero_or_more(text: str, value: Value) -> None:
    result = read_response(saved(samples=text), "response.json")

    assert result.values[("stats", "samples")] == value


def test_a_missing_metric_key_is_blank() -> None:
    result = read_response(saved().replace(b'"alpha": 1.5, ', b""), "response.json")

    assert result.values[("stats", "alpha")] == Value(None, "blank_in_source")


BLANK = Value(None, "blank_in_source")
UNPARSEABLE = Value(None, "unparseable_in_source")


@pytest.mark.parametrize(
    ("rows", "columns", "start", "end"),
    [
        pytest.param(
            # Neither the first row nor the last holds the earliest or the latest date.
            '[["2016-03-01", "2016-03-15"], ["2016-01-04", "2016-04-01"], '
            '["2016-02-01", "2016-03-01"]]',
            '["Tran Dt", "End Dt"]',
            Value("2016-01-04"),
            Value("2016-04-01"),
            id="earliest and latest, not row positions",
        ),
        pytest.param('[["2016-01-04"]]', '["Tran Dt"]', BLANK, BLANK, id="no End Dt"),
        pytest.param(
            '[["2016/01/04", "2016-03-01"]]',
            '["Tran Dt", "End Dt"]',
            UNPARSEABLE,
            Value("2016-03-01"),
            id="not YYYY-MM-DD",
        ),
        pytest.param(
            '[["2016-01-04", "2016-02-30"]]',
            '["Tran Dt", "End Dt"]',
            Value("2016-01-04"),
            UNPARSEABLE,
            id="not a calendar date",
        ),
        pytest.param(
            '[["2016-01-04", null]]',
            '["Tran Dt", "End Dt"]',
            Value("2016-01-04"),
            UNPARSEABLE,
            id="null",
        ),
        pytest.param(
            '[["2016-05-01", "2016-03-01"]]',
            '["Tran Dt", "End Dt"]',
            UNPARSEABLE,
            UNPARSEABLE,
            id="start after end",
        ),
    ],
)
def test_coverage_dates_are_read_from_every_row(
    rows: str, columns: str, start: Value, end: Value
) -> None:
    text = saved(rows=rows).replace(b'["Tran Dt", "End Dt"]', columns.encode())

    coverage = read_response(text, "response.json").coverage

    assert (coverage.start, coverage.end) == (start, end)
    assert coverage.periods == len(json.loads(rows))


@pytest.mark.parametrize(
    ("content", "problem"),
    [
        pytest.param(b"{", "it isn't JSON", id="not JSON"),
        pytest.param(b"\xff{}", "it isn't JSON", id="not UTF-8"),
        pytest.param(b"[]", "The top level isn't an object", id="an array"),
        pytest.param(
            saved().replace(b'"stats"', b'"Stats"'), "`stats` isn't an object", id="stats"
        ),
        pytest.param(
            saved().replace(b'"results"', b'"result"'), "`results` isn't an object", id="results"
        ),
        pytest.param(
            saved().replace(b'"port": {}', b'"port": []'),
            "`stats.port` isn't an object",
            id="stats.port",
        ),
        pytest.param(
            saved().replace(b'"bench": {}, ', b""),
            "`stats.bench` isn't an object",
            id="stats.bench",
        ),
        pytest.param(
            saved().replace(b'["Tran Dt", "End Dt"]', b'["Tran Dt", 2]'),
            "`results.columns` isn't an array of strings",
            id="columns",
        ),
        pytest.param(
            saved(rows='{"0": []}'), "`results.rows` isn't an array", id="rows not an array"
        ),
        pytest.param(
            saved(rows='[["2016-01-01"]]'),
            "a row of `results.rows` isn't an array as long as `columns`",
            id="a short row",
        ),
    ],
)
def test_a_response_without_the_required_structure_is_invalid(content: bytes, problem: str) -> None:
    with pytest.raises(TrialFolioError) as raised:
        read_response(content, "cases/c/attempts/a/response.json")

    assert raised.value.code == "provider.response_invalid"
    assert problem in raised.value.message
    assert "cases/c/attempts/a/response.json" in raised.value.message


def test_extra_keys_and_a_missing_chart_dont_make_a_response_invalid() -> None:
    text = saved().replace(b'{"stats"', b'{"extra": [1, {"x": null}], "stats"')

    result = read_response(text, "response.json")

    assert result.values[("stats", "alpha")] == Value("1.5")


def test_a_response_nested_too_deeply_to_read_is_invalid() -> None:
    # On a fixed stack, so the decoder raises RecursionError on every machine. Decoded, the
    # response would be invalid for its top level instead.
    with pytest.raises(TrialFolioError) as raised:
        on_a_fixed_stack(lambda: read_response(DEEP, "response.json"))

    assert raised.value.code == "provider.response_invalid"
    assert "it isn't JSON" in raised.value.message
