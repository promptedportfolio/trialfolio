"""`trialfolio report` re-renders a saved run's report offline into a new output directory: every
value of the run's normalized tables appears in it, and its links reach the run's files by
relative path. Anything that isn't a complete run is refused with `input.not_a_run`, and a run
directory that doesn't exist with `input.not_found`, before anything is written.

Traces to R01-AC08 (re-rendering with network access blocked matches the saved normalized data)
and R01-AC23 (an incomplete or non-run directory fails with `input.not_a_run` and exit 3, and
creates no output), through the CLI's entry function in the test process. The runs are written
by `trialfolio run`, over the fake server, and by `trialfolio demo`, and one is a copy of the
committed `runs/synthetic-run-1.0.0/`; the runs that are broken one way are copies of it. The
network guard is on throughout, so a re-render that connected anywhere but localhost would fail.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest

from tests.interface.conftest import Cli, config, plan_hash_for, serve_success, snapshot
from tests.support.html_report import Document, parse
from trialfolio.canonical import sha256_hex
from trialfolio.contracts.manifest import RunManifest
from trialfolio.tables import read_metrics_csv, read_settings_csv

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "runs" / "synthetic-run-1.0.0"
"""The committed historical run, which `trialfolio demo` wrote with the 1.0.0 schemas."""


def committed_run(cli: Cli, out: Path) -> Path:
    """A copy of the committed `runs/synthetic-run-1.0.0/`."""
    cli.accept_license()
    shutil.copytree(FIXTURE, out)
    return out


def demo_run(cli: Cli, out: Path) -> Path:
    """A run as `trialfolio demo` writes it."""
    cli.accept_license()
    outcome = cli("demo", "--out", out)
    assert outcome.exit_code == 0, outcome.stderr
    return out


def fake_server_run(cli: Cli, out: Path) -> Path:
    """A run as `trialfolio run` writes it, over the fake server, approved with `--approve`."""
    cli.ready()
    serve_success(cli.server)
    path = config("formula.yaml")
    outcome = cli("run", path, "--out", out, "--approve", plan_hash_for(path))
    assert outcome.exit_code == 0, outcome.stderr
    return out


def report_document(out: Path) -> Document:
    return parse((out / "report.html").read_text(encoding="utf-8"))


def table_cells(document: Document) -> set[tuple[str, ...]]:
    """The text of each table row's cells, header rows included."""
    return {
        tuple(cell.text for cell in row)
        for table in document.root.find_all("table")
        for row in document.rows(table)
    }


# Re-rendering (R01-AC08)


@pytest.mark.parametrize(
    "write", [fake_server_run, demo_run, committed_run], ids=["run", "demo", "committed"]
)
def test_report_rerenders_every_value_of_the_saved_tables(
    cli: Cli, write: Callable[[Cli, Path], Path]
) -> None:
    run = write(cli, cli.tmp / "runs" / "baseline")
    before = len(cli.server.received)
    out = cli.tmp / "reports" / "baseline"

    outcome = cli("report", run, "--out", out)

    assert outcome.exit_code == 0, outcome.stderr
    assert len(cli.server.received) == before
    cells = table_cells(report_document(out))
    metrics = read_metrics_csv((run / "normalized/metrics.csv").read_bytes(), "metrics.csv")
    settings = read_settings_csv((run / "normalized/settings.csv").read_bytes(), "settings.csv")
    for metric in metrics:
        assert metric.value is not None
        assert any(metric.value in row and metric.unit in row for row in cells), metric.metric_id
    for setting in settings:
        assert any(
            row[:4] == (setting.setting, setting.category, setting.value, setting.unit or "")
            for row in cells
        ), setting.setting


def test_report_writes_only_the_report_and_its_logs_and_leaves_the_run_unchanged(
    cli: Cli,
) -> None:
    run = demo_run(cli, cli.tmp / "runs" / "baseline")
    before = snapshot(run)
    out = cli.tmp / "reports" / "baseline"

    outcome = cli("report", run, "--out", out, "--json")

    assert outcome.exit_code == 0
    assert snapshot(run) == before
    assert sorted(path.name for path in out.iterdir()) == ["logs", "report.html"]
    summary = outcome.summary
    assert summary["command"] == "report"
    assert summary["outcome"] == "completed"
    assert summary["output_dir"] == str(out)
    assert summary["outputs"] == {"report": "report.html"}
    assert summary["counts"] == {}
    assert summary["error"] is None


def test_rerendered_links_reach_the_runs_files_from_the_reports_directory(cli: Cli) -> None:
    run = demo_run(cli, cli.tmp / "runs" / "a #1 %20 & ü")
    manifest = RunManifest.model_validate_json((run / "manifest.json").read_bytes())
    out = cli.tmp / "reports" / "baseline"

    assert cli("report", run, "--out", out).exit_code == 0

    hrefs = [a.attrs["href"] or "" for a in report_document(out).root.find_all("a")]
    relative = [h for h in hrefs if not h.startswith("#") and not urlsplit(h).scheme]
    # The manifest's files, apart from the run's own report, and the manifest itself.
    assert len(relative) == len(manifest.artifacts)
    for href in relative:
        assert href.startswith("../../runs/a%20%231%20%2520%20%26%20%C3%BC/")
        assert (out / unquote(href)).resolve().is_file()


