"""`trialfolio review` of runs whose ranking is a definition compares each node's weight: a result
that declares `ranking` declares each weight that differs, and one that doesn't gets a flagged
unexplained mismatch; a node a run doesn't have is `absent`, or unknown when its ranking is a
system named by name; and the review writes `differences.csv` 1.1.0, with `node`, and records
`screen-run-differences` version 2, while a review without weight rows writes 1.0.0 and version
1, as 0.3.0 does (docs/contracts.md, differences between screen runs, weight rows; review
output).

Traces to R04-AC04's review part, through the CLI: `ranking-weights.yaml`, `ranking-undeclared
.yaml`, and `ranking-other-forms.yaml`, whose runs the run builder writes, with `trialfolio run`
since release 0.4.0's R04-T12 built `run` for a definition, and through the core until then.
R04-T11 wrote these ahead of R04-T13, which the test
pairing gives `tests/interface/test_review_weights.py`, since they check R04-T11's review. A
synthetic run the core writes with the demo's client is named as such in the review's report,
not as the demo's (DSC-04). Every expected value is written here by hand.
"""

import csv
import io
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.interface.conftest import Cli, Outcome
from tests.support.clock import FixedClock
from tests.support.html_report import parse
from tests.support.run_builder import SYNTHETIC_RUN
from trialfolio.configuration import read_screen_configuration_v1_1
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.contracts.review_manifest import Method, ReviewManifest
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.execution import Execution
from trialfolio.planning import build_plan_v1_1, installed_versions
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_differences_csv, read_differences_csv_v1_1

type Built = Callable[[str], Path]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

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
HEAVY = ("60", "50", "50", "20", "50", "50", "20", "50", "50")
"""`value-momentum.xml`'s and `value-heavy.xml`'s weights, node by node."""


def review(cli: Cli, path: Path, out: Path) -> Outcome:
    cli.accept_license()
    outcome = cli("review", path, "--out", out)
    assert outcome.exit_code == 0, outcome.stderr
    return outcome


