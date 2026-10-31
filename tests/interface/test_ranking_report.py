"""What a report of a ranking definition holds, through the command: each `report.html` and
`sessions/<s>/report.html` that `trialfolio run` writes for a screen or an experiment whose
ranking is a definition, given in a file or by a snapshot, and the committed synthetic run's and
experiment's, read from copies, each parsed with `html.parser`.

Traces to R04-AC06, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_report.py`:

- a screen run's report gives the `ranking` row, with the definition's hash and ranking method,
  and each weight row by its canonical path;
- an experiment session's gives a table of weights: a row for each of the baseline's nodes, in
  its order, and a column for each planned case, in the plan's order, each cell as the case's
  `settings.csv` holds it, or `Removed` for `no-sales-yield`'s `Value/Sales Yield`;
- `ranking-positions.yaml`'s report aligns the cells by the baseline's nodes, not by their paths:
  its removal case's `settings.csv` names the factor left of the two that shared a name by that
  name, where the baseline's names it by its position, yet that case's weight is in the node's
  baseline row, only the removed factor's row gives `Removed`, and no row is added for a path only
  that case's `settings.csv` holds;
- with the responses swapped between two cases, the cases' order and marks don't change: no case
  is sorted, ranked, or marked by a weight or a metric, and none is called best;
- each report gives the definition's source, a file by its hash, or a snapshot by its system's
  name and ID and when it was read; each attempt's `POST /rank`, with its cost beside the
  backtest's; and, in its limitations, that each definition is written into `ApiRankingSystem`
  before its backtest, and what the ranking lock can't exclude;
- it never holds the definition's text, and it keeps R01-AC13's rules: the notices,
  `LicenseRef-NSPRL-1.1`, no script or external resource, the two outside links, the data
  statement, and "Not assessed"; and the synthetic run's and experiment's reports say their
  values are invented (DSC-04).

`tests/core/test_ranking_report.py` checks the same at the core, with the exact wording R04-T11
settled, which these checks repeat where a test needs it, with the lock's wording as R04-T13
gives it.
TS-T06 added the test of "Not assessed", which no test of a report with a definition made, and
the checks of R01-AC13's rules are tests/support/html_report.py's, which every kind of report's
tests call (docs/test-refactoring.md, finding 10).

Each run, experiment, and snapshot is written once for the module, with `trialfolio run`, through
the CLI's entry function in the test process, over a fake server of its own, with the fixed clock
and the ranking lock in the scenario's own directory; the snapshots by the snapshot builder.
Every expected value is written here by hand: the weights from the definitions' files, the hash
from `value-momentum.xml`'s bytes, and the snapshot's system from `rank-get.json`.
"""

import csv
import io
import json
import re
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    RANK_UPDATED,
    RESPONSES,
    ExperimentBuilder,
    experiment_config,
)
from tests.support.fake_portfolio123 import AUTHENTICATED, FakePortfolio123, distinct, response
from tests.support.html_report import (
    AttemptShown,
    Document,
    Element,
    assert_closing,
    assert_concise_notice_first,
    assert_full_notice,
    assert_links,
    assert_loads_nothing,
    assert_no_case_is_called_best,
    assert_not_assessed,
    listed_files,
    parse,
)
from tests.support.paths import SCREEN_CONFIGS
from tests.support.snapshot_builder import SnapshotBuilder, naming
from tests.support.synthetic_experiment import (
    SYNTHETIC_EXPERIMENT_WITH_DEFINITION,
    SYNTHETIC_RUN_WITH_DEFINITION,
    write_synthetic_ranking_experiment,
)

SCREEN: Final = SCREEN_CONFIGS / "definition.yaml"
EXAMPLE: Final = experiment_config("ranking-example.yaml")
POSITIONS: Final = experiment_config("ranking-positions.yaml")

DEFINITION_HASH: Final = "sha256:6bc59b992f83d5e4c245f37f187651ed18de6b9cb5949ac9f29b743273b26895"
"""The hash of `value-momentum.xml`'s text, which `rank-get.json`'s `xml` holds too."""
SYSTEM: Final = "Value and momentum, ID 104729, read 2026-10-03T14:00:02Z"
"""The snapshot's system, as `rank-get.json` gives its name and ID, read when the fixed clock's
third reading gives it, the end of its attempt."""

