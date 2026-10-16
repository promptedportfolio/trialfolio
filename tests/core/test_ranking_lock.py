"""The ranking lock: an execution with a definition takes it on the file its caller gives, before
it writes anything, and holds it until its execution ends; the file is created `0644`, opened
only for reading, never through a symbolic link, and never written; another descriptor's lock
fails the run with `experiment.locked`, and anything else that stops it with
`storage.write_failed`.

Traces to docs/contracts.md, the ranking lock (its file, opening it, the lock, a file replaced
before it's locked, its errors, when it's taken, and in the core) and the interface-independent
core; and to R04-AC05, at the core: an execution through the core, without the CLI and with every
`TRIALFOLIO_` variable unset, takes the lock its caller names. Another descriptor of this process
stands for another process, since `flock` locks an open file, whatever process holds it; the
interface tests, with the test launcher, take it from two processes (release 0.4.0's R04-T12).
The executors run with the demo's client, which sends nothing, or over the fake server. Each test
that takes the lock with `flock` runs on Linux and macOS; on Windows, which has no `fcntl`, only
the others run, and the test of a symbolic link there.
"""

import errno
import os
import stat
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.support import canaries
from tests.support.clock import FixedClock
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.configuration import (
    read_experiment_configuration_v1_1,
    read_screen_configuration,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.experiment_plan import PlanV1_3
from trialfolio.contracts.manifest import CommandRecord
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.experiment_execution import ExperimentExecution
from trialfolio.planning import (
    build_experiment_plan_v1_1,
    build_plan,
    build_plan_v1_1,
    installed_versions,
)
from trialfolio.provider import Credentials, P123ScreenBacktestClient, ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE, RankingLock, ranking_lock_path
from trialfolio.storage import LocalArtifactStore, StoredFile

if sys.platform != "win32":
    import fcntl

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="flock is Linux's and macOS's")

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SCREEN = FIXTURES / "screen-configs" / "definition.yaml"
EXPERIMENT = FIXTURES / "experiment-configs" / "ranking-example.yaml"
COMMAND = CommandRecord(name="run", options={}, started_at=FixedClock()())


def locked_elsewhere(path: Path) -> bool:
    """Whether another open file description holds the lock on `path`: this one can't take it."""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        assert error.errno in (errno.EAGAIN, errno.EWOULDBLOCK)
        return True
    finally:
        os.close(descriptor)
    return False


@contextmanager
def held(path: Path) -> Iterator[None]:
    """Holds the lock on `path` through another descriptor, as another process would."""
    path.touch()
    descriptor = os.open(path, os.O_RDONLY)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        yield
    finally:
        os.close(descriptor)


class Watched:
    """The real store, which checks, at each file the execution writes, whether the ranking lock
    is held, so a test sees it held from before the first write through the last."""

    def __init__(self, store: LocalArtifactStore, lock: Path) -> None:
        self._store = store
        self._lock = lock
        self.writes: list[tuple[str, bool]] = []

    def _watch(self, path: str) -> None:
        self.writes.append((path, self._lock.exists() and locked_elsewhere(self._lock)))

    def check_empty(self) -> None:
        self._store.check_empty()

    def claim(self, path: str, data: bytes, *, lock: bool = False) -> StoredFile:
        self._watch(path)
        return self._store.claim(path, data, lock=lock)

    def lock(self, path: str) -> None:
        self._store.lock(path)

    def close(self) -> None:
        self._store.close()

    def write(self, path: str, data: bytes, *, logged_as: str | None = None) -> StoredFile:
        self._watch(path)
        return self._store.write(path, data, logged_as=logged_as)

    def discard(self, path: str, data: bytes) -> None:
        self._store.discard(path, data)

    def read(self, path: str) -> bytes:
        return self._store.read(path)

    def entries(self, path: str) -> tuple[str, ...]:
        return self._store.entries(path)


@pytest.fixture(autouse=True)
def without_trial_folio_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    # The core reads no environment variable: its caller gives it the lock's file.
    for name in [name for name in os.environ if name.startswith("TRIALFOLIO_")]:
        monkeypatch.delenv(name)


def screen() -> tuple[bytes, bytes, PlanV1_2]:
    content = SCREEN.read_bytes()
    read = read_screen_configuration_v1_1(content, SCREEN.name, SCREEN)
    plan = build_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_2) and read.definition is not None
    return content, read.definition.content, plan


