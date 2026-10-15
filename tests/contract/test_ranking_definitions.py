"""Reading a ranking definition, naming its nodes, and applying a ranking variant enforce
docs/contracts.md's ranking definitions, node paths, and ranking variants.

Traces to R04-AC02, as release 0.4.0's test pairing gives it for this module: each invalid
definition in tests/fixtures/experiment-configs/ranking/invalid/, named by
`screen-configs/definition.yaml` and by `ranking-example.yaml`'s baseline, fails with
`config.invalid`, and the message names the configuration's key, the rule, and the line the
directory's README gives, and holds no text of the definition; a path that names nothing gives
`input.not_found`; and each of the ranking variants' invalid configurations that depend on the
definition fails by its own rule, naming its entry by its place. The other tests trace to the
rules of those three sections that R04-AC01's plan builds on: a definition's text, its line ends
and its references, the canonical paths, each ranking variant's case, made by the text rules,
and `ranking-written-differently.yaml` and `ranking-positions.yaml`, which name nodes by
position. R04-T06 wrote them, with the readers' reading of the definition's file.
"""

import os
import re
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from tests.support import canaries
from trialfolio.canonical import sha256_hex
from trialfolio.configuration import (
    ExperimentConfigurationRead,
    ScreenConfigurationRead,
    read_experiment_configuration_v1_1,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.experiment_configuration import RankingVariant
from trialfolio.errors import TrialFolioError
from trialfolio.ranking_definitions import (
    DefinitionProblem,
    NodePathProblem,
    RankingDefinition,
    apply_ranking_variant,
    parse_node_path,
    read_definition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures"
EXPERIMENTS = FIXTURES / "experiment-configs"
RANKING = EXPERIMENTS / "ranking"
INVALID_DEFINITIONS = RANKING / "invalid"
INVALID_CONFIGURATIONS = EXPERIMENTS / "invalid"
SCREEN = FIXTURES / "screen-configs" / "definition.yaml"
EXAMPLE = EXPERIMENTS / "ranking-example.yaml"


def read_screen(path: Path) -> ScreenConfigurationRead:
    return read_screen_configuration_v1_1(path.read_bytes(), path.name, path)


def read_experiment(path: Path) -> ExperimentConfigurationRead:
    return read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)


def definition(name: str) -> RankingDefinition:
    return read_definition((RANKING / name).read_bytes())


def rejection(path: Path, code: str = "config.invalid") -> TrialFolioError:
    """Reads the configuration at `path` with its reader, by its kind, and expects `code`."""
    reader = (
        read_screen if path.read_text(encoding="utf-8").count("kind: screen") else read_experiment
    )
    with pytest.raises(TrialFolioError) as caught:
        reader(path)
    assert caught.value.code == code
    return caught.value


def problems(path: Path) -> list[str]:
    """The problems a `config.invalid` message lists, one for each line after its first."""
    error = rejection(path)
    assert error.log_message == error.message
    first, *listed = error.message.split("\n")
    assert first == f"{path.name} isn't a valid configuration:"
    return [line.removeprefix("- ") for line in listed]


def laid_out(tmp_path: Path, content: bytes) -> tuple[Path, Path]:
    """Copies of `screen-configs/definition.yaml` and `ranking-example.yaml`, laid out as the
    fixtures are, with `content` in place of `value-momentum.xml`, which both name."""
    screen = tmp_path / "screen-configs" / SCREEN.name
    experiment = tmp_path / "experiment-configs" / EXAMPLE.name
    xml = tmp_path / "experiment-configs" / "ranking" / "value-momentum.xml"
    for path in (screen, xml):
        path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SCREEN, screen)
    shutil.copyfile(EXAMPLE, experiment)
    xml.write_bytes(content)
    return screen, experiment


# The definition's file.


def readme_lines() -> dict[str, int]:
    readme = (INVALID_DEFINITIONS / "README.md").read_text(encoding="utf-8")
    return {
        name: int(line)
        for name, line in re.findall(
            r"^\| `([a-z0-9-]+)\.xml` \| .+ \| (\d+) \|$", readme, re.MULTILINE
        )
    }


