"""`trialfolio review` refuses what it can't review before it writes anything: a configuration
that isn't valid, a run that isn't complete, a `run` directory that doesn't exist, a schema version
it has no reader for, and an output directory that isn't empty. Its message names the result,
and the output directory, if there is one, doesn't change.

Traces to R02-AC06 (an input that isn't a complete run is `input.not_a_run`, exit 3, and creates
no output directory, as is a `run` directory that doesn't exist, with `input.not_found`),
R02-AC10 (an output directory that isn't empty is `output.not_empty`, exit 4, and nothing in it
changes), the interface part of R02-AC11 (four invalid configurations through the CLI: exit 3,
and no output directory), and R02-AC14 (a schema version without a reader is
`artifact.unknown_schema_version`, exit 3, naming the result). Through the CLI's entry function in
the test process. tests/core/test_review_inputs.py checks the same breaks at the core, and
tests/contract/test_review_configuration.py every invalid configuration.

The runs that fail are copies of the committed `runs/synthetic-run-1.0.0/`, each broken one way,
as R01-AC23's are; the run builder writes the others, over the fake server, once for the module.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from tests.interface.conftest import Cli, Outcome, metadata, occupied, snapshot
from tests.support.run_builder import REVIEW_CONFIGS, SYNTHETIC_RUN
from trialfolio.canonical import sha256_hex

type Built = Callable[[str], Path]
type Json = dict[str, Any]

CONFIGURATION = """\
kind: review
schema_version: 1.0.0
title: Two copies of the demo's run
baseline: first
results:
  - label: first
    run: runs/first
  - label: second
    run: runs/second
"""
"""A review of two copies of the committed run, `first`, the baseline, and `second`."""

RESULTS = pytest.mark.parametrize("label", ["first", "second"], ids=["baseline", "another-result"])


def two_runs(cli: Cli) -> Path:
    """Writes the review configuration, and a copy of the committed run at each `run` path, and
    gives the configuration's path."""
    cli.accept_license()
    directory = cli.tmp / "review-config"
    for label in ("first", "second"):
        shutil.copytree(SYNTHETIC_RUN, directory / "runs" / label)
    path = directory / "review.yaml"
    path.write_text(CONFIGURATION, encoding="utf-8")
    return path


def review(cli: Cli, path: Path, out: Path) -> Outcome:
    return cli("review", path, "--out", out, "--json")


def failed(outcome: Outcome, code: str, exit_code: int) -> str:
    """The error's message, once the outcome is checked: nothing was claimed, so the summary
    names no output directory and no review."""
    assert outcome.exit_code == exit_code, outcome.stderr
    summary = outcome.summary
    error = summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == code
    assert summary["output_dir"] is None
    assert summary["outputs"] == {}
    assert summary["ids"] == {}
    message = error["message"]
    assert isinstance(message, str)
    assert f"Error ({code}): {message}" in outcome.stderr
    return message


def write_manifest(run: Path, manifest: Json) -> None:
    (run / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())


def rewrite(run: Path, path: str, data: bytes) -> None:
    """Replaces a file of a saved run, and its manifest entry to match, so only the checks beyond
    the hashes can tell."""
    (run / path).write_bytes(data)
    manifest = json.loads((run / "manifest.json").read_bytes())
    for artifact in manifest["artifacts"]:
        if artifact["path"] == path:
            artifact.update(artifact_id="sha256:" + sha256_hex(data), size=len(data))
    write_manifest(run, manifest)


def edit_json(run: Path, path: str, change: Callable[[Json], None]) -> None:
    content = json.loads((run / path).read_bytes())
    change(content)
    data = (json.dumps(content, indent=2) + "\n").encode()
    if path == "manifest.json":
        (run / path).write_bytes(data)
    else:
        rewrite(run, path, data)


def path_of(run: Path, role: str) -> str:
    manifest = json.loads((run / "manifest.json").read_bytes())
    (path,) = (a["path"] for a in manifest["artifacts"] if a["role"] == role)
    return path


def change_bytes(run: Path, path: str) -> None:
    """Changes a file without updating its manifest entry."""
    content = (run / path).read_bytes()
    changed = content.replace(b"SPY", b"QQQ")
    assert changed != content
    (run / path).write_bytes(changed)


def empty(run: Path) -> None:
    shutil.rmtree(run)
    run.mkdir()


def regular_file(run: Path) -> None:
    shutil.rmtree(run)
    run.write_text("not a run")


# What isn't a complete run (R02-AC06)

BROKEN: dict[str, tuple[Callable[[Path], None], str]] = {
    "no manifest": (lambda run: (run / "manifest.json").unlink(), "it has no manifest.json."),
    "a listed file missing": (
        lambda run: (run / "normalized/settings.csv").unlink(),
        "its manifest lists `normalized/settings.csv`, which is missing.",
    ),
    "bytes that don't match": (
        lambda run: change_bytes(run, "configuration.yaml"),
        "`configuration.yaml` doesn't match its artifact_id in the manifest",
    ),
    # Its artifact_id in the manifest is updated to match, so only the plan-hash check catches it.
    "a plan that doesn't recompute to its hash": (
        lambda run: edit_json(run, "plan.json", lambda plan: plan.update(title="Another title")),
        "its plan.json doesn't recompute to its plan_hash",
    ),
    "an empty directory": (empty, "it has no manifest.json."),
    "a regular file": (regular_file, "it isn't a directory."),
}
"""R01-AC23's breaks, each with the problem the message gives."""


