"""Reading an experiment configuration 1.1.0, from 0.4.0, enforces docs/contracts.md's experiment
configuration rules for a baseline ranked by a definition or a snapshot, and for ranking variants.

Traces to R04-AC02's ranking variants and baseline, as release 0.4.0's test pairing gives them for
`test_experiment_configuration.py`, from which TS-T07 separated experiment configuration 1.1.0's
tests into this module (docs/test-refactoring.md, modules to separate): the message names a ranking
variant's `set` entry by its place, never by its path; a 1.0.0 file with a ranking variant, or a
baseline ranked by a definition, says they need 1.1.0; and a budget is at least two requests a case.
Also to the ranking example's structure, which the configuration's reader accepts. R04-T05 wrote
them, with the reader of both versions. The 1.0.0 reader's messages for such a file stay 0.3.0's, as
the R04-T05 details in release 0.4.0's changes after sign-off give them; since R04-T12, `trialfolio
run` reads with the reader of both versions, so its messages are that reader's. What a path names in
the definition, and the example's cases, are R04-T06's: since then, the reader of both versions
reads the baseline's definition file, from the configuration's directory, so it's given the
configuration's path, and applies each ranking variant.
The ranking example's six tests, from `test_the_ranking_examples_are_the_fixtures_byte_for_byte` to
`test_an_escaped_slash_names_the_same_node_in_single_and_double_quotes`, repeat the ranking
example's validation, which R04-T02 left for R04-T04's test pairing to give R04-T06; TS-T08
separated them from `test_documented_ranking_example_compiles_to_its_cases`, which keeps the
example's cases (docs/test-refactoring.md, long functions). What the reader reads in the
definition, and each variant's case, are tested in tests/contract/test_ranking_definitions.py. The
invalid files' test, which reads each version's invalid files, is
tests/contract/test_experiment_configuration.py's, and the 0.3.0 experiment example these tests
compare with, and its readers, are tests/support/experiment_configs.py's.
"""

import re
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from tests.support.experiment_configs import example, read, rejection, with_line
from tests.support.paths import EXPERIMENT_CONFIGS, ROOT, SNAPSHOT_CONFIGS
from tests.support.snapshot_builder import SnapshotBuilder
from trialfolio.configuration import read_experiment_configuration_v1_1, read_run_configuration
from trialfolio.contracts.experiment_configuration import (
    ExperimentConfiguration,
    ExperimentConfigurationV1_1,
    RankingVariant,
    configured_variants,
    configured_variants_v1_1,
)
from trialfolio.errors import TrialFolioError

INVALID = EXPERIMENT_CONFIGS / "invalid"


# Experiment configuration 1.1.0, from 0.4.0: a baseline ranked by a definition or a snapshot,
# and ranking variants.


def ranking_example() -> str:
    """docs/contracts.md's ranking example: the experiment on `ranking/value-momentum.xml`."""
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("#### Ranking example") :]
    return re.findall(r"```yaml\n(.*?)```", section, re.DOTALL)[0]


def read_v1_1(
    content: str | bytes, source_name: str = "experiment.yaml"
) -> ExperimentConfiguration | ExperimentConfigurationV1_1:
    """Reads with the reader of both versions, as if the file were in the fixtures' directory,
    from which the baseline's definition path is read."""
    if isinstance(content, str):
        content = content.encode()
    return read_experiment_configuration_v1_1(
        content, source_name, EXPERIMENT_CONFIGS / source_name
    ).configuration


def read_ranked(content: str) -> ExperimentConfigurationV1_1:
    configuration = read_v1_1(content)
    assert isinstance(configuration, ExperimentConfigurationV1_1)
    return configuration


def ranking_rejection(content: str) -> str:
    return rejection(content, reader=read_v1_1)


def ranking_line(old: str, new: str) -> str:
    return with_line(old, new, ranking_example())


VALUE_HEAVY = "      set: {'Value': 60, 'Momentum': 20, 'Quality': 20}"


