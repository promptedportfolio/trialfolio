"""File faults: the double for injected storage failures below the store, in its file operations
(AGENTS.md, verification expectations: injected storage failures).

- **`SyncLog`** records each file and directory the store syncs, by identity, in order.
- **`Faults`** runs an effect, such as a failure or another process's action, at one of the store's
  file operations on a file or directory whose name contains the name given, which includes a
  file's temporary file: just before it's opened, once it's open, before each write, before each
  sync, once it's closed, or once a directory is created.

A sync is `os.fsync`, or, on macOS, `fcntl.F_FULLFSYNC`, which the store uses there, so both
patch the two (`patch_syncs`). `raises` and `once` make the effects.

TS-T04 moved them here from the core's conftest, whose fixtures `sync_log` and `faults` make them,
with `Faults`' operations as methods, which its `__init__` defined as closures.
"""

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


def patch_syncs(monkeypatch: pytest.MonkeyPatch, before: Callable[[int], object]) -> None:
    """Calls `before` with the descriptor just before each sync, whether `os.fsync` or, on
    macOS, `fcntl.F_FULLFSYNC`."""
    real_fsync = os.fsync

    def fsync(descriptor: int) -> None:
        before(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    if sys.platform == "darwin":
        import fcntl

        real_fcntl = fcntl.fcntl

        def full_sync(descriptor: int, command: int, argument: int = 0) -> int:
            if command == fcntl.F_FULLFSYNC:
                before(descriptor)
            return real_fcntl(descriptor, command, argument)

        monkeypatch.setattr(fcntl, "fcntl", full_sync)


class SyncLog:
    """Each file and directory the store synced, by identity, in order, from its creation."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.synced: list[Identity] = []
        patch_syncs(monkeypatch, self._record)

    def take(self) -> set[Identity]:
        """What was synced since the last call."""
        synced = set(self.synced)
        self.synced.clear()
        return synced

    def _record(self, descriptor: int) -> None:
        status = os.fstat(descriptor)
        self.synced.append((status.st_dev, status.st_ino))


type Effect = Callable[[], object]

type _Path = str | os.PathLike[str]


class Faults:
    """Injects a failure, or another process's action, into the store's file operations on one
    file or directory: the one whose name contains `name`, which includes a file's temporary
    file."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._before_open: dict[str, Effect] = {}
        self._after_open: dict[str, Effect] = {}
        self._before_write: dict[str, Effect] = {}
        self._after_close: dict[str, Effect] = {}
        self._after_mkdir: dict[str, Effect] = {}
        self._before_sync: dict[str, Effect] = {}
        self._writing: dict[int, Effect] = {}
        self._syncing: dict[int, Effect] = {}
        self._closing: dict[int, Effect] = {}
        self._real_open, self._real_write = os.open, os.write
        self._real_close, self._real_mkdir = os.close, os.mkdir
        monkeypatch.setattr(os, "open", self._open)
        monkeypatch.setattr(os, "write", self._write)
        monkeypatch.setattr(os, "close", self._close)
        monkeypatch.setattr(os, "mkdir", self._mkdir)
        patch_syncs(monkeypatch, self._sync)

    def on_open(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before the file is opened."""
        self._before_open[name] = effect

    def after_open(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the file is open, before the store gets its descriptor."""
        self._after_open[name] = effect

    def on_write(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before each write to the file."""
        self._before_write[name] = effect

    def on_sync(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before each sync of the file, whether `os.fsync` or, on macOS,
        `fcntl.F_FULLFSYNC`."""
        self._before_sync[name] = effect

    def after_close(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the file is closed, as if closing it reported an error."""
        self._after_close[name] = effect

    def after_mkdir(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the directory is created, before the store learns it was."""
        self._after_mkdir[name] = effect

    # The patched operations

    def _open(
        self, path: _Path, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        for effect in _matching(self._before_open, path):
            effect()
        descriptor = self._real_open(path, flags, mode, dir_fd=dir_fd)
        for effect in _matching(self._before_write, path):
            self._writing[descriptor] = effect
        for effect in _matching(self._before_sync, path):
            self._syncing[descriptor] = effect
        for effect in _matching(self._after_close, path):
            self._closing[descriptor] = effect
        try:
            for effect in _matching(self._after_open, path):
                effect()  # As if an interrupt arrived as the call returned.
        except BaseException:
            self._close(descriptor)  # The store never got it; the file stays.
            raise
        return descriptor

    def _write(self, descriptor: int, data: bytes | memoryview) -> int:
        effect = self._writing.get(descriptor)
        if effect is not None:
            effect()
        return self._real_write(descriptor, data)

    def _sync(self, descriptor: int) -> None:
        effect = self._syncing.get(descriptor)
        if effect is not None:
            effect()

    def _close(self, descriptor: int) -> None:
        self._writing.pop(descriptor, None)
        self._syncing.pop(descriptor, None)
        effect = self._closing.pop(descriptor, None)
        self._real_close(descriptor)
        if effect is not None:
            effect()

    def _mkdir(self, path: _Path, mode: int = 0o777) -> None:
        self._real_mkdir(path, mode)
        for effect in _matching(self._after_mkdir, path):
            effect()


def _matching(effects: dict[str, Effect], path: _Path) -> list[Effect]:
    name = Path(path).name
    return [effect for target, effect in effects.items() if target in name]


def raises(error: BaseException) -> Effect:
    """An effect that raises `error`."""

    def effect() -> None:
        raise error

    return effect


def once(effect: Effect) -> Effect:
    """`effect` the first time, and nothing after."""
    done = False

    def first() -> object:
        nonlocal done
        if done:
            return None
        done = True
        return effect()

    return first
