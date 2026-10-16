"""The ranking lock: the lock a run that writes `ApiRankingSystem` holds, so that no other Trial
Folio process on the machine writes it meanwhile, and two cases' write and backtest never
interleave (docs/contracts.md, the ranking lock; ADR 0001, decision 5; R04-AC05).

`RankingLock` takes the lock on the file its caller names, without waiting, and holds it until
`release`, or until the process ends, however it ends. The core takes it before a run writes
anything, and releases it when the run's execution ends; it reads no environment variable, so its
caller gives it the file, which `ranking_lock_path` gives from the environment the caller reads.

- **The file** is `trialfolio-ranking.lock`, in `TRIALFOLIO_LOCK_DIR` when that's set and not
  empty, and otherwise in a directory every user of the machine can write: `/tmp` on Linux and
  macOS, and the one `%ProgramData%` names on Windows. Trial Folio creates no directory for it.
- **Opening it.** It's opened only for reading, never through a symbolic link (`O_NOFOLLOW`), and
  created only when it doesn't exist, exclusively, and opened again when another process created
  it first. So a file another user created is opened, not created, which Linux's
  `protected_regular` allows. A file it creates gets the mode `0644`, whatever the umask, on Linux
  and macOS. It's never written, truncated, or removed: it stays empty.
- **The lock** is the experiment lock's kind: `fcntl.flock` with `LOCK_EX | LOCK_NB` on Linux and
  macOS, and `msvcrt.locking` with `LK_NBLCK` on the file's first byte on Windows, which
  Microsoft's documentation allows on a handle with read access, beyond the end of the file. The
  Windows parts come from that documentation, not from a check on Windows.
- **A file replaced before it's locked.** On Linux and macOS, once it holds the lock, it checks
  that the path still names the file it locked, by its device and inode, and otherwise opens the
  path again. A file removed while a run holds its lock is a limit the lock states.
- **Errors.** Another process's lock gives `experiment.locked`, exit 4, and any other failure to
  open or lock the file `storage.write_failed`, exit 4, whose message names the file, with its
  control and formatting characters written as escapes, and the system's reason, and says that
  `TRIALFOLIO_LOCK_DIR` can name another directory. The logged messages leave the path out.
"""

import errno
import logging
import os
import stat
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import Final, Self

from trialfolio.display import visible
from trialfolio.errors import TrialFolioError, reason_of

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

_logger = logging.getLogger(__name__)

LOCK_FILE: Final = "trialfolio-ranking.lock"
"""The ranking lock's file name, in its directory."""

LOCK_DIRECTORY_VARIABLE: Final = "TRIALFOLIO_LOCK_DIR"
"""The variable that names another directory for the ranking lock's file."""

_WINDOWS_PROGRAM_DATA: Final = r"C:\ProgramData"
"""Where `%ProgramData%` usually leads, for an environment that doesn't set it."""

_MODE: Final = 0o644
"""The mode of a lock file Trial Folio creates, whatever the umask, so every user can open it."""

_OPEN: Final[int] = (
    os.O_RDONLY
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_BINARY", 0)
)
"""Only for reading, never through a symbolic link, and closed in a program it runs."""

_ATTEMPTS: Final = 8
"""How many times it opens the path again, when the file it opened or locked was replaced, before
it gives up: each needs another process to remove the file at that moment."""

_HELD: Final = (
    frozenset({errno.EACCES})
    if sys.platform == "win32"
    else frozenset({errno.EAGAIN, errno.EWOULDBLOCK})
)
"""How taking the lock reports that another process holds it, as for the experiment lock:
`EWOULDBLOCK`, `EAGAIN` on Linux and macOS, from `flock`, and `EACCES` from `msvcrt.locking`."""

_HINT: Final = (
    f" {LOCK_DIRECTORY_VARIABLE} can name another directory for it; every process that uses the"
    " account must then name the same one."
)


def ranking_lock_path(environ: Mapping[str, str], platform: str = sys.platform) -> Path:
    """The ranking lock's file: `trialfolio-ranking.lock`, in `TRIALFOLIO_LOCK_DIR` when it's set
    and not empty, and otherwise in `/tmp` on Linux and macOS, which macOS keeps at
    `/private/tmp`, and in the directory `%ProgramData%` names on Windows, or `C:\\ProgramData`
    when it names none. `environ` is the environment the caller reads; nothing here reads it."""
    chosen = environ.get(LOCK_DIRECTORY_VARIABLE)
    if chosen:
        return Path(chosen) / LOCK_FILE
    if platform == "win32":
        # Windows reads its variables' names in any case; a mapping copied from it may not.
        program_data = environ.get("ProgramData") or environ.get("PROGRAMDATA")
        return Path(program_data or _WINDOWS_PROGRAM_DATA) / LOCK_FILE
    return Path("/tmp") / LOCK_FILE