RULES = {
    "not-well-formed": "it isn't well-formed XML 1.0: mismatched tag",
    "not-utf-8": "the file isn't UTF-8 text",
    "byte-order-mark": "the file starts with a byte-order mark",
    "root-not-ranking-system": "its root element isn't RankingSystem",
    "text-after-root": "it holds something other than white space after its RankingSystem element",
    "xml-declaration": "it holds an XML declaration",
    "doctype": "it holds a document type declaration",
    "comment": "it holds a comment",
    "processing-instruction": "it holds a processing instruction",
    "no-node": "its RankingSystem element holds no node",
    "empty-composite": "a Composite holds no node",
    "conditional-node": "an element where a node goes isn't a Composite, a StockFormula, or a",
    "ind-formula-node": "an element where a node goes isn't a Composite, a StockFormula, or a",
    "text-between-nodes": "it holds text between nodes",
    "stock-formula-other-element": "a StockFormula holds an element other than Formula",
    "stock-factor-other-element": "a StockFactor holds an element other than Factor",
    "formula-holds-element": "a Formula holds an element, where it holds only text",
    "missing-weight": "a node has no Weight attribute",
    "weight-zero": "a node's Weight is 0, which Portfolio123 reads as equal weighting",
    "weight-percent": "a node's Weight isn't a decimal in plain notation",
    "weight-space": "a node's Weight isn't a decimal in plain notation",
    "weight-sign": "a node's Weight isn't a decimal in plain notation",
    "weight-exponent": "a node's Weight isn't a decimal in plain notation",
    "weight-five-decimals": "a node's Weight has more than 4 digits after the decimal point",
    "weight-too-large": "a node's Weight must be less than 10^16",
    "weight-character-reference": "a node's Weight is written with a character or entity reference",
}
"""The rule each invalid definition breaks, as its message gives it."""


def test_every_invalid_definition_is_in_its_readme_and_has_its_rule() -> None:
    names = {path.stem for path in INVALID_DEFINITIONS.glob("*.xml")}

    assert set(readme_lines()) == names
    assert set(RULES) == names


def definition_text(path: Path) -> list[str]:
    """Each text the definition at `path` holds: its attribute values and its elements' text,
    of two characters or more, as a message mustn't quote them."""
    text = path.read_bytes().decode("utf-8", errors="replace")
    found = re.findall(r"=\"([^\"]*)\"", text) + re.findall(r">([^<]*)<", text)
    found += re.findall(r"^\s*([^<\s][^\n]*)$", text, re.MULTILINE)  # text outside elements
    return [value.strip() for value in found if len(value.strip()) >= 2]


@pytest.mark.parametrize("key", ["ranking.definition", "baseline.ranking.definition"])
@pytest.mark.parametrize(
    "path", sorted(INVALID_DEFINITIONS.glob("*.xml")), ids=lambda path: path.stem
)
def test_an_invalid_definition_fails_naming_its_key_rule_and_line(
    tmp_path: Path, path: Path, key: str
) -> None:
    screen, experiment = laid_out(tmp_path, path.read_bytes())

    (problem,) = problems(screen if key == "ranking.definition" else experiment)

    line = readme_lines()[path.stem]
    assert problem.startswith(
        f"`{key}` names a definition Trial Folio can't read, at line {line}: {RULES[path.stem]}"
    )
    assert "…" not in problem
    for value in definition_text(path):
        assert not re.search(rf"(?<![\w.^-]){re.escape(value)}(?![\w-])", problem), value


def test_a_definition_path_that_names_nothing_is_not_found(tmp_path: Path) -> None:
    """The file's path is shown, as the configuration gives it, but never logged: logs never
    hold a configuration's values."""
    screen, experiment = laid_out(tmp_path, b"")
    (tmp_path / "experiment-configs" / "ranking" / "value-momentum.xml").unlink()

    for path, key in ((screen, "ranking.definition"), (experiment, "baseline.ranking.definition")):
        error = rejection(path, "input.not_found")
        given = (
            "../experiment-configs/ranking/value-momentum.xml"
            if path == screen
            else "ranking/value-momentum.xml"
        )
        assert error.message.startswith(
            f"{path.name}: the file `{key}` names (`{given}`) doesn't exist. A definition's path "
            "is read from the configuration's directory, unless it's absolute"
        )
        assert error.log_message.startswith(f"{path.name}: the file `{key}` names doesn't exist.")
        assert "value-momentum" not in error.log_message


def test_a_definition_path_that_names_a_directory_is_invalid(tmp_path: Path) -> None:
    _, experiment = laid_out(tmp_path, b"")
    xml = tmp_path / "experiment-configs" / "ranking" / "value-momentum.xml"
    xml.unlink()
    xml.mkdir()

    (problem,) = problems(experiment)

    assert problem.startswith(
        "`baseline.ranking.definition` names something that isn't a file, such as a directory."
    )


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0, reason="needs file permissions that bind"
)
def test_a_definition_that_can_t_be_read_is_not_found(tmp_path: Path) -> None:
    """As a configuration file that can't be read is: the error says why."""
    screen, _ = laid_out(tmp_path, (RANKING / "value-momentum.xml").read_bytes())
    xml = tmp_path / "experiment-configs" / "ranking" / "value-momentum.xml"
    xml.chmod(0)
    try:
        error = rejection(screen, "input.not_found")
    finally:
        xml.chmod(0o644)

    assert error.message.startswith(
        f"{screen.name}: couldn't read the file `ranking.definition` names "
        "(`../experiment-configs/ranking/value-momentum.xml`): Permission denied."
    )
    assert error.log_message == (
        f"{screen.name}: couldn't read the file `ranking.definition` names: Permission denied."
    )


