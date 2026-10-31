"""What a report holds, through the CLI: the report `trialfolio run` writes over the fake server,
and the one `trialfolio report` re-renders from the committed `runs/synthetic-run-1.0.0/`. Each is
parsed with `html.parser`.

Traces to R01-AC13 (the concise notice links in-page to the full notice, which carries the
license name, its identifier, and the notice version; no scripts, event handlers, or external
resources; the only outside links are the LICENSE for the version that rendered the report and
Portfolio123's terms, beside the Portfolio123 data statement; "Not assessed" for statistical
validation and trading readiness), R01-AC12 (each unavailable metric shown as unavailable, with
its reason, never as zero), and R01-AC31 (the requested dates, the coverage, and the mismatch, or
that the coverage couldn't be established). tests/core/test_run_report.py checks the same at the
core, and the exact wording of each part.
"""

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import pytest

from tests.support.cli import Cli
from tests.support.fake_portfolio123 import serve_success
from tests.support.html_report import (
    Document,
    assert_closing,
    assert_concise_notice_first,
    assert_full_notice,
    assert_links,
    assert_loads_nothing,
    assert_not_assessed,
    parse,
)
from tests.support.paths import FIXTURES, screen_config

FIXTURE = FIXTURES / "runs" / "synthetic-run-1.0.0"
VERSION = version("trialfolio")
"""The version under test, which renders each report."""


@dataclass(frozen=True)
class Report:
    """A report, parsed, with the run it shows and the directory it's in."""

    document: Document
    run: Path
    out: Path


def run_report(cli: Cli, body: str = "complete.json") -> Report:
    """The report `trialfolio run` writes for `formula.yaml`, when the fake server answers the
    request with the response fixture `body`."""
    cli.ready()
    serve_success(cli.server, body)
    path = screen_config("formula.yaml")
    out = cli.tmp / "runs" / "baseline"
    outcome = cli.run_approved(path, out)
    assert outcome.exit_code == 0, outcome.stderr
    return Report(parse((out / "report.html").read_text(encoding="utf-8")), out, out)


def rerender(cli: Cli, run: Path) -> Report:
    """The report `trialfolio report` re-renders from the run at `run`, into a new directory."""
    out = cli.tmp / "reports" / "baseline"
    outcome = cli("report", run, "--out", out)
    assert outcome.exit_code == 0, outcome.stderr
    return Report(parse((out / "report.html").read_text(encoding="utf-8")), run, out)


def committed_report(cli: Cli) -> Report:
    """The report `trialfolio report` re-renders from a copy of `runs/synthetic-run-1.0.0/`."""
    cli.accept_license()
    run = cli.tmp / "runs" / "synthetic-run-1.0.0"
    shutil.copytree(FIXTURE, run)
    return rerender(cli, run)


REPORTS: dict[str, Callable[[Cli], Report]] = {
    "complete": run_report,
    "committed": committed_report,
}


@pytest.fixture(params=list(REPORTS.values()), ids=list(REPORTS))
def report(request: pytest.FixtureRequest, cli: Cli) -> Report:
    make: Callable[[Cli], Report] = request.param
    return make(cli)


# The notices and the links (R01-AC13)


def test_the_concise_notice_comes_first_and_links_to_the_full_notice_in_a_details_element(
    report: Report,
) -> None:
    assert_concise_notice_first(report.document)
    assert_full_notice(report.document, VERSION)


def test_the_closing_section_holds_the_portfolio123_data_statement_outside_the_full_notice(
    report: Report,
) -> None:
    assert_closing(report.document)


def test_its_only_outside_links_are_the_license_and_portfolio123s_terms(report: Report) -> None:
    # A report `trialfolio report` rendered elsewhere links the run's files from its own directory.
    assert_links(report.document, VERSION, report.out / "report.html", report.run, "manifest.json")


def test_it_runs_and_loads_nothing(report: Report) -> None:
    assert_loads_nothing(report.document)


def test_statistical_validation_and_trading_readiness_read_not_assessed(report: Report) -> None:
    assert_not_assessed(report.document)


# Unavailable metrics (R01-AC12)


def metric_values(document: Document, heading: str) -> dict[str, str]:
    """The value shown for each metric of a metrics table, by its identifier."""
    rows = document.rows(document.table_after(heading))[1:]
    return {row[0].find_all("code")[0].text: row[1].text for row in rows}


@pytest.mark.parametrize("rerendered", [False, True], ids=["run", "report"])
def test_each_unavailable_metric_is_shown_unavailable_with_its_reason(
    cli: Cli, rerendered: bool
) -> None:
    report = run_report(cli, "missing-metrics.json")
    if rerendered:
        report = rerender(cli, report.run)
    strategy = metric_values(report.document, "Strategy")
    benchmark = metric_values(report.document, "Benchmark")

    for value, reason in (
        (strategy["sortino_ratio"], "blank_in_source"),
        (strategy["beta"], "blank_in_source"),
        (benchmark["sharpe_ratio"], "unparseable_in_source"),
    ):
        assert value.startswith(f"Unavailable ({reason})")
        assert not re.search(r"[0-9]", value)
    unavailable = [
        value
        for values in (strategy, benchmark)
        for value in values.values()
        if "Unavailable" in value
    ]
    assert len(unavailable) == 3


# Coverage (R01-AC31)


def coverage(document: Document) -> list[list[str]]:
    """The coverage table's rows: setting, requested, coverage, unit, and comparison."""
    rows = document.rows(document.table_after("Coverage"))[1:]
    return [[cell.text for cell in row] for row in rows]


def test_the_report_shows_the_requested_dates_and_matching_coverage(cli: Cli) -> None:
    rows = coverage(run_report(cli).document)

    assert rows[0][1:3] == ["2016-01-01", "2016-01-01"]
    assert rows[1][1:3] == ["2025-12-31", "2025-12-31"]
    assert [row[4] for row in rows[:2]] == ["Matches", "Matches"]


def test_the_report_shows_both_dates_and_the_mismatch(cli: Cli) -> None:
    rows = coverage(run_report(cli, "coverage-mismatch.json").document)

    assert rows[0][1:3] == ["2016-01-01", "2016-01-04"]
    assert rows[1][1:3] == ["2025-12-31", "2025-12-26"]
    for row in rows[:2]:
        assert "coverage_mismatch" in row[4]


def test_without_periods_the_report_says_the_coverage_couldnt_be_established(cli: Cli) -> None:
    document = run_report(cli, "no-periods.json").document
    rows = coverage(document)

    assert "The coverage couldn't be established" in document.root.by_id("data").text
    assert [row[1] for row in rows[:2]] == ["2016-01-01", "2025-12-31"]
    assert [row[4] for row in rows[:2]] == ["Couldn't be established"] * 2
    assert all("coverage_mismatch" not in cell for row in rows for cell in row)
