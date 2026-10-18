"""Broken runs and experiments: the ways a test breaks a copy of a complete run, such as the
committed `runs/synthetic-run-1.0.0/`, so that `trialfolio report` and `trialfolio review` must
refuse it (release 0.1.0's R01-AC23, and release 0.2.0's R02-AC06 and R02-AC14), and a copy of an
experiment, so that a resume must refuse it (release 0.3.0's R03-AC17). It isn't a double: each
break changes real files of a real run or experiment.

- **`BROKEN`** holds R01-AC23's breaks, each with the problem a message gives for it.
- **`UNKNOWN_SCHEMA_VERSIONS`** holds R02-AC14's: a schema version without a reader, in a file or
  in the manifest's entry for one, each with the file a message names.
- **`BROKEN_EXPERIMENTS`** holds R03-AC17's breaks of a copy of the committed
  `experiments/synthetic-experiment-1.0.0/`, each with the problem the records check's message
  gives for it, and **`UNKNOWN_EXPERIMENT_SCHEMA_VERSIONS`** each record whose schema version
  can have no reader. The breaks that need a token dropped, a request sent again, or a table no
  manifest lists break an experiment the experiment builder writes, with the same functions:
  `edit_record`, `edit_attempt`, `copy_attempt`, and `another_parser`.

A break that edits a file the manifest lists, with `rewrite` or `edit_json`, updates its manifest
entry to match, so only the checks beyond the hashes can tell. An experiment's break, with
`rewrite_record` or `edit_record`, does the same for the latest manifest, and for the
`artifact_id` that each plan's `experiment.json` records for a plan's files, as release 0.3.0's
broken experiments require. R02-T10 moved the runs' breaks here from
`tests/core/test_review_inputs.py` and `tests/interface/test_report_command.py`, so the review's
interface checks could share them; R03-T11 added the experiments'.
"""

import json
import re
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

from trialfolio.canonical import sha256_hex
from trialfolio.tables import metrics_csv, read_metrics_csv

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
    # Not 1.1.0, which a review reads in a run manifest, from release 0.4.0's R04-T11.
    content["schema_version"] = "9.9.9"


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


# Broken experiments (release 0.3.0's R03-AC17)


def _json_bytes(content: Json) -> bytes:
    return (json.dumps(content, indent=2) + "\n").encode()


def _relative(out: Path, path: Path) -> str:
    return path.relative_to(out).as_posix()


def _numbered(out: Path, pattern: str) -> list[Path]:
    """The files that match `pattern`, such as `sessions/*/manifest.json`, in the order of their
    directories' numbers."""
    return sorted(out.glob(pattern), key=lambda path: int(path.parent.name))


_PLAN_FILE: Final = re.compile(r"plans/([1-9][0-9]*)/(plan\.json|configuration\.yaml)")


def rewrite_record(out: Path, path: str, data: bytes) -> None:
    """Replaces a file of the experiment in `out`, and each record of its `artifact_id` to match:
    the latest manifest's entry for it, when it lists it, and, for a plan's `plan.json` or
    `configuration.yaml`, the plan's entry in each `experiment.json` that holds one. The latest
    manifest itself has no entry."""
    (out / path).write_bytes(data)
    artifact_id = "sha256:" + sha256_hex(data)
    plan_file = _PLAN_FILE.fullmatch(path)
    if plan_file is not None:
        number = int(plan_file[1])
        field = "plan_artifact_id" if plan_file[2] == "plan.json" else "configuration_artifact_id"

        def recorded(record: Json) -> None:
            for entry in cast("list[Json]", record["plans"]):
                if entry["plan"] == number:
                    entry[field] = artifact_id

        for record in _numbered(out, "plans/*/experiment.json"):
            edit_record(out, _relative(out, record), recorded)
    manifests = _numbered(out, "sessions/*/manifest.json")
    if not manifests or _relative(out, manifests[-1]) == path:
        return
    manifest = json.loads(manifests[-1].read_bytes())
    for artifact in manifest["artifacts"]:
        if artifact["path"] == path:
            artifact.update(artifact_id=artifact_id, size=len(data))
    manifests[-1].write_bytes(_json_bytes(manifest))


def edit_record(out: Path, path: str, change: Callable[[Json], object]) -> None:
    """Changes a JSON file of the experiment in `out` with `change`, as `rewrite_record` replaces
    one: a record, or the latest manifest itself."""
    content = json.loads((out / path).read_bytes())
    change(content)
    rewrite_record(out, path, _json_bytes(content))


def case_of(out: Path, key: str) -> str:
    """The `case_id` of the current plan's case `key`, as its `experiment.json` records it."""
    record = json.loads(_numbered(out, "plans/*/experiment.json")[-1].read_bytes())
    (case_id,) = (case["case_id"] for case in record["planned_cases"] if case["case_key"] == key)
    return case_id


