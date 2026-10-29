"""An experiment session's report is one self-contained, script-free HTML file, as a run's is: the
notices, only the two outside links D-21 allows and the experiment's own files, and "Not
assessed". It shows every planned case in the plan's order, with its key, `case_id`, change,
description, and outcome; each case's metrics side by side, without a difference; the retired
cases; every plan with its reason; each repeat with the attempt it repeated; and each case
awaiting a repeat with the option that repeats it. Nothing is sorted, ranked, or marked by a
metric's value (docs/contracts.md, reports and the experiment manifest).

Traces, at the core, to R03-AC11 (every case and its outcome, the retired cases, each revision
with its reason, each repeat with the attempt it repeated, each case awaiting a repeat with the
option that repeats it, the prior-research declaration, which Trial Folio can't verify, no
performance-based selection, "Not assessed", R01-AC13's rules, and a synthetic experiment's
invented values), and to the report's part of R03-AC08 (the report shows each count, equal to
the manifest's, and a case whose repeat's authentication failed as still `unknown`, by its latest
possibly charged attempt). The rest trace to the experiment report's rules in docs/contracts.md:
its status, the baseline's settings, the coverage, the sources and exclusions, the versions,
section 7's statement of METH-03.2, and the limitations. The two tests of the singular in the
missing values trace to R03-AC11's report wording, and to the owner's decision of 2026-10-11 to
write one unavailable metric, and one case with normalized tables, in the singular. R03-T11's
`tests/interface/test_experiment_report.py` checks the report through the command.

Each experiment is written through the core during the test, over the fake server, as another
interface would write it, and the test reads the session's report from its directory. Every
expected value is written here by hand.
"""

import logging
import re
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from tests.support.clock import STARTED
from tests.support.experiment_lab import RELEASE_0_3_0, Lab, Ran
from tests.support.fake_portfolio123 import AUTHENTICATED, FakePortfolio123, Reply, response
from tests.support.html_report import Document, Element, parse
from tests.support.paths import EXPERIMENT_CONFIGS, RESPONSES
from trialfolio.contracts.experiment_manifest import ExperimentCommandRecord, ExperimentManifest
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution import ExperimentExecution, SessionStarted
from trialfolio.experiment_repeats import Repeat
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
from trialfolio.planning import installed_versions
from trialfolio.report import FULL_NOTICE_ID, ExperimentEvidence, HtmlReportRenderer

VERSION = installed_versions().trialfolio

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

# example.yaml's cases, in the plan's order, and holdings-40.yaml's new case.
BASELINE = "case-e29404ddebf86363"
LIQUIDITY = "case-b5d8a262354ab93d"
HOLDINGS_50 = "case-edb681850dd8e058"
WEEKLY = "case-0492159b4461ceff"
SLIPPAGE = "case-5dd6bf5d608d3956"
HOLDINGS_40 = "case-7982075205fd72cd"

REPLACES = "Replaces the rule AvgDailyTot(30) > 1000000 with AvgDailyTot(30) > 100000000"
LIQUIDITY_DESCRIPTION = "A stricter liquidity floor, 100 million dollars a day."
SUCCEEDED = "succeeded: its response was saved and normalized."


EXAMPLE = (EXPERIMENT_CONFIGS / "example.yaml").read_bytes()


@dataclass(frozen=True)
class Session:
    """A session the core ran, and the report it wrote."""

    number: int
    plan: PlanV1_1
    error: TrialFolioError | None
    execution: ExperimentExecution
    html: str
    manifest: ExperimentManifest
    out: Path

    @property
    def document(self) -> Document:
        return parse(self.html)

    @property
    def evidence(self) -> ExperimentEvidence:
        evidence = self.execution.evidence
        assert evidence is not None
        return evidence

    def attempt_ids(self, case_id: str) -> list[uuid.UUID]:
        """The case's attempts' IDs, in the order they were made."""
        view = next(
            view
            for view in (*self.evidence.cases, *self.evidence.retired)
            if view.case.case_id == case_id
        )
        return [attempt.attempt_id for attempt in view.attempts]


def session_of(ran: Ran) -> Session:
    """The session `ran` ran, with the report and the manifest it wrote."""
    (number,) = (event.session for event in ran.events if isinstance(event, SessionStarted))
    session = ran.out / "sessions" / str(number)
    assert isinstance(ran.plan, PlanV1_1)
    return Session(
        number=number,
        plan=ran.plan,
        error=ran.error,
        execution=ran.executed,
        html=(session / "report.html").read_text(encoding="utf-8"),
        manifest=ran.manifest(number, ExperimentManifest),
        out=ran.out,
    )


def _completed(lab: Lab, *, swapped: bool = False) -> list[Session]:
    """`example.yaml`, every case succeeded: `liquidity-100m` with `changed-metrics.json`, or
    `slippage-050` when swapped, `holdings-50` with metrics missing, and `rebalance-weeks-1`
    with coverage that differs from the requested dates."""
    changed, unchanged = response("changed-metrics.json"), response("complete.json")
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        response("complete.json"),
        unchanged if swapped else changed,
        response("missing-metrics.json"),
        response("coverage-mismatch.json"),
        changed if swapped else unchanged,
    )
    return [session_of(lab.new("example.yaml"))]


def _troubled(lab: Lab, tmp: Path) -> list[Session]:
    """`example.yaml`, with an `unknown` baseline (a 503), a rejected `holdings-50` (a 400),
    and a `liquidity-100m` whose response lacks the layout's structure; then a revision to
    `holdings-40`, with a budget of 8, that repeats the baseline."""
    lab.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        Reply(503),
        response("invalid-structure.json"),
        Reply(400),
        response("complete.json"),
        response("complete.json"),
    )
    first = session_of(lab.new("example.yaml"))
    (unknown,) = first.attempt_ids(BASELINE)
    lab.server.reply("/screen/backtest", response("complete.json"), response("complete.json"))
    revised = (EXPERIMENT_CONFIGS / "revisions" / "holdings-40.yaml").read_bytes()
    revised = revised.replace(b"provider_requests: 6", b"provider_requests: 8")
    second = session_of(
        lab.resume(
            "revisions/holdings-40.yaml",
            content=revised,
            reason="Holdings of 40, between the two.",
            repeats=[Repeat(BASELINE, unknown)],
        )
    )
    return [first, second]


def _stopped(lab: Lab) -> list[Session]:
    """`default-only.yaml`, whose authentication call gets a 401, so the baseline fails before
    its request is sent, and the default variant isn't started (D-32)."""
    lab.server.reply("/auth", Reply(401))
    return [session_of(lab.new("default-only.yaml"))]