def ranking_example_xml() -> str:
    """docs/contracts.md's ranking example's definition: the XML of `ranking/value-momentum.xml`."""
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("#### Ranking example") :]
    return re.findall(r"```xml\n(.*?)```", section, re.DOTALL)[0]


def snapshot_example() -> str:
    """docs/contracts.md's ranking snapshot configuration example."""
    contracts = (ROOT / "docs" / "contracts.md").read_text(encoding="utf-8")
    section = contracts[contracts.index("### Ranking snapshot configuration") :]
    return re.findall(r"```yaml\n(.*?)```", section, re.DOTALL)[0]


def ranking_problems(tmp_path: Path, content: str, definition: bytes) -> list[str]:
    """The problems of the experiment `content`, read with `definition` as the file its baseline
    names, `ranking/value-momentum.xml`, beside it."""
    path = tmp_path / "experiment.yaml"
    path.write_text(content, encoding="utf-8")
    (tmp_path / "ranking").mkdir(exist_ok=True)
    (tmp_path / "ranking" / "value-momentum.xml").write_bytes(definition)
    with pytest.raises(TrialFolioError) as caught:
        read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)
    assert caught.value.code == "config.invalid"
    return caught.value.message.split("\n")[1:]


ALTERED_DEFINITIONS = {
    "weight-zero": "a node's Weight is 0",
    "weight-percent": "a node's Weight isn't a decimal in plain notation",
    "xml-declaration": "it holds an XML declaration",
    "doctype": "it holds a document type declaration",
    "comment": "it holds a comment",
    "conditional-node": "an element where a node goes isn't a Composite",
    "root-not-ranking-system": "its root element isn't RankingSystem",
    "not-well-formed": "it isn't well-formed XML 1.0",
    "byte-order-mark": "the file starts with a byte-order mark",
    "empty-composite": "a Composite holds no node",
}
"""The alterations of the example's definition that its validation lists, each one of the
invalid definitions in `ranking/invalid/`, with the rule its message gives."""

VALUE_HEAVY_SET = "{'Value': 60, 'Momentum': 20, 'Quality': 20}"

ALTERED_VARIANTS = {
    "a-path-that-names-no-node": (
        "{'Value': 60, 'Momentum': 20, 'Qualty': 20}",
        "set[2]` is a node path whose segment 1 names none",
    ),
    "a-node-left-out": (
        "{'Value': 50, 'Momentum': 20}",
        "set` leaves out its parent's node at position 3.",
    ),
    "nodes-of-two-parents": (
        "{'Value': 60, 'Momentum/Year Return': 20, 'Quality': 20}",
        "set[1]` names a node of another",
    ),
    "one-node-named-twice": (
        "{'Value': 60, '#1': 60, 'Momentum': 20, 'Quality': 20}",
        "set[1]` names the same node as",
    ),
    "weights-of-another-sum": (
        "{'Value': 60, 'Momentum': 20, 'Quality': 30}",
        "set` gives weights that don't sum to",
    ),
    "weights-that-change-nothing": (
        "{'Value': 40, 'Momentum': 30, 'Quality': 30}",
        "set` gives every node the weight it has",
    ),
}
"""The alterations of the example's `value-heavy` variant that its validation lists, by an ID of
their own, each with the start of the problem its message gives, after `variants.ranking[0].`."""

SALES_YIELD_LINES = [
    (
        '\t\t<StockFormula Name="Sales Yield" Weight="50" RankType="Higher" Scope="Universe" '
        'Description="">'
    ),
    "\t\t\t<Formula>…</Formula>",
    "\t\t</StockFormula>",
]
"""The lines of the example's Sales Yield factor, which `no-sales-yield` removes: its definition's
lines 6 to 8, from 1."""


