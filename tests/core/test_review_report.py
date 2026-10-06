"""A review's report is one self-contained, script-free HTML file, as a run's is: the notices, only
the two outside links D-21 allows and the review's own files, and "Not assessed". It shows each
result against the baseline: the intended changes apart from the unexplained mismatches, each
metric beside the baseline's, with the difference only where the two are comparable, and every
unavailable value with its own reason (docs/contracts.md, reports and review output).

Traces, at the core, to the report parts of R02-AC03 (both benchmarks, the mismatch, and
benchmark-relative metrics side by side, without a difference), R02-AC04 (a missing value with
the copied metrics.csv's own reason, never zero), R02-AC07 (the intended change apart from the
unexplained mismatches), R02-AC09 (the notices, the links, no scripts, "Not assessed", and no
`run` path), R02-AC15 (why a run has no tables), R02-AC16 (synthetic results named before any
result, and labeled wherever their values appear), and R02-AC17 (the results that share each
response). The interface checks are R02-T10's.

The run builder writes each run a review configuration names, the input check reads them, and
the comparison core compares them, as a review does. The test writes the review's files and its
manifest itself, because the command that writes them is R02-T08's, as R01-T13's
`tests/core/test_report.py` did for a run. Every expected value is written here by hand.
"""

import logging
import re
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

import pytest

from tests.support.clock import STARTED
from tests.support.fake_portfolio123 import Reply
from tests.support.html_report import Document, Element, parse
from tests.support.run_builder import Run, RunBuilder
from trialfolio.configuration import read_review_configuration
from trialfolio.contracts.manifest import SourceRecord
from trialfolio.contracts.review_configuration import ReviewConfiguration
from trialfolio.contracts.review_manifest import (
    REVIEW_CONFIGURATION_FORMAT,
    Method,
    ReviewArtifact,
    ReviewCapabilities,
    ReviewCommandRecord,
    ReviewManifest,
    ReviewManifestCounts,
)
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION
from trialfolio.differences import DIFFERENCES_PATH, METHOD, METHOD_VERSION, ComparedRun, compare
from trialfolio.notices import (
    CONCISE_NOTICE,
    FULL_NOTICE,
    LICENSE_ID,
    LICENSE_NAME,
    NOTICE_VERSION,
    PORTFOLIO123_DATA_LABEL,
    PORTFOLIO123_DATA_STATEMENT,
    PORTFOLIO123_TERMS_URL,
    license_url,
)
from trialfolio.report import (
    FULL_NOTICE_ID,
    REPORT_PATH,
    HtmlReportRenderer,
    ReviewEvidence,
    write_review_report,
)
from trialfolio.review_inputs import check_review_inputs, local_run_stores
from trialfolio.runs import MANIFEST_PATH
from trialfolio.storage import LocalArtifactStore, StoredFile
from trialfolio.tables import differences_csv

VERSION = "0.2.0"
REVIEW_ID = UUID("6f1c2a4e-8b3d-4c5e-9f60-718293a4b5c6")

SECTIONS = [
    "objective",
    "definitions",
    "data",
    "results",
    "cases",
    "robustness",
    "statistics",
    "evidence",
    "feasibility",
    "conclusion",
]


@dataclass(frozen=True)
class Written:
    """A review, written as `trialfolio review` will write it, and its report."""

    configuration: ReviewConfiguration
    path: Path
    """The review configuration's path, beside the runs it names."""
    out: Path
    """The review's output directory."""
    evidence: ReviewEvidence
    report: StoredFile
    manifest: ReviewManifest
    html: str

    @property
    def document(self) -> Document:
        return parse(self.html)


def _artifact(stored: StoredFile, **fields: object) -> ReviewArtifact:
    return ReviewArtifact.model_validate(
        {
            "path": stored.path,
            "artifact_id": stored.artifact_id,
            "size": stored.size,
            "source": None,
            "label": None,
            **fields,
        }
    )


