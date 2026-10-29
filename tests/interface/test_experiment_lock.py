"""The experiment lock, through `trialfolio run`: while one process runs an experiment, another run
of it into the same directory fails with `experiment.locked`, sends nothing, and changes nothing,
until the first process ends, however it ends; and of two new experiments that claim one directory
at once, at most one succeeds, and the other leaves its files alone.

Traces to R03-AC09's interface part (`tests/core/test_experiment_lock.py` is its core part), and
to docs/contracts.md, the lock (when it's taken, how long it's held, and its release when the
process ends), running an experiment (a resume takes the lock before it reads any record, and
reserves its session only once approved), and JSON summary (`output_dir` and `counts` after
`experiment.locked`). The resume runs under the test launcher, in a new process, under a real
pseudo-terminal, where it waits at its prompt holding the lock until it's killed with `SIGKILL`;
the run it locks out runs through the CLI's entry function in the test process, and the
experiment it resumes is written with the experiment builder. The two claims run under the test
launcher, in two processes started at once, in two rounds, each over a fake server of its own,
which holds the claim that took the lock at its authentication call until the other claim has
ended. Each test runs over the fake server.
"""

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tests.support import canaries, launcher, terminal
from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    REFUSED,
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns,
)
from tests.support.fake_portfolio123 import AUTH, BACKTEST, FakePortfolio123, Reply
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.experiment_records import read_experiment
from trialfolio.storage import LOCK_LINE, LOCK_PATH, LocalArtifactStore

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no pseudo-terminals and no SIGKILL"
)

EXAMPLE = experiment_config("example.yaml")
RACE_SECONDS = 60.0
"""How long the claim that took the lock is held for the other to end: far longer than a process
takes to start and try its claim, so only two claims that both took the lock wait it out."""

type Builder = ExperimentBuilder[Outcome]


class Terminal(terminal.Terminal):
    """The terminal, whose process the test can kill with `SIGKILL` as it waits at a prompt."""

    def kill(self) -> int:
        """Kills the process with `SIGKILL`, and returns its exit code once it has ended."""
        os.kill(self._process.pid, signal.SIGKILL)
        return self.wait()


def files(root: Path) -> dict[str, tuple[int, bytes] | None]:
    """Everything under `root`, hidden entries included: each file's size and bytes, by its name,
    or None for a directory."""
    return {
        path.relative_to(root).as_posix(): (
            None if path.is_dir() else (path.stat().st_size, path.read_bytes())
        )
        for path in sorted(root.rglob("*"))
    }


@posix_only
def test_a_run_while_a_resume_waits_at_its_prompt_is_locked_out_until_the_resume_is_killed(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # Trial Folio's authentication call gets a 401, so no case's request is sent: each is due.
    assert experiments.run(EXAMPLE, out, authenticates=[REFUSED]).exit_code == 6
    argv = ("run", EXAMPLE, "--out", out, "--approve", plan_hash(EXAMPLE, out), "--json")
    received = len(cli.server.received)

    command = launcher.command(cli.server.endpoint, "run", EXAMPLE, "--out", out)
    with Terminal(command, cwd=cli.tmp) as waiting:
        # It holds the lock from before it reads the records, through its prompt.
        waiting.wait_for("Type approve to run this plan")
        before = files(out)
        locked = cli(*argv)
        after = files(out)
        killed = waiting.kill()

    assert killed == -signal.SIGKILL
    assert locked.exit_code == 4
    error = locked.error
    assert error["code"] == "experiment.locked"
    assert "Nothing was sent, and nothing was written." in error["message"]
    # It wrote nothing, so it gives no output directory, and read nothing, so no counts.
    assert (locked.summary["output_dir"], locked.summary["counts"]) == (None, {})
    assert after == before
    assert not (out / "sessions/2").exists()
    assert len(cli.server.received) == received

    # The operating system released the lock with the killed process, which had reserved no
    # session: the same command takes the lock, and resumes as session 2.
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", *[returns() for _ in range(5)])

    resumed = cli(*argv)

    assert resumed.exit_code == 0, resumed.stderr
    assert cli.server.requests()[received:] == [AUTH, *[BACKTEST] * 5]
    resumed_manifest = ExperimentManifest.model_validate_json(
        (out / "sessions/2/manifest.json").read_bytes()
    )
    assert (resumed_manifest.session, resumed_manifest.outcome) == (2, "completed")


def claim_at_once(out: Path, cwd: Path) -> tuple[list[Outcome], list[str]]:
    """Runs two new experiments of `example.yaml` into `out`, approved, in two processes started
    at once under the test launcher, over a new fake server, and gives each one's outcome, and
    the requests the server received. The server holds each authentication call's reply until
    one of the processes has ended, so the process that claimed the directory holds the lock
    until the other has tried to claim it, however late that one starts. It has replies for both,
    so that two claims that both succeeded could each complete, once `RACE_SECONDS` have
    passed."""
    release = threading.Event()
    authenticated = Reply(200, canaries.TOKEN.encode(), release=release)
    server = FakePortfolio123()
    try:
        server.reply("/auth", authenticated, authenticated)
        server.reply("/screen/backtest", *[returns() for _ in range(10)])
        command = launcher.command(
            server.endpoint, "run", EXAMPLE, "--out", out, "--approve", plan_hash(EXAMPLE, out)
        )
        processes = [
            subprocess.Popen(
                [*command, "--json"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
            )
            for _ in range(2)
        ]
        deadline = time.monotonic() + RACE_SECONDS
        while all(p.poll() is None for p in processes) and time.monotonic() < deadline:
            time.sleep(0.01)
        release.set()
        ended: list[Outcome] = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=120)
            ended.append(Outcome(process.returncode, stdout, stderr))
        return ended, server.requests()
    finally:
        server.close()


def test_two_new_experiments_claiming_one_directory_at_once_give_at_most_one_success(
    cli: Cli,
) -> None:
    cli.ready()
    successes = 0
    for place in (1, 2):
        out = cli.tmp / f"experiment-{place}"

        ended, requests = claim_at_once(out, cli.tmp)

        succeeded = [outcome.exit_code for outcome in ended].count(0)
        assert succeeded <= 1, ended
        for outcome in ended:
            if outcome.exit_code != 0:
                assert outcome.exit_code == 4, outcome.stderr
                assert outcome.error_code in ("output.not_empty", "experiment.locked")
        if succeeded:
            successes += 1
            # The other left its files alone: they pass a resume's records check, the lock file
            # holds its line, and the server received one experiment's requests.
            with LocalArtifactStore(out) as store:
                saved = read_experiment(store)
            assert saved.manifest is not None and saved.manifest.outcome == "completed"
            assert (out / LOCK_PATH).read_bytes() == LOCK_LINE
            assert requests == [AUTH, *[BACKTEST] * 5]
    # Neither succeeds only when one takes the lock in the moment between the other's creating
    # experiment.lock and locking it. If neither ever did, the other's files couldn't be shown to
    # be left alone: as when a claim that fails removes the file another claim created, so that
    # both fail.
    assert successes >= 1
