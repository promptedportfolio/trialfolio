"""`trialfolio run` of a ranking snapshot configuration: it shows the snapshot's plan, obtains its
approval, reads the system the configuration names with one `rank_get`, and writes the snapshot's
directory, never resumed or added to; it says on stdout whether the system's definition can be a
ranking, and never shows it.

Traces to docs/contracts.md, ranking snapshot output (its steps, the plan's display, the result,
the JSON summary, and logs), CLI behavior (choosing by `kind`, running the commands), the license
acknowledgment, and the ranking lock, which a snapshot doesn't take; and to R04-AC08 through the
CLI: the plan shown under a terminal before anything is sent, the one `GET /rank`, whose query
names the system, the snapshot's files and records, the same command run again into its
completed directory, and each failure's manifest; and R04-AC09's interface part, the requests a
snapshot sends. The CLI's entry function runs in the test process, with the fake server below
`urllib3`, the fixed clock, and the terminal through the test launcher.

R04-AC08's checks that a screen's or an experiment's configuration naming a snapshot builds its
plan through `trialfolio run` are in `tests/interface/test_ranking_run.py` and
`test_ranking_experiment.py`, which R04-T12 wrote when it made `run` read configurations 1.1.0;
`tests/core/test_ranking_snapshot.py` makes them at the core.
"""

import json
import sys
from pathlib import Path

import pytest

from tests.support.cli import Cli
from tests.support.directories import snapshot
from tests.support.fake_portfolio123 import Reply
from tests.support.snapshot_builder import (
    EXAMPLE,
    SNAPSHOT_CONFIGS,
    rank_get,
    serve_snapshot,
    snapshot_plan_hash,
    take_snapshot,
)
from trialfolio.contracts.attempt import AttemptRecordV1_2, StartRecordV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotManifest, RankingSnapshotRecord
from trialfolio.ranking_lock import LOCK_FILE, RankingLock

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows has no pseudo-terminals")

INVALID = SNAPSHOT_CONFIGS / "invalid"
RESPONSES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"


def attempt(out: Path) -> Path:
    (found,) = sorted((out / "attempts").iterdir())
    return found


# The plan, and its approval


@posix_only
def test_under_a_terminal_the_snapshots_plan_is_shown_and_nothing_is_sent_first(cli: Cli) -> None:
    cli.ready()
    serve_snapshot(cli)
    out = cli.tmp / "snapshot"
    plan_hash = snapshot_plan_hash()

    with cli.on_terminal("run", EXAMPLE, "--out", out) as terminal:
        terminal.wait_for("Type approve")
        shown = terminal.shown()
        received_before = cli.server.requests()
        terminal.press("approve\n")
        exit_code = terminal.wait()

    assert received_before == []
    prompt = shown.index("Type approve to run this plan")
    for line in (
        f"Ranking snapshot plan {plan_hash}",
        "Ranking system: Value and momentum",
        "It writes nothing to the account.",
        "The request, exactly as p123api's rank_get will send it to Portfolio123:",
        '"name": "Value and momentum"',
        "p123api sends these params as the query of GET /rank.",
        (
            "Budget: at most 1 provider request, each sent at most once: 1 credit at"
            " Portfolio123's documented cost of 1 per request (API functions: Rank, checked"
            " 2026-10-12)."
        ),
        "strategy_definition: system",
        f"Plan hash: {plan_hash}",
    ):
        assert line in shown
        assert shown.index(line) < prompt
    assert exit_code == 0, shown
    assert cli.server.requests() == ["POST /auth", "GET /rank?name=Value+and+momentum"]


def test_without_approval_the_plan_hash_is_given_and_nothing_is_sent_or_written(cli: Cli) -> None:
    cli.ready()
    out = cli.tmp / "snapshot"

    outcome = cli("run", EXAMPLE, "--out", out, "--json")

    assert outcome.exit_code == 2
    assert outcome.error_code == "plan.approval_required"
    assert outcome.summary["ids"] == {"plan_hash": snapshot_plan_hash()}
    assert outcome.summary["output_dir"] is None
    assert "Value and momentum" not in outcome.stderr
    assert not out.exists()
    assert cli.server.requests() == []


@pytest.mark.parametrize(
    "option",
    [["--revision-reason", "A reason."], ["--repeat", "baseline"]],
    ids=["reason", "repeat"],
)
def test_a_snapshot_has_no_plan_to_revise_and_no_case_to_repeat(
    cli: Cli, option: list[str]
) -> None:
    cli.ready()
    out = cli.tmp / "snapshot"

    outcome = take_snapshot(cli, out, *option, "--json")

    assert outcome.exit_code == 2
    assert outcome.error_code == "plan.approval_required"
    message = outcome.error["message"]
    assert "A ranking snapshot's run has no plan to revise, and no case to repeat." in message
    assert not out.exists()
    assert cli.server.requests() == []


# The snapshot