def _repeated(lab: Lab) -> list[Session]:
    """`default-only.yaml`, with a budget of 4: an `unknown` baseline (a 503), and a default
    variant whose response has no periods, so its coverage can't be established; then a repeat
    of the baseline whose authentication call gets a 401, so it sends nothing; then, by a
    `trialfolio run` command, a repeat of the baseline that gets a 400."""
    content = (EXPERIMENT_CONFIGS / "default-only.yaml").read_bytes()
    content = content.replace(b"provider_requests: 2", b"provider_requests: 4")
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), response("no-periods.json"))
    first = session_of(lab.new("default-only.yaml", content=content))
    (unknown,) = first.attempt_ids(BASELINE)
    repeat = Repeat(BASELINE, unknown)
    lab.server.reply("/auth", Reply(401))
    refused = session_of(lab.resume("default-only.yaml", content=content, repeats=[repeat]))
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(400))
    command = ExperimentCommandRecord(
        name="run",
        options={
            "approve": first.plan.plan_hash,
            "json": False,
            "revision_reason": False,
            "repeat": True,
        },
        started_at=STARTED,
    )
    third = lab.resume("default-only.yaml", content=content, repeats=[repeat], command=command)
    return [first, refused, session_of(third)]


def _one_missing(lab: Lab) -> list[Session]:
    """`default-only.yaml`, both cases succeeded: the baseline with `complete.json`, and the
    default variant with `complete.json` whose `stats.beta` is `null`, its one missing metric."""
    complete = (RESPONSES / "complete.json").read_bytes()
    assert b'"beta": 1.04,' in complete
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply(
        "/screen/backtest",
        Reply(200, complete),
        Reply(200, complete.replace(b'"beta": 1.04,', b'"beta": null,')),
    )
    return [session_of(lab.new("default-only.yaml"))]


def _synthetic(lab: Lab) -> list[Session]:
    return [session_of(lab.new("default-only.yaml", synthetic=True))]


HOSTILE = f"<script>alert(1)</script> & {chr(0x202E)}evil"
SHOWN = "<script>alert(1)</script> & \\u202eevil"


def _hostile(lab: Lab) -> list[Session]:
    """`example.yaml` with markup and a bidirectional override in its title, purpose, prior
    research, and a variant's description, and then a revision whose reason holds them too."""
    quoted = f"'{HOSTILE}'".encode()
    content = EXAMPLE
    for line in (
        b"title: Earnings yield sensitivity",
        (
            b"purpose: How do holdings, slippage, and a stricter liquidity rule change the"
            b" earnings-yield screen's results?"
        ),
        (
            b"  description: Earlier backtests of this screen in the Portfolio123 website compared"
            b" 25 and 50 holdings. Other variations tried there weren't recorded."
        ),
        b"      description: A stricter liquidity floor, 100 million dollars a day.",
    ):
        key, _, _ = line.partition(b": ")
        assert line in content
        content = content.replace(line, key + b": " + quoted)
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", *(response("complete.json") for _ in range(5)))
    first = session_of(lab.new("example.yaml", content=content))
    raised = content.replace(b"provider_requests: 6", b"provider_requests: 7")
    second = lab.resume("example.yaml", content=raised, reason=f"</td><b>bold</b>{HOSTILE}")
    return [first, session_of(second)]


SCENARIOS: dict[str, Callable[[Lab, Path], list[Session]]] = {
    "completed": lambda lab, _: _completed(lab),
    "swapped": lambda lab, _: _completed(lab, swapped=True),
    "troubled": _troubled,
    "stopped": lambda lab, _: _stopped(lab),
    "repeated": lambda lab, _: _repeated(lab),
    "one-missing": lambda lab, _: _one_missing(lab),
    "synthetic": lambda lab, _: _synthetic(lab),
    "hostile": lambda lab, _: _hostile(lab),
}

type Sessions = Callable[[str], list[Session]]


@pytest.fixture(scope="module")
def sessions(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Sessions]:
    """Writes each scenario's experiment once for the module, and gives its sessions."""
    root = tmp_path_factory.mktemp("experiments")
    written: dict[str, list[Session]] = {}
    servers: list[FakePortfolio123] = []

    def get(name: str) -> list[Session]:
        if name not in written:
            lab = Lab(root / name, FakePortfolio123(), reader=RELEASE_0_3_0)
            servers.append(lab.server)
            written[name] = SCENARIOS[name](lab, root)
        return written[name]

    yield get
    for server in servers:
        server.close()


def cells(document: Document, table: Element) -> list[list[str]]:
    """Each body row's cells, as text."""
    return [[cell.text for cell in row] for row in document.rows(table)[1:]]


def table_after(document: Document, heading: str) -> list[list[str]]:
    return cells(document, document.table_after(heading))


def header(document: Document, heading: str) -> list[str]:
    return [cell.text for cell in document.rows(document.table_after(heading))[0]]


def items_after(document: Document, heading: str) -> list[str]:
    """The text of each item of the first list after the `<h3>` whose text is `heading`."""
    (h3,) = (h for h in document.root.find_all("h3") if h.text == heading)
    first = next(ul for ul in document.root.find_all("ul") if document.before(h3, ul))
    return [li.text for li in first.find_all("li")]


def attempts_table(document: Document, caption: str) -> list[list[str]]:
    (table,) = (
        table
        for table in document.root.by_id("cases").find_all("table")
        if any(c.text == caption for c in table.find_all("caption"))
    )
    return cells(document, table)


# What the report holds, and doesn't (R01-AC13's rules)

NOTICES = ["completed", "troubled", "synthetic"]


@pytest.mark.parametrize("name", NOTICES)
def test_the_concise_notice_comes_before_any_result_and_links_to_the_full_notice(
    sessions: Sessions, name: str
) -> None:
    document = sessions(name)[-1].document
    notice = document.root.by_id("notice")
    (link,) = notice.find_all("a")

    assert notice.text == CONCISE_NOTICE
    assert link.attrs["href"] == f"#{FULL_NOTICE_ID}"
    assert document.root.by_id(FULL_NOTICE_ID).tag == "details"
    for later in (*document.root.find_all("section"), *document.root.find_all("table")):
        assert document.before(notice, later)


@pytest.mark.parametrize("name", NOTICES)
def test_the_data_statement_and_the_full_notice_with_the_license_close_the_report(
    sessions: Sessions, name: str
) -> None:
    document = sessions(name)[-1].document
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
    assert LICENSE_ID == "LicenseRef-NSPRL-1.1"
    assert LICENSE_ID in details.text
    assert f"Notice version {NOTICE_VERSION}." in details.text
    assert [a.attrs["href"] for a in details.find_all("a")] == [license_url(VERSION)]
    for section in document.root.find_all("section"):
        assert document.before(section, closing)


@pytest.mark.parametrize("name", NOTICES)
def test_its_links_are_the_two_outside_links_and_the_experiments_own_files(
    sessions: Sessions, name: str
) -> None:
    session = sessions(name)[-1]
    document = session.document
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    ids = {element.attrs.get("id") for element in document.root.iter()}
    outside = {href for href in hrefs if urlsplit(href).scheme or urlsplit(href).netloc}
    relative = [href for href in hrefs if href not in outside and not href.startswith("#")]
    directory = session.out / "sessions" / str(session.number)

    assert outside == {license_url(VERSION), PORTFOLIO123_TERMS_URL}
    for href in hrefs:
        if href.startswith("#"):
            assert href[1:] in ids
    linked: set[str] = set()
    for href in relative:
        assert not href.startswith("/")
        assert href.startswith("../../")
        target = (directory / unquote(href)).resolve()
        assert target.is_file()
        assert target.is_relative_to(session.out.resolve())
        linked.add(target.relative_to(session.out.resolve()).as_posix())
    assert linked == {
        f"sessions/{session.number}/manifest.json",
        *(a.path for a in session.manifest.artifacts if a.role != "report"),
    }


