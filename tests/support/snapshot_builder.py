"""The snapshot builder: writes a ranking snapshot with `trialfolio run`, through the CLI's entry
function in the test process, over the fake Portfolio123 server (release 0.4.0, test pairing). It
isn't a double: each snapshot is real `trialfolio run` output.

Each snapshot is of a configuration in `ranking-snapshot-configs/`, `example.yaml` unless the test
gives another, approved with `--approve` and its plan's hash, and written with the fixed clock.
The fake server answers its `GET /rank` with `responses/rank-get.json`, or one of its changes,
with a 200, or with a failure. Each snapshot has a server of its own, stopped before the builder
returns.

`naming` then writes a copy of a screen's or an experiment's configuration whose ranking is a
definition, beside the snapshot, with `ranking.snapshot` naming it in place of the definition and
its ranking method, so a test reads the snapshot as a ranking.

`serve_snapshot` and `take_snapshot` script and take the example's snapshot through the tests'
`Cli`, over the test's own server, for the CLI's tests. TS-T03 moved them here from
`tests/interface/test_ranking_snapshot.py`, from which `test_ranking_pause.py` imported them.

`take` takes the example's snapshot through the core instead, with `SnapshotExecution`, over the
test's own server, for the core's tests: `snapshot_plan` plans a snapshot configuration,
`system_reply` changes `rank-get.json`'s fields, and `read_json` and `artifact_id` read what a
snapshot wrote. TS-T07 moved them here from tests/core/test_ranking_snapshot.py, when it separated
the tests of reading a snapshot as a configuration's ranking into
tests/core/test_ranking_from_snapshot.py, which takes its snapshots with them (docs/test-refactoring.md, modules to separate).

The snapshot's values are invented, but nothing labels it synthetic, so a committed copy would
read as a ranking system Portfolio123 returned. It exists only in the test's temporary directory.
R04-T10 wrote it, with the snapshot's tests.
"""

import json
import os
import re
from pathlib import Path
from typing import Final

import pytest

from tests.support.cli import Cli
from tests.support.clock import FixedClock
from tests.support.environment import Outcome, isolated, run_cli
from tests.support.fake_portfolio123 import (
    AUTHENTICATED,
    CREDENTIALS,
    FakePortfolio123,
    Reply,
    response,
)
from tests.support.paths import RESPONSES, SNAPSHOT_CONFIGS
from tests.support.storage_faults import StorageFaults
from trialfolio.canonical import sha256_hex
from trialfolio.configuration import read_ranking_snapshot_configuration
from trialfolio.contracts.ranking_snapshot import RankingSnapshotPlan, SnapshotCommandRecord
from trialfolio.errors import TrialFolioError
from trialfolio.planning import build_snapshot_plan, installed_versions
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.snapshot_execution import SnapshotExecution
from trialfolio.storage import LocalArtifactStore

EXAMPLE: Final = SNAPSHOT_CONFIGS / "example.yaml"
"""The snapshot configuration a snapshot is of, unless a test gives another."""

_DEFINITION: Final = re.compile(
    r"^(?P<indent> *)definition: .*\n(?P=indent)ranking_method: .*\n", re.MULTILINE
)
"""A ranking given as a definition, with its ranking method, as the fixtures write it."""


def rank_get(name: str = "rank-get.json") -> Reply:
    """A 200 whose body is the `rank_get` response fixture `name`."""
    return Reply(200, (RESPONSES / name).read_bytes())


def snapshot_plan_hash(configuration: str = "example.yaml") -> str:
    """The hash of the plan of the snapshot configuration `configuration`, in
    `ranking-snapshot-configs/`, with the installed versions."""
    path = SNAPSHOT_CONFIGS / configuration
    read = read_ranking_snapshot_configuration(path.read_bytes(), path.name)
    return build_snapshot_plan(read, installed_versions()).plan_hash


def serve_snapshot(cli: Cli, reply: Reply | None = None) -> None:
    """Scripts a snapshot on `cli`'s server: authentication, then the `GET /rank`'s `reply`,
    `rank-get.json`'s 200 by default."""
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", rank_get() if reply is None else reply, method="GET")


def take_snapshot(cli: Cli, out: Path, *args: str, timeout: int | None = None) -> Outcome:
    """Runs the example's snapshot into `out` through `cli`, approved with `--approve`, with the
    request timeout `timeout`, or the CLI's own."""
    return cli(
        "run", EXAMPLE, "--out", out, "--approve", snapshot_plan_hash(), *args, timeout=timeout
    )


