"""`trialfolio review` compares saved runs with a baseline offline, and writes exactly the review
docs/contracts.md's review output gives: its configuration, byte for byte, which claims the output
directory; each run's manifest, plan, and tables, byte for byte, under `inputs/<label>/`;
`differences.csv`; the report; and the manifest, last. It logs a result by its position, never
its label.

Traces to the interface parts of R02-AC01 (the files, the manifest, and stdout), R02-AC02 (the
copies, byte for byte, and nothing else), R02-AC05 (offline, in the test process and in a new
one), R02-AC13 (the JSON summary of a review that completes), R02-AC15 (a run without tables),
R02-AC16 (synthetic results in the manifest), R02-AC17 (results that share a response: the
warning and the manifest), and R02-AC18 (the manifest's counts equal the table's); and to
docs/contracts.md's labels in logs, which R02-T08 applies to the store. R02-T08 wrote these ahead
of R02-T10, which adds the other interface checks the test pairing names.

The run builder writes the runs each review configuration names, with `trialfolio run` over the
fake server, once for the module, and the review only reads them. Every expected value is
written here by hand, or read from the runs, never from the code under test.
"""

import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.interface.conftest import Cli, Outcome, snapshot
from tests.support import launcher
from tests.support.clock import STARTED
from tests.support.run_builder import REVIEW_CONFIGS
from trialfolio.contracts.manifest import RunManifest
from trialfolio.contracts.plan import Plan
from trialfolio.contracts.review_manifest import Method, ReviewManifest
from trialfolio.tables import read_differences_csv

type Built = Callable[[str], Path]

SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "review-manifest-1.0.0.schema.json"
TABLE_FILES = ["manifest.json", "normalized/metrics.csv", "normalized/settings.csv", "plan.json"]
"""A run's files a review copies, when the run has tables, sorted."""


def review(cli: Cli, path: Path, out: Path, *options: str) -> Outcome:
    """Reviews the configuration at `path` into `out`, with the license acknowledged."""
    cli.accept_license()
    return cli("review", path, "--out", out, *options)


def manifest_of(out: Path) -> ReviewManifest:
    return ReviewManifest.model_validate_json((out / "manifest.json").read_bytes())