def with_weights(text: str, *changes: tuple[str, str, str]) -> str:
    """`text` with each change's node, by its name, given the new weight in place of the old, each
    written once."""
    for name, old, new in changes:
        written = f'Name="{name}" Weight="{old}"'
        assert text.count(written) == 1
        text = text.replace(written, f'Name="{name}" Weight="{new}"')
    return text


# The ranking example's validation, which R04-T02 left for R04-T04 (release 0.4.0's other checks in
# the default suite), repeated: each test is one of its checks.


def test_the_ranking_examples_are_the_fixtures_byte_for_byte() -> None:
    """The ranking example's XML and YAML are the fixtures, byte for byte, and so is the snapshot
    example."""
    xml = ranking_example_xml()
    assert (EXPERIMENT_CONFIGS / "ranking" / "value-momentum.xml").read_bytes() == xml.encode()
    assert (EXPERIMENT_CONFIGS / "ranking-example.yaml").read_bytes() == ranking_example().encode()
    snapshot = SNAPSHOT_CONFIGS / "example.yaml"
    assert snapshot.read_bytes() == snapshot_example().encode()


def test_documented_ranking_example_compiles_to_its_cases() -> None:
    """The experiment gives the four cases the example describes, each with the definition it
    describes. The plan these cases compile to is checked in `tests/core/test_ranking_plan.py`
    (release 0.4.0's R04-T07)."""
    xml = ranking_example_xml()
    path = EXPERIMENT_CONFIGS / "ranking-example.yaml"
    read = read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)

    assert read.definition is not None and read.definition.text == xml
    keys = [
        "baseline",
        *(variant.key for variant in configured_variants_v1_1(read_ranked(ranking_example()))),
    ]
    assert keys == ["baseline", "value-heavy", "tilt-earnings-yield", "no-sales-yield"]
    heavy, tilt, no_sales = (case.definition.text for case in read.ranking_cases)
    assert heavy == with_weights(
        xml, ("Value", "40", "60"), ("Momentum", "30", "20"), ("Quality", "30", "20")
    )
    assert tilt == with_weights(xml, ("Earnings Yield", "50", "70"), ("Sales Yield", "50", "30"))
    lines = xml.split("\n")
    assert lines[5:8] == SALES_YIELD_LINES
    removed = "\n".join(lines[:5] + lines[8:])
    assert no_sales == with_weights(removed, ("Earnings Yield", "50", "100"))
    assert len({xml, heavy, tilt, no_sales}) == 4


@pytest.mark.parametrize(
    ("name", "rule"), list(ALTERED_DEFINITIONS.items()), ids=list(ALTERED_DEFINITIONS)
)
def test_the_ranking_example_fails_with_each_altered_definition(
    tmp_path: Path, name: str, rule: str
) -> None:
    definition = (EXPERIMENT_CONFIGS / "ranking" / "invalid" / f"{name}.xml").read_bytes()

    (problem,) = ranking_problems(tmp_path, ranking_example(), definition)

    assert problem.startswith("- `baseline.ranking.definition` names a definition"), name
    assert rule in problem, name


@pytest.mark.parametrize(
    ("altered", "problem"), list(ALTERED_VARIANTS.values()), ids=list(ALTERED_VARIANTS)
)
def test_the_ranking_example_fails_with_each_altered_set(
    tmp_path: Path, altered: str, problem: str
) -> None:
    content = with_line(VALUE_HEAVY_SET, altered, ranking_example())

    found = ranking_problems(tmp_path, content, ranking_example_xml().encode())

    assert found == [found[0]] and found[0].startswith(f"- `variants.ranking[0].{problem}")


