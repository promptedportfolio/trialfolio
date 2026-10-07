"""What a review's report holds, through the CLI: the report `trialfolio review` writes, parsed
with `html.parser`, against the files the same review copied and the configuration it read.

Traces to the interface parts of R02-AC03 (both benchmarks, the mismatch, and benchmark-relative
metrics side by side, with the reason, without a difference), R02-AC04 (each missing value
unavailable, with the copied metrics.csv's own reason), R02-AC07 (the intended change apart from
the unexplained mismatches), R02-AC09 (the notices, no scripts or external resources, only the two
outside links D-21 allows and the review's own files, the Portfolio123 data statement, "Not
assessed", and no `run` path), R02-AC15 (why each run has no tables, from its copied manifest's
`error`), R02-AC16 (synthetic results named before any result, labeled wherever their values
appear, and never called Portfolio123's or a backtest's), and R02-AC17 (the results that share
each response). tests/core/test_review_report.py checks the same at the core, and the exact
wording of each part.

The run builder writes the runs each review configuration names, with `trialfolio run` over the
fake server, once for the module. Each review then runs once for the module, through the CLI's
entry function in the test process, with the license acknowledged and a temporary home. Expected
values are written here by hand, or read from the review's copies and its configuration, never
from the code under test.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from tests.interface.conftest import Cli
from tests.support.fake_portfolio123 import FakePortfolio123
from tests.support.html_report import Document, Element, parse
from trialfolio.configuration import read_review_configuration
from trialfolio.contracts.manifest import RunManifest
from trialfolio.contracts.review_configuration import ReviewConfiguration
from trialfolio.contracts.review_manifest import ReviewManifest
from trialfolio.contracts.tables import MetricsRow
from trialfolio.notices import (
    CONCISE_NOTICE,
    FULL_NOTICE,
    PORTFOLIO123_DATA_LABEL,
    PORTFOLIO123_DATA_STATEMENT,
)
from trialfolio.tables import read_metrics_csv, read_settings_csv

ROOT = Path(__file__).resolve().parents[2]
LICENSE_NAME = (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
"""The license's name, as LICENSE's first line gives it."""
LICENSE_URL = (
    f"https://github.com/promptedportfolio/trialfolio/blob/v{version('trialfolio')}/LICENSE"
)
"""The LICENSE published with the version under test, by its tag."""
TERMS_URL = "https://www.portfolio123.com/legal"

BENCHMARK_RELATIVE = [
    ("strategy", "correlation"),
    ("strategy", "r_squared"),
    ("strategy", "beta"),
    ("strategy", "alpha"),
    ("benchmark", "total_return"),
    ("benchmark", "annualized_return"),
    ("benchmark", "max_drawdown"),
    ("benchmark", "standard_deviation"),
    ("benchmark", "sharpe_ratio"),
    ("benchmark", "sortino_ratio"),
]
"""The metrics that depend on the benchmark: rows 10 to 13 and 15 to 20 of the layout."""


@dataclass(frozen=True)
class Reviewed:
    """A review `trialfolio review` wrote, with its configuration and its parsed report."""

    path: Path
    """The review configuration's path, beside the runs it names."""
    out: Path
    html: str

    @property
    def document(self) -> Document:
        return parse(self.html)

    @property
    def configuration(self) -> ReviewConfiguration:
        return read_review_configuration(self.path.read_bytes(), self.path.name)

    @property
    def manifest(self) -> ReviewManifest:
        return ReviewManifest.model_validate_json((self.out / "manifest.json").read_bytes())

    def copied_manifest(self, label: str) -> RunManifest:
        """The copy of the run manifest of the result `label`."""
        copy = self.out / "inputs" / label / "manifest.json"
        return RunManifest.model_validate_json(copy.read_bytes())

    def copied_metrics(self, label: str) -> dict[tuple[str, str], MetricsRow]:
        """The rows of the copy of the result `label`'s metrics.csv, by subject and metric."""
        copy = self.out / "inputs" / label / "normalized" / "metrics.csv"
        rows = read_metrics_csv(copy.read_bytes(), "metrics.csv")
        return {(row.subject, row.metric_id): row for row in rows}

    def copied_setting(self, label: str, setting: str) -> str:
        """The value of `setting` in the copy of the result `label`'s settings.csv."""
        copy = self.out / "inputs" / label / "normalized" / "settings.csv"
        rows = read_settings_csv(copy.read_bytes(), "settings.csv")
        (value,) = (row.value for row in rows if row.setting == setting)
        return value


type Review = Callable[[str], Reviewed]


