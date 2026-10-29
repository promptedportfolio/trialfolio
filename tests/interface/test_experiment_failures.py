"""`trialfolio run` with an experiment whose cases fail: a failed case is recorded, and the later
cases still run; after a 403, the next case authenticates again; and after Trial Folio's own
authentication call fails, or after a request gets `provider.quota_exceeded`, no later case
starts, and a resume runs the cases not started.

Traces to R03-AC05's interface part (D-32), and to docs/contracts.md, the budget across runs (a
failure that every later case would get stops the run, and the message names the error and says
that a resume runs the cases not started), HTTP exchanges (when Trial Folio authenticates),
experiment attempts (`authenticated_by`), running an experiment (the cases that are due, and
`execution.partial`'s message, with the option that repeats a case), the experiment manifest
(`outcome`), and logging (which attempt endings the terminal shows, D-38). Each test writes
`example.yaml`'s experiment with the experiment builder, through the CLI's entry function in the
test process, over the fake server, which answers a case's request with a 400, a 404, a 503, a
403, or a 402, or Trial Folio's authentication call with a 401 or a 503; three tests also fail a
write with the storage faults: an attempt record's, and a case's request's, as on a full disk or
unexpectedly. Each case's request is told apart by its body, which is the case's request as the
plan gives it.
"""

import functools
import json
from pathlib import Path

import pytest

from tests.support.cli import Cli
from tests.support.environment import Outcome
from tests.support.experiment_builder import (
    AUTHENTICATED,
    REFUSED,
    REJECTED,
    UNAVAILABLE,
    ExperimentBuilder,
    experiment_config,
    returns,
)
from tests.support.fake_portfolio123 import Reply
from tests.support.saved_records import attempt_directories, session_manifest
from tests.support.socket_faults import SocketFaults
from tests.support.storage_faults import FaultyStores
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_1, StartRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.planning import build_experiment_plan, installed_versions

EXAMPLE = experiment_config("example.yaml")
KEYS = ["baseline", "liquidity-100m", "holdings-50", "rebalance-weeks-1", "slippage-050"]
"""`example.yaml`'s cases, in the plan's order."""
HOLDINGS = KEYS.index("holdings-50")
AUTH = "POST /auth"
SEND = "POST /screen/backtest"

QUOTA = Reply(402, b"")
"""A 402 to a case's request: `failed`, possibly charged, with `provider.quota_exceeded`."""

FORBIDDEN = Reply(403, b"")
"""A 403 to a case's request: `failed`, possibly charged, with `provider.auth_failed`, and the
client's token is dropped."""

type Builder = ExperimentBuilder[Outcome]


@functools.cache
def plan() -> PlanV1_1:
    """The plan of a new experiment of `example.yaml`, with the installed versions."""
    configuration = read_experiment_configuration(EXAMPLE.read_bytes(), str(EXAMPLE))
    return build_experiment_plan(configuration, installed_versions())


def sent(cli: Cli, since: int = 0) -> list[str]:
    """The key of each case whose request the server received after the first `since` requests,
    in order, told by its body."""
    bodies = {
        json.dumps(case.requests[0].params.model_dump(mode="json"), sort_keys=True): case.case_key
        for case in plan().cases
    }
    return [
        bodies[json.dumps(json.loads(received.body), sort_keys=True)]
        for received in cli.server.received[since:]
        if received.path == "/screen/backtest"
    ]


def attempts_at(out: Path, place: int) -> list[Path]:
    """The attempts' directories of the case at `place` in the plan."""
    return attempt_directories(out, plan().cases[place].case_id)


def only_record(out: Path, place: int) -> AttemptRecordV1_1:
    """The attempt record of the case at `place`, which has one attempt."""
    (directory,) = attempts_at(out, place)
    return AttemptRecordV1_1.model_validate_json((directory / "attempt.json").read_bytes())


# A failed case is recorded, and the later cases still run