@pytest.mark.parametrize("name", NOTICES)
def test_it_runs_and_loads_nothing(sessions: Sessions, name: str) -> None:
    document = sessions(name)[-1].document
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
    sessions: Sessions, name: str
) -> None:
    document = sessions(name)[-1].document

    assert set(document.dd("Statistical validation")) == {"Not assessed"}
    assert set(document.dd("Trading readiness")) == {"Not assessed"}
    assert "Statistical validation: Not assessed." in document.root.by_id("statistics").text
    assert "Trading readiness: Not assessed." in document.root.by_id("feasibility").text
    assert document.root.by_id("robustness").text.startswith(
        "6. Robustness and concentration Not assessed."
    )


def test_every_section_appears_in_order(sessions: Sessions) -> None:
    document = sessions("completed")[0].document
    sections = document.root.find_all("section")

    assert [s.attrs["id"] for s in sections] == SECTIONS
    assert [s.find_all("h2")[0].text for s in sections] == [
        "1. Objective, purpose, and research status",
        "2. Definitions, and changes from the baseline",
        "3. Data sources, coverage, provenance, and missing values",
        "4. Returns, risks, costs, and assumptions",
        "5. Cases and attempts",
        "6. Robustness and concentration",
        "7. Statistical methods and uncertainty",
        "8. Development, selection, holdout, and forward evidence",
        "9. Feasibility, capacity, and missing execution evidence",
        "10. Conclusion, limitations, and artifacts",
    ]
    assert document.root.find_all("h1")[0].text == "Earnings yield sensitivity"
    assert document.root.find_all("title")[0].text == (
        "Earnings yield sensitivity · Trial Folio experiment report"
    )
    assert document.root.find_all("p")[0].text == "Trial Folio experiment report"
    assert document.dd("Session 1 outcome") == [
        "completed. An execution status, not a research finding."
    ]
    assert document.dd("Results") == [
        (
            "Backtested: from applying each case's screen rules to historical data, not from actual"
            " trades."
        )
    ]
    assert document.dd("Objective") == [
        (
            "Unavailable: an experiment declares no research objective or criteria, only its title,"
            " purpose, and prior research."
        )
    ]
    assert "Exposures Unavailable: the responses report no exposures." in (
        document.root.by_id("results").text
    )
    assert document.root.by_id("evidence").text == (
        "8. Development, selection, holdout, and forward evidence Unavailable: each case is a"
        " backtest over the same requested dates. The experiment has no separate development,"
        " selection, holdout, or forward period. Backtested: from applying each case's screen"
        " rules to historical data, not from actual trades."
    )


# Every case and its outcome (R03-AC11)


def test_every_planned_case_appears_in_the_plans_order_with_its_outcome(
    sessions: Sessions,
) -> None:
    document = sessions("completed")[0].document

    assert header(document, "Planned cases") == [
        "Case",
        "case_id",
        "Change",
        "Description",
        "Outcome",
        "Attempts",
    ]
    assert table_after(document, "Planned cases") == [
        ["baseline", BASELINE, "The baseline", "", SUCCEEDED, "1"],
        ["liquidity-100m", LIQUIDITY, REPLACES, LIQUIDITY_DESCRIPTION, SUCCEEDED, "1"],
        ["holdings-50", HOLDINGS_50, "max_holdings set to 50", "", SUCCEEDED, "1"],
        [
            "rebalance-weeks-1",
            WEEKLY,
            "rebalance_weeks set to 1, the default rebalance variant",
            "",
            SUCCEEDED,
            "1",
        ],
        ["slippage-050", SLIPPAGE, "slippage_percent set to 0.5", "", SUCCEEDED, "1"],
    ]
    assert table_after(document, "Changes from the baseline") == [
        row[:4] for row in table_after(document, "Planned cases")
    ]


def test_each_outcome_says_what_it_means_and_what_sends_the_case(sessions: Sessions) -> None:
    troubled = sessions("troubled")[0].document
    stopped = sessions("stopped")[0].document

    assert [row[4] for row in table_after(troubled, "Planned cases")] == [
        (
            "unknown (provider.outcome_unknown): its request may have been charged, and no"
            " response was saved. Awaiting a repeat."
        ),
        # From D-45, a case whose response failed validation awaits a repeat.
        (
            "failed (provider.response_invalid): its response was saved, but failed validation,"
            " so it wasn't normalized. Awaiting a repeat."
        ),
        (
            "failed (provider.unsupported_capability): its request may have reached"
            " Portfolio123, and may have been charged. Awaiting a repeat."
        ),
        SUCCEEDED,
        SUCCEEDED,
    ]
    assert [row[4] for row in table_after(stopped, "Planned cases")] == [
        (
            "failed (provider.auth_failed): no attempt's request could have reached"
            " Portfolio123. A resume sends it, within the budget."
        ),
        "not_yet_run: it has no attempt. A resume sends it, within the budget.",
    ]
    assert table_after(stopped, "Planned cases")[1][5] == "0"


def test_a_case_awaiting_a_repeat_is_marked_with_the_option_that_repeats_it(
    sessions: Sessions,
) -> None:
    session = sessions("troubled")[0]
    document = session.document
    (unknown,) = session.attempt_ids(BASELINE)
    (invalid,) = session.attempt_ids(LIQUIDITY)
    (rejected,) = session.attempt_ids(HOLDINGS_50)

    # From D-45, `liquidity-100m`, whose response failed validation, awaits a repeat too.
    assert items_after(document, "Cases awaiting a repeat") == [
        (
            f"baseline, {BASELINE}: attempt {unknown}, unknown (provider.outcome_unknown). The"
            f" option that repeats it: --repeat baseline:{unknown}"
        ),
        (
            f"liquidity-100m, {LIQUIDITY}: attempt {invalid}, succeeded, its response failed"
            " validation (provider.response_invalid). The option that repeats it: --repeat"
            f" liquidity-100m:{invalid}"
        ),
        (
            f"holdings-50, {HOLDINGS_50}: attempt {rejected}, failed"
            " (provider.unsupported_capability). The option that repeats it: --repeat"
            f" holdings-50:{rejected}"
        ),
    ]
    assert (
        "A case awaiting a repeat has an attempt whose request may have reached Portfolio123,"
        " and so may have been charged, and no attempt that succeeded with a response that"
        " passed validation. A resume never sends its request again on its own. A repeat sends"
        " it again, as a new attempt of the same case, which may be charged again, and counts"
        " against the budget. Each case is listed with its latest attempt whose request may have"
        " been charged. Running the experiment again"
        " with the option given below for a case, and the plan's approval, repeats it: the"
        " option confirms the possible repeat charge, by naming the attempt."
    ) in document.root.by_id("cases").text