@pytest.fixture(scope="module")
def review(built: Callable[[str], Path], tmp_path_factory: pytest.TempPathFactory) -> Review:
    """Runs `trialfolio review` on a review configuration, once for the module, with no server
    behind its endpoint, and gives what it wrote."""
    root = tmp_path_factory.mktemp("reviews")
    reviewed: dict[str, Reviewed] = {}

    def get(name: str) -> Reviewed:
        if name not in reviewed:
            path = built(name)
            directory = root / name.removesuffix(".yaml")
            directory.mkdir()
            server = FakePortfolio123()
            server.close()  # A review sends nothing.
            with pytest.MonkeyPatch.context() as monkeypatch:
                cli = Cli(monkeypatch, directory, server)
                cli.accept_license()
                out = directory / "review"
                outcome = cli("review", path, "--out", out)
            assert outcome.exit_code == 0, outcome.stderr
            html = (out / "report.html").read_text(encoding="utf-8")
            reviewed[name] = Reviewed(path, out, html)
        return reviewed[name]

    return get


def table_after(document: Document, heading: str) -> list[list[str]]:
    """Each body row's cells, as text, of the first table after the `<h3>` starting with
    `heading`."""
    return [[cell.text for cell in row] for row in document.rows(document.table_after(heading))[1:]]


def paragraphs_under(document: Document, heading: str) -> list[str]:
    """The text of each paragraph between the `<h3>` whose text is `heading` and the next
    heading."""
    (h3,) = (h for h in document.root.find_all("h3") if h.text == heading)
    assert h3.parent is not None
    siblings = [child for child in h3.parent.children if isinstance(child, Element)]
    texts: list[str] = []
    for sibling in siblings[siblings.index(h3) + 1 :]:
        if sibling.tag in ("h2", "h3"):
            break
        if sibling.tag == "p":
            texts.append(sibling.text)
    return texts


def compared(document: Document, label: str) -> dict[tuple[str, str], list[str]]:
    """The table of `label`'s metrics against the baseline's, by subject and metric: the text of
    each row's cells, which are the metric, its subject, the baseline's value, the result's, the
    unit, the difference, its decimals, and how the two compare."""
    rows = table_after(document, f"{label} against the baseline")
    return {(row[1], row[0].split()[-1]): row for row in rows}


# The notices, the links, and what the report holds (R02-AC09)

NOTICES = pytest.mark.parametrize("name", ["example.yaml", "synthetic.yaml"])


@NOTICES
def test_the_concise_notice_comes_first_and_links_to_the_full_notice_in_a_details_element(
    review: Review, name: str
) -> None:
    document = review(name).document
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


@NOTICES
def test_the_closing_section_holds_the_portfolio123_data_statement_outside_the_full_notice(
    review: Review, name: str
) -> None:
    document = review(name).document
    (details,) = document.root.find_all("details")
    (footer,) = document.root.find_all("footer")
    (statement,) = (p for p in footer.find_all("p") if p.text.startswith(PORTFOLIO123_DATA_LABEL))
    (terms,) = statement.find_all("a")

    assert statement.text == f"{PORTFOLIO123_DATA_LABEL} {PORTFOLIO123_DATA_STATEMENT}"
    assert not statement.inside(details)
    assert terms.text == "Portfolio123's terms"
    assert terms.attrs["href"] == TERMS_URL
    for section in document.root.find_all("section"):
        assert document.before(section, footer)


@NOTICES
def test_its_only_links_are_the_two_outside_links_and_the_reviews_own_files(
    review: Review, name: str
) -> None:
    reviewed = review(name)
    document = reviewed.document
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    ids = {element.attrs.get("id") for element in document.root.iter()}
    listed = {"manifest.json"} | {
        artifact.path for artifact in reviewed.manifest.artifacts if artifact.role != "report"
    }

    outside = [href for href in hrefs if urlsplit(href).scheme or urlsplit(href).netloc]
    assert sorted(outside) == sorted([LICENSE_URL, TERMS_URL])
    relative = [href for href in hrefs if href not in outside and not href.startswith("#")]
    for href in hrefs:
        if href.startswith("#"):
            assert href[1:] in ids
    for href in relative:
        # A path in the review: never one that leaves it, so none reaches a run.
        assert not href.startswith("/")
        assert ".." not in href.split("/")
        assert unquote(href) in listed, href
        assert (reviewed.out / unquote(href)).resolve().is_file()
    assert {unquote(href) for href in relative} == listed


@NOTICES
def test_no_run_path_and_no_path_of_the_command_appears(review: Review, name: str) -> None:
    reviewed = review(name)

    for result in reviewed.configuration.results:
        assert result.run not in reviewed.html
    assert str(reviewed.path.parent) not in reviewed.html
    assert str(reviewed.out) not in reviewed.html


@NOTICES
def test_it_runs_and_loads_nothing(review: Review, name: str) -> None:
    document = review(name).document
    elements = list(document.root.iter())
    styles = " ".join(style.text for style in document.root.find_all("style"))

    assert not [e for e in elements if e.tag in ("script", "link")]
    assert not [name for e in elements for name in e.attrs if name.lower().startswith("on")]
    assert not [e for e in elements if "src" in e.attrs]
    assert not re.search(r"url\s*\(", styles, re.IGNORECASE)