def test_an_absolute_definition_path_is_read_where_it_leads(tmp_path: Path) -> None:
    content = SCREEN.read_text(encoding="utf-8").replace(
        "'../experiment-configs/ranking/value-momentum.xml'",
        f"'{(RANKING / 'value-momentum.xml').as_posix()}'",
    )
    path = tmp_path / "screen.yaml"
    path.write_text(content, encoding="utf-8")

    read = read_screen(path)

    assert read.definition == definition("value-momentum.xml")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symbolic links")
def test_a_definition_is_read_where_the_file_system_resolves_its_path(tmp_path: Path) -> None:
    """A `..` after a symbolic link leads to the parent of the link's target, as opening the path
    does, and as a review finds its runs."""
    real = tmp_path / "real" / "screen-configs"
    screen, _ = laid_out(tmp_path / "real", (RANKING / "value-momentum.xml").read_bytes())
    os.symlink(real, tmp_path / "link")
    # Where `..` would lead if it removed the link's name, there's another definition.
    other = tmp_path / "experiment-configs" / "ranking" / "value-momentum.xml"
    other.parent.mkdir(parents=True)
    other.write_bytes((RANKING / "value-heavy.xml").read_bytes())

    read = read_screen(tmp_path / "link" / screen.name)

    assert read.definition == definition("value-momentum.xml")


def test_the_definition_s_bytes_are_kept_for_its_copy(tmp_path: Path) -> None:
    """The copy, `definition.xml`, is written from the bytes read in step 2, never by reading the
    file again (ranking definitions, its copy): a file changed after it was read doesn't change
    what the read holds."""
    content = (RANKING / "value-momentum.xml").read_bytes()
    screen, _ = laid_out(tmp_path, content)

    read = read_screen(screen)
    changed = (RANKING / "value-heavy.xml").read_bytes()
    (tmp_path / "experiment-configs" / "ranking" / "value-momentum.xml").write_bytes(changed)

    assert read.definition is not None
    assert read.definition.content == content
    assert read.definition == definition("value-momentum.xml")
    assert read_screen(screen).definition == definition("value-heavy.xml")


# The definition's text and form.


def test_the_example_s_definition_reads_as_its_nodes() -> None:
    read = definition("value-momentum.xml")
    content = (RANKING / "value-momentum.xml").read_bytes()

    assert read.content == content
    assert read.text == content.decode("utf-8")
    assert read.hash == "sha256:" + sha256_hex(content)
    assert [(node.path, node.kind, str(node.weight), node.line) for node in read.nodes] == [
        ("Value", "Composite", "40", 2),
        ("Value/Earnings Yield", "StockFormula", "50", 3),
        ("Value/Sales Yield", "StockFormula", "50", 6),
        ("Momentum", "Composite", "30", 10),
        ("Momentum/Six-Month Return", "StockFormula", "50", 11),
        ("Momentum/Year Return", "StockFormula", "50", 14),
        ("Quality", "Composite", "30", 18),
        ("Quality/Return on Equity", "StockFormula", "50", 19),
        ("Quality/Gross Margin", "StockFormula", "50", 22),
    ]
    assert [node.position for node in read.children(None)] == [1, 2, 3]
    assert [node.name for node in read.children(read.nodes[3])] == [
        "Six-Month Return",
        "Year Return",
    ]


@pytest.mark.parametrize("line_end", [b"\r\n", b"\r"], ids=["crlf", "cr"])
def test_each_line_end_is_read_as_a_line_feed(tmp_path: Path, line_end: bytes) -> None:
    """So a definition sent never holds a carriage return, and a file checked out with Windows
    line endings gives the same definition, and the same cases, as one checked out without."""
    content = (RANKING / "value-momentum.xml").read_bytes()
    _, experiment = laid_out(tmp_path, content.replace(b"\n", line_end))

    read = read_experiment(experiment)
    original = read_experiment(EXAMPLE)

    assert read.definition is not None and original.definition is not None
    assert read.definition.content == content.replace(b"\n", line_end)
    assert read.definition.text == original.definition.text
    assert "\r" not in read.definition.text
    assert read.definition.hash == original.definition.hash
    assert [case.definition.text for case in read.ranking_cases] == [
        case.definition.text for case in original.ranking_cases
    ]


def test_references_are_read_in_names_and_kept_in_the_text() -> None:
    """A name is its `Name` attribute as XML reads it, with its references replaced; the
    definition sent keeps them as written, and a formula may hold them."""
    content = (
        '<RankingSystem RankType="Higher">\n'
        '\t<StockFormula Name="Cash &amp; Debt" Weight="60" RankType="Higher">\n'
        "\t\t<Formula>Close(0) &lt; Close(20)</Formula>\n"
        "\t</StockFormula>\n"
        '\t<StockFormula Name="&#35;2" Weight="40" RankType="Higher">\n'
        "\t\t<Formula>…</Formula>\n"
        "\t</StockFormula>\n"
        "</RankingSystem>\n"
    ).encode()

    read = read_definition(content)

    assert [(node.name, node.path) for node in read.nodes] == [
        ("Cash & Debt", "Cash & Debt"),
        ("#2", "\\#2"),
    ]
    assert read.text == content.decode()
    assert read.node("\\#2") == read.nodes[1]
    assert read.node("#2") == read.nodes[1]