def test_a_path_to_two_nodes_and_the_removal_of_a_composite_or_its_only_factor_fail(
    tmp_path: Path,
) -> None:
    """The validation's other alterations, of `tilt-earnings-yield`'s and `no-sales-yield`'s
    paths, each with what its problems give, among the others its change makes."""
    xml = ranking_example_xml()
    content = ranking_example()
    # Two nodes that share a name, which the path names.
    shared = xml.replace('Name="Sales Yield"', 'Name="Earnings Yield"').encode()
    assert any(
        "`variants.ranking[1].set[0]` is a node path whose segment 2 names more than one" in found
        for found in ranking_problems(tmp_path, content, shared)
    )
    # The removal of a composite, and of a composite's only factor.
    composite = with_line("      remove: 'Value/Sales Yield'", "      remove: 'Value'", content)
    composite = with_line(
        "      set: {'Value/Earnings Yield': 100}",
        "      set: {'Momentum': 50, 'Quality': 50}",
        composite,
    )
    assert ranking_problems(tmp_path, composite, xml.encode())[0].startswith(
        "- `variants.ranking[2].remove` names a composite."
    )
    only = xml.encode().replace("\n".join(SALES_YIELD_LINES).encode() + b"\n", b"")
    only = only.replace(b'Name="Earnings Yield" Weight="50"', b'Name="Earnings Yield" Weight="100"')
    alone = with_line(
        "      remove: 'Value/Sales Yield'", "      remove: 'Value/Earnings Yield'", content
    )
    assert any(
        problem.startswith("- `variants.ranking[2].remove` names its parent's only node")
        for problem in ranking_problems(tmp_path, alone, only)
    )


def test_an_escaped_slash_names_the_same_node_in_single_and_double_quotes(tmp_path: Path) -> None:
    """A path with `\\/` in single quotes names the node a path with `\\\\/` in double quotes names,
    as YAML reads its own escapes first in double quotes."""
    slashed = ranking_example_xml().replace('Name="Sales Yield"', 'Name="P/E"').encode()
    single = with_line(
        "      set: {'Value/Earnings Yield': 70, 'Value/Sales Yield': 30}",
        "      set: {'Value/Earnings Yield': 70, 'Value/P\\/E': 30}",
        ranking_example(),
    )
    single = with_line("      remove: 'Value/Sales Yield'", "      remove: 'Value/P\\/E'", single)
    double = single.replace("'Value/P\\/E'", '"Value/P\\\\/E"')
    (tmp_path / "ranking").mkdir()
    (tmp_path / "ranking" / "value-momentum.xml").write_bytes(slashed)
    path = tmp_path / "experiment.yaml"
    cases = []
    for written in (single, double):
        path.write_text(written, encoding="utf-8")
        cases.append(
            [
                (case.definition.text, case.remove and case.remove.path)
                for case in read_experiment_configuration_v1_1(
                    path.read_bytes(), path.name, path
                ).ranking_cases
            ]
        )
    assert cases[0] == cases[1]
    assert cases[0][2][1] == "Value/P\\/E"


def test_the_ranking_example_reads_as_documented() -> None:
    """Its structure: the baseline ranked by a definition file, with its ranking method, three
    ranking variants, no default, and a budget of two requests a case. The definition, and the
    cases it gives, are read with it (release 0.4.0's R04-T06)."""
    configuration = read_v1_1(ranking_example())

    assert isinstance(configuration, ExperimentConfigurationV1_1)
    assert configuration.baseline.ranking.model_dump() == {
        "definition": "ranking/value-momentum.xml",
        "ranking_method": "percentile_nas_negative",
    }
    variants = configured_variants_v1_1(configuration)
    assert [(variant.key, variant.setting, variant.place) for variant in variants] == [
        ("value-heavy", "ranking", "variants.ranking[0]"),
        ("tilt-earnings-yield", "ranking", "variants.ranking[1]"),
        ("no-sales-yield", "ranking", "variants.ranking[2]"),
    ]
    changes = [variant.variant for variant in variants]
    assert all(isinstance(change, RankingVariant) for change in changes)
    assert [
        (change.set, change.remove) for change in changes if isinstance(change, RankingVariant)
    ] == [
        ({"Value": Decimal(60), "Momentum": Decimal(20), "Quality": Decimal(20)}, None),
        ({"Value/Earnings Yield": Decimal(70), "Value/Sales Yield": Decimal(30)}, None),
        ({"Value/Earnings Yield": Decimal(100)}, "Value/Sales Yield"),
    ]
    assert all(variant.screen is None for variant in variants)
    assert configuration.budget.provider_requests == 8