def write_review(path: Path, out: Path) -> Written:
    """Writes the review of the configuration at `path` into `out`: its configuration, the
    copies, `differences.csv`, the report, and the manifest, which is valid."""
    content = path.read_bytes()
    configuration = read_review_configuration(content, path.name)
    inputs = check_review_inputs(configuration, local_run_stores(path))
    differences = compare(configuration.baseline, [ComparedRun.of(checked) for checked in inputs])
    store = LocalArtifactStore(str(out))
    source = SourceRecord(
        acquired_at=STARTED,
        format=REVIEW_CONFIGURATION_FORMAT,
        format_version="1.0.0",
        parser_version=None,
        provenance="user_supplied",
        operation=None,
    )
    artifacts = [
        _artifact(
            store.claim("configuration.yaml", content),
            role="configuration",
            schema_version="1.0.0",
            source=source,
        )
    ]
    for checked in inputs:
        label = checked.result.label
        artifacts.extend(
            _artifact(
                store.write(f"inputs/{label}/{copy.path}", copy.content),
                role=copy.role,
                schema_version=copy.schema_version,
                label=label,
            )
            for copy in checked.copies
        )
    artifacts.append(
        _artifact(
            store.write(DIFFERENCES_PATH, differences_csv(differences.rows)),
            role="differences",
            schema_version=TABLES_SCHEMA_VERSION,
        )
    )
    evidence = ReviewEvidence(
        configuration, inputs, differences, REVIEW_ID, STARTED, tuple(artifacts)
    )
    report = write_review_report(store, evidence, HtmlReportRenderer(VERSION))
    manifest = ReviewManifest(
        schema_version="1.0.0",
        artifact_type="review",
        trialfolio_version=VERSION,
        created_at=STARTED,
        review_id=REVIEW_ID,
        command=ReviewCommandRecord(name="review", options={"json": False}, started_at=STARTED),
        synthetic=any(checked.reviewed.synthetic for checked in inputs),
        outcome="completed",
        error=None,
        baseline=configuration.baseline,
        results=tuple(checked.reviewed for checked in inputs),
        artifacts=(*artifacts, _artifact(report, role="report", schema_version=None)),
        methods=(Method(name=METHOD, version=METHOD_VERSION),),
        license_id=LICENSE_ID,
        notice_version=NOTICE_VERSION,
        capabilities=ReviewCapabilities(
            return_series="absent",
            statistical_validation="not_assessed",
            trading_readiness="not_assessed",
        ),
        counts=ReviewManifestCounts(
            results=len(inputs),
            settings=differences.setting_counts,
            metrics=differences.metric_counts,
        ),
    )
    store.write(MANIFEST_PATH, manifest.model_dump_json(indent=2).encode())
    html = (out / REPORT_PATH).read_text(encoding="utf-8")
    return Written(configuration, path, out, evidence, report, manifest, html)


type Review = Callable[[str], Written]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Callable[[str], Path]]:
    """Builds the runs a review configuration names, once for the module, beside a copy of it,
    and gives the copy's path."""
    root = tmp_path_factory.mktemp("runs")
    paths: dict[str, Path] = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        builder = RunBuilder(monkeypatch, root / "home")

        def get(name: str) -> Path:
            if name not in paths:
                paths[name] = builder.review(name, root / name.removesuffix(".yaml"))
            return paths[name]

        yield get


@pytest.fixture(scope="module")
def review(
    built: Callable[[str], Path], tmp_path_factory: pytest.TempPathFactory
) -> Callable[[str], Written]:
    """Writes the review of a review configuration, once for the module."""
    root = tmp_path_factory.mktemp("reviews")
    written: dict[str, Written] = {}

    def get(name: str) -> Written:
        if name not in written:
            written[name] = write_review(built(name), root / name.removesuffix(".yaml"))
        return written[name]

    return get


def cells(document: Document, table: Element) -> list[list[str]]:
    """Each body row's cells, as text."""
    return [[cell.text for cell in row] for row in document.rows(table)[1:]]


def table_after(document: Document, heading: str) -> list[list[str]]:
    return cells(document, document.table_after(heading))


def compared(document: Document, label: str) -> dict[tuple[str, str], list[str]]:
    """The table of `label`'s metrics against the baseline's, by metric and subject: the text of
    its cells."""
    rows = table_after(document, f"{label} against the baseline")
    return {(row[0].split()[-1], row[1]): row for row in rows}


# The notices, the links, and what the report holds (R02-AC09)

NOTICES = ["example.yaml", "synthetic.yaml"]


@pytest.mark.parametrize("name", NOTICES)
def test_the_concise_notice_comes_before_any_result_and_links_to_the_full_notice(
    review: Review, name: str
) -> None:
    document = review(name).document
    notice = document.root.by_id("notice")
    (link,) = notice.find_all("a")

    assert notice.text == CONCISE_NOTICE
    assert link.attrs["href"] == f"#{FULL_NOTICE_ID}"
    assert document.root.by_id(FULL_NOTICE_ID).tag == "details"
    for later in (*document.root.find_all("section"), *document.root.find_all("table")):
        assert document.before(notice, later)


