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
- **The experiment lock.** An experiment's claim takes an exclusive, non-blocking lock on the
  file that claims its directory, `experiment.lock`, before writing it, and a resumed experiment
  takes it on the existing file: `fcntl.flock` on Linux and macOS, and `msvcrt.locking` on the
  file's first byte on Windows. The store holds it until `close`, or until the process ends,
  however it ends, so a killed process leaves no stale lock (docs/contracts.md, the lock). On
  Windows, `close` unlocks the byte before closing the file, as Microsoft's documentation asks.
- **Discarding.** A write can fail after it has published its file. `discard` removes that file,
  when it holds exactly the write's bytes, for a caller whose file says something by being
  there, such as the manifest. `published` reads it back instead, for a caller that lists a file
  the store published whole.
- **Names in logs.** The store logs each file it writes by its path, and names it in its errors'
  logged messages, unless the caller gives another name for logs, because the path holds a
  configuration value: a review's copies are under `inputs/<label>/` (release 0.2.0, R02-T08).
- **Listing.** `entries` gives the names in a directory, so a resume finds an experiment's
  records through the store (release 0.3.0, R03-T09).

`ArtifactStore` combines four narrower protocols, `StoreReader`, `StoreWriter`, `StoreClaim`,
and `StoreLock`, so a reader of saved records takes only the store's reads; `LockableReader`
combines the first and the last, for the reader that takes the experiment lock before it reads
(docs/contracts.md, protocols).

The platform's primitives the local store builds on, publishing, syncing, the lock, and
deferring SIGINT, are in `trialfolio.filesystem`, with what R01-T08 and R03-T08 found each
platform reports. They don't log: the store logs a sync that's less durable, under this
module's name.
"""

import hashlib
import logging
import os
import secrets
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Final, NoReturn, Protocol, Self

from trialfolio.contracts.common import valid_relative_path
from trialfolio.errors import TrialFolioError, reason_of
from trialfolio.filesystem import (
    BINARY,
    defer_sigint,
    part_of_claim,
    publish,
    release_lock,
    sync,
    sync_directories,
    take_lock,
)

_logger = logging.getLogger(__name__)

LOCK_PATH: Final = "experiment.lock"
"""The file that claims an experiment's output directory, and on which the lock is taken. It's
here, beside the lock, so the CLI can take the lock of an experiment to resume before it loads
the modules that read the experiment's records (docs/contracts.md, running an experiment)."""

LOCK_LINE: Final = b"Trial Folio experiment lock: it claims this directory for one experiment.\n"
"""The lock file's one fixed line, so the file is never empty (docs/contracts.md, the lock)."""

_MODE: Final = 0o666
"""The mode new files are created with, before the umask."""

_DISAPPEARED: Final = "The output directory disappeared while Trial Folio claimed it."


@dataclass(frozen=True, slots=True)
class StoredFile:
    """A file the store wrote, as the manifest lists it."""

    path: str
    """Relative to the output root, with `/` separators."""
    artifact_id: str
    """`sha256:` and the hex SHA-256 of the file's bytes."""
    size: int
    """In bytes."""

    @classmethod
    def of(cls, path: str, data: bytes) -> Self:
        """The file at `path` that holds `data`."""
        return cls(
            path=path, artifact_id="sha256:" + hashlib.sha256(data).hexdigest(), size=len(data)
        )


class StoreReader(Protocol):
    """Reads one output directory's files by relative path: what a reader of saved records
    takes.

    Paths are relative to the store's root, with `/` separators, as `valid_relative_path`
    defines them; any other path raises `ValueError`.
    """

    def read(self, path: str) -> bytes:
        """Returns the bytes of a file under the root.

        Raises `FileNotFoundError` if there's none, and `OSError` if it can't be read.
        """
        ...

    def entries(self, path: str) -> tuple[str, ...]:
        """Returns the names of the entries in the directory `path` under the root, sorted,
        hidden ones included, so a resume can find an experiment's records (R03-T09).

        Raises `FileNotFoundError` if there's no such directory, `NotADirectoryError` if `path`
        is a file, and `OSError` if it can't be read.
        """
        ...


