"""The ranking lock through `trialfolio run`: the CLI gives the core the lock's file, from
`TRIALFOLIO_LOCK_DIR`, and a run that finds it held, or can't take it, fails before sending or
writing anything.

Traces to R04-AC05, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_lock.py`, with each process's `TRIALFOLIO_LOCK_DIR` the test's own
directory: while a `trialfolio run` of `ranking-example.yaml` holds the lock, the server holding
its first `rank_update`'s reply, another process's run of `definition.yaml`, and of
`ranking-example.yaml` into another directory, each fail with `experiment.locked`, exit 4, a
message that names the ranking lock, and nothing sent or written; once the reply goes, the first
run completes, each `POST /rank` followed by its own `POST /screen/backtest`, and then, or once
the first was killed with `SIGKILL`, the other's command succeeds. A resume meets the lock before
its session record. A run that waits at its approval prompt doesn't hold the lock, and neither
does a formula-ranked run or a resume that sends nothing, each of which runs beside a run that
holds it. A `TRIALFOLIO_LOCK_DIR` that names no directory, and a lock file this process can't
open, give `storage.write_failed`, exit 4, before anything is sent or written, with a message that
names the file and the variable. Also to the JSON summary of an experiment that finds the ranking
lock held: its cases, `counts` `{}`, and `output_dir` `null` (docs/contracts.md, JSON summary).
R04-T12 wrote them. A snapshot beside a run that holds the lock is in
`tests/interface/test_ranking_snapshot.py`, which R04-T10 wrote ahead of this task.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, FaultyStores, Outcome, plan_hash_for, response
from tests.support import launcher
from tests.support.experiment_builder import (
    AUTHENTICATED,
    RANK_UPDATED,
    ExperimentBuilder,
    experiment_config,
    held,
    plan_hash,
    returns,
    returns_each,
)
from tests.support.fake_portfolio123 import Reply
from trialfolio.configuration import read_experiment_configuration_v1_1
from trialfolio.planning import build_experiment_plan_v1_1, installed_versions
from trialfolio.ranking_lock import LOCK_DIRECTORY_VARIABLE, LOCK_FILE, RankingLock

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no pseudo-terminals, and no SIGKILL"
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
EXAMPLE = experiment_config("ranking-example.yaml")
DEFINITION = FIXTURES / "screen-configs" / "definition.yaml"
FORMULA = FIXTURES / "screen-configs" / "formula.yaml"
LOCKED = (
    "Another Trial Folio process on this machine is writing ApiRankingSystem, for an experiment"
    " or a screen run whose ranking is a definition: it holds the ranking lock."
)


def error(outcome: Outcome) -> dict[str, str]:
    return cast("dict[str, str]", outcome.summary["error"])


def serve_run(cli: Cli) -> None:
    """Scripts a screen run with a definition: authentication, its `POST /rank`, its backtest."""
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", RANK_UPDATED, method="POST")
    cli.server.reply("/screen/backtest", response("complete.json"))


def screen_run(cli: Cli, out: Path, config: Path = DEFINITION) -> Outcome:
    return cli("run", config, "--out", out, "--approve", plan_hash_for(config), "--json")


def wait_for_requests(cli: Cli, count: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + 60
    while len(cli.server.received) < count:
        assert process.poll() is None, "the first run ended before its requests arrived"
        assert time.monotonic() < deadline, "the requests never arrived"
        time.sleep(0.01)


def assert_locked(outcome: Outcome, out: Path) -> None:
    assert outcome.exit_code == 4, outcome.stderr
    assert error(outcome)["code"] == "experiment.locked"
    assert LOCKED in error(outcome)["message"]
    assert outcome.summary["output_dir"] is None
    assert not out.exists()


def pairs(requests: list[str]) -> bool:
    """Whether each `POST /screen/backtest` follows its own `POST /rank`, with nothing between."""
    sends = [request for request in requests if request != "POST /auth"]
    half = len(sends) // 2
    return sends[0::2] == ["POST /rank"] * half and sends[1::2] == ["POST /screen/backtest"] * half


# Two processes


def test_runs_that_find_the_lock_held_send_and_write_nothing_until_it_ends(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """The first run, in a process of its own, holds the lock while the server holds its first
    `rank_update`'s reply. A screen run and an experiment, in this process, find it held. Once
    the reply goes, the first completes, its cases' calls never interleaved, and then the screen
    run succeeds."""
    cli.ready()
    release = threading.Event()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply(
        "/rank",
        Reply(200, RANK_UPDATED.body, release=release),
        *(RANK_UPDATED,) * 3,
        method="POST",
    )
    cli.server.reply("/screen/backtest", *returns_each(4))
    first = cli.tmp / "first"
    argv = ["run", EXAMPLE, "--out", first, "--approve", plan_hash(EXAMPLE, first)]
    stderr_path = cli.tmp / "first-stderr.txt"
    with stderr_path.open("w") as stderr:
        process = subprocess.Popen(
            launcher.command(cli.server.endpoint, *argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
        )
        try:
            wait_for_requests(cli, 2, process)  # its authentication, and its first POST /rank
            screen = screen_run(cli, cli.tmp / "screen")
            experiment = experiments.run(EXAMPLE, cli.tmp / "second")
            received_while_held = cli.server.requests()
        finally:
            release.set()
        assert process.wait(60) == 0, stderr_path.read_text()

    assert_locked(screen, cli.tmp / "screen")
    assert_locked(experiment, cli.tmp / "second")
    # The experiment's summary gives its cases, and `counts` {}, as after any experiment.locked.
    assert len(cast("list[object]", experiment.summary["cases"])) == 4
    assert experiment.summary["counts"] == {}
    assert received_while_held == ["POST /auth", "POST /rank"]
    requests = cli.server.requests()
    assert len(requests) == 9
    assert pairs(requests)

    serve_run(cli)
    after = screen_run(cli, cli.tmp / "screen")

    assert after.exit_code == 0, after.stderr


@posix_only
def test_a_run_killed_while_it_holds_the_lock_leaves_none(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """The operating system releases the lock when the process ends, however it ends, so a run
    killed with `SIGKILL` leaves no stale lock (the ranking lock, when it's taken)."""
    cli.ready()
    experiments.kill(EXAMPLE, cli.tmp / "killed", ranks=(held(RANK_UPDATED),), received=2)
    serve_run(cli)

    outcome = screen_run(cli, cli.tmp / "screen")

    assert outcome.exit_code == 0, outcome.stderr


def test_a_resume_meets_the_lock_before_its_session_record(
    cli: Cli, experiments: ExperimentBuilder[Outcome], faults: FaultyStores
) -> None:
    """An experiment stopped at its second case's `rank-update-request.json`, before that case's
    `rank_update` was sent, has three cases due. While another process holds the ranking lock, its
    resume fails with `experiment.locked`, sends nothing, and reserves no new session; once the
    lock is free, the same command resumes it, and sends the cases due (the ranking lock, when
    it's taken; running an experiment, step 7)."""
    cli.ready()
    out = cli.tmp / "experiment"
    read = read_experiment_configuration_v1_1(EXAMPLE.read_bytes(), EXAMPLE.name, EXAMPLE)
    second = build_experiment_plan_v1_1(read, installed_versions()).cases[1].case_id
    faults.fail_before(f"{second}/rank-update-request.json", KeyboardInterrupt())
    stopped = experiments.run(
        EXAMPLE, out, ranks=(RANK_UPDATED,), sends=(returns(),), store_factory=faults
    )
    assert stopped.exit_code == 130, stopped.stderr
    received = cli.server.requests()
    assert received == ["POST /auth", "POST /rank", "POST /screen/backtest"]

    with RankingLock(cli.locks / LOCK_FILE):
        locked = experiments.run(EXAMPLE, out)

    assert locked.exit_code == 4, locked.stderr
    assert error(locked)["code"] == "experiment.locked"
    assert LOCKED in error(locked)["message"]
    assert locked.summary["output_dir"] is None
    assert locked.summary["counts"] == {}
    assert len(cast("list[object]", locked.summary["cases"])) == 4
    assert cli.server.requests() == received
    assert sorted(path.name for path in (out / "sessions").iterdir()) == ["1"]

    resumed = experiments.run(EXAMPLE, out, ranks=(RANK_UPDATED,) * 3, sends=returns_each(3))

    assert resumed.exit_code == 0, resumed.stderr
    sent = cli.server.requests()[len(received) :]
    assert sent[0] == "POST /auth"
    assert len(sent) == 7
    assert pairs(sent)


# What doesn't hold the lock, and what runs beside it


@posix_only
def test_a_run_waiting_at_its_approval_prompt_doesnt_hold_the_lock(cli: Cli) -> None:
    """The lock is taken after the approval and the check for credentials, so a run that waits
    for its approval doesn't hold it (the ranking lock, when it's taken)."""
    cli.ready()

    with cli.on_terminal("run", DEFINITION, "--out", cli.tmp / "waiting") as terminal:
        terminal.wait_for("Type approve")
        with RankingLock(cli.locks / LOCK_FILE) as lock:
            taken = lock.held
        terminal.press("no\n")
        assert terminal.wait() == 2

    assert taken
    assert cli.server.requests() == []


def test_a_formula_ranked_run_and_a_resume_that_sends_nothing_run_beside_a_held_lock(
    cli: Cli, experiments: ExperimentBuilder[Outcome]
) -> None:
    """Neither writes `ApiRankingSystem`, so neither takes the lock (the ranking lock, which runs
    take it)."""
    cli.ready()
    out = cli.tmp / "experiment"
    complete = experiments.run(EXAMPLE, out, ranks=(RANK_UPDATED,) * 4, sends=returns_each(4))
    assert complete.exit_code == 0, complete.stderr
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("complete.json"))

    with RankingLock(cli.locks / LOCK_FILE):
        formula = screen_run(cli, cli.tmp / "formula", FORMULA)
        resumed = experiments.run(EXAMPLE, out)

    assert formula.exit_code == 0, formula.stderr
    assert resumed.exit_code == 0, resumed.stderr
    assert cast("dict[str, object]", resumed.summary["ids"])["session"] == 2


