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

- **`BROKEN_RANKING_RUNS`** and **`BROKEN_RANKING_EXPERIMENTS`** hold release 0.4.0's R04-AC12
  breaks of the records with a ranking definition: of a copy of the committed
  `runs/synthetic-run-1.1.0/`, which `trialfolio report` refuses, and of a copy of the committed
  `experiments/synthetic-experiment-1.1.0/`, which a resume refuses, each with the problem the
  records check's message gives for it. **`UNKNOWN_RANKING_RUN_SCHEMA_VERSIONS`** and
  **`UNKNOWN_RANKING_EXPERIMENT_SCHEMA_VERSIONS`** hold each record 0.4.0 adds, whose schema
  version can have no reader. The break that needs a token a 401 or 403 to a `rank_update`
  dropped breaks an experiment the experiment builder writes, with `copy_attempt`.

A break that edits a file the manifest lists, with `rewrite` or `edit_json`, updates its manifest
entry to match, so only the checks beyond the hashes can tell, and one that removes such a file,
with `unlist` or `unlist_record`, removes its entry too. `edit_manifest` changes a run's entries
as the run manifest 1.0.0's model reads them, and `move` moves a file with its entry. An
experiment's break, with `rewrite_record` or `edit_record`, does the same for the latest manifest,
and for the `artifact_id` that each plan's `experiment.json` records for a plan's files, as
release 0.3.0's broken experiments require. R02-T10 moved the runs' breaks here from
`tests/core/test_review_inputs.py` and `tests/interface/test_report_command.py`, so the review's
interface checks could share them; R03-T11 added the experiments', and R04-T13 those with a
ranking definition. TS-T05 moved here the editors that `tests/core/test_saved_runs.py` and the
core's two resume modules wrote again, with `edit_manifest` and `move`, from the former, and
`record_1_1_0`, which the latter shares with `BROKEN_RANKING_EXPERIMENTS`.
"""

import json
import re
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

from tests.support.paths import RANKING_DEFINITIONS
from tests.support.screen_runs import manifest_json
from trialfolio.canonical import sha256_hex
from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.manifest import ManifestArtifact, RunManifest
from trialfolio.tables import (
    metrics_csv,
    read_metrics_csv,
    read_settings_csv_v1_1,
    settings_csv_v1_1,
)

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


def unlist(run: Path, path: str) -> None:
    """Removes a file of a saved run, and its manifest entry, so only the checks of what a run
    must hold can tell."""
    (run / path).unlink()
    manifest = json.loads((run / "manifest.json").read_bytes())
    manifest["artifacts"] = [a for a in manifest["artifacts"] if a["path"] != path]
    write_manifest(run, manifest)


def edit_manifest(
    run: Path, change: Callable[[list[ManifestArtifact]], list[ManifestArtifact]]
) -> None:
    """Changes the entries of a saved run's manifest, a run manifest 1.0.0."""
    manifest = RunManifest.model_validate_json((run / "manifest.json").read_bytes())
    artifacts = tuple(change(list(manifest.artifacts)))
    (run / "manifest.json").write_bytes(
        manifest_json(manifest.model_copy(update={"artifacts": artifacts}))
    )


def move(run: Path, path: str, to: str) -> None:
    """Moves a file of a saved run, and its manifest entry with it."""
    (run / to).parent.mkdir(parents=True, exist_ok=True)
    (run / path).rename(run / to)
    edit_manifest(
        run,
        lambda artifacts: [
            artifact.model_copy(update={"path": to}) if artifact.path == path else artifact
            for artifact in artifacts
        ],
    )


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


_ATTEMPT_RECORDS: Final = ("authenticating.json", "updating.json", "started.json", "attempt.json")
"""An attempt's records, in the order it writes them: an update record only when it sends a
definition. Each holds its `session` and `sequence`."""


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
        # A record 1.3.0 references its rank_update's files too.
        for holder in (record, record.get("ranking_update") or {}):
            for reference in ("request", "response"):
                if holder.get(reference):
                    holder[reference]["path"] = (
                        f"{copy}/{holder[reference]['path'].rsplit('/', 1)[-1]}"
                    )
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


# Broken runs and experiments with a ranking definition (release 0.4.0's R04-AC12)


def unlist_record(out: Path, path: str) -> None:
    """Removes a file of the experiment in `out`, and the latest manifest's entry for it, so only
    the checks of what an experiment must hold can tell."""
    (out / path).unlink()
    latest = _numbered(out, "sessions/*/manifest.json")[-1]
    manifest = json.loads(latest.read_bytes())
    manifest["artifacts"] = [a for a in manifest["artifacts"] if a["path"] != path]
    latest.write_bytes(_json_bytes(manifest))


def _transport_changed(record: Json) -> None:
    record["transport"]["urllib3"] = "0.0.1"


def _rank_update_status(status: int) -> Callable[[Json], None]:
    """Gives a record's `POST /rank` exchange another status."""

    def change(record: Json) -> None:
        (rank,) = [e for e in record["exchanges"] if e["request"] == "POST /rank"]
        rank["status"] = status

    return change


