"""The local `ArtifactStore` writes atomically, never replaces a file, syncs what it creates, and
takes only relative paths.

Traces to docs/contracts.md, artifact storage (REQ-05): relative paths, immutability, atomic
writes, never replacing, no hard links, and syncing, including new directories and macOS's
fallback from `F_FULLFSYNC`. Also to R01-AC29: a file system without hard links fails the first
atomic write with `storage.write_failed`. And to R01-T14's rule that a manifest whose write failed
leaves no manifest: `discard` removes a file that a failed write published. And to release
0.2.0's labels in logs (docs/contracts.md, review output): a name given for logs replaces a file's
path in the store's log event and its errors' logged messages, and the full messages keep the
path. The claim has its own tests, in test_output_claim.py.
"""

import errno
import hashlib
import logging
import os
import signal
import stat
import sys
from pathlib import Path

import pytest

from tests.core.conftest import Faults, SyncLog, identity, once, raises, snapshot
from trialfolio.errors import TrialFolioError
from trialfolio.storage import LocalArtifactStore, StoredFile

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Linux and macOS behavior")
macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS behavior")


@pytest.fixture
def store(tmp_path: Path) -> LocalArtifactStore:
    """A store that has claimed `tmp_path / "out"` with `plan.json`."""
    claimed = LocalArtifactStore(tmp_path / "out")
    claimed.claim("plan.json", b"{}\n")
    return claimed


def test_write_publishes_the_file_and_returns_its_content_address(
    store: LocalArtifactStore,
) -> None:
    data = b"metric,value\nannual_return,12.3\n"

    stored = store.write("normalized/metrics.csv", data)

    assert stored == StoredFile(
        path="normalized/metrics.csv",
        artifact_id="sha256:" + hashlib.sha256(data).hexdigest(),
        size=len(data),
    )
    assert store.read("normalized/metrics.csv") == data
    # No temporary file is left beside it.
    assert os.listdir(store.root / "normalized") == ["metrics.csv"]


def test_write_keeps_bytes_exactly(store: LocalArtifactStore) -> None:
    # Line endings and non-ASCII text are never translated, on any platform.
    data = "a\r\nb\nCafé\n".encode()

    store.write("configuration.yaml", data)

    assert (store.root / "configuration.yaml").read_bytes() == data


@pytest.mark.parametrize("existing", ["plan.json", "configuration.yaml"])
def test_write_never_replaces_a_file(store: LocalArtifactStore, existing: str) -> None:
    # The claim's own file, and one another process created under the final name.
    if existing != "plan.json":
        (store.root / existing).write_bytes(b"another process's\n")
    before = snapshot(store.root)

    with pytest.raises(TrialFolioError) as raised:
        store.write(existing, b"replacement\n")

    assert raised.value.code == "storage.write_failed"
    assert "already exists" in raised.value.message
    assert "never replaces" in raised.value.message
    assert snapshot(store.root) == before


def test_write_needs_a_claimed_directory(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "out")

    with pytest.raises(RuntimeError, match="claim"):
        store.write("configuration.yaml", b"kind: screen\n")

    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../outside.json",
        "cases/../../outside.json",
        "./plan.json",
        "cases//attempt.json",
        "cases/",
        "cases\\attempt.json",
        "C:attempt.json",
        "cases/attempt\0.json",
    ],
)
def test_paths_must_be_relative_to_the_root(
    store: LocalArtifactStore, tmp_path: Path, path: str
) -> None:
    before = snapshot(tmp_path)

    with pytest.raises(ValueError, match="relative path|inside the output directory"):
        store.write(path, b"x")
    with pytest.raises(ValueError, match="relative path|inside the output directory"):
        store.read(path)
    with pytest.raises(ValueError, match="relative path|inside the output directory"):
        LocalArtifactStore(tmp_path / "other").claim(path, b"x")

    assert snapshot(tmp_path) == before