@NOTICES
def test_statistical_validation_and_trading_readiness_read_not_assessed(
    review: Review, name: str
) -> None:
    document = review(name).document

    assert set(document.dd("Statistical validation")) == {"Not assessed"}
    assert set(document.dd("Trading readiness")) == {"Not assessed"}


# Benchmarks (R02-AC03)

BENCHMARKS = pytest.mark.parametrize(
    ("name", "comparison"),
    [
        ("undeclared.yaml", "an unexplained mismatch, flagged critical_unexplained_mismatch"),
        ("declared-benchmark.yaml", "an intended change"),
    ],
)


@BENCHMARKS
def test_the_report_shows_both_benchmarks_and_how_they_compare(
    review: Review, name: str, comparison: str
) -> None:
    reviewed = review(name)
    benchmarks = {row[0]: row[1:] for row in table_after(reviewed.document, "Benchmarks")}

    assert reviewed.copied_setting("baseline", "benchmark") == "SPY"
    assert reviewed.copied_setting("benchmark", "benchmark") == "IWM"
    assert benchmarks["baseline"] == ["SPY", "The baseline's"]
    assert benchmarks["benchmark"] == ["IWM", f"Differs: {comparison}"]


@BENCHMARKS
def test_metrics_across_benchmarks_are_side_by_side_with_the_reason_and_no_difference(
    review: Review, name: str, comparison: str
) -> None:
    reviewed = review(name)
    rows = compared(reviewed.document, "benchmark")
    baseline, other = reviewed.copied_metrics("baseline"), reviewed.copied_metrics("benchmark")

    for key in BENCHMARK_RELATIVE:
        _, _, shown_baseline, shown_value, _, difference, decimals, reason = rows[key]
        assert baseline[key].value is not None
        assert other[key].value is not None
        assert shown_baseline.startswith(f"{baseline[key].value} ")
        assert shown_baseline.endswith(" SPY")
        assert shown_value.startswith(f"{other[key].value} ")
        assert shown_value.endswith(" IWM")
        assert (difference, decimals) == ("", "")
        assert reason.startswith("Not compared (different_benchmark):")
    # A metric that doesn't depend on the benchmark is differenced.
    assert rows[("strategy", "annualized_return")][5:] == ["0.3 pp", "1", "Differenced"]


def test_an_undeclared_benchmark_is_listed_with_the_unexplained_mismatches(
    review: Review,
) -> None:
    mismatches = table_after(review("undeclared.yaml").document, "Unexplained mismatches")

    (row,) = (row for row in mismatches if row[1] == "benchmark")
    assert row[:5] == ["benchmark", "benchmark", "benchmark", "SPY", "IWM"]
    assert row[6].startswith("Flagged. critical_unexplained_mismatch:")


# Missing values (R02-AC04)


def test_a_missing_value_shows_its_copied_reason_and_never_zero(review: Review) -> None:
    reviewed = review("missing-metrics.yaml")
    rows = compared(reviewed.document, "missing")
    copied = reviewed.copied_metrics("missing")
    missing = {key: row for key, row in copied.items() if row.availability == "unavailable"}

    # The three metrics missing-metrics.json leaves out, or gives as null or as a string.
    assert {key: row.unavailable_reason for key, row in missing.items()} == {
        ("strategy", "sortino_ratio"): "blank_in_source",
        ("strategy", "beta"): "blank_in_source",
        ("benchmark", "sharpe_ratio"): "unparseable_in_source",
    }
    for key, row in missing.items():
        _, _, baseline, value, _, difference, decimals, comparison = rows[key]
        assert value.startswith(f"Unavailable ({row.unavailable_reason}):")
        assert not re.search(r"[0-9]", value)
        assert re.match(r"[0-9.]+", baseline)
        assert (difference, decimals) == ("", "")
        assert comparison.startswith("Unavailable (input_unavailable):")
    data = reviewed.document.root.by_id("data").text
    for (_, metric), row in missing.items():
        assert f"({metric}): Unavailable ({row.unavailable_reason}):" in data
    unavailable = [row for row in rows.values() if row[3].startswith("Unavailable")]
    assert len(unavailable) == 3


# Intended changes and unexplained mismatches (R02-AC07)


def test_a_declared_change_is_listed_apart_from_the_unexplained_mismatches(
    review: Review,
) -> None:
    reviewed = review("example.yaml")
    document = reviewed.document
    changes = reviewed.configuration.results[1].intended_changes
    assert changes is not None
    (declared,) = changes

    intended = table_after(document, "Intended changes")
    assert [row[:4] + row[5:6] for row in intended] == [
        ["hold50", "max_holdings", "25", "50", declared.reason]
    ]
    assert paragraphs_under(document, "Unexplained mismatches")[-1] == (
        "None: every setting that differs is declared."
    )