def test_a_baseline_may_name_a_snapshot_instead(tmp_path: Path) -> None:
    """The example's second form: the snapshot's directory, and no `ranking_method`, which the
    snapshot records. Release 0.4.0's R04-T10 reads the snapshot, so the test takes one, over the
    fake server, beside the configuration, where R04-T05's test named a directory that didn't
    exist, which no reader read then."""
    SnapshotBuilder(tmp_path / "home").snapshot(tmp_path / "ranking" / "value-momentum")
    content = ranking_line(
        "    definition: 'ranking/value-momentum.xml'\n    ranking_method: percentile_nas_negative",
        "    snapshot: 'ranking/value-momentum/'",
    )
    path = tmp_path / "experiment.yaml"

    configuration = read_experiment_configuration_v1_1(content.encode(), path.name, path)

    assert configuration.configuration.baseline.ranking.model_dump() == {
        "snapshot": "ranking/value-momentum/"
    }
    assert configuration.snapshot is not None


def test_a_weight_is_read_as_a_normalized_decimal() -> None:
    content = ranking_line(
        VALUE_HEAVY, "      set: {'Value': 60.0, 'Momentum': 20.000, 'Quality': 20}"
    )

    variant = configured_variants_v1_1(read_ranked(content))[0].variant

    assert isinstance(variant, RankingVariant)
    assert [str(weight) for weight in variant.set.values()] == ["60", "20", "20"]


def test_ranking_variants_come_after_rules_and_before_holdings() -> None:
    """The order of cases: the variants of rules, ranking, max_holdings, rebalance_weeks, and
    slippage_percent, the default in rebalance_weeks' place."""
    content = ranking_line(
        "  rebalance_weeks: []\n",
        "  slippage_percent:\n    - key: slippage-050\n      value: 0.5\n"
        "  max_holdings:\n    - key: holdings-50\n      value: 50\n"
        "  rules:\n    - key: no-microcaps\n      add: 'MktCap > 300'\n",
    )
    content = with_line("provider_requests: 8", "provider_requests: 16", content)

    variants = configured_variants_v1_1(read_ranked(content))

    assert [variant.key for variant in variants] == [
        "no-microcaps",
        "value-heavy",
        "tilt-earnings-yield",
        "no-sales-yield",
        "holdings-50",
        "rebalance-weeks-1",
        "slippage-050",
    ]
    assert [variant.default for variant in variants] == [False] * 5 + [True, False]
    # A variant of another setting keeps the baseline's definition: its case's ranking is the
    # baseline's.
    holdings = variants[4].screen
    assert holdings is not None and holdings.max_holdings == 50
    assert holdings.ranking == read_v1_1(content).baseline.ranking


def test_the_default_variant_counts_two_requests_with_a_definition() -> None:
    """Without `rebalance_weeks`, the default is a fifth case, so the budget needs 10."""
    content = ranking_line("  rebalance_weeks: []\n", "")

    assert "less than the 10 requests the experiment's 5 cases need" in ranking_rejection(content)
    assert read_v1_1(with_line("provider_requests: 8", "provider_requests: 10", content))


def test_a_budget_of_two_requests_a_case_is_accepted() -> None:
    assert read_v1_1(ranking_example()).budget.provider_requests == 8


