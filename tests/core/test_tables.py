"""The normalized tables are UTF-8 CSV without a byte-order mark, with `\\n` line endings, the
documented columns in order, RFC 4180 quoting that Python's `csv` module reads back, an empty
value only with its reason, only documented flag codes, and the same rows in the same order on
every run.

Traces to R01-AC14 and docs/contracts.md, normalized tables (format rules, and the schemas' CSV
adapter step). The tables are written from attempts run over the fake server, as the
normalization tests run them.
"""

import csv
import io
from collections.abc import Callable
from typing import get_args

import pytest

from tests.core.conftest import CONFIGS, RESPONSES, Execute
from trialfolio.contracts.common import FlagCode, UnavailableReason
from trialfolio.contracts.tables import METRICS_COLUMNS, SETTINGS_COLUMNS
from trialfolio.errors import TrialFolioError
from trialfolio.normalization import NormalizedTables
from trialfolio.tables import read_metrics_csv, read_settings_csv

FORMULA = (CONFIGS / "formula.yaml").read_bytes()

RESPONSE_FIXTURES = ("complete.json", "missing-metrics.json", "coverage-mismatch.json")


def tables(execute: Execute, response: str, content: bytes = FORMULA) -> tuple[bytes, bytes]:
    run = execute(content, (RESPONSES / response).read_bytes())
    written: NormalizedTables = run.write_tables()
    return run.store.read(written.metrics.path), run.store.read(written.settings.path)


def cells(content: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(content.decode("utf-8"), newline="")))


@pytest.mark.parametrize("response", RESPONSE_FIXTURES)
def test_the_tables_follow_the_format_rules(execute: Execute, response: str) -> None:
    metrics, settings = tables(execute, response)

    for content, columns in ((metrics, METRICS_COLUMNS), (settings, SETTINGS_COLUMNS)):
        assert not content.startswith(b"\xef\xbb\xbf")
        text = content.decode("utf-8")
        assert text.split("\n", 1)[0] == ",".join(columns)
        assert text.endswith("\n")
        assert "\r" not in text
    reasons = set(get_args(UnavailableReason))
    for row in cells(metrics):
        # An empty value only with its reason, and a reason only with an empty value.
        assert (row["value"] == "") == (row["unavailable_reason"] in reasons)
        assert (row["value"] == "") == (row["availability"] == "unavailable")
    flag_codes = set(get_args(FlagCode))
    for row in cells(settings):
        assert row["value"] != ""
        assert set(filter(None, row["flags"].split(";"))) <= flag_codes


@pytest.mark.parametrize("response", RESPONSE_FIXTURES)
def test_the_tables_read_back_as_the_rows_written(execute: Execute, response: str) -> None:
    run = execute(FORMULA, (RESPONSES / response).read_bytes())
    written = run.write_tables()

    metrics = run.store.read(written.metrics.path)
    settings = run.store.read(written.settings.path)
    assert read_metrics_csv(metrics, "metrics.csv") == written.metrics_rows
    assert read_settings_csv(settings, "settings.csv") == written.settings_rows


def test_text_that_needs_quoting_reads_back_unchanged(execute: Execute) -> None:
    rule = 'Name = "A, B"'
    content = FORMULA.replace(b"'AvgDailyTot(30) > 1000000'", f"'{rule}'".encode())
    run = execute(content, (RESPONSES / "complete.json").read_bytes())
    written = run.write_tables()

    settings = run.store.read(written.settings.path)
    rows = {row["setting"]: row for row in cells(settings)}
    assert rows["rules"]["value"] == '["Name = \\"A, B\\""]'
    assert rows["rules"]["original_value"] == f"- '{rule}'"
    # The ranking's original value spans two lines.
    assert rows["ranking"]["original_value"] == "formula: 'EarnYield'\n  lower_is_better: false"
    assert read_settings_csv(settings, "settings.csv") == written.settings_rows


def test_two_runs_write_the_same_rows_in_the_same_order(execute: Execute) -> None:
    first = tables(execute, "missing-metrics.json")
    second = tables(execute, "missing-metrics.json")

    assert first == second


# Reading a table that isn't one


def broken(content: bytes, old: bytes, new: bytes) -> bytes:
    assert old in content
    return content.replace(old, new, 1)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        pytest.param(lambda c: b"\xef\xbb\xbf" + c, "byte-order mark", id="byte-order mark"),
        pytest.param(lambda c: b"\xff" + c, "isn't UTF-8", id="not UTF-8"),
        pytest.param(lambda c: b"", "header", id="empty"),
        pytest.param(lambda c: broken(c, b"label,", b"Label,"), "header", id="header"),
        pytest.param(
            lambda c: broken(c, b",strategy,", b',"strat"egy,'), "RFC 4180", id="bad quoting"
        ),
        pytest.param(lambda c: c + b"x,y\n", "line 22", id="too few cells"),
        pytest.param(
            lambda c: broken(c, b",percent,1,", b",percent,one,"),
            "`source_decimals` is invalid",
            id="not an integer",
        ),
        pytest.param(
            lambda c: broken(c, b",2016-01-01,2025-12-31,", b",2016-02-30,2025-12-31,"),
            "`period_start` is invalid",
            id="not a date",
        ),
        pytest.param(
            lambda c: broken(c, b",percent,1,available", b",percent,2,available"),
            "line 5 isn't a valid row",
            id="not a valid row",
        ),
    ],
)
def test_a_metrics_table_that_isnt_one_is_not_a_run(
    execute: Execute, change: Callable[[bytes], bytes], problem: str
) -> None:
    metrics, _ = tables(execute, "complete.json")

    with pytest.raises(TrialFolioError) as raised:
        read_metrics_csv(change(metrics), "normalized/metrics.csv")

    assert raised.value.code == "input.not_a_run"
    assert "normalized/metrics.csv" in raised.value.message
    assert problem in raised.value.message


@pytest.mark.parametrize(
    ("old", "new", "problem"),
    [
        pytest.param(b",true,", b",yes,", "`critical` is invalid", id="not a boolean"),
        pytest.param(b",not_snapshotted\n", b",snapshot\n", "check `flags`", id="unknown flag"),
        pytest.param(b",not_sent,", b",,", "check `value`", id="an empty value"),
    ],
)
def test_a_settings_table_that_isnt_one_is_not_a_run(
    execute: Execute, old: bytes, new: bytes, problem: str
) -> None:
    _, settings = tables(execute, "complete.json")

    with pytest.raises(TrialFolioError) as raised:
        read_settings_csv(broken(settings, old, new), "normalized/settings.csv")

    assert raised.value.code == "input.not_a_run"
    assert problem in raised.value.message