def test_an_approved_snapshot_sends_one_rank_get_and_writes_its_directory(cli: Cli) -> None:
    cli.ready()
    serve_snapshot(cli)
    out = cli.tmp / "snapshot"

    outcome = take_snapshot(cli, out)

    assert outcome.exit_code == 0, outcome.stderr
    # Its authentication, then one GET /rank, whose query names the system, and nothing else.
    assert cli.server.requests() == ["POST /auth", "GET /rank?name=Value+and+momentum"]
    assert cli.server.problems() == []
    assert sorted(path.name for path in out.iterdir()) == [
        "attempts",
        "configuration.yaml",
        "definition.xml",
        "logs",
        "manifest.json",
        "plan.json",
        "snapshot.json",
    ]
    assert (out / "configuration.yaml").read_bytes() == EXAMPLE.read_bytes()
    start = StartRecordV1_2.model_validate_json((attempt(out) / "started.json").read_bytes())
    record = AttemptRecordV1_2.model_validate_json((attempt(out) / "attempt.json").read_bytes())
    assert (start.operation, start.case_id) == ("rank_get", None)
    assert (record.operation, record.case_id, record.outcome) == ("rank_get", None, "succeeded")
    response = json.loads((RESPONSES / "rank-get.json").read_bytes())
    assert (out / "definition.xml").read_bytes() == response["xml"].encode("utf-8")
    saved = RankingSnapshotRecord.model_validate_json((out / "snapshot.json").read_bytes())
    assert (saved.system.name, saved.system.id, saved.system.ranking_method) == (
        "Value and momentum",
        104729,
        2,
    )
    assert (saved.system.currency, saved.system.type) == ("USD", "Stock")
    assert saved.taken_at == record.ended_at
    manifest = RankingSnapshotManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert (manifest.outcome, manifest.synthetic, manifest.approval) == (
        "completed",
        False,
        "option",
    )
    assert manifest.command is not None and manifest.command.name == "run"
    # stdout says where it is, the system read, and that it can be a ranking; never the
    # definition.
    assert outcome.stdout.splitlines() == [
        f"Ranking snapshot taken: {out}",
        "Ranking system read: Value and momentum",
        (
            "Its definition, ranking method, currency, and type can be a ranking: name the"
            " snapshot's directory as ranking.snapshot in a screen's or an experiment's"
            " configuration, schema version 1.1.0."
        ),
        f"Plan hash: {snapshot_plan_hash()}",
    ]
    assert "Composite" not in outcome.stdout + outcome.stderr


def test_stdout_says_which_rule_keeps_a_snapshot_from_being_a_ranking(cli: Cli) -> None:
    cli.ready()
    serve_snapshot(cli, rank_get("rank-get-currency-cad.json"))

    outcome = take_snapshot(cli, cli.tmp / "snapshot")

    assert outcome.exit_code == 0, outcome.stderr
    assert (
        "It can't be a ranking: a screen's or an experiment's configuration that named it would"
        " fail, as one names a snapshot"
    ) in outcome.stdout
    assert "- whose system's currency isn't USD, which every backtest sends." in outcome.stdout
    assert "CAD" not in outcome.stdout


def test_stdout_writes_the_systems_name_with_its_control_and_formatting_characters_escaped(
    cli: Cli,
) -> None:
    """The name is text from Portfolio123's response, so an escape sequence or a bidirectional
    override in it can't act on the terminal (the result)."""
    cli.ready()
    escape, override, backslash = chr(0x1B), chr(0x202E), chr(0x5C)
    response = json.loads((RESPONSES / "rank-get.json").read_bytes())
    response["name"] = f"Value{escape}[31m and {override}momentum"
    serve_snapshot(cli, Reply(200, json.dumps(response).encode()))

    outcome = take_snapshot(cli, cli.tmp / "snapshot")

    assert outcome.exit_code == 0, outcome.stderr
    assert (
        f"Ranking system read: Value{backslash}u001b[31m and {backslash}u202emomentum"
        in outcome.stdout.splitlines()
    )
    assert escape not in outcome.stdout
    assert override not in outcome.stdout


def test_the_same_command_again_into_the_completed_snapshot_is_refused(cli: Cli) -> None:
    """A snapshot is never resumed or added to: a later snapshot goes into a directory of its
    own."""
    cli.ready()
    serve_snapshot(cli)
    out = cli.tmp / "snapshot"
    assert take_snapshot(cli, out).exit_code == 0
    before = snapshot(out)
    received = cli.server.requests()
    serve_snapshot(cli)

    again = take_snapshot(cli, out, "--json")

    assert again.exit_code == 4
    assert again.error_code == "output.not_empty"
    assert snapshot(out) == before
    assert cli.server.requests() == received