@pytest.mark.parametrize(
    ("reply", "outcome", "code"),
    [
        pytest.param(REJECTED, "failed", "provider.unsupported_capability", id="400"),
        pytest.param(Reply(404, b""), "failed", "provider.request_rejected", id="404"),
        pytest.param(UNAVAILABLE, "unknown", "provider.outcome_unknown", id="503"),
    ],
)
def test_a_failed_case_is_recorded_the_later_cases_still_run_and_the_command_exits_6(
    cli: Cli, experiments: Builder, reply: Reply, outcome: str, code: str
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    ran = experiments.run(EXAMPLE, out, sends=[returns(), returns(), reply, returns(), returns()])

    assert ran.exit_code == 6, ran.stderr
    record = only_record(out, HOLDINGS)
    assert (record.outcome, record.possibly_charged) == (outcome, True)
    assert record.error is not None and record.error.code == code
    # The later cases still run, each sent once, after the one authentication.
    assert cli.server.requests() == [AUTH, *[SEND] * 5]
    assert sent(cli) == KEYS
    assert [only_record(out, place).outcome for place in (HOLDINGS + 1, HOLDINGS + 2)] == [
        "succeeded",
        "succeeded",
    ]
    error = ran.error
    assert error["code"] == "execution.partial"
    assert f"`holdings-50`, {outcome} ({code})" in error["message"]
    assert f"--repeat holdings-50:{record.attempt_id}" in error["message"]
    session = session_manifest(out, 1, ExperimentManifest)
    assert session.outcome == "partial"
    assert session.error is not None and session.error.code == "execution.partial"


def test_after_a_403_the_next_case_authenticates_again_and_its_request_is_sent(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    ran = experiments.run(
        EXAMPLE,
        out,
        sends=[returns(), FORBIDDEN, returns(), returns(), returns()],
        authenticates=[AUTHENTICATED, AUTHENTICATED],
    )

    assert ran.exit_code == 6, ran.stderr
    forbidden = only_record(out, 1)
    assert (forbidden.outcome, forbidden.possibly_charged) == ("failed", True)
    assert forbidden.error is not None and forbidden.error.code == "provider.auth_failed"
    # The 403 dropped the token, so the next case's attempt authenticates before its send.
    assert cli.server.requests() == [AUTH, SEND, SEND, AUTH, SEND, SEND, SEND]
    assert sent(cli) == KEYS
    (directory,) = attempts_at(out, HOLDINGS)
    assert (directory / "authenticating.json").is_file()
    start = StartRecordV1_1.model_validate_json((directory / "started.json").read_bytes())
    assert start.authenticated_by == start.attempt_id
    assert [(e.request, e.status) for e in start.exchanges] == [(AUTH, 200)]
    assert only_record(out, HOLDINGS).outcome == "succeeded"
    assert session_manifest(out, 1, ExperimentManifest).counts.authentication_calls == 2


# What a failed case shows: its ending, Portfolio123's message, and what to do (D-38)

MISSPELLED = Reply(
    409, b"ERROR: Invalid criteria in Rule 2. Error near 'MktCapp': Invalid command 'MktCapp'"
)
"""A 409 to a case's request, as Portfolio123 answered a rule that names no factor in 0.3.0's
live walk-through: `failed`, possibly charged, with `provider.unsupported_capability`."""


@pytest.mark.parametrize(
    ("reply", "code", "revise"),
    [
        pytest.param(REJECTED, "provider.unsupported_capability", True, id="400"),
        pytest.param(MISSPELLED, "provider.unsupported_capability", True, id="409"),
        pytest.param(
            Reply(429, b"Too many requests"), "provider.request_rejected", False, id="429"
        ),
    ],
)
def test_a_failed_case_shows_its_ending_portfolio123s_message_and_the_sessions_report(
    cli: Cli, experiments: Builder, reply: Reply, code: str, revise: bool
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    ran = experiments.run(EXAMPLE, out, sends=[returns(), returns(), reply, returns(), returns()])

    assert ran.exit_code == 6, ran.stderr
    record = only_record(out, HOLDINGS)
    assert record.error is not None and record.error.code == code
    holdings = plan().cases[HOLDINGS].case_id
    lines = ran.stderr.splitlines()
    # Each case's place among the cases the session sends, and each attempt's ending, the failed
    # one's included, by the case's `case_id`.
    assert [line for line in lines if line.startswith("Case ")] == [
        f"Case {place} of 5 this session: {case.case_id}."
        for place, case in enumerate(plan().cases, 1)
    ]
    endings = [line for line in lines if line.startswith("Attempt for ")]
    assert [line.split(" ended ")[0] for line in endings] == [
        f"Attempt for {case.case_id}" for case in plan().cases
    ]
    assert endings[HOLDINGS].startswith(f"Attempt for {holdings} ended failed after ")
    assert endings[HOLDINGS].endswith(
        f": {code}; possibly charged: yes; attempt record written: yes."
    )
    text = reply.body.decode()
    rejected = (
        "Portfolio123 rejected a setting of `holdings-50`: a repeat sends the same request"
        " again, so change the setting instead, and revise the plan with --revision-reason."
    )
    message = ran.error["message"]
    assert f'Portfolio123\'s message for `holdings-50`: "{text}".' in message
    assert (rejected in message) is revise
    assert message.endswith(
        f"Session 1's report gives each case's attempts: {out / 'sessions/1/report.html'}."
    )
    # The log names the case by its `case_id`, and holds none of Portfolio123's message, the
    # revision's sentence, and the report's path.
    log = (out / "logs/trialfolio.log").read_text(encoding="utf-8")
    assert f"{holdings}, failed ({code})" in log
    assert text not in log
    assert "holdings-50" not in log
    assert "Portfolio123 rejected a setting of" not in log
    assert "report gives each case's attempts" not in log

    # A resume reads Portfolio123's message from the attempt record.
    resumed = experiments.run(EXAMPLE, out)

    assert resumed.exit_code == 6, resumed.stderr
    message = resumed.error["message"]
    assert f'Portfolio123\'s message for `holdings-50`: "{text}".' in message
    assert (rejected in message) is revise
    assert message.endswith(
        f"Session 2's report gives each case's attempts: {out / 'sessions/2/report.html'}."
    )
    assert not [line for line in resumed.stderr.splitlines() if line.startswith("Case ")]


def test_an_attempt_interrupted_during_its_send_leaves_its_ending_to_the_command(
    cli: Cli, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    cli.server.reply("/auth", AUTHENTICATED)
    with monkeypatch.context() as patch:
        SocketFaults(patch).interrupt_send(b"POST /screen/backtest")
        interrupted = cli("run", EXAMPLE, "--out", out, "--approve", plan().plan_hash)

    assert interrupted.exit_code == 130, interrupted.stderr
    assert f"Case 1 of 5 this session: {plan().cases[0].case_id}." in interrupted.stderr
    assert "Attempt for " not in interrupted.stderr
    assert "Error (command.interrupted): " in interrupted.stderr


def test_an_attempt_whose_record_isnt_written_leaves_its_ending_to_the_command(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # The first case's request gets a 503, so its outcome is unknown, and the write of its
    # attempt record fails unexpectedly, so the record isn't written, and the session ends.
    faults.fail_before("attempt.json", RuntimeError())

    ran = experiments.run(EXAMPLE, out, sends=[UNAVAILABLE], store_factory=faults)

    assert ran.exit_code == 5, ran.stderr
    first = plan().cases[0].case_id
    assert not list((out / "cases" / first / "attempts").glob("*/attempt.json"))
    assert f"Case 1 of 5 this session: {first}." in ran.stderr
    # The command's error follows, so the terminal doesn't show the attempt's ending too.
    assert "Attempt for " not in ran.stderr
    assert "Error (provider.outcome_unknown): " in ran.stderr


def test_an_attempt_a_storage_failure_ended_leaves_its_ending_to_the_command(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # The write of the first case's request fails as on a full disk, so its attempt ends with
    # `storage.write_failed` before its send, and its attempt record is written.
    faults.fail_os("request.json")

    ran = experiments.run(EXAMPLE, out, authenticates=[AUTHENTICATED], store_factory=faults)

    assert ran.exit_code == 4, ran.stderr
    record = only_record(out, 0)
    assert record.error is not None and record.error.code == "storage.write_failed"
    assert f"Case 1 of 5 this session: {plan().cases[0].case_id}." in ran.stderr
    # The session ends there, and the command's error follows, so the terminal doesn't show the
    # attempt's ending too.
    assert "Attempt for " not in ran.stderr
    assert "Error (storage.write_failed): " in ran.stderr
    assert cli.server.requests() == [AUTH]


def test_a_recorded_internal_error_shows_its_ending_and_the_session_goes_on(
    cli: Cli, experiments: Builder, faults: FaultyStores
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    # The write of the first case's request fails unexpectedly once the store has published it,
    # so its attempt ends with `internal.unexpected` before its send, and its attempt record is
    # written. The owner decided on 2026-10-13 that the terminal shows such an ending (D-38).
    faults.fail_after("request.json", RuntimeError())

    ran = experiments.run(EXAMPLE, out, sends=[returns()] * 4, store_factory=faults)

    assert ran.exit_code == 6, ran.stderr
    record = only_record(out, 0)
    assert (record.outcome, record.possibly_charged) == ("failed", False)
    assert record.error is not None and record.error.code == "internal.unexpected"
    first, second = (case.case_id for case in plan().cases[:2])
    lines = ran.stderr.splitlines()
    # The first case's ending, by its `case_id`, comes before the next case starts.
    (ending,) = [line for line in lines if line.startswith(f"Attempt for {first} ")]
    assert ending.startswith(f"Attempt for {first} ended failed after ")
    assert ending.endswith(
        ": internal.unexpected; possibly charged: no; attempt record written: yes."
    )
    assert lines.index(ending) < lines.index(f"Case 2 of 5 this session: {second}.")
    # The session goes on: each later case is sent, with the session's token.
    assert cli.server.requests() == [AUTH, *[SEND] * 4]
    assert sent(cli) == KEYS[1:]
    error = ran.error
    assert error["code"] == "execution.partial"
    assert "`baseline`, failed (internal.unexpected)" in error["message"]


# A failure every later case would get: no later case starts (D-32)


@pytest.mark.parametrize(
    ("authenticates", "sends", "requests", "stopped_at", "code"),
    [
        pytest.param(
            [AUTHENTICATED],
            [returns(), returns(), QUOTA],
            [AUTH, SEND, SEND, SEND],
            HOLDINGS,
            "provider.quota_exceeded",
            id="request-402",
        ),
        pytest.param([REFUSED], [], [AUTH], 0, "provider.auth_failed", id="authentication-401"),
        pytest.param(
            [Reply(503, b"")], [], [AUTH], 0, "provider.unavailable", id="authentication-503"
        ),
        pytest.param(
            [AUTHENTICATED, REFUSED],
            [returns(), FORBIDDEN],
            [AUTH, SEND, SEND, AUTH],
            HOLDINGS,
            "provider.auth_failed",
            id="authentication-401-after-a-403",
        ),
        pytest.param(
            [AUTHENTICATED, Reply(503, b"")],
            [returns(), FORBIDDEN],
            [AUTH, SEND, SEND, AUTH],
            HOLDINGS,
            "provider.unavailable",
            id="authentication-503-after-a-403",
        ),
    ],
)
def test_after_a_failure_every_later_case_would_get_no_later_case_starts(
    cli: Cli,
    experiments: Builder,
    authenticates: list[Reply],
    sends: list[Reply],
    requests: list[str],
    stopped_at: int,
    code: str,
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"

    ran = experiments.run(EXAMPLE, out, sends=sends, authenticates=authenticates)

    assert ran.exit_code == 6, ran.stderr
    stopped = only_record(out, stopped_at)
    assert stopped.error is not None and stopped.error.code == code
    # The server receives nothing more, and no later case has an attempt.
    assert cli.server.requests() == requests
    later = KEYS[stopped_at + 1 :]
    cases = ran.cases_by_key
    assert [cases[key]["outcome"] for key in later] == ["not_yet_run"] * len(later)
    assert all(
        not (out / "cases" / case.case_id).exists() for case in plan().cases[stopped_at + 1 :]
    )
    assert session_manifest(out, 1, ExperimentManifest).counts.cases.not_yet_run == len(later)
    error = ran.error
    assert error["code"] == "execution.partial"
    assert f"The error was {code}." in error["message"]
    assert "resumes the experiment, and runs the cases not started" in error["message"]


def test_a_resume_after_a_401_sends_each_case_not_started_the_one_refused_included(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, authenticates=[REFUSED]).exit_code == 6
    received = len(cli.server.received)

    resumed = experiments.run(EXAMPLE, out, sends=[returns() for _ in KEYS])

    assert resumed.exit_code == 0, resumed.stderr
    assert cli.server.requests()[received:] == [AUTH, *[SEND] * 5]
    assert sent(cli, received) == KEYS
    attempts = sorted(
        (
            AttemptRecordV1_1.model_validate_json((directory / "attempt.json").read_bytes())
            for directory in attempts_at(out, 0)
        ),
        key=lambda record: record.session,
    )
    assert [(a.session, a.outcome, a.repeat_of) for a in attempts] == [
        (1, "failed", None),
        (2, "succeeded", None),
    ]


def test_a_resume_after_a_402_sends_each_case_not_started_but_the_one_that_got_it(
    cli: Cli, experiments: Builder
) -> None:
    cli.ready()
    out = cli.tmp / "experiment"
    assert experiments.run(EXAMPLE, out, sends=[returns(), returns(), QUOTA]).exit_code == 6
    quota = only_record(out, HOLDINGS)
    received = len(cli.server.received)

    resumed = experiments.run(EXAMPLE, out, sends=[returns(), returns()])

    assert resumed.exit_code == 6, resumed.stderr
    assert cli.server.requests()[received:] == [AUTH, SEND, SEND]
    assert sent(cli, received) == KEYS[HOLDINGS + 1 :]
    # The case that got the 402 may have been charged, so it awaits a repeat.
    assert len(attempts_at(out, HOLDINGS)) == 1
    holdings = resumed.cases_by_key["holdings-50"]
    assert (holdings["outcome"], holdings["repeat_attempt_id"]) == (
        "failed",
        str(quota.attempt_id),
    )
    assert f"--repeat holdings-50:{quota.attempt_id}" in resumed.error["message"]
