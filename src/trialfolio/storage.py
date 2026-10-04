"""The artifact store: every artifact read and write goes through it (docs/contracts.md, artifact
storage; REQ-05; ADR 0003).

`ArtifactStore` is the protocol, and `LocalArtifactStore` its local filesystem implementation.
A store serves one output directory, its root, and takes paths relative to it.

- **Claiming.** A command claims a new output directory with its first file, created directly
  under its final name, and writes nothing else into a directory it hasn't claimed
  (docs/contracts.md, CLI behavior).
- **Atomic writes.** Every other file is written to a temporary name in its directory, synced,
  and published under its final name without replacing anything: with `os.link` on Linux and
  macOS, where `os.rename` would replace a file silently, and with `os.rename` on Windows, where
  it fails if the name exists.
- **Syncing.** A file is synced before it's published. On Linux and macOS, the directory that
  holds it is synced after, and so is the parent of each directory the store created on the way,
  so a new directory's entry is durable too. On macOS, a sync is `fcntl.F_FULLFSYNC`, because
  `fsync` doesn't flush the drive's cache there. Windows syncs files only: Python can't open a
  directory there.
- **Interrupts.** SIGINT is deferred during creation and ownership bookkeeping. Cleanup uses
  successful exclusive creation and file identity, never an empty file as a guess at ownership.
- **Discarding.** A write can fail after it has published its file. `discard` removes that file,
  when it holds exactly the write's bytes, for a caller whose file says something by being
  there, such as the manifest.

R01-T08 checked what each platform reports, on macOS 26.6.2 with Python 3.12.13:

- `os.link` on exFAT and FAT32 disk images fails with `ENOTSUP`, "Operation not supported".
- `F_FULLFSYNC` works on APFS, exFAT, and FAT32, for files and directories. devfs reports
  `ENODEV`, "Operation not supported by device". Go's `os` package falls back to `fsync` on
  `ENOTSUP`, which it reports SMB mounts give (golang/go#64215). Trial Folio falls back on those
  two, and treats any other error as a failed write.
- macOS keeps a file's extended attributes on FAT and exFAT in an AppleDouble file named `._`
  plus the file's name, created with the file and removed with it.
- On Windows, from CPython 3.12.13's source and Microsoft's documentation: `os.open` calls
  `_wopen`, which fails with `EACCES` for a directory; `os.fsync` calls `_commit`, which takes a
  file descriptor; and `os.rename` calls `MoveFileExW` with no flags, so it fails if the name
  exists, and doesn't ask for `MOVEFILE_WRITE_THROUGH`.
"""

import errno
import hashlib
import logging
import os
import secrets
import signal
import sys
import threading
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Final, NoReturn, Protocol

from trialfolio.contracts.common import valid_relative_path
from trialfolio.errors import TrialFolioError

if sys.platform == "darwin":
    import fcntl

_logger = logging.getLogger(__name__)

_NO_FULL_SYNC: Final = frozenset({errno.ENOTSUP, errno.ENODEV})
"""How macOS reports a file system without `F_FULLFSYNC`. Any other error is a failed sync."""

_NO_DIRECTORY_SYNC: Final = frozenset({errno.EBADF, errno.EINVAL})
"""How a system that can't sync a directory reports it. PostgreSQL's `fsync_fname_ext` ignores the
same two for a directory."""

_NO_HARD_LINKS: Final = frozenset({errno.ENOTSUP, errno.EPERM, errno.ENOSYS})
"""How `os.link` reports a file system without hard links: `ENOTSUP` on macOS; `EPERM` on Linux,
as link(2) documents; and `ENOSYS`, which libfuse returns for a file system without a link
operation."""

_APPLE_DOUBLE: Final = "._"
"""The prefix of the file that holds another file's extended attributes on macOS, where the file
system can't."""

_MODE: Final = 0o666
"""The mode new files are created with, before the umask."""

_BINARY: Final[int] = getattr(os, "O_BINARY", 0)
"""Windows translates line endings without this flag."""

_NO_FULL_SYNC_WARNING: Final = (
    "The output directory's file system doesn't support a full sync (F_FULLFSYNC), so Trial"
    " Folio syncs with fsync, which doesn't flush the drive's cache. The files written there are"
    " less durable after a power loss."
)
_NO_DIRECTORY_SYNC_WARNING: Final = (
    "The output directory's file system can't sync a directory, so the entries of the files"
    " written there may be lost after a power loss."
)


@dataclass(frozen=True, slots=True)
class StoredFile:
    """A file the store wrote, as the manifest lists it."""

    path: str
    """Relative to the output root, with `/` separators."""
    artifact_id: str
    """`sha256:` and the hex SHA-256 of the file's bytes."""
    size: int
    """In bytes."""