class SnapshotBuilder:
    """Writes snapshots with `trialfolio run`, in the test process, with a temporary home and
    without the variables Trial Folio reads, apart from the license acknowledgment and the canary
    credentials (`tests/support/environment.py`)."""

    def __init__(self, home: Path) -> None:
        self._home = home

    def snapshot(
        self,
        out: Path,
        reply: Reply | str = "rank-get.json",
        *,
        configuration: str = "example.yaml",
    ) -> Path:
        """Takes a snapshot of the configuration `configuration` into the new output directory
        `out`, with the server answering its `GET /rank` with `reply`, or the `rank_get`
        response fixture it names, and returns `out`."""
        path = SNAPSHOT_CONFIGS / configuration
        server = FakePortfolio123()
        try:
            server.reply("/auth", AUTHENTICATED)
            server.reply(
                "/rank", rank_get(reply) if isinstance(reply, str) else reply, method="GET"
            )
            self._home.mkdir(parents=True, exist_ok=True)
            with isolated(self._home, licensed=True, credentials=True):
                outcome = run_cli(
                    "run",
                    path,
                    "--out",
                    out,
                    "--approve",
                    snapshot_plan_hash(configuration),
                    endpoint=server.endpoint,
                )
        finally:
            server.close()
        # A snapshot that fails still writes its manifest.
        assert (out / "manifest.json").is_file(), outcome.stderr
        return out


def naming(configuration: Path, snapshot: Path, into: Path) -> Path:
    """Writes a copy of `configuration`, a screen's or an experiment's whose ranking is a
    definition, into the directory `into`, with `ranking.snapshot` naming `snapshot`, by its path
    relative to `into`, in place of the definition and its ranking method; and returns the copy's
    path."""
    relative = os.path.relpath(snapshot, into).replace(os.sep, "/")
    text, replaced = _DEFINITION.subn(
        lambda found: f"{found['indent']}snapshot: '{relative}'\n",
        configuration.read_text(encoding="utf-8"),
    )
    assert replaced == 1, "the configuration gives its ranking as a definition, once"
    into.mkdir(parents=True, exist_ok=True)
    path = into / configuration.name
    path.write_text(text, encoding="utf-8")
    return path


# Through the core, for the core's tests

STARTED_AT = FixedClock()()
SNAPSHOT_COMMAND = SnapshotCommandRecord(
    name="run", options={"approve": None, "json": False}, started_at=STARTED_AT
)


def snapshot_plan(name: str = "example.yaml") -> tuple[bytes, RankingSnapshotPlan]:
    path = SNAPSHOT_CONFIGS / name
    content = path.read_bytes()
    read = read_ranking_snapshot_configuration(content, path.name)
    return content, build_snapshot_plan(read, installed_versions())


def artifact_id(content: bytes) -> str:
    return "sha256:" + sha256_hex(content)


def take(
    server: FakePortfolio123,
    out: Path,
    reply: Reply | None = None,
    *,
    timeout: int | None = None,
    faults: tuple[pytest.MonkeyPatch, str, BaseException] | None = None,
) -> tuple[SnapshotExecution, TrialFolioError | None]:
    """Takes `example.yaml`'s snapshot into `out`, through the core, over the fake server, which
    answers its `GET /rank` with `reply`, `rank-get.json`'s 200 by default. `faults` makes the
    write of a named file raise an error, before it starts."""
    content, plan = snapshot_plan()
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-get.json") if reply is None else reply, method="GET")
    options = {} if timeout is None else {"timeout": timeout}
    with LocalArtifactStore(out) as real:
        store: LocalArtifactStore | StorageFaults = real
        if faults is not None:
            monkeypatch, name, error = faults
            store = StorageFaults(real, monkeypatch)
            store.fail_before(name, error)
        execution = SnapshotExecution(
            plan, plan.plan_hash, "option", store, SNAPSHOT_COMMAND, clock=FixedClock()
        )
        error = execution.run(
            content,
            lambda: P123ScreenBacktestClient(
                CREDENTIALS, endpoint=server.endpoint, snapshot=True, **options
            ),
        )
    return execution, error


def read_json(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_bytes())
    assert isinstance(loaded, dict)
    return loaded  # pyright: ignore[reportUnknownVariableType]


def system_reply(**changes: object) -> Reply:
    """A 200 whose body is `rank-get.json`'s, with `changes` to its fields."""
    payload = read_json(RESPONSES / "rank-get.json")
    return Reply(200, json.dumps({**payload, **changes}).encode())