@pytest.mark.parametrize("name", NOTICES)
def test_the_data_statement_and_the_full_notice_with_the_license_close_the_report(
    review: Review, name: str
) -> None:
    document = review(name).document
    closing = document.root.by_id("closing")
    details = document.root.by_id(FULL_NOTICE_ID)
    (statement,) = (p for p in closing.find_all("p") if p.text.startswith("Portfolio123 data."))
    paragraphs = [p.text for p in details.find_all("p")]

    assert statement.text == f"{PORTFOLIO123_DATA_LABEL} {PORTFOLIO123_DATA_STATEMENT}"
    assert [a.attrs["href"] for a in statement.find_all("a")] == [PORTFOLIO123_TERMS_URL]
    assert not statement.inside(details)
    assert document.before(statement, details)
    assert details.inside(closing)
    assert paragraphs[: len(FULL_NOTICE)] == list(FULL_NOTICE)
    assert LICENSE_NAME in details.text
    assert LICENSE_ID in details.text
    assert f"Notice version {NOTICE_VERSION}." in details.text
    assert [a.attrs["href"] for a in details.find_all("a")] == [license_url(VERSION)]
    for section in document.root.find_all("section"):
        assert document.before(section, closing)


@pytest.mark.parametrize("name", NOTICES)
def test_its_links_are_the_two_outside_links_and_the_reviews_own_files(
    review: Review, name: str
) -> None:
    written = review(name)
    document = written.document
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    ids = {element.attrs.get("id") for element in document.root.iter()}
    outside = {href for href in hrefs if urlsplit(href).scheme or urlsplit(href).netloc}
    relative = [href for href in hrefs if href not in outside and not href.startswith("#")]

    assert outside == {license_url(VERSION), PORTFOLIO123_TERMS_URL}
    for href in hrefs:
        if href.startswith("#"):
            assert href[1:] in ids
    for href in relative:
        assert not href.startswith("/")
        assert ".." not in href.split("/")
        target = (written.out / unquote(href)).resolve()
        assert target.is_file()
        assert target.is_relative_to(written.out.resolve())
    assert {unquote(href) for href in relative} == {
        MANIFEST_PATH,
        *(artifact.path for artifact in written.manifest.artifacts if artifact.role != "report"),
    }


@pytest.mark.parametrize("name", NOTICES)
def test_no_run_path_appears(review: Review, name: str) -> None:
    written = review(name)

    for result in written.configuration.results:
        assert result.run not in written.html
    assert str(written.path.parent) not in written.html
    assert written.path.name not in written.html


@pytest.mark.parametrize(
    "name", ["example.yaml", "synthetic.yaml", "without-tables.yaml", "shared-response.yaml"]
)
def test_it_runs_and_loads_nothing(review: Review, name: str) -> None:
    document = review(name).document
    elements = list(document.root.iter())
    (style,) = document.root.find_all("style")

    assert document.declarations == ("DOCTYPE html",)
    assert not [e for e in elements if e.tag in ("script", "link", "iframe", "object", "embed")]
    assert not [e for e in elements if e.tag in ("img", "base", "form", "svg")]
    assert not [name for e in elements for name in e.attrs if name.startswith("on")]
    assert not [e for e in elements if "src" in e.attrs or "style" in e.attrs]
    assert not [e for e in elements if e.tag == "meta" and "http-equiv" in e.attrs]
    assert not re.search(r"url\s*\(|@import", style.text, re.IGNORECASE)


@pytest.mark.parametrize("name", NOTICES)
def test_statistical_validation_and_trading_readiness_read_not_assessed(
    review: Review, name: str
) -> None:
    document = review(name).document

    assert set(document.dd("Statistical validation")) == {"Not assessed"}
    assert set(document.dd("Trading readiness")) == {"Not assessed"}
    assert "Statistical validation: Not assessed." in document.root.by_id("statistics").text
    assert "Trading readiness: Not assessed." in document.root.by_id("feasibility").text
    assert document.root.by_id("robustness").text.startswith(
        "6. Robustness and concentration Not assessed."
    )


def test_every_section_appears_in_order_and_says_what_it_cant_support(review: Review) -> None:
    document = review("example.yaml").document
    sections = document.root.find_all("section")

    assert [s.attrs["id"] for s in sections] == SECTIONS
    assert [s.find_all("h2")[0].text.split(".")[0] for s in sections] == [
        str(n) for n in range(1, 11)
    ]
    assert document.dd("Objective")[0].startswith("Unavailable:")
    assert "Exposures Unavailable:" in document.root.by_id("results").text
    assert "Unavailable:" in document.root.by_id("evidence").text
    assert document.dd("Review outcome") == [
        (
            "completed: each result was compared with the baseline. An execution status, not a"
            " research finding."
        )
    ]


def test_it_permits_no_conclusion_about_which_strategy_is_better(review: Review) -> None:
    conclusion = review("example.yaml").document.root.by_id("conclusion").text

    assert "The review compared 1 result with the baseline, hold25:" in conclusion
    assert "not about which strategy is better: the review ranks no result." in conclusion
    assert "permits no conclusion about whether any strategy is useful" in conclusion