class ArtifactStore(Protocol):
    """Persists and reads one output directory's artifacts by relative path.

    Paths are relative to the store's root, with `/` separators, as `valid_relative_path`
    defines them; any other path raises `ValueError`. No file is ever replaced or changed once
    it's written.
    """

    def check_empty(self) -> None:
        """Checks, without creating anything, that the root is absent or an empty directory.

        Raises `TrialFolioError` with `output.not_empty` if it holds anything, hidden files
        included, or exists and isn't a directory; and with `storage.write_failed` if it can't be
        created, because a parent isn't a directory or none exists, or can't be read.
        """
        ...

    def claim(self, path: str, data: bytes) -> StoredFile:
        """Claims the root for this store with its first file, and returns it.

        First checks the root as `check_empty` does, apart from listing it. Then creates the
        root, and any missing parent directories, one at a time. Then creates the file, which
        must be directly in the root, under its final name with an exclusive create, writes and
        syncs it, and lists the root. On success, the file and the directories' entries are
        durable, and the store can `write`.

        Raises `TrialFolioError` with `output.not_empty` if the file existed already, the root
        holds anything else, or the root or a parent disappeared; and with `storage.write_failed`
        if the root can't be created, or a write or sync fails. On any failure, an interrupt
        included, it removes what it created: its file, then the directories it created, deepest
        first, each only while it's empty.
        """
        ...

    def write(self, path: str, data: bytes) -> StoredFile:
        """Writes a new file atomically and durably, and returns it.

        Creates any missing directories on the way. The file is published under its final name
        complete, or not at all. When this returns, the file and the entries of the directories
        the store created are durable, as far as the platform allows.

        Raises `RuntimeError` before the store has claimed its root, and `TrialFolioError` with
        `storage.write_failed` if the name exists, the file system can't take an atomic write
        that never replaces a file, or any write or sync fails. A failed write leaves no
        temporary file, unless removing it failed too. It publishes nothing, unless only the
        steps after publishing failed: the file is then complete, but may not survive a power
        loss.
        """
        ...

    def discard(self, path: str, data: bytes) -> None:
        """Undoes a failed `write` of `data` to `path`, which may have published the file before
        a later step failed: removes the file if it holds exactly `data`.

        It's for a file whose presence alone says something, such as the manifest, which says
        the run is complete, so that a failed write leaves no such file. A missing file, and one
        with other bytes, are left as they are. SIGINT is deferred while it reads and removes
        the file.

        Raises `RuntimeError` before the store has claimed its root, and `TrialFolioError` with
        `storage.write_failed` if the file can't be read or removed.
        """
        ...

    def read(self, path: str) -> bytes:
        """Returns the bytes of a file under the root.

        Raises `FileNotFoundError` if there's none, and `OSError` if it can't be read.
        """
        ...


