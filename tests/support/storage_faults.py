"""Storage faults: the double for injected storage failures (release 0.1.0, test pairing).

`StorageFaults` wraps a real `ArtifactStore`, records every file it publishes, and fails at a
named file, once:

- **`fail_os(name)`** makes the real store's write fail with an `OSError` as it creates its
  temporary file, so the store reports it as it would a full disk: `storage.write_failed`.
- **`fail_before(name, error)`** raises `error`, such as a `KeyboardInterrupt` or an unexpected
  `RuntimeError`, before the real write starts.
- **`fail_after(name, error)`** raises `error` once the real write has published the file.
- **`fail_link(name)`** makes `os.link` fail as it does on a file system without hard links,
  such as FAT or exFAT, when the real store publishes `name`, and for every file after it. On
  Linux and macOS, the store publishes each file with `os.link`; on Windows it renames it, so
  this fault doesn't apply there.

A name matches a path's last segment, such as `response.json`. R01-T11 created this ahead of
R01-T15, which added the failed `os.link`.

`placeholder_identities` stands for the other way FAT and exFAT differ on macOS: every empty file
has the same placeholder inode until its first write. It patches `os` for the whole test, so it
applies to any store, wrapped or not.
"""

import errno
import os
import stat
import sys
from pathlib import Path

import pytest

from trialfolio.storage import ArtifactStore, StoredFile

_NO_HARD_LINKS = errno.ENOTSUP if sys.platform == "darwin" else errno.EPERM
"""How `os.link` reports a file system without hard links: `ENOTSUP` on macOS, as R01-T08 saw
on exFAT and FAT32 disk images, and `EPERM` on Linux, as link(2) documents."""

PLACEHOLDER_INODE = 2**64 - 3
"""The inode that `os.fstat` and `os.lstat` report for every new, empty file on exFAT and FAT32
disk images on macOS 26.6.2, until its first write gives it its own (2026-10-04)."""


def placeholder_identities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes every empty regular file report `PLACEHOLDER_INODE`, as FAT and exFAT do on macOS, so
    that two empty files have the same identity, and a file's identity changes when it's first
    written."""
    real_fstat, real_lstat = os.fstat, os.lstat

    def placeholder(result: os.stat_result) -> os.stat_result:
        if not stat.S_ISREG(result.st_mode) or result.st_size != 0:
            return result
        fields = list(result[: os.stat_result.n_sequence_fields])
        fields[stat.ST_INO] = PLACEHOLDER_INODE
        # The rest, such as st_mtime, come only from the mapping, which takes none of the
        # sequence's fields: Python 3.14 refuses one there.
        others = {
            name: getattr(result, name)
            for name in dir(result)
            if name.startswith("st_") and name not in os.stat_result.__match_args__
        }
        return os.stat_result(fields, others)

    def fstat(descriptor: int) -> os.stat_result:
        return placeholder(real_fstat(descriptor))

    def lstat(path: str | os.PathLike[str], *, dir_fd: int | None = None) -> os.stat_result:
        return placeholder(real_lstat(path, dir_fd=dir_fd))

    monkeypatch.setattr(os, "fstat", fstat)
    monkeypatch.setattr(os, "lstat", lstat)


class StorageFaults:
    """An `ArtifactStore` that wraps a real one, as the module says."""

    def __init__(self, store: ArtifactStore, monkeypatch: pytest.MonkeyPatch) -> None:
        self._store = store
        self._before: dict[str, BaseException] = {}
        self._after: dict[str, BaseException] = {}
        self._os_errors: set[str] = set()
        self._links_fail_at: str | None = None
        self._links_failing = False
        self.published: list[str] = []
        """Each path a write published, in order. A file written twice would appear twice."""
        real_open = os.open

        def open_(
            path: str | os.PathLike[str],
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            # The store's temporary file is `.<name>.<random>.tmp`.
            parts = Path(path).name.split(".")
            if len(parts) > 3 and parts[0] == "" and parts[-1] == "tmp":
                name = ".".join(parts[1:-2])
                if name in self._os_errors:
                    self._os_errors.discard(name)
                    raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))
            return real_open(path, flags, mode, dir_fd=dir_fd)

        monkeypatch.setattr(os, "open", open_)
        real_link = os.link

        def link(
            source: str | os.PathLike[str],
            destination: str | os.PathLike[str],
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            if Path(destination).name == self._links_fail_at:
                self._links_failing = True
            if self._links_failing:
                raise OSError(_NO_HARD_LINKS, os.strerror(_NO_HARD_LINKS))
            real_link(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )

        monkeypatch.setattr(os, "link", link)

    def fail_os(self, name: str) -> None:
        """The next write of `name` fails inside the real store with `ENOSPC`."""
        self._os_errors.add(name)

    def fail_link(self, name: str) -> None:
        """From the write of `name` on, the real store's `os.link` fails as it does on a file
        system without hard links."""
        self._links_fail_at = name

    def fail_before(self, name: str, error: BaseException) -> None:
        """The next write of `name` raises `error` before it starts."""
        self._before[name] = error

    def fail_after(self, name: str, error: BaseException) -> None:
        """The next write of `name` raises `error` once the file is published."""
        self._after[name] = error

    def check_empty(self) -> None:
        self._store.check_empty()

    def claim(self, path: str, data: bytes) -> StoredFile:
        stored = self._store.claim(path, data)
        self.published.append(path)
        return stored

    def write(self, path: str, data: bytes) -> StoredFile:
        name = path.rsplit("/", 1)[-1]
        before = self._before.pop(name, None)
        if before is not None:
            raise before
        stored = self._store.write(path, data)
        self.published.append(path)
        after = self._after.pop(name, None)
        if after is not None:
            raise after
        return stored

    def discard(self, path: str, data: bytes) -> None:
        self._store.discard(path, data)

    def read(self, path: str) -> bytes:
        return self._store.read(path)
