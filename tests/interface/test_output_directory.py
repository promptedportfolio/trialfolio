"""A command refuses an output directory that isn't empty when it starts, before anything is
written, and changes nothing in it; and a directory another process writes to before `run`
claims it fails the claim, leaving only the other process's files.

Traces to R01-AC15 and R01-AC27: `run`, `demo`, and `report` each fail with `output.not_empty`
and exit 4, and the fake server receives nothing. R01-AC27 is checked twice: with a second process
writing while `run`, under the test launcher on a terminal, waits at the approval prompt; and in
the test process, where the other process's file appears just before the claim, through the entry
function's `store_factory`.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import (
    Cli,
    Outcome,
    config,
    metadata,
    occupied,
    plan_hash_for,
    serve_success,
)
from trialfolio.storage import ArtifactStore, LocalArtifactStore, StoredFile


def assert_not_empty(cli: Cli, outcome: Outcome) -> None:
    assert outcome.exit_code == 4
    error = cast("dict[str, str]", outcome.summary["error"])
    assert error["code"] == "output.not_empty"
    assert outcome.summary["output_dir"] is None
    assert outcome.summary["outputs"] == {}
    assert cli.server.requests() == []


FILES = pytest.mark.parametrize("name", ["results.txt", ".hidden"], ids=["a-file", "a-hidden-file"])


@FILES
def test_run_refuses_a_directory_that_isnt_empty(cli: Cli, name: str) -> None:
    cli.ready()
    serve_success(cli.server)
    out = occupied(cli, name)
    before = metadata(out)
    approve = plan_hash_for(config("formula.yaml"))

    outcome = cli("run", config("formula.yaml"), "--out", out, "--approve", approve, "--json")

    assert_not_empty(cli, outcome)
    assert metadata(out) == before


@FILES
def test_demo_refuses_a_directory_that_isnt_empty(cli: Cli, name: str) -> None:
    cli.accept_license()
    out = occupied(cli, name)
    before = metadata(out)

    outcome = cli("demo", "--out", out, "--json")

    assert_not_empty(cli, outcome)
    assert metadata(out) == before


@FILES
def test_report_refuses_a_directory_that_isnt_empty(cli: Cli, name: str) -> None:
    cli.accept_license()
    run = cli.tmp / "run"
    assert cli("demo", "--out", run).exit_code == 0
    out = occupied(cli, name)
    before = metadata(out)
    run_before = metadata(run)

    outcome = cli("report", run, "--out", out, "--json")

    assert_not_empty(cli, outcome)
    assert metadata(out) == before
    assert metadata(run) == run_before


class Intruded:
    """The real store, with another process's file written into the output directory just
    before the claim: as when another process writes there while `run` waits for approval."""

    def __init__(self, root: str) -> None:
        self._store = LocalArtifactStore(root)
        self._root = Path(root)

    def check_empty(self) -> None:
        self._store.check_empty()

    def claim(self, path: str, data: bytes) -> StoredFile:
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "other.txt").write_bytes(b"another process's file\n")
        return self._store.claim(path, data)

    def write(self, path: str, data: bytes, *, logged_as: str | None = None) -> StoredFile:
        return self._store.write(path, data, logged_as=logged_as)

    def discard(self, path: str, data: bytes) -> None:
        self._store.discard(path, data)

    def read(self, path: str) -> bytes:
        return self._store.read(path)


def intruded(root: str) -> ArtifactStore:
    return Intruded(root)


def test_a_file_written_before_the_claim_fails_it_and_is_left_alone(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"
    approve = plan_hash_for(config("formula.yaml"))

    outcome = cli(
        "run",
        config("formula.yaml"),
        "--out",
        out,
        "--approve",
        approve,
        "--json",
        store_factory=intruded,
    )

    assert_not_empty(cli, outcome)
    assert sorted(os.listdir(out)) == ["other.txt"]
    assert (out / "other.txt").read_bytes() == b"another process's file\n"
    # Nothing of its own, logs included, and no log file anywhere.
    assert not list(cli.home.rglob("*.log"))


ANOTHER_PROCESS = """
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
(out / "other.txt").write_bytes(b"another process's file\\n")
"""


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")
def test_another_process_writing_while_run_waits_for_approval_fails_the_claim(cli: Cli) -> None:
    cli.ready()
    serve_success(cli.server)
    out = cli.tmp / "out"

    with cli.on_terminal("run", config("formula.yaml"), "--out", out, "--json") as terminal:
        terminal.wait_for("Type approve")
        subprocess.run([sys.executable, "-c", ANOTHER_PROCESS, str(out)], check=True)
        terminal.press("approve\n")
        exit_code = terminal.wait()

    assert exit_code == 4, terminal.shown()
    summary = json.loads(terminal.stdout)
    assert summary["error"]["code"] == "output.not_empty"
    assert summary["output_dir"] is None
    assert cli.server.received == ()
    assert sorted(os.listdir(out)) == ["other.txt"]
    assert (out / "other.txt").read_bytes() == b"another process's file\n"
    assert not list(cli.home.rglob("*.log"))
