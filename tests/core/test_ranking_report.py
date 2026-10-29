"""A run's and an experiment session's report of a ranking given as a definition shows each
case's weights, by their nodes' canonical paths, the definition's source, each attempt's
`POST /rank` with its cost beside the backtest's, and, in its limitations, that each definition
is written into `ApiRankingSystem` just before its backtest, and what the ranking lock can't
exclude; it never shows the definition's text, and it orders, ranks, and marks no case by a value
(docs/contracts.md, a ranking definition in a report).

Traces to R04-AC06 at the core, with the exact wording R04-T11 settled; and to R01-AC13's rules,
which a report with a definition keeps: the notices, `LicenseRef-NSPRL-1.1`, no script or
external resource, the two outside links, and the data statement; and DSC-04, for the synthetic
run's and experiment's. Each run and experiment is written through the core, with the real
client, `requests`, and `urllib3` over the fake server, or with the demo's client for a synthetic
one, with the fixed clock, and the ranking lock on a file in the test's temporary directory. The
snapshot is the snapshot builder's, real `trialfolio run` output. Every expected value is written
here by hand: the weights from the definitions' files, and the hashes from their bytes.
"""

import hashlib
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.support.clock import FixedClock, no_wait
from tests.support.experiment_lab import Lab
from tests.support.fake_portfolio123 import (
    AUTHENTICATED,
    CREDENTIALS,
    FakePortfolio123,
    Reply,
    each_its_own,
    response,
)
from tests.support.html_report import Document, Element, parse
from tests.support.paths import EXPERIMENT_CONFIGS, RANKING_DEFINITIONS, RESPONSES, screen_config
from tests.support.plans import ranked_experiment, ranked_screen
from tests.support.snapshot_builder import SnapshotBuilder, naming
from trialfolio.contracts.manifest import CommandRecord
from trialfolio.contracts.ranking_snapshot import RankingSnapshotRecord
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.execution import Execution
from trialfolio.notices import (
    CONCISE_NOTICE,
    LICENSE_ID,
    PORTFOLIO123_DATA_STATEMENT,
    PORTFOLIO123_TERMS_URL,
    license_url,
)
from trialfolio.planning import (
    installed_versions,
)
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.report import HtmlReportRenderer
from trialfolio.runs import read_run
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_settings_csv_v1_1

SCREEN = screen_config("definition.yaml")

COMMAND = CommandRecord(name="run", options={}, started_at=FixedClock()())

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

WEIGHTS = ("40", "50", "50", "30", "50", "50", "30", "50", "50")
"""`value-momentum.xml`'s weights, node by node."""

EXAMPLE_CASES = ("baseline", "value-heavy", "tilt-earnings-yield", "no-sales-yield")
"""`ranking-example.yaml`'s cases, in the plan's order."""

EXAMPLE_WEIGHTS = [
    ["Value", "40", "60", "40", "40"],
    ["Value/Earnings Yield", "50", "50", "70", "100"],
    ["Value/Sales Yield", "50", "50", "30", "Removed"],
    ["Momentum", "30", "20", "30", "30"],
    ["Momentum/Six-Month Return", "50", "50", "50", "50"],
    ["Momentum/Year Return", "50", "50", "50", "50"],
    ["Quality", "30", "20", "30", "30"],
    ["Quality/Return on Equity", "50", "50", "50", "50"],
    ["Quality/Gross Margin", "50", "50", "50", "50"],
]
"""`ranking-example.yaml`'s table of weights: each node, then each case's weight of it, as the
example's variants give them."""

COSTS = (
    "rank_update: 1 credits, as Portfolio123 reported. screen_backtest: 5 credits, as Portfolio123"
    " reported."
)
"""An attempt's costs, from `rank-update.json`'s and `complete.json`'s `cost`."""

INVENTED = "5 credits, as the invented response reports: nothing was charged"
"""A synthetic attempt's backtest's cost, from `complete.json`'s `cost`, which the demo's client
was given: the invented response's, never Portfolio123's (DSC-04)."""

