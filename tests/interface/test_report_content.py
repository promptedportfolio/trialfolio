"""What a report holds, through the CLI: the report `trialfolio run` writes over the fake server,
and the one `trialfolio report` re-renders from the committed `runs/synthetic-run-1.0.0/`. Each is
parsed with `html.parser`.

Traces to R01-AC13 (the concise notice links in-page to the full notice, which carries the
license name, its identifier, and the notice version; no scripts, event handlers, or external
resources; the only outside links are the LICENSE for the version that rendered the report and
Portfolio123's terms, beside the Portfolio123 data statement; "Not assessed" for statistical
validation and trading readiness), R01-AC12 (each unavailable metric shown as unavailable, with
its reason, never as zero), and R01-AC31 (the requested dates, the coverage, and the mismatch, or
that the coverage couldn't be established). tests/core/test_report.py checks the same at the
core, and the exact wording of each part.
"""

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from tests.interface.conftest import Cli, config, plan_hash_for, serve_success
from tests.support.html_report import Document, parse
from trialfolio.contracts.manifest import RunManifest
from trialfolio.notices import (
    CONCISE_NOTICE,
    FULL_NOTICE,
    PORTFOLIO123_DATA_LABEL,
    PORTFOLIO123_DATA_STATEMENT,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "runs" / "synthetic-run-1.0.0"
LICENSE_NAME = (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
"""The license's name, as LICENSE's first line gives it."""
LICENSE_URL = (
    f"https://github.com/promptedportfolio/trialfolio/blob/v{version('trialfolio')}/LICENSE"
)
"""The LICENSE published with the version under test, by its tag."""
TERMS_URL = "https://www.portfolio123.com/legal"


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
    path = config("formula.yaml")
    out = cli.tmp / "runs" / "baseline"
    outcome = cli("run", path, "--out", out, "--approve", plan_hash_for(path))
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
    document = report.document
    (notice,) = (p for p in document.root.find_all("p") if p.text == CONCISE_NOTICE)
    (link,) = notice.find_all("a")
    href = link.attrs["href"] or ""
    full = document.root.by_id(href.removeprefix("#"))

    assert href.startswith("#")
    assert full.tag == "details"
    for later in (*document.root.find_all("section"), *document.root.find_all("table")):
        assert document.before(notice, later)
    assert [p.text for p in full.find_all("p")][: len(FULL_NOTICE)] == list(FULL_NOTICE)
    assert LICENSE_NAME in full.text
    assert "LicenseRef-NSPRL-1.1" in full.text
    assert "Notice version 1.0." in full.text
    assert [a.attrs["href"] for a in full.find_all("a")] == [LICENSE_URL]


def test_the_closing_section_holds_the_portfolio123_data_statement_outside_the_full_notice(
    report: Report,
) -> None:
    document = report.document
    (details,) = document.root.find_all("details")
    (footer,) = document.root.find_all("footer")
    (statement,) = (p for p in footer.find_all("p") if p.text.startswith(PORTFOLIO123_DATA_LABEL))
    (terms,) = statement.find_all("a")

    assert statement.text == f"{PORTFOLIO123_DATA_LABEL} {PORTFOLIO123_DATA_STATEMENT}"
    assert not statement.inside(details)
    assert terms.text == "Portfolio123's terms"
    assert terms.attrs["href"] == TERMS_URL


def test_its_only_outside_links_are_the_license_and_portfolio123s_terms(report: Report) -> None:
    document = report.document
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    ids = {element.attrs.get("id") for element in document.root.iter()}
    manifest = RunManifest.model_validate_json((report.run / "manifest.json").read_bytes())
    files = {
        (report.run / artifact.path).resolve()
        for artifact in manifest.artifacts
        if artifact.role != "report"
    } | {(report.run / "manifest.json").resolve()}

    outside = [href for href in hrefs if urlsplit(href).scheme or urlsplit(href).netloc]
    assert sorted(outside) == sorted([LICENSE_URL, TERMS_URL])
    for href in hrefs:
        if href in outside:
            continue
        assert not href.startswith("/")
        if href.startswith("#"):
            assert href[1:] in ids
        else:
            assert (report.out / unquote(href)).resolve() in files, href


def test_it_runs_and_loads_nothing(report: Report) -> None:
    elements = list(report.document.root.iter())
    styles = " ".join(style.text for style in report.document.root.find_all("style"))

    assert not [e for e in elements if e.tag in ("script", "link")]
    assert not [name for e in elements for name in e.attrs if name.lower().startswith("on")]
    assert not [e for e in elements if "src" in e.attrs]
    assert not re.search(r"url\s*\(", styles, re.IGNORECASE)


def test_statistical_validation_and_trading_readiness_read_not_assessed(report: Report) -> None:
    assert set(report.document.dd("Statistical validation")) == {"Not assessed"}
    assert set(report.document.dd("Trading readiness")) == {"Not assessed"}


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
