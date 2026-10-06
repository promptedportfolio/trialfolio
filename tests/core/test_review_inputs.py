"""The review's input check reads each result's run, in the configuration's order, checks that
it's a complete run, as `trialfolio report` does, and keeps the bytes it checked of the files a
review copies. Anything that isn't a complete run is refused before anything is written, with a
message that names the result.

Traces, at the core, to R02-AC02 (the copies are byte-identical to the runs' files, and are
written from the bytes the check read), R02-AC06 (an input that isn't a complete run is
`input.not_a_run`, and a `run` directory that doesn't exist is `input.not_found`), and R02-AC14
(an unknown schema version is `artifact.unknown_schema_version`); and to docs/contracts.md,
review output (what each label names, and labels in logs) and configuration files (a path is
resolved relative to the configuration file). The interface checks are R02-T10's.

The runs are copies of the committed `runs/synthetic-run-1.0.0/`, which the broken ones are, as
R01-AC23's are, and runs written over the fake server, as `trialfolio run` writes them. Labels
and run directories are canary-like, so a test can tell that no log holds them.
"""

import json
import logging
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from tests.core.conftest import CONFIGS, RESPONSES, WriteRun, snapshot
from tests.support.broken_runs import (
    BROKEN,
    UNKNOWN_SCHEMA_VERSIONS,
    Json,
    edit_json,
    path_of,
    remove,
    rewrite,
    write_manifest,
)
from tests.support.fake_portfolio123 import Reply
from trialfolio.canonical import sha256_hex
from trialfolio.configuration import read_review_configuration
from trialfolio.contracts.manifest import RunManifest
from trialfolio.errors import TrialFolioError
from trialfolio.review_inputs import (
    ReviewInput,
    RunStores,
    check_review_inputs,
    local_run_stores,
)
from trialfolio.storage import ArtifactStore, LocalArtifactStore

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "runs" / "synthetic-run-1.0.0"
"""The committed historical run, which `trialfolio demo` wrote with the 1.0.0 schemas."""

FORMULA = (CONFIGS / "formula.yaml").read_bytes()
COMPLETE = Reply(200, (RESPONSES / "complete.json").read_bytes())


def label(position: int) -> str:
    return f"canary-label-{position}"


def run_path(position: int) -> str:
    """The `run` path of the result at `position`, as the configuration gives it."""
    return f"runs/canary-run-{position}"


def configure(directory: Path, runs: list[str]) -> tuple[Path, bytes]:
    """Writes a review configuration into `directory`, with one result for each `run` path, in
    order, labeled by its position. The first result is the baseline."""
    lines = [
        "kind: review",
        "schema_version: 1.0.0",
        "title: Input check",
        f"baseline: {label(1)}",
        "results:",
    ]
    for position, run in enumerate(runs, start=1):
        lines += [f"  - label: {label(position)}", f"    run: {json.dumps(run)}"]
    content = ("\n".join(lines) + "\n").encode()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "review.yaml"
    path.write_bytes(content)
    return path, content


def check(path: Path, content: bytes, stores: RunStores | None = None) -> tuple[ReviewInput, ...]:
    configuration = read_review_configuration(content, "review.yaml")
    return check_review_inputs(configuration, stores or local_run_stores(path))


def committed(root: Path, position: int) -> Path:
    """A copy of the committed run, at the `run` path of the result at `position`."""
    run = root / run_path(position)
    shutil.copytree(FIXTURE, run)
    return run


def placed(root: Path, run: Path, position: int) -> Path:
    """Moves a run written over the fake server to the `run` path of the result at
    `position`."""
    to = root / run_path(position)
    to.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(run, to)
    return to


def manifest_of(run: Path) -> RunManifest:
    return RunManifest.model_validate_json((run / "manifest.json").read_bytes())


def refused(root: Path, path: Path, content: bytes) -> TrialFolioError:
    """The error the check gives. It writes nothing, anywhere under `root`."""
    before = snapshot(root)
    with pytest.raises(TrialFolioError) as caught:
        check(path, content)
    assert snapshot(root) == before
    return caught.value