def test_the_title_and_purpose_are_the_configurations(review: Review) -> None:
    document = review("example.yaml").document

    assert document.root.find_all("h1")[0].text == "Holdings 25 versus 50"
    assert document.root.find_all("title")[0].text == (
        "Holdings 25 versus 50 · Trial Folio review report"
    )
    assert "Declared purpose Check whether doubling holdings changes risk as expected." in (
        document.root.by_id("objective").text
    )
    assert document.dd("Baseline") == ["hold25"]


@pytest.mark.parametrize(
    ("name", "title", "purpose"),
    [
        (
            "example.yaml",
            "Earnings yield with a liquidity floor",
            "Reference backtest for the 0.1.0 response layout.",
        ),
        (
            "synthetic-only.yaml",
            "Synthetic example: earnings yield with a liquidity floor",
            "Shows a run's files and report offline, from invented values.",
        ),
    ],
)
def test_each_result_shows_its_runs_title_and_purpose(
    review: Review, name: str, title: str, purpose: str
) -> None:
    """A run's plan holds its title and purpose, which the report shows, apart from the review's
    own (docs/contracts.md, review output)."""
    written = review(name)
    document = written.document
    declared = written.configuration.purpose

    assert document.dd("Run title") == [title, title]
    assert document.dd("Run purpose") == [purpose, purpose]
    assert declared is not None
    assert declared != purpose
    assert declared not in document.root.by_id("cases").text


def test_a_run_without_a_purpose_says_none_was_declared(review: Review) -> None:
    evidence = review("example.yaml").evidence
    first, second = evidence.inputs
    run = replace(second.run, plan=second.run.plan.model_copy(update={"purpose": None}))
    without = replace(evidence, inputs=(first, replace(second, run=run)))
    document = parse(HtmlReportRenderer(VERSION).render_review(without))

    assert document.dd("Run purpose") == [
        "Reference backtest for the 0.1.0 response layout.",
        "No purpose was declared.",
    ]


# Benchmarks (R02-AC03)


@pytest.mark.parametrize(
    ("name", "comparison"),
    [
        (
            "undeclared.yaml",
            "Differs: an unexplained mismatch, flagged critical_unexplained_mismatch",
        ),
        ("declared-benchmark.yaml", "Differs: an intended change"),
    ],
)
def test_the_report_shows_both_benchmarks_and_how_they_compare(
    review: Review, name: str, comparison: str
) -> None:
    benchmarks = table_after(review(name).document, "Benchmarks")

    assert benchmarks[0] == ["baseline", "SPY", "The baseline's"]
    assert ["benchmark", "IWM", comparison] in benchmarks


def test_an_undeclared_benchmark_is_a_flagged_unexplained_mismatch(review: Review) -> None:
    mismatches = table_after(review("undeclared.yaml").document, "Unexplained mismatches")

    (row,) = (row for row in mismatches if row[:2] == ["benchmark", "benchmark"])
    assert row[2:6] == ["benchmark", "SPY", "IWM", ""]
    assert row[6].startswith("Flagged. critical_unexplained_mismatch:")


@pytest.mark.parametrize("name", ["undeclared.yaml", "declared-benchmark.yaml"])
def test_metrics_across_benchmarks_are_side_by_side_with_the_reason_and_no_difference(
    review: Review, name: str
) -> None:
    rows = compared(review(name).document, "benchmark")
    reason = "Not compared (different_benchmark): The runs' benchmarks differ."
    side_by_side = {
        ("correlation", "strategy"): ("0.8123 vs. SPY", "0.79 vs. IWM"),
        ("r_squared", "strategy"): ("0.6598 vs. SPY", "0.6241 vs. IWM"),
        ("beta", "strategy"): ("1.04 vs. SPY", "1.1 vs. IWM"),
        ("alpha", "strategy"): ("-2.517 vs. SPY", "-1.9 vs. IWM"),
        ("total_return", "benchmark"): ("238.05 for SPY", "238.05 for IWM"),
        ("annualized_return", "benchmark"): ("12.3 for SPY", "12.3 for IWM"),
        ("max_drawdown", "benchmark"): ("-24.5 for SPY", "-24.5 for IWM"),
        ("standard_deviation", "benchmark"): ("15.4 for SPY", "15.4 for IWM"),
        ("sharpe_ratio", "benchmark"): ("0.7712 for SPY", "0.7712 for IWM"),
        ("sortino_ratio", "benchmark"): ("1.0398 for SPY", "1.0398 for IWM"),
    }

    for key, (baseline, value) in side_by_side.items():
        _, _, shown_baseline, shown_value, _, difference, decimals, comparison = rows[key]
        assert (shown_baseline, shown_value) == (baseline, value)
        assert (difference, decimals, comparison) == ("", "", reason)
    # The strategy's other metrics don't depend on the benchmark.
    assert rows[("annualized_return", "strategy")][5:] == ["0.3 pp", "1", "Differenced"]
    assert rows[("risk_samples", "strategy")][5:] == ["1 count", "0", "Differenced"]


