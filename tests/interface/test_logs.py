"""`trialfolio run`'s logs hold no configuration value, formula, or response content at any level;
they're written only under `<out>/logs/`, and only once the run has claimed the directory, except
that an internal error before the claim writes them to the per-user log directory; and a run
whose claim fails writes no log file anywhere.

Traces to R01-AC17, and to docs/contracts.md, logging and local diagnostics (content, format,
levels, and storage), through the CLI's entry function in the test process at
`TRIALFOLIO_LOG_LEVEL=DEBUG`, with `canaries.yaml` and the real client, `requests`, and `urllib3`
over the fake server, which answers with `responses/canaries.json`: `complete.json` with canary
strings in an extra key and in the chart, and canary numbers as a metric and in a period. The
canaries' scan looks for them in every log file. The per-user directories are under a temporary
home.
"""

import json
import os
from pathlib import Path

import pytest

from tests.interface.conftest import (
    AUTHENTICATED,
    CONFIGS,
    Cli,
    Outcome,
    plan_hash_for,
    response,
)
from tests.support import canaries
from tests.support.fake_portfolio123 import Reply
from trialfolio.storage import LocalArtifactStore, StoredFile
from trialfolio.userdirs import log_directory

CANARY_CONFIGURATION = CONFIGS / "canaries.yaml"

UNEXPECTED_CANARY = "canary-exception-message-4d8e2a71"
"""The message of an unexpected exception, which logs give only by its type."""

FIELDS = {"timestamp", "level", "event", "message", "trialfolio_version", "component"}
"""The fields every log line holds; linked IDs are added when they apply."""


def approved_run(cli: Cli, out: Path, **options: object) -> Outcome:
    return cli(
        "run",
        CANARY_CONFIGURATION,
        "--out",
        out,
        "--approve",
        plan_hash_for(CANARY_CONFIGURATION),
        "--json",
        **options,  # pyright: ignore[reportArgumentType]
    )


def log_files(cli: Cli) -> list[Path]:
    """Every log file under the test's directory: the output directories and the temporary
    home, which holds the per-user log directory."""
    return canaries.log_files([cli.tmp])


def logged_canaries(cli: Cli) -> list[str]:
    """Where a canary appears in a log file under the test's directory."""
    return canaries.logged([cli.tmp], more=[UNEXPECTED_CANARY])


def lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(autouse=True)
def debug(cli: Cli, monkeypatch: pytest.MonkeyPatch) -> None:
    """DEBUG level, set once `cli` has cleared the environment it starts with."""
    monkeypatch.setenv("TRIALFOLIO_LOG_LEVEL", "DEBUG")


class Interloper:
    """The output directory's real store, with another process writing a file into the directory
    just before the claim."""

    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self._store = LocalArtifactStore(root)

    def check_empty(self) -> None:
        self._store.check_empty()

    def claim(self, path: str, data: bytes) -> StoredFile:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "other.txt").write_text("another process's file\n")
        return self._store.claim(path, data)

    def write(self, path: str, data: bytes) -> StoredFile:
        return self._store.write(path, data)

    def discard(self, path: str, data: bytes) -> None:
        self._store.discard(path, data)

    def read(self, path: str) -> bytes:
        return self._store.read(path)


class Defective(Interloper):
    """The output directory's real store, whose claim fails unexpectedly, as a defect would."""

    def claim(self, path: str, data: bytes) -> StoredFile:
        raise RuntimeError(UNEXPECTED_CANARY)