def assert_names_the_result(error: TrialFolioError, position: int) -> None:
    """The message names the result by its label and `run` path. The logged message names it by
    its position, and holds neither."""
    assert f"result `{label(position)}`'s run directory (`{run_path(position)}`)" in (
        error.message.replace("Result", "result", 1)
    )
    assert f"result {position}'s run directory" in error.log_message.replace("Result", "result", 1)
    assert "canary" not in error.log_message


# What each label names, and what's copied (R02-AC02, review output)


def test_each_result_names_its_run_and_holds_the_checked_copies(
    write_run: WriteRun, tmp_path: Path
) -> None:
    runs = [
        committed(tmp_path, 1),
        placed(tmp_path, write_run(FORMULA, COMPLETE).out, 2),
        # No tables, and no saved response.
        placed(tmp_path, write_run(FORMULA, Reply(400, b"Unsupported value")).out, 3),
        # No tables, and a response saved undecoded.
        placed(
            tmp_path,
            write_run(FORMULA, Reply(200, (RESPONSES / "not-json.txt").read_bytes())).out,
            4,
        ),
    ]
    path, content = configure(tmp_path, [run_path(p) for p in range(1, 5)])

    inputs = check(path, content)

    assert [i.position for i in inputs] == [1, 2, 3, 4]
    assert [i.result.label for i in inputs] == [label(p) for p in range(1, 5)]
    for run, checked in zip(runs, inputs, strict=True):
        manifest = manifest_of(run)
        plan = json.loads((run / "plan.json").read_bytes())
        listed = {a.path: a for a in manifest.artifacts}
        tables = "metrics" in {a.role for a in manifest.artifacts}
        record = json.loads((run / path_of(run, "attempt_record")).read_bytes())
        reviewed = checked.reviewed

        assert reviewed.label == checked.result.label
        assert reviewed.run_manifest == "sha256:" + sha256_hex((run / "manifest.json").read_bytes())
        assert reviewed.synthetic == manifest.synthetic
        assert (reviewed.plan_hash, reviewed.case_id) == (
            plan["plan_hash"],
            plan["cases"][0]["case_id"],
        )
        assert reviewed.normalized_tables == tables
        assert reviewed.response == (record["response"] or {}).get("artifact_id")
        # The manifest, the plan, and the tables, when the run has them, and nothing else.
        assert [(c.path, c.role) for c in checked.copies] == [
            ("manifest.json", "run_manifest"),
            ("plan.json", "plan"),
            *(
                [("normalized/metrics.csv", "metrics"), ("normalized/settings.csv", "settings")]
                if tables
                else []
            ),
        ]
        for copy in checked.copies:
            assert copy.content == (run / copy.path).read_bytes()
            if copy.role == "run_manifest":
                assert copy.schema_version == manifest.schema_version
            else:
                entry = listed[copy.path]
                assert (copy.artifact_id, copy.size) == (entry.artifact_id, entry.size)
                assert copy.schema_version == entry.schema_version
    assert [i.reviewed.synthetic for i in inputs] == [True, False, False, False]
    assert [i.reviewed.normalized_tables for i in inputs] == [True, True, False, False]
    assert inputs[2].reviewed.response is None
    assert inputs[3].reviewed.response is not None


class CountingStore(LocalArtifactStore):
    """A local store that counts its reads, by path."""

    def __init__(self, root: str | os.PathLike[str], reads: list[str]) -> None:
        super().__init__(root)
        self._reads = reads

    def read(self, path: str) -> bytes:
        self._reads.append(path)
        return super().read(path)


def test_the_copies_are_the_bytes_read_once_whatever_changes_after(tmp_path: Path) -> None:
    runs = [committed(tmp_path, 1), committed(tmp_path, 2)]
    path, content = configure(tmp_path, [run_path(1), run_path(2)])
    reads: dict[str, list[str]] = {}
    local = local_run_stores(path)

    def counted(run: str) -> ArtifactStore | None:
        store = local(run)
        assert isinstance(store, LocalArtifactStore)
        return CountingStore(store.root, reads.setdefault(run, []))

    inputs = check(path, content, counted)
    for run, checked in zip(runs, inputs, strict=True):
        for copy in checked.copies:
            (run / copy.path).write_bytes(b"changed after the check\n")

    listed = [a.path for a in manifest_of(FIXTURE).artifacts]
    for checked in inputs:
        # The manifest and each file it lists, each read once.
        assert sorted(reads[run_path(checked.position)]) == sorted(["manifest.json", *listed])
        assert len(checked.copies) == 4
        for copy in checked.copies:
            assert copy.content == (FIXTURE / copy.path).read_bytes()