# What isn't a complete run (R01-AC23)


def rewrite(run: Path, path: str, data: bytes) -> None:
    """Replaces a file of a saved run, and its manifest entry to match, so only the checks
    beyond the hashes can tell."""
    (run / path).write_bytes(data)
    manifest = json.loads((run / "manifest.json").read_bytes())
    for artifact in manifest["artifacts"]:
        if artifact["path"] == path:
            artifact.update(artifact_id="sha256:" + sha256_hex(data), size=len(data))
    (run / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())


def edit_plan(run: Path, change: Callable[[dict[str, Any]], None]) -> None:
    plan = json.loads((run / "plan.json").read_bytes())
    change(plan)
    rewrite(run, "plan.json", (json.dumps(plan, indent=2) + "\n").encode())


def change_bytes(run: Path, path: str) -> None:
    """Changes a file without updating its manifest entry."""
    content = (run / path).read_bytes()
    changed = content.replace(b"SPY", b"QQQ")
    assert changed != content
    (run / path).write_bytes(changed)


BROKEN: dict[str, Callable[[Path], None]] = {
    "no manifest": lambda run: (run / "manifest.json").unlink(),
    "a listed file missing": lambda run: (run / "normalized/settings.csv").unlink(),
    "bytes that don't match": lambda run: change_bytes(run, "configuration.yaml"),
    # Its artifact_id in the manifest is updated to match, so only the plan-hash check catches it.
    "a plan that doesn't recompute to its hash": lambda run: edit_plan(
        run, lambda plan: plan.update(title="Another title")
    ),
}


@pytest.mark.parametrize("break_run", BROKEN.values(), ids=BROKEN.keys())
def test_an_incomplete_run_fails_and_creates_no_output(
    cli: Cli, break_run: Callable[[Path], None]
) -> None:
    run = committed_run(cli, cli.tmp / "run")
    break_run(run)
    out = cli.tmp / "report"

    outcome = cli("report", run, "--out", out, "--json")

    assert outcome.exit_code == 3
    assert outcome.summary["error"]["code"] == "input.not_a_run"  # pyright: ignore[reportIndexIssue]
    assert outcome.summary["output_dir"] is None
    assert outcome.summary["outputs"] == {}
    assert "Another title" not in outcome.stdout + outcome.stderr
    assert not out.exists()


def test_an_empty_directory_and_a_regular_file_arent_runs(cli: Cli) -> None:
    cli.accept_license()
    empty = cli.tmp / "empty"
    empty.mkdir()
    regular = cli.tmp / "file"
    regular.write_text("not a run")
    out = cli.tmp / "report"

    for given in (empty, regular):
        outcome = cli("report", given, "--out", out, "--json")
        assert outcome.exit_code == 3
        assert outcome.summary["error"]["code"] == "input.not_a_run"  # pyright: ignore[reportIndexIssue]
        assert not out.exists()


def test_a_run_directory_that_doesnt_exist_is_not_found(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "report"

    outcome = cli("report", cli.tmp / "missing", "--out", out, "--json")

    assert outcome.exit_code == 3
    assert outcome.summary["error"]["code"] == "input.not_found"  # pyright: ignore[reportIndexIssue]
    assert not out.exists()


def test_a_provider_package_that_cant_be_imported_is_an_unsupported_environment(
    cli: Cli,
) -> None:
    # `report` reads runs with modules that import p123api, and checks no versions.
    cli.accept_license()
    given = cli.tmp / "not-a-run"
    given.mkdir()
    (given / "notes.txt").write_text("not a run\n")
    out = cli.tmp / "report"

    outcome = cli.without_module("p123api", "report", given, "--out", out, "--json")

    assert outcome.exit_code == 3, outcome.stderr
    error = outcome.summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == "environment.unsupported"
    assert "p123api can't be imported" in error["message"]
    assert "If you run it from a copy of its repository, run uv sync there" in error["message"]
    assert not out.exists()


def test_a_broken_copy_leaves_a_non_empty_output_directory_unchanged(cli: Cli) -> None:
    copy = committed_run(cli, cli.tmp / "copy")
    BROKEN["no manifest"](copy)
    out = cli.tmp / "report"
    out.mkdir()
    (out / "keep.txt").write_text("someone else's file")
    before = snapshot(out)

    outcome = cli("report", copy, "--out", out, "--json")

    # The run is read before the output directory is checked.
    assert outcome.summary["error"]["code"] == "input.not_a_run"  # pyright: ignore[reportIndexIssue]
    assert snapshot(out) == before