def test_the_option_and_the_outcome_follow_the_latest_possibly_charged_attempt(
    sessions: Sessions,
) -> None:
    # A repeat whose authentication call got a 401 sent nothing: the case is still unknown, by
    # its latest possibly charged attempt (R03-AC08), and the option names that attempt, whose
    # confirmation nothing used. A later repeat that got a 400 is then the latest.
    _, refused, rejected = sessions("repeated")
    unknown, unsent = refused.attempt_ids(BASELINE)
    *_, latest = rejected.attempt_ids(BASELINE)

    assert table_after(refused.document, "Planned cases")[0][4:] == [
        (
            "unknown (provider.outcome_unknown): its request may have been charged, and no"
            " response was saved. Awaiting a repeat."
        ),
        "2, 1 of them a repeat",
    ]
    assert items_after(refused.document, "Cases awaiting a repeat") == [
        (
            f"baseline, {BASELINE}: attempt {unknown}, unknown (provider.outcome_unknown). The"
            f" option that repeats it: --repeat baseline:{unknown}"
        )
    ]
    row = attempts_table(refused.document, f"baseline, {BASELINE}")[1]
    assert [row[0], *row[4:6], row[6].split(":")[0], *row[7:]] == [
        str(unsent),
        "failed",
        "No",
        "provider.auth_failed",
        f"Repeats attempt {unknown}",
        "POST /auth: Response 401",
    ]
    assert table_after(rejected.document, "Planned cases")[0][4:] == [
        (
            "failed (provider.unsupported_capability): its request may have reached"
            " Portfolio123, and may have been charged. Awaiting a repeat."
        ),
        "3, 2 of them repeats",
    ]
    assert items_after(rejected.document, "Cases awaiting a repeat") == [
        (
            f"baseline, {BASELINE}: attempt {latest}, failed (provider.unsupported_capability)."
            f" The option that repeats it: --repeat baseline:{latest}"
        )
    ]


def test_no_case_is_marked_awaiting_a_repeat_once_none_is(sessions: Sessions) -> None:
    for name in ("completed", "stopped"):
        cases = sessions(name)[0].document.root.by_id("cases").text

        assert (
            "Cases awaiting a repeat None: no planned case has a request that may have been"
            " charged without succeeding."
        ) in cases
        assert "--repeat" not in cases


def test_each_repeat_names_the_attempt_it_repeated(sessions: Sessions) -> None:
    session = sessions("troubled")[1]
    document = session.document
    unknown, repeat = session.attempt_ids(BASELINE)
    first, second = attempts_table(document, f"baseline, {BASELINE}")

    assert first[:6] == [str(unknown), "1 · 1", "1", first[3], "unknown", "Yes"]
    assert first[6].startswith("provider.outcome_unknown: Portfolio123 answered the screen")
    assert first[7:] == [
        "",
        "POST /auth: Response 200 POST /screen/backtest: Response 503",
    ]
    assert second[:3] == [str(repeat), "2 · 1", "2"]
    assert second[4:] == [
        "succeeded",
        "Yes",
        "",
        f"Repeats attempt {unknown}",
        "POST /auth: Response 200 POST /screen/backtest: Response 200",
    ]
    assert table_after(document, "Planned cases")[0][4:] == [SUCCEEDED, "2, 1 of them a repeat"]
    assert document.dd("Repeats") == [
        "1: the attempts that repeat a case, each after a confirmation"
    ]


def test_each_plan_appears_with_its_reason_and_what_changed(sessions: Sessions) -> None:
    first, second = sessions("troubled")
    document = second.document

    assert table_after(document, "Plans and revisions") == [
        ["1", first.plan.plan_hash, "option", "None: the first plan", "The first plan"],
        [
            "2 (current)",
            second.plan.plan_hash,
            "option",
            "Holdings of 40, between the two.",
            (
                f"Cases added: holdings-50 ({HOLDINGS_40}) Cases retired: holdings-50"
                f" ({HOLDINGS_50}) Other parts changed: budget"
            ),
        ],
    ]
    assert items_after(document, "Plans and revisions") == [
        "option: Approved with the plan's full hash, as --approve gives it."
    ]
    assert table_after(first.document, "Plans and revisions") == [
        ["1 (current)", first.plan.plan_hash, "option", "None: the first plan", "The first plan"]
    ]


def test_the_retired_cases_appear_with_their_attempts(sessions: Sessions) -> None:
    session = sessions("troubled")[1]
    document = session.document
    (rejected,) = session.attempt_ids(HOLDINGS_50)

    assert table_after(document, "Retired cases") == [
        ["holdings-50", HOLDINGS_50, "max_holdings set to 50", "", "1", "failed", "1"]
    ]
    (row,) = attempts_table(document, f"holdings-50 (retired), {HOLDINGS_50}")
    assert row[:3] == [str(rejected), "1 · 3", "1"]
    assert row[4:6] == ["failed", "Yes"]
    assert table_after(document, "Planned cases")[2] == [
        "holdings-50",
        HOLDINGS_40,
        "max_holdings set to 40",
        "",
        SUCCEEDED,
        "1",
    ]
    assert "Retired cases None: no revision retired a case." in (
        sessions("completed")[0].document.root.by_id("cases").text
    )


def test_every_attempt_appears_under_its_case_in_the_order_it_was_made(
    sessions: Sessions,
) -> None:
    document = sessions("troubled")[1].document
    captions = [caption.text for caption in document.root.by_id("cases").find_all("caption")]

    assert captions == [
        f"baseline, {BASELINE}",
        f"liquidity-100m, {LIQUIDITY}",
        f"holdings-50, {HOLDINGS_40}",
        f"rebalance-weeks-1, {WEEKLY}",
        f"slippage-050, {SLIPPAGE}",
        f"holdings-50 (retired), {HOLDINGS_50}",
    ]
    places = [row[1] for caption in captions for row in attempts_table(document, caption)]
    assert places == ["1 · 1", "2 · 1", "1 · 2", "2 · 2", "1 · 4", "1 · 5", "1 · 3"]
    assert attempts_table(document, f"liquidity-100m, {LIQUIDITY}")[0][6] == ""


def test_the_prior_research_declaration_says_trial_folio_cant_verify_it(
    sessions: Sessions,
) -> None:
    objective = sessions("completed")[0].document.root.by_id("objective").text

    assert (
        "Declared prior research Status: partial: the description accounts for some of the"
        " earlier outcome-informed work on this idea, and there was more that it doesn't"
        " describe. Earlier backtests of this screen in the Portfolio123 website compared 25"
        " and 50 holdings. Other variations tried there weren't recorded. Trial Folio records"
        " the declaration as the user supplied it, and can't verify it."
    ) in objective
    assert (
        "Declared purpose How do holdings, slippage, and a stricter liquidity rule change the"
        " earnings-yield screen's results?"
    ) in objective


def test_an_unknown_declaration_without_a_description_says_none_was_declared(
    sessions: Sessions,
) -> None:
    evidence = sessions("completed")[0].evidence
    plan = evidence.plan.model_copy(
        update={
            "prior_research": evidence.plan.prior_research.model_copy(
                update={"status": "unknown", "description": None}
            )
        }
    )
    document = parse(HtmlReportRenderer(VERSION).render_experiment(replace(evidence, plan=plan)))

    assert (
        "Status: unknown: the user can't say what earlier outcome-informed work on this idea"
        " there was. No description was declared."
    ) in document.root.by_id("objective").text


# No performance-based selection (R03-AC11)