# Missing values (R02-AC04)


def test_a_missing_value_shows_its_own_reason_and_never_zero(review: Review) -> None:
    document = review("missing-metrics.yaml").document
    rows = compared(document, "missing")
    missing = {
        ("sortino_ratio", "strategy"): "blank_in_source",
        ("beta", "strategy"): "blank_in_source",
        ("sharpe_ratio", "benchmark"): "unparseable_in_source",
    }

    for key, reason in missing.items():
        _, _, baseline, value, _, difference, decimals, comparison = rows[key]
        assert value.startswith(f"Unavailable ({reason}):")
        assert not re.search(r"[0-9]", value)
        assert re.fullmatch(r"[0-9.]+( for SPY| vs\. SPY)?", baseline)
        assert (difference, decimals) == ("", "")
        assert comparison == "Unavailable (input_unavailable): A value is unavailable."
    data = document.root.by_id("data")
    items = [li.text for li in data.find_all("ul")[-1].find_all("li")]
    assert items == [
        (
            "missing: Sortino ratio, strategy (sortino_ratio): Unavailable (blank_in_source): The"
            " response gives no value for it."
        ),
        (
            "missing: Beta, strategy (beta): Unavailable (blank_in_source): The response gives"
            " no value for it."
        ),
        (
            "missing: Sharpe ratio, benchmark (sharpe_ratio): Unavailable"
            " (unparseable_in_source): Its value couldn't be interpreted. The saved response"
            " keeps it as it came."
        ),
    ]
    assert "3 metric values are unavailable, each with the reason its copied metrics.csv" in (
        data.text
    )


def test_every_metric_is_available_when_none_is_missing(review: Review) -> None:
    data = review("example.yaml").document.root.by_id("data")

    assert "Missing values None: every metric of every result is available." in data.text


# Intended changes and unexplained mismatches (R02-AC07)


def test_a_declared_change_is_listed_apart_from_the_unexplained_mismatches(
    review: Review,
) -> None:
    document = review("example.yaml").document
    definitions = document.root.by_id("definitions")

    assert table_after(document, "Intended changes") == [
        [
            "hold50",
            "max_holdings",
            "25",
            "50",
            "count",
            "Doubling holdings is the change under review.",
            "Yes: the values differ.",
            "",
        ]
    ]
    assert "Unexplained mismatches Settings that differ from the baseline's without a" in (
        definitions.text
    )
    assert "None: every setting that differs is declared." in definitions.text
    assert "The settings that read the same as the baseline's: 22 of 23 for hold50." in (
        definitions.text
    )


def test_undeclared_differences_are_the_unexplained_mismatches(review: Review) -> None:
    document = review("undeclared.yaml").document
    mismatches = table_after(document, "Unexplained mismatches")

    assert "Intended changes The changes each result declares, against the baseline, with its" in (
        document.root.by_id("definitions").text
    )
    assert "None: no result declares a change." in document.root.by_id("definitions").text
    assert [row[:6] for row in mismatches] == [
        ["slippage", "slippage_percent", "costs", "0.25", "1", "percent"],
        ["benchmark", "benchmark", "benchmark", "SPY", "IWM", ""],
        [
            "ranking-name",
            "ranking",
            "strategy",
            '{"formula": "EarnYield", "lower_is_better": false}',
            '{"name": "Synthetic Value Composite"}',
            "",
        ],
    ]
    assert [re.findall(r"([a-z_]+):", row[6]) for row in mismatches] == [
        ["critical_unexplained_mismatch"],
        ["critical_unexplained_mismatch"],
        ["critical_unexplained_mismatch", "not_snapshotted"],
    ]
    assert all(row[6].startswith("Flagged.") for row in mismatches)


def test_a_declared_change_that_isnt_there_is_flagged_not_observed(review: Review) -> None:
    rows = table_after(review("not-observed.yaml").document, "Intended changes")

    assert [row[:3] + row[6:7] for row in rows] == [
        ["declared", "max_holdings", "25", "No: the values are equal."],
        ["declared", "precision", "4", "No: the values are equal."],
    ]
    for row in rows:
        assert row[7].startswith("Flagged. intended_change_not_observed:")


