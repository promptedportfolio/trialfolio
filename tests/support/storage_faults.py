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

A name matches a path's last segment, such as `response.json`. A name that starts with `/`
matches a whole path instead, for `fail_os`, `fail_before`, and `fail_after`: `/manifest.json` is a
review's own manifest, written after its copies of each run's, `inputs/<label>/manifest.json`. For
those three, a name of the form `<case_id>/<name>` matches the file `<name>` of that case of an
experiment, in any of its attempts, or in its `normalized/`, since an attempt's ID is random:
`case-0123456789abcdef/started.json`. R01-T11 created this ahead of R01-T15, which added the
failed `os.link`, R02-T08 added whole paths, and R03-T11 a case's files.

`fail(name, fault)` sets a fault by its kind, which a test's parameters name: a `full disk`, as
`fail_os`; an `interrupt` or an `unexpected` failure, a `KeyboardInterrupt` or a `RuntimeError`
before the write; or a write `published` before it failed, as when the directory's sync fails.
`fail_each` sets one for each file of a mapping. TS-T04 wrote them once, from the three mappings of a kind to a call that tests wrote.

`placeholder_identities` stands for the other way FAT and exFAT differ on macOS: each new, empty
file has a temporary inode of its own until its first write gives it a lasting one. It patches
`os` for the whole test, so it applies to any store, wrapped or not.

`FaultyStores` is a command's `store_factory`, which wraps each output directory's real store in
storage faults, set up before the command runs. TS-T03 moved it here from the interface's
conftest. `Intruded`, the real store with another process's file written into the output
directory just before the claim, is TS-T03's too, for the two modules that each wrote it.
"""

import errno
import os
import stat
import sys
from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import Literal

import pytest

from trialfolio.errors import TrialFolioError
from trialfolio.storage import ArtifactStore, LocalArtifactStore, StoredFile

type Fault = Literal["full disk", "interrupt", "unexpected", "published"]
"""A kind of storage fault, as `StorageFaults.fail` sets it."""

_NO_HARD_LINKS = errno.ENOTSUP if sys.platform == "darwin" else errno.EPERM
"""How `os.link` reports a file system without hard links: `ENOTSUP` on macOS, as R01-T08 saw
on exFAT and FAT32 disk images, and `EPERM` on Linux, as link(2) documents."""


def placeholder_identities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes each empty regular file report a placeholder inode of its own, as FAT and exFAT do on
    macOS, so that a file's identity changes when it's first written.

    On exFAT and FAT32 disk images on macOS 26.6.2, `os.fstat` and `os.lstat` reported a temporary
    inode for each new, empty file, counted down from 2**64 for each mount, and a lasting one once
    it was first written (2026-10-04). Here, an empty file's placeholder is 2**64 - 1 minus its
    real inode: its own, and the same while it stays empty."""
    real_fstat, real_lstat = os.fstat, os.lstat

    def placeholder(result: os.stat_result) -> os.stat_result:
        if not stat.S_ISREG(result.st_mode) or result.st_size != 0:
            return result
        fields = list(result[: os.stat_result.n_sequence_fields])
        fields[stat.ST_INO] = 2**64 - 1 - result.st_ino
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
        self._armed = False
        """Whether the write under way fails as it creates its temporary file: a whole path's
        `fail_os`."""
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
                if self._armed or name in self._os_errors:
                    self._armed = False
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

    def fail(self, name: str, fault: Fault) -> None:
        """The next write of `name` fails with `fault`: a `full disk` inside the real store, as
        `fail_os`; an `interrupt` or an `unexpected` `RuntimeError` before it starts; or, once
        the file is `published`, `storage.write_failed`, as when the directory's sync fails."""
        match fault:
            case "full disk":
                self.fail_os(name)
            case "interrupt":
                self.fail_before(name, KeyboardInterrupt())
            case "unexpected":
                self.fail_before(name, RuntimeError())
            case "published":
                sync = TrialFolioError("storage.write_failed", "Couldn't sync the directory.")
                self.fail_after(name, sync)

    def fail_each(self, faults: Mapping[str, Fault]) -> None:
        """Each file's next write fails with its fault, as `fail` sets it."""
        for name, fault in faults.items():
            self.fail(name, fault)

    def check_empty(self) -> None:
        self._store.check_empty()

    def claim(self, path: str, data: bytes, *, lock: bool = False) -> StoredFile:
        stored = self._store.claim(path, data, lock=lock)
        self.published.append(path)
        return stored

    def lock(self, path: str) -> None:
        self._store.lock(path)

    def close(self) -> None:
        self._store.close()

    def write(self, path: str, data: bytes, *, logged_as: str | None = None) -> StoredFile:
        before = self._before.pop(_key(path, self._before), None)
        if before is not None:
            raise before
        key = _key(path, self._os_errors)
        # A whole path, or a case's file, which the temporary file's name can't give.
        if "/" in key:
            self._os_errors.discard(key)
            self._armed = True
        try:
            stored = self._store.write(path, data, logged_as=logged_as)
        finally:
            self._armed = False
        self.published.append(path)
        after = self._after.pop(_key(path, self._after), None)
        if after is not None:
            raise after
        return stored

    def discard(self, path: str, data: bytes) -> None:
        self._store.discard(path, data)

    def read(self, path: str) -> bytes:
        return self._store.read(path)

    def entries(self, path: str) -> tuple[str, ...]:
        return self._store.entries(path)


class Intruded(LocalArtifactStore):
    """The output directory's real store, with another process's file, `other.txt`, written into
    the directory just before the claim: as when another process writes there while `run` waits
    for approval."""

    def claim(self, path: str, data: bytes, *, lock: bool = False) -> StoredFile:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "other.txt").write_bytes(b"another process's file\n")
        return super().claim(path, data, lock=lock)


class FaultyStores:
    """A `store_factory` that wraps each output directory's real store in storage faults, set up
    as the test asks before the command runs."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._setups: list[Callable[[StorageFaults], None]] = []
        self.stores: list[StorageFaults] = []

    def fail_os(self, name: str) -> None:
        self._setups.append(lambda store: store.fail_os(name))

    def fail_before(self, name: str, error: BaseException) -> None:
        self._setups.append(lambda store: store.fail_before(name, error))

    def fail_after(self, name: str, error: BaseException) -> None:
        self._setups.append(lambda store: store.fail_after(name, error))

    def fail_link(self, name: str) -> None:
        self._setups.append(lambda store: store.fail_link(name))

    def fail(self, name: str, fault: Fault) -> None:
        self._setups.append(lambda store: store.fail(name, fault))

    def __call__(self, root: str) -> ArtifactStore:
        store = StorageFaults(LocalArtifactStore(root), self._monkeypatch)
        for setup in self._setups:
            setup(store)
        self.stores.append(store)
        return store

    @property
    def published(self) -> list[str]:
        """Every path the store published, in order."""
        (store,) = self.stores
        return store.published


def _key(path: str, faults: Collection[str]) -> str:
    """The name a fault for `path` is set under: its whole path, `/` first, when one is set; then,
    for a file of an experiment's case, `<case_id>/<name>`, when one is set; and otherwise its last
    segment."""
    whole = "/" + path
    if whole in faults:
        return whole
    parts = path.split("/")
    name = parts[-1]
    if len(parts) > 2 and parts[0] == "cases" and f"{parts[1]}/{name}" in faults:
        return f"{parts[1]}/{name}"
    return name
