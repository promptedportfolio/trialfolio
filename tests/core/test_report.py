"""The report is one self-contained, script-free HTML file: the concise notice before any result,
linking to the full notice at the end, with the license and the Portfolio123 data statement; only
the two outside links D-21 allows; the run's values exactly as its tables hold them, with their
units, and unavailable values with their reasons; every section, unavailable where the evidence
can't support it; and "Not assessed" for statistical validation and trading readiness.

Traces, at the core, to R01-AC13 (notices, links, no scripts or external resources, "Not
assessed"), R01-AC12 (each unavailable metric shown as unavailable, with its reason; no value
padded), R01-AC31 (the requested dates, the coverage, and the mismatch, or that the coverage
couldn't be established), and R01-AC10 (reproducibility labeled incomplete); and to
docs/contracts.md, reports, REQ-08, REQ-13 (neutral status), DSC-04 (results labeled by their
nature), and the JSON summary's rule that `quotaRemaining` stays out of shareable outputs. Each
report is rendered from a run written over the fake server by the real client and store, as `run`
writes it; R01-T16 checks the same through the CLI.
"""

import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from tests.core.conftest import CONFIGS, RESPONSES, WriteRun, Written
from tests.support.fake_portfolio123 import Reply
from tests.support.html_report import Document, Element, parse
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
from trialfolio.report import FULL_NOTICE_ID, HtmlReportRenderer

FORMULA = (CONFIGS / "formula.yaml").read_bytes()
RANKING_NAME = (CONFIGS / "ranking-name.yaml").read_bytes()


def response(name: str) -> Reply:
    return Reply(200, (RESPONSES / name).read_bytes())


@pytest.fixture
def complete(write_run: WriteRun) -> Written:
    return write_run(FORMULA, response("complete.json"))


def table_with(document: Document, heading: str) -> Element:
    """The table after the `<h3>` whose text starts with `heading`."""
    (h3,) = (h for h in document.root.find_all("h3") if h.text.startswith(heading))
    return next(t for t in document.root.find_all("table") if document.before(h3, t))


def metric_rows(document: Document, heading: str) -> dict[str, list[str]]:
    """Each row of a metrics table, by its identifier: the text of its cells."""
    rows = document.rows(table_with(document, heading))[1:]
    return {row[0].find_all("code")[0].text: [cell.text for cell in row] for row in rows}


# The notices (R01-AC13)


def test_the_concise_notice_comes_before_any_result_and_links_to_the_full_notice(
    complete: Written,
) -> None:
    document = parse(complete.html)
    notice = document.root.by_id("notice")
    (link,) = notice.find_all("a")

    assert notice.text == CONCISE_NOTICE
    assert link.attrs["href"] == f"#{FULL_NOTICE_ID}"
    assert document.root.by_id(FULL_NOTICE_ID).tag == "details"
    for later in (*document.root.find_all("section"), *document.root.find_all("table")):
        assert document.before(notice, later)


def test_the_full_notice_is_in_a_details_element_with_the_license(complete: Written) -> None:
    document = parse(complete.html)
    details = document.root.by_id(FULL_NOTICE_ID)
    paragraphs = [p.text for p in details.find_all("p")]
    links = [a.attrs["href"] for a in details.find_all("a")]

    assert paragraphs[: len(FULL_NOTICE)] == list(FULL_NOTICE)
    assert LICENSE_NAME in details.text
    assert LICENSE_ID in details.text
    assert f"Notice version {NOTICE_VERSION}." in details.text
    assert links == ["https://github.com/promptedportfolio/trialfolio/blob/v0.1.0/LICENSE"]


def test_the_portfolio123_data_statement_closes_the_report_before_the_full_notice(
    complete: Written,
) -> None:
    document = parse(complete.html)
    closing = document.root.by_id("closing")
    details = document.root.by_id(FULL_NOTICE_ID)
    (statement,) = (p for p in closing.find_all("p") if p.text.startswith("Portfolio123 data."))
    (terms,) = statement.find_all("a")

    assert statement.text == f"{PORTFOLIO123_DATA_LABEL} {PORTFOLIO123_DATA_STATEMENT}"
    assert terms.text == "Portfolio123's terms"
    assert terms.attrs["href"] == PORTFOLIO123_TERMS_URL
    assert not statement.inside(details)
    assert document.before(statement, details)
    assert details.inside(closing)
    for section in document.root.find_all("section"):
        assert document.before(section, closing)


