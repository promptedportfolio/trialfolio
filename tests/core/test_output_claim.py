"""A command claims its output directory with its first file, and a claim that fails removes only
what it created.

Traces to docs/contracts.md, CLI behavior (claiming the directory), and interrupts (before the
claim succeeds); to R01-AC15's check that a directory isn't empty, hidden files included; to
R01-AC27, of which this module is the core part: processes released together claim one directory,
and at most one succeeds each time; and to R01-AC28's interrupt while the claim writes `plan.json`,
which leaves nothing behind.
"""

import errno
import multiprocessing
import os
import sys
from multiprocessing.queues import Queue
from multiprocessing.synchronize import Barrier
from pathlib import Path

import pytest

from tests.core.conftest import Faults, SyncLog, identity, raises, snapshot
from trialfolio.errors import TrialFolioError
from trialfolio.storage import LocalArtifactStore

PLAN = b'{"schema_version": "1.0.0"}\n'


def claim_fails_with(code: str, store: LocalArtifactStore) -> TrialFolioError:
    with pytest.raises(TrialFolioError) as raised:
        store.claim("plan.json", PLAN)
    assert raised.value.code == code
    return raised.value


def test_check_empty_accepts_an_absent_or_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    LocalArtifactStore(tmp_path / "absent" / "out").check_empty()
    LocalArtifactStore(tmp_path / "empty").check_empty()

    assert snapshot(tmp_path) == {"empty": None}