WRITTEN = (
    "{each} is written into the account's ApiRankingSystem, with its rank_update, just before its"
    " backtest, which ranks by that system's name."
)
LOCK = (
    "The ranking lock kept other Trial Folio processes on the machine from writing"
    " ApiRankingSystem between a definition's write and its backtest, but only those that lock the"
    " same file: not one that sees another /tmp, such as in a container, or one with another"
    " TRIALFOLIO_LOCK_DIR. Portfolio123's website, or another machine, could have changed it"
    " between the two, and no record would show it."
)
SYNTHETIC = (
    "This {kind} is synthetic, and sent nothing, so nothing was written into the account's"
    " ApiRankingSystem. A definition that's sent is written into it just before its backtest,"
    " which ranks by that system's name, and the ranking lock keeps other Trial Folio processes on"
    " the machine from writing it between the two, but only those that lock the same file: not"
    " one that sees another /tmp, such as in a container, or one with another"
    " TRIALFOLIO_LOCK_DIR."
)
"""The limitations of a ranking given as a definition, as R04-T11 words them, with what the
ranking lock doesn't exclude as R04-T13 words it, after the review of R04-T12's pull request found
that the report named only Portfolio123's website and another machine."""


def digest(path: Path) -> str:
    """A definition's hash, from its file's bytes, which hold no carriage return."""
    content = path.read_bytes()
    assert b"\r" not in content
    return "sha256:" + hashlib.sha256(content).hexdigest()


def write_run(
    tmp_path: Path,
    server: FakePortfolio123,
    path: Path = SCREEN,
    *,
    synthetic: bool = False,
    backtest: Reply | None = None,
    invented: bytes | None = None,
) -> Path:
    """Writes the run of the screen configuration at `path` through the core: over the fake
    server, which answers its `rank_update` with `rank-update.json` and its backtest with
    `backtest`, `complete.json` by default; or, for a synthetic run, with the demo's client, and
    no command, which answers its backtest with `invented`, the demo's response by default."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    planned = ranked_screen(path)
    plan = planned.plan
    out = tmp_path / "run"
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", backtest or response("complete.json"))
    with LocalArtifactStore(out) as store:
        execution = Execution(
            plan,
            plan.plan_hash,
            "not_required" if synthetic else "option",
            store,
            None if synthetic else COMMAND,
            clock=FixedClock(),
            ranking_lock=tmp_path / LOCK_FILE,
            pause=no_wait(),
        )
        error = execution.run(
            planned.content,
            (
                (lambda: SyntheticScreenBacktestClient(invented or response_bytes()))
                if synthetic
                else (lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint))
            ),
            definition=planned.definition,
            snapshot=planned.snapshot,
        )
    assert (error is None) == (backtest is None)
    return out


def write_experiment(
    tmp_path: Path,
    server: FakePortfolio123,
    path: Path = EXPERIMENT_CONFIGS / "ranking-example.yaml",
    backtests: Sequence[Reply] | None = None,
) -> Path:
    """Writes a new experiment of the configuration at `path` through the core, over the fake
    server, which answers each case's `rank_update` with `rank-update.json`, and its backtests
    with `backtests`, in the plan's order, `complete.json` for each by default."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    cases = len(ranked_experiment(path).plan.cases)
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", *(response("rank-update.json"),) * cases, method="POST")
    # Each case's response its own, so none is a stale backtest (D-45).
    server.reply(
        "/screen/backtest", *each_its_own(backtests or (response("complete.json"),) * cases)
    )
    lab = Lab(tmp_path, server)
    lab.new(path)
    return lab.out


def write_synthetic_sessions(
    tmp_path: Path, names: Sequence[str], invented: bytes | None = None
) -> Path:
    """Writes an experiment through the core with the demo's client: a new one of the first of
    `names`, in `experiment-configs/`, then a revision into each of the others, in turn, one
    session each. The client answers each backtest with `invented`, the demo's response by
    default."""
    lab = Lab(tmp_path)
    hashes: list[str] = []
    for number, name in enumerate(names, start=1):
        reason = None if number == 1 else f"Revised into {name}."
        ran = lab.run(name, reason=reason, synthetic=True, invented=invented)
        assert ran.error is None
        assert ran.plan.plan_hash not in hashes, f"{name} isn't a revision"
        hashes.append(ran.plan.plan_hash)
    return lab.out