def test_its_only_outside_links_are_the_license_and_portfolio123s_terms(
    complete: Written,
) -> None:
    document = parse(complete.html)
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    ids = {element.attrs.get("id") for element in document.root.iter()}
    outside = {href for href in hrefs if urlsplit(href).scheme or urlsplit(href).netloc}
    relative = [href for href in hrefs if href not in outside and not href.startswith("#")]

    assert outside == {license_url("0.1.0"), PORTFOLIO123_TERMS_URL}
    for href in hrefs:
        if href.startswith("#"):
            assert href[1:] in ids
    for href in relative:
        assert not href.startswith("/")
        target = (complete.out / unquote(href)).resolve()
        assert target.is_file()
        assert target.is_relative_to(complete.out.resolve())
    assert {unquote(href) for href in relative} == {
        "manifest.json",
        *(artifact.path for artifact in complete.manifest.artifacts if artifact.role != "report"),
    }


@pytest.mark.parametrize(
    ("configuration", "reply", "synthetic"),
    [
        (FORMULA, response("complete.json"), False),
        (FORMULA, response("complete.json"), True),
        (FORMULA, Reply(400, b"Unsupported value"), False),
        (FORMULA, response("invalid-structure.json"), False),
    ],
    ids=["completed", "synthetic", "failed", "invalid-response"],
)
def test_it_runs_and_loads_nothing(
    write_run: WriteRun, configuration: bytes, reply: Reply, synthetic: bool
) -> None:
    written = write_run(configuration, reply, synthetic=synthetic)
    document = parse(written.html)
    elements = list(document.root.iter())
    (style,) = document.root.find_all("style")

    assert document.declarations == ("DOCTYPE html",)
    assert not [e for e in elements if e.tag in ("script", "link", "iframe", "object", "embed")]
    assert not [e for e in elements if e.tag in ("img", "base", "form", "svg")]
    assert not [name for e in elements for name in e.attrs if name.startswith("on")]
    assert not [e for e in elements if "src" in e.attrs or "style" in e.attrs]
    assert not [e for e in elements if e.tag == "meta" and "http-equiv" in e.attrs]
    assert not re.search(r"url\s*\(|@import", style.text, re.IGNORECASE)


def test_statistical_validation_and_trading_readiness_read_not_assessed(
    complete: Written,
) -> None:
    document = parse(complete.html)

    assert set(document.dd("Statistical validation")) == {"Not assessed"}
    assert set(document.dd("Trading readiness")) == {"Not assessed"}
    assert "Statistical validation: Not assessed." in document.root.by_id("statistics").text
    assert "Trading readiness: Not assessed." in document.root.by_id("feasibility").text


def test_no_status_is_styled_as_a_pass(write_run: WriteRun) -> None:
    """Every color in the stylesheet is a neutral gray, and no status element has its own
    styling, so a completed run looks like a failed one (REQ-13)."""
    completed = parse(write_run(FORMULA, response("complete.json")).html)
    failed = parse(write_run(FORMULA, Reply(400, b"Unsupported value")).html)
    (style,) = completed.root.find_all("style")

    for color in re.findall(r"#([0-9a-fA-F]{6})\b", style.text):
        channels = [int(color[i : i + 2], 16) for i in (0, 2, 4)]
        assert max(channels) - min(channels) <= 40, color
    for document in (completed, failed):
        (outcome,) = (
            dd
            for dl in document.root.find_all("dl")
            for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd"), strict=True)
            if dt.text == "Run outcome"
        )
        assert outcome.attrs == {}


# Sections, and what the evidence can't support


