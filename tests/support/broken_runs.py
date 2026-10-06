"""Broken runs: the ways a test breaks a copy of a complete run, such as the committed
`runs/synthetic-run-1.0.0/`, so that `trialfolio report` and `trialfolio review` must refuse it
(release 0.1.0's R01-AC23, and release 0.2.0's R02-AC06 and R02-AC14). It isn't a double: each
break changes real files of a real run.

- **`BROKEN`** holds R01-AC23's breaks, each with the problem a message gives for it.
- **`UNKNOWN_SCHEMA_VERSIONS`** holds R02-AC14's: a schema version without a reader, in a file or
  in the manifest's entry for one, each with the file a message names.

A break that edits a file the manifest lists, with `rewrite` or `edit_json`, updates its manifest
entry to match, so only the checks beyond the hashes can tell. R02-T10 moved these here from
`tests/core/test_review_inputs.py` and `tests/interface/test_report_command.py`, so the review's
interface checks could share them.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

from trialfolio.canonical import sha256_hex

type Json = dict[str, Any]


def write_manifest(run: Path, manifest: Json) -> None:
    (run / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())


def rewrite(run: Path, path: str, data: bytes) -> None:
    """Replaces a file of a saved run, and its manifest entry to match."""
    (run / path).write_bytes(data)
    manifest = json.loads((run / "manifest.json").read_bytes())
    for artifact in manifest["artifacts"]:
        if artifact["path"] == path:
            artifact.update(artifact_id="sha256:" + sha256_hex(data), size=len(data))
    write_manifest(run, manifest)


def edit_json(run: Path, path: str, change: Callable[[Json], None]) -> None:
    """Changes a JSON file of a saved run with `change`: the manifest itself, or a file it lists,
    whose entry is updated to match."""
    content = json.loads((run / path).read_bytes())
    change(content)
    data = (json.dumps(content, indent=2) + "\n").encode()
    if path == "manifest.json":
        (run / path).write_bytes(data)
    else:
        rewrite(run, path, data)


def path_of(run: Path, role: str) -> str:
    """The path of the one file of `role` that the run's manifest lists."""
    manifest = json.loads((run / "manifest.json").read_bytes())
    (path,) = (a["path"] for a in manifest["artifacts"] if a["role"] == role)
    return path


def remove(run: Path, path: str) -> None:
    (run / path).unlink()


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


BROKEN: Final[dict[str, tuple[Callable[[Path], None], str]]] = {
    "no manifest": (lambda run: remove(run, "manifest.json"), "it has no manifest.json."),
    "a listed file missing": (
        lambda run: remove(run, "normalized/settings.csv"),
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
"""R01-AC23's breaks of a complete run, each with the problem the message gives. The plan's new
title, "Another title", is a value no message may show."""


def newer(content: Json) -> None:
    content["schema_version"] = "1.1.0"


def newer_entry(role: str) -> Callable[[Json], None]:
    """Gives the manifest's entry for the file of `role` a newer schema version."""

    def change(manifest: Json) -> None:
        (entry,) = (a for a in cast("list[Json]", manifest["artifacts"]) if a["role"] == role)
        newer(entry)

    return change


def newer_schema(run: Path, target: str, change: Callable[[Json], None]) -> None:
    """Applies `change` to the run's manifest, when `target` is `manifest.json`, or to the file of
    the role `target`."""
    edit_json(run, target if target == "manifest.json" else path_of(run, target), change)


UNKNOWN_SCHEMA_VERSIONS: Final[dict[str, tuple[str, Callable[[Json], None], str]]] = {
    "manifest": ("manifest.json", newer, "manifest.json"),
    "plan": ("plan", newer, "plan.json"),
    "attempt record": ("attempt_record", newer, "attempt.json"),
    "a table's entry": ("manifest.json", newer_entry("metrics"), "normalized/metrics.csv"),
    "an attempt record's entry": ("manifest.json", newer_entry("attempt_record"), "attempt.json"),
}
"""R02-AC14's schema versions without a reader: the file to change, `manifest.json` or a role,
the change, and the file a message names."""