def _backtest_after_a_failed_rank_update(record: Json) -> None:
    """Gives an attempt record's `POST /rank` exchange a 500, and no saved `rank_update`
    response, which follows only a 200, so the record shows a backtest sent after a `rank_update`
    that didn't get its 200, and nothing else wrong."""
    _rank_update_status(500)(record)
    record["ranking_update"]["response"] = None


def _another_weight(content: bytes, node: str) -> bytes:
    """A `settings.csv` 1.1.0 with the weight row of `node` given another weight, 45."""
    rows = read_settings_csv_v1_1(content, "settings.csv")
    assert any(row.node == node for row in rows)
    changed = [row.model_copy(update={"value": "45"}) if row.node == node else row for row in rows]
    return settings_csv_v1_1(changed)


def attempt_directory(run: Path) -> str:
    """The directory of a run's one attempt, from the attempt record its manifest lists."""
    return path_of(run, "attempt_record").rsplit("/", 1)[0]


def _run_attempt_file(name: str) -> Callable[[Path], str]:
    return lambda run: f"{attempt_directory(run)}/{name}"


BROKEN_RANKING_RUNS: Final[dict[str, tuple[Callable[[Path], None], str]]] = {
    "an attempt with started.json and no updating.json": (
        lambda run: unlist(run, _run_attempt_file("updating.json")(run)),
        "wrote its update record first",
    ),
    "an update record that disagrees with its start record": (
        lambda run: edit_json(run, _run_attempt_file("updating.json")(run), _transport_changed),
        "doesn't hold the update record's values and exchanges",
    ),
    "a started.json whose exchanges don't end with POST /rank and its 200": (
        lambda run: edit_json(
            run, _run_attempt_file("started.json")(run), _rank_update_status(500)
        ),
        "isn't a valid start record",
    ),
    # The manifest's entry is updated to match, so only the attempt record's reference catches
    # it.
    "a rank-update-request.json whose bytes aren't what the attempt record records": (
        lambda run: rewrite(run, _run_attempt_file("rank-update-request.json")(run), b"{}\n"),
        "which its manifest doesn't list as that file",
    ),
    "an attempt record 1.0.0 under a plan 1.2.0": (
        lambda run: edit_json(
            run,
            _run_attempt_file("attempt.json")(run),
            lambda record: record.update(schema_version="1.0.0"),
        ),
        "isn't the version an attempt under its plan writes",
    ),
    "a POST /screen/backtest exchange that doesn't follow a POST /rank with a 200": (
        lambda run: edit_json(
            run, _run_attempt_file("attempt.json")(run), _backtest_after_a_failed_rank_update
        ),
        "isn't a valid attempt record",
    ),
    "a run whose definition.xml is missing": (
        lambda run: unlist(run, "definition.xml"),
        "doesn't list definition.xml as the run's one ranking_definition",
    ),
    "a run whose definition isn't its ranking_source's": (
        lambda run: rewrite(
            run, "definition.xml", (RANKING_DEFINITIONS / "synthetic-heavy.xml").read_bytes()
        ),
        "isn't its plan's ranking definition",
    ),
    "a weight row that isn't its definition's": (
        lambda run: rewrite(
            run,
            "normalized/settings.csv",
            _another_weight((run / "normalized/settings.csv").read_bytes(), "Value"),
        ),
        "weight rows aren't its definition's",
    ),
}
"""R04-AC12's breaks of a copy of the committed run with a ranking definition, which
`trialfolio report` refuses, each with the problem the message gives. Its one attempt, the
baseline's, authenticated, so its `started.json` holds `POST /auth` and `POST /rank`."""

UNKNOWN_RANKING_RUN_SCHEMA_VERSIONS: Final[dict[str, tuple[Callable[[Path], str], bool]]] = {
    "run manifest 1.1.0": (lambda run: "manifest.json", False),
    "plan 1.2.0": (lambda run: "plan.json", False),
    "an update record": (_run_attempt_file("updating.json"), False),
    "a start record 1.2.0": (_run_attempt_file("started.json"), False),
    "an attempt record 1.2.0": (_run_attempt_file("attempt.json"), False),
    "settings.csv 1.1.0's entry": (lambda run: "normalized/settings.csv", True),
}
"""R04-AC12's records of a run with a ranking definition whose schema version may have no
reader, by the path of each in a copy of the committed run, and whether the version is the one the
manifest's entry gives, which is the only one a table has, or the file's own."""


def _experiment_attempt_file(key: str, name: str) -> Callable[[Path], str]:
    return lambda out: f"{attempt_of(out, key)}/{name}"