NODES: Final = (
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
"""`value-momentum.xml`'s nodes, by canonical path, in its order, which `synthetic.xml` shares."""
WEIGHTS: Final = ("40", "50", "50", "30", "50", "50", "30", "50", "50")
"""`value-momentum.xml`'s weights, node by node, which `synthetic.xml` shares."""

CASES: Final = ("baseline", "value-heavy", "tilt-earnings-yield", "no-sales-yield")
"""`ranking-example.yaml`'s cases, in the plan's order."""
EXAMPLE_WEIGHTS: Final = [
    ["Node", *CASES],
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
"""`ranking-example.yaml`'s table of weights, as the example's variants give them."""
SYNTHETIC_WEIGHTS: Final = [
    ["Node", "baseline", "value-heavy", "no-sales-yield"],
    *([row[0], row[1], row[2], row[4]] for row in EXAMPLE_WEIGHTS[1:]),
]
"""The synthetic experiment's second session's table: `synthetic.xml` has `value-momentum.xml`'s
nodes and weights, and its variants are the example's `value-heavy` and `no-sales-yield`."""

COSTS: Final = (
    "rank_update: 1 credits, as Portfolio123 reported. screen_backtest: 5 credits, as Portfolio123"
    " reported."
)
"""An attempt's costs, from `rank-update.json`'s `cost`, 1, and `complete.json`'s, 5."""
NOT_REPORTED: Final = "rank_update: Not reported. screen_backtest: Not reported."
"""A synthetic attempt's costs: the demo's client's responses report none."""

WRITTEN: Final = (
    "{each} is written into the account's ApiRankingSystem, with its rank_update, just before its"
    " backtest, which ranks by that system's name."
)
LOCK: Final = (
    "The ranking lock kept other Trial Folio processes on the machine from writing"
    " ApiRankingSystem between a definition's write and its backtest, but only those that lock the"
    " same file: not one that sees another /tmp, such as in a container, or one with another"
    " TRIALFOLIO_LOCK_DIR. Portfolio123's website, or another machine, could have changed it"
    " between the two, and no record would show it."
)
SYNTHETIC: Final = (
    "This {kind} is synthetic, and sent nothing, so nothing was written into the account's"
    " ApiRankingSystem. A definition that's sent is written into it just before its backtest,"
    " which ranks by that system's name, and the ranking lock keeps other Trial Folio processes on"
    " the machine from writing it between the two, but only those that lock the same file: not"
    " one that sees another /tmp, such as in a container, or one with another"
    " TRIALFOLIO_LOCK_DIR."
)
"""A ranking definition's limitations, for a run or an experiment that sent its definitions, and
for a synthetic one."""


@dataclass(frozen=True)
class Shown:
    """One report, with the output it shows."""

    out: Path
    """The run's or the experiment's directory."""
    path: Path
    """The report's path: the run's `report.html`, a session's, or one `trialfolio report`
    rendered again elsewhere."""
    manifest_path: Path | None = None
    """The manifest of what the report shows, when it isn't beside the report."""

    @property
    def document(self) -> Document:
        return parse(self.path.read_text(encoding="utf-8"))

    @property
    def html(self) -> str:
        return self.path.read_text(encoding="utf-8")

    @property
    def manifest(self) -> dict[str, object]:
        """The manifest beside the report, as JSON."""
        loaded = json.loads(self.listed.read_bytes())
        return cast("dict[str, object]", loaded)

    @property
    def listed(self) -> Path:
        """The manifest's path."""
        return (
            self.path.parent / "manifest.json" if self.manifest_path is None else self.manifest_path
        )

    def case_id(self, key: str) -> str:
        """The `case_id` of the planned case `key`, as the current plan's `experiment.json`
        gives it."""
        record = json.loads(
            (self.out / f"plans/{self.manifest['plan']}/experiment.json").read_bytes()
        )
        (case_id,) = (c["case_id"] for c in record["planned_cases"] if c["case_key"] == key)
        return cast("str", case_id)

    def weights(self, case_id: str) -> dict[str, str]:
        """The weight of each node, by its canonical path, in an experiment case's
        `settings.csv`."""
        path = self.out / "cases" / case_id / "normalized" / "settings.csv"
        rows = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"), newline=""))
        return {row["node"]: row["value"] for row in rows if row["setting"] == "ranking_weight"}


type Scenario = Callable[[Cli, Path], list[Shown]]


def _run(config: Path, *, snapshot: bool = False) -> Scenario:
    def write(cli: Cli, directory: Path) -> list[Shown]:
        if snapshot:
            config_ = naming(config, _snapshot(directory), directory / "screen-configs")
        else:
            config_ = config
        cli.server.reply("/auth", AUTHENTICATED)
        cli.server.reply("/rank", RANK_UPDATED, method="POST")
        cli.server.reply("/screen/backtest", response("complete.json"))
        out = directory / "run"
        outcome = cli.run_approved(config_, out)
        assert outcome.exit_code == 0, outcome.stderr
        return [Shown(out, out / "report.html")]

    return write


def _experiment(config: Path, changed: str | None = None, *, snapshot: bool = False) -> Scenario:
    def write(cli: Cli, directory: Path) -> list[Shown]:
        config_ = config
        if snapshot:
            config_ = naming(config, _snapshot(directory), directory / "experiment-configs")
        cases = 4 if config == EXAMPLE else 3
        keys = CASES if config == EXAMPLE else ("baseline", "positions-heavy", "no-first-yield")
        # Each case's response its own, so none is a stale backtest (D-45).
        sends = distinct(
            *(
                (
                    RESPONSES / ("changed-metrics.json" if key == changed else "complete.json")
                ).read_bytes()
                for key in keys
            )
        )
        out = directory / "experiment"
        builder: ExperimentBuilder[Outcome] = ExperimentBuilder(cli.server, cli)
        outcome = builder.run(config_, out, ranks=[RANK_UPDATED] * cases, sends=sends)
        assert outcome.exit_code == 0, outcome.stderr
        return [Shown(out, out / "sessions/1/report.html")]

    return write


def _snapshot(directory: Path) -> Path:
    """A snapshot of `ranking-snapshot-configs/example.yaml`, which the snapshot builder takes,
    over a server of its own, answering its `GET /rank` with `rank-get.json`."""
    return SnapshotBuilder(directory / "snapshot-home").snapshot(
        directory / "ranking" / "value-momentum"
    )


def _rendered(cli: Cli, directory: Path) -> list[Shown]:
    """The committed synthetic run's report, rendered again from a copy of its records by
    `trialfolio report`, into a directory of its own, with the code under test."""
    run = directory / SYNTHETIC_RUN_WITH_DEFINITION.name
    shutil.copytree(SYNTHETIC_RUN_WITH_DEFINITION, run)
    out = directory / "report"
    outcome = cli("report", run, "--out", out)
    assert outcome.exit_code == 0, outcome.stderr
    return [Shown(run, out / "report.html", run / "manifest.json")]


def _written_again(cli: Cli, directory: Path) -> list[Shown]:
    """The synthetic experiment, written again through the core with the demo's client, as the
    synthetic writer wrote the committed one, with the code under test."""
    out = directory / "experiment"
    write_synthetic_ranking_experiment(out)
    return [Shown(out, out / f"sessions/{n}/report.html") for n in (1, 2)]


def _copy(fixture: Path, reports: tuple[str, ...]) -> Scenario:
    def write(cli: Cli, directory: Path) -> list[Shown]:
        out = directory / fixture.name
        shutil.copytree(fixture, out)
        return [Shown(out, out / report) for report in reports]

    return write


SCENARIOS: Final[dict[str, Scenario]] = {
    "run": _run(SCREEN),
    "snapshot-run": _run(SCREEN, snapshot=True),
    "experiment": _experiment(EXAMPLE, "value-heavy"),
    "swapped": _experiment(EXAMPLE, "no-sales-yield"),
    "positions": _experiment(POSITIONS),
    "snapshot-experiment": _experiment(EXAMPLE, snapshot=True),
    "synthetic-run": _copy(SYNTHETIC_RUN_WITH_DEFINITION, ("report.html",)),
    "synthetic-experiment": _copy(
        SYNTHETIC_EXPERIMENT_WITH_DEFINITION, ("sessions/1/report.html", "sessions/2/report.html")
    ),
    "synthetic-run-rendered": _rendered,
    "synthetic-experiment-written": _written_again,
}
"""Each scenario's writer: `ranking-example.yaml` with `changed-metrics.json` for `value-heavy`
and `complete.json` for the others, and again with `no-sales-yield`'s and `value-heavy`'s
responses swapped; `ranking-positions.yaml` with `complete.json` for each case; `definition.yaml`,
as a screen run; each of `definition.yaml` and `ranking-example.yaml` naming a snapshot in place
of its definition; copies of the committed synthetic run and experiment; the synthetic run's
report rendered again by `trialfolio report`; and the synthetic experiment written again by the
synthetic writer, so the synthetic reports' checks read what the code under test writes too."""

SYNTHETIC_RUNS: Final = ("synthetic-run", "synthetic-run-rendered")
SYNTHETIC_EXPERIMENTS: Final = ("synthetic-experiment", "synthetic-experiment-written")
REAL: Final = ("run", "snapshot-run", "experiment", "positions", "snapshot-experiment")
EVERY: Final = (*SCENARIOS,)

type Reports = Callable[[str], list[Shown]]


@pytest.fixture(scope="module")
def reports(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Reports]:
    """Writes each scenario once for the module, with the license acknowledged, the canary
    credentials, a temporary home, and a server of its own, and gives its reports."""
    root = tmp_path_factory.mktemp("reports")
    written: dict[str, list[Shown]] = {}
    servers: list[FakePortfolio123] = []

    def get(name: str) -> list[Shown]:
        if name not in written:
            directory = root / name
            # A scenario that failed fails each test that reads it, not only the first.
            assert not directory.exists(), f"the {name} scenario couldn't be written"
            directory.mkdir()
            server = FakePortfolio123()
            servers.append(server)
            with pytest.MonkeyPatch.context() as monkeypatch:
                cli = Cli(monkeypatch, directory, server)
                cli.ready()
                written[name] = SCENARIOS[name](cli, directory)
        return written[name]

    yield get
    for server in servers:
        server.close()


# The weights


@pytest.mark.parametrize("name", ["run", "snapshot-run", *SYNTHETIC_RUNS])
def test_a_runs_report_gives_its_ranking_row_and_each_weight_by_its_path(
    reports: Reports, name: str
) -> None:
    (shown,) = reports(name)
    document = shown.document

    assert document.dd("Ranking method") == [
        "percentile_nas_negative: Percentile NAs Negative, sent as rankingMethod 2"
    ]
    if name not in SYNTHETIC_RUNS:
        assert document.dd("Definition") == [DEFINITION_HASH]
    assert document.ranking_weights() == [
        ["Node", "Weight"],
        *([node, weight] for node, weight in zip(NODES, WEIGHTS, strict=True)),
    ]
    assert document.heading("The ranking definition").inside(document.root.by_id("definitions"))
    # Among the settings, the `ranking` row with the definition's hash and ranking method, then a
    # weight row for each node, named by its canonical path.
    rows = document.texts(document.table_after("All settings"))
    names = [row[0] for row in rows]
    ranking = names.index("ranking")
    (definition,) = re.findall(r"sha256:[0-9a-f]{64}", rows[ranking][2])
    assert json.loads(rows[ranking][2]) == {
        "definition": definition,
        "ranking_method": "percentile_nas_negative",
    }
    assert definition == document.dd("Definition")[0]
    assert [row[:3] for row in rows[ranking + 1 : ranking + 1 + len(NODES)]] == [
        [f"ranking_weight {node}", "strategy", weight]
        for node, weight in zip(NODES, WEIGHTS, strict=True)
    ]


def test_an_experiment_sessions_report_gives_a_table_of_each_cases_weights(
    reports: Reports,
) -> None:
    (shown,) = reports("experiment")
    document = shown.document

    shown_weights = document.ranking_weights()

    assert shown_weights == EXAMPLE_WEIGHTS
    assert document.heading("The ranking's weights").inside(document.root.by_id("definitions"))
    # Each cell is the weight the case's settings.csv holds for the node, or `Removed` exactly
    # where the case's definition has no such node.
    header, *rows = shown_weights
    for column, key in enumerate(header[1:], start=1):
        weights = shown.weights(shown.case_id(key))
        for row in rows:
            assert row[column] == weights.get(row[0], "Removed"), (key, row[0])
    assert [row[0] for row in rows if "Removed" in row] == ["Value/Sales Yield"]


def test_a_removals_weights_are_aligned_by_the_baselines_nodes_not_their_paths(
    reports: Reports,
) -> None:
    """`no-first-yield` removes the first of `Value P/E`'s two factors named Yield, so its
    settings.csv names the one left by its name, `Value P\\/E/Yield`, where the baseline's names
    it by its position, `Value P\\/E/#2`."""
    (shown,) = reports("positions")

    rows = shown.document.ranking_weights()

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
    baseline = shown.weights(shown.case_id("baseline"))
    removal = shown.weights(shown.case_id("no-first-yield"))
    assert list(baseline)[:3] == [r"Value P\/E", r"Value P\/E/#1", r"Value P\/E/#2"]
    assert list(removal)[:3] == [r"Value P\/E", r"Value P\/E/Yield", r"Value P\/E/Cash Flow"]
    # The case's weight of the factor left is in that node's baseline row, and no row is added
    # for the path only the case's settings.csv holds.
    assert removal[r"Value P\/E/Yield"] == "60"
    assert r"Value P\/E/Yield" not in [row[0] for row in rows]


# No case is ordered, ranked, or marked


UUID: Final = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


def without_values(document: Document) -> str:
    """The report's main text, without the metrics tables, which hold each case's values, the
    artifacts' table, whose IDs and sizes follow the responses, and the random attempt IDs."""
    text = document.root.find_all("main")[0].text
    for heading in ("Strategy", "Benchmark", "Artifacts"):
        text = text.replace(document.table_after(heading).text, "")
    return UUID.sub("", text)


def test_with_two_cases_responses_swapped_no_case_is_sorted_ranked_or_marked(
    reports: Reports,
) -> None:
    (first,) = reports("experiment")
    (second,) = reports("swapped")
    before, after = first.document, second.document
    heavy, removal = (2 + CASES.index(key) for key in ("value-heavy", "no-sales-yield"))

    # Each table gives a column for each case in the plan's order, whatever its values.
    assert before.ranking_weights() == after.ranking_weights() == EXAMPLE_WEIGHTS
    for heading in ("Strategy", "Benchmark"):
        shown = [d.texts(d.table_after(heading)) for d in (before, after)]
        assert shown[0][0] == shown[1][0] == ["Metric", "Unit", *CASES]
        columns = [list(zip(*rows[1:], strict=True)) for rows in shown]
        if heading == "Strategy":
            # changed-metrics.json changes only the strategy's metrics.
            assert columns[0][heavy] != columns[0][removal]
        expected = list(columns[0])
        expected[heavy], expected[removal] = columns[0][removal], columns[0][heavy]
        assert columns[1] == expected
    assert before.texts(before.table_after("Planned cases")) == after.texts(
        after.table_after("Planned cases")
    )
    assert without_values(before) == without_values(after)
    # Nothing marks a case: no element is styled or emphasized for one, and no cell of the
    # weights' table holds anything but its value.
    for document in (before, after):
        main = document.root.find_all("main")[0]
        assert not [e for e in main.iter() if e.tag in ("mark", "b", "strong", "u", "i")]
        assert not [e for e in main.iter() if "style" in e.attrs]
        (table,) = (t for e in document.under("The ranking's weights") for t in e.find_all("table"))
        for cell in (cell for row in document.rows(table) for cell in row):
            assert cell.attrs == {}
    classes = [{e.attrs.get("class") for e in d.root.iter()} for d in (before, after)]
    assert classes[0] == classes[1]


def prose(element: Element) -> str:
    """The text inside `element`, apart from each `<code>`'s, which names a call, a file, or a
    value, such as `rank_update` or `POST /rank`, never a judgment of a case."""
    if element.tag == "code":
        return " "
    return " ".join(child if isinstance(child, str) else prose(child) for child in element.children)


@pytest.mark.parametrize("name", ["experiment", "positions", "snapshot-experiment"])
def test_no_case_is_called_best_or_ranked(reports: Reports, name: str) -> None:
    for shown in reports(name):
        main = " ".join(prose(shown.document.root.find_all("main")[0]).split())
        # The budget cites Portfolio123's documentation of the call by its page's title.
        main = main.replace("API functions: Rank,", "")

        # The conclusion and the weights' table say that no case is ranked or called best, and
        # nothing says otherwise: the only other sentences that rank are the method's, whose
        # backtest ranks by `ApiRankingSystem`'s name.
        assert_no_case_is_called_best(main, "ranks by that system's name")


# The definition's source, the calls, and the limitations


@pytest.mark.parametrize(
    ("name", "sources"),
    [
        (
            "run",
            [
                (
                    None,
                    (
                        f"A file, by the definition's hash, {DEFINITION_HASH}. definition.xml is"
                        " the run's copy of the file, byte for byte."
                    ),
                )
            ],
        ),
        (
            "snapshot-run",
            [
                (
                    None,
                    (
                        f"A ranking snapshot of the system {SYSTEM}, as its record, snapshot.json,"
                        f" gives it. The definition's hash: {DEFINITION_HASH}. definition.xml and"
                        " snapshot.json are the run's copies of the snapshot's files, byte for"
                        " byte."
                    ),
                )
            ],
        ),
        ("experiment", [("1", f"A file, by the definition's hash, {DEFINITION_HASH}.")]),
        (
            "snapshot-experiment",
            [
                (
                    "1",
                    (
                        f"A ranking snapshot of the system {SYSTEM}, as its record, snapshot.json,"
                        f" gives it. The definition's hash: {DEFINITION_HASH}."
                    ),
                )
            ],
        ),
    ],
)
def test_each_report_gives_its_definitions_source(
    reports: Reports, name: str, sources: list[tuple[str | None, str]]
) -> None:
    (shown,) = reports(name)
    document = shown.document

    assert document.ranking_sources() == sources
    heading = document.heading("The ranking definition's source")
    assert heading.inside(document.root.by_id("data"))


def test_a_runs_attempt_gives_its_post_rank_with_its_cost_beside_the_backtests(
    reports: Reports,
) -> None:
    (shown,) = reports("run")
    (attempt,) = shown.out.glob("cases/*/attempts/*")
    document = shown.document

    assert document.attempts_shown() == [
        AttemptShown(
            None,
            attempt.name,
            (
                "POST /auth: Response 200",
                "POST /rank: Response 200",
                "POST /screen/backtest: Response 200",
            ),
            COSTS,
        )
    ]
    # The run's cost sums both requests' costs.
    assert document.dd("Cost")[0] == "6 credits, as Portfolio123 reported"


def test_each_experiment_attempt_gives_its_post_rank_with_its_cost_beside_the_backtests(
    reports: Reports,
) -> None:
    (shown,) = reports("experiment")

    attempts = shown.document.attempts_shown()

    # The baseline's attempt authenticates for the session; the others send with its token.
    assert [(a.case, a.exchanges, a.cost) for a in attempts] == [
        (
            f"{key}, {shown.case_id(key)}",
            (
                *(("POST /auth: Response 200",) if key == "baseline" else ()),
                "POST /rank: Response 200",
                "POST /screen/backtest: Response 200",
            ),
            COSTS,
        )
        for key in CASES
    ]
    for attempt in attempts:
        case_id = shown.case_id(attempt.case.split(", ")[0]) if attempt.case else ""
        assert (shown.out / "cases" / case_id / "attempts" / attempt.attempt_id).is_dir()


@pytest.mark.parametrize(
    ("name", "each"),
    [
        ("run", "The run's definition"),
        ("snapshot-run", "The run's definition"),
        ("experiment", "Each case's definition"),
        ("positions", "Each case's definition"),
        ("snapshot-experiment", "Each case's definition"),
    ],
)
def test_the_limitations_say_where_each_definition_is_written_and_what_the_lock_cant_exclude(
    reports: Reports, name: str, each: str
) -> None:
    (shown,) = reports(name)

    items = shown.document.items_under("Limitations")

    assert WRITTEN.format(each=each) in items
    assert LOCK in items


@pytest.mark.parametrize("name", EVERY)
def test_a_report_never_holds_the_definitions_text(reports: Reports, name: str) -> None:
    for shown in reports(name):
        html = shown.html
        for part in ("RankingSystem RankType", "Composite", "StockFormula", "StockFactor"):
            assert part not in html
        for part in ("RankType", 'Scope="Universe"', "Scope=&quot;Universe&quot;", "<Formula"):
            assert part not in html
        assert "&lt;Formula" not in html


# What the report holds, and doesn't (R01-AC13's rules)


@pytest.mark.parametrize("name", EVERY)
def test_the_concise_notice_comes_first_and_links_to_the_full_notice_with_the_license(
    reports: Reports, name: str
) -> None:
    for shown in reports(name):
        assert_concise_notice_first(shown.document)
        assert_full_notice(shown.document, cast("str", shown.manifest["trialfolio_version"]))


@pytest.mark.parametrize("name", EVERY)
def test_the_closing_section_holds_the_portfolio123_data_statement_outside_the_full_notice(
    reports: Reports, name: str
) -> None:
    for shown in reports(name):
        assert_closing(shown.document)


@pytest.mark.parametrize("name", EVERY)
def test_its_only_outside_links_are_the_license_and_portfolio123s_terms(
    reports: Reports, name: str
) -> None:
    for shown in reports(name):
        version = cast("str", shown.manifest["trialfolio_version"])
        manifest = shown.listed.relative_to(shown.out).as_posix()

        # Each file the manifest lists is linked, the definition's copy among them.
        assert_links(shown.document, version, shown.path, shown.out, manifest)
        assert any(
            Path(path).name == "definition.xml" for path in listed_files(shown.out, manifest)
        )


@pytest.mark.parametrize("name", EVERY)
def test_it_runs_and_loads_nothing(reports: Reports, name: str) -> None:
    for shown in reports(name):
        assert_loads_nothing(shown.document)


@pytest.mark.parametrize("name", EVERY)
def test_statistical_validation_and_trading_readiness_read_not_assessed(
    reports: Reports, name: str
) -> None:
    for shown in reports(name):
        assert_not_assessed(shown.document)


# The synthetic run and experiment (DSC-04)


@pytest.mark.parametrize("name", SYNTHETIC_RUNS)
def test_the_synthetic_runs_report_says_its_values_are_invented(
    reports: Reports, name: str
) -> None:
    (shown,) = reports(name)
    document = shown.document
    (banner,) = (p for p in document.root.find_all("p") if p.attrs.get("class") == "synthetic")

    assert shown.manifest["synthetic"] is True
    assert document.before(banner, document.root.by_id("objective"))
    assert "from invented values" in banner.text
    assert "None of them comes from Portfolio123, and nothing was sent to it." in banner.text
    items = document.items_under("Limitations")
    assert SYNTHETIC.format(kind="run") in items
    assert LOCK not in items
    (attempt,) = document.attempts_shown()
    assert attempt.cost == NOT_REPORTED
    assert "Portfolio123 reported" not in document.root.text


@pytest.mark.parametrize("name", SYNTHETIC_EXPERIMENTS)
def test_the_synthetic_experiments_reports_say_their_values_are_invented(
    reports: Reports, name: str
) -> None:
    first, second = reports(name)

    assert second.document.ranking_weights() == SYNTHETIC_WEIGHTS
    for shown in (first, second):
        document = shown.document
        (kind,) = (e for e in document.root.iter() if e.attrs.get("class") == "kind")
        (banner,) = (e for e in document.root.iter() if e.attrs.get("class") == "synthetic")

        assert shown.manifest["synthetic"] is True
        assert kind.text.endswith("Synthetic experiment")
        assert document.before(banner, document.root.by_id("objective"))
        assert "invented" in banner.text
        for heading in ("Strategy", "Benchmark"):
            (caption,) = document.table_after(heading).find_all("caption")
            assert "Every value is invented." in caption.text
        items = document.items_under("Limitations")
        assert SYNTHETIC.format(kind="experiment") in items
        assert LOCK not in items
        assert {attempt.cost for attempt in document.attempts_shown()} == {NOT_REPORTED}
        assert "Portfolio123 reported" not in document.root.text