def test_a_1_1_0_baseline_ranked_by_a_formula_needs_one_request_a_case() -> None:
    """Version 1.1.0 changes nothing for a baseline that isn't ranked by a definition."""
    content = example().replace("schema_version: 1.0.0", "schema_version: 1.1.0", 1)

    configuration = read_v1_1(content)

    assert isinstance(configuration, ExperimentConfigurationV1_1)
    assert [variant.key for variant in configured_variants_v1_1(configuration)] == [
        variant.key for variant in configured_variants(read(example()))
    ]
    assert read_v1_1(with_line("provider_requests: 6", "provider_requests: 5", content))
    budget = with_line("provider_requests: 6", "provider_requests: 4", content)
    assert ranking_rejection(budget).endswith(
        "`budget.provider_requests` is less than the experiment's 5 cases. It must be at least "
        "the number of cases, so that each can be sent once."
    )


def test_a_ranking_variant_s_key_is_unique_among_the_cases() -> None:
    content = ranking_line(
        "  rebalance_weeks: []\n",
        "  max_holdings:\n    - key: value-heavy\n      value: 50\n  rebalance_weeks: []\n",
    )
    content = with_line("provider_requests: 8", "provider_requests: 10", content)

    assert "`variants.max_holdings[0].key` repeats the key of `variants.ranking[0]`" in (
        ranking_rejection(content)
    )


def test_a_set_entry_is_named_by_its_place_never_by_its_path() -> None:
    """A node path holds node names, the user's strategy definition, so no message holds one,
    whatever rule the entry breaks (node paths)."""
    paths = ["Momentum/Secret Price", "Value #2", "Quality"]
    content = ranking_line(
        VALUE_HEAVY,
        f"      set: {{'{paths[0]}': 60, '{paths[1]}': '20', '{paths[2]}': 0, '{paths[1]}': 1}}",
    )

    message = ranking_rejection(content)

    assert "`variants.ranking[0].set[0]`" in message
    for path in paths:
        assert path not in message
    for path in ("Momentum", "Secret Price", "Value #2"):
        assert path not in message


def test_each_weight_problem_names_its_entry() -> None:
    content = ranking_line(VALUE_HEAVY, "      set: {'Value': '60', 'Momentum': 0, 'Quality': 20}")

    message = ranking_rejection(content)

    assert "`variants.ranking[0].set[0]` must be a number written without quotes" in message
    assert "`variants.ranking[0].set[1]` must be greater than 0" in message
    assert "Value" not in message and "Momentum" not in message


@pytest.mark.parametrize("weight", ["sixty", "60%"])
def test_a_weight_written_as_plain_text_is_reported_as_a_weight(weight: str) -> None:
    """A weight is never text, so a plain one is a weight written wrongly, not a node path
    written without quotes: the entry's key, `'Value'`, is quoted."""
    content = ranking_line(
        VALUE_HEAVY, f"      set: {{'Value': {weight}, 'Momentum': 20, 'Quality': 20}}"
    )

    message = ranking_rejection(content)

    assert message == (
        "experiment.yaml isn't a valid configuration:\n"
        "- `variants.ranking[0].set[0]` must be a number written without quotes, such as 0.25."
    )


def test_a_plain_path_with_a_plain_weight_is_reported_once_for_each() -> None:
    content = ranking_line(VALUE_HEAVY, "      set: {Value: sixty, 'Momentum': 20, 'Quality': 20}")

    message = ranking_rejection(content)

    assert message.count("`variants.ranking[0].set[0]` is a node path written without quotes") == 1
    assert (
        message.count("`variants.ranking[0].set[0]` must be a number written without quotes") == 1
    )


def test_an_empty_set_names_its_variant() -> None:
    message = ranking_rejection(ranking_line(VALUE_HEAVY, "      set: {}"))

    assert "`variants.ranking[0].set` must hold at least 1 item." in message


def test_a_set_s_paths_and_remove_may_be_in_double_quotes() -> None:
    content = ranking_line(VALUE_HEAVY, '      set: {"Value": 60, "Momentum": 20, "Quality": 20}')
    content = with_line(
        "      remove: 'Value/Sales Yield'", '      remove: "Value/Sales Yield"', content
    )

    variants = configured_variants_v1_1(read_ranked(content))

    assert [variant.key for variant in variants][-1] == "no-sales-yield"


