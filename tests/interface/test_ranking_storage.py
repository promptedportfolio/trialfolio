"""A storage failure or an interrupt at a file release 0.4.0 adds exits with
`storage.write_failed` and 4, or `command.interrupted` and 130, leaves no manifest, says the
output is incomplete, and writes no file twice: a plan's `definition.xml` or `snapshot.json`, an
attempt's `rank-update-request.json`, `updating.json`, or `rank-update-response.json`, and a
snapshot's `definition.xml`, `snapshot.json`, or manifest. After a fault in a plan's files,
nothing was sent. A fault at `rank-update-response.json`, after the `rank_update`'s 200, sends no
backtest, and leaves the attempt `failed` and possibly charged, so its case awaits a repeat. Then
the same command resumes the experiment, after a fault in one of its attempts, and replaces no
record; and fails with `output.not_empty`, exit 4, after a fault in a screen run's files or a
snapshot's, since `run` resumes neither, or in a new experiment's plan, which wasn't recorded.

A snapshot's message says it has no manifest after a fault at its `configuration.yaml` or its
attempt's files too, as a run's does. And a storage failure at the attempt record, which leaves
the start record running, ends a run's message, or a snapshot's, with one detail of its
requests, the attempt's own, then that the output has no manifest: for a run without a
definition too, since the rule is 0.1.0's. Neither is resumed, so what the start record says
isn't added, as it is to an experiment session's message, whose resume reads it.

After a saved response that failed validation, `provider.response_invalid`, a fault while a run
writes its report or its manifest, or while a snapshot writes its manifest, says the output has
no manifest, then keeps the response's message after "Before that:", which TS-T02 added (the
missing tests' item 4, in docs/test-refactoring.md).

Traces to R04-AC13, as release 0.4.0's test pairing gives it for
`tests/interface/test_ranking_storage.py`, and to docs/contracts.md, sending a definition (the
attempt's files, and the backtest only after the write), ranking snapshot output, running an
experiment (an ending without a manifest), endings that decide the error code, execution outcomes
and attempts (an error that decides the code keeps the message of the one it overrides), and CLI
behavior (which directories `run` resumes, and what a run writes after its attempt), and to the
corrected defects the review of R04-T13's pull request found. Through the CLI's entry function in the test
process, over the fake server, with storage faults wrapping the real store: at a whole path, such
as `/definition.xml`, or at a file of a case, in its attempt. A screen run is of
`screen-configs/definition.yaml`, or `formula.yaml` without a definition, an experiment of
`ranking-example.yaml`, whose first case, `baseline`, authenticates, and a snapshot of
`ranking-snapshot-configs/example.yaml`; a plan's `snapshot.json` is that of a configuration that
names a snapshot the snapshot builder took, beside it. The ranking lock is in the test's own
directory.
"""

import json
from pathlib import Path
from typing import Final

import pytest

from tests.support.cli import Cli, plan_hash_for
from tests.support.directories import snapshot
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    RANK_UPDATED,
    ExperimentBuilder,
    experiment_config,
    plan_hash,
    returns_each,
)
from tests.support.fake_portfolio123 import AUTH, AUTHENTICATED, BACKTEST, RANK, RANK_GET, response
from tests.support.paths import screen_config
from tests.support.snapshot_builder import (
    SNAPSHOT_CONFIGS,
    SnapshotBuilder,
    naming,
    rank_get,
    snapshot_plan_hash,
)
from tests.support.storage_faults import Fault, FaultyStores
from trialfolio.configuration import read_experiment_configuration_v1_1
from trialfolio.contracts.attempt import AttemptRecordV1_2, AttemptRecordV1_3
from trialfolio.planning import build_experiment_plan_v1_1, installed_versions

type Builder = ExperimentBuilder[Outcome]

DEFINITION = screen_config("definition.yaml")
EXAMPLE = experiment_config("ranking-example.yaml")
SNAPSHOT = SNAPSHOT_CONFIGS / "example.yaml"