def test_a_flagged_setting_that_is_the_same_is_listed_with_its_flag(review: Review) -> None:
    document = review("coverage.yaml").document
    (paragraph,) = (
        p for p in document.root.find_all("p") if p.text == "These are the same, but flagged:"
    )
    table = next(t for t in document.root.find_all("table") if document.before(paragraph, t))

    assert [row[:4] for row in cells(document, table)] == [
        ["coverage-mismatch", "start_date", "2016-01-01", ""],
        ["coverage-mismatch", "end_date", "2025-12-31", ""],
    ]
    for row in cells(document, table):
        assert row[4].startswith("Flagged. coverage_mismatch:")


def test_the_coverage_shows_each_results_dates_and_how_far_they_moved(review: Review) -> None:
    rows = table_after(review("coverage.yaml").document, "Coverage")
    couldnt = "Couldn't be established. Unavailable (blank_in_source):"

    assert rows[0] == ["baseline", "2016-01-01", "2025-12-31", "4", "The baseline"]
    assert rows[1] == [
        "coverage-mismatch",
        "2016-01-04: requested 2016-01-01, flagged coverage_mismatch",
        "2025-12-26: requested 2025-12-31, flagged coverage_mismatch",
        "4",
        "Start: 3 days End: -5 days Periods: 0",
    ]
    assert rows[2][0] == "no-periods"
    assert rows[2][1].startswith(couldnt)
    assert rows[2][2].startswith(couldnt)
    assert rows[2][3:] == [
        "0",
        (
            "Start: Unavailable (input_unavailable): A value is unavailable. End: Unavailable"
            " (input_unavailable): A value is unavailable. Periods: -4"
        ),
    ]


# Runs without tables (R02-AC15)


def test_the_report_says_why_each_run_has_no_tables(review: Review) -> None:
    written = review("without-tables.yaml")
    document = written.document
    tables = document.dd("Normalized tables")
    errors = {
        checked.result.label: checked.run.manifest.error for checked in written.evidence.inputs
    }

    assert tables[0] == "Yes: its metrics.csv and settings.csv are copied."
    for shown, label, code in (
        (tables[1], "rejected", "provider.unsupported_capability"),
        (tables[2], "invalid-structure", "provider.response_invalid"),
        (tables[3], "not-json", "provider.response_invalid"),
    ):
        error = errors[label]
        assert error is not None
        assert error.code == code
        expected = f"No. Its run ended with {code}, and its manifest says: {error.message}"
        assert shown == " ".join(expected.split())
    assert document.dd("Saved response")[1] == "None: the run saved no response."


def test_a_run_without_tables_has_every_metric_unavailable(review: Review) -> None:
    document = review("without-tables.yaml").document

    for label in ("rejected", "invalid-structure", "not-json"):
        for row in compared(document, label).values():
            assert row[3] == "Unavailable: the run has no normalized tables."
            assert row[5:] == [
                "",
                "",
                "Unavailable (input_unavailable): A value is unavailable.",
            ]
    rows = table_after(document, "Coverage")
    assert [row[4] for row in rows[1:]] == ["Unavailable: its run has no normalized tables."] * 3
    assert (
        "rejected, invalid-structure, and not-json have no normalized tables, so their metrics"
        " are unavailable."
    ) in document.root.by_id("conclusion").text


# Synthetic results (R02-AC16)


@pytest.mark.parametrize(
    ("name", "banner"),
    [
        ("synthetic.yaml", "Synthetic results. demo is synthetic: written by trialfolio demo"),
        (
            "synthetic-only.yaml",
            "Synthetic results. demo and demo-again are synthetic: written by trialfolio demo",
        ),
    ],
)
def test_before_any_result_the_report_says_which_results_are_synthetic(
    review: Review, name: str, banner: str
) -> None:
    document = review(name).document
    (shown,) = (e for e in document.root.iter() if e.attrs.get("class") == "synthetic")

    assert shown.text.startswith(banner)
    assert "None of" in shown.text
    assert "values comes from Portfolio123, and nothing was sent to it." in shown.text
    for later in (*document.root.find_all("section"), *document.root.find_all("table")):
        assert document.before(shown, later)
    assert (
        document.root.find_all("header")[0]
        .find_all("p")[0]
        .text.endswith(
            "Synthetic results" if name == "synthetic-only.yaml" else "Includes synthetic results"
        )
    )