def experiment() -> tuple[bytes, bytes, PlanV1_3]:
    content = EXPERIMENT.read_bytes()
    read = read_experiment_configuration_v1_1(content, EXPERIMENT.name, EXPERIMENT)
    plan = build_experiment_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_3) and read.definition is not None
    return content, read.definition.content, plan


@posix_only
def test_the_file_is_created_0644_opened_only_for_reading_and_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / LOCK_FILE
    opened: list[int] = []
    real_open = os.open

    def recording(file: str | os.PathLike[str], flags: int, *args: int, **kwargs: int) -> int:
        if Path(file) == path:
            opened.append(flags)
        return real_open(file, flags, *args, **kwargs)

    lock = RankingLock(path)
    monkeypatch.setattr(os, "open", recording)
    previous = os.umask(0o077)
    try:
        lock.acquire()
    finally:
        os.umask(previous)
        monkeypatch.setattr(os, "open", real_open)
    try:
        assert lock.held
        assert locked_elsewhere(path)
    finally:
        lock.release()

    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert path.stat().st_size == 0
    assert not locked_elsewhere(path)
    assert opened
    for flags in opened:
        assert flags & (os.O_WRONLY | os.O_RDWR | os.O_TRUNC | os.O_APPEND) == 0
        assert flags & os.O_NOFOLLOW
    # Created only when it didn't exist, exclusively.
    assert [bool(flags & os.O_CREAT) for flags in opened] == [False, True]
    assert opened[1] & os.O_EXCL