class LocalArtifactStore:
    """An `ArtifactStore` for a directory on a local file system.

    On Linux and macOS, the file system must support hard links, which FAT and exFAT don't.
    """

    def __init__(self, root: str | os.PathLike[str]) -> None:
        # abspath also resolves `..` segments, so a claim never creates a directory that's only
        # on the way to `..`.
        self._root = Path(os.path.abspath(root))
        self._claimed = False
        self._unsynced: list[Path] = []
        """Directories this store created whose entry in their parent isn't synced."""
        self._warned: set[str] = set()

    @property
    def root(self) -> Path:
        """The output directory, as an absolute path."""
        return self._root

    def check_empty(self) -> None:
        if not self._check_root():
            return
        try:
            with os.scandir(self._root) as entries:
                occupied = next(entries, None) is not None
        except FileNotFoundError:
            return
        except OSError as error:
            raise TrialFolioError(
                "storage.write_failed",
                f"Couldn't read the output directory: {_reason(error)}. Check its permissions.",
            ) from error
        if occupied:
            _not_empty("The output directory isn't empty.")

    def claim(self, path: str, data: bytes) -> StoredFile:
        if "/" in valid_relative_path(path):
            raise ValueError("the file that claims a directory must be directly in it")
        if self._claimed:
            raise RuntimeError("this store has already claimed its directory")
        self._check_root()
        claim = _Claim(self._root / path)
        try:
            self._claim(claim, data)
        except BaseException as error:
            claim.undo()
            if isinstance(error, OSError):
                raise TrialFolioError(
                    "storage.write_failed",
                    f"Couldn't claim the output directory with {path}: {_reason(error)}. Check"
                    " its free space and permissions.",
                ) from error
            raise
        self._claimed = True
        return _stored(path, data)

    def write(self, path: str, data: bytes) -> StoredFile:
        parts = valid_relative_path(path).split("/")
        if not self._claimed:
            raise RuntimeError("claim the output directory before writing to it")
        directory = self._root.joinpath(*parts[:-1])
        final = directory / parts[-1]
        # Unique, so that it's safe to remove whatever has this name; hidden, so that a crash
        # leaves a name no artifact has.
        temporary: Path | None = directory / f".{parts[-1]}.{secrets.token_hex(8)}.tmp"
        try:
            _make_directories(directory, self._unsynced, stop=self._root)
            self._write_new(temporary, data)
            _publish(temporary, final, path)
            if sys.platform != "win32":
                os.unlink(temporary)
            temporary = None
            self._sync_new_entries(final)
        except OSError as error:
            raise TrialFolioError(
                "storage.write_failed",
                f"Couldn't write {path} durably: {_reason(error)}. Check the output directory's"
                " free space and permissions.",
            ) from error
        finally:
            if temporary is not None:
                _remove(temporary)
        stored = _stored(path, data)
        _logger.debug(
            "Wrote %s (%s).",
            stored.path,
            stored.artifact_id,
            extra={"event": "artifact.write.completed"},
        )
        return stored

    def discard(self, path: str, data: bytes) -> None:
        parts = valid_relative_path(path).split("/")
        if not self._claimed:
            raise RuntimeError("claim the output directory before writing to it")
        final = self._root.joinpath(*parts)
        try:
            with _defer_sigint():
                try:
                    if final.read_bytes() != data:
                        return  # Another file: not this write's to remove.
                    os.unlink(final)
                except FileNotFoundError:
                    return  # Never published.
        except OSError as error:
            raise TrialFolioError(
                "storage.write_failed",
                f"Couldn't remove {path}, which a failed write may have left: {_reason(error)}.",
            ) from error
        try:
            self._sync_directories([final.parent])
        except OSError:
            pass  # The file is gone either way, and the failure being reported matters more.

    def read(self, path: str) -> bytes:
        # Reads follow symbolic links, as any file read does. The manifest's hashes, not the
        # store, detect a file that changed.
        return self._root.joinpath(*valid_relative_path(path).split("/")).read_bytes()

    def _check_root(self) -> bool:
        """Raises unless the root is a directory, or can be created as one. Returns whether it
        exists."""
        if os.path.lexists(self._root):
            if not os.path.isdir(self._root):
                # Including a symbolic link to nothing.
                _not_empty("The output path exists and isn't a directory.")
            return True
        for parent in self._root.parents:
            if os.path.lexists(parent):
                if os.path.isdir(parent):
                    return False
                raise TrialFolioError(
                    "storage.write_failed",
                    "The output directory can't be created: a parent of it isn't a directory."
                    " Choose another output directory.",
                )
        raise TrialFolioError(
            "storage.write_failed",
            "The output directory can't be created: none of its parent directories exists."
            " Check the drive or share it's on.",
        )

    def _claim(self, claim: "_Claim", data: bytes) -> None:
        try:
            new = _make_directories(self._root, claim.directories)
        except FileNotFoundError:
            # _check_root found a parent, so it disappeared, because a competing claim that
            # created it failed and removed it.
            _not_empty("The output directory disappeared while Trial Folio claimed it.")
        descriptor: int | None = None
        try:
            try:
                with _defer_sigint():
                    descriptor = os.open(
                        claim.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, _MODE
                    )
                    claim.file = os.fstat(descriptor)
            except FileExistsError:
                _not_empty("The output directory isn't empty.")
            except FileNotFoundError:
                _not_empty("The output directory disappeared while Trial Folio claimed it.")
            self._write_all(descriptor, data)
        finally:
            if descriptor is not None:
                os.close(descriptor)
        try:
            names = os.listdir(self._root)
        except FileNotFoundError:
            _not_empty("The output directory disappeared while Trial Folio claimed it.")
        if claim.path.name not in names or not claim.owns_file():
            _not_empty("The output directory changed while Trial Folio claimed it.")
        if any(not _part_of(name, claim.path.name) for name in names):
            _not_empty(
                "Another process wrote to the output directory while Trial Folio claimed it."
            )
        # The root's parent too: a competing claim may have created the root, and failed before
        # syncing it.
        self._sync_directories(
            [self._root, self._root.parent, *(directory.parent for directory in new)]
        )

    def _write_new(self, path: Path, data: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _BINARY, _MODE)
        try:
            self._write_all(descriptor, data)
        finally:
            os.close(descriptor)

    def _write_all(self, descriptor: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view) :]
        self._sync(descriptor)

    def _sync_new_entries(self, file: Path) -> None:
        """Syncs the directory holding `file`, and the parent of each directory on the way to it
        that the store may have created and hasn't synced."""
        directories = [file.parent]
        for directory in file.parents:
            if directory in self._unsynced:
                directories.append(directory.parent)
            if directory == self._root:
                break
        self._sync_directories(directories)
        synced = set(file.parents)
        self._unsynced = [directory for directory in self._unsynced if directory not in synced]

    def _sync_directories(self, directories: Iterable[Path]) -> None:
        if sys.platform == "win32":
            return  # Python can't open a directory on Windows.
        # Deepest first, each once.
        for directory in sorted(set(directories), key=lambda path: len(path.parts), reverse=True):
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                self._sync(descriptor)
            except OSError as error:
                if error.errno not in _NO_DIRECTORY_SYNC:
                    raise
                self._warn(_NO_DIRECTORY_SYNC_WARNING)
            finally:
                os.close(descriptor)

    def _sync(self, descriptor: int) -> None:
        if sys.platform == "darwin":
            try:
                fcntl.fcntl(descriptor, fcntl.F_FULLFSYNC)
            except OSError as error:
                if error.errno not in _NO_FULL_SYNC:
                    raise
                self._warn(_NO_FULL_SYNC_WARNING)
            else:
                return
        os.fsync(descriptor)

    def _warn(self, message: str) -> None:
        """Logs that the store's writes are less durable, once for each reason."""
        if message not in self._warned:
            self._warned.add(message)
            _logger.warning(message, extra={"event": "artifact.sync.degraded"})