def _without_values(session: Session) -> str:
    """The report's main text, without the attempt IDs, which are random, and without the
    values and sizes that come from each case's response."""
    document = session.document
    main = document.root.find_all("main")[0]
    text = main.text
    for heading in ("Strategy", "Benchmark: SPY", "Artifacts"):
        table = document.table_after(heading)
        text = text.replace(table.text, "")
    return re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", "", text)


def test_swapping_two_cases_responses_changes_no_order_or_mark(sessions: Sessions) -> None:
    (completed,) = sessions("completed")
    (swapped,) = sessions("swapped")
    before, after = completed.document, swapped.document

    assert _without_values(completed) == _without_values(swapped)
    for heading in ("Strategy", "Benchmark: SPY"):
        assert (
            header(before, heading)
            == header(after, heading)
            == [
                "Metric",
                "Unit",
                "baseline",
                "liquidity-100m",
                "holdings-50",
                "rebalance-weeks-1",
                "slippage-050",
            ]
        )
        columns = [list(column) for column in zip(*table_after(before, heading), strict=True)]
        swapped_columns = [
            list(column) for column in zip(*table_after(after, heading), strict=True)
        ]
        assert swapped_columns == [*columns[:3], columns[6], *columns[4:6], columns[3]]
    # Nothing in the report marks a case: no element is styled or emphasized for one.
    for document in (before, after):
        classes = {e.attrs.get("class") for e in document.root.iter()}
        assert classes == {None, "page", "kind", "notice", "wide", "long", "muted"}
        assert not [e for e in document.root.find_all("main")[0].iter() if e.tag in ("mark", "b")]
        strong = [e.text for e in document.root.find_all("main")[0].find_all("strong")]
        assert strong == []


def test_no_case_is_called_best_or_ranked(sessions: Sessions) -> None:
    for name in ("completed", "troubled"):
        main = sessions(name)[-1].document.root.find_all("main")[0].text

        assert re.findall(r"[^.]*\bbest\b[^.]*\.", main) == [
            " No case is ranked, selected, or called best."
        ]
        assert "That's a statement about execution, not about any strategy." in main
        assert (
            "this report permits no conclusion about whether any case's strategy is useful, or"
            " whether its results could be achieved."
        ) in main


def test_each_cases_metrics_are_side_by_side_as_its_table_holds_them(
    sessions: Sessions,
) -> None:
    document = sessions("completed")[0].document
    strategy = {row[0].split()[-1]: row for row in table_after(document, "Strategy")}
    benchmark = {row[0].split()[-1]: row for row in table_after(document, "Benchmark: SPY")}

    assert list(strategy) == [
        "total_return",
        "annualized_return",
        "max_drawdown",
        "standard_deviation",
        "sharpe_ratio",
        "sortino_ratio",
        "correlation",
        "r_squared",
        "beta",
        "alpha",
        "risk_samples",
    ]
    assert strategy["total_return"] == [
        "Total return total_return",
        "percent",
        "151.7",
        "151.68",
        "151.7",
        "151.7",
        "151.7",
    ]
    assert strategy["sortino_ratio"][2:] == [
        "0.8842",
        "0.9105",
        "Unavailable (blank_in_source)",
        "0.8842",
        "0.8842",
    ]
    assert strategy["beta"] == [
        "Beta vs. SPY beta",
        "ratio",
        "1.04",
        "1.1",
        "Unavailable (blank_in_source)",
        "1.04",
        "1.04",
    ]
    assert benchmark["sharpe_ratio"][2:] == [
        "0.7712",
        "0.7712",
        "Unavailable (unparseable_in_source)",
        "0.7712",
        "0.7712",
    ]
    captions = [c.text for c in document.root.by_id("results").find_all("caption")]
    assert captions == [
        "The cases' rows cover different periods; the coverage above gives each.",
        "The cases' rows cover different periods; the coverage above gives each.",
    ]
    assert (
        "Each case's metrics, as its metrics.csv holds them, side by side in the plan's order."
        " Each value has exactly the digits the response carries, never padded or rounded. The"
        " risk statistics are Portfolio123's, for the period the settings give as"
        " risk_stats_period. The report computes no difference between cases, and orders,"
        " ranks, and marks no case by a value."
    ) in document.root.by_id("results").text


def test_a_case_without_tables_isnt_shown_beside_the_others_and_says_why(
    sessions: Sessions,
) -> None:
    first, second = sessions("troubled")
    results = first.document.root.by_id("results").text

    assert header(first.document, "Strategy")[2:] == ["rebalance-weeks-1", "slippage-050"]
    assert (
        "Not shown, without normalized tables: baseline, liquidity-100m, and holdings-50. The"
        " coverage above says why."
    ) in results
    assert [row[4] for row in table_after(first.document, "Coverage")] == [
        "Unavailable: no attempt of it succeeded, so there's no response to normalize.",
        (
            "Unavailable: its saved response doesn't have the layout's required structure, so it"
            " wasn't normalized."
        ),
        "Unavailable: no attempt of it succeeded, so there's no response to normalize.",
        "Matches",
        "Matches",
    ]
    assert (
        "The retired cases' tables are kept in their directories, and listed among the"
        " artifacts. They aren't shown here."
    ) in second.document.root.by_id("results").text
    stopped = sessions("stopped")[0].document
    assert (
        "Unavailable: no planned case has normalized tables, so there are no metrics to show."
        in (stopped.root.by_id("results").text)
    )
    assert table_after(stopped, "Coverage")[1][4] == "Unavailable: it hasn't been run yet."


def test_each_cases_coverage_is_compared_with_the_requested_dates(sessions: Sessions) -> None:
    document = sessions("completed")[0].document

    assert table_after(document, "Coverage") == [
        ["baseline", "2016-01-01", "2025-12-31", "4", "Matches"],
        ["liquidity-100m", "2016-01-01", "2025-12-31", "4", "Matches"],
        ["holdings-50", "2016-01-01", "2025-12-31", "4", "Matches"],
        [
            "rebalance-weeks-1",
            "2016-01-04",
            "2025-12-26",
            "4",
            (
                "The start differs, flagged coverage_mismatch and the end differs, flagged"
                " coverage_mismatch."
            ),
        ],
        ["slippage-050", "2016-01-01", "2025-12-31", "4", "Matches"],
    ]
    assert (
        "compared with the requested dates, which every case shares: 2016-01-01 to 2025-12-31."
    ) in document.root.by_id("data").text


def test_coverage_that_couldnt_be_established_is_never_shown_as_matching(
    sessions: Sessions,
) -> None:
    # The default variant's response has no periods.
    document = sessions("repeated")[0].document

    assert table_after(document, "Coverage")[1] == [
        "rebalance-weeks-1",
        "Unavailable (blank_in_source)",
        "Unavailable (blank_in_source)",
        "0",
        "The start couldn't be established and the end couldn't be established.",
    ]