@pytest.mark.parametrize(
    ("name", "synthetic", "real"),
    [
        ("synthetic.yaml", {"demo"}, {"hold50"}),
        ("synthetic-only.yaml", {"demo", "demo-again"}, set()),
    ],
)
def test_a_synthetic_results_values_are_labeled_wherever_they_appear(
    review: Review, name: str, synthetic: set[str], real: set[str]
) -> None:
    """Values appear in tables, and under headings. Wherever a cell or a heading names a
    synthetic result, it marks it synthetic, and it never marks a result that isn't."""
    document = review(name).document
    marks: dict[str, list[str]] = {label: [] for label in synthetic | real}
    for element in document.root.iter():
        if element.tag not in ("td", "th", "h3"):
            continue
        children = element.children
        for index, child in enumerate(children):
            if isinstance(child, Element) and child.tag == "code" and child.text in marks:
                after = children[index + 1] if index + 1 < len(children) else ""
                marks[child.text].append(after if isinstance(after, str) else "")

    for label in synthetic:
        assert len(marks[label]) >= 10
        assert all(after.startswith(" (synthetic)") for after in marks[label])
    for label in real:
        assert marks[label]
        assert not [after for after in marks[label] if "synthetic" in after]


ATTRIBUTED = [
    "Portfolio123's Sharpe ratio",
    "Portfolio123's Sortino ratio",
    "Portfolio123's alpha",
    "Cumulative return over the backtest",
]
"""A run report's metric definitions that call a value Portfolio123's or a backtest's."""


def test_a_synthetic_results_values_are_never_called_portfolio123s_or_a_backtests(
    review: Review,
) -> None:
    real = review("example.yaml").document.root.find_all("main")[0].text
    synthetic = review("synthetic-only.yaml").document.root.find_all("main")[0].text
    claims = [
        "read from each run's response from Portfolio123",
        "Portfolio123's screen backtest, through",
        "captured from Portfolio123's response, by the result's run",
        "each result is one backtest",
        "Backtested:",
        "Portfolio123's data and engines change",
        *ATTRIBUTED,
        "Portfolio123's default applies",
    ]

    for claim in claims:
        assert claim in real
        assert claim not in synthetic
    assert "each run's invented response" in synthetic
    assert "each result is one synthetic example" in synthetic
    assert "carry_cost" in synthetic
    assert (
        "not_sent: Not sent: where a real run leaves it to Portfolio123's default, which isn't"
        " documented. Here nothing was sent, and no value came from Portfolio123."
    ) in synthetic


def test_a_review_of_both_says_which_values_are_synthetic(review: Review) -> None:
    document = review("synthetic.yaml").document
    sources = {row[0]: row[1] for row in table_after(document, "Sources")}

    assert document.dd("Results")[0] == (
        "Backtested, from applying each screen's rules to historical data, not from actual"
        " trades, apart from demo: synthetic, invented values, neither backtested nor actual"
        " results."
    )
    assert sources["demo (synthetic)"].startswith("Invented values, written by trialfolio demo")
    assert "Nothing was sent to Portfolio123." in sources["demo (synthetic)"]
    assert sources["hold50"].startswith("Portfolio123's screen backtest, through")
    assert document.dd("Results")[1:] == [
        "Synthetic: invented values, neither backtested nor actual results.",
        "Backtested: from applying the screen's rules to historical data, not from actual trades.",
    ]
    definitions = document.root.by_id("definitions").text
    assert (
        "an invented one for demo, whose values don't come from Portfolio123. Each is defined as"
        " that layout defines it."
    ) in definitions
    for claim in ATTRIBUTED:
        assert claim not in definitions
    assert "The Sharpe ratio, as the response layout defines it." in definitions
    assert (
        "not_sent: Not sent. For a backtested result, Portfolio123's default applies, and it"
        " isn't documented. For demo, which is synthetic, nothing was sent."
    ) in document.root.by_id("results").text


# Shared responses (R02-AC17)


def test_the_report_names_the_results_that_share_each_response(review: Review) -> None:
    written = review("shared-response.yaml")
    document = written.document
    responses = {result.label: result.response for result in written.manifest.results}
    (paragraph,) = (h3 for h3 in document.root.find_all("h3") if h3.text == "Shared responses")
    (shared,) = (
        ul for ul in document.root.by_id("cases").find_all("ul") if document.before(paragraph, ul)
    )

    assert [li.text for li in shared.find_all("li")] == [
        f"baseline and written-differently: {responses['baseline']}",
        f"hold50-first and hold50-second: {responses['hold50-first']}",
    ]
    assert responses["baseline"] == responses["written-differently"]
    assert responses["hold50-first"] == responses["hold50-second"]
    notes = {
        h3.text.split()[0]: h3
        for h3 in document.root.by_id("results").find_all("h3")
        if "against the baseline" in h3.text
    }
    flagged = "Every metric row is flagged identical_source"
    results = document.root.by_id("results").text
    assert f"{flagged}: its run's saved response is byte-identical to baseline's." in results
    assert f"{flagged}: its run's saved response is byte-identical to hold50-second's." in results
    assert f"{flagged}: its run's saved response is byte-identical to hold50-first's." in results
    assert set(notes) == {"written-differently", "hold50-first", "hold50-second", "slippage"}
    assert results.count(flagged) == 3