def test_two_results_that_name_one_run_name_the_same_run(tmp_path: Path) -> None:
    committed(tmp_path, 1)
    path, content = configure(tmp_path, [run_path(1), run_path(1)])

    first, second = check(path, content)

    assert first.reviewed.label != second.reviewed.label
    assert first.reviewed.model_dump(exclude={"label"}) == second.reviewed.model_dump(
        exclude={"label"}
    )
    assert first.copies == second.copies


def test_a_run_path_is_read_from_the_configurations_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    committed(tmp_path, 1)
    absolute = committed(tmp_path, 2)
    path, content = configure(tmp_path / "reviews", [f"../{run_path(1)}", str(absolute)])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    inputs = check(path, content)

    assert [i.reviewed.synthetic for i in inputs] == [True, True]
    # A path that names a run only from the working directory names nothing.
    shutil.copytree(tmp_path / "runs", elsewhere / "runs")
    path, content = configure(tmp_path / "reviews", [run_path(1), run_path(2)])
    error = refused(tmp_path, path, content)
    assert error.code == "input.not_found"
    assert_names_the_result(error, 1)


@pytest.mark.skipif(os.name == "nt", reason="creating a symbolic link needs a privilege there")
def test_a_run_path_after_a_symbolic_link_is_read_where_the_file_system_leads(
    tmp_path: Path,
) -> None:
    # A corrected defect: the check found the run where the file system leads, but read it
    # where `..` leads when it's removed as text, with the segment before it.
    shared, project = tmp_path / "shared", tmp_path / "project"
    committed(shared, 1)
    committed(shared, 2)
    # Where `..` leads as text from the linked directory: an incomplete run at result 1's path,
    # and the only run at result 3's.
    remove(committed(project, 1), "manifest.json")
    committed(project, 3)
    (shared / "reviews").mkdir()
    (project / "reviews").symlink_to(shared / "reviews", target_is_directory=True)
    runs = [f"../{run_path(1)}", f"../{run_path(2)}"]
    path, content = configure(project / "reviews", runs)

    inputs = check(path, content)

    for checked in inputs:
        for copy in checked.copies:
            assert copy.content == (FIXTURE / copy.path).read_bytes()
    path, content = configure(project / "reviews", [*runs, f"../{run_path(3)}"])
    error = refused(tmp_path, path, content)
    assert error.code == "input.not_found"
    assert error.message.startswith(
        f"Result `{label(3)}`'s run directory (`../{run_path(3)}`) doesn't exist."
    )
    assert error.log_message.startswith("Result 3's run directory doesn't exist.")


# What isn't a complete run (R02-AC06)


@pytest.mark.parametrize("position", [1, 2], ids=["the baseline", "another result"])
@pytest.mark.parametrize(("break_run", "problem"), BROKEN.values(), ids=BROKEN.keys())
def test_an_incomplete_run_is_refused_naming_its_result(
    tmp_path: Path, position: int, break_run: Callable[[Path], None], problem: str
) -> None:
    runs = [committed(tmp_path, 1), committed(tmp_path, 2)]
    break_run(runs[position - 1])
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    error = refused(tmp_path, path, content)

    assert error.code == "input.not_a_run"
    assert error.message.startswith(
        f"Result `{label(position)}`'s run directory (`{run_path(position)}`) isn't a complete"
        f" Trial Folio run: {problem}"
    )
    assert error.log_message.startswith(
        f"Result {position}'s run directory isn't a complete Trial Folio run: {problem}"
    )
    assert_names_the_result(error, position)
    assert "Another title" not in error.message


