"""Boundaries for the core tests: what the store syncs, failures injected into its file
operations (AGENTS.md, verification expectations: injected storage failures), and an attempt run
over the fake Portfolio123 server, below `urllib3`, whose saved response the normalization tests
read."""

import itertools
import json
import os
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.attempts import Attempt
from trialfolio.configuration import original_values, read_screen_configuration
from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.plan import Plan
from trialfolio.normalization import NormalizedTables, write_tables
from trialfolio.planning import VERIFIED_VERSIONS, Versions, build_plan
from trialfolio.provider import Credentials, P123ScreenBacktestClient
from trialfolio.storage import LocalArtifactStore, StoredFile

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
    file or directory: the one whose name contains `name`, which includes a file's temporary
    file."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._before_open: dict[str, Effect] = {}
        self._after_open: dict[str, Effect] = {}
        self._before_write: dict[str, Effect] = {}
        self._after_close: dict[str, Effect] = {}
        self._after_mkdir: dict[str, Effect] = {}
        self._writing: dict[int, Effect] = {}
        self._closing: dict[int, Effect] = {}
        real_open, real_write, real_close, real_mkdir = os.open, os.write, os.close, os.mkdir

        def matching(effects: dict[str, Effect], path: str | os.PathLike[str]) -> list[Effect]:
            name = Path(path).name
            return [effect for target, effect in effects.items() if target in name]

        def open_(
            path: str | os.PathLike[str],
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            for effect in matching(self._before_open, path):
                effect()
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            for effect in matching(self._before_write, path):
                self._writing[descriptor] = effect
            for effect in matching(self._after_close, path):
                self._closing[descriptor] = effect
            try:
                for effect in matching(self._after_open, path):
                    effect()  # As if an interrupt arrived as the call returned.
            except BaseException:
                close(descriptor)  # The store never got it; the file stays.
                raise
            return descriptor

        def write(descriptor: int, data: bytes | memoryview) -> int:
            effect = self._writing.get(descriptor)
            if effect is not None:
                effect()
            return real_write(descriptor, data)

        def close(descriptor: int) -> None:
            self._writing.pop(descriptor, None)
            effect = self._closing.pop(descriptor, None)
            real_close(descriptor)
            if effect is not None:
                effect()

        def mkdir(path: str | os.PathLike[str], mode: int = 0o777) -> None:
            real_mkdir(path, mode)
            for effect in matching(self._after_mkdir, path):
                effect()

        monkeypatch.setattr(os, "open", open_)
        monkeypatch.setattr(os, "write", write)
        monkeypatch.setattr(os, "close", close)
        monkeypatch.setattr(os, "mkdir", mkdir)

    def on_open(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before the file is opened."""
        self._before_open[name] = effect

    def after_open(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the file is open, before the store gets its descriptor."""
        self._after_open[name] = effect

    def on_write(self, name: str, effect: Effect) -> None:
        """Runs `effect` just before each write to the file."""
        self._before_write[name] = effect

    def after_close(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the file is closed, as if closing it reported an error."""
        self._after_close[name] = effect

    def after_mkdir(self, name: str, effect: Effect) -> None:
        """Runs `effect` once the directory is created, before the store learns it was."""
        self._after_mkdir[name] = effect


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> Faults:
    return Faults(monkeypatch)


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


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Every file and directory under `root`, hidden ones included: a file's bytes, or None for a
    directory."""
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


CONFIGS = Path(__file__).resolve().parents[1] / "fixtures" / "screen-configs"
RESPONSES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"

VERSIONS = Versions(
    trialfolio="0.1.0",
    p123api=VERIFIED_VERSIONS["p123api"][0],
    requests=VERIFIED_VERSIONS["requests"][0],
    urllib3=VERIFIED_VERSIONS["urllib3"][0],
)


@dataclass(frozen=True)
class Normalized:
    """A run's attempt over the fake server, and what normalizing its saved response wrote."""

    store: LocalArtifactStore
    plan: Plan
    configuration: StoredFile
    response: SavedResponse
    sent: dict[str, object]
    """The backtest request's body, as the fake server received it."""

    def write_tables(self) -> NormalizedTables:
        content = self.store.read(self.configuration.path)
        return write_tables(
            self.store,
            self.plan,
            original_values(content, "configuration.yaml"),
            configuration=self.configuration,
            response=self.response,
        )


type Execute = Callable[[bytes, bytes], Normalized]


@pytest.fixture
def execute(tmp_path: Path) -> Iterator[Execute]:
    """Runs one attempt as `run` does: plans the configuration's bytes, claims a new output
    directory with `plan.json`, saves `configuration.yaml`, and sends the request with the real
    client, `requests`, and `urllib3` to the fake server, which answers it with a 200 and the
    body given. The attempt saves the response; normalizing it is left to the test."""
    server = FakePortfolio123()
    outputs = itertools.count(1)

    def run(content: bytes, body: bytes) -> Normalized:
        plan = build_plan(read_screen_configuration(content, "configuration.yaml"), VERSIONS)
        store = LocalArtifactStore(tmp_path / f"out-{next(outputs)}")
        store.claim("plan.json", plan.model_dump_json(indent=2).encode())
        configuration = store.write("configuration.yaml", content)
        server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
        server.reply("/screen/backtest", Reply(200, body))
        credentials = Credentials(canaries.API_ID, canaries.API_KEY)
        with P123ScreenBacktestClient(credentials, endpoint=server.endpoint) as client:
            result = Attempt(plan, plan.plan_hash, store).run(client)
        assert result.record.outcome == "succeeded"
        assert result.record.response is not None
        sent = json.loads(server.received[-1].body)
        return Normalized(store, plan, configuration, result.record.response, sent)

    yield run
    server.close()
