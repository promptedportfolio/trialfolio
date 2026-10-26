"""The platform's primitives that the local artifact store builds on (docs/contracts.md, artifact
storage): publishing a file under its final name without replacing one, syncing files and
directories as durably as the platform allows, a lock taken without waiting, and deferring SIGINT
while a creation's ownership is recorded. Each says what Linux, macOS, and Windows do, and what
Trial Folio does on each.

`trialfolio.storage`'s `LocalArtifactStore` uses them. So does the ranking lock
(`trialfolio.ranking_lock`), which takes and releases its lock as the experiment lock is taken
and released, in its own words. Nothing here logs: a sync that's less durable than it should be
is told to its caller, as the sentence that says why, and the store logs it, once for each output
directory, under `trialfolio.storage`'s name.

R01-T08 checked what each platform reports, on macOS 26.6.2 with Python 3.12.13:

- `os.link` on exFAT and FAT32 disk images fails with `ENOTSUP`, "Operation not supported".
- `F_FULLFSYNC` works on APFS, exFAT, and FAT32, for files and directories. devfs reports
  `ENODEV`, "Operation not supported by device". Go's `os` package falls back to `fsync` on
  `ENOTSUP`, which it reports SMB mounts give (golang/go#64215). Trial Folio falls back on those
  two, and treats any other error as a failed write.
- macOS keeps a file's extended attributes on FAT and exFAT in an AppleDouble file named `._`
  plus the file's name, created with the file and removed with it.
- On FAT and exFAT, macOS gives each new, empty file a temporary inode of its own, counted down
  from 2**64 for each mount, until its first write gives it a lasting one. A write that failed
  with `ENOSPC`, and wrote nothing, gave the empty file another temporary inode, and so did
  mounting the volume again. A walk-through of the user guide found on 2026-10-04, on macOS
  26.6.2, that the claim had read its file's identity before writing it, so every claim there
  failed with `output.not_empty`. It now reads it once the file is written, or once writing it
  failed. PR #30's review checked these inodes on disk images the same day.
- R03-T08 tried the experiment lock on APFS, exFAT, and FAT32 disk images on macOS 26.6.2, with
  Python 3.14.6, on 2026-10-09. Each took the lock on the new, empty file's descriptor, and
  refused a second one, from another descriptor of the same process or from another process, with
  `EAGAIN` ("Resource temporarily unavailable"), which is `EWOULDBLOCK` there. Closing the
  descriptor released it, and so did killing its process with `SIGKILL`.
- On Windows, from CPython 3.12.13's source and Microsoft's documentation: `os.open` calls
  `_wopen`, which fails with `EACCES` for a directory; `os.fsync` calls `_commit`, which takes a
  file descriptor; and `os.rename` calls `MoveFileExW` with no flags, so it fails if the name
  exists, and doesn't ask for `MOVEFILE_WRITE_THROUGH`.
"""

import errno
import os
import signal
import sys
import threading
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager, suppress
from pathlib import Path
from types import FrameType
from typing import Final

from trialfolio.errors import TrialFolioError, reason_of

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

type Degraded = Callable[[str], None]
"""Told, with the sentence that says why, each time a sync is less durable than it should be."""

BINARY: Final[int] = getattr(os, "O_BINARY", 0)
"""Windows translates line endings without this flag."""

_NO_FULL_SYNC: Final = frozenset({errno.ENOTSUP, errno.ENODEV})
"""How macOS reports a file system without `F_FULLFSYNC`. Any other error is a failed sync."""

_NO_DIRECTORY_SYNC: Final = frozenset({errno.EBADF, errno.EINVAL})
"""How a system that can't sync a directory reports it. PostgreSQL's `fsync_fname_ext` ignores the
same two for a directory."""

_NO_HARD_LINKS: Final = frozenset({errno.ENOTSUP, errno.EPERM, errno.ENOSYS})
"""How `os.link` reports a file system without hard links: `ENOTSUP` on macOS; `EPERM` on Linux,
as link(2) documents; and `ENOSYS`, which libfuse returns for a file system without a link
operation."""

_LOCK_HELD: Final = (
    frozenset({errno.EACCES})
    if sys.platform == "win32"
    else frozenset({errno.EAGAIN, errno.EWOULDBLOCK})
)
"""How taking a lock without waiting reports that another process holds it: `EWOULDBLOCK`, which
is `EAGAIN` on Linux and macOS, from `flock`, and `EACCES` from `msvcrt.locking` on Windows,
whose C runtime documents it as a locking violation. Any other error refuses the lock, `EACCES`
from `flock` included."""

_APPLE_DOUBLE: Final = "._"
"""The prefix of the file that holds another file's extended attributes on macOS, where the file
system can't."""

_NO_FULL_SYNC_WARNING: Final = (
    "The output directory's file system doesn't support a full sync (F_FULLFSYNC), so Trial"
    " Folio syncs with fsync, which doesn't flush the drive's cache. The files written there are"
    " less durable after a power loss."
)
_NO_DIRECTORY_SYNC_WARNING: Final = (
    "The output directory's file system can't sync a directory, so the entries of the files"
    " written there may be lost after a power loss."
)


