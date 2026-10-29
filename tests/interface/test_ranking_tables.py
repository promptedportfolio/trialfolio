"""`trialfolio run` of a screen or an experiment whose ranking is a definition writes
`settings.csv` 1.1.0, as each manifest records it: 1.0.0's columns, then `node`, and a weight row
for each node of the case's definition right after `ranking`, by its canonical path, with its
normalized weight. A weight row's `original_key`, `original_value`, and `source_artifact` are the
definition's, or, for a weight the case's ranking variant sets, its `set` entry's. A run or a
case without a definition writes `settings.csv` 1.0.0, as in 0.3.0.

Traces to R04-AC04's tables part, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_tables.py`, and to docs/contracts.md, weight rows and `settings.csv`:
`original_key`, `original_value`, and `source_artifact` are `baseline.ranking.definition`, the
`Weight` attribute's text, and the `artifact_id` of `plans/1/definition.xml`; or, for a weight the
variant sets, the `set` entry's place, its YAML text, such as `60.0` from
`ranking-written-differently.yaml`, and the `artifact_id` of `plans/1/configuration.yaml`; a screen
run's take `ranking.definition` and the `artifact_id` of its own `definition.xml`. The review part
of R04-AC04 is `tests/interface/test_review_weights.py`'s, and the core's,
`tests/core/test_ranking_execution.py`'s.

Each run and experiment is written with `trialfolio run`, through the CLI's entry function in the
test process, over the fake server, with the fixed clock and the ranking lock in the test's own
directory. Every expected value is written here by hand: the weights from the definition's file,
and the originals from the configuration's text. Only the `artifact_id`s are computed, from the
files' bytes.
"""

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Final

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    RANK_UPDATED,
    ExperimentBuilder,
    experiment_config,
    returns_each,
)
from tests.support.fake_portfolio123 import AUTHENTICATED, response, serve_success
from tests.support.paths import SCREEN_CONFIGS
from trialfolio.contracts.experiment_manifest import ExperimentManifest, ExperimentManifestV1_1
from trialfolio.contracts.manifest import RunManifest, RunManifestV1_1

EXAMPLE: Final = experiment_config("ranking-example.yaml")
WRITTEN_DIFFERENTLY: Final = experiment_config("ranking-written-differently.yaml")

COLUMNS_1_0_0: Final = (
    "label",
    "setting",
    "category",
    "critical",
    "value",
    "unit",
    "interpretation",
    "provenance",
    "inference_rule",
    "original_key",
    "original_value",
    "source_artifact",
    "flags",
)
"""`settings.csv` 1.0.0's columns, in docs/contracts.md's order."""

COLUMNS_1_1_0: Final = (*COLUMNS_1_0_0, "node")
"""`settings.csv` 1.1.0's: 1.0.0's, then `node`."""

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
"""`value-momentum.xml`'s nodes, by canonical path, in its order."""

BASELINE: Final[dict[str, str]] = dict(
    zip(NODES, ("40", "50", "50", "30", "50", "50", "30", "50", "50"), strict=True)
)
"""`value-momentum.xml`'s weight of each node, as its `Weight` attributes write them."""

WEIGHTS: Final[dict[str, dict[str, str]]] = {
    "baseline": BASELINE,
    "value-heavy": BASELINE | {"Value": "60", "Momentum": "20", "Quality": "20"},
    "tilt-earnings-yield": BASELINE | {"Value/Earnings Yield": "70", "Value/Sales Yield": "30"},
    "no-sales-yield": {
        node: weight
        for node, weight in (BASELINE | {"Value/Earnings Yield": "100"}).items()
        if node != "Value/Sales Yield"
    },
}
"""Each of `ranking-example.yaml`'s cases' weight rows, in order: the baseline's definition, or
the baseline's with exactly its variant's change. `no-sales-yield` has 8, without
`Value/Sales Yield`."""

type Rows = list[dict[str, str]]
type Builder = ExperimentBuilder[Outcome]