def test_attributes_other_than_weight_and_name_aren_t_read() -> None:
    """They're sent as they're written: a `>` in one, and attributes in any order, or in single
    quotes, read the same."""
    content = (
        "<RankingSystem>\n"
        "\t<StockFormula Description='a > b' Weight = '25.50' Name=\"Only\" Scope=\"Universe\">"
        "<Formula>…</Formula></StockFormula>\n"
        "</RankingSystem>\n"
    ).encode()

    (node,) = read_definition(content).nodes

    assert (node.name, node.weight, node.weight_text) == ("Only", Decimal("25.5"), "25.50")


def test_a_node_without_a_name_or_with_an_empty_one_has_none() -> None:
    content = (
        "<RankingSystem>\n"
        '\t<StockFactor Weight="50"><Factor>…</Factor></StockFactor>\n'
        '\t<StockFactor Name="" Weight="50"><Factor>…</Factor></StockFactor>\n'
        "</RankingSystem>\n"
    ).encode()

    assert [(node.name, node.path) for node in read_definition(content).nodes] == [
        (None, "#1"),
        (None, "#2"),
    ]


def test_an_empty_element_tag_composite_holds_no_node() -> None:
    content = b'<RankingSystem>\n\t<Composite Name="Empty" Weight="100"/>\n</RankingSystem>\n'

    with pytest.raises(DefinitionProblem, match="a Composite holds no node") as caught:
        read_definition(content)

    assert caught.value.line == 2


def test_a_factor_needn_t_hold_its_element() -> None:
    """Trial Folio doesn't count a factor's `Formula` or `Factor` elements, or read its text."""
    content = (
        "<RankingSystem>\n"
        '\t<StockFormula Name="A" Weight="50"/>\n'
        '\t<StockFactor Name="B" Weight="50">text<Factor>…</Factor><Factor/></StockFactor>\n'
        "</RankingSystem>\n"
    ).encode()

    assert [node.kind for node in read_definition(content).nodes] == ["StockFormula", "StockFactor"]


# Node paths and canonical paths.


@pytest.mark.parametrize(
    ("path", "segments"),
    [
        ("Value", ("Value",)),
        ("Value/Sales Yield", ("Value", "Sales Yield")),
        ("#1/#2", (1, 2)),
        ("Value P\\/E/#10", ("Value P/E", 10)),
        ("Price\\\\Book", ("Price\\Book",)),
        ("\\#Momentum", ("#Momentum",)),
        ("Value #2", ("Value #2",)),
        (" Spaced ", (" Spaced ",)),
    ],
)
def test_a_node_path_reads_as_its_segments(path: str, segments: tuple[str | int, ...]) -> None:
    assert parse_node_path(path) == segments


@pytest.mark.parametrize(
    ("path", "segment", "problem"),
    [
        ("", 1, "is empty"),
        ("/Value", 1, "is empty"),
        ("Value/", 2, "is empty"),
        ("#", 1, "starts with # but isn't a position"),
        ("#01", 1, "starts with # but isn't a position"),
        ("#2a", 1, "starts with # but isn't a position"),
        ("#0", 1, "is position 0"),
        ("Value\\", 1, "holds a \\ that starts no escape"),
        ("a\\#b", 1, "holds a \\ that starts no escape"),
        ("Value/\\n", 2, "holds a \\ that starts no escape"),
    ],
)
def test_a_node_path_written_wrongly_names_its_segment(
    path: str, segment: int, problem: str
) -> None:
    with pytest.raises(NodePathProblem) as caught:
        parse_node_path(path)

    assert caught.value.segment == segment
    assert caught.value.problem.startswith(problem)


def test_positions_xml_s_canonical_paths() -> None:
    """By name where no other node of the parent has it, by position otherwise, with escapes:
    the two factors named Yield, and the two factors without a name, by their positions."""
    read = definition("positions.xml")

    assert [node.path for node in read.nodes] == [
        "Value P\\/E",
        "Value P\\/E/#1",
        "Value P\\/E/#2",
        "Value P\\/E/Cash Flow",
        "#2",
        "#3",
        "Price\\\\Book",
        "Price\\\\Book/Book Yield",
        "\\#Momentum",
        "\\#Momentum/Short Return",
        "\\#Momentum/Long Return",
        "Secret Sauce",
        "Secret Sauce/Margin",
        "Secret Sauce/Turnover",
    ]
    assert [node.kind for node in read.nodes][4:6] == ["StockFactor", "StockFactor"]
    # Every node's canonical path names it.
    assert all(read.node(node.path) == node for node in read.nodes)


# Ranking variants.


def variant(set_: dict[str, int | str], remove: str | None = None) -> RankingVariant:
    weights = {path: Decimal(str(weight)) for path, weight in set_.items()}
    if remove is None:
        return RankingVariant(key="case", set=weights)
    return RankingVariant(key="case", set=weights, remove=remove)