@pytest.mark.parametrize("name", ["notes.txt", ".hidden"])
def test_check_empty_refuses_a_directory_that_holds_anything(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_bytes(b"kept\n")

    with pytest.raises(TrialFolioError) as raised:
        LocalArtifactStore(tmp_path).check_empty()

    assert raised.value.code == "output.not_empty"
    assert snapshot(tmp_path) == {name: b"kept\n"}


def test_check_empty_refuses_a_file(tmp_path: Path) -> None:
    (tmp_path / "out").write_bytes(b"kept\n")

    with pytest.raises(TrialFolioError) as raised:
        LocalArtifactStore(tmp_path / "out").check_empty()

    assert raised.value.code == "output.not_empty"


def test_claim_creates_the_directory_and_its_first_file(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "runs" / "baseline")

    stored = store.claim("plan.json", PLAN)

    assert (stored.path, stored.size) == ("plan.json", len(PLAN))
    assert snapshot(tmp_path) == {
        "runs": None,
        "runs/baseline": None,
        "runs/baseline/plan.json": PLAN,
    }
    # Once claimed, the store writes.
    store.write("configuration.yaml", b"kind: screen\n")


def test_claim_takes_an_existing_empty_directory(tmp_path: Path) -> None:
    LocalArtifactStore(tmp_path).claim("plan.json", PLAN)

    assert snapshot(tmp_path) == {"plan.json": PLAN}


@pytest.mark.skipif(sys.platform == "win32", reason="Linux and macOS behavior")
def test_claim_syncs_the_file_each_new_directory_and_the_parent_of_the_first(
    tmp_path: Path, sync_log: SyncLog
) -> None:
    LocalArtifactStore(tmp_path / "runs" / "baseline").claim("plan.json", PLAN)

    assert sync_log.take() == {
        identity(tmp_path / "runs" / "baseline" / "plan.json"),
        identity(tmp_path / "runs" / "baseline"),
        identity(tmp_path / "runs"),
        identity(tmp_path),
    }


@pytest.mark.parametrize("name", ["notes.txt", ".hidden", "plan.json"])
def test_claim_of_a_directory_that_isnt_empty_changes_nothing(tmp_path: Path, name: str) -> None:
    # Including a file under the claim's own name, which it must not remove.
    (tmp_path / name).write_bytes(b"kept\n")

    claim_fails_with("output.not_empty", LocalArtifactStore(tmp_path))

    assert snapshot(tmp_path) == {name: b"kept\n"}


def test_claim_of_a_file_changes_nothing(tmp_path: Path) -> None:
    (tmp_path / "out").write_bytes(b"kept\n")

    claim_fails_with("output.not_empty", LocalArtifactStore(tmp_path / "out"))

    assert snapshot(tmp_path) == {"out": b"kept\n"}


def test_claim_fails_when_another_process_writes_during_it(tmp_path: Path, faults: Faults) -> None:
    root = tmp_path / "runs" / "baseline"
    faults.on_write("plan.json", lambda: (root / "theirs.txt").write_bytes(b"theirs\n"))

    message = claim_fails_with("output.not_empty", LocalArtifactStore(root)).message

    assert "Another process wrote" in message
    # The claim removed its own file. The directories it created hold the other file, so they
    # stay.
    assert snapshot(tmp_path) == {
        "runs": None,
        "runs/baseline": None,
        "runs/baseline/theirs.txt": b"theirs\n",
    }


def test_claim_fails_when_the_directory_disappears_during_it(
    tmp_path: Path, faults: Faults
) -> None:
    # A competing claim that created the directory failed, and removed it.
    root = tmp_path / "runs" / "baseline"
    faults.on_open("plan.json", lambda: os.rmdir(root))

    claim_fails_with("output.not_empty", LocalArtifactStore(root))

    # The parent it created is removed too.
    assert snapshot(tmp_path) == {}


def test_claim_fails_when_a_parent_disappears_during_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "runs" / "baseline"
    real_mkdir = os.mkdir

    def mkdir(path: str | os.PathLike[str], mode: int = 0o777) -> None:
        if Path(path) == root:
            os.rmdir(root.parent)  # The competing claim removed the parent it created.
        real_mkdir(path, mode)

    monkeypatch.setattr(os, "mkdir", mkdir)

    claim_fails_with("output.not_empty", LocalArtifactStore(root))

    assert snapshot(tmp_path) == {}


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (OSError(errno.ENOSPC, "No space left on device"), TrialFolioError),
        (KeyboardInterrupt(), KeyboardInterrupt),
    ],
    ids=["disk-full", "interrupt"],
)
def test_a_claim_that_fails_while_writing_leaves_nothing(
    tmp_path: Path,
    faults: Faults,
    failure: BaseException,
    expected: type[BaseException],
) -> None:
    faults.on_write("plan.json", raises(failure))

    with pytest.raises(expected) as raised:
        LocalArtifactStore(tmp_path / "runs" / "baseline").claim("plan.json", PLAN)

    if isinstance(raised.value, TrialFolioError):
        assert raised.value.code == "storage.write_failed"
        assert "No space left on device" in raised.value.message
    assert snapshot(tmp_path) == {}


def test_a_failed_claim_leaves_a_directory_another_process_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, faults: Faults
) -> None:
    # Another process creates the output directory first, so the claim uses it as it is, and
    # doesn't remove it. The claim created the parent, which isn't empty, so it stays too.
    root = tmp_path / "runs" / "baseline"
    real_mkdir = os.mkdir

    def mkdir(path: str | os.PathLike[str], mode: int = 0o777) -> None:
        if Path(path) == root:
            real_mkdir(path, mode)
            raise FileExistsError(errno.EEXIST, "File exists")
        real_mkdir(path, mode)

    monkeypatch.setattr(os, "mkdir", mkdir)
    faults.on_write("plan.json", raises(OSError(errno.ENOSPC, "No space left on device")))

    claim_fails_with("storage.write_failed", LocalArtifactStore(root))

    assert snapshot(tmp_path) == {"runs": None, "runs/baseline": None}