class RankingLock:
    """The ranking lock, on the file at `path`. It's taken once, by `acquire`, and held until
    `release`, which the context manager calls too. Whatever happens, `held` says whether it's
    held."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        """Opens nothing."""
        self._path = Path(path)
        self._descriptor: int | None = None
        self._taken = 0.0

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._descriptor is not None

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.release()

    def acquire(self) -> None:
        """Takes the lock, without waiting.

        Raises `TrialFolioError` with `experiment.locked` when another process holds it, and with
        `storage.write_failed` when the file can't be opened, created, or locked, or keeps being
        replaced. Raises `RuntimeError` if this lock is held already.
        """
        if self._descriptor is not None:
            raise RuntimeError("the ranking lock is taken once")
        for _ in range(_ATTEMPTS):
            descriptor = self._open()
            kept = False
            try:
                _lock(self._path, descriptor)
                if _still_named(self._path, descriptor):
                    self._descriptor, kept = descriptor, True
            finally:
                if not kept:
                    os.close(descriptor)
            if kept:
                self._taken = time.monotonic()
                _logger.info(
                    "Took the ranking lock: no other Trial Folio process on this machine writes"
                    " ApiRankingSystem until this run ends.",
                    extra={"event": "ranking.lock.taken"},
                )
                return
        raise _unavailable(self._path, "another program kept replacing the file")

    def release(self) -> None:
        """Releases the lock, if it's held, by closing its file. The operating system releases it
        too when the process ends, however it ends."""
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            return
        _release(descriptor)
        _logger.debug(
            "Released the ranking lock after %.3f s.",
            time.monotonic() - self._taken,
            extra={"event": "ranking.lock.released"},
        )

    def _open(self) -> int:
        """Opens the file, only for reading, or creates it, exclusively, when it doesn't exist,
        and opens it again when another process created it first."""
        for _ in range(_ATTEMPTS):
            try:
                return os.open(self._path, _OPEN)
            except FileNotFoundError:
                pass
            except OSError as error:
                raise _unavailable(self._path, reason_of(error)) from error
            try:
                descriptor = os.open(self._path, _OPEN | os.O_CREAT | os.O_EXCL, _MODE)
            except FileExistsError:
                continue
            except OSError as error:
                raise _unavailable(self._path, reason_of(error)) from error
            _set_mode(self._path, descriptor)
            return descriptor
        raise _unavailable(self._path, "another program kept removing the file")


def _set_mode(path: Path, descriptor: int) -> None:
    """Gives a file this process created the mode `0644`, whatever the umask, on Linux and
    macOS. Windows has no such mode."""
    if sys.platform == "win32":
        return
    try:
        os.fchmod(descriptor, _MODE)
    except OSError as error:
        os.close(descriptor)
        raise _unavailable(path, reason_of(error)) from error


def _lock(path: Path, descriptor: int) -> None:
    """Takes the lock on `descriptor` without waiting. Raises `TrialFolioError` with
    `experiment.locked` when another process holds it, and with `storage.write_failed` when the
    file system refuses it for any other reason."""
    try:
        if sys.platform == "win32":
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in _HELD:
            raise TrialFolioError(
                "experiment.locked",
                "Another Trial Folio process on this machine is writing ApiRankingSystem, for an"
                " experiment or a screen run whose ranking is a definition: it holds the ranking"
                " lock. Wait for it to end, then run the command again. Nothing was sent, and"
                " nothing was written.",
            ) from error
        raise _unavailable(path, reason_of(error)) from error


def _still_named(path: Path, descriptor: int) -> bool:
    """Whether the path still names the file `descriptor` locked, by its device and inode, on
    Linux and macOS. Another program may have removed the file after this process opened it, and
    a third process may have created and locked a new one meanwhile."""
    if sys.platform == "win32":
        return True
    try:
        named = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return False
    held = os.fstat(descriptor)
    return stat.S_ISREG(named.st_mode) and (named.st_dev, named.st_ino) == (
        held.st_dev,
        held.st_ino,
    )


def _release(descriptor: int) -> None:
    """Releases the lock `descriptor` holds, and closes it. On Windows, it first unlocks the
    file's first byte, as Microsoft's `_locking` documentation asks before a file is closed.
    Errors are ignored, since closing the descriptor releases the lock either way."""
    if sys.platform == "win32":
        try:
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    try:
        os.close(descriptor)
    except OSError:
        pass


def _unavailable(path: Path, reason: str) -> TrialFolioError:
    """`storage.write_failed` for a ranking lock that can't be opened, created, or taken, with the
    file's path in the message, and without it in the logged message."""
    lead = "Couldn't take the ranking lock"
    tail = (
        f". Trial Folio holds it while a run writes ApiRankingSystem, so that two of its processes"
        f" never interleave a case's write and its backtest.{_HINT} Nothing was sent, and nothing"
        " was written."
    )
    return TrialFolioError(
        "storage.write_failed",
        f"{lead}, {visible(os.fspath(path))}: {reason}{tail}",
        f"{lead}: {reason}{tail}",
    )