def test_the_baseline_settings_are_its_settings_csvs_or_else_the_plans(
    sessions: Sessions,
) -> None:
    recorded = sessions("completed")[0].document
    planned = sessions("troubled")[0].document
    heading = "The baseline's settings"

    assert (
        "As the baseline's settings.csv records them. As written is the value's text in the"
        " experiment configuration."
    ) in recorded.root.by_id("definitions").text
    assert header(recorded, heading)[4] == "Provenance"
    assert table_after(recorded, heading)[8] == [
        "start_date",
        "dates",
        "2016-01-01",
        "",
        "verified",
        "",
        "2016-01-01",
        "",
    ]
    # troubled's baseline is unknown, so it has no settings.csv.
    assert (
        "The baseline has no settings.csv, so these are the plan's resolved settings, each with"
        " the provenance the plan expects it to have once the request is sent."
    ) in planned.root.by_id("definitions").text
    assert header(planned, heading) == [
        "Setting",
        "Category",
        "Value",
        "Unit",
        "Expected provenance",
        "Flags",
        "As written",
        "Notes",
    ]
    assert table_after(planned, heading)[8] == [
        "start_date",
        "dates",
        "2016-01-01",
        "",
        "verified",
        "",
        "",
        "",
    ]


def test_the_layout_and_the_per_period_series_are_named_once_a_response_has_them(
    sessions: Sessions,
) -> None:
    saved = sessions("completed")[0].document
    unsaved = sessions("stopped")[0].document
    missing = [
        "Actual trades: none.",
        (
            "Commission: Not modeled by this provider path: the API documents no commission"
            " parameter, and slippage is its only trading-cost input."
        ),
        (
            "Parameters not sent, whose defaults aren't documented: max_pos_pct, rank_tolerance,"
            " carry_cost, long_weight, short_weight."
        ),
    ]

    assert saved.dd("Response layout") == ["p123api-screen-backtest version 1, parser version 1"]
    assert saved.root.by_id("data").text.endswith(
        "Exclusions None. Trial Folio excludes nothing from the saved responses, and keeps each"
        " whole, as it was saved. Their per-period series are preserved there, but not"
        " interpreted."
    )
    assert [li.text for li in saved.root.by_id("feasibility").find_all("li")] == [
        *missing,
        (
            "Turnover, positions, and per-period returns: preserved in the saved responses, but"
            " not interpreted."
        ),
    ]
    assert unsaved.dd("Response layout") == [
        "Unavailable: no planned case's response was normalized."
    ]
    assert unsaved.root.by_id("data").text.endswith(
        "Exclusions None: the experiment saved no response."
    )
    assert [li.text for li in unsaved.root.by_id("feasibility").find_all("li")] == missing


def test_the_missing_values_name_their_case_and_reason(sessions: Sessions) -> None:
    document = sessions("completed")[0].document

    assert table_after(document, "Missing values") == [
        [
            "holdings-50",
            "Sortino ratio, strategy (sortino_ratio)",
            "Unavailable (blank_in_source): The response gives no value for it.",
        ],
        [
            "holdings-50",
            "Beta, strategy (beta)",
            "Unavailable (blank_in_source): The response gives no value for it.",
        ],
        [
            "holdings-50",
            "Sharpe ratio, benchmark (sharpe_ratio)",
            (
                "Unavailable (unparseable_in_source): Its value couldn't be interpreted. The saved"
                " response keeps it as it came."
            ),
        ],
    ]
    assert (
        "3 metrics are unavailable, across the 5 cases with normalized tables. None is shown as"
        " zero."
    ) in document.root.by_id("data").text


def test_one_unavailable_metric_is_written_in_the_singular(sessions: Sessions) -> None:
    # The owner's decision of 2026-10-11. Both cases have tables, so only the metric is singular.
    document = sessions("one-missing")[0].document

    assert table_after(document, "Missing values") == [
        [
            "rebalance-weeks-1",
            "Beta, strategy (beta)",
            "Unavailable (blank_in_source): The response gives no value for it.",
        ]
    ]
    assert (
        "1 metric is unavailable, across the 2 cases with normalized tables. None is shown as zero."
    ) in document.root.by_id("data").text
    assert "1 metric is unavailable, with its reason above." in items_after(document, "Limitations")


def test_one_case_with_normalized_tables_is_written_in_the_singular(sessions: Sessions) -> None:
    # The owner's decision of 2026-10-11. The baseline is `unknown`, so only the default variant
    # has tables, and its response has no periods, so two of its metrics are unavailable.
    document = sessions("repeated")[0].document

    assert (
        "2 metrics are unavailable, across the 1 case with normalized tables. None is shown as"
        " zero."
    ) in document.root.by_id("data").text
    assert "2 metrics are unavailable, with their reasons above." in items_after(
        document, "Limitations"
    )


def test_the_costs_and_assumptions_name_the_cases_that_change_them(sessions: Sessions) -> None:
    document = sessions("completed")[0].document

    assert table_after(document, "Costs") == [
        ["slippage_percent", "0.25", "percent", "slippage-050: 0.5", ""],
        [
            "commission",
            "not_modeled",
            "",
            "No case",
            (
                "Not modeled by this provider path: the API documents no commission parameter, and"
                " slippage is its only trading-cost input."
            ),
        ],
        [
            "carry_cost",
            "not_sent",
            "",
            "No case",
            "Not sent. Portfolio123's default applies, and it isn't documented.",
        ],
    ]
    assert table_after(document, "Implementation assumptions") == [
        ["transaction_price", "open", "", "No case", ""],
        ["rebalance_weeks", "4", "weeks", "rebalance-weeks-1: 1", ""],
        ["max_holdings", "25", "count", "holdings-50: 50", ""],
        ["pit_method", "complete", "", "No case", ""],
    ]


# The counts (R03-AC08's report part)


