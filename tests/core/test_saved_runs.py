"""`trialfolio report`'s core reads a saved run back, checks it's complete, and re-renders its
report offline into a new output directory: every value of the run's tables appears in it, its
artifact links reach the run's files from the report's directory, and anything that isn't a
complete run is refused before anything is written.

Traces, at the core, to R01-AC08 (re-rendering offline matches the saved normalized data) and
R01-AC23 (an incomplete or non-run directory is `input.not_a_run`, and creates no output); and to
docs/contracts.md, plan hashing (a saved plan recomputes to its hash), artifact compatibility (an
unknown schema version is `artifact.unknown_schema_version`), and CLI behavior (validation first;
an output directory that isn't empty is refused). The network guard blocks any connection a
re-render would make. R01-T16 checks the same through the CLI.
"""

import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path, PurePath
from typing import Any, cast
from urllib.parse import unquote, urlsplit

import pytest

from tests.core.conftest import CONFIGS, RESPONSES, WriteRun, Written, manifest_json, snapshot
from tests.support.fake_portfolio123 import Reply
from tests.support.html_report import parse
from trialfolio.canonical import sha256_hex
from trialfolio.contracts.manifest import RunManifest
from trialfolio.errors import TrialFolioError
from trialfolio.report import HtmlReportRenderer, rerender_report
from trialfolio.runs import read_run
from trialfolio.storage import LocalArtifactStore
from trialfolio.tables import read_metrics_csv, read_settings_csv

FORMULA = (CONFIGS / "formula.yaml").read_bytes()
RANKING_NAME = (CONFIGS / "ranking-name.yaml").read_bytes()
COMPLETE = Reply(200, (RESPONSES / "complete.json").read_bytes())
RENDERER = HtmlReportRenderer("0.1.0")


@pytest.fixture
def complete(write_run: WriteRun) -> Written:
    return write_run(FORMULA, COMPLETE)


def relative(run: Path, out: Path) -> str:
    return PurePath(os.path.relpath(run, out)).as_posix()


def rerender(run: Path, out: Path, run_path: str | None = "") -> str:
    """Re-renders the run at `run` into `out`, as `trialfolio report` does, and returns the
    report."""
    if run_path == "":
        run_path = relative(run, out)
    rerender_report(LocalArtifactStore(run), LocalArtifactStore(out), RENDERER, run_path=run_path)
    return (out / "report.html").read_text(encoding="utf-8")


def rewrite(out: Path, path: str, data: bytes) -> None:
    """Replaces a file of a saved run, and its manifest entry to match, so only the checks
    beyond the hashes can tell."""
    (out / path).write_bytes(data)
    manifest = RunManifest.model_validate_json((out / "manifest.json").read_bytes())
    artifacts = tuple(
        artifact.model_copy(update={"artifact_id": "sha256:" + sha256_hex(data), "size": len(data)})
        if artifact.path == path
        else artifact
        for artifact in manifest.artifacts
    )
    (out / "manifest.json").write_bytes(
        manifest_json(manifest.model_copy(update={"artifacts": artifacts}))
    )


def edit_json(out: Path, path: str, change: Callable[[dict[str, Any]], None]) -> None:
    content = json.loads((out / path).read_bytes())
    change(content)
    data = (json.dumps(content, indent=2) + "\n").encode()
    if path == "manifest.json":
        (out / path).write_bytes(data)
    else:
        rewrite(out, path, data)


def refused(run: Path, out: Path) -> TrialFolioError:
    with pytest.raises(TrialFolioError) as caught:
        rerender(run, out)
    assert not out.exists()
    return caught.value


# Re-rendering (R01-AC08)


def test_report_rerenders_every_value_of_the_saved_tables(
    complete: Written, tmp_path: Path
) -> None:
    document = parse(rerender(complete.out, tmp_path / "reports" / "baseline"))
    cells = {
        tuple(cell.text for cell in row)
        for table in document.root.find_all("table")
        for row in document.rows(table)
    }
    metrics = read_metrics_csv((complete.out / "normalized/metrics.csv").read_bytes(), "m")
    settings = read_settings_csv((complete.out / "normalized/settings.csv").read_bytes(), "s")

    for metric in metrics:
        assert metric.value is not None
        assert any(metric.value in row and metric.unit in row for row in cells), metric.metric_id
    for setting in settings:
        assert any(
            row[:4] == (setting.setting, setting.category, setting.value, setting.unit or "")
            for row in cells
        ), setting.setting


def test_rerendering_reproduces_the_runs_own_report(complete: Written) -> None:
    saved = read_run(LocalArtifactStore(complete.out))

    assert RENDERER.render(saved, "") == complete.html
    assert [attempt.status.outcome for attempt in saved.attempts] == ["succeeded"]
    assert saved.attempts[0].start is not None
    assert saved.metrics == complete.saved.metrics
    assert saved.settings == complete.saved.settings