@posix_only
def test_an_existing_file_is_opened_as_it_is(tmp_path: Path) -> None:
    path = tmp_path / LOCK_FILE
    path.touch()
    path.chmod(0o640)
    modified = path.stat().st_mtime_ns

    with RankingLock(path):
        assert locked_elsewhere(path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    assert path.stat().st_mtime_ns == modified
    assert path.stat().st_size == 0


@posix_only
def test_a_symbolic_link_at_its_path_isnt_followed(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.touch()
    path = tmp_path / LOCK_FILE
    path.symlink_to(target)

    with pytest.raises(TrialFolioError) as raised:
        RankingLock(path).acquire()

    assert raised.value.code == "storage.write_failed"
    # The open itself refuses the link (`O_NOFOLLOW`), before any lock is taken on its target.
    cause = raised.value.__cause__
    assert isinstance(cause, OSError)
    assert cause.errno == errno.ELOOP
    assert not locked_elsewhere(target)


@posix_only
def test_a_symbolic_link_that_the_open_follows_is_refused_before_its_target_is_locked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Windows's open has no `O_NOFOLLOW`, so it follows a link at the path: here, an open without
    # the flag stands for it. A defect found by the review of R04-T08's pull request: on Windows,
    # the link's target was locked.
    target = tmp_path / "target"
    target.touch()
    path = tmp_path / LOCK_FILE
    path.symlink_to(target)
    real_open, real_flock = os.open, fcntl.flock
    locked: list[int] = []

    def following(file: str | os.PathLike[str], flags: int, *args: int, **kwargs: int) -> int:
        if Path(file) == path:
            flags &= ~os.O_NOFOLLOW
        return real_open(file, flags, *args, **kwargs)

    def recording(descriptor: int, operation: int) -> None:
        locked.append(descriptor)
        real_flock(descriptor, operation)

    monkeypatch.setattr(os, "open", following)
    monkeypatch.setattr(fcntl, "flock", recording)
    with pytest.raises(TrialFolioError) as raised:
        RankingLock(path).acquire()
    monkeypatch.undo()

    assert raised.value.code == "storage.write_failed"
    assert "symbolic link" in raised.value.message
    assert locked == []
    assert not locked_elsewhere(target)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows behavior")
def test_windows_refuses_a_symbolic_link_at_its_path(tmp_path: Path) -> None:
    # Windows's open follows a symbolic link: the lock refuses one before it locks its target.
    target = tmp_path / "target"
    target.touch()
    path = tmp_path / LOCK_FILE
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("creating a symbolic link needs a privilege on Windows")

    lock = RankingLock(path)
    with pytest.raises(TrialFolioError) as raised:
        lock.acquire()

    assert raised.value.code == "storage.write_failed"
    assert "symbolic link" in raised.value.message
    assert not lock.held


@posix_only
@pytest.mark.parametrize("kind", ["FIFO", "directory"])
def test_a_path_that_isnt_a_regular_file_fails_at_once(tmp_path: Path, kind: str) -> None:
    # A defect found by the review of R04-T08's pull request: opening a FIFO for reading waited
    # for a writer, so a FIFO at the path, which any user can make in `/tmp`, hung every run with
    # a definition; and a directory failed only after 8 opens, as a file replaced each time.
    path = tmp_path / LOCK_FILE
    if kind == "FIFO":
        os.mkfifo(path)
    else:
        path.mkdir()
    lock = RankingLock(path)
    ended: list[BaseException] = []

    def acquire() -> None:
        try:
            lock.acquire()
        except BaseException as error:  # noqa: BLE001 - the test reads it.
            ended.append(error)

    thread = threading.Thread(target=acquire, daemon=True)
    thread.start()
    thread.join(10)
    if thread.is_alive():
        # A writer lets the waiting open go on, so the test fails rather than hangs.
        os.close(os.open(path, os.O_WRONLY | os.O_NONBLOCK))
        thread.join(10)
        pytest.fail("taking the lock waited at the path")

    (error,) = ended
    assert isinstance(error, TrialFolioError)
    assert error.code == "storage.write_failed"
    assert "it isn't a regular file" in error.message
    assert str(path) in error.message
    assert not lock.held


@posix_only
def test_another_descriptors_lock_gives_experiment_locked(tmp_path: Path) -> None:
    path = tmp_path / LOCK_FILE
    lock = RankingLock(path)

    with held(path), pytest.raises(TrialFolioError) as raised:
        lock.acquire()

    assert raised.value.code == "experiment.locked"
    assert "another Trial Folio process" in raised.value.message.replace("Another", "another")
    assert "ApiRankingSystem" in raised.value.message
    assert "ranking lock" in raised.value.message
    assert "Nothing was sent" in raised.value.message
    assert not lock.held


def test_any_other_error_gives_storage_write_failed_naming_the_file_and_the_variable(
    tmp_path: Path,
) -> None:
    path = tmp_path / "no-directory" / LOCK_FILE

    with pytest.raises(TrialFolioError) as raised:
        RankingLock(path).acquire()

    assert raised.value.code == "storage.write_failed"
    assert str(path) in raised.value.message
    assert "TRIALFOLIO_LOCK_DIR" in raised.value.message
    # The logged message leaves the path out.
    assert str(path) not in raised.value.log_message
    assert not path.parent.exists()


@posix_only
def test_a_file_replaced_before_the_lock_is_taken_is_opened_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / LOCK_FILE
    real_flock = fcntl.flock
    replaced: list[bool] = []

    def replacing(descriptor: int, operation: int) -> None:
        # Another program removes the file this process opened, and another creates a new one,
        # before this process locks the first.
        if not replaced:
            path.unlink()
            path.touch()
            replaced.append(True)
        real_flock(descriptor, operation)

    monkeypatch.setattr(fcntl, "flock", replacing)
    with RankingLock(path):
        monkeypatch.setattr(fcntl, "flock", real_flock)
        # The path's file, the new one, is the one locked.
        assert locked_elsewhere(path)

    assert replaced == [True]


@pytest.mark.parametrize(
    ("environ", "platform", "expected"),
    [
        ({}, "linux", Path("/tmp") / LOCK_FILE),
        ({}, "darwin", Path("/tmp") / LOCK_FILE),
        ({"TRIALFOLIO_LOCK_DIR": ""}, "linux", Path("/tmp") / LOCK_FILE),
        ({"TRIALFOLIO_LOCK_DIR": "/srv/locks"}, "linux", Path("/srv/locks") / LOCK_FILE),
        ({"ProgramData": "C:\\ProgramData"}, "win32", Path("C:\\ProgramData") / LOCK_FILE),
        ({"PROGRAMDATA": "D:\\Data"}, "win32", Path("D:\\Data") / LOCK_FILE),
        ({}, "win32", Path("C:\\ProgramData") / LOCK_FILE),
        ({"TRIALFOLIO_LOCK_DIR": "E:\\locks"}, "win32", Path("E:\\locks") / LOCK_FILE),
    ],
)
def test_the_default_directories_are_checked_as_paths(
    environ: dict[str, str], platform: str, expected: Path
) -> None:
    # Checked as paths, without being locked: the default suite never takes the machine's lock.
    assert ranking_lock_path(environ, platform) == expected


@posix_only
def test_a_screen_run_holds_the_lock_from_before_its_first_write_until_it_ends(
    tmp_path: Path,
) -> None:
    content, definition, plan = screen()
    lock = tmp_path / LOCK_FILE
    out = tmp_path / "out"
    with LocalArtifactStore(out) as real:
        store = Watched(real, lock)
        error = Execution(
            plan, plan.plan_hash, "not_required", store, None, clock=FixedClock(), ranking_lock=lock
        ).run(
            content, lambda: SyntheticScreenBacktestClient(response_bytes()), definition=definition
        )

    assert error is None
    assert store.writes[0] == ("plan.json", True)
    assert store.writes[-1] == ("manifest.json", True)
    assert all(locked for _, locked in store.writes)
    assert not locked_elsewhere(lock)


@posix_only
def test_a_new_experiment_holds_the_lock_from_before_its_claim_until_it_ends(
    tmp_path: Path,
) -> None:
    content, definition, plan = experiment()
    lock = tmp_path / LOCK_FILE
    with LocalArtifactStore(tmp_path / "out") as real:
        store = Watched(real, lock)
        error = ExperimentExecution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            SyntheticScreenBacktestClient(response_bytes()),
            command=None,
            clock=FixedClock(),
            ranking_lock=lock,
        ).run(content, definition=definition)

    assert error is None
    assert store.writes[0] == ("experiment.lock", True)
    assert store.writes[-1] == ("sessions/1/manifest.json", True)
    assert all(locked for _, locked in store.writes)
    assert not locked_elsewhere(lock)


@posix_only
def test_a_held_lock_fails_a_screen_run_before_anything_is_sent_or_written(
    tmp_path: Path,
) -> None:
    content, definition, plan = screen()
    lock = tmp_path / LOCK_FILE
    out = tmp_path / "out"
    made: list[object] = []

    def never() -> ScreenBacktestClient:
        made.append(1)
        raise AssertionError("no client is made")

    store = LocalArtifactStore(out)
    execution = Execution(plan, plan.plan_hash, "option", store, COMMAND, ranking_lock=lock)

    with held(lock), pytest.raises(TrialFolioError) as raised:
        execution.run(content, never, definition=definition)

    assert raised.value.code == "experiment.locked"
    assert not execution.claimed
    assert not out.exists()
    assert made == []


@posix_only
def test_a_held_lock_fails_a_new_experiment_before_anything_is_sent_or_written(
    tmp_path: Path,
) -> None:
    content, definition, plan = experiment()
    lock = tmp_path / LOCK_FILE
    out = tmp_path / "out"
    server = FakePortfolio123()
    try:
        credentials = Credentials(canaries.API_ID, canaries.API_KEY)
        with (
            P123ScreenBacktestClient(credentials, endpoint=server.endpoint) as client,
            LocalArtifactStore(out) as store,
        ):
            execution = ExperimentExecution(
                plan, plan.plan_hash, "option", store, client, command=None, ranking_lock=lock
            )
            with held(lock), pytest.raises(TrialFolioError) as raised:
                execution.run(content, definition=definition)
    finally:
        server.close()

    assert raised.value.code == "experiment.locked"
    assert not execution.claimed
    assert not out.exists()
    assert server.requests() == []


@posix_only
def test_a_run_without_a_definition_takes_no_lock(tmp_path: Path) -> None:
    formula = FIXTURES / "screen-configs" / "formula.yaml"
    content = formula.read_bytes()
    plan = build_plan(read_screen_configuration(content, formula.name), installed_versions())
    lock = tmp_path / LOCK_FILE
    server = FakePortfolio123()
    server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
    server.reply(
        "/screen/backtest", Reply(200, (FIXTURES / "responses" / "complete.json").read_bytes())
    )
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    try:
        with held(lock), LocalArtifactStore(tmp_path / "out") as store:
            error = Execution(plan, plan.plan_hash, "option", store, COMMAND).run(
                content, lambda: P123ScreenBacktestClient(credentials, endpoint=server.endpoint)
            )
    finally:
        server.close()

    assert error is None
    with pytest.raises(ValueError, match="ranking lock"):
        Execution(
            plan,
            plan.plan_hash,
            "option",
            LocalArtifactStore(tmp_path / "x"),
            COMMAND,
            ranking_lock=lock,
        )