def test_the_example_s_variants_give_the_definitions_it_describes() -> None:
    read = read_experiment(EXAMPLE)
    baseline = definition("value-momentum.xml")
    text = baseline.text

    assert read.definition == baseline
    heavy, tilt, no_sales = read.ranking_cases
    assert heavy.definition.text == (RANKING / "value-heavy.xml").read_text(encoding="utf-8")
    assert tilt.definition.text == text.replace(
        'Name="Earnings Yield" Weight="50"', 'Name="Earnings Yield" Weight="70"'
    ).replace('Name="Sales Yield" Weight="50"', 'Name="Sales Yield" Weight="30"')
    sales = text[text.index('\n\t\t<StockFormula Name="Sales Yield"') :]
    sales = sales[: sales.index("</StockFormula>") + len("</StockFormula>")]
    assert no_sales.definition.text == text.replace(sales, "").replace(
        'Name="Earnings Yield" Weight="50"', 'Name="Earnings Yield" Weight="100"'
    )
    assert [(case.place, case.remove and case.remove.path) for case in read.ranking_cases] == [
        ("variants.ranking[0]", None),
        ("variants.ranking[1]", None),
        ("variants.ranking[2]", "Value/Sales Yield"),
    ]
    assert [
        [(entry.place, entry.node.path, entry.weight) for entry in case.set]
        for case in read.ranking_cases
    ] == [
        [
            ("variants.ranking[0].set[0]", "Value", Decimal(60)),
            ("variants.ranking[0].set[1]", "Momentum", Decimal(20)),
            ("variants.ranking[0].set[2]", "Quality", Decimal(20)),
        ],
        [
            ("variants.ranking[1].set[0]", "Value/Earnings Yield", Decimal(70)),
            ("variants.ranking[1].set[1]", "Value/Sales Yield", Decimal(30)),
        ],
        [("variants.ranking[2].set[0]", "Value/Earnings Yield", Decimal(100))],
    ]
    # The case's own nodes, with their canonical paths: 8 without Sales Yield.
    assert [node.path for node in no_sales.definition.nodes] == [
        node.path for node in baseline.nodes if node.path != "Value/Sales Yield"
    ]


def test_the_screen_s_definition_is_the_example_baseline_s() -> None:
    read = read_screen(SCREEN)
    experiment = read_experiment(EXAMPLE)

    assert read.definition is not None and experiment.definition is not None
    assert read.definition.hash == experiment.definition.hash
    assert read.definition.text == experiment.definition.text


def test_written_differently_gives_the_example_s_cases() -> None:
    """By position, in another order, `60.0`, and in double quotes: the same definitions, and
    each entry the same node and weight, in the definition's order."""
    example = read_experiment(EXAMPLE)
    written = read_experiment(EXPERIMENTS / "ranking-written-differently.yaml")

    def cases(read: ExperimentConfigurationRead) -> list[object]:
        return [
            (
                case.definition.text,
                [(entry.node.path, entry.weight) for entry in case.set],
                case.remove and case.remove.path,
            )
            for case in read.ranking_cases
        ]

    assert written.definition == example.definition
    assert cases(written) == cases(example)
    # Each entry keeps its own place in its file.
    assert [entry.place for entry in written.ranking_cases[0].set] == [
        "variants.ranking[0].set[1]",
        "variants.ranking[0].set[0]",
        "variants.ranking[0].set[2]",
    ]


def test_ranking_positions_names_nodes_by_position_and_by_escaped_names() -> None:
    read = read_experiment(EXPERIMENTS / "ranking-positions.yaml")

    heavy, no_first = read.ranking_cases
    assert [(entry.node.path, str(entry.weight)) for entry in heavy.set] == [
        ("Value P\\/E", "30"),
        ("#2", "5"),
        ("#3", "5"),
        ("Price\\\\Book", "25"),
        ("\\#Momentum", "15"),
        ("Secret Sauce", "20"),
    ]
    assert [str(node.weight) for node in heavy.definition.children(None)] == [
        "30",
        "5",
        "5",
        "25",
        "15",
        "20",
    ]
    assert no_first.remove is not None and no_first.remove.path == "Value P\\/E/#1"
    assert [(entry.node.path, str(entry.weight)) for entry in no_first.set] == [
        ("Value P\\/E/#2", "60"),
        ("Value P\\/E/Cash Flow", "40"),
    ]
    # The factor left of the two named Yield is the only one now, so its name names it.
    assert [node.path for node in no_first.definition.nodes][:3] == [
        "Value P\\/E",
        "Value P\\/E/Yield",
        "Value P\\/E/Cash Flow",
    ]


