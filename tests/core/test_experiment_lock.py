"""The experiment lock: an experiment's claim takes it on `experiment.lock`, a resumed one on the
existing file, and the store holds it until it's closed, or its process ends.

Traces to docs/contracts.md, the lock, and claiming the directory; and to R03-AC09, of which this
module is the core part: the store holds the lock until it's closed, `experiment.lock` holds its
one line, another holder gets `experiment.locked`, and a refused lock, other than one another
process holds, gives `storage.write_failed` before any record is written. The lock is the real
`flock` (or `msvcrt.locking` on Windows); only a lock the file system refuses is injected, at
`fcntl.flock`, a storage boundary.
"""

import errno
import multiprocessing
import os
import signal
import sys
from multiprocessing.queues import Queue
from pathlib import Path

import pytest

from tests.core.conftest import snapshot
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution import LOCK_LINE, LOCK_PATH
from trialfolio.storage import LocalArtifactStore


def held_elsewhere(root: Path) -> str:
    """What another store gets when it tries to take the lock on `root`'s `experiment.lock`."""
    other = LocalArtifactStore(root)
    try:
        other.lock(LOCK_PATH)
    except TrialFolioError as error:
        return error.code
    other.close()
    return "acquired"


def test_a_claim_with_the_lock_holds_it_until_the_store_is_closed(tmp_path: Path) -> None:
    out = tmp_path / "out"
    store = LocalArtifactStore(out)

    store.claim(LOCK_PATH, LOCK_LINE, lock=True)

    assert snapshot(out) == {LOCK_PATH: LOCK_LINE}
    assert LOCK_LINE.count(b"\n") == 1 and LOCK_LINE.endswith(b"\n")
    assert held_elsewhere(out) == "experiment.locked"
    store.write("sessions/1/session.json", b"{}\n")  # the claim lets it write
    store.close()
    assert held_elsewhere(out) == "acquired"


def test_a_resumed_store_takes_the_lock_on_the_existing_file(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with LocalArtifactStore(out) as first:
        first.claim(LOCK_PATH, LOCK_LINE, lock=True)
    before = snapshot(out)

    with LocalArtifactStore(out) as resumed:
        resumed.lock(LOCK_PATH)
        assert held_elsewhere(out) == "experiment.locked"
        resumed.write("sessions/1/session.json", b"{}\n")  # it owns the directory now

    assert held_elsewhere(out) == "acquired"
    assert snapshot(out)[LOCK_PATH] == before[LOCK_PATH]


def test_another_holder_refuses_the_lock_and_leaves_the_directory_as_it_was(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    with LocalArtifactStore(out) as holder:
        holder.claim(LOCK_PATH, LOCK_LINE, lock=True)
        before = snapshot(out)
        other = LocalArtifactStore(out)

        with pytest.raises(TrialFolioError) as raised:
            other.lock(LOCK_PATH)

        assert raised.value.code == "experiment.locked"
        assert "Nothing was sent" in raised.value.message
        with pytest.raises(RuntimeError):
            other.write("sessions/1/session.json", b"{}\n")
        assert snapshot(out) == before


def test_a_missing_lock_file_is_left_to_the_caller(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_bytes(b"kept\n")

    with pytest.raises(FileNotFoundError):
        LocalArtifactStore(tmp_path).lock(LOCK_PATH)

    assert snapshot(tmp_path) == {"notes.txt": b"kept\n"}


def hold_the_lock(root: str, ready: "Queue[str]") -> None:
    """Takes the lock on `root`'s `experiment.lock`, says so, and waits to be killed."""
    store = LocalArtifactStore(root)
    try:
        store.lock(LOCK_PATH)
    except TrialFolioError as error:
        ready.put(error.code)
        return
    ready.put("held")
    signal.pause()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no SIGKILL")
def test_another_process_holding_the_lock_refuses_it_until_it_is_killed(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with LocalArtifactStore(out) as first:
        first.claim(LOCK_PATH, LOCK_LINE, lock=True)
    context = multiprocessing.get_context("spawn")
    ready: Queue[str] = context.Queue()
    holder = context.Process(target=hold_the_lock, args=(str(out), ready))
    holder.start()
    try:
        assert ready.get(timeout=60) == "held"
        assert held_elsewhere(out) == "experiment.locked"
    finally:
        os.kill(holder.pid or 0, signal.SIGKILL)
        holder.join(timeout=60)

    # The operating system released it with the process: no stale lock.
    assert held_elsewhere(out) == "acquired"


# A lock the file system refuses


@pytest.fixture
def refused_lock(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Makes `fcntl.flock` fail with the errno the test appends, as a file system that refuses
    locks would; once the list is empty, it locks as usual."""
    if sys.platform == "win32":
        pytest.skip("Windows locks with msvcrt.locking")
    import fcntl

    errors: list[int] = []
    real_flock = fcntl.flock

    def flock(descriptor: int, operation: int) -> None:
        if errors:
            code = errors.pop(0)
            raise OSError(code, os.strerror(code))
        real_flock(descriptor, operation)

    monkeypatch.setattr(fcntl, "flock", flock)
    return errors


@pytest.mark.parametrize("code", [errno.ENOLCK, errno.EOPNOTSUPP, errno.EINVAL])
def test_a_refused_lock_fails_the_claim_and_leaves_nothing(
    tmp_path: Path, refused_lock: list[int], code: int
) -> None:
    refused_lock.append(code)
    out = tmp_path / "runs" / "out"

    with pytest.raises(TrialFolioError) as raised:
        LocalArtifactStore(out).claim(LOCK_PATH, LOCK_LINE, lock=True)

    assert raised.value.code == "storage.write_failed"
    assert "refused it" in raised.value.message
    assert os.strerror(code) in raised.value.message
    assert snapshot(tmp_path) == {}


def test_a_lock_held_at_the_claim_is_experiment_locked_and_leaves_nothing(
    tmp_path: Path, refused_lock: list[int]
) -> None:
    refused_lock.append(errno.EWOULDBLOCK)

    with pytest.raises(TrialFolioError) as raised:
        LocalArtifactStore(tmp_path / "out").claim(LOCK_PATH, LOCK_LINE, lock=True)

    assert raised.value.code == "experiment.locked"
    assert snapshot(tmp_path) == {}


def test_a_refused_lock_on_resume_writes_nothing(tmp_path: Path, refused_lock: list[int]) -> None:
    out = tmp_path / "out"
    with LocalArtifactStore(out) as first:
        first.claim(LOCK_PATH, LOCK_LINE, lock=True)
    before = snapshot(out)
    refused_lock.append(errno.ENOLCK)
    resumed = LocalArtifactStore(out)

    with pytest.raises(TrialFolioError) as raised:
        resumed.lock(LOCK_PATH)

    assert raised.value.code == "storage.write_failed"
    with pytest.raises(RuntimeError):
        resumed.write("sessions/1/session.json", b"{}\n")
    assert snapshot(out) == before
    assert held_elsewhere(out) == "acquired"  # the failed attempt holds nothing


def test_a_claim_that_fails_after_taking_the_lock_releases_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    real_write = os.write

    def interrupted(descriptor: int, data: bytes | memoryview) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "write", interrupted)
    with pytest.raises(KeyboardInterrupt):
        LocalArtifactStore(out).claim(LOCK_PATH, LOCK_LINE, lock=True)
    monkeypatch.setattr(os, "write", real_write)

    assert snapshot(tmp_path) == {}
    with LocalArtifactStore(out) as again:
        again.claim(LOCK_PATH, LOCK_LINE, lock=True)
        assert held_elsewhere(out) == "experiment.locked"