def test_an_interrupt_as_the_claim_creates_its_file_leaves_nothing(
    tmp_path: Path, faults: Faults
) -> None:
    # The interrupt arrives as os.open returns, before the store has the descriptor.
    faults.after_open("plan.json", raises(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        LocalArtifactStore(tmp_path / "runs" / "baseline").claim("plan.json", PLAN)

    assert snapshot(tmp_path) == {}


def test_an_interrupt_as_the_claim_creates_a_directory_leaves_nothing(
    tmp_path: Path, faults: Faults
) -> None:
    faults.after_mkdir("baseline", raises(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        LocalArtifactStore(tmp_path / "runs" / "baseline").claim("plan.json", PLAN)

    assert snapshot(tmp_path) == {}


def test_an_interrupt_before_the_claim_opens_its_file_leaves_another_processs_file(
    tmp_path: Path, faults: Faults
) -> None:
    # The claim can't tell whether it created the file, so it removes it only if it's empty.
    def theirs_then_interrupt() -> None:
        (tmp_path / "plan.json").write_bytes(b"theirs\n")
        raise KeyboardInterrupt

    faults.on_open("plan.json", theirs_then_interrupt)

    with pytest.raises(KeyboardInterrupt):
        LocalArtifactStore(tmp_path).claim("plan.json", PLAN)

    assert snapshot(tmp_path) == {"plan.json": b"theirs\n"}


def test_a_failed_close_fails_the_claim_and_leaves_nothing(tmp_path: Path, faults: Faults) -> None:
    faults.after_close("plan.json", raises(OSError(errno.EIO, "Input/output error")))

    message = claim_fails_with(
        "storage.write_failed", LocalArtifactStore(tmp_path / "runs" / "baseline")
    ).message

    assert "Input/output error" in message
    assert snapshot(tmp_path) == {}


@pytest.mark.skipif(sys.platform == "win32", reason="Linux and macOS behavior")
def test_claim_syncs_the_parent_of_a_directory_it_didnt_create(
    tmp_path: Path, sync_log: SyncLog
) -> None:
    # A competing claim may have created the directory and failed before syncing its entry.
    (tmp_path / "out").mkdir()

    LocalArtifactStore(tmp_path / "out").claim("plan.json", PLAN)

    assert identity(tmp_path) in sync_log.take()


def test_dot_dot_in_the_output_path_creates_nothing_outside_it(tmp_path: Path) -> None:
    LocalArtifactStore(tmp_path / "missing" / ".." / "out").claim("plan.json", PLAN)

    assert snapshot(tmp_path) == {"out": None, "out/plan.json": PLAN}


@pytest.mark.skipif(sys.platform == "win32", reason="symbolic links need privileges on Windows")
def test_a_link_to_nothing_as_the_output_directory_is_not_a_directory(tmp_path: Path) -> None:
    (tmp_path / "out").symlink_to(tmp_path / "nowhere")
    store = LocalArtifactStore(tmp_path / "out")

    with pytest.raises(TrialFolioError) as raised:
        store.check_empty()
    message = claim_fails_with("output.not_empty", store).message

    assert raised.value.code == "output.not_empty"
    assert "isn't a directory" in raised.value.message
    assert "isn't a directory" in message
    assert sorted(os.listdir(tmp_path)) == ["out"]


@pytest.mark.parametrize("parent", ["file", "link-to-nothing"])
def test_a_parent_that_isnt_a_directory_fails_the_check_and_the_claim_alike(
    tmp_path: Path, parent: str
) -> None:
    if parent == "file":
        (tmp_path / "parent").write_bytes(b"kept\n")
    elif sys.platform == "win32":
        pytest.skip("symbolic links need privileges on Windows")
    else:
        (tmp_path / "parent").symlink_to(tmp_path / "nowhere")
    store = LocalArtifactStore(tmp_path / "parent" / "out")

    with pytest.raises(TrialFolioError) as raised:
        store.check_empty()
    message = claim_fails_with("storage.write_failed", store).message

    assert raised.value.code == "storage.write_failed"
    assert "a parent of it isn't a directory" in raised.value.message
    assert "a parent of it isn't a directory" in message
    assert sorted(os.listdir(tmp_path)) == ["parent"]


def test_claim_needs_its_file_directly_in_the_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="directly"):
        LocalArtifactStore(tmp_path).claim("cases/plan.json", PLAN)

    assert snapshot(tmp_path) == {}


def test_a_store_claims_once(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    store.claim("plan.json", PLAN)

    with pytest.raises(RuntimeError, match="already claimed"):
        store.claim("report.html", b"<!doctype html>\n")


def test_claim_on_macos_ignores_the_apple_double_file_of_its_own_file(
    tmp_path: Path, faults: Faults
) -> None:
    # On FAT and exFAT, macOS creates `._plan.json` with plan.json, to hold its extended
    # attributes. Verified on disk images on macOS 26.6.2. Anywhere else, it's another file.
    faults.on_write("plan.json", lambda: (tmp_path / "._plan.json").write_bytes(b"attributes"))
    store = LocalArtifactStore(tmp_path)

    if sys.platform == "darwin":
        store.claim("plan.json", PLAN)
        assert sorted(os.listdir(tmp_path)) == ["._plan.json", "plan.json"]
    else:
        claim_fails_with("output.not_empty", store)


def test_claim_on_macos_counts_any_other_apple_double_file(tmp_path: Path, faults: Faults) -> None:
    faults.on_write("plan.json", lambda: (tmp_path / "._theirs").write_bytes(b"attributes"))

    claim_fails_with("output.not_empty", LocalArtifactStore(tmp_path))


# Processes released together by a barrier (R01-AC27).

WORKERS = 4
ROUNDS = 25


def claim_in_rounds(
    worker: int, base: str, same_name: bool, barrier: Barrier, results: "Queue[tuple[int, str]]"
) -> None:
    """Claims one new directory each round, as soon as the barrier releases every worker."""
    for round_ in range(ROUNDS):
        store = LocalArtifactStore(Path(base) / f"round-{round_}" / "runs" / "baseline")
        name = "plan.json" if same_name else f"claim-{worker}.json"
        barrier.wait()
        try:
            store.claim(name, f"{worker}\n".encode())
        except TrialFolioError as error:
            results.put((round_, error.code))
        except BaseException as error:  # noqa: BLE001 - reported to the test, which fails on it
            results.put((round_, repr(error)))
        else:
            results.put((round_, f"claimed:{name}"))


@pytest.mark.parametrize("same_name", [True, False], ids=["same-file", "different-files"])
def test_at_most_one_of_several_simultaneous_claims_succeeds(
    tmp_path: Path, same_name: bool
) -> None:
    # The same file is what two runs claim with. Different files, as two different commands
    # would use, exercise the listing: each claim lists the directory only once its file exists.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(WORKERS, timeout=60)
    results: Queue[tuple[int, str]] = context.Queue()
    workers = [
        context.Process(
            target=claim_in_rounds, args=(worker, str(tmp_path), same_name, barrier, results)
        )
        for worker in range(WORKERS)
    ]
    for process in workers:
        process.start()
    outcomes = [results.get(timeout=120) for _ in range(WORKERS * ROUNDS)]
    for process in workers:
        process.join(timeout=60)
        assert process.exitcode == 0

    for round_ in range(ROUNDS):
        round_outcomes = [outcome for number, outcome in outcomes if number == round_]
        claimed = [outcome.removeprefix("claimed:") for outcome in round_outcomes]
        claimed = [name for name in claimed if name.endswith(".json")]
        # Every claim either succeeded or found the directory in use.
        assert sorted(set(round_outcomes) - {f"claimed:{name}" for name in claimed}) in (
            [],
            ["output.not_empty"],
        )
        assert len(claimed) <= 1
        if same_name:
            assert claimed == ["plan.json"]
        # Only the winner's file is left, and no loser's.
        files = {path.name for path in (tmp_path / f"round-{round_}").rglob("*") if path.is_file()}
        assert files == set(claimed)