@RESULTS
@pytest.mark.parametrize(("break_run", "problem"), BROKEN.values(), ids=BROKEN.keys())
def test_an_incomplete_run_fails_naming_its_result_and_creates_no_output(
    cli: Cli, label: str, break_run: Callable[[Path], None], problem: str
) -> None:
    path = two_runs(cli)
    break_run(path.parent / "runs" / label)
    before = snapshot(path.parent)
    out = cli.tmp / "review"

    outcome = review(cli, path, out)

    message = failed(outcome, "input.not_a_run", 3)
    assert message.startswith(
        f"Result `{label}`'s run directory (`runs/{label}`) isn't a complete Trial Folio run:"
        f" {problem}"
    )
    assert "Another title" not in outcome.stdout + outcome.stderr
    assert not out.exists()
    assert snapshot(path.parent) == before


def test_a_run_directory_that_doesnt_exist_is_not_found(cli: Cli) -> None:
    path = two_runs(cli)
    shutil.rmtree(path.parent / "runs" / "second")
    out = cli.tmp / "review"

    outcome = review(cli, path, out)

    message = failed(outcome, "input.not_found", 3)
    assert message.startswith("Result `second`'s run directory (`runs/second`) doesn't exist.")
    assert not out.exists()


@pytest.mark.parametrize("name", ["results.txt", ".hidden"], ids=["a-file", "a-hidden-file"])
def test_a_broken_input_is_reported_before_an_output_directory_that_isnt_empty(
    cli: Cli, name: str
) -> None:
    path = two_runs(cli)
    (path.parent / "runs" / "second" / "manifest.json").unlink()
    out = occupied(cli, name)
    before = metadata(out)

    outcome = review(cli, path, out)

    # The runs are read before the output directory is checked.
    failed(outcome, "input.not_a_run", 3)
    assert metadata(out) == before


# An output directory that isn't empty (R02-AC10)


@pytest.mark.parametrize("name", ["results.txt", ".hidden"], ids=["a-file", "a-hidden-file"])
def test_an_output_directory_that_isnt_empty_is_refused_and_unchanged(
    cli: Cli, built: Built, name: str
) -> None:
    cli.accept_license()
    path = built("example.yaml")
    out = occupied(cli, name)
    before = metadata(out)
    runs_before = metadata(path.parent)

    outcome = review(cli, path, out)

    failed(outcome, "output.not_empty", 4)
    assert metadata(out) == before
    assert metadata(path.parent) == runs_before


# A configuration that isn't valid (R02-AC11)


@pytest.mark.parametrize(
    "name",
    [
        "misspelled-key.yaml",
        "duplicate-key.yaml",
        "intended-change-on-baseline.yaml",
        "unknown-setting.yaml",
    ],
)
def test_an_invalid_configuration_fails_and_creates_no_output(cli: Cli, name: str) -> None:
    cli.accept_license()
    path = REVIEW_CONFIGS / "invalid" / name
    content = path.read_text(encoding="utf-8")
    (key,) = (line.removeprefix("# Key: ") for line in content.splitlines() if "# Key: " in line)
    out = cli.tmp / "review"

    outcome = review(cli, path, out)

    message = failed(outcome, "config.invalid", 3)
    assert message.startswith(f"{path} isn't a valid configuration:")
    # tests/contract/test_review_configuration.py checks that it never holds the value.
    assert f"`{key}`" in message
    assert not out.exists()
    assert snapshot(cli.tmp) == {"home": None}


# A schema version without a reader (R02-AC14)


def newer(content: Json) -> None:
    content["schema_version"] = "1.1.0"


def newer_entry(role: str) -> Callable[[Json], None]:
    """Gives the manifest's entry for the file of `role` a newer schema version."""

    def change(manifest: Json) -> None:
        (entry,) = (a for a in cast("list[Json]", manifest["artifacts"]) if a["role"] == role)
        newer(entry)

    return change


@RESULTS
@pytest.mark.parametrize(
    ("target", "change", "named"),
    [
        ("manifest.json", newer, "manifest.json"),
        ("plan", newer, "plan.json"),
        ("attempt_record", newer, "attempt.json"),
        ("manifest.json", newer_entry("metrics"), "normalized/metrics.csv"),
        ("manifest.json", newer_entry("attempt_record"), "attempt.json"),
    ],
    ids=["manifest", "plan", "attempt record", "a table's entry", "an attempt record's entry"],
)
def test_a_schema_version_without_a_reader_fails_naming_its_result(
    cli: Cli, label: str, target: str, change: Callable[[Json], None], named: str
) -> None:
    path = two_runs(cli)
    run = path.parent / "runs" / label
    edit_json(run, target if target == "manifest.json" else path_of(run, target), change)
    out = cli.tmp / "review"

    outcome = review(cli, path, out)

    message = failed(outcome, "artifact.unknown_schema_version", 3)
    assert f"{named}` in result `{label}`'s run directory (`runs/{label}`): " in message
    assert not out.exists()