def test_read_of_a_missing_file_raises_file_not_found(store: LocalArtifactStore) -> None:
    with pytest.raises(FileNotFoundError):
        store.read("cases/case-0123456789abcdef/attempts/missing/attempt.json")


@posix_only
@pytest.mark.parametrize("code", [errno.ENOTSUP, errno.EPERM, errno.ENOSYS])
def test_a_file_system_without_hard_links_fails_the_write(
    store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    # How os.link reports it: ENOTSUP on macOS, verified on exFAT and FAT32 disk images; EPERM on
    # Linux, as link(2) documents; and ENOSYS, which libfuse returns without a link operation.
    def link(source: object, destination: object) -> None:
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(os, "link", link)

    with pytest.raises(TrialFolioError) as raised:
        store.write("configuration.yaml", b"kind: screen\n")

    assert raised.value.code == "storage.write_failed"
    assert "configuration.yaml" in raised.value.message
    assert "doesn't support hard links" in raised.value.message
    # Nothing is published, and the temporary file is gone.
    assert os.listdir(store.root) == ["plan.json"]


@posix_only
def test_permission_errors_are_not_reported_as_missing_hard_links(
    store: LocalArtifactStore, faults: Faults
) -> None:
    # macOS reports EPERM when its privacy protection refuses a file, as link(2) does on Linux for
    # a file system without hard links. Only os.link's error means that.
    faults.on_open("configuration.yaml", raises(PermissionError(errno.EPERM, "Not permitted")))

    with pytest.raises(TrialFolioError) as raised:
        store.write("configuration.yaml", b"kind: screen\n")

    assert raised.value.code == "storage.write_failed"
    assert "hard links" not in raised.value.message
    assert "Not permitted" in raised.value.message


@pytest.mark.parametrize(
    "failure",
    [OSError(errno.ENOSPC, "No space left on device"), KeyboardInterrupt()],
    ids=["disk-full", "interrupt"],
)
def test_a_failed_write_publishes_nothing_and_leaves_no_temporary_file(
    store: LocalArtifactStore, faults: Faults, failure: BaseException
) -> None:
    faults.on_write("response.json", raises(failure))
    directory = "cases/case-0123456789abcdef/attempts/1b4e28ba-2fa1-4d2b-883f-0016d3cca427"

    with pytest.raises(TrialFolioError if isinstance(failure, OSError) else KeyboardInterrupt) as e:
        store.write(f"{directory}/response.json", b"{}\n")

    if isinstance(e.value, TrialFolioError):
        assert e.value.code == "storage.write_failed"
        assert "No space left on device" in e.value.message
    assert os.listdir(store.root / directory) == []


def test_an_interrupt_as_the_temporary_file_is_created_leaves_no_temporary_file(
    store: LocalArtifactStore, faults: Faults
) -> None:
    faults.after_open("configuration.yaml", raises(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        store.write("configuration.yaml", b"kind: screen\n")

    assert os.listdir(store.root) == ["plan.json"]


def test_a_failed_close_of_the_temporary_file_leaves_no_temporary_file(
    store: LocalArtifactStore, faults: Faults
) -> None:
    faults.after_close("configuration.yaml", raises(OSError(errno.EIO, "Input/output error")))

    with pytest.raises(TrialFolioError) as raised:
        store.write("configuration.yaml", b"kind: screen\n")

    assert raised.value.code == "storage.write_failed"
    assert os.listdir(store.root) == ["plan.json"]


@posix_only
def test_an_interrupt_after_publishing_removes_the_temporary_name(
    store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link

    def link_then_interrupt(source: str, destination: str) -> None:
        real_link(source, destination)
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "link", link_then_interrupt)

    with pytest.raises(KeyboardInterrupt):
        store.write("configuration.yaml", b"kind: screen\n")

    # The file was published; only its temporary name is gone.
    assert sorted(os.listdir(store.root)) == ["configuration.yaml", "plan.json"]


@posix_only
def test_a_failed_removal_of_the_temporary_name_fails_the_write(
    store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unlink(path: str) -> None:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(os, "unlink", unlink)

    with pytest.raises(TrialFolioError) as raised:
        store.write("configuration.yaml", b"kind: screen\n")

    assert raised.value.code == "storage.write_failed"
    assert "Input/output error" in raised.value.message


@posix_only
def test_writes_sync_each_new_directory_and_the_parent_of_the_first(
    store: LocalArtifactStore, sync_log: SyncLog
) -> None:
    attempt = (
        store.root / "cases/case-0123456789abcdef/attempts/1b4e28ba-2fa1-4d2b-883f-0016d3cca427"
    )
    relative = attempt.relative_to(store.root).as_posix()

    store.write(f"{relative}/started.json", b"{}\n")

    # The file, each directory created on the way, and the root, which holds the first.
    created = [attempt, *attempt.parents][:4]
    assert [path.name for path in created][-1] == "cases"
    assert sync_log.take() == {
        identity(attempt / "started.json"),
        *(identity(directory) for directory in created),
        identity(store.root),
    }

    store.write(f"{relative}/attempt.json", b"{}\n")

    # Only the new file and the directory that holds it: the others are durable already.
    assert sync_log.take() == {identity(attempt / "attempt.json"), identity(attempt)}


@posix_only
def test_a_directory_left_by_a_failed_write_is_synced_by_the_next_write_under_it(
    store: LocalArtifactStore, sync_log: SyncLog, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link

    def failing_link(source: object, destination: object) -> None:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(os, "link", failing_link)
    with pytest.raises(TrialFolioError):
        store.write("normalized/metrics.csv", b"metric\n")
    monkeypatch.setattr(os, "link", real_link)
    sync_log.take()

    store.write("normalized/settings.csv", b"setting\n")

    normalized = store.root / "normalized"
    assert sync_log.take() == {
        identity(normalized / "settings.csv"),
        identity(normalized),
        identity(store.root),
    }


@posix_only
def test_a_directory_whose_creation_was_interrupted_is_synced_by_the_next_write(
    store: LocalArtifactStore, sync_log: SyncLog, faults: Faults
) -> None:
    attempt = "1b4e28ba-2fa1-4d2b-883f-0016d3cca427"
    relative = f"cases/case-0123456789abcdef/attempts/{attempt}"
    # A real SIGINT must wait until the new directory is recorded for the next write's syncs.
    faults.after_mkdir(attempt, once(lambda: signal.raise_signal(signal.SIGINT)))
    with pytest.raises(KeyboardInterrupt):
        store.write(f"{relative}/started.json", b"{}\n")
    sync_log.take()

    store.write(f"{relative}/attempt.json", b"{}\n")

    # Nothing on the way was synced before, so each new directory's entry is synced now.
    directory = store.root / relative
    assert sync_log.take() == {
        identity(directory / "attempt.json"),
        *(identity(path) for path in [directory, *directory.parents][:4]),
        identity(store.root),
    }


def refuse_directory_syncs(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    """Makes every sync of a directory fail with `code`, as some systems do."""

    def is_directory(descriptor: int) -> bool:
        return stat.S_ISDIR(os.fstat(descriptor).st_mode)

    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        if is_directory(descriptor):
            raise OSError(code, os.strerror(code))
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    if sys.platform == "darwin":
        import fcntl

        real_fcntl = fcntl.fcntl

        def full_sync(descriptor: int, command: int, argument: int = 0) -> int:
            if command == fcntl.F_FULLFSYNC and is_directory(descriptor):
                raise OSError(code, os.strerror(code))
            return real_fcntl(descriptor, command, argument)

        monkeypatch.setattr(fcntl, "fcntl", full_sync)


@posix_only
@pytest.mark.parametrize("code", [errno.EINVAL, errno.EBADF])
def test_a_system_that_cant_sync_a_directory_writes_with_a_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    code: int,
) -> None:
    # PostgreSQL ignores these two for a directory too.
    refuse_directory_syncs(monkeypatch, code)
    store = LocalArtifactStore(tmp_path / "out")

    with caplog.at_level(logging.WARNING, logger="trialfolio.storage"):
        store.claim("plan.json", b"{}\n")
        store.write("normalized/metrics.csv", b"metric\n")

    assert store.read("normalized/metrics.csv") == b"metric\n"
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert [getattr(record, "event", None) for record in warnings] == ["artifact.sync.degraded"]
    assert "can't sync a directory" in warnings[0].getMessage()


@posix_only
def test_any_other_failure_to_sync_a_directory_fails_the_write(
    store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    refuse_directory_syncs(monkeypatch, errno.EIO)

    with pytest.raises(TrialFolioError) as raised:
        store.write("configuration.yaml", b"kind: screen\n")

    assert raised.value.code == "storage.write_failed"
    assert "Input/output error" in raised.value.message


# Discarding a failed write (R01-T14: a manifest whose write failed leaves no manifest)


@posix_only
def test_discard_removes_the_file_a_failed_write_published(
    store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = b'{"outcome": "completed"}\n'
    refuse_directory_syncs(monkeypatch, errno.EIO)
    with pytest.raises(TrialFolioError):
        store.write("manifest.json", data)
    # Only the sync after publishing failed, so the file is there.
    assert (store.root / "manifest.json").read_bytes() == data

    # Its own directory sync fails too, which doesn't fail the removal.
    store.discard("manifest.json", data)

    assert os.listdir(store.root) == ["plan.json"]


def test_discard_leaves_another_file_and_a_missing_one_alone(store: LocalArtifactStore) -> None:
    (store.root / "manifest.json").write_bytes(b"another process's\n")
    before = snapshot(store.root)

    store.discard("manifest.json", b"this write's\n")
    store.discard("report.html", b"this write's\n")

    assert snapshot(store.root) == before


@posix_only
def test_a_failed_removal_fails_the_discard(
    store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = b"{}\n"
    store.write("manifest.json", data)

    def unlink(path: str) -> None:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(os, "unlink", unlink)

    with pytest.raises(TrialFolioError) as raised:
        store.discard("manifest.json", data)

    assert raised.value.code == "storage.write_failed"
    assert "Input/output error" in raised.value.message
    assert (store.root / "manifest.json").read_bytes() == data


def test_discard_needs_a_claimed_directory(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "out")

    with pytest.raises(RuntimeError):
        store.discard("manifest.json", b"{}\n")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows behavior")
def test_windows_syncs_files_only(store: LocalArtifactStore, sync_log: SyncLog) -> None:
    # Python can't open a directory on Windows (docs/contracts.md, syncing).
    store.write("normalized/metrics.csv", b"metric\n")

    assert sync_log.take() == {identity(store.root / "normalized/metrics.csv")}


@macos_only
@pytest.mark.parametrize("code", [errno.ENOTSUP, errno.ENODEV])
def test_macos_falls_back_to_fsync_without_a_full_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    code: int,
) -> None:
    # ENODEV is what devfs reports, verified on macOS 26.6.2, and ENOTSUP what Go's os package
    # reports for SMB mounts.
    import fcntl

    real_fcntl = fcntl.fcntl

    def no_full_sync(descriptor: int, command: int, argument: int = 0) -> int:
        if command == fcntl.F_FULLFSYNC:
            raise OSError(code, os.strerror(code))
        return real_fcntl(descriptor, command, argument)

    synced: list[int] = []
    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        synced.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(fcntl, "fcntl", no_full_sync)
    monkeypatch.setattr(os, "fsync", fsync)
    store = LocalArtifactStore(tmp_path / "out")

    with caplog.at_level(logging.WARNING, logger="trialfolio.storage"):
        store.claim("plan.json", b"{}\n")
        store.write("normalized/metrics.csv", b"metric\n")
        store.write("normalized/settings.csv", b"setting\n")

    assert store.read("normalized/settings.csv") == b"setting\n"
    assert synced  # Each sync fell back to fsync.
    # One warning for the directory, not one for each write.
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert [getattr(record, "event", None) for record in warnings] == ["artifact.sync.degraded"]
    assert "less durable" in warnings[0].getMessage()


@macos_only
def test_macos_fails_the_write_when_a_full_sync_fails_otherwise(
    store: LocalArtifactStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An I/O error isn't a missing feature: a fallback fsync could hide it.
    import fcntl

    real_fcntl = fcntl.fcntl

    def failing_full_sync(descriptor: int, command: int, argument: int = 0) -> int:
        if command == fcntl.F_FULLFSYNC:
            raise OSError(errno.EIO, "Input/output error")
        return real_fcntl(descriptor, command, argument)

    monkeypatch.setattr(fcntl, "fcntl", failing_full_sync)

    with pytest.raises(TrialFolioError) as raised:
        store.write("configuration.yaml", b"kind: screen\n")

    assert raised.value.code == "storage.write_failed"
    assert "Input/output error" in raised.value.message
    assert os.listdir(store.root) == ["plan.json"]


# Names in logs (release 0.2.0, R02-T08)

COPY = "inputs/hold50/normalized/metrics.csv"
"""A review's copy, whose path holds its result's label, `hold50`, a configuration value."""
COPY_LOGGED = "normalized/metrics.csv of result 2"


def test_a_name_for_logs_replaces_the_path_in_the_write_event(
    store: LocalArtifactStore, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="trialfolio.storage"):
        stored = store.write(COPY, b"metric\n", logged_as=COPY_LOGGED)
        default = store.write("normalized/differences.csv", b"kind\n")

    assert stored.path == COPY
    assert store.read(COPY) == b"metric\n"
    events = [
        record.getMessage()
        for record in caplog.records
        if getattr(record, "event", None) == "artifact.write.completed"
    ]
    assert events == [
        f"Wrote {COPY_LOGGED} ({stored.artifact_id}).",
        f"Wrote normalized/differences.csv ({default.artifact_id}).",
    ]


def _disk_full(store: LocalArtifactStore, faults: Faults, monkeypatch: pytest.MonkeyPatch) -> None:
    faults.on_open("metrics.csv", raises(OSError(errno.ENOSPC, "No space left on device")))


def _exists(store: LocalArtifactStore, faults: Faults, monkeypatch: pytest.MonkeyPatch) -> None:
    (store.root / "inputs" / "hold50" / "normalized").mkdir(parents=True)
    (store.root / COPY).write_bytes(b"another process's\n")


def _no_hard_links(
    store: LocalArtifactStore, faults: Faults, monkeypatch: pytest.MonkeyPatch
) -> None:
    def link(source: object, destination: object) -> None:
        raise OSError(errno.ENOTSUP, os.strerror(errno.ENOTSUP))

    monkeypatch.setattr(os, "link", link)


FAILURES = {
    "disk-full": (_disk_full, "durably: No space left on device"),
    "exists": (_exists, "a file with that name already exists"),
    "no-hard-links": (_no_hard_links, "doesn't support hard links"),
}


@pytest.mark.parametrize("failure", FAILURES)
def test_a_name_for_logs_replaces_the_path_in_the_errors_logged_message(
    store: LocalArtifactStore, faults: Faults, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    if failure == "no-hard-links" and sys.platform == "win32":
        pytest.skip("Windows publishes files by renaming them")
    cause, problem = FAILURES[failure]
    cause(store, faults, monkeypatch)

    with pytest.raises(TrialFolioError) as raised:
        store.write(COPY, b"metric\n", logged_as=COPY_LOGGED)

    error = raised.value
    assert error.code == "storage.write_failed"
    # The terminal's message names the file by its path; the logged one never holds the label.
    assert f"Couldn't write {COPY}" in error.message
    assert problem in error.message
    assert f"Couldn't write {COPY_LOGGED}" in error.log_message
    assert problem in error.log_message
    assert "hold50" not in error.log_message
    assert str(error) == error.log_message
