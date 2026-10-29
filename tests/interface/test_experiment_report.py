"""What an experiment session's report holds, through the command: each `sessions/<s>/report.html`
`trialfolio run` writes, and the committed synthetic experiment's, read from a copy, each parsed
with `html.parser`.

Traces to R03-AC11's interface part (every planned case, in the plan's order, with its key,
`case_id`, description, change, and outcome; the retired cases; each revision with its reason;
each repeat with the attempt it repeated; each case awaiting a repeat with the option that repeats
it; the prior-research declaration, which Trial Folio can't verify; with two cases' responses
swapped, no order or mark changes, and no case is called best; and "Not assessed"), to R01-AC13's
rules as an experiment's report keeps them (the notices, `LicenseRef-NSPRL-1.1`, no script or
external resource, only the two outside links D-21 allows and the experiment's own files, and the
Portfolio123 data statement), and to DSC-04 (the synthetic experiment's report says its values are
invented, and never calls them Portfolio123's). tests/core/test_experiment_report.py checks the
same at the core, with the exact wording of each part.

The experiment builder writes each experiment once for the module, through the CLI's entry
function in the test process, over a fake server of its own: `example.yaml` with
`changed-metrics.json` for `liquidity-100m` and `complete.json` for the others, and again with
`liquidity-100m`'s and `slippage-050`'s responses swapped; R03-AC05's, with an unknown case, a
rejected one, and a 402 that stops the last; R03-AC07's revision to `holdings-40.yaml`; and
R03-AC14's repeats, the last after a revision that raises the budget. Expected values are written
here by hand, or read from the experiment's records, never from the code under test.
"""

import json
import re
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    REJECTED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    returns,
)
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.html_report import Document, Element, parse
from tests.support.synthetic_experiment import SYNTHETIC_EXPERIMENT
from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.notices import (
    CONCISE_NOTICE,
    FULL_NOTICE,
    PORTFOLIO123_DATA_LABEL,
    PORTFOLIO123_DATA_STATEMENT,
)

