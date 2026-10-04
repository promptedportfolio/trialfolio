"""Storage faults: the double for injected storage failures (release 0.1.0, test pairing).

`StorageFaults` wraps a real `ArtifactStore`, records every file it publishes, and fails at a
named file, once:

- **`fail_os(name)`** makes the real store's write fail with an `OSError` as it creates its
  temporary file, so the store reports it as it would a full disk: `storage.write_failed`.
- **`fail_before(name, error)`** raises `error`, such as a `KeyboardInterrupt` or an unexpected
  `RuntimeError`, before the real write starts.
- **`fail_after(name, error)`** raises `error` once the real write has published the file.

A name matches a path's last segment, such as `response.json`. R01-T11 created this ahead of
R01-T15, which adds a failed `os.link`, as on a file system without hard links.
"""

import errno
import os
from pathlib import Path

import pytest

from trialfolio.storage import ArtifactStore, StoredFile


class StorageFaults:
    """An `ArtifactStore` that wraps a real one, as the module says."""

    def __init__(self, store: ArtifactStore, monkeypatch: pytest.MonkeyPatch) -> None:
        self._store = store
        self._before: dict[str, BaseException] = {}
        self._after: dict[str, BaseException] = {}
        self._os_errors: set[str] = set()
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

    def fail_os(self, name: str) -> None:
        """The next write of `name` fails inside the real store with `ENOSPC`."""
        self._os_errors.add(name)

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