RUN_INCOMPLETE: Final = "The run has no manifest, so its output is incomplete."
SNAPSHOT_INCOMPLETE: Final = "The snapshot has no manifest, so its output is incomplete."
SESSION_INCOMPLETE: Final = (
    "The session has no manifest, so the experiment's output reads as incomplete until running"
    " the same command again resumes it."
)
UNRECORDED: Final = (
    "Nothing was sent. The experiment's first plan wasn't recorded, so its output is incomplete,"
    " and the directory can't be resumed: remove the directory, and run the command again."
)


FAULTS: Final = (pytest.param("full disk", id="storage"), pytest.param("interrupt", id="interrupt"))
"""Each kind of fault: a write that fails inside the real store with `ENOSPC`, which gives
`storage.write_failed`, or a `KeyboardInterrupt` before the write starts, which gives
`command.interrupted`, as `StorageFaults.fail` sets it."""


def failed(outcome: Outcome, kind: Fault) -> str:
    """The error's message, once the outcome is checked against the fault's kind: its code, its
    exit code, stderr, and a summary without a manifest."""
    code, exit_code = (
        ("storage.write_failed", 4) if kind == "full disk" else ("command.interrupted", 130)
    )
    assert outcome.exit_code == exit_code, outcome.stderr
    error = outcome.error
    assert error["code"] == code
    assert f"Error ({code}): {error['message']}" in outcome.stderr
    assert "manifest" not in outcome.outputs
    return error["message"]


def written_once(faults: FaultyStores) -> None:
    """The storage faults' record of what the store published shows no file written twice."""
    published = faults.published
    assert len(published) == len(set(published)), published


def sent(cli: Cli, since: int = 0) -> list[str]:
    """Each request the server received since the `since`th, by its method and its path without
    the query."""
    return [received.request for received in cli.server.received[since:]]


def refused_again(cli: Cli, argv: list[str | Path], out: Path) -> str:
    """Runs the same command again, and checks that it fails with `output.not_empty`, exit 4,
    sends nothing, and leaves the directory's files as they were; gives the message."""
    before = snapshot(out)
    received = len(cli.server.received)

    again = cli(*argv)

    assert again.exit_code == 4, again.stderr
    error = again.error
    assert error["code"] == "output.not_empty"
    assert len(cli.server.received) == received
    assert snapshot(out) == before
    return error["message"]


def snapshot_named(cli: Cli, configuration: Path) -> Path:
    """A copy of `configuration`, a screen's or an experiment's ranked by a definition, beside a
    snapshot the snapshot builder takes, with `ranking.snapshot` naming it."""
    builder = SnapshotBuilder(cli.tmp / "snapshot-home")
    taken = builder.snapshot(cli.tmp / "configs" / "ranking" / "snapshot")
    return naming(configuration, taken, cli.tmp / "configs")


# A screen run with a ranking definition


def run_screen(cli: Cli, path: Path, faults: FaultyStores) -> tuple[list[str | Path], Outcome]:
    """Runs the screen configuration at `path`, approved, over a server that answers its
    authentication, `rank_update`, and backtest, with `faults`; gives the command's arguments,
    for the same command again, and its outcome."""
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", response("rank-update.json"), method="POST")
    cli.server.reply("/screen/backtest", response("complete.json"))
    out = cli.tmp / "run"
    argv: list[str | Path] = ["run", path, "--out", out, "--approve", plan_hash_for(path), "--json"]
    return argv, cli(*argv, store_factory=faults)


NEITHER_SENT: Final = "Neither the rank_update request nor the screen backtest request was sent."
UPDATE_ONLY: Final = (
    "The rank_update request, which writes the case's ranking definition into ApiRankingSystem,"
    " reached Portfolio123, and may have been charged. The screen backtest request wasn't sent."
)