def test_a_weight_variant_rewrites_only_the_weights_that_differ() -> None:
    """In their normalized form, between their quotes; a weight given unchanged keeps its text,
    even one written `30.0`."""
    baseline = read_definition(
        (RANKING / "value-momentum.xml")
        .read_bytes()
        .replace(b'Name="Momentum" Weight="30"', b'Name="Momentum" Weight="30.0"')
    )

    case = apply_ranking_variant(
        baseline, variant({"Value": "50.000", "Momentum": 30, "Quality": "20.0"}), "v"
    )

    assert case.definition.text == baseline.text.replace(
        'Name="Value" Weight="40"', 'Name="Value" Weight="50"'
    ).replace('Name="Quality" Weight="30"', 'Name="Quality" Weight="20"')
    assert 'Name="Momentum" Weight="30.0"' in case.definition.text


def test_a_removal_takes_out_its_element_alone_when_it_shares_its_line() -> None:
    """Its line goes with it only when spaces and tabs alone come before it there."""
    baseline = read_definition(
        b'<RankingSystem>\n\t<Composite Name="C" Weight="100">'
        b'<StockFormula Name="A" Weight="50"/>  <StockFormula Name="B" Weight="50"/>\n'
        b"\t</Composite>\n</RankingSystem>\n"
    )

    case = apply_ranking_variant(baseline, variant({"C/A": 100}, remove="C/B"), "v")

    assert case.definition.text == (
        '<RankingSystem>\n\t<Composite Name="C" Weight="100">'
        '<StockFormula Name="A" Weight="100"/>  \n'
        "\t</Composite>\n</RankingSystem>\n"
    )


def test_a_removal_at_the_top_level_keeps_the_sum_of_every_top_level_node() -> None:
    """A factor at any level can be removed: a top-level StockFactor's weight goes to the nodes
    left beside it, here named by position."""
    baseline = definition("positions.xml")

    case = apply_ranking_variant(
        baseline,
        variant(
            {"#1": 25, "#2": 20, "#4": 20, "#5": 15, "#6": 20},
            remove="#3",
        ),
        "variants.ranking[0]",
    )

    assert [node.path for node in case.definition.children(None)] == [
        "Value P\\/E",
        "#2",
        "Price\\\\Book",
        "\\#Momentum",
        "Secret Sauce",
    ]


def test_the_revised_definition_keeps_two_of_the_example_s_cases(tmp_path: Path) -> None:
    """`value-momentum-revised.xml` changes only the Value composite's factors, which
    `tilt-earnings-yield` and `no-sales-yield` set: their definitions don't change, so a revision
    keeps them, and `value-heavy`'s does."""
    _, experiment = laid_out(tmp_path, (RANKING / "value-momentum-revised.xml").read_bytes())

    revised = read_experiment(experiment)
    example = read_experiment(EXAMPLE)

    assert revised.definition is not None and example.definition is not None
    assert revised.definition.hash != example.definition.hash
    assert [
        case.definition.text == old.definition.text
        for case, old in zip(revised.ranking_cases, example.ranking_cases, strict=True)
    ] == [False, True, True]


def test_synthetic_heavy_is_synthetic_with_its_top_level_weights_moved() -> None:
    case = apply_ranking_variant(
        definition("synthetic.xml"), variant({"Value": 60, "Momentum": 20, "Quality": 20}), "v"
    )

    assert case.definition.text == (RANKING / "synthetic-heavy.xml").read_text(encoding="utf-8")


def test_the_live_check_s_definition_has_the_form_r04_t01_sent() -> None:
    read = definition("live.xml")

    assert [(node.path, node.kind, str(node.weight)) for node in read.nodes] == [
        ("Earnings", "Composite", "50"),
        ("Earnings/Earnings Yield", "StockFormula", "100"),
        ("Liquidity", "Composite", "50"),
        ("Liquidity/Dollar Volume", "StockFormula", "100"),
    ]
    assert "<Formula>EarnYield</Formula>" in read.text
    assert "<Formula>AvgDailyTot(30)</Formula>" in read.text