_ATTEMPT_RECORDS: Final = ("authenticating.json", "started.json", "attempt.json")
"""An attempt's records, in the order it writes them. Each holds its `session` and `sequence`."""


def attempts_of(out: Path, key: str) -> list[str]:
    """The directories of the attempts of the current plan's case `key`, by `session` and then
    `sequence`."""

    def place(directory: Path) -> tuple[int, int]:
        name = next(name for name in _ATTEMPT_RECORDS if (directory / name).exists())
        record = json.loads((directory / name).read_bytes())
        return record["session"], record["sequence"]

    directories = (out / "cases" / case_of(out, key) / "attempts").iterdir()
    return [_relative(out, directory) for directory in sorted(directories, key=place)]


def attempt_of(out: Path, key: str) -> str:
    """The directory of the one attempt of the current plan's case `key`."""
    (directory,) = attempts_of(out, key)
    return directory


def attempt_id_of(directory: str) -> str:
    """The `attempt_id` of the attempt in `directory`, which its directory is named by."""
    return directory.rsplit("/", 1)[-1]


def edit_attempt(out: Path, directory: str, change: Callable[[Json], object]) -> None:
    """Changes each record of the attempt in `directory` the same way, so they still agree, as
    `edit_record` changes one."""
    for name in _ATTEMPT_RECORDS:
        if (out / directory / name).exists():
            edit_record(out, f"{directory}/{name}", change)


def copy_attempt(out: Path, directory: str, case_id: str | None = None, **fields: object) -> str:
    """Copies the attempt in `directory` as a new attempt, of the case `case_id`, or its own, with
    `fields` changed in each of its records, and gives the new attempt's directory. No manifest
    lists it, so only the check under test reads it."""
    case_id = case_id or directory.split("/")[1]
    attempt_id = str(uuid.uuid4())
    copy = f"cases/{case_id}/attempts/{attempt_id}"
    shutil.copytree(out / directory, out / copy)
    for name in _ATTEMPT_RECORDS:
        path = out / copy / name
        if not path.exists():
            continue
        record = json.loads(path.read_bytes())
        if record.get("authenticated_by") == record["attempt_id"]:
            record["authenticated_by"] = attempt_id
        record.update(case_id=case_id, attempt_id=attempt_id, **fields)
        for reference in ("request", "response"):
            if record.get(reference):
                record[reference]["path"] = f"{copy}/{record[reference]['path'].rsplit('/', 1)[-1]}"
        path.write_bytes(_json_bytes(record))
    return copy


def another_parser(out: Path, path: str) -> None:
    """Rewrites the `metrics.csv` at `path`, which no manifest lists, as another parser might have
    written it from the same response, as after an upgrade whose parser reads the response
    differently: a valid table, with the strategy's Sharpe ratio a digit off."""
    rows = read_metrics_csv((out / path).read_bytes(), path)
    changed = [
        row.model_copy(update={"value": _another_digit(row.value)})
        if (row.subject, row.metric_id) == ("strategy", "sharpe_ratio")
        else row
        for row in rows
    ]
    assert changed != list(rows)
    (out / path).write_bytes(metrics_csv(changed))


def _another_digit(value: str | None) -> str:
    """`value` with its last digit changed, so it keeps its decimals."""
    assert value is not None
    return value[:-1] + ("1" if value[-1] != "1" else "2")


_ZEROS: Final = "sha256:" + "0" * 64
"""An `artifact_id` or a hash that no file or plan has."""

_NO_CASE: Final = "case-0123456789abcdef"
"""A `case_id` the synthetic experiment doesn't have."""


def _retitled(out: Path) -> None:
    """Gives the current plan, in its `plan.json` and in its `experiment.json`, which records it,
    another title, without recomputing its hash."""
    edit_record(out, "plans/2/plan.json", lambda plan: plan.update(title="Another title"))
    edit_record(out, "plans/2/experiment.json", lambda record: record.update(title="Another title"))


def _last_entry(**fields: object) -> Callable[[Path], None]:
    """Changes `fields` in the last entry of the current plan's `experiment.json`."""

    def change(out: Path) -> None:
        edit_record(
            out, "plans/2/experiment.json", lambda record: record["plans"][-1].update(fields)
        )

    return change