def test_a_1_0_0_file_can_t_vary_the_ranking() -> None:
    path = INVALID / "variant-ranking.yaml"

    message = rejection(path.read_bytes(), path.name, read_v1_1)

    assert (
        "`variants.ranking` needs schema_version 1.1.0, with a baseline ranked by a definition "
        "or a snapshot. In 1.0.0, a variant may change rules, max_holdings, rebalance_weeks, or "
        "slippage_percent." in message
    )


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        (
            "variant-ranking.yaml",
            (
                "`variants.ranking` isn't a setting a variant may change. A variant may change "
                "rules, max_holdings, rebalance_weeks, or slippage_percent."
            ),
        ),
        (
            "baseline-definition-in-1.0.0.yaml",
            (
                "`baseline.ranking` must hold exactly one of formula, name, or id. The supported "
                "forms are {formula, lower_is_better}, {name}, and {id}."
            ),
        ),
    ],
    ids=["ranking-variant", "baseline-definition"],
)
def test_the_1_0_0_reader_gives_a_1_0_0_file_0_3_0_s_message(name: str, problem: str) -> None:
    """0.3.0's reader, which reads 1.0.0 only, keeps 0.3.0's message for such a file."""
    path = INVALID / name

    message = rejection(path.read_bytes(), path.name)

    assert message == f"{name} isn't a valid configuration:\n- {problem}"


def run_reader(directory: Path) -> Callable[[bytes, str], object]:
    """`trialfolio run`'s reader, as if the file were in `directory`."""
    return lambda content, name: read_run_configuration(content, name, directory / name)


@pytest.mark.parametrize(
    ("name", "later"),
    [
        ("variant-ranking.yaml", "`variants.ranking` needs schema_version 1.1.0"),
        ("baseline-definition-in-1.0.0.yaml", "a form that needs schema_version 1.1.0"),
    ],
    ids=["ranking-variant", "baseline-definition"],
)
def test_run_s_reader_tells_a_1_0_0_file_its_key_needs_1_1_0(name: str, later: str) -> None:
    """Since R04-T12, `trialfolio run` reads 1.1.0, with the reader of both versions, so it tells
    a 1.0.0 file that gives a key of 1.1.0 that the key needs that version, as the release's
    changes after sign-off give it (R04-T05's review)."""
    path = INVALID / name

    message = rejection(path.read_bytes(), path.name, run_reader(INVALID))

    assert later in message
    assert message == rejection(path.read_bytes(), path.name, read_v1_1)


RANKED_BY_SALES = (
    "  ranking:\n"
    "    - key: ranked-by-sales\n"
    "      value:\n"
    "        formula: 'SalesGr%TTM'\n"
    "        lower_is_better: false\n"
)

NOT_A_VARIANT_SETTING = (
    "`variants.ranking` isn't a setting a variant may change. A variant may change rules, "
    "max_holdings, rebalance_weeks, or slippage_percent."
)


@pytest.mark.parametrize(
    ("variant", "problem"),
    [
        ("      set:\n        Value: 100\n", NOT_A_VARIANT_SETTING),
        ("      remove: Value\n", NOT_A_VARIANT_SETTING),
        (
            "      set:\n        'Value': 1\n        'Value': 2\n",
            "`variants.ranking[0].set.Value` appears more than once.",
        ),
        (
            "      set:\n        'api_key': 1\n",
            (
                "`variants.ranking[0].set.api_key` looks like a credential. A configuration never "
                "holds credentials: the CLI reads them from TRIALFOLIO_P123_API_ID and "
                "TRIALFOLIO_P123_API_KEY."
            ),
        ),
    ],
    ids=["unquoted-path", "unquoted-remove", "path-twice", "credential-word"],
)
def test_the_1_0_0_reader_reads_a_1_0_0_ranking_variant_s_keys_as_0_3_0_did(
    variant: str, problem: str
) -> None:
    """0.3.0's reader has no node paths: it reads a ranking variant's keys as any other, as 0.3.0
    did, and asks for no quotes a 1.0.0 file can't use. Its message is the one 0.3.0 gave."""
    path = INVALID / "variant-ranking.yaml"
    content = path.read_text(encoding="utf-8")
    assert content.count(RANKED_BY_SALES) == 1
    content = content.replace(RANKED_BY_SALES, f"  ranking:\n    - key: weights\n{variant}")

    message = rejection(content, path.name)

    assert message == f"{path.name} isn't a valid configuration:\n- {problem}"


