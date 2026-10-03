"""An attempt writes its start record durably before the request is sent, and its attempt record
once, when it ends, never replacing either; a start record alone reads as `running`.

Traces to docs/contracts.md, execution outcomes and attempts (the two records and their field
shapes), HTTP exchanges (possibly charged), uncertain completion, endings that decide the error
code, and interrupts; and to release 0.1.0's failure table. Also, at the core, to R01-AC03 (the
response and provider metadata are saved before anything else, and the record's hashes match the
files), R01-AC06 (a read timeout is `unknown`, sent once), R01-AC07 (one attempt; the exchanges in
order; `provider_requests` is 0 after a failed authentication and a `not_connected` request),
R01-AC25 (the records name the plan hash; `request.json` holds the request's numbers as sent),
R01-AC28 (what each interrupt leaves), and R01-AC29 (a storage failure after a 200 is `unknown`,
and a start record alone reads as `running`). The real client, `requests`, and `urllib3` run over
the fake server; storage faults wrap the real store.
"""

import hashlib
import json
import logging
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.support import canaries
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.socket_faults import SocketFaults
from tests.support.storage_faults import StorageFaults
from trialfolio.attempts import (
    Attempt,
    AttemptResult,
    AttemptStatus,
    attempt_directory,
    read_attempt,
)
from trialfolio.configuration import read_screen_configuration
from trialfolio.contracts.attempt import AttemptRecord, Exchange, StartRecord
from trialfolio.contracts.plan import Plan
from trialfolio.errors import TrialFolioError
from trialfolio.planning import VERIFIED_VERSIONS, Versions, build_plan
from trialfolio.provider import (
    REQUEST_TIMEOUT_SECONDS,
    Credentials,
    DecodedResponse,
    P123ScreenBacktestClient,
    ScreenBacktestResponse,
    UndecodedResponse,
)
from trialfolio.storage import LocalArtifactStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "screen-configs"

AUTH = "POST /auth"
BACKTEST = "POST /screen/backtest"
AUTHENTICATED = Exchange(request=AUTH, result="response", status=200, note=None)

STARTED_AT = datetime(2026, 10, 3, 12, 0, 0, tzinfo=UTC)
ENDED_AT = datetime(2026, 10, 3, 12, 0, 7, tzinfo=UTC)

PAYLOAD = {
    "stats": {"port": {"total_return": 123.4567}, "bench": {"total_return": 98.7}},
    "results": {"columns": ["Tran Dt"], "rows": [["2016-01-04"]]},
    "cost": 5,
    "quotaRemaining": 995,
}
"""A decoded response. Its contents don't matter to recording, only that they're kept."""

PROVIDER_TEXT = "Invalid screen rule near canary-rule-text"
"""Portfolio123's own message for a 400, which logs must leave out."""


def response(request: str, status: int) -> Exchange:
    return Exchange(request=request, result="response", status=status, note=None)


def ended(request: str, result: str) -> Exchange:
    return Exchange.model_validate(
        {"request": request, "result": result, "status": None, "note": None}
    )


def clock() -> Callable[[], datetime]:
    """The start time for the first call, and the end time for every later one."""
    times = iter([STARTED_AT])
    return lambda: next(times, ENDED_AT)


class Interposed:
    """The real client, with an action just before the request's call: the provider client is a
    boundary the tests may stand in at (AGENTS.md, verification expectations)."""

    def __init__(self, client: P123ScreenBacktestClient, action: Callable[[], object]) -> None:
        self._client = client
        self._action = action

    @property
    def authenticated(self) -> bool:
        return self._client.authenticated

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        return self._client.exchanges

    def authenticate(self) -> None:
        self._client.authenticate()

    def screen_backtest(self, params: Mapping[str, object]) -> ScreenBacktestResponse:
        self._action()
        return self._client.screen_backtest(params)

    def close(self) -> None:
        self._client.close()


@pytest.fixture
def plan() -> Plan:
    path = FIXTURES / "formula.yaml"
    versions = Versions(
        trialfolio="0.1.0",
        p123api=VERIFIED_VERSIONS["p123api"][0],
        requests=VERIFIED_VERSIONS["requests"][0],
        urllib3=VERIFIED_VERSIONS["urllib3"][0],
    )
    return build_plan(read_screen_configuration(path.read_bytes(), path.name), versions)


