"""The pause between a `rank_update`'s 200 and its backtest, in the core (D-45): every attempt that
sends a definition waits, once its `rank_update`'s response is saved, until at least 10 seconds
have passed on a monotonic clock since that 200 arrived, and only then writes its backtest's
request and start record, and sends the backtest.

Traces to docs/contracts.md, sending a definition (the pause, its place among the attempt's
files, cancellation, and what an interrupt during it leaves), uncertain completion and an attempt
stopped after its update record (what a resume records of one interrupted during the pause), and
logging and local diagnostics (`attempt.backtest.waiting`); and to D-45. The real client,
`requests`, and `urllib3` run over the fake server; the pause is the fake pause, whose monotonic
clock moves only when it sleeps, or when a test moves it, and which records what the server had
received at each sleep; storage faults wrap the real store; the clock is fixed; and every
execution takes the ranking lock on a file in the test's temporary directory.
"""

import logging
from pathlib import Path

import pytest

from tests.support.clock import FakePause, FixedClock, Slept
from tests.support.experiment_lab import Lab
from tests.support.fake_portfolio123 import (
    AUTH,
    AUTHENTICATED,
    BACKTEST,
    CREDENTIALS,
    RANK,
    FakePortfolio123,
    Reply,
    distinct,
    exchange,
    response,
)
from tests.support.file_faults import Faults, once
from tests.support.paths import EXPERIMENT_CONFIGS, screen_config
from tests.support.plans import ranked_experiment, ranked_screen, screen_plan
from tests.support.saved_records import only_attempt
from tests.support.storage_faults import Fault
from trialfolio.contracts.attempt import AttemptRecordV1_2, AttemptRecordV1_3
from trialfolio.contracts.manifest import CommandRecord
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.experiment_execution import Cancellation
from trialfolio.pause import UPDATE_PAUSE_SECONDS
from trialfolio.provider import P123ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.storage import LocalArtifactStore

COMMAND = CommandRecord(name="run", options={}, started_at=FixedClock()())
WAITING = "attempt.backtest.waiting"


SCREEN = screen_config("definition.yaml")
FORMULA = screen_config("formula.yaml")


def client(server: FakePortfolio123) -> P123ScreenBacktestClient:
    return P123ScreenBacktestClient(CREDENTIALS, endpoint=server.endpoint)


def run_screen(
    tmp_path: Path, server: FakePortfolio123, pause: FakePause
) -> TrialFolioError | None:
    planned = ranked_screen()
    content, definition, plan = planned.content, planned.definition, planned.plan
    with LocalArtifactStore(tmp_path / "out") as store:
        return Execution(
            plan,
            plan.plan_hash,
            "option",
            store,
            COMMAND,
            clock=FixedClock(),
            ranking_lock=tmp_path / LOCK_FILE,
            pause=pause.pause,
        ).run(content, lambda: client(server), definition=definition)


def script(server: FakePortfolio123, cases: int, *, auths: int = 1) -> None:
    server.reply("/auth", *(AUTHENTICATED for _ in range(auths)))
    server.reply("/rank", *(response("rank-update.json") for _ in range(cases)), method="POST")
    server.reply(
        "/screen/backtest", *distinct(*(response("complete.json").body for _ in range(cases)))
    )


# Where the pause comes, and how long it lasts