def report(out: Path, session: int | None = None) -> Document:
    path = out / ("report.html" if session is None else f"sessions/{session}/report.html")
    return parse(path.read_text(encoding="utf-8"))


def table_after(document: Document, heading: str) -> Element:
    """The first table after the `<h3>` whose text is `heading`."""
    (h3,) = (h for h in document.root.find_all("h3") if h.text == heading)
    return next(t for t in document.root.find_all("table") if document.before(h3, t))


def cells(document: Document, heading: str, *, starts: bool = False) -> list[list[str]]:
    """The text of each cell of each row of the first table after the `<h3>` whose text is
    `heading`, or, with `starts`, starts with it, its header row first."""
    table = document.table_after(heading) if starts else table_after(document, heading)
    return [[cell.text for cell in row] for row in document.rows(table)]


def paragraph_after(document: Document, heading: str) -> str:
    """The text of the first paragraph after the `<h3>` whose text is `heading`."""
    (h3,) = (h for h in document.root.find_all("h3") if h.text == heading)
    return next(p for p in document.root.find_all("p") if document.before(h3, p)).text


def limitations(document: Document) -> list[str]:
    (h3,) = (h for h in document.root.find_all("h3") if h.text == "Limitations")
    items = next(ul for ul in document.root.find_all("ul") if document.before(h3, ul))
    return [li.text for li in items.find_all("li")]


def section(document: Document, section_id: str) -> Element:
    return document.root.by_id(section_id)


def attempt_costs(document: Document) -> dict[str, set[str]]:
    """The `Cost` cells of the attempts in a session's tables of attempts, by the plan each
    attempt ran under."""
    found: dict[str, set[str]] = {}
    for table in document.root.find_all("table"):
        heads, *rows = [[cell.text for cell in row] for row in document.rows(table)] or [[]]
        if heads[:1] != ["Attempt"]:
            continue
        assert heads[-1] == "Cost"
        for row in rows:
            found.setdefault(row[heads.index("Plan")], set()).add(row[-1])
    return found


# A screen run's report