def test_a_run_directory_that_doesnt_exist_is_not_found(tmp_path: Path) -> None:
    committed(tmp_path, 1)
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    error = refused(tmp_path, path, content)

    assert error.code == "input.not_found"
    assert error.message.startswith(
        f"Result `{label(2)}`'s run directory (`{run_path(2)}`) doesn't exist."
    )
    assert error.log_message.startswith("Result 2's run directory doesn't exist.")
    assert_names_the_result(error, 2)


@pytest.mark.skipif(os.name == "nt", reason="creating a symbolic link needs a privilege there")
def test_a_symbolic_link_to_nothing_is_not_found(tmp_path: Path) -> None:
    committed(tmp_path, 1)
    (tmp_path / run_path(2)).symlink_to(tmp_path / "nothing", target_is_directory=True)
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    # Not through `refused`, whose snapshot can't read a link to nothing.
    with pytest.raises(TrialFolioError) as caught:
        check(path, content)

    error = caught.value
    assert error.code == "input.not_found"
    assert_names_the_result(error, 2)


@pytest.mark.parametrize(
    ("run", "shown"),
    [
        pytest.param(
            f"notes.txt/../{run_path(1)}",
            f"notes.txt/../{run_path(1)}",
            id="after-a-file",
            marks=pytest.mark.skipif(
                os.name == "nt", reason="Windows removes a `..` as text, before the file system"
            ),
        ),
        pytest.param(f"{run_path(1)}\0", f"{run_path(1)}\\u0000", id="with-a-nul"),
    ],
)
def test_a_run_path_the_file_system_refuses_is_not_found(
    tmp_path: Path, run: str, shown: str
) -> None:
    # A corrected defect: on Python 3.12, the check removed a `..` after a file and read the run
    # beyond it, and a NUL raised an error that named no result.
    committed(tmp_path, 1)
    (tmp_path / "notes.txt").write_bytes(b"A file, not a directory.\n")
    path, content = configure(tmp_path, [run_path(1), run])

    error = refused(tmp_path, path, content)

    assert error.code == "input.not_found"
    assert error.message.startswith(
        f"Result `{label(2)}`'s run directory (`{shown}`) doesn't exist."
    )
    assert error.log_message.startswith("Result 2's run directory doesn't exist.")


def test_the_first_result_that_fails_is_reported(tmp_path: Path) -> None:
    remove(committed(tmp_path, 1), "manifest.json")
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    first = refused(tmp_path, path, content)

    path, content = configure(tmp_path, [run_path(2), run_path(1)])
    second = refused(tmp_path, path, content)

    # Result 2 names nothing, but result 1's run, which isn't complete, comes first.
    assert first.code == "input.not_a_run"
    assert_names_the_result(first, 1)
    # Reversed, result 1 names nothing, and that comes first.
    assert second.code == "input.not_found"
    assert "result 1's run directory" in second.log_message.lower()


def test_a_table_that_cant_be_read_names_its_result(tmp_path: Path) -> None:
    run = committed(tmp_path, 2)
    committed(tmp_path, 1)
    rewrite(
        run,
        "normalized/metrics.csv",
        b"\xef\xbb\xbf" + (run / "normalized/metrics.csv").read_bytes(),
    )
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    error = refused(tmp_path, path, content)

    assert error.code == "input.not_a_run"
    assert error.log_message == (
        "Result 2's run directory isn't a complete Trial Folio run: its `normalized/metrics.csv`"
        " isn't a normalized table Trial Folio can read: it starts with a byte-order mark."
        " Nothing was written. Give the output directory of a run that finished, as"
        " `trialfolio run` or `trialfolio demo` wrote it."
    )
    assert_names_the_result(error, 2)


@pytest.mark.parametrize("role", ["plan", "metrics"])
def test_a_copy_needs_the_schema_version_its_run_records(tmp_path: Path, role: str) -> None:
    run = committed(tmp_path, 2)
    committed(tmp_path, 1)
    entry_path = path_of(run, role)

    def unversioned(manifest: Json) -> None:
        for artifact in cast("list[Json]", manifest["artifacts"]):
            if artifact["role"] == role:
                artifact["schema_version"] = None

    edit_json(run, "manifest.json", unversioned)
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    error = refused(tmp_path, path, content)

    assert error.code == "input.not_a_run"
    assert (
        f"isn't a complete Trial Folio run: its manifest lists `{entry_path}` without a schema"
        " version, which a review records for each file it copies."
    ) in error.message
    assert_names_the_result(error, 2)