def test_rerendered_links_reach_the_runs_files_from_the_reports_directory(
    complete: Written, tmp_path: Path
) -> None:
    run = tmp_path / "runs" / "a #1 %20 & ü"
    shutil.copytree(complete.out, run)
    out = tmp_path / "reports" / "baseline"
    document = parse(rerender(run, out))
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    relative_hrefs = [h for h in hrefs if not h.startswith("#") and not urlsplit(h).scheme]

    assert len(relative_hrefs) == len(complete.manifest.artifacts)
    for href in relative_hrefs:
        assert href.startswith("../../runs/a%20%231%20%2520%20%26%20%C3%BC/")
        assert (out / unquote(href)).resolve().is_file()
    assert (out / "report.html").read_bytes() != (run / "report.html").read_bytes()


def test_without_a_relative_path_the_artifacts_are_named_without_links(
    complete: Written, tmp_path: Path
) -> None:
    document = parse(rerender(complete.out, tmp_path / "report", run_path=None))
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    named = {code.text for code in document.root.by_id("conclusion").find_all("code")}

    assert [h for h in hrefs if not h.startswith("#") and not urlsplit(h).scheme] == []
    assert {"manifest.json", "plan.json", "normalized/metrics.csv"} <= named


def test_a_run_that_didnt_complete_is_read_without_tables(
    write_run: WriteRun, tmp_path: Path
) -> None:
    written = write_run(FORMULA, Reply(400, b"Unsupported value"))
    saved = read_run(LocalArtifactStore(written.out))

    assert (saved.metrics, saved.settings) == (None, None)
    assert [attempt.status.outcome for attempt in saved.attempts] == ["failed"]
    assert saved.manifest.error is not None
    assert RENDERER.render(saved, "") == written.html
    assert "The normalized result is unavailable" in rerender(written.out, tmp_path / "report")


# What isn't a complete run (R01-AC23)


def remove(run: Path, path: str) -> None:
    (run / path).unlink()


def change_bytes(run: Path, path: str) -> None:
    """Changes a file without updating its manifest entry."""
    (run / path).write_bytes((run / path).read_bytes().replace(b"SPY", b"QQQ"))


BROKEN: dict[str, Callable[[Path], None]] = {
    "no manifest": lambda run: remove(run, "manifest.json"),
    "a listed file missing": lambda run: remove(run, "normalized/settings.csv"),
    "bytes that don't match": lambda run: change_bytes(run, "configuration.yaml"),
    # Its artifact_id in the manifest is updated to match, so only the plan-hash check catches it.
    "a plan that doesn't recompute to its hash": lambda run: edit_json(
        run, "plan.json", lambda plan: plan.update(title="Another title")
    ),
    # A valid plan, whose budget canonical JSON can't write exactly, so it has no hash.
    "a plan that can't be hashed": lambda run: edit_json(
        run,
        "plan.json",
        lambda plan: plan["budget"].update(credits=2**53, credits_per_request=2**53),
    ),
}


@pytest.mark.parametrize("break_run", BROKEN.values(), ids=BROKEN.keys())
def test_an_incomplete_run_is_refused_and_nothing_is_written(
    complete: Written, tmp_path: Path, break_run: Callable[[Path], None]
) -> None:
    break_run(complete.out)

    error = refused(complete.out, tmp_path / "report")

    assert error.code == "input.not_a_run"
    assert "Another title" not in error.message


def test_the_messages_name_the_problem(complete: Written, tmp_path: Path) -> None:
    run = complete.out
    messages: list[str] = []
    for name in (
        "no manifest",
        "a listed file missing",
        "a plan that doesn't recompute to its hash",
        "a plan that can't be hashed",
    ):
        copy = tmp_path / name
        shutil.copytree(run, copy)
        BROKEN[name](copy)
        messages.append(refused(copy, tmp_path / f"report-{name}").message)

    assert "it has no manifest.json." in messages[0]
    assert "lists `normalized/settings.csv`, which is missing." in messages[1]
    assert "its plan.json doesn't recompute to its plan_hash" in messages[2]
    assert "its plan.json can't be hashed (" in messages[3]
    assert str(2**53) not in messages[3]