def files_under(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def artifact_id(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def run_manifest(run: Path) -> RunManifest:
    return RunManifest.model_validate_json((run / "manifest.json").read_bytes())


def response_of(run: Path) -> str | None:
    """The `artifact_id` of the run's saved response, from its manifest."""
    responses = [
        artifact.artifact_id
        for artifact in run_manifest(run).artifacts
        if artifact.role in ("provider_response", "provider_response_undecoded")
    ]
    assert len(responses) <= 1
    return responses[0] if responses else None


# A two-run review (R02-AC01, R02-AC02, R02-AC05)


def test_a_two_run_review_writes_exactly_its_files_and_exits_0(cli: Cli, built: Built) -> None:
    path = built("example.yaml")
    out = cli.tmp / "review"

    outcome = review(cli, path, out)

    assert outcome.exit_code == 0, outcome.stderr
    assert files_under(out) == [
        "configuration.yaml",
        *(f"inputs/hold25/{name}" for name in TABLE_FILES),
        *(f"inputs/hold50/{name}" for name in TABLE_FILES),
        "logs/trialfolio.log",
        "manifest.json",
        "normalized/differences.csv",
        "report.html",
    ]
    configuration = (out / "configuration.yaml").read_bytes()
    assert configuration == (REVIEW_CONFIGS / "example.yaml").read_bytes()
    manifest = manifest_of(out)
    assert manifest.review_id.version == 4
    assert manifest.baseline == "hold25"
    assert manifest.created_at > STARTED
    assert manifest.command.name == "review"
    assert manifest.command.options == {"json": False}
    assert manifest.command.started_at == STARTED
    assert manifest.methods == (Method(name="screen-run-differences", version=1),)
    assert manifest.synthetic is False
    assert manifest.counts.results == 2
    # The manifest's own files: the configuration, its one source artifact, the table, and the
    # report, in the order they're written, after the copies.
    own = [artifact for artifact in manifest.artifacts if artifact.label is None]
    assert [(artifact.path, artifact.role) for artifact in own] == [
        ("configuration.yaml", "configuration"),
        ("normalized/differences.csv", "differences"),
        ("report.html", "report"),
    ]
    for artifact in own:
        assert artifact.artifact_id == artifact_id(out / artifact.path)
        assert artifact.size == (out / artifact.path).stat().st_size
    source = own[0].source
    assert source is not None
    assert (source.format, source.format_version) == ("review-configuration", "1.0.0")
    assert (source.provenance, source.acquired_at) == ("user_supplied", STARTED)
    assert [artifact.schema_version for artifact in own] == ["1.0.0", "1.0.0", None]
    lines = outcome.stdout.splitlines()
    assert lines[:2] == [f"Review completed: {out}", f"Report: {out / 'report.html'}"]
    assert f"Review ID: {manifest.review_id}" in lines
    assert lines[-1] == "Statistical validation and trading readiness: not assessed."


def test_the_manifest_has_only_the_schemas_keys_and_no_path(cli: Cli, built: Built) -> None:
    path = built("example.yaml")
    out = cli.tmp / "review"

    review(cli, path, out)

    text = (out / "manifest.json").read_text(encoding="utf-8")
    loaded = json.loads(text)
    schema = json.loads(SCHEMA.read_bytes())
    assert set(schema["required"]) <= set(loaded) <= set(schema["properties"])
    # A review sends nothing and parses no response, so it has no plan, approval, parsers, or
    # reproducibility: each copied run manifest records its own.
    for key in ("plan_hash", "approval", "parsers", "reproducibility"):
        assert key not in loaded
    # Neither the configuration's path nor --out, nor any run path: a path can name the user.
    for given in (str(path), str(path.parent), str(out), "runs/hold25", "runs/hold50"):
        assert given not in text


def test_each_result_names_its_run(cli: Cli, built: Built) -> None:
    path = built("example.yaml")
    out = cli.tmp / "review"

    review(cli, path, out)

    results = manifest_of(out).results
    assert [result.label for result in results] == ["hold25", "hold50"]
    for result in results:
        run = path.parent / "runs" / result.label
        plan = Plan.model_validate_json((run / "plan.json").read_bytes())
        assert result.run_manifest == artifact_id(run / "manifest.json")
        assert result.synthetic is False
        assert result.plan_hash == plan.plan_hash
        assert result.case_id == plan.cases[0].case_id
        assert result.normalized_tables is True
        assert result.response == response_of(run)
        assert result.response is not None


def test_each_copy_is_its_runs_file_byte_for_byte_and_nothing_else_is_copied(
    cli: Cli, built: Built
) -> None:
    path = built("example.yaml")
    runs = path.parent / "runs"
    before = snapshot(runs)
    out = cli.tmp / "review"

    review(cli, path, out)

    manifest = manifest_of(out)
    for label in ("hold25", "hold50"):
        run, copied = runs / label, out / "inputs" / label
        # Not its configuration, start or attempt record, request, response, or report.
        assert files_under(copied) == TABLE_FILES
        listed = {artifact.path: artifact for artifact in run_manifest(run).artifacts}
        entries = {
            artifact.path: artifact for artifact in manifest.artifacts if artifact.label == label
        }
        assert sorted(entries) == [f"inputs/{label}/{name}" for name in TABLE_FILES]
        for name in TABLE_FILES:
            assert (copied / name).read_bytes() == (run / name).read_bytes()
            entry = entries[f"inputs/{label}/{name}"]
            assert entry.artifact_id == artifact_id(run / name)
            assert entry.size == (run / name).stat().st_size
            if name == "manifest.json":
                assert entry.role == "run_manifest"
                assert entry.schema_version == run_manifest(run).schema_version
            else:
                # The copied manifest's entry matches the copy, so it can be checked alone.
                assert entry.schema_version == listed[name].schema_version
                assert listed[name].artifact_id == artifact_id(copied / name)
    assert snapshot(runs) == before


def test_the_review_runs_offline_in_a_new_process(cli: Cli, built: Built) -> None:
    path = built("example.yaml")
    out = cli.tmp / "review"
    cli.accept_license()
    endpoint = cli.server.endpoint
    cli.server.close()  # No server behind the endpoint: a review sends nothing.

    result = subprocess.run(
        launcher.command(endpoint, "review", path, "--out", out),
        capture_output=True,
        text=True,
        check=False,
        cwd=cli.tmp,
    )

    # The network guard, first on the new process's path, would end it with its own status.
    assert result.returncode == 0, result.stderr
    assert (out / "manifest.json").is_file()


def test_a_review_in_the_test_process_sends_nothing(cli: Cli, built: Built) -> None:
    out = cli.tmp / "review"

    outcome = review(cli, built("example.yaml"), out)

    assert outcome.exit_code == 0, outcome.stderr
    assert cli.server.received == ()


# The JSON summary (R02-AC13) and the manifest's counts (R02-AC18)


@pytest.mark.parametrize(
    ("name", "flagged", "unavailable"),
    [("example.yaml", 0, 0), ("undeclared.yaml", 3, 3), ("without-tables.yaml", 0, 60)],
)
def test_the_summary_and_the_manifest_count_the_table(
    cli: Cli, built: Built, name: str, flagged: int, unavailable: int
) -> None:
    # undeclared.yaml has three undeclared critical changes, and missing-metrics.json's three
    # missing metrics; without-tables.yaml's three results each have 20 unavailable metrics.
    out = cli.tmp / "review"

    outcome = review(cli, built(name), out, "--json")

    assert outcome.exit_code == 0, outcome.stderr
    summary = outcome.summary
    manifest = manifest_of(out)
    rows = read_differences_csv((out / "normalized" / "differences.csv").read_bytes(), name)
    settings = [row for row in rows if row.kind == "setting"]
    metrics = [row for row in rows if row.kind == "metric"]
    counted = Counter((row.kind, row.classification) for row in rows)
    counts = manifest.counts
    assert counts.results == len(manifest.results)
    assert counts.settings.same == counted["setting", "same"]
    assert counts.settings.intended_change == counted["setting", "intended_change"]
    assert counts.settings.unexplained_mismatch == counted["setting", "unexplained_mismatch"]
    assert counts.settings.unknown == counted["setting", "unknown"]
    assert counts.settings.flagged == sum(row.flagged for row in settings) == flagged
    assert counts.metrics.differenced == counted["metric", "differenced"]
    assert counts.metrics.not_comparable == counted["metric", "not_comparable"]
    assert counts.metrics.unavailable == counted["metric", "unavailable"] == unavailable
    assert counts.metrics.flagged == sum(row.flagged for row in metrics)
    assert summary["command"] == "review"
    assert summary["outcome"] == "completed"
    assert summary["ids"] == {"review_id": str(manifest.review_id)}
    assert summary["output_dir"] == str(out)
    assert summary["outputs"] == {
        "manifest": "manifest.json",
        "report": "report.html",
        "differences": "normalized/differences.csv",
    }
    assert summary["counts"] == {
        "results": len(manifest.results),
        "settings_flagged": flagged,
        "metrics_unavailable": unavailable,
        "warnings": 0,
    }
    assert summary["error"] is None


# Runs without tables (R02-AC15)


def test_a_run_without_tables_has_its_manifest_and_plan_copied(cli: Cli, built: Built) -> None:
    path = built("without-tables.yaml")
    out = cli.tmp / "review"

    outcome = review(cli, path, out)

    assert outcome.exit_code == 0, outcome.stderr
    results = {result.label: result for result in manifest_of(out).results}
    for label in ("rejected", "invalid-structure", "not-json"):
        assert files_under(out / "inputs" / label) == ["manifest.json", "plan.json"]
        assert results[label].normalized_tables is False
        assert results[label].response == response_of(path.parent / "runs" / label)
    # Portfolio123 rejected the request, so nothing was saved; the others saved a response that
    # failed validation, one of them undecoded.
    assert results["rejected"].response is None
    assert results["invalid-structure"].response is not None
    assert results["not-json"].response is not None


# Synthetic results (R02-AC16)


@pytest.mark.parametrize(
    ("name", "synthetic"),
    [
        ("synthetic.yaml", {"demo": True, "hold50": False}),
        ("synthetic-only.yaml", {"demo": True, "demo-again": True}),
    ],
)
def test_synthetic_results_are_marked_in_the_manifest(
    cli: Cli, built: Built, name: str, synthetic: dict[str, bool]
) -> None:
    out = cli.tmp / "review"

    outcome = review(cli, built(name), out)

    assert outcome.exit_code == 0, outcome.stderr
    manifest = manifest_of(out)
    assert manifest.synthetic is True
    assert {result.label: result.synthetic for result in manifest.results} == synthetic
    assert "It includes synthetic results, whose values are invented" in outcome.stdout


# Results that share a response (R02-AC17)


def test_results_that_share_a_response_are_warned_of_and_named_in_the_manifest(
    cli: Cli, built: Built
) -> None:
    path = built("shared-response.yaml")
    out = cli.tmp / "review"

    outcome = review(cli, path, out, "--json")

    assert outcome.exit_code == 0, outcome.stderr
    # By position: the baseline and the run of the same settings written differently, and the
    # two runs of holdings-50.yaml.
    warnings = [line for line in outcome.stderr.splitlines() if line.startswith("Warning: ")]
    assert len(warnings) == 2
    assert warnings[0].startswith("Warning: Results 1 and 2 have byte-identical saved responses")
    assert warnings[1].startswith("Warning: Results 3 and 4 have byte-identical saved responses")
    assert outcome.summary["counts"]["warnings"] == 2  # pyright: ignore[reportIndexIssue]
    results = {result.label: result for result in manifest_of(out).results}
    runs = path.parent / "runs"
    baseline, differently = results["baseline"], results["written-differently"]
    first, second = results["hold50-first"], results["hold50-second"]
    assert baseline.response == differently.response == response_of(runs / "baseline")
    assert first.response == second.response == response_of(runs / "hold50-first")
    assert results["slippage"].response not in (baseline.response, first.response)
    # Two runs of one configuration: one case, told apart by their labels.
    assert first.case_id == second.case_id
    assert first.run_manifest != second.run_manifest


# Labels in logs (docs/contracts.md, review output)


def test_the_log_names_each_result_by_its_position_never_its_label(
    cli: Cli, built: Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRIALFOLIO_LOG_LEVEL", "DEBUG")
    path = built("example.yaml")
    out = cli.tmp / "review"

    outcome = review(cli, path, out)

    assert outcome.exit_code == 0, outcome.stderr
    events = [
        json.loads(line)
        for line in (out / "logs" / "trialfolio.log").read_text(encoding="utf-8").splitlines()
    ]
    written = [event["message"] for event in events if event["event"] == "artifact.write.completed"]
    copies = [message.split(" (sha256:")[0] for message in written if " of result " in message]
    assert copies == [
        f"Wrote {name} of result {position}"
        for position in (1, 2)
        for name in (
            "manifest.json",
            "plan.json",
            "normalized/metrics.csv",
            "normalized/settings.csv",
        )
    ]
    log = (out / "logs" / "trialfolio.log").read_text(encoding="utf-8")
    for label in ("hold25", "hold50"):
        assert label not in log
    # The command's events from the claim on carry the review's ID, and the input check's, before
    # it, don't: it didn't exist yet. The store's events carry none, as for a run.
    review_id = str(manifest_of(out).review_id)
    linked = {event["event"]: event.get("review_id") for event in events}
    assert linked["review.input.loaded"] is None
    for name in ("cli.output.claimed", "report.render.completed", "cli.command.completed"):
        assert linked[name] == review_id


# The command's help (the owner's decision, 2026-10-07)


def test_the_help_says_trialfolio_compares_saved_runs(cli: Cli) -> None:
    outcome = cli("--help")

    assert outcome.exit_code == 0
    text = " ".join(outcome.stdout.split())
    assert "compare saved runs with a baseline" in text
    assert "review Compare saved runs with a baseline offline." in text


# The environment


def test_a_provider_package_that_cant_be_imported_is_an_unsupported_environment(
    cli: Cli, built: Built
) -> None:
    # A review reads runs with modules that import p123api, and checks no versions.
    cli.accept_license()
    out = cli.tmp / "review"

    outcome = cli.without_module("p123api", "review", built("example.yaml"), "--out", out, "--json")

    assert outcome.exit_code == 3, outcome.stderr
    error = outcome.summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == "environment.unsupported"
    assert "p123api can't be imported" in error["message"]
    assert not out.exists()