@pytest.mark.parametrize(
    "variant",
    [
        "      set:\n        Value: 100\n",
        "      set:\n        'Value': 1\n        'Value': 2\n",
        "      set:\n        'api_key': 1\n",
    ],
    ids=["unquoted-path", "path-twice", "credential-word"],
)
def test_run_s_reader_reads_a_1_0_0_ranking_variant_s_keys_as_node_paths(variant: str) -> None:
    """Since R04-T12, `trialfolio run` reads with the reader of both versions, which reads a
    ranking variant's keys as node paths in either version, and names a `set` entry by its
    place, never by its path."""
    path = INVALID / "variant-ranking.yaml"
    content = path.read_text(encoding="utf-8")
    content = content.replace(RANKED_BY_SALES, f"  ranking:\n    - key: weights\n{variant}")

    message = rejection(content, path.name, run_reader(INVALID))

    assert message == rejection(content, path.name, read_v1_1)
    assert "variants.ranking[0].set." not in message
    assert "api_key" not in message


def test_a_1_1_0_variant_of_another_setting_names_the_ranking_among_those_it_can() -> None:
    content = ranking_line(
        "  rebalance_weeks: []\n",
        "  universe:\n    - key: russell\n      value: 'Russell 1000'\n  rebalance_weeks: []\n",
    )

    assert (
        "`variants.universe` isn't a setting a variant may change. A variant may change rules, "
        "ranking, max_holdings, rebalance_weeks, or slippage_percent."
    ) in ranking_rejection(content)


def test_without_files_the_reader_reads_no_file_the_baselines_ranking_names() -> None:
    """The core reads the configuration of a plan without a ranking definition with `files`
    false: a baseline's definition named, without its bytes, is a `ValueError`, though the file
    exists, while a baseline ranked another way reads (R04-T12)."""
    assert read_v1_1(ranking_example()) is not None

    with pytest.raises(ValueError, match="names a file"):
        read_experiment_configuration_v1_1(
            ranking_example().encode(),
            "experiment.yaml",
            EXPERIMENT_CONFIGS / "experiment.yaml",
            files=False,
        )
    formula = with_line("schema_version: 1.0.0", "schema_version: 1.1.0")
    read = read_experiment_configuration_v1_1(
        formula.encode(), "experiment.yaml", "experiment.yaml", files=False
    )
    assert (read.definition, read.configuration.schema_version) == (None, "1.1.0")


def test_the_readers_name_the_versions_they_read() -> None:
    """0.3.0's reader reads 1.0.0 only, so a 1.1.0 file is a version it doesn't read; the reader
    of both versions, which `trialfolio run` reads with since R04-T12, names both."""
    assert "Supported versions: 1.0.0." in rejection(ranking_example())
    unsupported = with_line("schema_version: 1.0.0", "schema_version: 2.0.0")
    assert "Supported versions: 1.0.0, 1.1.0." in ranking_rejection(unsupported)
    assert "Supported versions: 1.0.0, 1.1.0." in rejection(
        unsupported, "experiment.yaml", run_reader(EXPERIMENT_CONFIGS)
    )


def test_the_reader_of_both_versions_reads_1_0_0_as_before() -> None:
    configuration = read_v1_1(example())

    assert type(configuration) is ExperimentConfiguration
    assert configuration == read(example())