class StoreWriter(Protocol):
    """Writes new files into an output directory the store owns, by relative path, as
    `StoreReader` takes them, and undoes a failed write. No file is ever replaced or changed once
    it's written."""

    def write(self, path: str, data: bytes, *, logged_as: str | None = None) -> StoredFile:
        """Writes a new file atomically and durably, and returns it.

        Creates any missing directories on the way. The file is published under its final name
        complete, or not at all. When this returns, the file and the entries of the directories
        the store created are durable, as far as the platform allows.

        `logged_as` is the name the store's log events, and its errors' logged messages, give the
        file, when its path holds a configuration value, which logs never hold: a review's copy
        is under `inputs/<label>/`, so it's named by its result's position instead, such as
        `manifest.json of result 2`. Its path by default. The errors' full messages give the path.

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


class StoreClaim(Protocol):
    """Claims a new output directory for the store, with its first file, so the store owns it."""

    def check_empty(self) -> None:
        """Checks, without creating anything, that the root is absent or an empty directory.

        Raises `TrialFolioError` with `output.not_empty` if it holds anything, hidden files
        included, or exists and isn't a directory; and with `storage.write_failed` if it can't be
        created, because a parent isn't a directory or none exists, or can't be read.
        """
        ...

    def claim(self, path: str, data: bytes, *, lock: bool = False) -> StoredFile:
        """Claims the root for this store with its first file, and returns it.

        First checks the root as `check_empty` does, apart from listing it. Then creates the
        root, and any missing parent directories, one at a time. Then creates the file, which
        must be directly in the root and not empty, under its final name with an exclusive
        create, writes and syncs it, and lists the root. On success, the file and the
        directories' entries are durable, and the store can `write`.

        With `lock`, for an experiment's `experiment.lock`, it takes the experiment lock on the
        descriptor that created the file, before writing it, and holds it until `close`.

        Raises `TrialFolioError` with `output.not_empty` if the file existed already, the root
        holds anything else, or the root or a parent disappeared; with `experiment.locked` if
        another process holds the lock; and with `storage.write_failed` if the root can't be
        created, a write or sync fails, or the file system refuses the lock. On any failure, an
        interrupt included, it releases the lock, and removes what it created: its file, then
        the directories it created, deepest first, each only while it's empty.
        """
        ...


class StoreLock(Protocol):
    """Holds the experiment lock on the output directory, so one process at a time runs an
    experiment there (docs/contracts.md, the lock)."""

    def lock(self, path: str) -> None:
        """Takes the experiment lock on `path`, the existing file directly in the root that
        claimed it for an experiment, and holds it until `close`, so a resumed experiment owns
        its directory: the store can `write` once it holds it, without claiming the root.

        Raises `FileNotFoundError` if there's no such file, as when the root isn't a directory;
        `TrialFolioError` with
        `experiment.locked` if another process holds the lock, and with `storage.write_failed`
        if the file can't be opened or the file system refuses the lock. It writes nothing.
        """
        ...

    def close(self) -> None:
        """Releases the experiment lock, if the store holds it. The operating system also
        releases it when the process ends, however it ends."""
        ...


class ArtifactStore(StoreReader, StoreWriter, StoreClaim, StoreLock, Protocol):
    """Persists and reads one output directory's artifacts by relative path.

    Paths are relative to the store's root, with `/` separators, as `valid_relative_path`
    defines them; any other path raises `ValueError`. No file is ever replaced or changed once
    it's written.
    """


class LockableReader(StoreReader, StoreLock, Protocol):
    """A store that's read once its experiment lock is taken, so the records can't change while
    they're read: what a resumed experiment's reader takes (`open_experiment`)."""


def published(store: StoreReader, path: str, data: bytes) -> StoredFile | None:
    """The file `path`, if a write of `data` that failed published it whole, as the store can
    before a later step fails or an interrupt stops it; None if it holds other bytes, or can't be
    read, as when it was never published."""
    try:
        if store.read(path) != data:
            return None
    except OSError:
        return None
    return StoredFile.of(path, data)


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
        self._lock: int | None = None
        """The descriptor that holds the experiment lock, while the store holds it."""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

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
                f"Couldn't read the output directory: {reason_of(error)}. Check its permissions.",
            ) from error
        if occupied:
            _not_empty("The output directory isn't empty.")

    def claim(self, path: str, data: bytes, *, lock: bool = False) -> StoredFile:
        if "/" in valid_relative_path(path):
            raise ValueError("the file that claims a directory must be directly in it")
        if not data:
            # On FAT and exFAT, an empty file has only a temporary identity, which can change while
            # it stays empty, so it can't prove ownership.
            raise ValueError("the file that claims a directory must not be empty")
        if self._claimed:
            raise RuntimeError("this store has already claimed its directory")
        self._check_root()
        claim = _Claim(self._root / path)
        try:
            self._claim(claim, data, lock=lock)
        except BaseException as error:
            # Released first: Windows can't remove a file while a descriptor holds it open.
            claim.release()
            claim.undo()
            if isinstance(error, OSError):
                raise TrialFolioError(
                    "storage.write_failed",
                    f"Couldn't claim the output directory with {path}: {reason_of(error)}. Check"
                    " its free space and permissions.",
                ) from error
            raise
        self._lock = claim.lock
        self._claimed = True
        return StoredFile.of(path, data)

    def lock(self, path: str) -> None:
        if "/" in valid_relative_path(path):
            raise ValueError("the experiment lock is directly in the output directory")
        if self._claimed:
            raise RuntimeError("this store already owns its directory")
        try:
            descriptor = os.open(self._root / path, os.O_WRONLY | BINARY)
        except FileNotFoundError:
            raise
        except NotADirectoryError as error:  # The root, or a parent of it, is a file.
            raise FileNotFoundError(error.errno, error.strerror) from error
        except OSError as error:
            raise TrialFolioError(
                "storage.write_failed",
                f"Couldn't open the experiment lock, {path}: {reason_of(error)}. Check the output"
                " directory's permissions.",
            ) from error
        held = False
        try:
            take_lock(descriptor, path)
            with defer_sigint():
                self._lock = descriptor
                held = True
        finally:
            if not held:
                os.close(descriptor)
        self._claimed = True

    def close(self) -> None:
        with defer_sigint():
            descriptor, self._lock = self._lock, None
            if descriptor is not None:
                release_lock(descriptor)

    def write(self, path: str, data: bytes, *, logged_as: str | None = None) -> StoredFile:
        parts = valid_relative_path(path).split("/")
        if not self._claimed:
            raise RuntimeError("claim the output directory before writing to it")
        logged = path if logged_as is None else logged_as
        directory = self._root.joinpath(*parts[:-1])
        final = directory / parts[-1]
        # Unique, so that it's safe to remove whatever has this name; hidden, so that a crash
        # leaves a name no artifact has.
        temporary: Path | None = directory / f".{parts[-1]}.{secrets.token_hex(8)}.tmp"
        try:
            _make_directories(directory, self._unsynced, stop=self._root)
            self._write_new(temporary, data)
            publish(temporary, final, path, logged)
            if sys.platform != "win32":
                os.unlink(temporary)
            temporary = None
            self._sync_new_entries(final)
        except OSError as error:
            reason = reason_of(error)

            def problem(name: str) -> str:
                return (
                    f"Couldn't write {name} durably: {reason}. Check the output directory's free"
                    " space and permissions."
                )

            raise TrialFolioError("storage.write_failed", problem(path), problem(logged)) from error
        finally:
            if temporary is not None:
                _remove(temporary)
        stored = StoredFile.of(path, data)
        _logger.debug(
            "Wrote %s (%s).",
            logged,
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
            with defer_sigint():
                try:
                    if final.read_bytes() != data:
                        return  # Another file: not this write's to remove.
                    os.unlink(final)
                except FileNotFoundError:
                    return  # Never published.
        except OSError as error:
            raise TrialFolioError(
                "storage.write_failed",
                f"Couldn't remove {path}, which a failed write may have left: {reason_of(error)}.",
            ) from error
        try:
            sync_directories([final.parent], self._warn)
        except OSError:
            pass  # The file is gone either way, and the failure being reported matters more.

    def read(self, path: str) -> bytes:
        # Reads follow symbolic links, as any file read does. The manifest's hashes, not the
        # store, detect a file that changed.
        return self._root.joinpath(*valid_relative_path(path).split("/")).read_bytes()

    def entries(self, path: str) -> tuple[str, ...]:
        directory = self._root.joinpath(*valid_relative_path(path).split("/"))
        with os.scandir(directory) as found:
            return tuple(sorted(entry.name for entry in found))

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

    def _claim(self, claim: "_Claim", data: bytes, *, lock: bool) -> None:
        """The claim's steps: the directories, the file, which it writes and, with `lock`, locks,
        and the check that the root holds only that file, then the syncs of the directories."""
        try:
            new = _make_directories(self._root, claim.directories)
        except FileNotFoundError:
            # _check_root found a parent, so it disappeared, because a competing claim that
            # created it failed and removed it.
            _not_empty(_DISAPPEARED)
        try:
            self._fill(claim, claim.create(), data, lock=lock)
        finally:
            claim.close()
        self._check_claimed(claim)
        # The root's parent too: a competing claim may have created the root, and failed before
        # syncing it.
        sync_directories(
            [self._root, self._root.parent, *(directory.parent for directory in new)], self._warn
        )

    def _fill(self, claim: "_Claim", descriptor: int, data: bytes, *, lock: bool) -> None:
        """Writes the claim's file through `descriptor`, which created it, with `lock` taking the
        experiment lock on it first, and reads its identity again once it's written."""
        try:
            if lock:
                # Before the file has its line, so no other process can take the lock on the
                # file this claim created.
                take_lock(descriptor, claim.path.name)
            self._write_all(descriptor, data)
            # Read again once written: on FAT and exFAT, macOS gives a new, empty file a
            # temporary inode, which its first write replaces.
            with defer_sigint():
                claim.file = os.fstat(descriptor)
                if lock:
                    # The descriptor now holds the lock: the store keeps it open.
                    claim.lock, claim.descriptor = descriptor, None
        except BaseException:
            # So may a write that failed or was interrupted, even one that wrote nothing, and
            # cleanup checks this identity. If reading it fails too, the first failure is the
            # one to report.
            claim.identify()
            raise

    def _check_claimed(self, claim: "_Claim") -> None:
        """Raises `output.not_empty` unless the root holds the claim's file, and nothing else, as
        it was when the claim created it."""
        try:
            names = os.listdir(self._root)
        except FileNotFoundError:
            _not_empty(_DISAPPEARED)
        if claim.path.name not in names or not claim.owns_file():
            _not_empty("The output directory changed while Trial Folio claimed it.")
        if any(not part_of_claim(name, claim.path.name) for name in names):
            _not_empty(
                "Another process wrote to the output directory while Trial Folio claimed it."
            )

    def _write_new(self, path: Path, data: bytes) -> None:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | BINARY, _MODE)
        try:
            self._write_all(descriptor, data)
        finally:
            os.close(descriptor)

    def _write_all(self, descriptor: int, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(descriptor, view) :]
        sync(descriptor, self._warn)

    def _sync_new_entries(self, file: Path) -> None:
        """Syncs the directory holding `file`, and the parent of each directory on the way to it
        that the store may have created and hasn't synced."""
        directories = [file.parent]
        for directory in file.parents:
            if directory in self._unsynced:
                directories.append(directory.parent)
            if directory == self._root:
                break
        sync_directories(directories, self._warn)
        synced = set(file.parents)
        self._unsynced = [directory for directory in self._unsynced if directory not in synced]

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
    descriptor: int | None = None
    """The descriptor that created the file, while the claim holds it open, and before it holds
    the experiment lock."""
    lock: int | None = None
    """The descriptor that holds the experiment lock, once the claim has taken it."""

    def create(self) -> int:
        """Creates the file, with an exclusive create, records its identity, and returns the
        descriptor that created it, which the claim holds open until `close`."""
        try:
            with defer_sigint():
                descriptor = os.open(
                    self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | BINARY, _MODE
                )
                self.descriptor = descriptor
                self.file = os.fstat(descriptor)
        except FileExistsError:
            _not_empty("The output directory isn't empty.")
        except FileNotFoundError:
            _not_empty(_DISAPPEARED)
        return descriptor

    def identify(self) -> None:
        """Reads the file's identity again from the descriptor that holds it open, if one does.
        A failure leaves the identity as it was."""
        held = self.descriptor if self.descriptor is not None else self.lock
        if held is not None:
            with defer_sigint(), suppress(OSError):
                self.file = os.fstat(held)

    def close(self) -> None:
        """Closes the descriptor that created the file, unless it now holds the lock."""
        if self.descriptor is not None:
            descriptor, self.descriptor = self.descriptor, None
            os.close(descriptor)

    def release(self) -> None:
        """Releases the experiment lock, if the claim took it."""
        with defer_sigint():
            descriptor, self.lock = self.lock, None
            if descriptor is not None:
                release_lock(descriptor)

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
        with defer_sigint():
            try:
                os.mkdir(candidate)
            except FileExistsError:
                pass  # If it isn't a directory, the next step fails with NotADirectoryError.
            else:
                made.append(candidate)
    return missing


def _remove(path: Path) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass  # Already gone, or the failure being reported matters more.


def _not_empty(problem: str) -> NoReturn:
    raise TrialFolioError(
        "output.not_empty",
        f"{problem} Trial Folio writes only into a new or empty directory, and never into one it"
        " hasn't claimed. Choose a new or empty output directory.",
    )
