"""A user interrupt at each stage of `trialfolio run` exits with `command.interrupted` and 130,
and leaves the records that stage specifies, writing no file twice.

Traces to R01-AC28 and docs/contracts.md, interrupts and endings that decide the error code,
through the CLI's entry function in the test process. The stages:

- at the approval prompt, by a real SIGINT while the CLI reads a pseudo-terminal: nothing is
  left, and nothing is sent. R01-T16 repeats it under the test launcher, in its own process.
- while the claim writes `plan.json`: the claim removes what it created, so nothing is left.
- just after `configuration.yaml`, during authentication, and while `started.json` is written
  after authentication succeeded: a `failed` attempt record, not possibly charged, with nothing
  sent to the backtest path.
- during the backtest request's send: `unknown`, possibly charged.
- after the backtest request got a 400, before the attempt record: the record is written once,
  with `command.interrupted`, keeping Portfolio123's message after "Before that:".
- after the attempt record: the record isn't changed.

Each ending after the claim leaves no manifest, so the output is visibly incomplete. Storage
faults and socket faults inject the interrupts, at the boundaries the release allows.
"""

import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.interface.conftest import (
    AUTHENTICATED,
    Cli,
    FaultyStores,
    Outcome,
    config,
    plan_hash_for,
    serve_success,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.socket_faults import SocketFaults
from tests.support.terminal import PseudoTerminal
from trialfolio.contracts.attempt import AttemptRecord
from trialfolio.storage import ArtifactStore, LocalArtifactStore, StoredFile

FORMULA = config("formula.yaml")
PROVIDER_TEXT = "Unsupported value"
"""Portfolio123's own message for the 400."""


def approved_run(cli: Cli, out: Path, **options: object) -> Outcome:
    return cli(
        "run",
        FORMULA,
        "--out",
        out,
        "--approve",
        plan_hash_for(FORMULA),
        "--json",
        **options,  # pyright: ignore[reportArgumentType]
    )


def interrupted(outcome: Outcome) -> None:
    assert outcome.exit_code == 130, outcome.stderr
    error = outcome.summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == "command.interrupted"


def attempt_directory(out: Path) -> Path:
    (directory,) = (out / "cases").glob("*/attempts/*")
    return directory


def record_of(out: Path) -> AttemptRecord:
    return AttemptRecord.model_validate_json((attempt_directory(out) / "attempt.json").read_bytes())


def written_once(faults: FaultyStores) -> None:
    assert len(faults.published) == len(set(faults.published)), faults.published


class AfterWrite:
    """A `store_factory` whose store runs `action` once `name` is published: here, to install a
    socket fault once the start record is written, so it strikes the request's send only."""

    def __init__(self, name: str, action: Callable[[], object]) -> None:
        self._name = name
        self._action = action

    def __call__(self, root: str) -> ArtifactStore:
        return _AfterWriteStore(LocalArtifactStore(root), self._name, self._action)


class _AfterWriteStore:
    def __init__(self, store: LocalArtifactStore, name: str, action: Callable[[], object]) -> None:
        self._store = store
        self._name = name
        self._action = action

    def check_empty(self) -> None:
        self._store.check_empty()

    def claim(self, path: str, data: bytes) -> StoredFile:
        return self._store.claim(path, data)

    def write(self, path: str, data: bytes) -> StoredFile:
        stored = self._store.write(path, data)
        if path.rsplit("/", 1)[-1] == self._name:
            self._action()
        return stored

    def read(self, path: str) -> bytes:
        return self._store.read(path)


# Before the claim


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals or SIGINT")
def test_ctrl_c_at_the_approval_prompt_leaves_nothing(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"
    with PseudoTerminal() as terminal:

        def interrupt_at_the_prompt() -> None:
            deadline = time.monotonic() + 10
            while b"Type approve" not in terminal._shown:
                if time.monotonic() > deadline:
                    return
                time.sleep(0.01)
            os.kill(os.getpid(), signal.SIGINT)

        watcher = threading.Thread(target=interrupt_at_the_prompt, daemon=True)
        watcher.start()
        outcome = cli(
            "run", FORMULA, "--out", out, "--json", stdin=terminal.stdin, stderr=terminal.stderr
        )
        watcher.join()
        shown = terminal.shown()

    interrupted(outcome)
    assert "Type approve" in shown
    assert "Nothing was sent, and no output was created." in shown
    assert not out.exists()
    assert cli.server.received == ()
    assert outcome.summary["output_dir"] is None


def test_an_interrupt_while_the_claim_writes_the_plan_leaves_nothing(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "parent" / "out"
    claim_files: set[int] = set()
    real_open, real_write = os.open, os.write

    def open_(
        path: str | os.PathLike[str], flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if Path(path).name == "plan.json":
            claim_files.add(descriptor)
        return descriptor

    def write(descriptor: int, data: bytes | memoryview) -> int:
        if descriptor in claim_files:
            raise KeyboardInterrupt
        return real_write(descriptor, data)

    monkeypatch.setattr(os, "open", open_)
    monkeypatch.setattr(os, "write", write)

    outcome = approved_run(cli, out)

    interrupted(outcome)
    assert claim_files, "the claim never opened plan.json"
    assert not (cli.tmp / "parent").exists()
    assert cli.server.received == ()
    assert outcome.summary["output_dir"] is None


# After the claim, before the request's send


def test_an_interrupt_just_after_the_configuration_records_a_failed_attempt(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    faults.fail_after("configuration.yaml", KeyboardInterrupt())

    outcome = approved_run(cli, out, store_factory=faults)

    interrupted(outcome)
    record = record_of(out)
    assert record.outcome == "failed"
    assert record.possibly_charged is False
    assert record.exchanges == ()
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    assert cli.server.received == ()
    assert not (out / "manifest.json").exists()
    assert not (attempt_directory(out) / "started.json").exists()
    assert outcome.summary["ids"]["attempt_id"] == attempt_directory(out).name  # pyright: ignore[reportIndexIssue]
    written_once(faults)


def test_ctrl_c_during_authentication_records_a_failed_attempt(
    cli: Cli, faults: FaultyStores, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    SocketFaults(monkeypatch).interrupt_send()

    outcome = approved_run(cli, out, store_factory=faults)

    interrupted(outcome)
    record = record_of(out)
    assert record.outcome == "failed"
    assert record.possibly_charged is False
    assert [(e.request, e.result) for e in record.exchanges] == [("POST /auth", "interrupted")]
    assert cli.server.received == ()
    assert not (attempt_directory(out) / "started.json").exists()
    assert not (out / "manifest.json").exists()
    written_once(faults)


def test_an_interrupt_while_the_start_record_is_written_sends_nothing_to_the_backtest(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    faults.fail_before("started.json", KeyboardInterrupt())

    outcome = approved_run(cli, out, store_factory=faults)

    interrupted(outcome)
    record = record_of(out)
    assert record.outcome == "failed"
    assert record.possibly_charged is False
    assert [(e.request, e.status) for e in record.exchanges] == [("POST /auth", 200)]
    assert cli.server.requests() == ["POST /auth"]
    assert not (attempt_directory(out) / "started.json").exists()
    assert outcome.summary["counts"]["provider_requests"] == 0  # pyright: ignore[reportIndexIssue]
    written_once(faults)


# During and after the request's send


def test_ctrl_c_during_the_backtest_send_is_unknown_and_possibly_charged(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    sockets = SocketFaults(monkeypatch)

    outcome = approved_run(
        cli, out, store_factory=AfterWrite("started.json", sockets.interrupt_send)
    )

    interrupted(outcome)
    record = record_of(out)
    assert record.outcome == "unknown"
    assert record.possibly_charged is True
    assert [(e.request, e.result) for e in record.exchanges] == [
        ("POST /auth", "response"),
        ("POST /screen/backtest", "interrupted"),
    ]
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    assert cli.server.requests() == ["POST /auth"]
    assert (attempt_directory(out) / "started.json").exists()
    assert not (out / "manifest.json").exists()
    assert outcome.summary["counts"]["provider_requests"] == 1  # pyright: ignore[reportIndexIssue]


def test_an_interrupt_after_a_400_before_the_attempt_record_keeps_portfolio123s_message(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", Reply(400, PROVIDER_TEXT.encode()))
    faults.fail_before("attempt.json", KeyboardInterrupt())

    outcome = approved_run(cli, out, store_factory=faults)

    interrupted(outcome)
    record = record_of(out)
    assert record.outcome == "failed"
    assert record.possibly_charged is True
    assert [(e.request, e.status) for e in record.exchanges] == [
        ("POST /auth", 200),
        ("POST /screen/backtest", 400),
    ]
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    before_that = record.error.message.split("Before that:", 1)[1]
    assert PROVIDER_TEXT in before_that
    assert cli.server.requests() == ["POST /auth", "POST /screen/backtest"]
    assert not (out / "manifest.json").exists()
    written_once(faults)


def test_an_interrupt_after_the_attempt_record_leaves_it_unchanged(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", Reply(400, PROVIDER_TEXT.encode()))
    faults.fail_after("attempt.json", KeyboardInterrupt())

    outcome = approved_run(cli, out, store_factory=faults)

    interrupted(outcome)
    record = record_of(out)
    assert record.outcome == "failed"
    assert record.error is not None
    assert record.error.code == "provider.unsupported_capability"
    assert PROVIDER_TEXT in record.error.message
    assert not (out / "manifest.json").exists()
    assert not (out / "report.html").exists()
    written_once(faults)


def test_an_interrupt_after_a_successful_attempt_record_leaves_no_manifest(
    cli: Cli, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "out"
    serve_success(cli.server)
    faults.fail_after("attempt.json", KeyboardInterrupt())

    outcome = approved_run(cli, out, store_factory=faults)

    interrupted(outcome)
    record = record_of(out)
    assert record.outcome == "succeeded"
    assert record.error is None
    assert (attempt_directory(out) / "response.json").exists()
    assert not (out / "normalized").exists()
    assert not (out / "manifest.json").exists()
    written_once(faults)
