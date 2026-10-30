"""The core tests' fixtures: what the store syncs, failures injected into its file operations
(AGENTS.md, verification expectations: injected storage failures), an attempt run over the fake
Portfolio123 server, below `urllib3`, whose saved response the normalization tests read, and a
complete run, with its report and manifest, for the report tests.

TS-T04 moved the helpers the tests import to modules under `tests/support/`: `SyncLog`, `Faults`,
and their effects to `file_faults.py`, the runs' types and `execute_run` to `screen_runs.py`, the
fixtures' paths to `paths.py`, and `snapshot` to `directories.py`, which held the same function. So
this file keeps the fixtures. TS-T05 wrote `write_run`'s run through `Execution`, which builds its
manifest, where R01-T14 had left the fixture building one itself, ahead of the CLI.
"""

import itertools
import json
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest

from tests.support.clock import FixedClock
from tests.support.fake_portfolio123 import AUTHENTICATED, CREDENTIALS, FakePortfolio123, Reply
from tests.support.file_faults import Faults, SyncLog
from tests.support.screen_runs import (
    RUN_STARTED,
    VERSIONS,
    Execute,
    Normalized,
    WriteRun,
    Written,
    run_command,
)
from trialfolio.attempts import Attempt
from trialfolio.configuration import read_screen_configuration
from trialfolio.execution import Execution
from trialfolio.planning import build_plan
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.storage import LocalArtifactStore


@pytest.fixture
def sync_log(monkeypatch: pytest.MonkeyPatch) -> SyncLog:
    """Records every sync, whether `os.fsync` or, on macOS, `fcntl.F_FULLFSYNC`."""
    return SyncLog(monkeypatch)


@pytest.fixture
def faults(monkeypatch: pytest.MonkeyPatch) -> Faults:
    return Faults(monkeypatch)


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
        server.reply("/auth", AUTHENTICATED)
        server.reply("/screen/backtest", Reply(200, body))
        with P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint) as client:
            result = Attempt(plan, plan.plan_hash, store).run(client)
        assert result.record.outcome == "succeeded"
        assert result.record.response is not None
        sent = json.loads(server.received[-1].body)
        return Normalized(store, plan, configuration, result.record.response, sent)

    yield run
    server.close()


@pytest.fixture
def write_run(tmp_path: Path) -> Iterator[WriteRun]:
    """Writes a complete run through `Execution`, as `trialfolio run` does once it's approved with
    `--approve`: plans the configuration's bytes, claims a new output directory with `plan.json`,
    saves `configuration.yaml`, runs the attempt with the real client over the fake server,
    normalizes a response that succeeded, writes the report, and then the manifest. `backtest` is
    the fake server's reply to the request, and `authentication` its reply to Trial Folio's
    authentication call. The clock reads a second after `RUN_STARTED`, and a second later at each
    reading after it.

    `synthetic` labels the run as `trialfolio demo` writes it, with its command and the approval
    `not_required`, although the attempt still reaches the fake server, which no synthetic run
    Trial Folio writes does."""
    server = FakePortfolio123()
    outputs = itertools.count(1)

    def run(
        content: bytes,
        backtest: Reply | None = None,
        *,
        authentication: Reply | None = None,
        synthetic: bool = False,
    ) -> Written:
        plan = build_plan(read_screen_configuration(content, "configuration.yaml"), VERSIONS)
        out = tmp_path / f"run-{next(outputs)}"
        server.reply("/auth", authentication or AUTHENTICATED)
        if backtest is not None:
            server.reply("/screen/backtest", backtest)
        before = len(server.received)
        execution = Execution(
            plan,
            plan.plan_hash,
            "not_required" if synthetic else "option",
            LocalArtifactStore(out),
            run_command(plan, synthetic=synthetic),
            clock=FixedClock(RUN_STARTED + timedelta(seconds=1)),
        )
        execution.run(
            content, lambda: P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint)
        )
        return Written.of(out, plan, execution, tuple(server.requests()[before:]))

    yield run
    server.close()