def artifact_id(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def table(path: Path) -> tuple[list[str], Rows]:
    """A `settings.csv`'s header, and its rows, each by the header's names."""
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"), newline=""))
    rows = list(reader)
    assert reader.fieldnames is not None
    return list(reader.fieldnames), rows


def written(cli: Cli, experiments: Builder, config: Path = EXAMPLE) -> Path:
    """Writes the experiment of `config`, four cases, each answered with `rank-update.json`'s 200
    to its `POST /rank` and `complete.json`'s to its backtest, and returns its directory."""
    cli.ready()
    out = cli.tmp / "experiment"
    outcome = experiments.run(config, out, ranks=[RANK_UPDATED] * 4, sends=returns_each(4))
    assert outcome.exit_code == 0, outcome.stderr
    return out


def case_ids(out: Path) -> dict[str, str]:
    """Each planned case's `case_id`, by its key, as the first plan's `experiment.json` gives
    them."""
    manifest = ExperimentManifestV1_1.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    record = (out / f"plans/{manifest.plan}/experiment.json").read_text(encoding="utf-8")
    planned = json.loads(record)["planned_cases"]
    return {case["case_key"]: case["case_id"] for case in planned}


def weight_rows(rows: Rows) -> Rows:
    return [row for row in rows if row["setting"] == "ranking_weight"]


# Each case's weight rows


def test_each_cases_settings_csv_is_1_1_0_with_a_weight_row_for_each_node_after_ranking(
    cli: Cli, experiments: Builder
) -> None:
    out = written(cli, experiments)
    ids = case_ids(out)
    manifest = ExperimentManifestV1_1.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    versions = {a.path: a.schema_version for a in manifest.artifacts if a.role == "settings"}

    assert list(ids) == list(WEIGHTS)
    for key, weights in WEIGHTS.items():
        path = out / "cases" / ids[key] / "normalized" / "settings.csv"
        header, rows = table(path)

        assert versions[path.relative_to(out).as_posix()] == "1.1.0"
        assert header == list(COLUMNS_1_1_0)
        settings = [row["setting"] for row in rows]
        ranking = settings.index("ranking")
        after = rows[ranking + 1 : ranking + 1 + len(weights)]
        # The weight rows come right after `ranking`, one for each node of the case's definition,
        # in its order, by canonical path, and then `max_holdings`, as in 0.3.0.
        assert [(row["setting"], row["node"], row["value"]) for row in after] == [
            ("ranking_weight", node, weight) for node, weight in weights.items()
        ]
        assert settings[ranking + 1 + len(weights)] == "max_holdings"
        assert len(weight_rows(rows)) == len(weights)
        for row in after:
            assert (row["label"], row["category"], row["critical"], row["unit"]) == (
                ids[key],
                "strategy",
                "true",
                "",
            )
            assert (row["interpretation"], row["provenance"], row["inference_rule"]) == (
                "interpreted",
                "verified",
                "",
            )
            assert row["flags"] == ""
        # `node` is empty on every row but the weight rows.
        assert {row["node"] for row in rows if row["setting"] != "ranking_weight"} == {""}


def test_a_weights_original_is_its_definitions_unless_its_variant_sets_it(
    cli: Cli, experiments: Builder
) -> None:
    """`ranking-written-differently.yaml` writes `value-heavy`'s `set` as
    `{"Momentum": 20, "#1": 60.0, "Quality": 20}`, so `Value`'s weight, `60`, comes from its
    second entry, as it's written, `60.0`; `tilt-earnings-yield`'s as
    `{"#1/Sales Yield": 30, "Value/#1": 70}`; and `no-sales-yield`'s as
    `{"Value/Earnings Yield": 100}`."""
    out = written(cli, experiments, WRITTEN_DIFFERENTLY)
    ids = case_ids(out)
    definition = artifact_id(out / "plans/1/definition.xml")
    configuration = artifact_id(out / "plans/1/configuration.yaml")
    from_variant = {
        ("value-heavy", "Momentum"): ("variants.ranking[0].set[0]", "20", "20"),
        ("value-heavy", "Value"): ("variants.ranking[0].set[1]", "60", "60.0"),
        ("value-heavy", "Quality"): ("variants.ranking[0].set[2]", "20", "20"),
        ("tilt-earnings-yield", "Value/Sales Yield"): ("variants.ranking[1].set[0]", "30", "30"),
        ("tilt-earnings-yield", "Value/Earnings Yield"): (
            "variants.ranking[1].set[1]",
            "70",
            "70",
        ),
        ("no-sales-yield", "Value/Earnings Yield"): ("variants.ranking[2].set[0]", "100", "100"),
    }

    for key, weights in WEIGHTS.items():
        _, rows = table(out / "cases" / ids[key] / "normalized" / "settings.csv")
        for row in weight_rows(rows):
            node = row["node"]
            found = (row["original_key"], row["value"], row["original_value"])
            if (key, node) in from_variant:
                assert found == from_variant[key, node], (key, node)
                assert row["source_artifact"] == configuration, (key, node)
            else:
                # Every other weight is the baseline's definition's: its `Weight` attribute's
                # text, from the plan's copy of the file.
                assert found == ("baseline.ranking.definition", weights[node], BASELINE[node])
                assert row["source_artifact"] == definition, (key, node)
        (ranking,) = [row for row in rows if row["setting"] == "ranking"]
        # A ranking variant's case takes its `ranking` row from its variant, which changes its
        # definition's hash; the baseline's from its `ranking`.
        index = list(WEIGHTS).index(key) - 1
        expected = "baseline.ranking" if index < 0 else f"variants.ranking[{index}]"
        assert ranking["original_key"] == expected
        assert ranking["source_artifact"] == configuration


def test_a_screen_runs_weight_rows_come_from_its_own_definition_xml(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", RANK_UPDATED, method="POST")
    cli.server.reply("/screen/backtest", response("complete.json"))
    config = SCREEN_CONFIGS / "definition.yaml"
    out = cli.tmp / "run"

    outcome = cli.run_approved(config, out)

    assert outcome.exit_code == 0, outcome.stderr
    manifest = RunManifestV1_1.model_validate_json((out / "manifest.json").read_bytes())
    (entry,) = [a for a in manifest.artifacts if a.role == "settings"]
    assert (entry.path, entry.schema_version) == ("normalized/settings.csv", "1.1.0")
    header, rows = table(out / "normalized" / "settings.csv")
    assert header == list(COLUMNS_1_1_0)
    definition = artifact_id(out / "definition.xml")
    assert [
        (row["node"], row["value"], row["original_key"], row["original_value"])
        for row in weight_rows(rows)
    ] == [(node, weight, "ranking.definition", weight) for node, weight in BASELINE.items()]
    assert {row["source_artifact"] for row in weight_rows(rows)} == {definition}


# Without a definition


def test_a_run_without_a_definition_writes_settings_csv_1_0_0(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    config = SCREEN_CONFIGS / "formula.yaml"
    out = cli.tmp / "run"

    outcome = cli.run_approved(config, out)

    assert outcome.exit_code == 0, outcome.stderr
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    (entry,) = [a for a in manifest.artifacts if a.role == "settings"]
    assert entry.schema_version == "1.0.0"
    header, rows = table(out / "normalized" / "settings.csv")
    assert header == list(COLUMNS_1_0_0)
    assert not weight_rows(rows)


def test_a_screen_configuration_1_1_0_ranked_by_a_formula_writes_settings_csv_1_0_0(
    cli: Cli,
) -> None:
    """A configuration 1.1.0 whose ranking is a formula gives plan 1.0.0, so its run writes
    `settings.csv` 1.0.0, without `node` (docs/contracts.md, plans with a ranking definition)."""
    cli.ready()
    serve_success(cli.server)
    config = cli.tmp / "formula-1.1.0.yaml"
    text = (SCREEN_CONFIGS / "formula.yaml").read_text(encoding="utf-8")
    config.write_text(text.replace("schema_version: 1.0.0", "schema_version: 1.1.0"))
    out = cli.tmp / "run"

    outcome = cli.run_approved(config, out)

    assert outcome.exit_code == 0, outcome.stderr
    header, rows = table(out / "normalized" / "settings.csv")
    assert header == list(COLUMNS_1_0_0)
    assert not weight_rows(rows)


def test_a_case_without_a_definition_writes_settings_csv_1_0_0(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    outcome = experiments.run(experiment_config("example.yaml"), out, sends=returns_each(5))
    assert outcome.exit_code == 0, outcome.stderr
    manifest = ExperimentManifest.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )

    paths = sorted(out.glob("cases/*/normalized/settings.csv"))

    assert len(paths) == 5
    assert {a.schema_version for a in manifest.artifacts if a.role == "settings"} == {"1.0.0"}
    for path in paths:
        header, rows = table(path)
        assert header == list(COLUMNS_1_0_0)
        assert not weight_rows(rows)