# When the lock can't be taken


@pytest.mark.parametrize("kind", ["screen", "experiment"])
def test_a_lock_directory_that_doesnt_exist_is_storage_write_failed(
    cli: Cli,
    experiments: ExperimentBuilder[Outcome],
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    """Trial Folio creates no directory for the lock, so a `TRIALFOLIO_LOCK_DIR` that names none
    fails the run before anything is sent or written, and the message names the file and the
    variable (the ranking lock, when it can't be opened or locked)."""
    cli.ready()
    missing = cli.tmp / "no such directory"
    monkeypatch.setenv(LOCK_DIRECTORY_VARIABLE, str(missing))
    out = cli.tmp / "run"

    outcome = screen_run(cli, out) if kind == "screen" else experiments.run(EXAMPLE, out)

    assert outcome.exit_code == 4, outcome.stderr
    assert error(outcome)["code"] == "storage.write_failed"
    assert str(missing / LOCK_FILE) in error(outcome)["message"]
    assert LOCK_DIRECTORY_VARIABLE in error(outcome)["message"]
    assert not out.exists()
    assert cli.server.requests() == []
    assert not missing.exists()


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,  # pyright: ignore[reportAttributeAccessIssue,unused-ignore]
    reason="a file mode that refuses this process: POSIX, and not the superuser",
)
def test_a_lock_file_this_process_cant_open_is_storage_write_failed(cli: Cli) -> None:
    cli.ready()
    lock_file = cli.locks / LOCK_FILE
    lock_file.touch()
    lock_file.chmod(0)
    out = cli.tmp / "run"
    try:
        outcome = screen_run(cli, out)
    finally:
        lock_file.chmod(0o644)

    assert outcome.exit_code == 4, outcome.stderr
    assert error(outcome)["code"] == "storage.write_failed"
    assert str(lock_file) in error(outcome)["message"]
    assert LOCK_DIRECTORY_VARIABLE in error(outcome)["message"]
    assert not out.exists()
    assert cli.server.requests() == []