VARIANT_PROBLEMS = {
    "set-missing-node": (
        "`variants.ranking[0].set` leaves out its parent's node at position 3. A variant gives "
        "the weight of every node of the parent it changes, each once, so none is left for "
        "Portfolio123 to rescale."
    ),
    "set-two-parents": (
        "`variants.ranking[0].set[1]` names a node of another parent than "
        "`variants.ranking[0].set[0]` does. A variant sets the weights of one parent's nodes: "
        "every top-level node, or every node of one composite."
    ),
    "set-node-twice": (
        "`variants.ranking[0].set[3]` names the same node as `variants.ranking[0].set[0]`. A set "
        "gives each node's weight once."
    ),
    "set-sum-differs": (
        "`variants.ranking[0].set` gives weights that don't sum to what the same nodes' weights "
        "sum to in the baseline's definition. A variant moves weight between siblings and keeps "
        "their sum, so no result depends on how Portfolio123 treats another total."
    ),
    "set-changes-nothing": (
        "`variants.ranking[0].set` gives every node the weight it has in the baseline's "
        "definition, so the variant changes nothing. A ranking variant changes at least one "
        "weight, or removes a factor."
    ),
    "path-no-node": (
        "`variants.ranking[1].set[1]` is a node path whose segment 2 names none of its parent's "
        "nodes in the baseline's definition."
    ),
    "path-two-nodes": (
        "`variants.ranking[1].remove` is a node path whose segment 2 names more than one of its "
        "parent's nodes. Name the one it means by its position instead, such as #2."
    ),
    "path-empty-segment": (
        "`variants.ranking[1].set[0]` is a node path whose segment 2 is empty. A path's segments "
        "are separated by single slashes, with none at its start or end."
    ),
    "path-position-zero": (
        "`variants.ranking[1].set[0]` is a node path whose segment 2 is position 0. Positions "
        "count from 1."
    ),
    "path-position-past-end": (
        "`variants.ranking[1].set[1]` is a node path whose segment 2 is a position past its "
        "parent's last node."
    ),
    "path-position-leading-zero": (
        "`variants.ranking[1].set[0]` is a node path whose segment 2 starts with # but isn't a "
        "position: # and a whole number without a leading zero, such as #2. A name that starts "
        "with # is written \\#."
    ),
    "path-position-not-a-number": (
        "`variants.ranking[1].set[0]` is a node path whose segment 2 starts with # but isn't a "
        "position: # and a whole number without a leading zero, such as #2. A name that starts "
        "with # is written \\#."
    ),
    "path-bad-escape": (
        "`variants.ranking[1].set[0]` is a node path whose segment 2 holds a \\ that starts no "
        "escape. In a node path, \\/ stands for /, \\\\ for \\, and \\# at a segment's start for "
        "#. Inside double quotes, YAML reads its own escapes first, so each \\ of a path is "
        "written \\\\ there."
    ),
    "remove-composite": (
        "`variants.ranking[2].remove` names a composite. A variant removes one factor, a "
        "StockFormula or a StockFactor, never a composite with the factors it holds."
    ),
    "remove-only-factor": (
        "`variants.ranking[1].remove` names its parent's only node, so the removal would leave "
        "the parent without one. A removal leaves at least one node beside the factor it removes."
    ),
    "two-variants-one-definition": (
        "`variants.ranking[3]` gives the same definition as `variants.ranking[0]`, so the two "
        "would be one case. Each case has settings of its own."
    ),
}
"""Each of the ranking variants' invalid configurations that depend on the definition, with the
one problem its message gives: its own rule's."""


def test_every_variant_case_is_in_the_invalid_configurations_readme() -> None:
    readme = (INVALID_CONFIGURATIONS / "README.md").read_text(encoding="utf-8")
    section = readme[readme.index("### What a ranking variant's paths name") :]

    assert set(re.findall(r"^\| `([a-z0-9-]+)\.yaml` \|", section, re.MULTILINE)) == set(
        VARIANT_PROBLEMS
    )


@pytest.mark.parametrize("name", sorted(VARIANT_PROBLEMS))
def test_each_ranking_variant_case_fails_by_its_own_rule(name: str) -> None:
    """The invalid configurations' test checks each one's key and value; this one, that its
    message gives its own rule, and nothing else."""
    assert problems(INVALID_CONFIGURATIONS / f"{name}.yaml") == [VARIANT_PROBLEMS[name]]


def ranking_variants(tmp_path: Path, variants: str, base: Path = EXAMPLE) -> list[str]:
    """The problems of `base` with its ranking variants replaced by `variants`, from a copy in
    `tmp_path` whose definition's path is absolute, so it leads where it did."""
    text = base.read_text(encoding="utf-8").replace(
        "    definition: 'ranking/", f"    definition: '{RANKING.as_posix()}/"
    )
    start = text.index("  ranking:\n    - key:")
    end = text.index("  rebalance_weeks: []")
    path = tmp_path / base.name
    path.write_text(text[:start] + variants + text[end:], encoding="utf-8")
    return problems(path)


def test_a_removal_s_set_names_only_the_nodes_left_beside_it(tmp_path: Path) -> None:
    assert ranking_variants(
        tmp_path,
        "  ranking:\n    - key: removed\n      remove: 'Value/Sales Yield'\n"
        "      set: {'Value/Earnings Yield': 50, 'Value/Sales Yield': 50}\n",
    ) == [
        (
            "`variants.ranking[0].set[1]` names the factor the variant removes. A removal's set gives "
            "the weights of the nodes left beside it."
        )
    ]
    assert ranking_variants(
        tmp_path,
        "  ranking:\n    - key: removed\n      remove: 'Value/Sales Yield'\n"
        "      set: {'Value/Earnings Yield': 100, 'Momentum/Year Return': 50}\n",
    ) == [
        (
            "`variants.ranking[0].set[1]` names a node of another parent than the factor the variant "
            "removes. A removal's set gives the weights of the nodes left beside it."
        )
    ]


def test_a_removal_s_weights_keep_the_sum_with_the_factor_it_removes(tmp_path: Path) -> None:
    assert ranking_variants(
        tmp_path,
        "  ranking:\n    - key: removed\n      remove: 'Value/Sales Yield'\n"
        "      set: {'Value/Earnings Yield': 50}\n",
    ) == [
        (
            "`variants.ranking[0].set` gives weights that don't sum to what its parent's nodes, the "
            "factor it removes included, sum to in the baseline's definition. The removed factor's "
            "weight goes to the nodes left beside it."
        )
    ]