@dataclass
class _Claim:
    """What a claim created, recorded while SIGINT delivery is deferred."""

    path: Path
    file: os.stat_result | None = None
    """The identity read from the descriptor returned by a successful exclusive create."""
    directories: list[Path] = field(default_factory=list[Path])
    """Outermost first."""

    def undo(self) -> None:
        if self.owns_file():
            _remove(self.path)
        for directory in reversed(self.directories):
            try:
                os.rmdir(directory)
            except FileNotFoundError:
                continue  # Never created, or already removed by a competing claim.
            except OSError:
                return  # Another process wrote there; leave it and its parents as they are.

    def owns_file(self) -> bool:
        if self.file is None:
            return False
        try:
            return os.path.samestat(self.file, os.lstat(self.path))
        except OSError:
            return False  # Missing, or ownership can't be checked; don't remove someone else's.


def _make_directories(directory: Path, made: list[Path], stop: Path | None = None) -> list[Path]:
    """Creates `directory` and its missing parents, one at a time, outermost first, and returns
    those that were missing. A directory that another process creates first is used as it is.
    With `stop`, it creates nothing at or above it.

    SIGINT is deferred until each successful creation is recorded in `made`.
    """
    missing: list[Path] = []
    for candidate in (directory, *directory.parents):
        if candidate == stop or os.path.lexists(candidate):
            break
        missing.append(candidate)
    missing.reverse()
    for candidate in missing:
        with _defer_sigint():
            try:
                os.mkdir(candidate)
            except FileExistsError:
                pass  # If it isn't a directory, the next step fails with NotADirectoryError.
            else:
                made.append(candidate)
    return missing


def _publish(temporary: Path, final: Path, path: str) -> None:
    """Gives the temporary file its final name, never replacing a file."""
    try:
        if sys.platform == "win32":
            os.rename(temporary, final)
        else:
            os.link(temporary, final)
    except FileExistsError as error:
        raise TrialFolioError(
            "storage.write_failed",
            f"Couldn't write {path}: a file with that name already exists in the output"
            " directory, and Trial Folio never replaces a file.",
        ) from error
    except OSError as error:
        if sys.platform == "win32" or error.errno not in _NO_HARD_LINKS:
            raise
        raise TrialFolioError(
            "storage.write_failed",
            f"Couldn't write {path}: the output directory's file system doesn't support hard"
            f" links ({_reason(error)}). FAT and exFAT don't. Trial Folio publishes each file"
            " with a hard link, so that it never replaces one. Choose an output directory on"
            " another file system.",
        ) from error


def _part_of(name: str, claimed: str) -> bool:
    """Whether a name in a directory being claimed is the claim's own file. On macOS, that
    includes the AppleDouble file it gets on FAT or exFAT."""
    if sys.platform == "darwin" and name == _APPLE_DOUBLE + claimed:
        return True
    return name == claimed


@contextmanager
def _defer_sigint() -> Generator[None, None, None]:
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


def _remove(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass  # Already gone, or the failure being reported matters more.


def _stored(path: str, data: bytes) -> StoredFile:
    return StoredFile(
        path=path, artifact_id="sha256:" + hashlib.sha256(data).hexdigest(), size=len(data)
    )


def _reason(error: OSError) -> str:
    # strerror never includes the path, which the error's text would.
    return error.strerror or type(error).__name__


def _not_empty(problem: str) -> NoReturn:
    raise TrialFolioError(
        "output.not_empty",
        f"{problem} Trial Folio writes only into a new or empty directory, and never into one it"
        " hasn't claimed. Choose a new or empty output directory.",
    )