BROKEN_EXPERIMENTS: Final[dict[str, tuple[Callable[[Path], object], str]]] = {
    # Unchecked, the attempt would read as one a stopped run left running.
    "a listed attempt record missing": (
        lambda out: remove(out, f"{attempt_of(out, 'rebalance-weeks-1')}/attempt.json"),
        "/attempt.json`, which is missing.",
    ),
    # Without the latest manifest, it would read as a first run that stopped before anything was
    # sent: `output.not_empty`.
    "the first plan's experiment.json missing": (
        lambda out: remove(out, "plans/1/experiment.json"),
        "lists `plans/1/experiment.json`, which is missing.",
    ),
    "a listed file with other bytes": (
        lambda out: change_bytes(out, "plans/1/configuration.yaml"),
        "`plans/1/configuration.yaml` doesn't match its artifact_id in the latest manifest",
    ),
    "a plan that doesn't recompute to its hash": (
        _retitled,
        "`plans/2/plan.json` doesn't recompute to its plan_hash",
    ),
    "experiment.json's last entry, by its number": (
        _last_entry(plan=3),
        "experiment.json`'s last entry isn't its directory's plan: it gives another number.",
    ),
    "experiment.json's last entry, by its hash": (
        _last_entry(plan_hash=_ZEROS),
        "last entry isn't its directory's plan: it gives another plan_hash than its plan.json.",
    ),
    "experiment.json's last entry, by plan.json's artifact_id": (
        _last_entry(plan_artifact_id=_ZEROS),
        "its plan.json or configuration.yaml has another artifact_id than it records.",
    ),
    "experiment.json's last entry, by configuration.yaml's artifact_id": (
        _last_entry(configuration_artifact_id=_ZEROS),
        "its plan.json or configuration.yaml has another artifact_id than it records.",
    ),
    "experiment.json's earlier entries": (
        lambda out: edit_record(
            out,
            "plans/2/experiment.json",
            lambda record: record["plans"][0].update(plan_artifact_id=_ZEROS),
        ),
        "experiment.json`'s earlier entries aren't those of the previous plan's experiment.json.",
    ),
    "a latest manifest that isn't synthetic, though the plans record not_required": (
        lambda out: edit_record(
            out,
            "sessions/2/manifest.json",
            lambda manifest: manifest.update(synthetic=False, approval="option"),
        ),
        "isn't synthetic, though the experiment's plans record the approval not_required.",
    ),
    "an attempt naming a case the experiment doesn't have": (
        lambda out: copy_attempt(
            out, attempt_of(out, "rebalance-weeks-1"), case_id=_NO_CASE, sequence=9
        ),
        "name a case their plan doesn't have.",
    ),
    "an attempt naming a session the experiment doesn't have": (
        lambda out: edit_attempt(
            out, attempt_of(out, "rebalance-weeks-1"), lambda record: record.update(session=9)
        ),
        "name a session the experiment doesn't have.",
    ),
    # The default variant's attempt was the second the first session started, after the
    # baseline's.
    "two attempts of a session with one sequence": (
        lambda out: edit_attempt(
            out, attempt_of(out, "rebalance-weeks-1"), lambda record: record.update(sequence=1)
        ),
        "two attempts of session 1 have the same sequence, 1,",
    ),
    # The default variant's request was sent with the baseline's token, in the first session;
    # `holdings-50` authenticated in the second.
    "a request sent with a token from another session": (
        lambda out: edit_attempt(
            out,
            attempt_of(out, "rebalance-weeks-1"),
            lambda record: record.update(
                authenticated_by=attempt_id_of(attempt_of(out, "holdings-50"))
            ),
        ),
        "was sent with a token no attempt of its session obtained before it.",
    ),
}
"""R03-AC17's breaks of a copy of the committed synthetic experiment, each with the problem the
records check's message gives. Its current plan is `plans/2/`, and its latest manifest
`sessions/2/manifest.json`. The plan's new title, "Another title", is a value no message may
show."""


def unreadable(content: Json) -> None:
    """Gives a record a schema version that no version of Trial Folio has a reader for yet."""
    content["schema_version"] = "9.9.9"


UNKNOWN_EXPERIMENT_SCHEMA_VERSIONS: Final[dict[str, Callable[[Path], str]]] = {
    "experiment.json": lambda out: "plans/2/experiment.json",
    "plan.json": lambda out: "plans/2/plan.json",
    "a session record": lambda out: "sessions/2/session.json",
    "an authentication record": lambda out: f"{attempt_of(out, 'baseline')}/authenticating.json",
    "a start record": lambda out: f"{attempt_of(out, 'baseline')}/started.json",
    "an attempt record": lambda out: f"{attempt_of(out, 'baseline')}/attempt.json",
    "the latest manifest": lambda out: "sessions/2/manifest.json",
}
"""R03-AC17's records whose schema version may have no reader, by the path of each in a copy of
the committed synthetic experiment, for `edit_record` to give it `unreadable`'s version."""