def test_a_removal_s_set_leaving_out_a_node_names_it_by_its_position(tmp_path: Path) -> None:
    problem = ranking_variants(
        tmp_path,
        "  ranking:\n    - key: removed\n      remove: '#3'\n      set: {'#1': 70}\n",
        EXPERIMENTS / "ranking-positions.yaml",
    )

    assert problem == [
        (
            "`variants.ranking[0].set` leaves out its parent's node at positions 2, 4, 5, and 6. A "
            "variant gives the weight of every node its parent keeps beside the factor it removes, "
            "each once, so none is left for Portfolio123 to rescale."
        )
    ]


def test_each_variant_s_first_problem_is_listed(tmp_path: Path) -> None:
    """Every variant is checked, and each that breaks a rule gives its first problem."""
    assert ranking_variants(
        tmp_path,
        "  ranking:\n"
        "    - key: first\n      set: {'Value': 60, 'Momentum': 20, 'Quality': 30}\n"
        "    - key: second\n      set: {'Valu': 60}\n"
        "    - key: third\n      set: {'Value': 60, 'Momentum': 20, 'Quality': 20}\n",
    ) == [
        (
            "`variants.ranking[0].set` gives weights that don't sum to what the same nodes' weights "
            "sum to in the baseline's definition. A variant moves weight between siblings and keeps "
            "their sum, so no result depends on how Portfolio123 treats another total."
        ),
        (
            "`variants.ranking[1].set[0]` is a node path whose segment 1 names none of its parent's "
            "nodes in the baseline's definition."
        ),
    ]


def test_messages_never_hold_a_node_s_name() -> None:
    """Paths hold node names, the user's strategy definition, so a message names an entry by its
    place, and a node left out by its position (node paths)."""
    names = [node.name for node in definition("positions.xml").nodes if node.name]
    for name in ("set-missing-node", "path-two-nodes", "remove-only-factor", "set-two-parents"):
        (problem,) = problems(INVALID_CONFIGURATIONS / f"{name}.yaml")
        for node_name in [*names, "Value", "Momentum", "Quality", "Year Return", "Sales Yield"]:
            assert node_name not in problem


def test_a_snapshot_baseline_s_paths_are_checked_for_how_they_re_written(tmp_path: Path) -> None:
    """Release 0.4.0's R04-T10 reads a snapshot, which gives its definition, and so the cases.
    Until then, what's written wrongly in a path fails, and nothing else is read."""
    text = EXAMPLE.read_text(encoding="utf-8").replace(
        "    definition: 'ranking/value-momentum.xml'\n    ranking_method: percentile_nas_negative\n",
        "    snapshot: 'ranking/value-momentum/'\n",
    )
    path = tmp_path / "experiment.yaml"
    path.write_text(text, encoding="utf-8")

    read = read_experiment(path)
    assert (read.definition, read.ranking_cases) == (None, ())

    path.write_text(text.replace("'Value/Sales Yield': 30", "'Value//Sales Yield': 30"), "utf-8")
    assert problems(path) == [
        (
            "`variants.ranking[1].set[1]` is a node path whose segment 2 is empty. A path's segments "
            "are separated by single slashes, with none at its start or end."
        )
    ]
    path.write_text(text.replace("remove: 'Value/Sales Yield'", "remove: 'Value/#0'"), "utf-8")
    assert problems(path) == [
        (
            "`variants.ranking[2].remove` is a node path whose segment 2 is position 0. Positions "
            "count from 1."
        )
    ]


def test_a_ranking_by_another_form_reads_no_definition() -> None:
    screen = read_screen(FIXTURES / "screen-configs" / "formula.yaml")
    experiment = read_experiment(EXPERIMENTS / "example.yaml")

    assert screen.definition is None
    assert (experiment.definition, experiment.ranking_cases) == (None, ())


def test_the_canaries_definition_holds_its_listed_canaries() -> None:
    """Each name, formula, and `Description` holds a distinct canary, and each weight has
    distinctive digits, as `tests/support/canaries.py` lists them, for R04-AC11's scans."""
    read = definition("canaries.xml")
    text = read.text

    assert [node.name for node in read.nodes] == list(canaries.RANKING_DEFINITION[:9])
    assert [node.weight_text for node in read.nodes] == list(canaries.RANKING_DEFINITION[21:])
    assert re.findall(r"<Formula>([^<]*)</Formula>", text) == list(
        canaries.RANKING_DEFINITION[9:15]
    )
    assert re.findall(r'Description="([^"]*)"', text) == list(canaries.RANKING_DEFINITION[15:21])
    assert len(set(canaries.RANKING_DEFINITION)) == len(canaries.RANKING_DEFINITION)
    assert all(text.count(canary) == 1 for canary in canaries.RANKING_DEFINITION)