def test_the_report_shows_each_count_as_the_manifest_records_it(sessions: Sessions) -> None:
    first, second = sessions("troubled")
    *_, repeated = sessions("repeated")

    for session, expected in (
        (
            first,
            {
                "planned": "Planned cases: 5 = 2 succeeded + 2 failed + 0 skipped + 1 unknown + 0"
                " not yet run.",
                "Attempts": "3 succeeded, 1 failed, 1 unknown, 0 running",
                "Repeats": "0: the attempts that repeat a case, each after a confirmation",
                "Retired cases": "0",
                "Counted against the budget": (
                    "Provider requests: 5 of the budget's 6. Authentication calls: 1 of its 6."
                ),
                "Cost": "15 credits, as Portfolio123 reported",
            },
        ),
        (
            second,
            {
                "planned": "Planned cases: 5 = 4 succeeded + 1 failed + 0 skipped + 0 unknown + 0"
                " not yet run.",
                "Attempts": "5 succeeded, 1 failed, 1 unknown, 0 running",
                "Repeats": "1: the attempts that repeat a case, each after a confirmation",
                "Retired cases": "1",
                "Counted against the budget": (
                    "Provider requests: 7 of the budget's 8. Authentication calls: 2 of its 8."
                ),
                "Cost": "25 credits, as Portfolio123 reported",
            },
        ),
        (
            repeated,
            {
                "planned": "Planned cases: 2 = 1 succeeded + 1 failed + 0 skipped + 0 unknown + 0"
                " not yet run.",
                "Attempts": "1 succeeded, 2 failed, 1 unknown, 0 running",
                "Repeats": "2: the attempts that repeat a case, each after a confirmation",
                "Retired cases": "0",
                "Counted against the budget": (
                    "Provider requests: 3 of the budget's 4. Authentication calls: 3 of its 4."
                ),
                "Cost": "5 credits, as Portfolio123 reported",
            },
        ),
    ):
        document = session.document
        counts = session.manifest.counts
        cases = document.root.by_id("cases")

        assert cases.find_all("p")[0].text.startswith(expected["planned"])
        assert document.dd("Attempts") == [expected["Attempts"]]
        assert document.dd("Repeats") == [expected["Repeats"]]
        assert document.dd("Retired cases") == [expected["Retired cases"]]
        assert document.dd("Retries") == ["0"]
        assert document.dd("Counted against the budget")[0].startswith(
            expected["Counted against the budget"]
        )
        assert document.dd("Cost") == [expected["Cost"]]
        # The manifest records the same counts.
        shown = cases.find_all("p")[0].text
        assert (
            f"{counts.cases.planned} = {counts.cases.succeeded} succeeded + {counts.cases.failed}"
            f" failed + {counts.cases.skipped} skipped + {counts.cases.unknown} unknown +"
            f" {counts.cases.not_yet_run} not yet run."
        ) in shown
        assert document.dd("Attempts") == [
            (
                f"{counts.attempts.succeeded} succeeded, {counts.attempts.failed} failed,"
                f" {counts.attempts.unknown} unknown, {counts.attempts.running} running"
            )
        ]
        assert document.dd("Repeats")[0].startswith(f"{counts.attempts.repeats}:")
        assert document.dd("Retired cases") == [str(counts.retired_cases)]
        assert document.dd("Counted against the budget")[0].startswith(
            f"Provider requests: {counts.provider_requests} of the budget's"
            f" {counts.budget.provider_requests}. Authentication calls:"
            f" {counts.authentication_calls} of its {counts.budget.authentication_calls}."
        )
        assert document.dd("Cost") == [f"{counts.cost} credits, as Portfolio123 reported"]
    # A plan's two limits are equal, so the counts are rendered with limits that differ, to show
    # that each is the limit it's named as.
    evidence = first.evidence
    limits = evidence.counts.budget.model_copy(update={"authentication_calls": 9})
    counts = evidence.counts.model_copy(update={"budget": limits})
    document = parse(
        HtmlReportRenderer(VERSION).render_experiment(replace(evidence, counts=counts))
    )
    assert document.dd("Counted against the budget")[0].startswith(
        "Provider requests: 5 of the budget's 6. Authentication calls: 1 of its 9."
    )


def test_section_7_calls_the_counts_research_history_not_a_multiple_testing_family(
    sessions: Sessions,
) -> None:
    # METH-03.2. Between them, the two sessions give different values to each pair of counts.
    for session, counts in (
        (
            sessions("troubled")[1],
            (
                "The current plan has 5 cases, and revisions retired 1. Attempts made: 7, with 1"
                " repeat among them."
            ),
        ),
        (
            sessions("repeated")[2],
            (
                "The current plan has 2 cases, and revisions retired 0. Attempts made: 4, with 2"
                " repeats among them."
            ),
        ),
    ):
        statistics = session.document.root.by_id("statistics")

        assert [p.text for p in statistics.find_all("p")] == [
            (
                "Statistical validation: Not assessed. No statistical method was applied, so the"
                " report states no uncertainty, multiple-testing adjustment, or power. Summary"
                " statistics alone don't support intervals, a return series, or a drawdown"
                " history, so none is shown or reconstructed."
            ),
            (
                f"{counts} These counts are the experiment's research history, not a"
                " multiple-testing family: an attempt or a repeat is a provider operation, not a"
                " hypothesis, and a predefined variant isn't one either, unless its outcome"
                " informs a selection."
            ),
        ]


def test_the_plan_its_approval_and_the_budget_are_shown(sessions: Sessions) -> None:
    session = sessions("completed")[0]
    document = session.document

    assert document.dd("Plan") == [f"Plan 1, {session.plan.plan_hash}, the current plan"]
    assert document.dd("Approval") == ["Approved with the plan's full hash, as --approve gives it."]
    assert document.dd("Budget") == [
        (
            "6 provider requests, at most 30 credits at Portfolio123's documented cost (API: Screen,"
            " checked 2026-10-01), and at most 6 authentication calls, for every run of the"
            " experiment."
        )
    ]
    assert document.dd("Session written by") == [
        (
            f"Trial Folio {VERSION}, through its core, for an interface other than the trialfolio"
            " commands"
        )
    ]
    assert document.dd("Report rendered by") == [f"Trial Folio {VERSION}"]


def test_the_versions_name_the_command_that_wrote_the_session(sessions: Sessions) -> None:
    session = sessions("repeated")[2]

    assert session.manifest.command is not None
    assert session.document.dd("Session written by") == [
        f"Trial Folio {VERSION}, command run, started 2026-10-03T14:00:00Z"
    ]


def test_a_partial_sessions_status_gives_its_error_code(sessions: Sessions) -> None:
    assert sessions("troubled")[0].document.dd("Session 1 outcome") == [
        "partial (execution.partial). An execution status, not a research finding."
    ]


def test_the_conclusion_says_how_the_session_ended_and_permits_nothing_more(
    sessions: Sessions,
) -> None:
    completed = sessions("completed")[0].document.root.by_id("conclusion").text
    partial = sessions("troubled")[1].document.root.by_id("conclusion").text

    assert (
        "Permitted conclusion Every planned case succeeded: its response was saved and"
        " normalized. That's a statement about execution, not about any strategy."
    ) in completed
    assert (
        "Permitted conclusion Session 2 ended with execution.partial: 4 of the 5 planned cases"
        " succeeded, and section 5 gives each case's outcome."
    ) in partial
    assert (
        "This is session 2's report. Each later run of the experiment that reaches its end"
        " writes its own report and manifest, which supersede this one, and replaces no file."
    ) in partial
    assert (
        "The prior research is declared partial, and Trial Folio can't verify the declaration."
        " Earlier outcome-informed work on this idea isn't fully recorded, so a claim drawn"
        " from these cases is limited accordingly."
    ) in partial
    assert "No normalized result for liquidity-100m: section 5 gives each case's outcome." in (
        partial
    )
    assert items_after(sessions("completed")[0].document, "Limitations") == [
        (
            "Backtested: from applying each case's screen rules to historical data, not from"
            " actual trades."
        ),
        (
            "Reproducibility is incomplete: universe names an object in the Portfolio123 account"
            " whose definition wasn't captured. If it changes, the same configuration can give"
            " different results."
        ),
        (
            "Portfolio123's data and engines change, so sending a case's request again may give"
            " different results. A repeat is a new attempt, never a replacement."
        ),
        (
            "The prior research is declared partial, and Trial Folio can't verify the"
            " declaration. Earlier outcome-informed work on this idea isn't fully recorded, so a"
            " claim drawn from these cases is limited accordingly."
        ),
        "Inferred defaults, not reported by Portfolio123: data_vendor, risk_stats_period.",
        "The coverage differs from the requested dates for rebalance-weeks-1.",
        "3 metrics are unavailable, with their reasons above.",
        (
            "Only summary statistics are reported: no return series, drawdown history, or"
            " interval is shown."
        ),
        (
            "This is session 1's report. Each later run of the experiment that reaches its end"
            " writes its own report and manifest, which supersede this one, and replaces no file."
        ),
    ]