def record_1_1_0(out: Path, directory: str) -> None:
    """An attempt record 1.1.0, valid, of an attempt that ended before it authenticated, of the
    case of the attempt in `directory`, under the current plan 1.3.0, in a new attempt's directory
    of session 2, which no manifest lists."""
    record = json.loads((out / directory / "attempt.json").read_bytes())
    attempt_id = str(uuid.uuid4())
    # Validated from its JSON, as the strict model reads a file.
    old = AttemptRecordV1_1.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "trialfolio_version": record["trialfolio_version"],
                "attempt_id": attempt_id,
                "case_id": record["case_id"],
                "plan_hash": record["plan_hash"],
                "session": 2,
                "sequence": 9,
                "authenticated_by": None,
                "repeat_of": None,
                "started_at": record["started_at"],
                "provider_wrapper": record["provider_wrapper"],
                "transport": record["transport"],
                "ended_at": record["started_at"],
                "outcome": "failed",
                "error": {"code": "command.interrupted", "message": "Interrupted."},
                "exchanges": [],
                "possibly_charged": False,
                "request": None,
                "response": None,
                "provider_metadata": {"cost": None, "quota_remaining": None},
            }
        )
    )
    attempt = out / "cases" / record["case_id"] / "attempts" / attempt_id
    attempt.mkdir()
    (attempt / "attempt.json").write_bytes(old.model_dump_json(indent=2).encode())


def _experiment_weight_changed(out: Path) -> None:
    path = f"cases/{case_of(out, 'value-heavy')}/normalized/settings.csv"
    rewrite_record(out, path, _another_weight((out / path).read_bytes(), "Value/Earnings Yield"))


BROKEN_RANKING_EXPERIMENTS: Final[dict[str, tuple[Callable[[Path], object], str]]] = {
    "an attempt with started.json and no updating.json": (
        lambda out: unlist_record(out, _experiment_attempt_file("baseline", "updating.json")(out)),
        "without the update record written before it",
    ),
    "an update record that disagrees with its start record": (
        lambda out: edit_record(
            out, _experiment_attempt_file("value-heavy", "updating.json")(out), _transport_changed
        ),
        "the start record doesn't hold the update record's values",
    ),
    "a started.json whose exchanges don't end with POST /rank and its 200": (
        lambda out: edit_record(
            out,
            _experiment_attempt_file("value-heavy", "started.json")(out),
            _rank_update_status(500),
        ),
        "isn't a valid start record",
    ),
    # The latest manifest's entry is updated to match, so only the attempt record's reference
    # catches it.
    "a rank-update-request.json whose bytes aren't what the attempt record records": (
        lambda out: rewrite_record(
            out,
            _experiment_attempt_file("no-sales-yield", "rank-update-request.json")(out),
            b"{}\n",
        ),
        "doesn't match the artifact_id its attempt record gives it",
    ),
    "an attempt record 1.1.0 under a plan 1.3.0": (
        lambda out: record_1_1_0(out, attempt_of(out, "baseline")),
        "aren't the version an attempt under their plan writes",
    ),
    "a POST /screen/backtest exchange that doesn't follow a POST /rank with a 200": (
        lambda out: edit_record(
            out,
            _experiment_attempt_file("no-sales-yield", "attempt.json")(out),
            _backtest_after_a_failed_rank_update,
        ),
        "isn't a valid attempt record",
    ),
    "a plan whose definition.xml is missing": (
        lambda out: unlist_record(out, "plans/1/definition.xml"),
        "`plans/1/definition.xml` is missing",
    ),
    "a plan whose definition isn't its ranking_source's": (
        lambda out: rewrite_record(
            out,
            "plans/2/definition.xml",
            (RANKING_DEFINITIONS / "synthetic-heavy.xml").read_bytes(),
        ),
        "isn't its plan's ranking definition",
    ),
    "a weight row that isn't its definition's": (
        _experiment_weight_changed,
        "weight rows aren't its case's definition's",
    ),
}
"""R04-AC12's breaks of a copy of the committed synthetic experiment with a ranking definition,
each with the problem the records check's message gives. Its current plan is `plans/2/`, and its
latest manifest `sessions/2/manifest.json`. `baseline` authenticated in session 1, and
`value-heavy` sent with its token after it; `no-sales-yield`, which the revision added,
authenticated in session 2."""

UNKNOWN_RANKING_EXPERIMENT_SCHEMA_VERSIONS: Final[dict[str, tuple[Callable[[Path], str], bool]]] = {
    "experiment.json 1.1.0": (lambda out: "plans/2/experiment.json", False),
    "plan 1.3.0": (lambda out: "plans/2/plan.json", False),
    "an update record": (_experiment_attempt_file("value-heavy", "updating.json"), False),
    "a start record 1.3.0": (_experiment_attempt_file("value-heavy", "started.json"), False),
    "an attempt record 1.3.0": (_experiment_attempt_file("value-heavy", "attempt.json"), False),
    "experiment manifest 1.1.0": (lambda out: "sessions/2/manifest.json", False),
    "settings.csv 1.1.0's entry": (
        lambda out: f"cases/{case_of(out, 'baseline')}/normalized/settings.csv",
        True,
    ),
}
"""R04-AC12's records of an experiment with a ranking definition whose schema version may have no
reader, by the path of each in a copy of the committed synthetic experiment, and whether the
version is the one the latest manifest's entry gives, which is the only one a table has, or the
file's own."""