SCREEN_FAULTS: Final = {
    "definition.xml": ("/definition.xml", [], NEITHER_SENT),
    "rank-update-request.json": ("rank-update-request.json", [AUTH], NEITHER_SENT),
    "updating.json": ("updating.json", [AUTH], NEITHER_SENT),
    "rank-update-response.json": ("rank-update-response.json", [AUTH, RANK], UPDATE_ONLY),
}
"""Where each fault strikes a screen run, the requests sent before it, and what the message says
of the two requests, as written by hand: nothing before the plan's copy of the definition, which
comes before the attempt; the authentication, which a screen run's attempt makes first, before
its `rank-update-request.json` and its update record; and the `rank_update` too, before its
response is saved."""


@pytest.mark.parametrize("kind", FAULTS)
@pytest.mark.parametrize("at", SCREEN_FAULTS)
def test_a_fault_at_a_screen_runs_file_leaves_no_manifest_and_the_run_isnt_resumed(
    cli: Cli, faults: FaultyStores, at: str, kind: Fault
) -> None:
    name, before, said = SCREEN_FAULTS[at]
    faults.fail(name, kind)

    argv, outcome = run_screen(cli, DEFINITION, faults)

    message = failed(outcome, kind)
    assert message.endswith(f"{said} {RUN_INCOMPLETE}")
    out = cli.tmp / "run"
    assert not (out / "manifest.json").exists()
    assert sent(cli) == before
    written_once(faults)
    refused_again(cli, argv, out)


@pytest.mark.parametrize("kind", FAULTS)
def test_a_fault_at_a_screen_runs_rank_update_response_sends_no_backtest(
    cli: Cli, faults: FaultyStores, kind: Fault
) -> None:
    faults.fail("rank-update-response.json", kind)

    _, outcome = run_screen(cli, DEFINITION, faults)

    failed(outcome, kind)
    assert sent(cli) == [AUTH, RANK]
    (attempt,) = (cli.tmp / "run" / "cases").glob("*/attempts/*")
    assert not (attempt / "rank-update-response.json").exists()
    assert not (attempt / "request.json").exists()
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.ranking_update is not None and record.ranking_update.response is None
    assert [(e.request, e.status) for e in record.exchanges] == [(AUTH, 200), (RANK, 200)]


@pytest.mark.parametrize("kind", FAULTS)
@pytest.mark.parametrize("name", ["definition.xml", "snapshot.json"])
def test_a_fault_at_a_runs_copy_of_a_snapshot_sends_nothing_and_leaves_no_manifest(
    cli: Cli, faults: FaultyStores, name: str, kind: Fault
) -> None:
    named = snapshot_named(cli, DEFINITION)
    faults.fail(f"/{name}", kind)

    argv, outcome = run_screen(cli, named, faults)

    message = failed(outcome, kind)
    assert RUN_INCOMPLETE in message
    out = cli.tmp / "run"
    assert not (out / "manifest.json").exists()
    assert sent(cli) == []
    written_once(faults)
    refused_again(cli, argv, out)


# An experiment with a ranking definition


def case_id_of(path: Path, key: str) -> str:
    """The `case_id` of the case `key` of a new experiment of the configuration at `path`."""
    read = read_experiment_configuration_v1_1(path.read_bytes(), path.name, path)
    plan = build_experiment_plan_v1_1(read, installed_versions())
    (case_id,) = (case.case_id for case in plan.cases if case.case_key == key)
    return case_id


def records(out: Path) -> dict[str, bytes]:
    """Each file of the experiment's records, by path: everything but its logs."""
    return {
        path: content
        for path, content in snapshot(out).items()
        if content is not None and not path.startswith("logs/")
    }