def publish(temporary: Path, final: Path, path: str, logged: str) -> None:
    """Gives the temporary file its final name, never replacing a file. An error's message names
    the file by `path`, and its logged message by `logged`."""
    try:
        if sys.platform == "win32":
            os.rename(temporary, final)
        else:
            os.link(temporary, final)
    except FileExistsError as error:

        def exists(name: str) -> str:
            return (
                f"Couldn't write {name}: a file with that name already exists in the output"
                " directory, and Trial Folio never replaces a file."
            )

        raise TrialFolioError("storage.write_failed", exists(path), exists(logged)) from error
    except OSError as error:
        if sys.platform == "win32" or error.errno not in _NO_HARD_LINKS:
            raise
        reason = reason_of(error)

        def no_links(name: str) -> str:
            return (
                f"Couldn't write {name}: the output directory's file system doesn't support hard"
                f" links ({reason}). FAT and exFAT don't. Trial Folio publishes each file"
                " with a hard link, so that it never replaces one. Choose an output directory on"
                " another file system."
            )

        raise TrialFolioError("storage.write_failed", no_links(path), no_links(logged)) from error


def sync(descriptor: int, degraded: Degraded) -> None:
    """Syncs the file or directory `descriptor` holds open: on macOS with `F_FULLFSYNC`, since
    `fsync` doesn't flush the drive's cache there, and with `fsync` elsewhere, or on macOS where
    the file system doesn't support a full sync, which it tells `degraded`."""
    if sys.platform == "darwin":
        try:
            fcntl.fcntl(descriptor, fcntl.F_FULLFSYNC)
        except OSError as error:
            if error.errno not in _NO_FULL_SYNC:
                raise
            degraded(_NO_FULL_SYNC_WARNING)
        else:
            return
    os.fsync(descriptor)


def sync_directories(directories: Iterable[Path], degraded: Degraded) -> None:
    """Syncs each directory, deepest first, each once, so the entries in it are durable. On
    Windows it does nothing, since Python can't open a directory there. A system that can't sync
    a directory is told to `degraded`, and any other error raised."""
    if sys.platform == "win32":
        return  # Python can't open a directory on Windows.
    # Deepest first, each once.
    for directory in sorted(set(directories), key=lambda path: len(path.parts), reverse=True):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            sync(descriptor, degraded)
        except OSError as error:
            if error.errno not in _NO_DIRECTORY_SYNC:
                raise
            degraded(_NO_DIRECTORY_SYNC_WARNING)
        finally:
            os.close(descriptor)


def lock_without_waiting(descriptor: int) -> None:
    """Takes a lock on the file `descriptor` holds open, without waiting: an exclusive `flock` on
    Linux and macOS, which a process loses only when every descriptor of its open file is closed,
    and `msvcrt.locking` on the file's first byte on Windows. Raises the `OSError` the platform
    gives when it can't, which `lock_held` reads."""
    if sys.platform == "win32":
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def lock_held(error: OSError) -> bool:
    """Whether `error`, from `lock_without_waiting`, says that another process holds the lock,
    rather than that the file system refuses it."""
    return error.errno in _LOCK_HELD


def take_lock(descriptor: int, name: str) -> None:
    """Takes the experiment lock on `descriptor`, without waiting, as `lock_without_waiting`
    takes a lock (docs/contracts.md, the lock).

    Raises `TrialFolioError` with `experiment.locked` if another process holds it, and with
    `storage.write_failed` if the file system refuses it for any other reason.
    """
    try:
        lock_without_waiting(descriptor)
    except OSError as error:
        if lock_held(error):
            raise TrialFolioError(
                "experiment.locked",
                f"Another process is running this experiment: it holds the experiment lock,"
                f" {name}, in the output directory. Nothing was sent, and nothing was written."
                " Wait for it to end, then run the command again.",
            ) from error
        raise TrialFolioError(
            "storage.write_failed",
            f"Couldn't take the experiment lock, {name}: the output directory's file system"
            f" refused it ({reason_of(error)}). Trial Folio locks an experiment's directory so"
            " that only one process runs it at a time. Choose an output directory on another"
            " file system. Nothing was sent.",
        ) from error


def release_lock(descriptor: int) -> None:
    """Releases the lock that `descriptor` holds, the experiment lock or the ranking lock, and
    closes it. On Windows, it first unlocks the file's first byte, as Microsoft's `_locking`
    documentation asks before a file is closed: the system releases a lock left at close only when
    its resources allow, so the lock's owner could find it still held. `msvcrt.locking` unlocks
    from the file's position, which writing the claim's line moved. Closing releases `flock`'s
    lock on Linux and macOS. Errors are ignored, since closing the descriptor releases the lock
    either way."""
    if sys.platform == "win32":
        with suppress(OSError):
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
    with suppress(OSError):
        os.close(descriptor)


def part_of_claim(name: str, claimed: str) -> bool:
    """Whether a name in a directory being claimed is the claim's own file, `claimed`. On macOS,
    that includes the AppleDouble file it gets on FAT or exFAT."""
    if sys.platform == "darwin" and name == _APPLE_DOUBLE + claimed:
        return True
    return name == claimed


@contextmanager
def defer_sigint() -> Generator[None, None, None]:
    """Delays a callable SIGINT handler until a creation's ownership has been recorded.

    Python delivers signal handlers only in the main thread. Workers therefore need no handler
    changes; ignored or default OS dispositions are left alone too. Restore the caller's handler
    before delivering a pending interrupt, including when the protected operation failed.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGINT)
    if not callable(previous):
        yield
        return
    pending: tuple[int, FrameType | None] | None = None

    def defer(signum: int, frame: FrameType | None) -> None:
        nonlocal pending
        pending = (signum, frame)

    try:
        signal.signal(signal.SIGINT, defer)
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
        if pending is not None:
            previous(*pending)
