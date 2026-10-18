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

The snapshot's values are invented, but nothing labels it synthetic, so a committed copy would
read as a ranking system Portfolio123 returned. It exists only in the test's temporary directory.
R04-T10 wrote it, with the snapshot's tests.
"""

import io
import os
import re
import sys
from pathlib import Path
from typing import Final

import pytest

from tests.support import canaries
from tests.support.clock import FixedClock
from tests.support.environment import VARIABLES
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE
from trialfolio.cli import API_ID_VARIABLE, API_KEY_VARIABLE, main
from trialfolio.configuration import read_ranking_snapshot_configuration
from trialfolio.planning import build_snapshot_plan, installed_versions

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures"
SNAPSHOT_CONFIGS: Final = FIXTURES / "ranking-snapshot-configs"
RESPONSES: Final = FIXTURES / "responses"

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


class SnapshotBuilder:
    """Writes snapshots with `trialfolio run`, in the test process, with a temporary home and
    without the variables Trial Folio reads, apart from the license acknowledgment and the canary
    credentials."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
        self._monkeypatch = monkeypatch
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
        stderr = io.StringIO()
        try:
            server.reply("/auth", Reply(200, canaries.TOKEN.encode()))
            server.reply(
                "/rank", rank_get(reply) if isinstance(reply, str) else reply, method="GET"
            )
            with self._monkeypatch.context() as patch:
                self._home.mkdir(parents=True, exist_ok=True)
                patch.setenv("HOME", str(self._home))
                for name in VARIABLES:
                    patch.delenv(name, raising=False)
                patch.setenv(ACCEPT_VARIABLE, ACCEPT_VALUE)
                patch.setenv(API_ID_VARIABLE, canaries.API_ID)
                patch.setenv(API_KEY_VARIABLE, canaries.API_KEY)
                patch.setattr(sys, "stdin", io.StringIO())
                patch.setattr(sys, "stdout", io.StringIO())
                patch.setattr(sys, "stderr", stderr)
                main(
                    [
                        "run",
                        str(path),
                        "--out",
                        str(out),
                        "--approve",
                        snapshot_plan_hash(configuration),
                    ],
                    endpoint=server.endpoint,
                    clock=FixedClock(),
                )
        finally:
            server.close()
        # A snapshot that fails still writes its manifest.
        assert (out / "manifest.json").is_file(), stderr.getvalue()
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