ROOT = Path(__file__).resolve().parents[2]
LICENSE_NAME = (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
"""The license's name, as LICENSE's first line gives it."""
TERMS_URL = "https://www.portfolio123.com/legal"

EXAMPLE = experiment_config("example.yaml")
KEYS = ("baseline", "liquidity-100m", "holdings-50", "rebalance-weeks-1", "slippage-050")
"""`example.yaml`'s cases, in the plan's order."""
PRIOR_RESEARCH = (
    "Earlier backtests of this screen in the Portfolio123 website compared 25 and 50 holdings."
    " Other variations tried there weren't recorded."
)
"""`example.yaml`'s prior-research description, declared `partial`."""
REASON = "Tries 40 holdings instead of 50."
"""The reason given for the revision to `holdings-40.yaml`."""
BUDGET_REASON = "Raises the budget for a repeat."
"""The reason given for the revision to `budget-raised.yaml`."""
SYNTHETIC_REASON = "Adds a holdings variant."
"""The reason the synthetic experiment's writer gave for its revision."""
QUOTA = Reply(402, b"")
"""A 402 to a case's request: `failed`, possibly charged, and no later case starts (D-32)."""

SUCCEEDED = ("succeeded",) * len(KEYS)


def license_url(version: str) -> str:
    """The LICENSE published with `version`, by its tag."""
    return f"https://github.com/promptedportfolio/trialfolio/blob/v{version}/LICENSE"


@dataclass(frozen=True)
class Session:
    """A session of an experiment, with the outcomes the test expects of its planned cases, in
    the plan's order."""

    out: Path
    number: int
    outcomes: tuple[str, ...]

    @property
    def document(self) -> Document:
        return parse((self.out / f"sessions/{self.number}/report.html").read_text(encoding="utf-8"))

    @property
    def manifest(self) -> ExperimentManifest:
        return ExperimentManifest.model_validate_json(
            (self.out / f"sessions/{self.number}/manifest.json").read_bytes()
        )

    @property
    def record(self) -> dict[str, object]:
        """The current plan's `experiment.json`, as JSON."""
        path = self.out / f"plans/{self.manifest.plan}/experiment.json"
        return cast("dict[str, object]", json.loads(path.read_bytes()))

    def planned(self) -> list[dict[str, object]]:
        return cast("list[dict[str, object]]", self.record["planned_cases"])

    def case_id(self, key: str) -> str:
        (case_id,) = (case["case_id"] for case in self.planned() if case["case_key"] == key)
        return cast("str", case_id)

    def attempts(self, case_id: str) -> list[AttemptRecordV1_1]:
        """The case's attempt records up to this session, by session and then sequence."""
        records = [
            AttemptRecordV1_1.model_validate_json(path.read_bytes())
            for path in (self.out / "cases" / case_id / "attempts").glob("*/attempt.json")
        ]
        made = [record for record in records if record.session <= self.number]
        return sorted(made, key=lambda record: (record.session, record.sequence))


type Scenario = Callable[[ExperimentBuilder[Outcome], Path], list[Session]]


def option(outcome: Outcome, key: str) -> str:
    """The `--repeat` value the summary gives to confirm a repeat of the case `key`."""
    cases = outcome.cases
    (attempt,) = (case["repeat_attempt_id"] for case in cases if case["case_key"] == key)
    return f"{key}:{attempt}"


def _completed(changed: str) -> Scenario:
    def write(experiments: ExperimentBuilder[Outcome], out: Path) -> list[Session]:
        sends = [
            returns("changed-metrics.json" if key == changed else "complete.json") for key in KEYS
        ]
        outcome = experiments.run(EXAMPLE, out, sends=sends)
        assert outcome.exit_code == 0, outcome.stderr
        return [Session(out, 1, SUCCEEDED)]

    return write


def _failed(experiments: ExperimentBuilder[Outcome], out: Path) -> list[Session]:
    # liquidity-100m's request gets a 503, holdings-50's a 400, and rebalance-weeks-1's a 402,
    # after which slippage-050 doesn't start.
    outcome = experiments.run(EXAMPLE, out, sends=[returns(), UNAVAILABLE, REJECTED, QUOTA])
    assert outcome.exit_code == 6, outcome.stderr
    return [Session(out, 1, ("succeeded", "unknown", "failed", "failed", "not_yet_run"))]


def _revised(experiments: ExperimentBuilder[Outcome], out: Path) -> list[Session]:
    first = experiments.run(EXAMPLE, out, sends=[returns() for _ in KEYS])
    assert first.exit_code == 0, first.stderr
    revised = experiments.run(
        experiment_config("revisions/holdings-40.yaml"),
        out,
        "--revision-reason",
        REASON,
        sends=[returns()],
    )
    assert revised.exit_code == 0, revised.stderr
    return [Session(out, 1, SUCCEEDED), Session(out, 2, SUCCEEDED)]


def _repeated(experiments: ExperimentBuilder[Outcome], out: Path) -> list[Session]:
    # holdings-50's request gets a 503, and its repeat a 503 too, which spends the budget of 6
    # provider requests; a revision that raises it to 8 then repeats it again, and it succeeds.
    awaiting = ("succeeded", "succeeded", "unknown", "succeeded", "succeeded")
    first = experiments.run(
        EXAMPLE, out, sends=[returns(), returns(), UNAVAILABLE, returns(), returns()]
    )
    assert first.exit_code == 6, first.stderr
    second = experiments.run(
        EXAMPLE, out, "--repeat", option(first, "holdings-50"), sends=[UNAVAILABLE]
    )
    assert second.exit_code == 6, second.stderr
    third = experiments.run(
        experiment_config("revisions/budget-raised.yaml"),
        out,
        "--revision-reason",
        BUDGET_REASON,
        "--repeat",
        option(second, "holdings-50"),
        sends=[returns()],
    )
    assert third.exit_code == 0, third.stderr
    return [Session(out, 1, awaiting), Session(out, 2, awaiting), Session(out, 3, SUCCEEDED)]


SCENARIOS: dict[str, Scenario] = {
    "completed": _completed("liquidity-100m"),
    "swapped": _completed("slippage-050"),
    "failed": _failed,
    "revised": _revised,
    "repeated": _repeated,
}

SYNTHETIC = ("succeeded",) * 2, ("succeeded",) * 3
"""The synthetic experiment's sessions' outcomes: its two cases, and then its revision's three."""

type Sessions = Callable[[str], list[Session]]


@pytest.fixture(scope="module")
def sessions(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Sessions]:
    """Writes each scenario's experiment once for the module, with the license acknowledged, the
    canary credentials, and a temporary home, and gives its sessions. `synthetic` is a copy of
    the committed synthetic experiment."""
    root = tmp_path_factory.mktemp("experiments")
    written: dict[str, list[Session]] = {}
    servers: list[FakePortfolio123] = []

    def get(name: str) -> list[Session]:
        if name not in written:
            directory = root / name
            # A scenario that failed fails each test that reads it, not only the first.
            assert not directory.exists(), f"the {name} experiment couldn't be written"
            directory.mkdir()
            out = directory / "experiment"
            if name == "synthetic":
                shutil.copytree(SYNTHETIC_EXPERIMENT, out)
                written[name] = [
                    Session(out, number, outcomes)
                    for number, outcomes in enumerate(SYNTHETIC, start=1)
                ]
            else:
                server = FakePortfolio123()
                servers.append(server)
                with pytest.MonkeyPatch.context() as monkeypatch:
                    cli = Cli(monkeypatch, directory, server)
                    cli.ready()
                    written[name] = SCENARIOS[name](ExperimentBuilder(server, cli), out)
        return written[name]

    yield get
    for server in servers:
        server.close()


def table(document: Document, heading: str) -> list[dict[str, str]]:
    """The body rows of the first table after the `<h3>` `heading`, each by its header's
    cells."""
    header, *rows = document.rows(document.table_after(heading))
    names = [cell.text for cell in header]
    return [dict(zip(names, (cell.text for cell in row), strict=True)) for row in rows]


def first_word(text: str) -> str:
    return re.split(r"[ :]", text)[0]


def assert_change(shown: str, variant: object) -> None:
    """The change shown is the variant's, as `experiment.json` records it: its setting and value,
    or each rule it adds, replaces, or puts in its place; or it says the case is the baseline."""
    if variant is None:
        assert "baseline" in shown.lower()
        return
    recorded = cast("dict[str, object]", variant)
    if recorded["value"] is not None:
        assert cast("str", recorded["setting"]) in shown
        assert str(recorded["value"]) in shown
    for rule in ("add", "replace", "with"):
        if recorded[rule] is not None:
            assert cast("str", recorded[rule]) in shown
    if recorded["default"]:
        assert "default" in shown


def attempts_table(document: Document, case_id: str, *, retired: bool = False) -> Element:
    """The attempts table of the case `case_id`, by its caption."""
    (found,) = (
        t
        for t in document.root.by_id("cases").find_all("table")
        if any(
            case_id in caption.text and ("(retired)" in caption.text) == retired
            for caption in t.find_all("caption")
        )
    )
    return found


def attempt_rows(document: Document, found: Element) -> dict[str, dict[str, str]]:
    """An attempts table's rows, each by its header's cells, by attempt ID."""
    header, *rows = document.rows(found)
    names = [cell.text for cell in header]
    by_name = [dict(zip(names, (cell.text for cell in row), strict=True)) for row in rows]
    return {row["Attempt"]: row for row in by_name}


def items_after(document: Document, heading: str) -> list[str]:
    """The text of each item of the list that directly follows the `<h3>` `heading`'s text, or
    none when a paragraph is all that does."""
    (h3,) = (h for h in document.root.find_all("h3") if h.text == heading)
    parent = h3.parent
    assert parent is not None
    siblings = [child for child in parent.children if isinstance(child, Element)]
    after = siblings[siblings.index(h3) + 1 :]
    following = next((e for e in after if e.tag in ("h3", "ul")), None)
    if following is None or following.tag != "ul":
        return []
    return [li.text for li in following.find_all("li")]


REAL = ["completed", "failed", "revised", "repeated"]
EVERY = [*REAL, "synthetic"]


# Every case and its outcome (R03-AC11)


@pytest.mark.parametrize("name", EVERY)
def test_every_planned_case_appears_in_the_plans_order_with_its_change_and_outcome(
    sessions: Sessions, name: str
) -> None:
    for session in sessions(name):
        rows = table(session.document, "Planned cases")
        planned = session.planned()

        assert [(row["Case"], row["case_id"], row["Description"]) for row in rows] == [
            (case["case_key"], case["case_id"], case["description"] or "") for case in planned
        ]
        for row, case in zip(rows, planned, strict=True):
            assert_change(row["Change"], case["variant"])
        assert tuple(first_word(row["Outcome"]) for row in rows) == session.outcomes
        if name != "synthetic":
            assert tuple(row["Case"] for row in rows) == KEYS


def test_the_retired_case_appears_with_its_last_plan_and_its_attempt(sessions: Sessions) -> None:
    first, second = sessions("revised")
    old = first.case_id("holdings-50")
    (retired,) = cast("list[dict[str, object]]", second.record["retired_cases"])

    (row,) = table(second.document, "Retired cases")

    assert (row["Case"], row["case_id"], row["Last plan"]) == ("holdings-50", old, "1")
    assert row["Description"] == (retired["description"] or "")
    assert_change(row["Change"], retired["variant"])
    assert first_word(row["Outcome"]) == "succeeded"
    (attempt,) = second.attempts(old)
    rows = attempt_rows(second.document, attempts_table(second.document, old, retired=True))
    assert list(rows) == [str(attempt.attempt_id)]
    # The new holdings-50 case is planned, with a case_id of its own; the first plan retired none.
    assert second.case_id("holdings-50") != old
    assert not [t for t in first.document.root.find_all("th") if t.text == "Last plan"]


@pytest.mark.parametrize(
    ("name", "reasons"),
    [
        ("completed", [None]),
        ("failed", [None]),
        ("revised", [None, REASON]),
        ("repeated", [None, BUDGET_REASON]),
        ("synthetic", [None, SYNTHETIC_REASON]),
    ],
)
def test_each_plan_appears_with_its_hash_and_approval_and_each_revision_with_its_reason(
    sessions: Sessions, name: str, reasons: list[str | None]
) -> None:
    for session in sessions(name):
        plans = cast("list[dict[str, object]]", session.record["plans"])
        rows = table(session.document, "Plans and revisions")

        # Every plan up to the session's, oldest first.
        assert [(first_word(row["Plan"]), row["Plan hash"], row["Approval"]) for row in rows] == [
            (str(entry["plan"]), entry["plan_hash"], entry["approval"]) for entry in plans
        ]
        for row, entry, reason in zip(rows, plans, reasons, strict=False):
            assert entry["reason"] == reason
            if reason is None:
                assert row["Reason"] not in ("", *(r for r in reasons if r is not None))
            else:
                assert row["Reason"] == reason
            # What the revision changed: the cases it added and retired, by case_id, and the
            # other parts.
            changes = cast("dict[str, list[object]] | None", entry["changes"])
            if changes is not None:
                added = cast("list[dict[str, str]]", changes["cases_added"])
                retired = cast("list[dict[str, str]]", changes["cases_retired"])
                for case in (*added, *retired):
                    assert case["case_id"] in row["Changes"]
                for part in cast("list[str]", changes["parts"]):
                    assert part in row["Changes"]
    # The revision to holdings-40.yaml adds the new holdings-50 case and retires the old one.
    if name == "revised":
        first, second = sessions(name)
        (row,) = table(second.document, "Plans and revisions")[1:]
        assert second.case_id("holdings-50") in row["Changes"]
        assert first.case_id("holdings-50") in row["Changes"]


def test_each_repeat_names_the_attempt_it_repeated(sessions: Sessions) -> None:
    _, second, third = sessions("repeated")
    case_id = third.case_id("holdings-50")
    unknown, repeat, last = third.attempts(case_id)
    # The second session repeated the first's attempt, and the third the second's.
    assert (unknown.repeat_of, repeat.repeat_of, last.repeat_of) == (
        None,
        unknown.attempt_id,
        repeat.attempt_id,
    )

    for session, attempts in ((second, (unknown, repeat)), (third, (unknown, repeat, last))):
        document = session.document
        rows = attempt_rows(document, attempts_table(document, case_id))

        assert list(rows) == [str(attempt.attempt_id) for attempt in attempts]
        for attempt in attempts:
            shown = rows[str(attempt.attempt_id)]["Repeats"]
            if attempt.repeat_of is None:
                assert shown == ""
            else:
                assert shown.split() == ["Repeats", "attempt", str(attempt.repeat_of)]


@pytest.mark.parametrize(
    ("name", "awaiting"),
    [
        ("completed", [[]]),
        ("failed", [["liquidity-100m", "holdings-50", "rebalance-weeks-1"]]),
        ("repeated", [["holdings-50"], ["holdings-50"], []]),
    ],
)
def test_each_case_awaiting_a_repeat_is_listed_with_the_option_that_repeats_it(
    sessions: Sessions, name: str, awaiting: list[list[str]]
) -> None:
    for session, keys in zip(sessions(name), awaiting, strict=True):
        document = session.document
        items = items_after(document, "Cases awaiting a repeat")

        assert len(items) == len(keys)
        for item, key in zip(items, keys, strict=True):
            case_id = session.case_id(key)
            # The option names the case's latest attempt that may have been charged.
            latest = [attempt for attempt in session.attempts(case_id) if attempt.possibly_charged]
            assert item.startswith(f"{key}, {case_id}: ")
            assert item.endswith(f" --repeat {key}:{latest[-1].attempt_id}")
        if not keys:
            assert "--repeat" not in document.root.by_id("cases").text


@pytest.mark.parametrize("name", EVERY)
def test_the_prior_research_declaration_is_shown_and_said_to_be_unverifiable(
    sessions: Sessions, name: str
) -> None:
    for session in sessions(name):
        objective = session.document.root.by_id("objective").text
        declared = cast("dict[str, str]", session.record["prior_research"])

        assert f"Status: {declared['status']}" in objective
        assert declared["description"] in objective
        assert re.search(r"Trial Folio [^.]*can't verify it\.", objective)
        if name != "synthetic":
            assert (declared["status"], declared["description"]) == ("partial", PRIOR_RESEARCH)


# No performance-based selection (R03-AC11)

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def without_values(document: Document) -> str:
    """The report's main text, without the metrics tables, which hold each case's values, the
    artifacts' table, whose IDs and sizes follow the responses, and the random attempt IDs."""
    text = document.root.find_all("main")[0].text
    for heading in ("Strategy", "Benchmark", "Artifacts"):
        text = text.replace(document.table_after(heading).text, "")
    return UUID.sub("", text)


def test_with_two_cases_responses_swapped_no_order_or_mark_changes(sessions: Sessions) -> None:
    (completed,) = sessions("completed")
    (swapped,) = sessions("swapped")
    before, after = completed.document, swapped.document
    liquidity, slippage = (2 + KEYS.index(key) for key in ("liquidity-100m", "slippage-050"))

    for heading in ("Strategy", "Benchmark"):
        shown = [before.rows(before.table_after(heading)), after.rows(after.table_after(heading))]
        headers = [[cell.text for cell in rows[0]] for rows in shown]
        # Each column a case's, in the plan's order, whatever its values.
        assert headers[0] == headers[1] == ["Metric", "Unit", *KEYS]
        columns = [
            [
                list(column)
                for column in zip(*([c.text for c in row] for row in rows[1:]), strict=True)
            ]
            for rows in shown
        ]
        if heading == "Strategy":
            # changed-metrics.json changes only the strategy's metrics.
            assert columns[0][liquidity] != columns[0][slippage]
        expected = list(columns[0])
        expected[liquidity], expected[slippage] = columns[0][slippage], columns[0][liquidity]
        assert columns[1] == expected
    assert table(before, "Planned cases") == table(after, "Planned cases")
    assert without_values(before) == without_values(after)
    # Nothing marks a case: no element is styled or emphasized for one.
    for document in (before, after):
        main = document.root.find_all("main")[0]
        assert not [e for e in main.iter() if e.tag in ("mark", "b", "strong", "u", "i")]
        assert not [e for e in main.iter() if "style" in e.attrs]
    classes = [{e.attrs.get("class") for e in d.root.iter()} for d in (before, after)]
    assert classes[0] == classes[1]


@pytest.mark.parametrize("name", REAL)
def test_no_case_is_called_best_or_ranked(sessions: Sessions, name: str) -> None:
    for session in sessions(name):
        main = session.document.root.find_all("main")[0].text
        said = re.findall(
            r"[^.]*\b(?:best|better|worse|ranks?|ranked|top|winner|wins|outperforms?)\b[^.]*\.",
            main,
            re.IGNORECASE,
        )

        # The conclusion says that no case is ranked or called best, and nothing says otherwise.
        assert said
        assert all("no case" in sentence.lower() for sentence in said), said


@pytest.mark.parametrize("name", EVERY)
def test_statistical_validation_and_trading_readiness_read_not_assessed(
    sessions: Sessions, name: str
) -> None:
    for session in sessions(name):
        document = session.document

        assert set(document.dd("Statistical validation")) == {"Not assessed"}
        assert set(document.dd("Trading readiness")) == {"Not assessed"}


# What the report holds, and doesn't (R01-AC13's rules)


@pytest.mark.parametrize("name", EVERY)
def test_the_concise_notice_comes_first_and_links_to_the_full_notice_with_the_license(
    sessions: Sessions, name: str
) -> None:
    for session in sessions(name):
        document = session.document
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
        version = session.manifest.trialfolio_version
        assert [a.attrs["href"] for a in full.find_all("a")] == [license_url(version)]


@pytest.mark.parametrize("name", EVERY)
def test_the_closing_section_holds_the_portfolio123_data_statement_outside_the_full_notice(
    sessions: Sessions, name: str
) -> None:
    for session in sessions(name):
        document = session.document
        (details,) = document.root.find_all("details")
        (footer,) = document.root.find_all("footer")
        (statement,) = (
            p for p in footer.find_all("p") if p.text.startswith(PORTFOLIO123_DATA_LABEL)
        )
        (terms,) = statement.find_all("a")

        assert statement.text == f"{PORTFOLIO123_DATA_LABEL} {PORTFOLIO123_DATA_STATEMENT}"
        assert not statement.inside(details)
        assert document.before(statement, details)
        assert terms.attrs["href"] == TERMS_URL


@pytest.mark.parametrize("name", EVERY)
def test_its_only_outside_links_are_the_license_and_portfolio123s_terms(
    sessions: Sessions, name: str
) -> None:
    for session in sessions(name):
        document = session.document
        hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
        ids = {element.attrs.get("id") for element in document.root.iter()}
        manifest = session.manifest
        directory = session.out / "sessions" / str(session.number)
        files = {
            (session.out / artifact.path).resolve()
            for artifact in manifest.artifacts
            if artifact.role != "report"
        } | {(directory / "manifest.json").resolve()}

        outside = [href for href in hrefs if urlsplit(href).scheme or urlsplit(href).netloc]
        assert sorted(outside) == sorted([license_url(manifest.trialfolio_version), TERMS_URL])
        linked: set[Path] = set()
        for href in hrefs:
            if href in outside:
                continue
            assert not href.startswith("/")
            if href.startswith("#"):
                assert href[1:] in ids
            else:
                linked.add((directory / unquote(href)).resolve())
        # Each of the session's files is linked, from the session's own directory.
        assert linked == files


@pytest.mark.parametrize("name", EVERY)
def test_it_runs_and_loads_nothing(sessions: Sessions, name: str) -> None:
    for session in sessions(name):
        elements = list(session.document.root.iter())
        styles = " ".join(style.text for style in session.document.root.find_all("style"))

        assert not [e for e in elements if e.tag in ("script", "link", "iframe", "object", "img")]
        assert not [name for e in elements for name in e.attrs if name.lower().startswith("on")]
        assert not [e for e in elements if "src" in e.attrs]
        assert not re.search(r"url\s*\(|@import", styles, re.IGNORECASE)


# The synthetic experiment (R03-AC11, DSC-04)

CLAIMS = [
    "read from each case's response from Portfolio123",
    "Portfolio123's Sharpe ratio",
    "The risk statistics are Portfolio123's",
    "as Portfolio123 reported",
    "each case is a backtest",
    "Backtested:",
]
"""What a real experiment's report says that calls a value Portfolio123's or a backtest's."""


def test_the_synthetic_experiments_report_says_its_values_are_invented(
    sessions: Sessions,
) -> None:
    real = sessions("completed")[0].document.root.find_all("main")[0].text
    for claim in CLAIMS:
        assert claim in real

    for session in sessions("synthetic"):
        document = session.document
        main = document.root.find_all("main")[0].text
        (kind,) = (e for e in document.root.iter() if e.attrs.get("class") == "kind")
        (banner,) = (e for e in document.root.iter() if e.attrs.get("class") == "synthetic")

        assert session.manifest.synthetic
        assert kind.text.endswith("Synthetic experiment")
        assert document.before(banner, document.root.by_id("objective"))
        assert "invented" in banner.text
        assert "none comes from Portfolio123" in banner.text
        (results,) = document.dd("Results")
        assert results.startswith("Synthetic: invented values")
        for heading in ("Strategy", "Benchmark"):
            (caption,) = document.table_after(heading).find_all("caption")
            assert "Every value is invented." in caption.text
        for claim in CLAIMS:
            assert claim not in main