def test_a_screen_runs_backtest_is_sent_10_seconds_after_its_rank_updates_200(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
    pause = FakePause(server)

    error = run_screen(tmp_path, server, pause)

    assert error is None
    # One wait, after the rank_update's 200 and before the backtest was sent, of 10 seconds on
    # the monotonic clock, which nothing else moved.
    assert pause.slept == [Slept(UPDATE_PAUSE_SECONDS, (AUTH, RANK))]
    assert pause.now - 1000.0 == UPDATE_PAUSE_SECONDS
    assert server.requests() == [AUTH, RANK, BACKTEST]


def test_each_case_of_an_experiment_waits_once_between_its_two_calls(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    script(server, 4)
    pause = FakePause(server)

    execution = Lab(tmp_path, server).new(pause=pause.pause).executed

    assert [outcome for _, outcome in execution.outcomes] == ["succeeded"] * 4
    assert pause.slept == [
        Slept(UPDATE_PAUSE_SECONDS, (AUTH, *(RANK, BACKTEST) * place, RANK)) for place in range(4)
    ]


def test_the_wait_is_measured_from_the_rank_updates_200(
    tmp_path: Path, server: FakePortfolio123, faults: Faults
) -> None:
    # Saving the rank_update's response takes 4 seconds, so 6 remain of the 10 after its 200.
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
    pause = FakePause(server)
    faults.on_write("rank-update-response.json", once(lambda: pause.advance(4)))

    error = run_screen(tmp_path, server, pause)

    assert error is None
    assert pause.slept == [Slept(UPDATE_PAUSE_SECONDS - 4, (AUTH, RANK))]


def test_nothing_is_logged_or_waited_once_10_seconds_have_passed(
    tmp_path: Path, server: FakePortfolio123, faults: Faults, caplog: pytest.LogCaptureFixture
) -> None:
    # Saving the rank_update's response takes 10 seconds, so no time is left to wait: the
    # attempt sends its backtest without sleeping, or logging that it waits.
    caplog.set_level(logging.INFO, logger="trialfolio")
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
    pause = FakePause(server)
    faults.on_write("rank-update-response.json", once(lambda: pause.advance(UPDATE_PAUSE_SECONDS)))

    error = run_screen(tmp_path, server, pause)

    assert error is None
    assert server.requests() == [AUTH, RANK, BACKTEST]
    assert pause.slept == []
    assert WAITING not in {getattr(record, "event", None) for record in caplog.records}


def test_a_sleep_that_ends_early_is_followed_by_another_until_10_seconds_have_passed(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
    pause = FakePause(server, shortfalls=[4.5])

    error = run_screen(tmp_path, server, pause)

    assert error is None
    assert pause.slept == [Slept(10, (AUTH, RANK)), Slept(4.5, (AUTH, RANK))]
    assert pause.now - 1000.0 == UPDATE_PAUSE_SECONDS


def test_no_attempt_waits_without_a_definition(tmp_path: Path, server: FakePortfolio123) -> None:
    content = FORMULA.read_bytes()
    plan = screen_plan(FORMULA)
    server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    server.reply(
        "/screen/backtest",
        *distinct(
            response("complete.json").body,
            response("complete.json").body,
            response("complete.json").body,
        ),
    )
    pause = FakePause(server)
    with LocalArtifactStore(tmp_path / "run") as store:
        error = Execution(
            plan, plan.plan_hash, "option", store, COMMAND, clock=FixedClock(), pause=pause.pause
        ).run(content, lambda: client(server))
    assert error is None

    # An experiment without a definition, plan 1.1.0, doesn't wait either.
    Lab(tmp_path, server).new("default-only.yaml", pause=pause.pause)

    assert server.requests() == [AUTH, BACKTEST, AUTH, BACKTEST, BACKTEST]
    assert pause.slept == []


def test_the_demos_client_never_waits(
    tmp_path: Path, server: FakePortfolio123, caplog: pytest.LogCaptureFixture
) -> None:
    # It sends nothing, so nothing ranks a backtest.
    caplog.set_level(logging.INFO, logger="trialfolio")
    pause = FakePause()
    planned = ranked_screen()
    content, definition, plan = planned.content, planned.definition, planned.plan
    with LocalArtifactStore(tmp_path / "run") as store:
        error = Execution(
            plan,
            plan.plan_hash,
            "not_required",
            store,
            None,
            clock=FixedClock(),
            ranking_lock=tmp_path / LOCK_FILE,
            pause=pause.pause,
        ).run(
            content, lambda: SyntheticScreenBacktestClient(response_bytes()), definition=definition
        )
    assert error is None
    made = Lab(tmp_path, server).new(synthetic=True, pause=pause.pause).error

    assert made is None
    assert pause.slept == []
    assert WAITING not in {getattr(record, "event", None) for record in caplog.records}


@pytest.mark.parametrize(
    "reply",
    [Reply(400, b"Invalid ranking system"), Reply(200, b"<html>not JSON</html>")],
    ids=["400", "200 not JSON"],
)
def test_no_wait_follows_a_rank_update_whose_200_wasnt_decoded_and_saved(
    tmp_path: Path, server: FakePortfolio123, reply: Reply
) -> None:
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", reply, method="POST")
    pause = FakePause(server)

    error = run_screen(tmp_path, server, pause)

    assert error is not None
    assert server.requests() == [AUTH, RANK]
    assert pause.slept == []


def test_the_wait_is_logged_before_it_begins(
    tmp_path: Path, server: FakePortfolio123, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="trialfolio")
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    server.reply("/screen/backtest", response("complete.json"))
    logged_before_sleep: list[list[str]] = []
    pause = FakePause(server)
    pause.on_sleep = lambda: logged_before_sleep.append(
        [str(getattr(record, "event", "")) for record in caplog.records]
    )
    plan = ranked_screen().plan

    error = run_screen(tmp_path, server, pause)

    assert error is None
    (waiting,) = [r for r in caplog.records if getattr(r, "event", None) == WAITING]
    assert waiting.levelno == logging.INFO
    assert waiting.getMessage() == (
        "Waiting 10 seconds after the rank_update before sending the backtest, so Portfolio123"
        " ranks by the definition just written."
    )
    assert getattr(waiting, "case_id", None) == plan.cases[0].case_id
    assert getattr(waiting, "attempt_id", None) == only_attempt(tmp_path / "out").name
    assert getattr(waiting, "plan_hash", None) == plan.plan_hash
    # Logged once the rank_update's exchange ended, and before the wait and the backtest's send.
    (before,) = logged_before_sleep
    assert before[-1] == WAITING
    events = [str(getattr(record, "event", "")) for record in caplog.records]
    sends = [
        index
        for index, record in enumerate(caplog.records)
        if record.getMessage() == f"Sending {BACKTEST}."
    ]
    assert events.index(WAITING) < sends[0]


# An interrupt, and a cancellation, during the wait


def test_an_interrupt_during_the_wait_sends_no_backtest_and_its_case_awaits_a_repeat(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # The attempt stopped after its rank_update's response was saved, and before its backtest's
    # request and start record: failed, possibly charged, with command.interrupted.
    lab = Lab(tmp_path, server)
    script(server, 4, auths=2)
    pause = FakePause(server)

    def interrupt() -> None:
        pause.on_sleep = None
        raise KeyboardInterrupt

    pause.on_sleep = interrupt

    stopped = lab.new(pause=pause.pause).executed

    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    baseline = plan.cases[0].case_id
    assert server.requests() == [AUTH, RANK]
    assert stopped.manifest is None
    attempt = lab.attempt(baseline)
    record = AttemptRecordV1_3.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert "The screen backtest request wasn't sent" in record.error.message
    assert record.exchanges == (exchange(AUTH, 200), exchange(RANK, 200))
    assert (attempt / "rank-update-response.json").exists()
    assert not (attempt / "request.json").exists()
    assert not (attempt / "started.json").exists()

    # The resume doesn't send it again: only a confirmed repeat does.
    resumed = lab.resume(pause=pause.pause).executed

    assert server.requests()[2:] == [AUTH, *(RANK, BACKTEST) * 3]
    assert resumed.repeat_attempts == {baseline: record.attempt_id}
    assert lab.read().cases(plan)[0].state == "awaiting_repeat"


def test_an_attempt_record_lost_after_an_interrupt_during_the_wait_is_recorded_by_the_resume(
    tmp_path: Path, server: FakePortfolio123, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A second interrupt, while the attempt record is written, leaves the update record as the
    # attempt's latest, with the rank_update's response saved: the resume records it failed,
    # with the rank_update's 200 completed from that response (sending a definition).
    lab = Lab(tmp_path, server, monkeypatch)
    script(server, 4, auths=2)
    plan = ranked_experiment(EXPERIMENT_CONFIGS / "ranking-example.yaml").plan
    baseline = plan.cases[0].case_id
    pause = FakePause(server)

    def interrupt() -> None:
        pause.on_sleep = None
        raise KeyboardInterrupt

    pause.on_sleep = interrupt
    # The attempt record is written once more after an interrupt, so both writes are faulted.
    faults: dict[str, Fault] = {
        f"{baseline}/attempt.json": "interrupt",
        "attempt.json": "interrupt",
    }
    stopped = lab.new(pause=pause.pause, arm=lambda store: store.fail_each(faults)).executed
    assert stopped.manifest is None
    attempt = lab.attempt(baseline)
    assert not (attempt / "attempt.json").exists()
    assert (attempt / "rank-update-response.json").exists()

    lab.resume(pause=pause.pause)

    record = AttemptRecordV1_3.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert record.exchanges == (
        exchange(AUTH, 200),
        exchange(RANK, 200, note="completed_from_saved_response"),
    )
    assert server.requests()[2:] == [AUTH, *(RANK, BACKTEST) * 3]


def test_a_cancellation_during_the_wait_still_sends_the_backtest(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # Cancellation is checked only before each attempt, never between its two calls, so a case
    # is never left written and not backtested.
    script(server, 4)
    cancellation = Cancellation()
    pause = FakePause(server, on_sleep=cancellation.cancel)

    execution = Lab(tmp_path, server).new(pause=pause.pause, cancellation=cancellation).executed

    assert server.requests() == [AUTH, RANK, BACKTEST]
    assert [outcome for _, outcome in execution.outcomes] == [
        "succeeded",
        *("not_yet_run",) * 3,
    ]
    assert pause.slept == [Slept(UPDATE_PAUSE_SECONDS, (AUTH, RANK))]
    manifest = execution.manifest
    assert manifest is not None and manifest.outcome == "partial"
    assert manifest.error is not None and "cancelled" in manifest.error.message


def test_a_screen_runs_interrupt_during_the_wait_sends_no_backtest(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    server.reply("/auth", AUTHENTICATED)
    server.reply("/rank", response("rank-update.json"), method="POST")
    pause = FakePause(server)

    def interrupt() -> None:
        raise KeyboardInterrupt

    pause.on_sleep = interrupt

    error = run_screen(tmp_path, server, pause)

    assert error is not None and error.code == "command.interrupted"
    assert "The screen backtest request wasn't sent" in error.message
    assert server.requests() == [AUTH, RANK]
    attempt = only_attempt(tmp_path / "out")
    record = AttemptRecordV1_2.model_validate_json((attempt / "attempt.json").read_bytes())
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert not (attempt / "started.json").exists()
    assert not (tmp_path / "out" / "manifest.json").exists()