def test_a_success_logs_only_under_the_output_directory_and_no_canary(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("canaries.json"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 0, outcome.stderr
    assert log_files(cli) == [out / "logs" / "trialfolio.log"]
    assert not log_directory(os.environ).exists()
    assert logged_canaries(cli) == []
    # Every canary does reach the run's artifacts, so the scan of the logs means something.
    configuration = (out / "configuration.yaml").read_text()
    assert all(canary in configuration for canary in canaries.CONFIGURATION)
    saved = next(out.glob("cases/*/attempts/*/response.json")).read_text()
    assert all(canary in saved for canary in canaries.RESPONSE)


def test_each_log_line_is_one_json_object_with_the_documented_fields(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("canaries.json"))
    out = cli.tmp / "out"

    approved_run(cli, out)

    events = lines(out / "logs" / "trialfolio.log")
    assert events
    for event in events:
        assert FIELDS <= set(event)
        assert isinstance(event["timestamp"], str)
        assert event["timestamp"].endswith("Z")
        assert event["level"] in ("DEBUG", "INFO", "WARNING", "ERROR")
        assert event["trialfolio_version"] == "0.1.0"
        assert isinstance(event["event"], str)
        assert "." in event["event"]
    names = [event["event"] for event in events]
    assert names[0] == "cli.command.started"
    assert names[-1] == "cli.command.completed"
    # DEBUG is recorded at that level.
    assert "artifact.write.completed" in names
    # Logs record the plan hash and the case ID, never the plan's contents.
    (created,) = (event for event in events if event["event"] == "plan.created")
    assert created["plan_hash"] == plan_hash_for(CANARY_CONFIGURATION)
    assert str(created["case_id"]).startswith("case-")


def test_an_authentication_failure_logs_no_canary(cli: Cli) -> None:
    cli.ready()
    cli.server.reply("/auth", Reply(401, b"Unauthorized"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 5
    assert log_files(cli) == [out / "logs" / "trialfolio.log"]
    assert logged_canaries(cli) == []


def test_a_claim_that_fails_writes_no_log_file_anywhere(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"

    outcome = approved_run(cli, out, store_factory=Interloper)

    assert outcome.exit_code == 4
    assert outcome.summary["error"]["code"] == "output.not_empty"  # pyright: ignore[reportIndexIssue]
    assert sorted(p.name for p in out.iterdir()) == ["other.txt"]
    assert log_files(cli) == []
    assert not log_directory(os.environ).exists()
    assert cli.server.requests() == []


def test_an_internal_error_before_the_claim_logs_to_the_per_user_directory(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "out"

    outcome = approved_run(cli, out, store_factory=Defective)

    assert outcome.exit_code == 1
    error = outcome.summary["error"]
    assert isinstance(error, dict)
    assert error["code"] == "internal.unexpected"
    (logged,) = log_files(cli)
    assert logged.parent == log_directory(os.environ)
    assert str(logged) in str(error["message"])  # pyright: ignore[reportUnknownArgumentType]
    assert UNEXPECTED_CANARY not in str(error["message"])  # pyright: ignore[reportUnknownArgumentType]
    assert logged_canaries(cli) == []
    assert not out.exists()
    events = [event["event"] for event in lines(logged)]
    assert "cli.command.unexpected" in events
    assert events[-1] == "cli.command.completed"


def test_an_unknown_log_level_is_ignored_with_a_warning(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    monkeypatch.setenv("TRIALFOLIO_LOG_LEVEL", "verbose")
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("canaries.json"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 0
    assert "Warning: TRIALFOLIO_LOG_LEVEL" in outcome.stderr
    events = lines(out / "logs" / "trialfolio.log")
    levels = {event["level"] for event in events}
    assert "INFO" in levels
    assert "DEBUG" not in levels
    assert "cli.environment.ignored" in [event["event"] for event in events]
    assert outcome.summary["counts"]["warnings"] == 1  # pyright: ignore[reportIndexIssue]


def test_the_warning_level_leaves_info_out_of_the_log_file(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    monkeypatch.setenv("TRIALFOLIO_LOG_LEVEL", "WARNING")
    # A warning, logged before the claim and held until it.
    monkeypatch.setenv("SSLKEYLOGFILE", str(cli.tmp / "keys.log"))
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", response("canaries.json"))
    out = cli.tmp / "out"

    outcome = approved_run(cli, out)

    assert outcome.exit_code == 0
    events = lines(out / "logs" / "trialfolio.log")
    assert [(event["level"], event["event"]) for event in events] == [
        ("WARNING", "cli.environment.ignored")
    ]
    # stderr still shows progress, whatever the log file's level.
    assert "Claimed the output directory." in outcome.stderr
