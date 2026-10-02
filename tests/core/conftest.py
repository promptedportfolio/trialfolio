"""Storage boundaries for the core tests: what the store syncs, and failures injected into its
file operations (AGENTS.md, verification expectations: injected storage failures)."""

import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

type Identity = tuple[int, int]


def identity(path: Path) -> Identity:
    """The device and inode of a file or directory, which outlast any one descriptor."""
    status = os.stat(path)
    return (status.st_dev, status.st_ino)


class SyncLog:
    """Each file and directory the store synced, by identity, in order."""

    def __init__(self) -> None:
        self.synced: list[Identity] = []

    def take(self) -> set[Identity]:
        """What was synced since the last call."""
        synced = set(self.synced)
        self.synced.clear()
        return synced


@pytest.fixture
def sync_log(monkeypatch: pytest.MonkeyPatch) -> SyncLog:
    """Records every sync, whether `os.fsync` or, on macOS, `fcntl.F_FULLFSYNC`."""
    log = SyncLog()

    def record(descriptor: int) -> None:
        status = os.fstat(descriptor)
        log.synced.append((status.st_dev, status.st_ino))

    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        record(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    if sys.platform == "darwin":
        import fcntl

        real_fcntl = fcntl.fcntl

        def full_sync(descriptor: int, command: int, argument: int = 0) -> int:
            if command == fcntl.F_FULLFSYNC:
                record(descriptor)
            return real_fcntl(descriptor, command, argument)

        monkeypatch.setattr(fcntl, "fcntl", full_sync)
    return log


type Effect = Callable[[], object]


class Faults:
    """Injects a failure, or another process's action, into the store's file operations on one
    file: the file whose name contains `name`, which includes its temporary file."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._opening: dict[str, Effect] = {}
        self._writing: dict[str, Effect] = {}
        self._descriptors: dict[int, Effect] = {}
        real_open, real_write, real_close = os.open, os.write, os.close

        def open_(
            path: str | os.PathLike[str],
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            name = Path(path).name
            for target, effect in self._opening.items():
                if target in name:
                    effect()
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            for target, effect in self._writing.items():
                if target in name:
                    self._descriptors[descriptor] = effect
            return descriptor

        def write(descriptor: int, data: bytes | memoryview) -> int:
            effect = self._descriptors.get(descriptor)
            if effect is not None:
                effect()
            return real_write(descriptor, data)

        def close(descriptor: int) -> None:
            self._descriptors.pop(descriptor, None)
            real_close(descriptor)

        monkeypatch.setattr(os, "open", open_)
        monkeypatch.setattr(os, "write", write)
        monkeypatch.setattr(os, "close", close)

    def on_open(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before the file is opened."""
        self._opening[name] = effect

    def on_write(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before each write to the file."""
        self._writing[name] = effect


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> Faults:
    return Faults(monkeypatch)


def raises(error: BaseException) -> Effect:
    """An effect that raises `error`."""

    def effect() -> None:
        raise error

    return effect


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Every file and directory under `root`, hidden ones included: a file's bytes, or None for a
    directory."""
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }
