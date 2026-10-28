"""A resumed experiment, through `trialfolio run`: each case keeps its `case_id` across restarts,
and each attempt has an ID of its own; an interruption after case n resumes at case n + 1, with no
request sent again; and a restart skips the complete cases, and records each attempt a stopped run
left without its attempt record, a repeat's included, flagging one whose completion is uncertain,
which it doesn't send again.

Traces to R03-AC02's interface part (the plan hash in separate processes, each case's `case_id` in
every record and manifest, and distinct version 4 attempt IDs), R03-AC04, and R03-AC06, and to
docs/contracts.md, uncertain completion, experiment attempts (the authentication record, and the
attempt record a later run writes), HTTP exchanges (a read timeout), running an experiment (the
cases that are due, and the plan display's progress), and JSON summary (`cases`). Each experiment
is written with the experiment builder, through the CLI's entry function in the test process, with
the real client, `requests`, and `urllib3` over the fake server, and stopped where the test needs
it: by an interrupt from the storage faults, or by storage faults at both writes of an attempt
record; or by `SIGKILL`, under the test launcher in a new process, while the fake server holds a
reply. The plan hash's check runs the command under the test launcher, and the plan display's
under a real pseudo-terminal in the test process.
"""

import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import cast

import pytest

from tests.support import launcher
from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    held,
    returns,
)
from tests.support.fake_portfolio123 import FakePortfolio123
from tests.support.saved_records import attempt_directories, attempt_records, session_manifest
from tests.support.storage_faults import FaultyStores
from tests.support.terminal import PseudoTerminal
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_1, AuthenticationRecord, StartRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, PlanV1_1
from trialfolio.planning import build_experiment_plan, installed_versions
from trialfolio.tables import read_metrics_csv, read_settings_csv

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="Windows has no SIGKILL and no pseudo-terminals"
)

EXAMPLE = experiment_config("example.yaml")
DEFAULT_ONLY = experiment_config("default-only.yaml")
AUTH = "POST /auth"
SEND = "POST /screen/backtest"
CASE_ID = re.compile(rb"case-[0-9a-f]{16}")
"""A `case_id`, as a file's bytes hold it."""

type Builder = ExperimentBuilder[Outcome]


def plan_of(path: Path) -> PlanV1_1:
    """The plan of a new experiment of the configuration at `path`, with the installed versions."""
    configuration = read_experiment_configuration(path.read_bytes(), str(path))
    return build_experiment_plan(configuration, installed_versions())


def sent(server: FakePortfolio123, plan: PlanV1_1, start: int = 0) -> list[str]:
    """The key of the case whose request each request the server received, from the `start`th on,
    sends, by its body, in order."""

    def params(case: ExperimentPlanCase) -> object:
        return case.requests[0].params.model_dump(mode="json")

    keys: list[str] = []
    for received in server.received[start:]:
        if received.path == "/screen/backtest":
            body = json.loads(received.body)
            (key,) = (case.case_key for case in plan.cases if params(case) == body)
            keys.append(key)
    return keys


def complete_cases_sent_once(server: FakePortfolio123, plan: PlanV1_1, outcome: Outcome) -> None:
    """The server received the request of each case that `outcome` gives as complete only once,
    in every run of the experiment."""
    keys = sent(server, plan)
    complete = [key for key, case in outcome.cases_by_key.items() if case["outcome"] == "succeeded"]
    assert complete
    assert all(keys.count(key) == 1 for key in complete), keys


def names(directory: Path) -> set[str]:
    return {path.name for path in directory.iterdir()}


# Case and attempt identities (R03-AC02)


def test_run_json_gives_the_same_plan_hash_in_separate_processes_and_output_directories(
    cli: Cli,
) -> None:
    cli.accept_license()
    hashes: list[object] = []
    # Each process hashes text with a seed of its own, so the plan can't depend on a set's order.
    for seed in ("1", "2"):
        out = cli.tmp / f"experiment-{seed}"
        result = subprocess.run(
            launcher.command(cli.server.endpoint, "run", EXAMPLE, "--out", out, "--json"),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            cwd=cli.tmp,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        # Without approval: the summary gives the hash to approve, and nothing is created.
        assert result.returncode == 2, result.stderr
        summary = json.loads(result.stdout)
        assert summary["error"]["code"] == "plan.approval_required"
        hashes.append(summary["ids"]["plan_hash"])
        assert not out.exists()

    assert hashes == [plan_of(EXAMPLE).plan_hash] * 2
    assert cli.server.requests() == []


def interrupted_resumed_and_repeated(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> tuple[Path, list[Outcome]]:
    """Writes `example.yaml`'s experiment in three runs: one interrupted just after the second
    case's tables; a resume, in which `holdings-50`'s request gets a 503, so it awaits a repeat;
    and a repeat of it that its attempt ID confirms. Returns the experiment's directory, and each
    run's outcome."""
    cli.ready()
    out = cli.tmp / "experiment"
    second = plan_of(EXAMPLE).cases[1]
    faults.fail_after(f"{second.case_id}/settings.csv", KeyboardInterrupt())
    interrupted = experiments.run(EXAMPLE, out, sends=[returns(), returns()], store_factory=faults)
    assert interrupted.exit_code == 130, interrupted.stderr
    resumed = experiments.run(EXAMPLE, out, sends=[UNAVAILABLE, returns(), returns()])
    assert resumed.exit_code == 6, resumed.stderr
    attempt = resumed.cases_by_key["holdings-50"]["repeat_attempt_id"]
    repeated = experiments.run(
        EXAMPLE, out, "--repeat", f"holdings-50:{attempt}", sends=[returns()]
    )
    assert repeated.exit_code == 0, repeated.stderr
    return out, [interrupted, resumed, repeated]


def test_an_interrupted_and_resumed_experiment_names_each_case_by_one_case_id_everywhere(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    out, outcomes = interrupted_resumed_and_repeated(cli, experiments, faults)
    plan = plan_of(EXAMPLE)
    identities = [(case.case_key, case.case_id) for case in plan.cases]
    ids = {case_id for _, case_id in identities}

    # Each run's summary, the plan, and its experiment.json give each key the same case_id.
    for outcome in outcomes:
        cases = outcome.cases
        assert [(case["case_key"], case["case_id"]) for case in cases] == identities
    saved_plan = json.loads((out / "plans/1/plan.json").read_bytes())
    assert [(case["case_key"], case["case_id"]) for case in saved_plan["cases"]] == identities
    record = json.loads((out / "plans/1/experiment.json").read_bytes())
    assert [(c["case_key"], c["case_id"]) for c in record["planned_cases"]] == identities
    # Each case's directory is named by its case_id, and each of its records, and each row of its
    # tables, names that case_id, and no other.
    assert {path.name for path in (out / "cases").iterdir()} == ids
    for case_id in ids:
        for directory in attempt_directories(out, case_id):
            for name in ("authenticating.json", "started.json", "attempt.json"):
                if (directory / name).exists():
                    assert json.loads((directory / name).read_bytes())["case_id"] == case_id
        metrics = (out / f"cases/{case_id}/normalized/metrics.csv").read_bytes()
        settings = (out / f"cases/{case_id}/normalized/settings.csv").read_bytes()
        assert {row.label for row in read_metrics_csv(metrics, "metrics")} == {case_id}
        assert {row.label for row in read_settings_csv(settings, "settings")} == {case_id}
    for path in (out / "cases").rglob("*"):
        if path.is_file():
            case_id = path.relative_to(out / "cases").parts[0]
            assert set(CASE_ID.findall(path.read_bytes())) <= {case_id.encode()}, path
    # Each manifest lists every case's files under that case_id, and names no other.
    assert not (out / "sessions/1/manifest.json").exists()
    for session in (2, 3):
        listed = session_manifest(out, session, ExperimentManifest).artifacts
        assert {a.path.split("/")[1] for a in listed if a.path.startswith("cases/")} == ids
        data = (out / f"sessions/{session}/manifest.json").read_bytes()
        assert {found.decode() for found in CASE_ID.findall(data)} == ids


def canonical_version_4(value: object) -> bool:
    """Whether `value` is a version 4 UUID's text in canonical form: lowercase, with hyphens."""
    return isinstance(value, str) and (
        str(uuid.UUID(value)) == value and uuid.UUID(value).version == 4
    )


def test_every_attempt_a_repeat_included_has_a_distinct_version_4_uuid_in_canonical_form(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    out, outcomes = interrupted_resumed_and_repeated(cli, experiments, faults)
    holdings = plan_of(EXAMPLE).cases[2].case_id

    directories = list((out / "cases").glob("*/attempts/*"))
    attempt_ids = [path.name for path in directories]
    # Two attempts in the first run, three in the resume, and the repeat: each its own.
    assert len(attempt_ids) == len(set(attempt_ids)) == 6
    assert all(canonical_version_4(attempt_id) for attempt_id in attempt_ids)
    for directory in directories:
        for name in ("authenticating.json", "started.json", "attempt.json"):
            if not (directory / name).exists():
                continue
            loaded = json.loads((directory / name).read_bytes())
            # Each record gives its attempt's ID, and names others by theirs, as written.
            assert loaded["attempt_id"] == directory.name
            for key in ("authenticated_by", "repeat_of"):
                assert loaded.get(key) is None or loaded[key] in attempt_ids
    first, repeat = attempt_records(out, holdings, AttemptRecordV1_1)
    assert repeat.repeat_of == first.attempt_id != repeat.attempt_id
    _, resumed, _ = outcomes
    assert resumed.cases_by_key["holdings-50"]["repeat_attempt_id"] == str(first.attempt_id)


# An interruption after case n resumes at case n + 1 (R03-AC04)


@pytest.mark.parametrize("n", [1, 4])
def test_an_interrupt_after_case_n_resumes_at_case_n_plus_1_and_sends_no_request_again(
    cli: Cli, experiments: Builder, faults: FaultyStores, n: int
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)
    case_id = plan.cases[n - 1].case_id
    faults.fail_after(f"{case_id}/settings.csv", KeyboardInterrupt())

    interrupted = experiments.run(
        EXAMPLE, out, sends=[returns() for _ in range(n)], store_factory=faults
    )

    assert interrupted.exit_code == 130
    assert interrupted.error_code == "command.interrupted"
    assert not (out / "sessions/1/manifest.json").exists()
    # The interrupt came just after case n's tables, the last files its attempt writes, after
    # its attempt record.
    last = faults.published[-3:]
    assert [path.rsplit("/", 1)[-1] for path in last] == [
        "attempt.json",
        "metrics.csv",
        "settings.csv",
    ]
    assert all(path.startswith(f"cases/{case_id}/") for path in last)
    received = len(cli.server.received)

    resumed = experiments.run(EXAMPLE, out, sends=[returns() for _ in range(5 - n)])

    assert resumed.exit_code == 0, resumed.stderr
    assert cli.server.requests()[received:] == [AUTH, *[SEND] * (5 - n)]
    # The requests of cases n + 1 to 5, each once, and none of cases 1 to n.
    keys = [case.case_key for case in plan.cases]
    assert sent(cli.server, plan, received) == keys[n:]
    assert sent(cli.server, plan) == keys
    counts = session_manifest(out, 2, ExperimentManifest).counts
    assert counts.cases.succeeded == 5
    attempts = counts.attempts
    assert (attempts.succeeded, attempts.failed, attempts.unknown, attempts.running) == (5, 0, 0, 0)
    assert (counts.provider_requests, counts.authentication_calls) == (5, 2)


# A restart skips complete cases and flags uncertain completion (R03-AC06)


@posix_only
def test_a_send_killed_mid_flight_is_recorded_as_unknown_and_awaits_a_repeat_unsent(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)
    second = plan.cases[1]

    experiments.kill(EXAMPLE, out, sends=[returns(), held(returns())], received=3)

    (directory,) = attempt_directories(out, second.case_id)
    assert names(directory) == {"request.json", "started.json"}
    start = StartRecordV1_1.model_validate_json((directory / "started.json").read_bytes())
    assert not (out / "sessions/1/manifest.json").exists()
    cli.server.reply("/auth", AUTHENTICATED)
    cli.server.reply("/screen/backtest", *[returns() for _ in range(3)])
    received = len(cli.server.received)

    with PseudoTerminal() as terminal:
        terminal.press("approve\n")
        outcome = cli(
            "run", EXAMPLE, "--out", out, "--json", stdin=terminal.stdin, stderr=terminal.stderr
        )
    shown = terminal.shown()

    option = f"--repeat {second.case_key}:{start.attempt_id}"
    awaiting = (
        "So far: unknown (command.interrupted), after 1 attempt. Its request may have reached"
        " Portfolio123, and may have been charged, so it's sent again only by a repeat, which may"
        f" be charged again: {option}"
    )
    case_line = f"Case {second.case_key} ({second.case_id}):"
    assert shown.index(case_line) < shown.index(awaiting) < shown.index("Type approve")
    assert outcome.exit_code == 6, shown
    assert outcome.error_code == "execution.partial"
    assert outcome.cases_by_key[second.case_key] == {
        "case_key": second.case_key,
        "case_id": second.case_id,
        "outcome": "unknown",
        "repeat_attempt_id": str(start.attempt_id),
    }
    # The resume sends the cases that are due, and not the second case's request again.
    assert cli.server.requests()[received:] == [AUTH, SEND, SEND, SEND]
    assert sent(cli.server, plan, received) == [case.case_key for case in plan.cases[2:]]
    complete_cases_sent_once(cli.server, plan, outcome)
    # Its attempt record, written by the resume, keeps what its start record holds.
    record = AttemptRecordV1_1.model_validate_json((directory / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert record.attempt_id == start.attempt_id
    assert (record.exchanges, record.session, record.sequence, record.repeat_of) == (
        start.exchanges,
        start.session,
        start.sequence,
        start.repeat_of,
    )
    assert (record.session, record.sequence, record.authenticated_by) == (
        1,
        2,
        start.authenticated_by,
    )
    assert record.response is None


@posix_only
def test_a_repeat_killed_mid_flight_is_recorded_with_its_start_records_exchanges_and_repeat_of(
    cli: Cli, experiments: Builder
) -> None:
    # The second case above sends with the session's token, and isn't a repeat, so its start
    # record has no exchange and no repeat_of. A repeat is its session's first attempt, which
    # authenticates, and names the attempt it repeats.
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)
    holdings = plan.cases[2]
    first = experiments.run(
        EXAMPLE, out, sends=[returns(), returns(), UNAVAILABLE, returns(), returns()]
    )
    assert first.exit_code == 6, first.stderr
    repeated = cast("str", first.cases_by_key[holdings.case_key]["repeat_attempt_id"])

    experiments.kill(
        EXAMPLE,
        out,
        "--repeat",
        f"{holdings.case_key}:{repeated}",
        sends=[held(returns())],
        received=2,
    )

    (directory,) = [
        path for path in attempt_directories(out, holdings.case_id) if path.name != repeated
    ]
    assert names(directory) == {"authenticating.json", "request.json", "started.json"}
    start = StartRecordV1_1.model_validate_json((directory / "started.json").read_bytes())
    assert str(start.repeat_of) == repeated
    received = len(cli.server.received)

    resumed = experiments.run(EXAMPLE, out)

    assert resumed.exit_code == 6, resumed.stderr
    assert len(cli.server.received) == received
    record = AttemptRecordV1_1.model_validate_json((directory / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert (record.exchanges, record.session, record.sequence, record.repeat_of) == (
        start.exchanges,
        start.session,
        start.sequence,
        start.repeat_of,
    )
    assert [(e.request, e.status) for e in record.exchanges] == [(AUTH, 200)]
    assert (record.session, record.sequence) == (2, 1)
    # The killed repeat is now the case's latest possibly charged attempt.
    assert resumed.cases_by_key[holdings.case_key]["repeat_attempt_id"] == str(record.attempt_id)
    complete_cases_sent_once(cli.server, plan, resumed)


def test_an_attempt_record_unwritten_after_its_response_was_saved_is_completed_from_it(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(DEFAULT_ONLY)
    baseline, rebalance = plan.cases
    # Both writes of its attempt.json fail: the first is interrupted before it starts, and the
    # second, which an interrupt gives a record that wasn't published, fails as a full disk would.
    faults.fail_before(f"{baseline.case_id}/attempt.json", KeyboardInterrupt())
    faults.fail_os(f"{baseline.case_id}/attempt.json")

    interrupted = experiments.run(DEFAULT_ONLY, out, sends=[returns()], store_factory=faults)

    assert interrupted.exit_code == 130
    assert interrupted.error_code == "command.interrupted"
    (directory,) = attempt_directories(out, baseline.case_id)
    assert names(directory) == {
        "authenticating.json",
        "request.json",
        "started.json",
        "response.json",
    }
    assert not (out / f"cases/{baseline.case_id}/normalized").exists()
    received = len(cli.server.received)

    resumed = experiments.run(DEFAULT_ONLY, out, sends=[returns()])

    assert resumed.exit_code == 0, resumed.stderr
    # Only the other case is sent.
    assert cli.server.requests()[received:] == [AUTH, SEND]
    assert sent(cli.server, plan, received) == [rebalance.case_key]
    complete_cases_sent_once(cli.server, plan, resumed)
    record = AttemptRecordV1_1.model_validate_json((directory / "attempt.json").read_bytes())
    assert (record.outcome, record.error, record.possibly_charged) == ("succeeded", None, True)
    assert [(e.request, e.result, e.status, e.note) for e in record.exchanges] == [
        (AUTH, "response", 200, None),
        (SEND, "response", 200, "completed_from_saved_response"),
    ]
    assert record.response is not None
    assert (
        record.response.path == f"cases/{baseline.case_id}/attempts/{directory.name}/response.json"
    )
    # The case's tables, which the stopped run didn't write, from its saved response.
    normalized = out / f"cases/{baseline.case_id}/normalized"
    metrics = read_metrics_csv((normalized / "metrics.csv").read_bytes(), "metrics")
    settings = read_settings_csv((normalized / "settings.csv").read_bytes(), "settings")
    assert {row.source_artifact for row in metrics} == {record.response.artifact_id}
    assert {row.label for row in (*metrics, *settings)} == {baseline.case_id}
    assert resumed.cases_by_key[baseline.case_key]["outcome"] == "succeeded"


@posix_only
def test_an_authentication_call_killed_mid_flight_is_failed_counted_and_its_case_sent(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(DEFAULT_ONLY)
    baseline, _ = plan.cases

    experiments.kill(DEFAULT_ONLY, out, authenticates=[held(AUTHENTICATED)], received=1)

    (directory,) = attempt_directories(out, baseline.case_id)
    assert names(directory) == {"authenticating.json"}
    authentication = AuthenticationRecord.model_validate_json(
        (directory / "authenticating.json").read_bytes()
    )
    # Its record alone counts the call against the budget, before a resume records the attempt.
    unapproved = experiments.run(DEFAULT_ONLY, out, approve=False)
    assert unapproved.error_code == "plan.approval_required"
    counts = unapproved.counts
    assert (counts["authentication_calls"], counts["provider_requests"]) == (1, 0)
    assert "0 provider requests and 1 authentication call" in unapproved.stderr
    received = len(cli.server.received)

    resumed = experiments.run(DEFAULT_ONLY, out, sends=[returns(), returns()])

    assert resumed.exit_code == 0, resumed.stderr
    # Nothing was sent, so the case is due, and the resume sends it.
    assert cli.server.requests()[received:] == [AUTH, SEND, SEND]
    assert sent(cli.server, plan, received) == [case.case_key for case in plan.cases]
    old, new = attempt_records(out, baseline.case_id, AttemptRecordV1_1)
    assert old.attempt_id == authentication.attempt_id
    assert (old.outcome, old.possibly_charged, old.request) == ("failed", False, None)
    assert old.error is not None and old.error.code == "command.interrupted"
    assert [(e.request, e.result, e.status) for e in old.exchanges] == [(AUTH, "interrupted", None)]
    assert (old.session, old.sequence, old.repeat_of) == (
        authentication.session,
        authentication.sequence,
        authentication.repeat_of,
    )
    assert (new.session, new.outcome) == (2, "succeeded")
    # The killed call counts against the budget, beside the resume's.
    counts = session_manifest(out, 2, ExperimentManifest).counts
    assert (counts.authentication_calls, counts.provider_requests) == (2, 2)
    assert resumed.counts["authentication_calls"] == 2


def test_a_read_timeout_leaves_its_case_unknown_the_later_cases_run_and_a_resume_doesnt_send_it(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    plan = plan_of(EXAMPLE)
    second = plan.cases[1]
    cli.server.reply("/auth", AUTHENTICATED)
    # The server holds the second case's response past the request timeout.
    cli.server.reply(
        "/screen/backtest", returns(), held(returns()), returns(), returns(), returns()
    )

    outcome = cli(
        "run",
        EXAMPLE,
        "--out",
        out,
        "--approve",
        plan.plan_hash,
        "--json",
        timeout=launcher.SHORTEST_TIMEOUT_SECONDS,
    )

    assert outcome.exit_code == 6, outcome.stderr
    assert outcome.error_code == "execution.partial"
    (record,) = attempt_records(out, second.case_id, AttemptRecordV1_1)
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert record.error is not None and record.error.code == "provider.outcome_unknown"
    assert [(e.request, e.result) for e in record.exchanges] == [(SEND, "interrupted")]
    # The later cases still ran.
    assert sent(cli.server, plan) == [case.case_key for case in plan.cases]
    outcomes = [case["outcome"] for case in outcome.cases_by_key.values()]
    assert outcomes == ["succeeded", "unknown", "succeeded", "succeeded", "succeeded"]
    received = len(cli.server.received)

    resumed = experiments.run(EXAMPLE, out)

    assert resumed.exit_code == 6, resumed.stderr
    assert len(cli.server.received) == received
    # Nor does it start an attempt of any case.
    assert len(list(out.glob("cases/*/attempts/*"))) == 5
    assert resumed.cases_by_key[second.case_key]["outcome"] == "unknown"
    assert resumed.cases_by_key[second.case_key]["repeat_attempt_id"] == str(record.attempt_id)
    complete_cases_sent_once(cli.server, plan, resumed)