def test_every_section_appears_in_order(complete: Written) -> None:
    sections = parse(complete.html).root.find_all("section")

    assert [s.attrs["id"] for s in sections] == [
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
    assert [s.find_all("h2")[0].text.split(".")[0] for s in sections] == [
        str(n) for n in range(1, 11)
    ]


def test_sections_the_evidence_cant_support_say_so(complete: Written) -> None:
    document = parse(complete.html)

    assert document.dd("Objective")[0].startswith("Unavailable:")
    assert "Changes from a baseline Unavailable:" in document.root.by_id("definitions").text
    assert document.root.by_id("robustness").text.endswith(
        "Not assessed. Robustness results and the concentration of contributions need more than"
        " one run's summary statistics, and Trial Folio doesn't assess them."
    )
    assert "Unavailable:" in document.root.by_id("evidence").text
    assert "Exposures Unavailable:" in document.root.by_id("results").text


def test_a_run_without_a_purpose_says_none_was_declared(write_run: WriteRun) -> None:
    configuration = b"".join(
        line for line in FORMULA.splitlines(keepends=True) if not line.startswith(b"purpose:")
    )
    document = parse(write_run(configuration, response("complete.json")).html)

    assert "Declared purpose No purpose was declared." in document.root.by_id("objective").text


def test_results_are_labeled_backtested_and_a_synthetic_run_synthetic(
    write_run: WriteRun,
) -> None:
    real = parse(write_run(FORMULA, response("complete.json")).html)
    synthetic = parse(write_run(FORMULA, response("complete.json"), synthetic=True).html)

    assert real.dd("Results")[0].startswith("Backtested:")
    assert not [e for e in real.root.iter() if e.attrs.get("class") == "synthetic"]
    assert synthetic.dd("Results")[0].startswith("Synthetic:")
    (banner,) = (e for e in synthetic.root.iter() if e.attrs.get("class") == "synthetic")
    assert banner.text.startswith("Synthetic example.")
    assert "Synthetic example" in synthetic.root.find_all("header")[0].find_all("p")[0].text
    assert synthetic.dd("Approval") == ["Not required: the synthetic run sends nothing."]


def test_a_synthetic_runs_report_never_calls_it_a_backtest_or_its_values_portfolio123s(
    write_run: WriteRun,
) -> None:
    real = parse(write_run(FORMULA, response("complete.json")).html)
    synthetic = parse(write_run(FORMULA, response("complete.json"), synthetic=True).html)
    claims = {
        "definitions": "read from Portfolio123's response",
        "data": "captured from Portfolio123's response, by this run",
        "results": "The risk statistics are Portfolio123's",
        "cases": "Portfolio123 returned a response",
        "evidence": "the run is one backtest",
    }

    for section, claim in claims.items():
        assert claim in real.root.by_id(section).text
        assert claim not in synthetic.root.find_all("main")[0].text
    assert "invented response" in synthetic.root.by_id("definitions").text
    assert "Here it comes from the run's configuration or its invented response" in (
        synthetic.root.by_id("data").text
    )
    assert "The risk statistics are invented" in synthetic.root.by_id("results").text
    assert "the run is one synthetic example" in synthetic.root.by_id("evidence").text


# Values, units, and unavailable metrics (R01-AC12)


def test_each_metric_shows_exactly_its_digits_with_its_unit(complete: Written) -> None:
    document = parse(complete.html)
    assert complete.saved.metrics is not None
    tables = {
        "strategy": metric_rows(document, "Strategy"),
        "benchmark": metric_rows(document, "Benchmark"),
    }

    shown = 0
    for row in complete.saved.metrics:
        if row.metric_id.startswith("coverage_"):
            continue
        _, value, unit, decimals, provenance, source = tables[row.subject][row.metric_id]
        assert (value, unit, provenance, source) == (
            row.value,
            row.unit,
            row.provenance,
            row.source_location,
        )
        assert decimals == ("" if row.source_decimals is None else str(row.source_decimals))
        shown += 1
    assert shown == 17
    # Never padded to the requested precision of 4.
    assert tables["benchmark"]["annualized_return"][1] == "12.3"


def test_an_unavailable_metric_shows_its_reason_and_never_zero(write_run: WriteRun) -> None:
    document = parse(write_run(FORMULA, response("missing-metrics.json")).html)
    strategy = metric_rows(document, "Strategy")
    benchmark = metric_rows(document, "Benchmark")
    missing = document.root.by_id("data").find_all("ul")[-1]

    for cells, reason in (
        (strategy["sortino_ratio"], "blank_in_source"),
        (strategy["beta"], "blank_in_source"),
        (benchmark["sharpe_ratio"], "unparseable_in_source"),
    ):
        assert cells[1].startswith(f"Unavailable ({reason}):")
        assert not re.search(r"[0-9]", cells[1])
        assert cells[3] == ""
    assert [li.text.split(":")[0] for li in missing.find_all("li")] == [
        "Sortino ratio, strategy (sortino_ratio)",
        "Beta, strategy (beta)",
        "Sharpe ratio, benchmark (sharpe_ratio)",
    ]
    assert "3 of 20 metrics are unavailable. None is shown as zero." in (
        document.root.by_id("data").text
    )


# Coverage (R01-AC31)


def coverage(document: Document) -> list[list[str]]:
    rows = document.rows(table_with(document, "Coverage"))
    return [[cell.text for cell in row] for row in rows[1:]]


def test_coverage_equal_to_the_requested_dates_matches(complete: Written) -> None:
    assert coverage(parse(complete.html)) == [
        ["Coverage start", "2016-01-01", "2016-01-01", "date", "Matches"],
        ["Coverage end", "2025-12-31", "2025-12-31", "date", "Matches"],
        ["Coverage periods", "", "4", "count", ""],
    ]


def test_coverage_that_differs_shows_both_dates_and_the_mismatch(write_run: WriteRun) -> None:
    document = parse(write_run(FORMULA, response("coverage-mismatch.json")).html)
    mismatch = "Differs: flagged coverage_mismatch"

    assert coverage(document)[:2] == [
        ["Coverage start", "2016-01-01", "2016-01-04", "date", mismatch],
        ["Coverage end", "2025-12-31", "2025-12-26", "date", mismatch],
    ]
    assert "The coverage differs from the requested start_date and end_date." in (
        document.root.by_id("conclusion").text
    )


def test_without_periods_the_report_says_the_coverage_couldnt_be_established(
    write_run: WriteRun,
) -> None:
    document = parse(write_run(FORMULA, response("no-periods.json")).html)
    rows = coverage(document)

    assert "The coverage couldn't be established" in document.root.by_id("data").text
    assert [row[4] for row in rows[:2]] == ["Couldn't be established"] * 2
    assert [row[2].split(":")[0] for row in rows[:2]] == ["Unavailable (blank_in_source)"] * 2
    assert rows[2][2] == "0"
    assert "Matches" not in document.root.by_id("data").text


# Settings and reproducibility (R01-AC10)


def settings(document: Document) -> dict[str, list[str]]:
    """Each row of the settings table, by setting: the text of its cells, with the flags cell
    reduced to its codes, separated by semicolons."""
    rows = document.rows(table_with(document, "All settings"))
    return {
        row[0].text: [
            ";".join(code.text for code in cell.find_all("code")) if index == 5 else cell.text
            for index, cell in enumerate(row)
        ]
        for row in rows[1:]
    }


def test_every_setting_shows_its_value_unit_provenance_flags_and_text_as_written(
    complete: Written,
) -> None:
    shown = settings(parse(complete.html))
    assert complete.saved.settings is not None

    assert list(shown) == [row.setting for row in complete.saved.settings]
    for row in complete.saved.settings:
        _, category, value, unit, provenance, flags, original, _ = shown[row.setting]
        assert (category, value, unit, provenance, original) == (
            row.category,
            row.value,
            row.unit or "",
            row.provenance,
            " ".join((row.original_value or "").split()),
        )
        assert flags == ";".join(row.flags)
    assert shown["commission"][-1].startswith("Portfolio123's API: Screen page documents no")
    assert shown["max_pos_pct"][-1] == (
        "Not sent. Portfolio123's default applies, and it isn't documented."
    )


def test_a_ranking_by_name_labels_reproducibility_incomplete(write_run: WriteRun) -> None:
    by_name = parse(write_run(RANKING_NAME, response("complete.json")).html)
    by_formula = parse(write_run(FORMULA, response("complete.json")).html)

    assert settings(by_name)["ranking"][5] == "not_snapshotted"
    assert settings(by_formula)["ranking"][5] == ""
    assert (
        "Reproducibility is incomplete: universe and ranking name objects in the Portfolio123"
        " account whose definition wasn't captured."
    ) in by_name.root.by_id("conclusion").text
    assert (
        "Reproducibility is incomplete: universe names an object in the Portfolio123 account"
    ) in by_formula.root.by_id("conclusion").text


# Runs that didn't complete


def test_a_failed_run_accounts_for_its_attempt_and_shows_no_result(write_run: WriteRun) -> None:
    written = write_run(FORMULA, Reply(400, b"Unsupported value"))
    document = parse(written.html)
    cases = document.root.by_id("cases")
    results = document.root.by_id("results")

    assert document.dd("Run outcome") == [
        "failed (provider.unsupported_capability). An execution status, not a research finding."
    ]
    assert document.dd("Outcome")[0].startswith("failed:")
    assert document.dd("Error")[0].startswith("provider.unsupported_capability: Portfolio123")
    assert document.dd("Error")[0].endswith('Portfolio123\'s message: "Unsupported value"')
    assert document.dd("Possibly charged") == ["Yes"]
    exchanges = [[c.text for c in row] for row in document.rows(cases.find_all("table")[0])[1:]]
    assert exchanges == [
        ["1", "POST /auth", "Response", "200", ""],
        ["2", "POST /screen/backtest", "Response", "400", ""],
    ]
    assert (
        "The normalized result is unavailable: no attempt succeeded, so there's no response to"
        " normalize."
    ) in results.text
    assert "Strategy" not in [h.text for h in results.find_all("h3")]
    assert "Expected provenance" in [th.text for th in results.find_all("th")]
    assert "The run didn't complete: it ended with provider.unsupported_capability." in (
        document.root.by_id("conclusion").text
    )


def test_a_failed_authentication_shows_nothing_was_charged(write_run: WriteRun) -> None:
    document = parse(write_run(FORMULA, authentication=Reply(401, b"")).html)

    assert document.dd("Possibly charged") == ["No"]
    assert document.dd("Provider requests") == [
        (
            "0: the sends that may have reached Portfolio123, which may be charged even when they"
            " fail. Authentication isn't counted."
        ),
        "0",
    ]
    assert "None: the run saved no response." in document.root.by_id("data").text


def test_a_response_without_the_required_structure_shows_the_result_unavailable(
    write_run: WriteRun,
) -> None:
    document = parse(write_run(FORMULA, response("invalid-structure.json")).html)

    assert document.dd("Run outcome")[0].startswith("failed (provider.response_invalid)")
    assert document.dd("Outcome")[0].startswith("succeeded:")
    assert (
        "The normalized result is unavailable: the saved response doesn't have the layout's"
        " required structure, so it wasn't normalized."
    ) in document.root.by_id("results").text


def test_an_undecodable_response_shows_the_result_unavailable(write_run: WriteRun) -> None:
    document = parse(write_run(FORMULA, Reply(200, b"<html>not JSON</html>")).html)

    assert (
        "the response couldn't be decoded as JSON, so it was saved as it came, and wasn't"
        " normalized."
    ) in document.root.by_id("results").text
    assert "None. The response is kept whole, as it came, undecoded." in (
        document.root.by_id("data").text
    )


# What the report holds, and doesn't


def test_text_from_the_configuration_cant_add_markup_or_reorder_whats_shown(
    write_run: WriteRun,
) -> None:
    override = chr(0x202E)
    title = f"<script>alert(1)</script> & {override}evil"
    rule = 'Close(0) < 5 and Name != "</code><b>bold"'
    configuration = (
        FORMULA.decode()
        .replace("title: Earnings yield with a liquidity floor", f"title: '{title}'")
        .replace("  - 'AvgDailyTot(30) > 1000000'", f"  - '{rule}'")
        .encode()
    )
    written = write_run(configuration, response("complete.json"))
    document = parse(written.html)
    shown = "<script>alert(1)</script> & \\u202eevil"

    assert not document.root.find_all("script")
    assert not document.root.find_all("b")
    assert override not in written.html
    assert document.root.find_all("h1")[0].text == shown
    assert document.root.find_all("title")[0].text.startswith(shown)
    assert settings(document)["rules"][2] == f'["{rule.replace(chr(34), chr(92) + chr(34))}"]'


def test_the_account_quota_stays_out(write_run: WriteRun) -> None:
    # complete.json's quota, 4321, can turn up by chance in the report's hashes and attempt ID.
    # Fifteen digits can't: a given 15-character run of hex digits is about one in 10^18.
    quota = 864209753186420
    body = json.loads((RESPONSES / "complete.json").read_bytes())
    body["quotaRemaining"] = quota
    written = write_run(FORMULA, Reply(200, json.dumps(body).encode()))
    attempt = written.saved.attempts[0].record
    assert attempt is not None
    assert attempt.provider_metadata.quota_remaining == quota

    assert str(quota) not in written.html
    assert "quota" not in written.html.lower()
    assert parse(written.html).dd("Cost")[0] == "5 credits, as Portfolio123 reported"


def test_rendering_is_deterministic_and_names_its_version(complete: Written) -> None:
    renderer = HtmlReportRenderer("0.1.0")

    assert renderer.render(complete.saved, "") == complete.html
    later = parse(HtmlReportRenderer("0.2.3").render(complete.saved, ""))
    details = later.root.by_id(FULL_NOTICE_ID)
    assert [a.attrs["href"] for a in details.find_all("a")] == [license_url("0.2.3")]
    assert later.dd("Report rendered by") == ["Trial Folio 0.2.3"]
    assert later.dd("Run written by")[0].startswith("Trial Folio 0.1.0")


def test_the_renderer_needs_a_version_and_a_relative_run_path(complete: Written) -> None:
    for version in ("v0.1.0", "0.1", "01.0.0", ""):
        with pytest.raises(ValueError, match="major"):
            HtmlReportRenderer(version)
    for run_path in ("/runs/baseline", "runs//baseline", "./runs"):
        with pytest.raises(ValueError, match="relative"):
            HtmlReportRenderer("0.1.0").render(complete.saved, run_path)


def test_the_report_is_written_into_the_run(complete: Written) -> None:
    report = complete.out / "report.html"

    assert complete.report.path == "report.html"
    assert report.read_bytes().decode("utf-8") == complete.html
    assert not report.read_bytes().startswith(b"\xef\xbb\xbf")
    assert Path(report).stat().st_size == complete.report.size