def test_a_run_with_more_than_one_saved_response_is_refused(tmp_path: Path) -> None:
    """A second attempt, whose records and files are each listed with their hashes, so only the
    review's own check can tell."""
    run = committed(tmp_path, 2)
    committed(tmp_path, 1)
    first = path_of(run, "attempt_record").rpartition("/")[0]
    attempt_id = str(uuid.UUID(int=1, version=4))
    second = f"{first.rpartition('/')[0]}/{attempt_id}"
    shutil.copytree(run / first, run / second)
    manifest = json.loads((run / "manifest.json").read_bytes())
    entries = [a for a in manifest["artifacts"] if a["path"].startswith(f"{first}/")]
    for entry in entries:
        moved = entry["path"].replace(first, second)
        if entry["role"] in ("start_record", "attempt_record"):
            record = json.loads((run / moved).read_bytes())
            record["attempt_id"] = attempt_id
            for reference in ("request", "response"):
                if record.get(reference) is not None:
                    record[reference]["path"] = record[reference]["path"].replace(first, second)
            data = (json.dumps(record, indent=2) + "\n").encode()
            (run / moved).write_bytes(data)
            entry = {**entry, "artifact_id": "sha256:" + sha256_hex(data), "size": len(data)}
        manifest["artifacts"].append({**entry, "path": moved})
    write_manifest(run, manifest)
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    error = refused(tmp_path, path, content)

    assert error.code == "input.not_a_run"
    assert (
        "its attempts saved more than one response, but a screen run sends its request at most"
        " once."
    ) in error.message
    assert_names_the_result(error, 2)


# A schema version without a reader (R02-AC14)


@pytest.mark.parametrize(
    ("target", "change", "named"),
    UNKNOWN_SCHEMA_VERSIONS.values(),
    ids=UNKNOWN_SCHEMA_VERSIONS.keys(),
)
def test_a_schema_version_without_a_reader_is_unknown(
    tmp_path: Path, target: str, change: Callable[[Json], None], named: str
) -> None:
    run = committed(tmp_path, 2)
    committed(tmp_path, 1)
    if target != "manifest.json":
        target = path_of(run, target)
    edit_json(run, target, change)
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    error = refused(tmp_path, path, content)

    assert error.code == "artifact.unknown_schema_version"
    assert f"{named}` in result `{label(2)}`'s run directory (`{run_path(2)}`): " in error.message
    assert f"{named}` in result 2's run directory: " in error.log_message
    assert_names_the_result(error, 2)
    assert "1.1.0" not in error.message


# Labels in logs (review output)


def test_the_checks_log_events_name_each_result_by_its_position(
    write_run: WriteRun, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    committed(tmp_path, 1)
    placed(tmp_path, write_run(FORMULA, COMPLETE).out, 2)
    path, content = configure(tmp_path, [run_path(1), run_path(2)])

    with caplog.at_level(logging.DEBUG, logger="trialfolio"):
        inputs = check(path, content)
        remove(tmp_path / run_path(2), "manifest.json")
        with pytest.raises(TrialFolioError):
            check(path, content)

    loaded = [r for r in caplog.records if getattr(r, "event", None) == "review.input.loaded"]
    assert [r.getMessage() for r in loaded] == [
        f"Checked result {i.position}'s run, {i.reviewed.run_manifest}." for i in inputs
    ] + [f"Checked result 1's run, {inputs[0].reviewed.run_manifest}."]
    assert [(vars(r)["plan_hash"], vars(r)["case_id"]) for r in loaded[:2]] == [
        (i.reviewed.plan_hash, i.reviewed.case_id) for i in inputs
    ]
    assert not any("canary" in record.getMessage() for record in caplog.records)