@pytest.fixture
def server() -> Iterator[FakePortfolio123]:
    fake = FakePortfolio123()
    yield fake
    fake.close()


@pytest.fixture
def make_client(server: FakePortfolio123) -> Iterator[Callable[..., P123ScreenBacktestClient]]:
    made: list[P123ScreenBacktestClient] = []

    def make(timeout: int = REQUEST_TIMEOUT_SECONDS) -> P123ScreenBacktestClient:
        client = P123ScreenBacktestClient(
            Credentials(canaries.API_ID, canaries.API_KEY),
            endpoint=server.endpoint,
            timeout=timeout,
        )
        made.append(client)
        return client

    yield make
    for client in made:
        client.close()


@pytest.fixture
def client(make_client: Callable[..., P123ScreenBacktestClient]) -> P123ScreenBacktestClient:
    return make_client()


@pytest.fixture
def out(tmp_path: Path) -> Path:
    return tmp_path / "out"


@pytest.fixture
def store(out: Path, plan: Plan, monkeypatch: pytest.MonkeyPatch) -> StorageFaults:
    """The real store, claimed with `plan.json` as `run` claims it, inside storage faults."""
    faults = StorageFaults(LocalArtifactStore(out), monkeypatch)
    faults.claim("plan.json", plan.model_dump_json(indent=2).encode())
    return faults


@pytest.fixture
def attempt(plan: Plan, store: StorageFaults) -> Attempt:
    return Attempt(plan, plan.plan_hash, store, clock=clock())


def authenticates(server: FakePortfolio123) -> None:
    server.reply("/auth", Reply(200, canaries.TOKEN.encode()))


def answers(server: FakePortfolio123, reply: Reply) -> None:
    authenticates(server)
    server.reply("/screen/backtest", reply)


def files(out: Path, attempt: Attempt) -> set[str]:
    directory = out / attempt.directory
    return {path.name for path in directory.iterdir()} if directory.exists() else set()


def saved_record(out: Path, attempt: Attempt) -> AttemptRecord:
    content = (out / attempt.directory / "attempt.json").read_bytes()
    return AttemptRecord.model_validate_json(content)


def status(out: Path, attempt: Attempt) -> AttemptStatus | None:
    return read_attempt(LocalArtifactStore(out), attempt.case_id, attempt.attempt_id)


def check_recorded(out: Path, attempt: Attempt, result: AttemptResult) -> AttemptRecord:
    """The record was written once, as the result gives it, and it reads as it says."""
    record = saved_record(out, attempt)
    assert record == result.record
    assert result.recorded
    assert status(out, attempt) == AttemptStatus(
        attempt_id=attempt.attempt_id,
        outcome=record.outcome,
        possibly_charged=record.possibly_charged,
        provider_requests=1 if record.possibly_charged else 0,
    )
    return record


# Success