def records(out: Path) -> list[dict[str, str]]:
    content = (out / "normalized/differences.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(content)))


def weights(out: Path, label: str) -> list[dict[str, str]]:
    return [r for r in records(out) if r["label"] == label and r["name"] == "ranking_weight"]


def test_a_declared_ranking_declares_each_weight_that_differs(cli: Cli, built: Built) -> None:
    out = cli.tmp / "review"

    review(cli, built("ranking-weights.yaml"), out)

    rows = weights(out, "value-heavy")
    assert [(r["node"], r["baseline_value"], r["value"]) for r in rows] == list(
        zip(NODES, WEIGHTS, HEAVY, strict=True)
    )
    reason = "More weight on value, taken equally from momentum and quality."
    for row in rows:
        if row["baseline_value"] != row["value"]:
            assert (row["classification"], row["declared_reason"]) == ("intended_change", reason)
        else:
            assert (row["classification"], row["declared_reason"]) == ("same", "")
        assert (row["flagged"], row["flags"]) == ("false", "")
    content = (out / "normalized/differences.csv").read_bytes()
    assert content.splitlines()[0].endswith(b",flagged,flags,node")
    assert len(read_differences_csv_v1_1(content, "differences.csv")) == 32 + 20
    manifest = ReviewManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.methods == (Method(name="screen-run-differences", version=2),)
    (table,) = (a for a in manifest.artifacts if a.role == "differences")
    assert table.schema_version == "1.1.0"
    # Each run's copies are the versions it records: its plan 1.2.0, its manifest 1.1.0, and its
    # settings.csv 1.1.0.
    copies = {(a.label, a.role): a.schema_version for a in manifest.artifacts if a.label}
    for label in ("definition", "value-heavy"):
        assert copies[label, "plan"] == "1.2.0"
        assert copies[label, "run_manifest"] == "1.1.0"
        assert copies[label, "settings"] == "1.1.0"
        assert copies[label, "metrics"] == "1.0.0"
    assert manifest.counts.settings.intended_change == 4


def test_an_undeclared_weight_that_differs_is_a_flagged_critical_mismatch(
    cli: Cli, built: Built
) -> None:
    out = cli.tmp / "review"

    review(cli, built("ranking-undeclared.yaml"), out)

    for row in weights(out, "value-heavy"):
        if row["baseline_value"] != row["value"]:
            assert (row["classification"], row["flagged"], row["flags"]) == (
                "unexplained_mismatch",
                "true",
                "critical_unexplained_mismatch",
            )
        else:
            assert (row["classification"], row["flagged"]) == ("same", "false")


def test_a_formulas_node_is_absent_and_a_named_systems_weight_unknown(
    cli: Cli, built: Built
) -> None:
    out = cli.tmp / "review"

    review(cli, built("ranking-other-forms.yaml"), out)

    formula = weights(out, "formula")
    named = weights(out, "ranking-name")
    assert [(r["node"], r["baseline_value"], r["value"]) for r in formula] == [
        (node, weight, "absent") for node, weight in zip(NODES, WEIGHTS, strict=True)
    ]
    assert {r["classification"] for r in formula} == {"intended_change"}
    assert [(r["node"], r["baseline_value"], r["value"]) for r in named] == [
        (node, weight, "") for node, weight in zip(NODES, WEIGHTS, strict=True)
    ]
    assert {(r["classification"], r["flags"]) for r in named} == {("unknown", "critical_unknown")}


def test_a_review_without_weight_rows_writes_1_0_0_and_version_1(cli: Cli, built: Built) -> None:
    out = cli.tmp / "review"

    review(cli, built("example.yaml"), out)

    content = (out / "normalized/differences.csv").read_bytes()
    assert content.splitlines()[0].endswith(b",flagged,flags")
    assert read_differences_csv(content, "differences.csv")
    manifest = ReviewManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert manifest.methods == (Method(name="screen-run-differences", version=1),)
    (table,) = (a for a in manifest.artifacts if a.role == "differences")
    assert table.schema_version == "1.0.0"


# A synthetic run the core wrote (DSC-04)


def synthetic_run(tmp_path: Path, out: Path) -> Path:
    """Writes `definition.yaml`'s run through the core with the demo's client: a synthetic run
    with a definition, which no command writes."""
    path = FIXTURES / "screen-configs" / "definition.yaml"
    content = path.read_bytes()
    read = read_screen_configuration_v1_1(content, path.name, path)
    plan = build_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_2) and read.definition is not None
    with LocalArtifactStore(out) as store:
        error = Execution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            None,
            clock=FixedClock(),
            ranking_lock=tmp_path / LOCK_FILE,
        ).run(
            content,
            lambda: SyntheticScreenBacktestClient(response_bytes()),
            definition=read.definition.content,
        )
    assert error is None
    return out


def synthetic_review(directory: Path, results: dict[str, str]) -> Path:
    """Writes a review configuration into `directory`, with a result for each label, naming the
    run at its `run` path; the first is the baseline."""
    lines = ["kind: review", "schema_version: 1.0.0", "title: Synthetic runs"]
    lines.append(f"baseline: {next(iter(results))}")
    lines.append("results:")
    for label, run in results.items():
        lines += [f"  - label: {label}", f"    run: {run}"]
    path = directory / "review.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("demo", "writer"),
    [
        (False, "Trial Folio's core, with the demo's client,"),
        (True, "trialfolio demo, or Trial Folio's core with the demo's client,"),
    ],
)
def test_a_synthetic_run_the_core_wrote_is_named_so(cli: Cli, demo: bool, writer: str) -> None:
    runs = cli.tmp / "runs"
    synthetic_run(cli.tmp, runs / "core")
    results = {"core": "runs/core"}
    if demo:
        shutil.copytree(SYNTHETIC_RUN, runs / "demo")
        results = {"demo": "runs/demo", **results}
    else:
        synthetic_run(cli.tmp, runs / "core-again")
        results["core-again"] = "runs/core-again"
    out = cli.tmp / "review"

    review(cli, synthetic_review(cli.tmp, results), out)

    document = parse((out / "report.html").read_text(encoding="utf-8"))
    (banner,) = (p for p in document.root.find_all("p") if p.attrs.get("class") == "synthetic")
    assert f"synthetic: written by {writer} from invented values." in banner.text
    sources = [
        [cell.text for cell in row][:2] for row in document.rows(document.table_after("Sources"))
    ]
    source = (
        "Invented values, written by Trial Folio's core, with the demo's client, in the layout of"
        " Portfolio123's screen backtest response. Nothing was sent to Portfolio123."
    )
    assert ["core (synthetic)", source] in sources