@pytest.mark.parametrize(
    ("reply", "code", "timeout"),
    [
        (Reply(404, b"Not found"), "provider.request_rejected", None),
        (Reply(503, b""), "provider.outcome_unknown", None),
        # A reply that comes after the 1-second request timeout.
        (Reply(200, b"{}", delay=3), "provider.outcome_unknown", 1),
        (rank_get("rank-get-without-xml.json"), "provider.response_invalid", None),
        (rank_get("rank-get-lone-surrogate.json"), "provider.response_invalid", None),
    ],
    ids=["404", "503", "read-timeout", "without-structure", "lone-surrogate"],
)
def test_a_failed_snapshot_has_no_definition_and_a_failed_manifest(
    cli: Cli, reply: Reply, code: str, timeout: int | None
) -> None:
    cli.ready()
    serve_snapshot(cli, reply)
    out = cli.tmp / "snapshot"

    outcome = take_snapshot(cli, out, "--json", timeout=timeout)

    assert outcome.exit_code == 5
    assert outcome.error_code == code
    assert not (out / "definition.xml").exists()
    assert not (out / "snapshot.json").exists()
    manifest = RankingSnapshotManifest.model_validate_json((out / "manifest.json").read_bytes())
    assert (manifest.outcome, manifest.error and manifest.error.code) == ("failed", code)
    assert outcome.summary["outputs"] == {"manifest": "manifest.json"}
    assert "The snapshot's records are in" in outcome.stderr


def test_a_ranking_method_the_wrapper_doesnt_know_leaves_response_raw(cli: Cli) -> None:
    cli.ready()
    serve_snapshot(cli, rank_get("rank-get-unknown-method.json"))
    out = cli.tmp / "snapshot"

    outcome = take_snapshot(cli, out, "--json")

    assert outcome.error_code == "provider.response_invalid"
    assert (attempt(out) / "response.raw").is_file()
    assert not (out / "definition.xml").exists()


def test_a_snapshots_json_summary_gives_a_runs_keys(cli: Cli) -> None:
    cli.ready()
    serve_snapshot(cli)
    out = cli.tmp / "snapshot"

    outcome = take_snapshot(cli, out, "--json")

    summary = outcome.summary
    record = AttemptRecordV1_2.model_validate_json((attempt(out) / "attempt.json").read_bytes())
    assert summary["schema_version"] == "1.2.0"
    assert (summary["command"], summary["outcome"], summary["exit_code"]) == (
        "run",
        "completed",
        0,
    )
    assert summary["ids"] == {
        "plan_hash": snapshot_plan_hash(),
        "attempt_id": str(record.attempt_id),
    }
    assert summary["output_dir"] == str(out)
    assert summary["outputs"] == {"manifest": "manifest.json"}
    assert "cases" not in summary
    counts = outcome.counts
    assert {
        key: counts[key] for key in ("attempts", "provider_requests", "metrics_unavailable", "cost")
    } == {
        "attempts": 1,
        "provider_requests": 1,
        "metrics_unavailable": 0,
        "cost": 1,
    }


def test_a_snapshot_runs_beside_a_run_that_holds_the_ranking_lock(cli: Cli) -> None:
    """A snapshot writes nothing to the account, so it takes no lock (the ranking lock)."""
    cli.ready()
    serve_snapshot(cli)

    with RankingLock(cli.locks / LOCK_FILE):
        outcome = take_snapshot(cli, cli.tmp / "snapshot")

    assert outcome.exit_code == 0, outcome.stderr


def test_a_snapshots_logs_name_it_by_its_plan_hash_and_attempt_never_its_system(
    cli: Cli,
) -> None:
    cli.ready()
    serve_snapshot(cli)
    out = cli.tmp / "snapshot"

    assert take_snapshot(cli, out).exit_code == 0

    log = (out / "logs" / "trialfolio.log").read_text(encoding="utf-8")
    events = [json.loads(line) for line in log.splitlines()]
    ended = next(event for event in events if event["event"] == "snapshot.completed")
    assert ended["plan_hash"] == snapshot_plan_hash()
    assert "attempt_id" in ended and "case_id" not in ended
    for value in ("Value and momentum", "Value+and+momentum", "104729", "Composite"):
        assert value not in log


# Validation


def test_a_snapshot_without_an_acknowledgment_writes_nothing(cli: Cli) -> None:
    cli.credentials()
    out = cli.tmp / "snapshot"

    outcome = take_snapshot(cli, out, "--json")

    assert outcome.exit_code == 2
    assert outcome.error_code == "license.not_acknowledged"
    assert not out.exists()
    assert cli.server.requests() == []


@pytest.mark.parametrize("name", ["misspelled-key.yaml", "unquoted-system.yaml"])
def test_an_invalid_snapshot_configuration_is_refused_before_anything_is_written(
    cli: Cli, name: str
) -> None:
    cli.ready()
    out = cli.tmp / "snapshot"

    outcome = cli("run", INVALID / name, "--out", out, "--json")

    assert outcome.exit_code == 3
    assert outcome.error_code == "config.invalid"
    assert not out.exists()
    assert cli.server.requests() == []


def test_a_snapshot_without_credentials_sends_nothing(cli: Cli) -> None:
    cli.accept_license()
    out = cli.tmp / "snapshot"

    outcome = take_snapshot(cli, out, "--json")

    assert outcome.exit_code == 5
    assert outcome.error_code == "provider.auth_failed"
    assert not out.exists()
    assert cli.server.requests() == []