# A synthetic experiment (R03-AC11)

CLAIMS = [
    "read from each case's response from Portfolio123",
    "Portfolio123's screen backtest, through",
    "captured from Portfolio123's response, by the case's attempt",
    "each case is a backtest",
    "Backtested:",
    "The risk statistics are Portfolio123's",
    "Portfolio123's data and engines change",
    "Portfolio123's Sharpe ratio",
    "Portfolio123's Sortino ratio",
    "Portfolio123's alpha",
    "Cumulative return over the backtest",
    "Portfolio123's default applies",
    "as Portfolio123 reported",
]
"""What a real experiment's report says that calls a value Portfolio123's or a backtest's."""


def test_a_synthetic_experiments_report_says_its_values_are_invented(
    sessions: Sessions,
) -> None:
    document = sessions("synthetic")[0].document
    real = sessions("completed")[0].document.root.find_all("main")[0].text
    synthetic = document.root.find_all("main")[0].text
    (banner,) = (e for e in document.root.iter() if e.attrs.get("class") == "synthetic")

    for claim in CLAIMS:
        assert claim in real
        assert claim not in synthetic
    assert document.root.find_all("p")[0].text == (
        "Trial Folio experiment report · Synthetic experiment"
    )
    assert banner.text == (
        "Synthetic experiment. Trial Folio wrote this experiment with the demo's client, from"
        " invented values. Every value, attempt, and count in it is invented: none comes from"
        " Portfolio123, and nothing was sent to it or charged."
    )
    assert document.before(banner, document.root.by_id("objective"))
    assert document.dd("Results") == [
        "Synthetic: invented values, neither backtested nor actual results."
    ]
    assert document.dd("Approval") == ["Not required: the synthetic experiment sends nothing."]
    assert document.dd("Session written by") == [
        (
            f"Trial Folio {VERSION}, through its core, with the demo's client: no trialfolio"
            " command writes a synthetic experiment"
        )
    ]
    assert "Every value is invented." in document.root.by_id("results").text
    assert "The risk statistics are invented, as every value here is" in synthetic
    assert (
        "The experiment is synthetic, so its attempts, their exchanges, and the counts below"
        " are invented, as a real experiment would record them. Nothing was sent to"
        " Portfolio123, and nothing was charged."
    ) in synthetic
    assert "each case is a synthetic example over the same requested dates" in synthetic
    assert "Every planned case succeeded: its invented response was saved and normalized." in (
        synthetic
    )


def test_a_synthetic_case_awaiting_a_repeat_names_its_attempt_but_no_option(
    sessions: Sessions,
) -> None:
    """`trialfolio run` doesn't resume a synthetic experiment, so its report gives no option."""
    evidence = sessions("synthetic")[0].evidence
    view = evidence.cases[0]
    (attempt,) = view.attempts
    unknown = attempt.model_copy(update={"outcome": "unknown", "response": None})
    awaiting = replace(view, outcome="unknown", attempts=(unknown,), metrics=None, settings=None)
    document = parse(
        HtmlReportRenderer(VERSION).render_experiment(
            replace(evidence, cases=(awaiting, *evidence.cases[1:]))
        )
    )

    assert items_after(document, "Cases awaiting a repeat") == [
        f"baseline, {BASELINE}: attempt {attempt.attempt_id}, unknown."
    ]
    cases = document.root.by_id("cases").text
    assert "--repeat" not in cases
    assert (
        "trialfolio run doesn't resume a synthetic experiment: only Trial Folio's core repeats a"
        " case of one, with the demo's client, given the attempt below."
    ) in cases


# What the report holds, and how it's written


def test_text_from_the_configuration_or_the_reason_cant_add_markup_or_reorder_whats_shown(
    sessions: Sessions,
) -> None:
    first, second = sessions("hostile")
    document = second.document

    assert not document.root.find_all("script")
    assert not document.root.find_all("b")
    assert chr(0x202E) not in first.html
    assert chr(0x202E) not in second.html
    assert document.root.find_all("h1")[0].text == SHOWN
    assert document.root.find_all("title")[0].text.startswith(SHOWN)
    assert document.dd("Title") == [SHOWN]
    objective = document.root.by_id("objective").text
    assert f"Declared purpose {SHOWN}" in objective
    assert "Status: partial: " in objective
    assert f"there was more that it doesn't describe. {SHOWN} Trial Folio records" in objective
    assert table_after(document, "Planned cases")[1][3] == SHOWN
    assert table_after(document, "Plans and revisions")[1][3] == f"</td><b>bold</b>{SHOWN}"


def test_rendering_is_deterministic_and_names_its_version(sessions: Sessions) -> None:
    session = sessions("troubled")[1]

    assert HtmlReportRenderer(VERSION).render_experiment(session.evidence) == session.html
    later = parse(HtmlReportRenderer("0.4.1").render_experiment(session.evidence))
    details = later.root.by_id(FULL_NOTICE_ID)
    assert [a.attrs["href"] for a in details.find_all("a")] == [license_url("0.4.1")]
    assert later.dd("Report rendered by") == ["Trial Folio 0.4.1"]
    assert later.dd("Session written by")[0].startswith(f"Trial Folio {VERSION},")


def test_the_report_is_written_into_its_session_and_logs_no_content(
    tmp_path: Path, server: FakePortfolio123, caplog: pytest.LogCaptureFixture
) -> None:
    lab = Lab(tmp_path, server, reader=RELEASE_0_3_0)
    with caplog.at_level(logging.DEBUG, logger="trialfolio.report"):
        (session,) = _synthetic(lab)
    report = session.execution.report
    (record,) = (r for r in caplog.records if r.name == "trialfolio.report")

    assert report is not None
    assert report.path == "sessions/1/report.html"
    assert (tmp_path / "experiment" / report.path).read_bytes().decode("utf-8") == session.html
    assert not session.html.encode("utf-8").startswith(b"\xef\xbb\xbf")
    assert getattr(record, "event", None) == "report.render.completed"
    assert getattr(record, "plan_hash", None) == session.plan.plan_hash
    assert record.getMessage() == f"Rendered the session's report, {report.artifact_id}."


def test_the_evidence_needs_each_case_in_order_and_not_the_report(sessions: Sessions) -> None:
    evidence = sessions("troubled")[1].evidence
    report = next(
        artifact
        for artifact in sessions("troubled")[1].manifest.artifacts
        if artifact.role == "report"
    )

    with pytest.raises(ValueError, match="plan's order"):
        replace(evidence, cases=tuple(reversed(evidence.cases)))
    with pytest.raises(ValueError, match="record's order"):
        replace(evidence, retired=())
    with pytest.raises(ValueError, match="not the report"):
        replace(evidence, artifacts=(*evidence.artifacts, report))
    with pytest.raises(ValueError, match="both of its normalized tables"):
        replace(evidence.cases[0], settings=None)
    with pytest.raises(ValueError, match="only a case that succeeded"):
        replace(evidence.cases[0], outcome="failed")
    with pytest.raises(ValueError, match="order they were made"):
        replace(evidence.cases[0], attempts=tuple(reversed(evidence.cases[0].attempts)))
