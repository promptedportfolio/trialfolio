"""`trialfolio run` with an experiment whose cases fail: a failed case is recorded, and the later
cases still run; after a 403, the next case authenticates again; and after Trial Folio's own
authentication call fails, or after a request gets `provider.quota_exceeded`, no later case
starts, and a resume runs the cases not started.

Traces to R03-AC05's interface part (D-32), and to docs/contracts.md, the budget across runs (a
failure that every later case would get stops the run, and the message names the error and says
that a resume runs the cases not started), HTTP exchanges (when Trial Folio authenticates),
experiment attempts (`authenticated_by`), running an experiment (the cases that are due, and
`execution.partial`'s message, with the option that repeats a case), and the experiment manifest
(`outcome`). Each test writes `example.yaml`'s experiment with the experiment builder, through
the CLI's entry function in the test process, over the fake server, which answers a case's
request with a 400, a 404, a 503, a 403, or a 402, or Trial Folio's authentication call with a
401 or a 503. Each case's request is told apart by its body, which is the case's request as the
plan gives it.
"""

import functools
import json
from pathlib import Path
from typing import cast

import pytest

from tests.interface.conftest import Cli, Outcome
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


def cases_of(outcome: Outcome) -> dict[str, dict[str, object]]:
    """The summary's cases, by key."""
    cases = cast("list[dict[str, object]]", outcome.summary["cases"])
    return {cast("str", case["case_key"]): case for case in cases}


def error_of(outcome: Outcome) -> dict[str, str]:
    return cast("dict[str, str]", outcome.summary["error"])


def attempt_directories(out: Path, place: int) -> list[Path]:
    return sorted((out / "cases" / plan().cases[place].case_id / "attempts").iterdir())


def only_record(out: Path, place: int) -> AttemptRecordV1_1:
    """The attempt record of the case at `place`, which has one attempt."""
    (directory,) = attempt_directories(out, place)
    return AttemptRecordV1_1.model_validate_json((directory / "attempt.json").read_bytes())


def manifest(out: Path, session: int) -> ExperimentManifest:
    return ExperimentManifest.model_validate_json(
        (out / f"sessions/{session}/manifest.json").read_bytes()
    )


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
    error = error_of(ran)
    assert error["code"] == "execution.partial"
    assert f"`holdings-50`, {outcome} ({code})" in error["message"]
    assert f"--repeat holdings-50:{record.attempt_id}" in error["message"]
    session = manifest(out, 1)
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
    (directory,) = attempt_directories(out, HOLDINGS)
    assert (directory / "authenticating.json").is_file()
    start = StartRecordV1_1.model_validate_json((directory / "started.json").read_bytes())
    assert start.authenticated_by == start.attempt_id
    assert [(e.request, e.status) for e in start.exchanges] == [(AUTH, 200)]
    assert only_record(out, HOLDINGS).outcome == "succeeded"
    assert manifest(out, 1).counts.authentication_calls == 2


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
    cases = cases_of(ran)
    assert [cases[key]["outcome"] for key in later] == ["not_yet_run"] * len(later)
    assert all(
        not (out / "cases" / case.case_id).exists() for case in plan().cases[stopped_at + 1 :]
    )
    assert manifest(out, 1).counts.cases.not_yet_run == len(later)
    error = error_of(ran)
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
            for directory in attempt_directories(out, 0)
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
    assert len(attempt_directories(out, HOLDINGS)) == 1
    holdings = cases_of(resumed)["holdings-50"]
    assert (holdings["outcome"], holdings["repeat_attempt_id"]) == (
        "failed",
        str(quota.attempt_id),
    )
    assert f"--repeat holdings-50:{quota.attempt_id}" in error_of(resumed)["message"]