def test_no_shared_response_is_named_when_none_is_shared(review: Review) -> None:
    cases = review("example.yaml").document.root.by_id("cases").text

    assert "Shared responses None: no two results have byte-identical saved responses." in cases


# What the report holds, and how it's written


def test_text_from_the_configuration_or_portfolio123_cant_add_markup_or_reorder_whats_shown(
    built: Callable[[str], Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The configuration's text, and Portfolio123's own message in a run's error (decision 3 of
    R02-T07), are shown as text."""
    override = chr(0x202E)
    hostile = f"<script>alert(1)</script> & {override}evil"
    example = built("example.yaml")
    directory = tmp_path / "configuration"
    shutil.copytree(example.parent / "runs", directory / "runs")
    rejected = Reply(400, b"</dd><b>bold</b> <script>alert(2)</script>")
    RunBuilder(monkeypatch, tmp_path / "home").run(
        Run("formula.yaml", rejected), directory / "runs" / "rejected"
    )
    content = (
        example.read_text(encoding="utf-8")
        .replace("title: Holdings 25 versus 50", f"title: '{hostile}'")
        .replace(
            "reason: Doubling holdings is the change under review.",
            f"reason: '</td><b>bold</b>{override}'",
        )
        .replace("    run: runs/hold50\n", f"    run: runs/hold50\n    description: '{hostile}'\n")
    ) + "  - label: rejected\n    run: runs/rejected\n"
    path = directory / "hostile.yaml"
    path.write_text(content, encoding="utf-8")
    written = write_review(path, tmp_path / "review")
    document = written.document
    shown = "<script>alert(1)</script> & \\u202eevil"
    error = written.evidence.inputs[2].run.manifest.error

    assert not document.root.find_all("script")
    assert not document.root.find_all("b")
    assert override not in written.html
    assert document.root.find_all("h1")[0].text == shown
    assert document.root.find_all("title")[0].text.startswith(shown)
    assert document.dd("Description")[1] == shown
    assert table_after(document, "Intended changes")[0][5] == "</td><b>bold</b>\\u202e"
    assert error is not None
    assert "</dd><b>bold</b> <script>alert(2)</script>" in error.message
    assert document.dd("Normalized tables")[2] == (
        "No. Its run ended with provider.unsupported_capability, and its manifest says:"
        f" {error.message}"
    )


def test_rendering_is_deterministic_and_names_its_version(review: Review) -> None:
    written = review("example.yaml")

    assert HtmlReportRenderer(VERSION).render_review(written.evidence) == written.html
    later = parse(HtmlReportRenderer("0.3.1").render_review(written.evidence))
    details = later.root.by_id(FULL_NOTICE_ID)
    assert [a.attrs["href"] for a in details.find_all("a")] == [license_url("0.3.1")]
    assert later.dd("Report rendered by") == ["Trial Folio 0.3.1"]
    assert later.dd("Review ID") == [str(REVIEW_ID)]
    assert later.dd("Method") == ["screen-run-differences version 1"]


def test_the_report_is_written_into_the_review_and_logs_no_content(
    built: Callable[[str], Path], tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="trialfolio.report"):
        written = write_review(built("example.yaml"), tmp_path / "review")
    report = written.out / REPORT_PATH
    (record,) = (r for r in caplog.records if r.name == "trialfolio.report")

    assert written.report.path == REPORT_PATH
    assert report.read_bytes().decode("utf-8") == written.html
    assert not report.read_bytes().startswith(b"\xef\xbb\xbf")
    assert report.stat().st_size == written.report.size
    assert getattr(record, "event", None) == "report.render.completed"
    assert getattr(record, "review_id", None) == str(REVIEW_ID)
    assert record.getMessage() == f"Rendered the review's report, {written.report.artifact_id}."


def test_the_evidence_needs_each_result_in_order_and_not_the_report(review: Review) -> None:
    evidence = review("example.yaml").evidence
    report = ReviewArtifact(
        path=REPORT_PATH,
        artifact_id="sha256:" + "0" * 64,
        size=1,
        role="report",
        schema_version=None,
        source=None,
        label=None,
    )

    with pytest.raises(ValueError, match="each result"):
        ReviewEvidence(
            evidence.configuration,
            evidence.inputs[::-1],
            evidence.differences,
            REVIEW_ID,
            STARTED,
            evidence.artifacts,
        )
    with pytest.raises(ValueError, match="not the report"):
        ReviewEvidence(
            evidence.configuration,
            evidence.inputs,
            evidence.differences,
            REVIEW_ID,
            STARTED,
            (*evidence.artifacts, report),
        )