def test_a_success_writes_the_start_record_before_sending_and_the_attempt_record_after(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    plan: Plan,
    out: Path,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    directory = out / attempt.directory
    started_when_sent: list[bool] = []

    result = attempt.run(
        Interposed(client, lambda: started_when_sent.append((directory / "started.json").exists()))
    )

    # The start record was durable before the request was sent, and nothing was written twice.
    assert started_when_sent == [True]
    prefix = attempt.directory + "/"
    assert store.published == [
        "plan.json",
        *(prefix + name for name in ("request.json", "started.json", "response.json")),
        prefix + "attempt.json",
    ]
    assert [f.role for f in result.files] == [
        "provider_request",
        "start_record",
        "provider_response",
        "attempt_record",
    ]
    start = StartRecord.model_validate_json((directory / "started.json").read_bytes())
    assert start.exchanges == (AUTHENTICATED,)
    assert start.plan_hash == plan.plan_hash
    assert start.case_id == plan.cases[0].case_id
    assert start.started_at == STARTED_AT
    assert start.provider_wrapper == plan.provider_wrapper
    assert start.transport == plan.transport

    record = check_recorded(out, attempt, result)
    assert record.outcome == "succeeded"
    assert record.error is None
    assert result.error is None
    assert record.exchanges == (AUTHENTICATED, response(BACKTEST, 200))
    assert record.possibly_charged
    assert record.ended_at == ENDED_AT
    # Everything the start record holds, the attempt record holds too.
    assert (
        record.model_dump(exclude={"exchanges"}).items()
        >= start.model_dump(exclude={"exchanges"}).items()
    )
    assert record.provider_metadata.cost == 5
    assert record.provider_metadata.quota_remaining == 995

    # The references name the files by their hashes.
    for reference in (record.request, record.response):
        assert reference is not None
        content = (out / reference.path).read_bytes()
        assert reference.artifact_id == "sha256:" + hashlib.sha256(content).hexdigest()
    assert record.response is not None
    assert record.response.form == "decoded"

    # The response decodes to what was served, and the request to what was sent, number for
    # number: the slippage's text is the body's.
    assert json.loads((directory / "response.json").read_bytes()) == PAYLOAD
    assert result.response == DecodedResponse(PAYLOAD)
    sent = server.received[1].body
    saved_request = (directory / "request.json").read_bytes()
    assert json.loads(saved_request) == json.loads(sent)
    assert b'"slippage": 0.25' in sent
    assert b'"slippage": 0.25' in saved_request
    assert server.requests() == [AUTH, BACKTEST]


def test_an_undecodable_200_is_saved_raw_and_succeeds_for_capture(
    server: FakePortfolio123, client: P123ScreenBacktestClient, attempt: Attempt, out: Path
) -> None:
    answers(server, Reply(200, b"Not JSON <html>"))

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.outcome == "succeeded"
    assert record.response is not None
    assert record.response.form == "undecoded"
    assert (out / record.response.path).read_bytes() == b"Not JSON <html>"
    assert files(out, attempt) == {"request.json", "started.json", "response.raw", "attempt.json"}
    assert result.response == UndecodedResponse(b"Not JSON <html>")
    assert record.provider_metadata.cost is None
    assert record.provider_metadata.quota_remaining is None


# Authentication and the request: each ending gives its outcome, code, and possibly charged


def test_failed_authentication_leaves_only_a_failed_attempt_record(
    server: FakePortfolio123, client: P123ScreenBacktestClient, attempt: Attempt, out: Path
) -> None:
    server.reply("/auth", Reply(401))

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert files(out, attempt) == {"attempt.json"}
    assert record.exchanges == (response(AUTH, 401),)
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert record.error is not None
    assert record.error.code == "provider.auth_failed"
    assert result.error is not None
    assert result.error.code == "provider.auth_failed"
    assert record.request is None
    assert server.requests() == [AUTH]


@pytest.mark.parametrize(
    ("reply", "outcome", "code"),
    [
        pytest.param(
            Reply(400, PROVIDER_TEXT.encode()),
            "failed",
            "provider.unsupported_capability",
            id="400",
        ),
        pytest.param(Reply(402), "failed", "provider.quota_exceeded", id="402"),
        pytest.param(Reply(404), "failed", "provider.request_rejected", id="404"),
        pytest.param(Reply(503), "unknown", "provider.outcome_unknown", id="503"),
        pytest.param(Reply(action="reset"), "unknown", "provider.outcome_unknown", id="reset"),
    ],
)
def test_a_request_that_reached_portfolio123_is_possibly_charged(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    attempt: Attempt,
    out: Path,
    reply: Reply,
    outcome: str,
    code: str,
) -> None:
    answers(server, reply)

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.outcome == outcome
    assert record.possibly_charged
    assert record.error is not None
    assert record.error.code == code
    assert record.response is None
    assert record.request is not None
    assert files(out, attempt) == {"request.json", "started.json", "attempt.json"}
    assert server.requests() == [AUTH, BACKTEST]
    if reply.status == 400:
        # The terminal and the record keep Portfolio123's own message.
        assert PROVIDER_TEXT in record.error.message


def test_a_read_timeout_is_unknown_and_sent_once(
    server: FakePortfolio123,
    make_client: Callable[..., P123ScreenBacktestClient],
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(200, b"{}", delay=3))

    result = attempt.run(make_client(timeout=1))

    record = check_recorded(out, attempt, result)
    assert record.exchanges == (AUTHENTICATED, ended(BACKTEST, "interrupted"))
    assert record.outcome == "unknown"
    assert record.possibly_charged
    assert record.error is not None
    assert record.error.code == "provider.outcome_unknown"
    assert server.requests() == [AUTH, BACKTEST]


def test_a_request_that_never_connected_is_failed_and_not_charged(
    server: FakePortfolio123, client: P123ScreenBacktestClient, attempt: Attempt, out: Path
) -> None:
    authenticates(server)

    result = attempt.run(Interposed(client, server.close))

    record = check_recorded(out, attempt, result)
    assert record.exchanges == (AUTHENTICATED, ended(BACKTEST, "not_connected"))
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert record.error is not None
    assert record.error.code == "provider.unavailable"
    # A request exchange references its saved request, though nothing was sent.
    assert record.request is not None


# Storage failures decide the code; the exchanges decide the outcome


def test_a_storage_failure_after_a_200_is_unknown_and_possibly_charged(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    store.fail_os("response.json")

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.outcome == "unknown"
    assert record.possibly_charged
    assert record.response is None
    assert record.error is not None
    assert record.error.code == "storage.write_failed"
    assert "may have been charged" in record.error.message
    assert result.error is not None
    assert result.error.code == "storage.write_failed"
    assert result.response is None
    assert files(out, attempt) == {"request.json", "started.json", "attempt.json"}


def test_without_its_attempt_record_a_start_record_reads_as_running(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    store.fail_os("response.json")
    store.fail_os("attempt.json")

    result = attempt.run(client)

    assert not result.recorded
    assert result.record.outcome == "unknown"
    assert result.error is not None
    assert result.error.code == "storage.write_failed"
    assert files(out, attempt) == {"request.json", "started.json"}
    assert status(out, attempt) == AttemptStatus(
        attempt_id=attempt.attempt_id, outcome="running", possibly_charged=True, provider_requests=1
    )


def test_a_storage_failure_at_the_start_record_sends_nothing(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    store.fail_os("started.json")

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.exchanges == (AUTHENTICATED,)
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert record.error is not None
    assert record.error.code == "storage.write_failed"
    assert "wasn't sent" in record.error.message
    assert server.requests() == [AUTH]


# Interrupts, at each stage: the code is command.interrupted, and the exchanges give the outcome


def test_an_interrupt_before_authenticating_records_a_failed_attempt(
    server: FakePortfolio123, store: StorageFaults, attempt: Attempt, out: Path
) -> None:
    result = attempt.end_before_authenticating(KeyboardInterrupt())

    record = check_recorded(out, attempt, result)
    assert record.exchanges == ()
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    assert "wasn't sent" in record.error.message
    assert files(out, attempt) == {"attempt.json"}
    assert server.requests() == []


def test_ctrl_c_during_authentication_records_a_failed_attempt(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    attempt: Attempt,
    out: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    SocketFaults(monkeypatch).interrupt_send()

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.exchanges == (ended(AUTH, "interrupted"),)
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    assert files(out, attempt) == {"attempt.json"}


def test_an_interrupt_while_the_start_record_is_written_sends_nothing(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    store.fail_before("started.json", KeyboardInterrupt())

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    assert "started.json" not in files(out, attempt)
    assert server.requests() == [AUTH]


def test_ctrl_c_during_the_request_is_unknown_and_possibly_charged(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    attempt: Attempt,
    out: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    faults = SocketFaults(monkeypatch)

    result = attempt.run(Interposed(client, faults.interrupt_send))

    record = check_recorded(out, attempt, result)
    assert record.exchanges == (AUTHENTICATED, ended(BACKTEST, "interrupted"))
    assert record.outcome == "unknown"
    assert record.possibly_charged
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    assert "may have been charged" in record.error.message


def test_an_interrupt_while_the_response_is_saved_is_unknown(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    store.fail_before("response.json", KeyboardInterrupt())

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.exchanges == (AUTHENTICATED, response(BACKTEST, 200))
    assert record.outcome == "unknown"
    assert record.possibly_charged
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    assert result.response is None


def test_an_interrupt_after_a_400_before_the_attempt_record_still_writes_it_once(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(400, PROVIDER_TEXT.encode()))
    store.fail_before("attempt.json", KeyboardInterrupt())

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.outcome == "failed"
    assert record.possibly_charged
    assert record.error is not None
    assert record.error.code == "command.interrupted"
    # The interrupt decided the code, and the message keeps Portfolio123's.
    assert PROVIDER_TEXT in record.error.message
    assert store.published.count(f"{attempt.directory}/attempt.json") == 1


def test_an_interrupt_after_the_attempt_record_leaves_it_unchanged(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(400, PROVIDER_TEXT.encode()))
    store.fail_after("attempt.json", KeyboardInterrupt())

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.error is not None
    assert record.error.code == "provider.unsupported_capability"
    assert result.error is not None
    assert result.error.code == "command.interrupted"
    assert store.published.count(f"{attempt.directory}/attempt.json") == 1
    assert [f.role for f in result.files].count("attempt_record") == 1


def test_an_interrupt_after_a_saved_response_keeps_the_success(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    store.fail_before("attempt.json", KeyboardInterrupt())

    result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.outcome == "succeeded"
    assert record.error is None
    assert result.error is not None
    assert result.error.code == "command.interrupted"
    assert "its response was saved" in result.error.message
    assert result.response == DecodedResponse(PAYLOAD)


# Other endings


def test_an_unexpected_error_after_a_200_is_an_unknown_outcome(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    attempt: Attempt,
    out: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    answers(server, Reply(200, json.dumps(PAYLOAD).encode()))
    store.fail_before("response.json", RuntimeError("canary-exception-text"))

    with caplog.at_level(logging.DEBUG):
        result = attempt.run(client)

    record = check_recorded(out, attempt, result)
    assert record.outcome == "unknown"
    assert record.possibly_charged
    assert record.error is not None
    assert record.error.code == "provider.outcome_unknown"
    assert "RuntimeError" in record.error.message
    # Neither the record nor the logs repeat the exception's message, which could hold a value.
    assert "canary-exception-text" not in record.error.message
    assert "canary-exception-text" not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize(
    ("ending", "code"),
    [
        pytest.param(RuntimeError(), "internal.unexpected", id="unexpected"),
        pytest.param(
            TrialFolioError("storage.write_failed", "Couldn't write configuration.yaml durably."),
            "storage.write_failed",
            id="storage",
        ),
    ],
)
def test_an_ending_before_authenticating_is_failed_with_its_code(
    attempt: Attempt, out: Path, ending: BaseException, code: str
) -> None:
    result = attempt.end_before_authenticating(ending)

    record = check_recorded(out, attempt, result)
    assert record.outcome == "failed"
    assert not record.possibly_charged
    assert record.error is not None
    assert record.error.code == code
    assert "wasn't sent" in record.error.message


def test_an_attempt_needs_the_plans_hash_and_ends_once(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    plan: Plan,
    out: Path,
) -> None:
    with pytest.raises(TrialFolioError) as raised:
        Attempt(plan, "sha256:" + "0" * 64, store, clock=clock())
    assert raised.value.code == "plan.approval_required"
    assert store.published == ["plan.json"]

    attempt = Attempt(plan, plan.plan_hash, store, clock=clock())
    attempt.end_before_authenticating(KeyboardInterrupt())
    with pytest.raises(RuntimeError):
        attempt.run(client)
    assert server.requests() == []


# Reading a saved attempt


def test_an_attempt_without_records_reads_as_none_and_a_foreign_record_is_refused(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    plan: Plan,
    attempt: Attempt,
    out: Path,
) -> None:
    assert status(out, attempt) is None

    other = Attempt(plan, plan.plan_hash, store, clock=clock())
    other.end_before_authenticating(KeyboardInterrupt())
    foreign = out / other.directory / "attempt.json"
    target = out / attempt_directory(attempt.case_id, attempt.attempt_id) / "attempt.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(foreign.read_bytes())

    with pytest.raises(ValueError, match="another attempt"):
        status(out, attempt)


# Logs


def test_logs_name_the_attempt_and_hold_no_credential_or_content(
    server: FakePortfolio123,
    client: P123ScreenBacktestClient,
    store: StorageFaults,
    plan: Plan,
    caplog: pytest.LogCaptureFixture,
) -> None:
    answers(server, Reply(400, PROVIDER_TEXT.encode()))

    with caplog.at_level(logging.DEBUG):
        attempt = Attempt(plan, plan.plan_hash, store, clock=clock())
        attempt.run(client)

    events = {getattr(r, "event", None): r for r in caplog.records}
    for name in ("attempt.started", "attempt.completed"):
        logged = events[name]
        assert getattr(logged, "attempt_id", None) == str(attempt.attempt_id)
        assert getattr(logged, "plan_hash", None) == attempt.plan_hash
        assert getattr(logged, "case_id", None) == attempt.case_id
    assert "provider.unsupported_capability" in events["attempt.completed"].getMessage()
    for secret in (canaries.API_ID, canaries.API_KEY, canaries.TOKEN, PROVIDER_TEXT, "EarnYield"):
        assert secret not in caplog.text