EXPERIMENT_FAULTS: Final = {
    "rank-update-request.json": (
        [AUTH],
        [AUTH, *[RANK, BACKTEST] * 4],
        0,
        "Neither the rank_update request nor the screen backtest request was sent.",
    ),
    "updating.json": (
        [AUTH],
        [AUTH, *[RANK, BACKTEST] * 4],
        0,
        "Neither the rank_update request nor the screen backtest request was sent.",
    ),
    "rank-update-response.json": ([AUTH, RANK], [AUTH, *[RANK, BACKTEST] * 3], 6, None),
}
"""For each fault at a file of `baseline`'s attempt, as written by hand: the requests sent before
it, the requests the resume sends, its exit code, and what the stopped run's message says of the
`rank_update`, where it says it. A fault before the `rank_update`'s send leaves the case due, so
the resume sends all four cases, each with its `rank_update` and backtest, after one
authentication. One at its response, after the 200, leaves it possibly charged, awaiting a
repeat, which the resume doesn't send, so it sends the other three cases and ends with
`execution.partial`."""


@pytest.mark.parametrize("kind", FAULTS)
@pytest.mark.parametrize("at", EXPERIMENT_FAULTS)
def test_a_fault_at_an_experiment_attempts_file_leaves_no_manifest_and_the_command_resumes(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    monkeypatch: pytest.MonkeyPatch,
    at: str,
    kind: Fault,
) -> None:
    before, resumed, exit_code, said = EXPERIMENT_FAULTS[at]
    cli.ready()
    out = cli.tmp / "experiment"
    # The same command, run twice: approved by the new experiment's plan hash.
    approve = ("--approve", plan_hash(EXAMPLE, out))
    ranks, sends = [RANK_UPDATED] * 4, returns_each(4)
    faults.fail(f"{case_id_of(EXAMPLE, 'baseline')}/{at}", kind)

    stopped = experiments.run(
        EXAMPLE, out, *approve, approve=False, store_factory=faults, ranks=ranks, sends=sends
    )

    message = failed(stopped, kind)
    assert SESSION_INCOMPLETE in message
    if said is not None:
        assert said in message
    assert not (out / "sessions/1/manifest.json").exists()
    assert sent(cli) == before
    written_once(faults)
    kept = records(out)
    received = len(cli.server.received)
    again_faults = FaultyStores(monkeypatch)

    again = experiments.run(
        EXAMPLE, out, *approve, approve=False, store_factory=again_faults, ranks=ranks, sends=sends
    )

    assert again.exit_code == exit_code, again.stderr
    assert again.ids["session"] == 2
    assert (out / "sessions/2/manifest.json").is_file()
    assert sent(cli, received) == resumed
    # No record was replaced: each file the stopped run left is as it was, and the resume wrote
    # none of them, nor any file twice.
    for path, content in kept.items():
        assert (out / path).read_bytes() == content, path
    assert len(again_faults.published) == len(set(again_faults.published))
    assert set(again_faults.published).isdisjoint(faults.published)