def test_a_runs_report_gives_its_ranking_row_and_each_weight_by_its_path(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    document = report(write_run(tmp_path, server))

    definitions = section(document, "definitions")
    (h3,) = (h for h in definitions.find_all("h3") if h.text == "The ranking definition")
    assert document.dd("Definition") == [digest(RANKING_DEFINITIONS / "value-momentum.xml")]
    assert document.dd("Ranking method") == [
        "percentile_nas_negative: Percentile NAs Negative, sent as rankingMethod 2"
    ]
    rows = cells(document, "The ranking definition")
    assert rows[0] == ["Node", "Weight"]
    assert rows[1:] == [list(row) for row in zip(NODES, WEIGHTS, strict=True)]
    table = table_after(document, "The ranking definition")
    assert table.inside(definitions) and document.before(h3, table)
    assert table.find_all("caption")[0].text == (
        "Each node's weight, by its canonical path, in the definition's order, as settings.csv"
        " records them."
    )
    assert paragraph_after(document, "The ranking definition") == (
        "The ranking is a ranking system's definition, given by its hash, its ranking method, and"
        " each node's weight, which the ranking row and its weight rows give. The definition's"
        " text isn't shown: the plan holds it, and the artifacts below link the plan."
    )


def test_a_run_without_tables_gives_the_weights_its_plan_resolves(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    document = report(write_run(tmp_path, server, backtest=Reply(400, b"Unsupported value")))

    rows = cells(document, "The ranking definition")

    assert rows[1:] == [list(row) for row in zip(NODES, WEIGHTS, strict=True)]
    caption = table_after(document, "The ranking definition").find_all("caption")[0]
    assert caption.text == (
        "Each node's weight, by its canonical path, in the definition's order, as the plan"
        " resolves them."
    )


def test_a_runs_report_gives_its_definitions_source_a_file_by_its_hash(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    document = report(write_run(tmp_path, server))

    text = paragraph_after(document, "The ranking definition's source")

    assert text == (
        f"A file, by the definition's hash, {digest(RANKING_DEFINITIONS / 'value-momentum.xml')}."
        " definition.xml is the run's copy of the file, byte for byte."
    )
    (h3,) = (h for h in document.root.find_all("h3") if h.text == "The ranking definition's source")
    assert h3.inside(section(document, "data"))


def test_a_runs_snapshot_source_gives_its_systems_name_id_and_when_it_was_read(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    snapshot = SnapshotBuilder(tmp_path / "home").snapshot(tmp_path / "ranking" / "value-momentum")
    record = RankingSnapshotRecord.model_validate_json((snapshot / "snapshot.json").read_bytes())
    path = naming(SCREEN, snapshot, tmp_path / "screen-configs")

    document = report(write_run(tmp_path, server, path))

    # `trialfolio report` reads the snapshot's record from the run's copy, and renders the same.
    with LocalArtifactStore(tmp_path / "run") as store:
        saved = read_run(store)
    assert saved.snapshot == record
    html = (tmp_path / "run" / "report.html").read_text(encoding="utf-8")
    assert HtmlReportRenderer(installed_versions().trialfolio).render(saved, "") == html
    read = record.taken_at.isoformat().replace("+00:00", "Z")
    assert paragraph_after(document, "The ranking definition's source") == (
        f"A ranking snapshot of the system Value and momentum, ID 104729, read {read}, as its"
        " record, snapshot.json, gives it. The definition's hash:"
        f" {digest(RANKING_DEFINITIONS / 'value-momentum.xml')}. definition.xml and snapshot.json are"
        " the run's copies of the snapshot's files, byte for byte."
    )


def test_a_runs_attempt_lists_its_post_rank_with_its_cost_beside_the_backtests(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    document = report(write_run(tmp_path, server))

    rows = cells(document, "Attempt", starts=True)

    assert [row[1:4] for row in rows[1:]] == [
        ["POST /auth", "Response", "200"],
        ["POST /rank", "Response", "200"],
        ["POST /screen/backtest", "Response", "200"],
    ]
    # The case's cost, 6 credits, then the attempt's, each request's.
    assert document.dd("Cost") == ["6 credits, as Portfolio123 reported", COSTS]


def test_a_runs_limitations_say_where_its_definition_was_written(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    items = limitations(report(write_run(tmp_path, server)))

    assert WRITTEN.format(each="The run's definition") in items
    assert LOCK in items


# An experiment session's report


def test_an_experiments_report_gives_a_table_of_each_cases_weights(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    backtests = [response(name) for name in ("complete.json", "changed-metrics.json")]
    backtests += [response("complete.json")] * 2
    document = report(write_experiment(tmp_path, server, backtests=backtests), 1)

    rows = cells(document, "The ranking's weights")

    assert rows[0] == ["Node", *EXAMPLE_CASES]
    assert rows[1:] == EXAMPLE_WEIGHTS
    table = table_after(document, "The ranking's weights")
    assert table.inside(section(document, "definitions"))
    (baseline,) = (h for h in document.root.find_all("h3") if h.text == "The baseline's settings")
    assert document.before(baseline, table)
    assert paragraph_after(document, "The ranking's weights") == (
        "Each case's ranking is a ranking system's definition: the baseline's, or the baseline's"
        " with exactly its ranking variant's change, which its change above gives. A row for each"
        " node of the baseline's definition, in its order, by its canonical path, and a column"
        " for each planned case, in the plan's order. Each cell is the weight the case's"
        " definition gives the node, as the case's settings.csv holds it, or, for a case without"
        " one, its plan; Removed is the factor its variant removes. Each case's weights are"
        " aligned by the baseline's nodes, not by their paths, which a removal can change. The"
        " table orders, ranks, and marks no case by a weight. The definitions' text isn't shown:"
        " the plan holds each case's, and the artifacts below link the plan."
    )


def test_a_case_without_settings_csv_gives_its_plans_weights(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # `tilt-earnings-yield`'s backtest is rejected, so it has no tables.
    backtests = [response("complete.json")] * 2 + [Reply(400, b"Unsupported value")]
    backtests += [response("complete.json")]
    out = write_experiment(tmp_path, server, backtests=backtests)

    rows = cells(report(out, 1), "The ranking's weights")

    assert len(list(out.glob("cases/*/normalized/settings.csv"))) == 3
    assert rows[1:] == EXAMPLE_WEIGHTS


def test_a_cases_weights_are_aligned_by_the_baselines_nodes_not_their_paths(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    """`no-first-yield` removes the first of `Value P/E`'s two Yield factors, so its settings.csv
    names the second by its name, `Value P\\/E/Yield`, where the baseline's names it by its
    position, `Value P\\/E/#2`. Its weight of that node is in the node's baseline row, only the
    removed factor's row gives `Removed`, and no row is added for its path."""
    out = write_experiment(tmp_path, server, EXPERIMENT_CONFIGS / "ranking-positions.yaml")

    rows = cells(report(out, 1), "The ranking's weights")

    assert rows == [
        ["Node", "baseline", "positions-heavy", "no-first-yield"],
        [r"Value P\/E", "25", "30", "25"],
        [r"Value P\/E/#1", "40", "40", "Removed"],
        [r"Value P\/E/#2", "40", "40", "60"],
        [r"Value P\/E/Cash Flow", "20", "20", "40"],
        ["#2", "10", "5", "10"],
        ["#3", "10", "5", "10"],
        [r"Price\\Book", "20", "25", "20"],
        [r"Price\\Book/Book Yield", "100", "100", "100"],
        [r"\#Momentum", "15", "15", "15"],
        [r"\#Momentum/Short Return", "50", "50", "50"],
        [r"\#Momentum/Long Return", "50", "50", "50"],
        ["Secret Sauce", "20", "20", "20"],
        ["Secret Sauce/Margin", "60", "60", "60"],
        ["Secret Sauce/Turnover", "40", "40", "40"],
    ]
    nodes = [
        [row.node for row in read_settings_csv_v1_1(path.read_bytes(), path.name) if row.node]
        for path in out.glob("cases/*/normalized/settings.csv")
    ]
    removal = [r"Value P\/E", r"Value P\/E/Yield", r"Value P\/E/Cash Flow"]
    assert [found[:3] for found in nodes].count(removal) == 1


def ordering(document: Document) -> list[list[str]]:
    """Where the report places each case: the heads of its tables of weights and of metrics, and
    the ledger's order of planned cases."""
    planned = [row[0] for row in cells(document, "Planned cases")[1:]]
    return [
        cells(document, "The ranking's weights")[0],
        cells(document, "Strategy")[0],
        cells(document, "Benchmark", starts=True)[0],
        planned,
    ]


def test_swapping_responses_between_cases_changes_no_order_or_mark(
    tmp_path: Path,
) -> None:
    documents: list[Document] = []
    for changed in (1, 3):
        backtests = [response("complete.json")] * 4
        backtests[changed] = response("changed-metrics.json")
        fake = FakePortfolio123()
        try:
            out = write_experiment(tmp_path / str(changed), fake, backtests=backtests)
        finally:
            fake.close()
        documents.append(report(out, 1))

    first, second = documents
    assert ordering(first) == ordering(second)
    assert ordering(first)[3] == list(EXAMPLE_CASES)
    for document in documents:
        weights = table_after(document, "The ranking's weights")
        # No cell is marked: none has an attribute, or anything but its value in it.
        for cell in (c for row in document.rows(weights) for c in row):
            assert cell.attrs == {}
            assert {child.tag for child in cell.iter()} <= {cell.tag, "code"}
        text = document.root.text
        assert text.count("best") == 1
        assert "No case is ranked, selected, or called best." in text


def test_an_experiments_attempts_give_each_cost_beside_the_backtests(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    document = report(write_experiment(tmp_path, server), 1)

    for case in EXAMPLE_CASES:
        rows = cells(document, "Attempts")
        heads = rows[0]
        assert heads[-1] == "Cost"
        assert heads[-2] == "Exchanges"
        table = next(
            t
            for t in document.root.find_all("table")
            if t.find_all("caption") and t.find_all("caption")[0].text.startswith(f"{case},")
        )
        (attempt,) = [[cell.text for cell in row] for row in document.rows(table)[1:]]
        assert attempt[-2] == (
            "POST /auth: Response 200 POST /rank: Response 200 POST /screen/backtest: Response 200"
            if case == "baseline"
            else "POST /rank: Response 200 POST /screen/backtest: Response 200"
        )
        assert attempt[-1] == COSTS


def test_an_experiments_source_gives_its_definitions_file_by_its_hash(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    document = report(write_experiment(tmp_path, server), 1)

    assert cells(document, "The ranking definition's source") == [
        ["Plan", "Source"],
        [
            "1",
            f"A file, by the definition's hash, {digest(RANKING_DEFINITIONS / 'value-momentum.xml')}.",
        ],
    ]
    table = table_after(document, "The ranking definition's source")
    assert table.inside(section(document, "data"))


def test_an_experiments_snapshot_source_gives_its_systems_name_id_and_when_it_was_read(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    snapshot = SnapshotBuilder(tmp_path / "home").snapshot(tmp_path / "ranking" / "value-momentum")
    record = RankingSnapshotRecord.model_validate_json((snapshot / "snapshot.json").read_bytes())
    path = naming(
        EXPERIMENT_CONFIGS / "ranking-example.yaml", snapshot, tmp_path / "experiment-configs"
    )

    document = report(write_experiment(tmp_path, server, path), 1)

    read = record.taken_at.isoformat().replace("+00:00", "Z")
    assert cells(document, "The ranking definition's source")[1] == [
        "1",
        (
            f"A ranking snapshot of the system Value and momentum, ID 104729, read {read}, as"
            " its record, snapshot.json, gives it. The definition's hash:"
            f" {digest(RANKING_DEFINITIONS / 'value-momentum.xml')}."
        ),
    ]


def test_each_plans_source_is_given_whether_its_ranking_is_a_definition_or_not(
    tmp_path: Path,
) -> None:
    """A formula's plan, revised into a definition's, then back."""
    out = write_synthetic_sessions(
        tmp_path, ["example.yaml", "revisions/ranking-from-formula.yaml", "example.yaml"]
    )

    third = report(out, 3)

    none = "None: the ranking isn't a definition."
    assert cells(third, "The ranking definition's source")[1:] == [
        ["1", none],
        [
            "2",
            f"A file, by the definition's hash, {digest(RANKING_DEFINITIONS / 'value-momentum.xml')}.",
        ],
        ["3", none],
    ]
    # The current plan's ranking is a formula, so it has no table of weights; but the
    # experiment's attempts sent definitions, so its limitations and its attempts' costs stay.
    assert "The ranking's weights" not in [h.text for h in third.root.find_all("h3")]
    assert SYNTHETIC.format(kind="experiment") in limitations(third)
    assert cells(third, "Attempts")[0][-1] == "Cost"
    # An attempt under a formula's plan, 1 or 3, sent no definition, so its cost is the
    # backtest's alone; one under plan 2 gives its rank_update's beside it.
    assert attempt_costs(third) == {
        "1": {"Not reported"},
        "2": {"rank_update: Not reported. screen_backtest: Not reported."},
    }
    # Before the revision, no plan had a definition, so the first session's report has none of
    # it, as 0.3.0 wrote it.
    first = report(out, 1)
    headings = [h.text for h in first.root.find_all("h3")]
    assert "The ranking definition's source" not in headings
    assert cells(first, "Attempts")[0][-1] == "Exchanges"


def test_an_experiments_limitations_say_where_each_definition_is_written(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    items = limitations(report(write_experiment(tmp_path, server), 1))

    assert WRITTEN.format(each="Each case's definition") in items
    assert LOCK in items


# What every report with a definition holds


@pytest.fixture
def documents(tmp_path: Path, server: FakePortfolio123) -> list[tuple[str, Document]]:
    """A run's report, and an experiment session's, each with a definition, as HTML text and
    parsed."""
    run = (write_run(tmp_path / "run", server) / "report.html").read_text(encoding="utf-8")
    fake = FakePortfolio123()
    try:
        experiment = write_experiment(tmp_path / "experiment", fake)
    finally:
        fake.close()
    session = (experiment / "sessions/1/report.html").read_text(encoding="utf-8")
    return [(run, parse(run)), (session, parse(session))]


def test_a_report_never_holds_the_definitions_text(
    documents: list[tuple[str, Document]],
) -> None:
    for html, _ in documents:
        for part in ("&lt;RankingSystem", "&lt;Composite", "&lt;StockFormula", "RankType"):
            assert part not in html


def test_a_report_with_a_definition_keeps_the_notices_and_links_rules(
    documents: list[tuple[str, Document]],
) -> None:
    for html, document in documents:
        assert document.root.by_id("notice").text == CONCISE_NOTICE
        assert LICENSE_ID in document.root.by_id("full-notice").text
        assert PORTFOLIO123_DATA_STATEMENT in document.root.by_id("closing").text
        assert "<script" not in html
        assert not any(name.startswith("on") for e in document.root.iter() for name in e.attrs)
        outside = {
            href
            for a in document.root.find_all("a")
            if (href := a.attrs.get("href")) is not None and urlsplit(href).scheme
        }
        version = installed_versions().trialfolio
        assert outside == {license_url(version), PORTFOLIO123_TERMS_URL}


# Synthetic runs and experiments (DSC-04)


def test_a_synthetic_runs_report_says_its_values_are_invented_and_nothing_was_written(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    document = report(write_run(tmp_path, server, synthetic=True))

    (banner,) = (p for p in document.root.find_all("p") if p.attrs.get("class") == "synthetic")
    assert banner.text == (
        "Synthetic example. This run was written by Trial Folio's core, with the demo's client,"
        " from invented values. None of them comes from Portfolio123, and nothing was sent to"
        " it."
    )
    items = limitations(document)
    assert SYNTHETIC.format(kind="run") in items
    assert LOCK not in items
    assert document.dd("Cost")[-1] == "rank_update: Not reported. screen_backtest: Not reported."


def test_a_synthetic_runs_costs_are_its_invented_responses_never_portfolio123s(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    """The demo's client answers the backtest with `complete.json`, whose `cost` is 5, and its
    `rank_update` with an empty object, which gives none."""
    out = write_run(
        tmp_path, server, synthetic=True, invented=(RESPONSES / "complete.json").read_bytes()
    )

    document = report(out)

    assert document.dd("Cost") == [
        "5 credits, as the invented responses report: nothing was charged",
        f"rank_update: Not reported. screen_backtest: {INVENTED}.",
    ]
    assert "Portfolio123 reported" not in document.root.text


def test_a_synthetic_experiments_report_says_nothing_was_written(tmp_path: Path) -> None:
    out = write_synthetic_sessions(tmp_path, ["ranking-example.yaml"])

    document = report(out, 1)

    assert SYNTHETIC.format(kind="experiment") in limitations(document)
    assert cells(document, "The ranking's weights")[1:] == EXAMPLE_WEIGHTS
    assert "Every value, attempt, and count in it is invented" in document.root.text


def test_a_synthetic_experiments_costs_are_its_invented_responses_never_portfolio123s(
    tmp_path: Path,
) -> None:
    """A formula's plan, revised into a definition's, each case's backtest answered with
    `complete.json`, whose `cost` is 5, and each `rank_update` with an empty object, which gives
    none: ten attempts, five under each plan."""
    out = write_synthetic_sessions(
        tmp_path,
        ["example.yaml", "revisions/ranking-from-formula.yaml"],
        (RESPONSES / "complete.json").read_bytes(),
    )

    document = report(out, 2)

    assert attempt_costs(document) == {
        "1": {INVENTED},
        "2": {f"rank_update: Not reported. screen_backtest: {INVENTED}."},
    }
    assert document.dd("Cost") == [
        "50 credits, as the invented responses report: nothing was charged"
    ]
    assert "Portfolio123 reported" not in document.root.text