def test_undeclared_differences_are_the_unexplained_mismatches(review: Review) -> None:
    document = review("undeclared.yaml").document

    assert paragraphs_under(document, "Intended changes")[-1] == (
        "None: no result declares a change."
    )
    mismatches = table_after(document, "Unexplained mismatches")
    assert [row[:2] for row in mismatches] == [
        ["slippage", "slippage_percent"],
        ["benchmark", "benchmark"],
        ["ranking-name", "ranking"],
    ]
    assert all(row[6].startswith("Flagged. critical_unexplained_mismatch:") for row in mismatches)


# Runs without tables (R02-AC15)


def test_the_report_says_why_each_run_has_no_tables_from_its_copied_manifest(
    review: Review,
) -> None:
    reviewed = review("without-tables.yaml")
    shown = dict(
        zip(
            [result.label for result in reviewed.configuration.results],
            reviewed.document.dd("Normalized tables"),
            strict=True,
        )
    )

    assert shown["baseline"] == "Yes: its metrics.csv and settings.csv are copied."
    for label in ("rejected", "invalid-structure", "not-json"):
        error = reviewed.copied_manifest(label).error
        assert error is not None
        expected = f"No. Its run ended with {error.code}, and its manifest says: {error.message}"
        assert shown[label] == " ".join(expected.split())
        for row in compared(reviewed.document, label).values():
            assert row[3] == "Unavailable: the run has no normalized tables."
            assert row[7].startswith("Unavailable (input_unavailable):")


# Synthetic results (R02-AC16)

SYNTHETIC = pytest.mark.parametrize(
    ("name", "synthetic", "real"),
    [
        ("synthetic.yaml", {"demo"}, {"hold50"}),
        ("synthetic-only.yaml", {"demo", "demo-again"}, set[str]()),
    ],
)


def labels_in(element: Element) -> list[str]:
    return [code.text for code in element.find_all("code")]


@SYNTHETIC
def test_before_any_result_the_report_says_which_results_are_synthetic(
    review: Review, name: str, synthetic: set[str], real: set[str]
) -> None:
    document = review(name).document
    (banner,) = (e for e in document.root.iter() if e.attrs.get("class") == "synthetic")

    assert banner.text.startswith("Synthetic results.")
    assert set(labels_in(banner)) & (synthetic | real) == synthetic
    assert "values comes from Portfolio123, and nothing was sent to it." in banner.text
    for later in (*document.root.find_all("section"), *document.root.find_all("table")):
        assert document.before(banner, later)


@SYNTHETIC
def test_a_synthetic_results_values_are_labeled_wherever_they_appear(
    review: Review, name: str, synthetic: set[str], real: set[str]
) -> None:
    """A cell or a heading that names a synthetic result marks it synthetic, and one that names a
    result that isn't never does."""
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
        assert marks[label]
        assert all(after.startswith(" (synthetic)") for after in marks[label])
    for label in real:
        assert marks[label]
        assert not [after for after in marks[label] if "synthetic" in after]


CLAIMS = [
    "read from each run's response from Portfolio123",
    "Portfolio123's screen backtest, through",
    "captured from Portfolio123's response",
    "Backtested:",
    "one backtest",
]
"""What a report says of results that came from Portfolio123: each is in the report of
`example.yaml`, whose runs were written by `trialfolio run`."""


def test_a_synthetic_results_values_are_never_called_portfolio123s_or_a_backtests(
    review: Review,
) -> None:
    real = review("example.yaml").document.root.find_all("main")[0].text
    synthetic = review("synthetic-only.yaml").document.root.find_all("main")[0].text

    for claim in CLAIMS:
        assert claim in real
        assert claim not in synthetic
    assert "Synthetic: invented values, neither backtested nor actual results." in synthetic


# Shared responses (R02-AC17)


def test_the_report_names_the_results_that_share_each_response(review: Review) -> None:
    reviewed = review("shared-response.yaml")
    document = reviewed.document
    responses = {result.label: result.response for result in reviewed.manifest.results}
    cases = document.root.by_id("cases")
    (heading,) = (h3 for h3 in cases.find_all("h3") if h3.text == "Shared responses")
    (shared,) = (ul for ul in cases.find_all("ul") if document.before(heading, ul))

    assert responses["baseline"] == responses["written-differently"]
    assert responses["hold50-first"] == responses["hold50-second"]
    assert [li.text for li in shared.find_all("li")] == [
        f"baseline and written-differently: {responses['baseline']}",
        f"hold50-first and hold50-second: {responses['hold50-first']}",
    ]
    # The fourth result's metrics are the baseline's, but its response is its own.
    assert "slippage" not in shared.text