@pytest.mark.parametrize("kind", FAULTS)
def test_a_fault_at_an_experiments_rank_update_response_leaves_its_case_awaiting_a_repeat(
    cli: Cli, experiments: Builder, faults: FaultyStores, kind: Fault
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    baseline = case_id_of(EXAMPLE, "baseline")
    faults.fail(f"{baseline}/rank-update-response.json", kind)

    stopped = experiments.run(
        EXAMPLE, out, ranks=[RANK_UPDATED] * 4, sends=returns_each(4), store_factory=faults
    )

    failed(stopped, kind)
    assert sent(cli) == [AUTH, RANK]
    (attempt,) = (out / "cases" / baseline / "attempts").iterdir()
    assert not (attempt / "rank-update-response.json").exists()
    assert not (attempt / "started.json").exists()
    record = AttemptRecordV1_3.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.ranking_update is not None and record.ranking_update.response is None
    assert [(e.request, e.status) for e in record.exchanges] == [(AUTH, 200), (RANK, 200)]
    cases = stopped.cases
    assert (cases[0]["case_id"], cases[0]["outcome"]) == (baseline, "failed")
    assert cases[0]["repeat_attempt_id"] == attempt.name
    received = len(cli.server.received)

    # The resume never sends it again on its own: it awaits a repeat.
    resumed = experiments.run(EXAMPLE, out, ranks=[RANK_UPDATED] * 3, sends=returns_each(3))

    assert resumed.exit_code == 6, resumed.stderr
    assert sent(cli, received) == [AUTH, *[RANK, BACKTEST] * 3]
    assert [path.name for path in (out / "cases" / baseline / "attempts").iterdir()] == [
        attempt.name
    ]


@pytest.mark.parametrize("kind", FAULTS)
@pytest.mark.parametrize("name", ["definition.xml", "snapshot.json"])
def test_a_fault_at_a_new_experiments_plan_files_sends_nothing_and_it_cant_be_resumed(
    cli: Cli,
    experiments: Builder,
    faults: FaultyStores,
    name: str,
    kind: Fault,
) -> None:
    # A plan's definition.xml comes before its experiment.json, so the first plan isn't recorded.
    configuration = EXAMPLE if name == "definition.xml" else snapshot_named(cli, EXAMPLE)
    cli.ready()
    out = cli.tmp / "experiment"
    approve = ("--approve", plan_hash(configuration, out))
    faults.fail(f"/plans/1/{name}", kind)

    stopped = experiments.run(
        configuration,
        out,
        *approve,
        ranks=[RANK_UPDATED] * 4,
        sends=returns_each(4),
        approve=False,
        store_factory=faults,
    )

    message = failed(stopped, kind)
    assert UNRECORDED in message
    assert not (out / "plans/1/experiment.json").exists()
    assert sent(cli) == []
    written_once(faults)
    again = refused_again(cli, ["run", configuration, "--out", out, *approve, "--json"], out)
    assert "Remove the directory, and run the command again." in again


# A ranking snapshot


@pytest.mark.parametrize("kind", FAULTS)
@pytest.mark.parametrize("name", ["definition.xml", "snapshot.json", "manifest.json"])
def test_a_fault_at_a_snapshots_file_leaves_no_manifest_and_it_isnt_resumed(
    cli: Cli, faults: FaultyStores, name: str, kind: Fault
) -> None:
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", rank_get(), method="GET")
    out = cli.tmp / "snapshot"
    argv: list[str | Path] = [
        "run",
        SNAPSHOT,
        "--out",
        out,
        "--approve",
        snapshot_plan_hash(),
        "--json",
    ]
    faults.fail(f"/{name}", kind)

    outcome = cli(*argv, store_factory=faults)

    message = failed(outcome, kind)
    assert SNAPSHOT_INCOMPLETE in message
    assert not (out / "manifest.json").exists()
    # The snapshot's files come after its one rank_get, which a snapshot never sends again.
    assert sent(cli) == [AUTH, RANK_GET]
    written_once(faults)
    record = json.loads(next((out / "attempts").glob("*/attempt.json")).read_bytes())
    assert (record["outcome"], record["operation"]) == ("succeeded", "rank_get")
    refused_again(cli, argv, out)


SNAPSHOT_ATTEMPT_FAULTS: Final = {
    "configuration.yaml": ("/configuration.yaml", [], "The rank_get request wasn't sent."),
    "request.json": ("request.json", [AUTH], "The rank_get request wasn't sent."),
    "started.json": ("started.json", [AUTH], "The rank_get request wasn't sent."),
    "response.json": (
        "response.json",
        [AUTH, RANK_GET],
        (
            "The rank_get request may have been charged, and its outcome is unknown: no response"
            " was saved. Trial Folio never retries it automatically: check the account's API"
            " credits on Portfolio123's website before running the command again."
        ),
    ),
}
"""Where each fault strikes a snapshot before its attempt record, the requests sent before it, and
what the message says of the `rank_get`, as written by hand: `configuration.yaml` before the
attempt; the attempt's `request.json` and start record after its authentication; and its response
after the `rank_get`. The attempt record's own fault is below."""


@pytest.mark.parametrize("kind", FAULTS)
@pytest.mark.parametrize("at", SNAPSHOT_ATTEMPT_FAULTS)
def test_a_fault_before_a_snapshots_attempt_record_says_it_has_no_manifest(
    cli: Cli, faults: FaultyStores, at: str, kind: Fault
) -> None:
    name, before, said = SNAPSHOT_ATTEMPT_FAULTS[at]
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", rank_get(), method="GET")
    out = cli.tmp / "snapshot"
    argv: list[str | Path] = [
        "run",
        SNAPSHOT,
        "--out",
        out,
        "--approve",
        snapshot_plan_hash(),
        "--json",
    ]
    faults.fail(name, kind)

    outcome = cli(*argv, store_factory=faults)

    message = failed(outcome, kind)
    assert message.endswith(f"{said} {SNAPSHOT_INCOMPLETE}")
    assert not (out / "manifest.json").exists()
    assert sent(cli) == before
    written_once(faults)
    refused_again(cli, argv, out)


# An attempt record that can't be written


CHECK_SPACE: Final = "Check the output directory's free space and permissions."
"""How a storage failure's own message ends, before the details of the requests."""
BOTH_SUCCEEDED: Final = (
    "The rank_update request, which writes the case's ranking definition into ApiRankingSystem,"
    " and the screen backtest request succeeded, and their responses were saved."
)

UNRECORDED_ATTEMPTS: Final = {
    "screen run": (
        screen_config("formula.yaml"),
        [AUTH, BACKTEST],
        "The screen backtest request succeeded, and its response was saved.",
        RUN_INCOMPLETE,
    ),
    "screen run with a definition": (
        DEFINITION,
        [AUTH, RANK, BACKTEST],
        BOTH_SUCCEEDED,
        RUN_INCOMPLETE,
    ),
    "snapshot": (
        SNAPSHOT,
        [AUTH, RANK_GET],
        "The rank_get request succeeded, and its response was saved.",
        SNAPSHOT_INCOMPLETE,
    ),
}
"""For a run without a definition, one with a definition, and a snapshot, each as written by
hand: the requests it sends, each answered with a 200; what the attempt's own error says of them;
and that the output has no manifest."""


@pytest.mark.parametrize("what", UNRECORDED_ATTEMPTS)
def test_a_storage_failure_at_the_attempt_record_gives_the_attempts_detail_then_the_manifests(
    cli: Cli, faults: FaultyStores, what: str
) -> None:
    configuration, requests, attempt_said, incomplete = UNRECORDED_ATTEMPTS[what]
    faults.fail_os("attempt.json")
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", response("rank-update.json"), method="POST")
    cli.server.reply("/rank", rank_get(), method="GET")
    cli.server.reply("/screen/backtest", response("complete.json"))
    out = cli.tmp / "out"
    approve = snapshot_plan_hash() if configuration == SNAPSHOT else plan_hash_for(configuration)

    outcome = cli(
        "run", configuration, "--out", out, "--approve", approve, "--json", store_factory=faults
    )

    # One detail of the requests, the attempt's own, between the storage failure's message and
    # the manifest's: not the start record's too, which reads as running, since neither a run
    # nor a snapshot is resumed.
    message = failed(outcome, "full disk")
    assert message.endswith(f"{CHECK_SPACE} {attempt_said} {incomplete}")
    assert "reads as running" not in message
    assert sent(cli) == requests
    (attempt,) = out.glob("**/attempts/*")
    assert (attempt / "started.json").is_file()
    assert not (attempt / "attempt.json").exists()
    assert not (out / "manifest.json").exists()


def test_an_experiments_storage_failure_at_the_attempt_record_gives_its_start_records_detail_too(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    faults.fail_os(f"{case_id_of(EXAMPLE, 'baseline')}/attempt.json")

    stopped = experiments.run(
        EXAMPLE, out, ranks=[RANK_UPDATED] * 4, sends=returns_each(4), store_factory=faults
    )

    # The resume reads the start record, so the session's message says what it says too.
    message = failed(stopped, "full disk")
    assert message.endswith(
        f"{CHECK_SPACE} {BOTH_SUCCEEDED} The rank_update request of the last attempt, which"
        " writes the case's ranking definition into ApiRankingSystem, reached Portfolio123, and"
        " may have been charged. Its screen backtest request may have been sent, and may have"
        " been charged: its start record reads as running. Trial Folio never retries either"
        f" automatically. The attempts recorded so far are kept. {SESSION_INCOMPLETE}"
    )
    assert sent(cli) == [AUTH, RANK, BACKTEST]
    assert not (out / "sessions/1/manifest.json").exists()


# An ending after a response that failed validation


RESPONSE_INVALID: Final = {
    "run": (
        (
            "Portfolio123's response was saved, as {saved}, but Trial Folio can't read it as"
            " p123api-screen-backtest version 1:"
        ),
        (
            "So the normalized result is unavailable. The saved response is kept as it came; report"
            " the problem if it persists."
        ),
    ),
    "snapshot": (
        (
            "Portfolio123's answer to the rank_get request was saved, as {saved}, but it doesn't"
            " have the structure a snapshot needs:"
        ),
        (
            "The snapshot has no definition.xml or snapshot.json. The saved response is kept as it"
            " came; report the problem if it persists."
        ),
    ),
}
"""How the message of `provider.response_invalid` starts and ends, for a run and for a snapshot,
as written by hand: `invalid-structure.json`'s answer to a run's backtest, and
`rank-get-without-xml.json`'s to a snapshot's `rank_get`."""

ENDINGS_AFTER_AN_INVALID_RESPONSE: Final = {
    "a run's report": (DEFINITION, "/report.html", "run", RUN_INCOMPLETE),
    "a run's manifest": (DEFINITION, "/manifest.json", "run", RUN_INCOMPLETE),
    "a snapshot's manifest": (SNAPSHOT, "/manifest.json", "snapshot", SNAPSHOT_INCOMPLETE),
}
"""Each file of the ending a fault strikes after the saved response failed validation: a run's
report and its manifest, and a snapshot's manifest."""


@pytest.mark.parametrize("kind", FAULTS)
@pytest.mark.parametrize("at", ENDINGS_AFTER_AN_INVALID_RESPONSE)
def test_a_fault_at_the_ending_after_an_invalid_response_keeps_its_message_after_before_that(
    cli: Cli, faults: FaultyStores, at: str, kind: Fault
) -> None:
    configuration, name, what, incomplete = ENDINGS_AFTER_AN_INVALID_RESPONSE[at]
    cli.ready()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/rank", response("rank-update.json"), method="POST")
    cli.server.reply("/rank", rank_get("rank-get-without-xml.json"), method="GET")
    cli.server.reply("/screen/backtest", response("invalid-structure.json"))
    out = cli.tmp / "out"
    approve = snapshot_plan_hash() if configuration == SNAPSHOT else plan_hash_for(configuration)
    faults.fail(name, kind)

    outcome = cli(
        "run", configuration, "--out", out, "--approve", approve, "--json", store_factory=faults
    )

    # The fault decides the code, and its message says the output has no manifest, then keeps
    # the response's own after "Before that:" (execution outcomes and attempts).
    ending, earlier = failed(outcome, kind).split(" Before that: ")
    assert ending.endswith(incomplete)
    (saved,) = out.glob("**/response.json")
    start, end = RESPONSE_INVALID[what]
    assert earlier.startswith(start.format(saved=saved.relative_to(out).as_posix()))
    assert earlier.endswith(end)
    assert not (out / "manifest.json").exists()
    written_once(faults)