def test_an_empty_directory_and_a_regular_file_arent_runs(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    regular = tmp_path / "file"
    regular.write_text("not a run")

    for given in (empty, regular):
        error = refused(given, tmp_path / "report")
        assert error.code == "input.not_a_run"
    assert "it isn't a directory." in refused(regular, tmp_path / "report").message


type Json = dict[str, object]


def newer(content: Json) -> None:
    content["schema_version"] = "1.1.0"


def newer_entry(role: str) -> Callable[[Json], None]:
    """Gives the manifest's entry for the file of `role` a newer schema version."""

    def change(manifest: Json) -> None:
        artifacts = cast("list[Json]", manifest["artifacts"])
        (entry,) = (artifact for artifact in artifacts if artifact["role"] == role)
        newer(entry)

    return change


@pytest.mark.parametrize(
    ("target", "change"),
    [
        ("manifest.json", newer),
        ("plan", newer),
        ("attempt_record", newer),
        ("manifest.json", newer_entry("metrics")),
        ("manifest.json", newer_entry("attempt_record")),
    ],
    ids=["manifest", "plan", "attempt record", "a table's entry", "an attempt record's entry"],
)
def test_a_schema_version_without_a_reader_is_unknown(
    complete: Written, tmp_path: Path, target: str, change: Callable[[Json], None]
) -> None:
    if target != "manifest.json":
        (target,) = (a.path for a in complete.manifest.artifacts if a.role == target)
    edit_json(complete.out, target, change)

    error = refused(complete.out, tmp_path / "report")

    assert error.code == "artifact.unknown_schema_version"
    assert "1.1.0" not in error.message


def test_a_manifest_that_isnt_a_valid_run_manifest_is_refused(
    complete: Written, tmp_path: Path
) -> None:
    for change, expected in (
        (lambda m: m.update(artifact_type="review"), "isn't a run's manifest"),
        (lambda m: m.update(outcome="<b>great</b>"), "check `outcome`"),
        (lambda m: m.update(note="<b>extra</b>"), "check its fields"),
        (lambda m: m.pop("schema_version"), "has no schema version"),
    ):
        run = tmp_path / f"run-{len(expected)}"
        shutil.copytree(complete.out, run)
        edit_json(run, "manifest.json", change)

        error = refused(run, tmp_path / "report")

        assert error.code == "input.not_a_run"
        assert expected in error.message
        assert "<b>" not in error.message
    (complete.out / "manifest.json").write_bytes(b"[1, 2")
    assert "`manifest.json` isn't JSON." in refused(complete.out, tmp_path / "report").message


def test_files_from_another_run_are_refused_even_with_matching_hashes(
    write_run: WriteRun, tmp_path: Path
) -> None:
    run = write_run(FORMULA, COMPLETE)
    other = write_run(RANKING_NAME, COMPLETE)
    cases = (
        ("normalized/metrics.csv", "another case than the plan's"),
        ("normalized/settings.csv", "another case than the plan's"),
        ("plan.json", "its manifest names another plan than its plan.json"),
    )
    for path, expected in cases:
        copy = tmp_path / path.replace("/", "-")
        shutil.copytree(run.out, copy)
        rewrite(copy, path, (other.out / path).read_bytes())

        error = refused(copy, tmp_path / "report")

        assert error.code == "input.not_a_run"
        assert expected in error.message


def test_an_attempt_record_must_be_its_directorys_and_reference_listed_files(
    complete: Written, tmp_path: Path
) -> None:
    record = next(a.path for a in complete.manifest.artifacts if a.role == "attempt_record")
    edits = (
        (
            lambda r: r.update(attempt_id="00000000-0000-4000-8000-000000000000"),
            "names another attempt than its directory",
        ),
        (
            lambda r: r["request"].update(artifact_id="sha256:" + "0" * 64),
            "which its manifest doesn't list as that file",
        ),
    )
    for change, expected in edits:
        copy = tmp_path / f"run-{len(expected)}"
        shutil.copytree(complete.out, copy)
        edit_json(copy, record, change)

        error = refused(copy, tmp_path / "report")

        assert error.code == "input.not_a_run"
        assert expected in error.message


# The output directory


def test_an_output_directory_that_isnt_empty_is_refused_unchanged(
    complete: Written, tmp_path: Path
) -> None:
    out = tmp_path / "report"
    out.mkdir()
    (out / ".hidden").write_text("someone else's")
    before = snapshot(out)

    with pytest.raises(TrialFolioError) as caught:
        rerender(complete.out, out)

    assert caught.value.code == "output.not_empty"
    assert snapshot(out) == before


def test_the_run_is_read_before_the_output_directory_is_checked(tmp_path: Path) -> None:
    out = tmp_path / "report"
    out.mkdir()
    (out / "file").write_text("occupied")

    with pytest.raises(TrialFolioError) as caught:
        rerender(tmp_path / "missing", out)

    assert caught.value.code == "input.not_a_run"


def test_the_run_is_left_unchanged(complete: Written, tmp_path: Path) -> None:
    before = snapshot(complete.out)

    rerender(complete.out, tmp_path / "report")

    assert snapshot(complete.out) == before
    assert sorted(p.name for p in (tmp_path / "report").iterdir()) == ["report.html"]
