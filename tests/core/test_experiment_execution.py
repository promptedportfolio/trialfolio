"""The executor runs a new experiment's cases in the plan's order, one attempt each, with one
authentication, and records each attempt, each succeeded case's tables, and the session's report
and manifest.

Traces to docs/contracts.md, running an experiment (a new experiment), experiment output,
experiment attempts, an experiment's normalized tables, the budget across runs (authenticating
once, and D-32's stop), the experiment manifest (the counts, and a synthetic experiment), and
the lock; and, at the core, to R03-AC01 (each case's request is sent as the plan gives it),
R03-AC02 (attempt IDs are distinct version 4 UUIDs), R03-AC05 (a failed case is recorded, later
cases still run, and after Trial Folio's own authentication call fails, or after
`provider.quota_exceeded`, no later case starts), R03-AC08 (the counts add up), R03-AC09 (the
lock is held while the experiment runs), R03-AC18 (each succeeded case's tables, labeled with
its `case_id`, with `original_key` and `original_value` from its plan's configuration), and
R03-AC19 (a storage failure or an interrupt ends the session without its manifest, and replaces
no record). The real client, `requests`, and `urllib3` run over the fake server; storage faults
wrap the real store; the clock is fixed.

R03-AC10's core check needs attempts an earlier session made: in a new experiment, whose budget
is at least the number of cases, each case's one attempt makes at most one request and one
authentication call, so the budget always covers it. R03-T09, which writes resume, writes it.
"""

import json
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.support import canaries
from tests.support.clock import FixedClock
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.storage_faults import StorageFaults
from trialfolio.configuration import read_experiment_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_1, AuthenticationRecord, StartRecordV1_1
from trialfolio.contracts.experiment_manifest import ExperimentManifest
from trialfolio.contracts.experiment_plan import PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord, SessionRecord
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution import (
    LOCK_PATH,
    AttemptStarted,
    ExperimentExecution,
    ProgressEvent,
)
from trialfolio.planning import build_experiment_plan, installed_versions
from trialfolio.provider import Credentials, P123ScreenBacktestClient
from trialfolio.storage import ArtifactStore, LocalArtifactStore
from trialfolio.tables import read_metrics_csv, read_settings_csv

CONFIGS = Path(__file__).resolve().parents[1] / "fixtures" / "experiment-configs"
RESPONSES = Path(__file__).resolve().parents[1] / "fixtures" / "responses"

AUTH = "POST /auth"
SEND = "POST /screen/backtest"
AUTHENTICATED = Reply(200, canaries.TOKEN.encode())


def complete() -> Reply:
    return Reply(200, (RESPONSES / "complete.json").read_bytes())


def plan_of(name: str) -> tuple[bytes, PlanV1_1]:
    content = (CONFIGS / name).read_bytes()
    configuration = read_experiment_configuration(content, name)
    return content, build_experiment_plan(configuration, installed_versions())


@dataclass(frozen=True)
class Executed:
    """An experiment the executor wrote, and what it saw."""

    out: Path
    plan: PlanV1_1
    error: TrialFolioError | None
    execution: ExperimentExecution
    received: tuple[str, ...]
    bodies: tuple[dict[str, object], ...]
    """The body of each request the fake server received for a case, in order."""
    events: tuple[ProgressEvent, ...]

    def json(self, path: str) -> dict[str, object]:
        return json.loads((self.out / path).read_bytes())

    @property
    def manifest(self) -> ExperimentManifest:
        return ExperimentManifest.model_validate_json(
            (self.out / "sessions/1/manifest.json").read_bytes()
        )

    def attempts(self, case_id: str) -> list[Path]:
        return sorted((self.out / "cases" / case_id / "attempts").iterdir())

    def record(self, case_id: str) -> AttemptRecordV1_1:
        (attempt,) = self.attempts(case_id)
        return AttemptRecordV1_1.model_validate_json((attempt / "attempt.json").read_bytes())


type Faulted = Callable[[LocalArtifactStore], ArtifactStore]
"""Wraps the output directory's real store, such as in storage faults."""


class Experiments:
    """Runs experiments into new output directories, over one fake server."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.server = FakePortfolio123()
        self._outputs = 0

    def run(
        self,
        name: str = "example.yaml",
        *,
        faults: Faulted | None = None,
        progress: list[ProgressEvent] | None = None,
    ) -> Executed:
        content, plan = plan_of(name)
        self._outputs += 1
        out = self.tmp / f"out-{self._outputs}"
        real = LocalArtifactStore(out)
        store: ArtifactStore = real if faults is None else faults(real)
        events: list[ProgressEvent] = [] if progress is None else progress
        before = len(self.server.received)
        credentials = Credentials(canaries.API_ID, canaries.API_KEY)
        with P123ScreenBacktestClient(credentials, endpoint=self.server.endpoint) as client:
            execution = ExperimentExecution(
                plan,
                plan.plan_hash,
                "option",
                store,
                client,
                command=None,
                clock=FixedClock(),
                progress=events.append,
            )
            try:
                error = execution.run(content)
            finally:
                real.close()
        received = self.server.received[before:]
        return Executed(
            out=out,
            plan=plan,
            error=error,
            execution=execution,
            received=tuple(f"{r.method} {r.path}" for r in received),
            bodies=tuple(json.loads(r.body) for r in received if r.path == "/screen/backtest"),
            events=tuple(events),
        )


@pytest.fixture
def experiments(tmp_path: Path) -> Iterator[Experiments]:
    runner = Experiments(tmp_path)
    yield runner
    runner.server.close()


def ids(plan: PlanV1_1) -> list[str]:
    return [case.case_id for case in plan.cases]


def outcomes(executed: Executed) -> list[str]:
    return [outcome for _, outcome in executed.execution.outcomes]


# A new experiment


def test_every_case_is_sent_once_in_the_plans_order_after_one_authentication(
    experiments: Experiments,
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", *(complete() for _ in range(5)))

    executed = experiments.run()

    assert executed.error is None
    assert executed.received == (AUTH, SEND, SEND, SEND, SEND, SEND)
    plan = executed.plan
    assert list(executed.bodies) == [
        case.requests[0].params.model_dump(mode="json") for case in plan.cases
    ]
    assert outcomes(executed) == ["succeeded"] * 5
    records = [executed.record(case_id) for case_id in ids(plan)]
    first = records[0].attempt_id
    assert [(r.session, r.sequence) for r in records] == [(1, n) for n in range(1, 6)]
    assert all(r.authenticated_by == first for r in records)
    assert all(r.plan_hash == plan.plan_hash and r.repeat_of is None for r in records)
    assert [len(r.exchanges) for r in records] == [2, 1, 1, 1, 1]
    attempt_ids = [r.attempt_id for r in records]
    assert len(set(attempt_ids)) == 5
    assert all(a.version == 4 and str(a) == str(uuid.UUID(str(a))) for a in attempt_ids)


def test_only_the_attempt_that_authenticates_has_an_authentication_record(
    experiments: Experiments,
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", complete(), complete())

    executed = experiments.run("default-only.yaml")

    first, second = (executed.attempts(case_id)[0] for case_id in ids(executed.plan))
    authentication = AuthenticationRecord.model_validate_json(
        (first / "authenticating.json").read_bytes()
    )
    start = StartRecordV1_1.model_validate_json((first / "started.json").read_bytes())
    assert (authentication.attempt_id, authentication.session, authentication.sequence) == (
        start.attempt_id,
        1,
        1,
    )
    assert authentication.started_at == start.started_at
    assert [e.request for e in start.exchanges] == [AUTH]
    assert not (second / "authenticating.json").exists()
    later = StartRecordV1_1.model_validate_json((second / "started.json").read_bytes())
    assert later.exchanges == () and later.authenticated_by == start.attempt_id


def test_the_records_are_written_in_order_and_none_twice(
    experiments: Experiments, monkeypatch: pytest.MonkeyPatch
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", complete(), complete())
    wrapped: list[StorageFaults] = []

    def faults(store: LocalArtifactStore) -> StorageFaults:
        wrapped.append(StorageFaults(store, monkeypatch))
        return wrapped[0]

    executed = experiments.run("default-only.yaml", faults=faults)

    baseline, default = (f"cases/{case_id}" for case_id in ids(executed.plan))
    first = executed.attempts(ids(executed.plan)[0])[0].name
    second = executed.attempts(ids(executed.plan)[1])[0].name
    assert wrapped[0].published == [
        LOCK_PATH,
        "sessions/1/session.json",
        "plans/1/configuration.yaml",
        "plans/1/plan.json",
        "plans/1/experiment.json",
        *(
            f"{baseline}/attempts/{first}/{name}"
            for name in (
                "authenticating.json",
                "request.json",
                "started.json",
                "response.json",
                "attempt.json",
            )
        ),
        f"{baseline}/normalized/metrics.csv",
        f"{baseline}/normalized/settings.csv",
        *(
            f"{default}/attempts/{second}/{name}"
            for name in ("request.json", "started.json", "response.json", "attempt.json")
        ),
        f"{default}/normalized/metrics.csv",
        f"{default}/normalized/settings.csv",
        "sessions/1/report.html",
        "sessions/1/manifest.json",
    ]


def test_the_session_and_plan_records_and_the_manifest_account_for_every_file(
    experiments: Experiments,
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", *(complete() for _ in range(5)))

    executed = experiments.run()

    plan = executed.plan
    assert (executed.out / "plans/1/configuration.yaml").read_bytes() == (
        CONFIGS / "example.yaml"
    ).read_bytes()
    assert PlanV1_1.model_validate_json((executed.out / "plans/1/plan.json").read_bytes()) == plan
    record = ExperimentRecord.model_validate_json(
        (executed.out / "plans/1/experiment.json").read_bytes()
    )
    assert [case.case_id for case in record.planned_cases] == ids(plan)
    assert record.plans[0].approval == "option" and record.plans[0].revises is None
    session = SessionRecord.model_validate_json(
        (executed.out / "sessions/1/session.json").read_bytes()
    )
    assert session.session == 1
    manifest = executed.manifest
    assert (manifest.outcome, manifest.error, manifest.synthetic, manifest.command) == (
        "completed",
        None,
        False,
        None,
    )
    assert (manifest.plan, manifest.plan_hash, manifest.approval) == (1, plan.plan_hash, "option")
    listed = {artifact.path for artifact in manifest.artifacts}
    on_disk = {
        path.relative_to(executed.out).as_posix()
        for path in executed.out.rglob("*")
        if path.is_file()
    }
    assert on_disk - listed == {LOCK_PATH, "sessions/1/manifest.json"}
    counts = manifest.counts
    assert counts.cases.model_dump() == {
        "planned": 5,
        "succeeded": 5,
        "failed": 0,
        "skipped": 0,
        "unknown": 0,
        "not_yet_run": 0,
    }
    assert (counts.provider_requests, counts.authentication_calls) == (5, 1)
    assert (counts.budget.provider_requests, counts.budget.authentication_calls) == (6, 6)
    assert counts.attempts.succeeded == 5 and counts.attempts.repeats == 0
    assert counts.retired_cases == 0


# Cases that fail


@pytest.mark.parametrize(
    ("reply", "outcome", "code"),
    [
        (Reply(400, b'{"message": "bad setting"}'), "failed", "provider.unsupported_capability"),
        (Reply(404), "failed", "provider.request_rejected"),
        (Reply(503), "unknown", "provider.outcome_unknown"),
    ],
)
def test_a_failed_case_is_recorded_and_the_later_cases_still_run(
    experiments: Experiments, reply: Reply, outcome: str, code: str
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply(
        "/screen/backtest", complete(), complete(), reply, complete(), complete()
    )

    executed = experiments.run()

    assert executed.received == (AUTH, SEND, SEND, SEND, SEND, SEND)
    assert outcomes(executed) == ["succeeded", "succeeded", outcome, "succeeded", "succeeded"]
    holdings = executed.plan.cases[2]
    record = executed.record(holdings.case_id)
    assert (record.outcome, record.possibly_charged) == (outcome, True)
    assert record.error is not None and record.error.code == code
    error = executed.error
    assert error is not None and error.code == "execution.partial"
    assert f"`{holdings.case_key}`, {outcome} ({code})" in error.message
    assert "a confirmed repeat sends it" in error.message
    assert holdings.case_key not in error.log_message
    assert holdings.case_id in error.log_message
    manifest = executed.manifest
    assert manifest.outcome == "partial"
    assert manifest.error is not None and manifest.error.code == "execution.partial"
    assert not (executed.out / "cases" / holdings.case_id / "normalized").exists()


def test_after_a_403_the_next_case_authenticates_again(experiments: Experiments) -> None:
    experiments.server.reply("/auth", AUTHENTICATED, AUTHENTICATED)
    experiments.server.reply(
        "/screen/backtest", complete(), Reply(403), complete(), complete(), complete()
    )

    executed = experiments.run()

    assert executed.received == (AUTH, SEND, SEND, AUTH, SEND, SEND, SEND)
    records = [executed.record(case_id) for case_id in ids(executed.plan)]
    assert records[1].error is not None and records[1].error.code == "provider.auth_failed"
    third = records[2]
    assert third.authenticated_by == third.attempt_id
    assert [e.request for e in third.exchanges] == [AUTH, SEND]
    assert records[3].authenticated_by == records[4].authenticated_by == third.attempt_id
    assert executed.manifest.counts.authentication_calls == 2


@pytest.mark.parametrize(
    ("authentication", "backtest", "sent", "stopped_at", "code"),
    [
        ([Reply(401)], [], (AUTH,), 0, "provider.auth_failed"),
        ([Reply(503)], [], (AUTH,), 0, "provider.unavailable"),
        (
            [AUTHENTICATED],
            [complete(), Reply(402)],
            (AUTH, SEND, SEND),
            1,
            "provider.quota_exceeded",
        ),
        (
            [AUTHENTICATED, Reply(401)],
            [complete(), Reply(403)],
            (AUTH, SEND, SEND, AUTH),
            2,
            "provider.auth_failed",
        ),
    ],
    ids=["authentication-401", "authentication-503", "quota-402", "authentication-after-403"],
)
def test_after_a_failure_every_later_case_would_get_no_later_case_starts(
    experiments: Experiments,
    authentication: Sequence[Reply],
    backtest: Sequence[Reply],
    sent: tuple[str, ...],
    stopped_at: int,
    code: str,
) -> None:
    experiments.server.reply("/auth", *authentication)
    experiments.server.reply("/screen/backtest", *backtest)

    executed = experiments.run()

    assert executed.received == sent
    plan = executed.plan
    stopped = executed.record(plan.cases[stopped_at].case_id)
    assert stopped.error is not None and stopped.error.code == code
    later = outcomes(executed)[stopped_at + 1 :]
    assert later == ["not_yet_run"] * len(later)
    assert all(
        not (executed.out / "cases" / case.case_id).exists()
        for case in plan.cases[stopped_at + 1 :]
    )
    error = executed.error
    assert error is not None and error.code == "execution.partial"
    assert f"The error was {code}." in error.message
    assert "resumes the experiment, and runs the cases not started" in error.message
    assert executed.manifest.counts.cases.not_yet_run == len(later)


def test_a_failed_authentication_is_counted_and_sends_nothing(experiments: Experiments) -> None:
    experiments.server.reply("/auth", Reply(401))

    executed = experiments.run("default-only.yaml")

    baseline = executed.plan.cases[0]
    (attempt,) = executed.attempts(baseline.case_id)
    assert (attempt / "authenticating.json").exists()
    assert not (attempt / "started.json").exists()
    record = executed.record(baseline.case_id)
    assert (record.outcome, record.possibly_charged, record.authenticated_by) == (
        "failed",
        False,
        None,
    )
    assert outcomes(executed) == ["failed", "not_yet_run"]
    counts = executed.manifest.counts
    assert (counts.provider_requests, counts.authentication_calls) == (0, 1)


def test_a_response_that_fails_validation_leaves_its_case_failed_without_tables(
    experiments: Experiments,
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    invalid = Reply(200, (RESPONSES / "invalid-structure.json").read_bytes())
    experiments.server.reply("/screen/backtest", complete(), invalid)

    executed = experiments.run("default-only.yaml")

    _, default = executed.plan.cases
    assert executed.record(default.case_id).outcome == "succeeded"
    assert outcomes(executed) == ["succeeded", "failed"]
    assert not (executed.out / "cases" / default.case_id / "normalized").exists()
    error = executed.error
    assert error is not None
    assert f"`{default.case_key}`, failed (provider.response_invalid)" in error.message
    assert "a confirmed repeat sends it" not in error.message
    assert executed.manifest.counts.attempts.succeeded == 2


# Each case's tables


def test_each_succeeded_case_has_its_tables_with_its_plans_original_values(
    experiments: Experiments,
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", *(complete() for _ in range(5)))

    executed = experiments.run()

    manifest = executed.manifest
    by_path = {artifact.path: artifact.artifact_id for artifact in manifest.artifacts}
    configuration = by_path["plans/1/configuration.yaml"]
    expected = {
        "baseline": ("baseline.max_holdings", "25"),
        "liquidity-100m": ("baseline.max_holdings", "25"),
        "holdings-50": ("variants.max_holdings[0].value", "50"),
        "rebalance-weeks-1": ("baseline.max_holdings", "25"),
        "slippage-050": ("baseline.max_holdings", "25"),
    }
    for case in executed.plan.cases:
        directory = f"cases/{case.case_id}/normalized"
        metrics = read_metrics_csv((executed.out / directory / "metrics.csv").read_bytes(), "m")
        settings = read_settings_csv((executed.out / directory / "settings.csv").read_bytes(), "s")
        assert {row.label for row in metrics} | {row.label for row in settings} == {case.case_id}
        rows = {row.setting: row for row in settings}
        holdings = rows["max_holdings"]
        assert (holdings.original_key, holdings.original_value) == expected[case.case_key]
        assert {row.source_artifact for row in settings} == {configuration}
        (response,) = (
            path
            for path in by_path
            if path.startswith(f"cases/{case.case_id}/") and path.endswith("response.json")
        )
        assert {row.source_artifact for row in metrics} == {by_path[response]}
    default = executed.plan.cases[3]
    rows = read_settings_csv(
        (executed.out / f"cases/{default.case_id}/normalized/settings.csv").read_bytes(), "s"
    )
    weeks = next(row for row in rows if row.setting == "rebalance_weeks")
    assert (weeks.value, weeks.original_key, weeks.original_value) == ("1", None, None)
    liquidity = executed.plan.cases[1]
    rows = read_settings_csv(
        (executed.out / f"cases/{liquidity.case_id}/normalized/settings.csv").read_bytes(), "s"
    )
    rules = next(row for row in rows if row.setting == "rules")
    assert (rules.original_key, rules.original_value) == (
        "variants.rules[0].with",
        "'AvgDailyTot(30) > 100000000'",
    )


# The synthetic experiment


def test_the_demos_client_writes_a_synthetic_experiment_that_sends_nothing(
    tmp_path: Path,
) -> None:
    content, plan = plan_of("default-only.yaml")
    client = SyntheticScreenBacktestClient(response_bytes())
    out = tmp_path / "out"
    with LocalArtifactStore(out) as store:
        error = ExperimentExecution(
            plan, plan.plan_hash, "not_required", store, client, command=None, clock=FixedClock()
        ).run(content)

    assert error is None
    assert [e.request for e in client.exchanges] == [AUTH, SEND, SEND]
    manifest = ExperimentManifest.model_validate_json(
        (out / "sessions/1/manifest.json").read_bytes()
    )
    assert (manifest.synthetic, manifest.approval, manifest.command) == (True, "not_required", None)
    record = ExperimentRecord.model_validate_json((out / "plans/1/experiment.json").read_bytes())
    assert record.plans[0].approval == "not_required"
    report = (out / "sessions/1/report.html").read_text(encoding="utf-8")
    assert "Synthetic experiment." in report
    assert "Every value, attempt, and count in it is invented" in report
    assert manifest.counts.cases.succeeded == 2


def test_the_demos_client_needs_no_approval_and_nothing_else_does(tmp_path: Path) -> None:
    _, plan = plan_of("default-only.yaml")
    synthetic = SyntheticScreenBacktestClient(response_bytes())
    store = LocalArtifactStore(tmp_path / "out")
    with pytest.raises(ValueError, match="needs no approval"):
        ExperimentExecution(plan, plan.plan_hash, "option", store, synthetic, command=None)
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    with (
        P123ScreenBacktestClient(credentials, endpoint="http://127.0.0.1:9") as real,
        pytest.raises(ValueError, match="needs no approval"),
    ):
        ExperimentExecution(plan, plan.plan_hash, "not_required", store, real, command=None)
    assert not (tmp_path / "out").exists()


# Before anything is sent


def test_execution_needs_the_plans_own_hash_and_writes_nothing_without_it(
    experiments: Experiments,
) -> None:
    content, plan = plan_of("example.yaml")
    other_content, other = plan_of("default-only.yaml")
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    store = LocalArtifactStore(experiments.tmp / "out")
    with P123ScreenBacktestClient(credentials, endpoint=experiments.server.endpoint) as client:
        with pytest.raises(TrialFolioError) as raised:
            ExperimentExecution(plan, other.plan_hash, "option", store, client, command=None)
        assert raised.value.code == "plan.approval_required"
        execution = ExperimentExecution(plan, plan.plan_hash, "option", store, client, command=None)
        with pytest.raises(ValueError, match="doesn't give the plan"):
            execution.run(other_content)

    assert not (experiments.tmp / "out").exists()
    assert experiments.server.received == ()
    assert content != other_content


def test_a_directory_that_isnt_empty_is_refused_before_anything_is_sent(
    experiments: Experiments,
) -> None:
    out = experiments.tmp / "out-1"
    out.mkdir()
    (out / "notes.txt").write_bytes(b"kept\n")

    with pytest.raises(TrialFolioError) as raised:
        experiments.run()

    assert raised.value.code == "output.not_empty"
    assert sorted(path.name for path in out.iterdir()) == ["notes.txt"]
    assert experiments.server.received == ()


# The lock


def test_the_lock_is_held_while_the_experiment_runs(experiments: Experiments) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", complete(), complete())
    found: list[str] = []

    class Watching(list[ProgressEvent]):
        def append(self, event: ProgressEvent) -> None:
            super().append(event)
            if isinstance(event, AttemptStarted):
                other = LocalArtifactStore(experiments.tmp / "out-1")
                try:
                    other.lock(LOCK_PATH)
                    found.append("acquired")
                    other.close()
                except TrialFolioError as error:
                    found.append(error.code)

    executed = experiments.run("default-only.yaml", progress=Watching())

    assert executed.error is None
    assert found == ["experiment.locked", "experiment.locked"]
    after = LocalArtifactStore(executed.out)
    after.lock(LOCK_PATH)  # the store was closed, so the lock is free
    after.close()


# Endings without a manifest


def test_an_interrupt_ends_the_session_without_its_manifest_and_keeps_its_records(
    experiments: Experiments, monkeypatch: pytest.MonkeyPatch
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", *(complete() for _ in range(5)))
    wrapped: list[StorageFaults] = []

    def faults(store: LocalArtifactStore) -> StorageFaults:
        wrapped.append(StorageFaults(store, monkeypatch))
        # The second case's tables, the first of which is written whole.
        _, plan = plan_of("example.yaml")
        wrapped[0].fail_after(
            f"/cases/{plan.cases[1].case_id}/normalized/metrics.csv", KeyboardInterrupt()
        )
        return wrapped[0]

    executed = experiments.run(faults=faults)

    error = executed.error
    assert error is not None and error.code == "command.interrupted"
    assert "The session has no manifest" in error.message
    assert executed.received == (AUTH, SEND, SEND)
    assert not (executed.out / "sessions/1/manifest.json").exists()
    assert not (executed.out / "sessions/1/report.html").exists()
    published = wrapped[0].published
    assert len(published) == len(set(published))
    second = executed.plan.cases[1].case_id
    assert executed.record(second).outcome == "succeeded"
    assert (executed.out / "cases" / second / "normalized/metrics.csv").exists()
    assert not (executed.out / "cases" / second / "normalized/settings.csv").exists()


@pytest.mark.parametrize("name", ["/sessions/1/session.json", "/plans/1/experiment.json"])
def test_a_storage_failure_before_the_plan_is_recorded_sends_nothing(
    experiments: Experiments, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    def faults(store: LocalArtifactStore) -> StorageFaults:
        faulted = StorageFaults(store, monkeypatch)
        faulted.fail_os(name)
        return faulted

    executed = experiments.run(faults=faults)

    error = executed.error
    assert error is not None and error.code == "storage.write_failed"
    assert "Nothing was sent" in error.message
    assert "remove the directory, and run the command again" in error.message
    assert executed.received == ()
    assert executed.execution.manifest is None


def test_a_storage_failure_after_a_200_leaves_the_case_unknown_without_a_manifest(
    experiments: Experiments, monkeypatch: pytest.MonkeyPatch
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", complete(), complete())

    def faults(store: LocalArtifactStore) -> StorageFaults:
        faulted = StorageFaults(store, monkeypatch)
        faulted.fail_os("response.json")
        return faulted

    executed = experiments.run("default-only.yaml", faults=faults)

    error = executed.error
    assert error is not None and error.code == "storage.write_failed"
    assert executed.received == (AUTH, SEND)
    record = executed.record(executed.plan.cases[0].case_id)
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    assert "may have been charged" in error.message
    assert not (executed.out / "sessions/1/manifest.json").exists()


def test_an_attempt_record_that_wasnt_written_ends_the_session_without_its_manifest(
    experiments: Experiments, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A defect found by PR #66's review: the session went on, and wrote a manifest that counted
    # the attempt as succeeded, without its attempt record or its case's tables.
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", complete(), complete())

    def faults(store: LocalArtifactStore) -> StorageFaults:
        faulted = StorageFaults(store, monkeypatch)
        faulted.fail_before("attempt.json", RuntimeError())
        return faulted

    executed = experiments.run("default-only.yaml", faults=faults)

    error = executed.error
    assert error is not None and error.code == "internal.unexpected"
    assert executed.received == (AUTH, SEND)
    first, second = ids(executed.plan)
    (attempt,) = executed.attempts(first)
    assert (attempt / "started.json").is_file()
    assert not (attempt / "attempt.json").exists()
    assert not (executed.out / "cases" / first / "normalized").exists()
    assert not (executed.out / "cases" / second).exists()
    assert "its start record reads as running" in error.message
    assert "The session has no manifest" in error.message
    assert executed.execution.manifest is None
    assert not (executed.out / "sessions/1/manifest.json").exists()
    assert not (executed.out / "sessions/1/report.html").exists()
    # A running start record counts as unknown. A defect found by PR #66's review: the outcomes
    # read the attempt record that wasn't written, and gave the case as succeeded.
    assert outcomes(executed) == ["unknown", "not_yet_run"]


@pytest.mark.parametrize("records", ["authentication-record", "no-record"])
def test_an_attempt_without_a_start_record_or_an_attempt_record_reads_as_its_records_do(
    experiments: Experiments, monkeypatch: pytest.MonkeyPatch, records: str
) -> None:
    # As a resume will count it (the cases that are due): with only its authentication record,
    # failed and not possibly charged, and with no record, as no attempt. A defect found by PR
    # #66's review: the outcomes read the attempt record that wasn't written.
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", complete(), complete())
    _, plan = plan_of("default-only.yaml")
    first, second = ids(plan)
    wrapped: list[StorageFaults] = []

    def faults(store: LocalArtifactStore) -> StorageFaults:
        wrapped.append(StorageFaults(store, monkeypatch))
        if records == "authentication-record":
            wrapped[0].fail_before("started.json", RuntimeError())
            wrapped[0].fail_before("attempt.json", RuntimeError())
        return wrapped[0]

    class Arming(list[ProgressEvent]):
        """Fails the second case's request.json and attempt.json, before either is written. It
        sends with the first case's token, so it has no authentication record."""

        def append(self, event: ProgressEvent) -> None:
            super().append(event)
            started = isinstance(event, AttemptStarted) and event.case_id == second
            if records == "no-record" and started:
                wrapped[0].fail_before("request.json", RuntimeError())
                wrapped[0].fail_before("attempt.json", RuntimeError())

    executed = experiments.run("default-only.yaml", faults=faults, progress=Arming())

    error = executed.error
    assert error is not None and error.code == "internal.unexpected"
    assert executed.execution.manifest is None
    if records == "authentication-record":
        assert executed.received == (AUTH,)
        (attempt,) = executed.attempts(first)
        assert sorted(path.name for path in attempt.iterdir()) == [
            "authenticating.json",
            "request.json",
        ]
        assert outcomes(executed) == ["failed", "not_yet_run"]
    else:
        assert executed.received == (AUTH, SEND)
        assert not (executed.out / "cases" / second).exists()
        assert outcomes(executed) == ["succeeded", "not_yet_run"]


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (KeyboardInterrupt(), "command.interrupted"),
        # What the store raises when the sync after publishing a file fails. A defect found by
        # PR #66's review: the attempt record then had no authenticated_by.
        (
            TrialFolioError(
                "storage.write_failed",
                "Couldn't write started.json durably: Input/output error. Check the output"
                " directory's free space and permissions.",
            ),
            "storage.write_failed",
        ),
    ],
    ids=["interrupt", "storage-failure"],
)
def test_a_start_record_published_before_a_failure_agrees_with_the_attempt_record(
    experiments: Experiments, monkeypatch: pytest.MonkeyPatch, failure: BaseException, code: str
) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)

    def faults(store: LocalArtifactStore) -> StorageFaults:
        faulted = StorageFaults(store, monkeypatch)
        faulted.fail_after("started.json", failure)
        return faulted

    executed = experiments.run("default-only.yaml", faults=faults)

    error = executed.error
    assert error is not None and error.code == code
    assert executed.received == (AUTH,)
    (attempt,) = executed.attempts(ids(executed.plan)[0])
    start = StartRecordV1_1.model_validate_json((attempt / "started.json").read_bytes())
    record = AttemptRecordV1_1.model_validate_json((attempt / "attempt.json").read_bytes())
    # An attempt record has authenticated_by exactly when it has a start record, and the same.
    assert record.authenticated_by == start.authenticated_by == start.attempt_id
    assert (record.outcome, record.possibly_charged) == ("failed", False)
    (result,) = executed.execution.attempts
    assert result.start == start
    assert [file.role for file in result.files].count("start_record") == 1
    assert not (executed.out / "sessions/1/manifest.json").exists()


def test_an_interrupt_once_the_first_plan_is_published_leaves_it_to_resume(
    experiments: Experiments, monkeypatch: pytest.MonkeyPatch
) -> None:
    def faults(store: LocalArtifactStore) -> StorageFaults:
        faulted = StorageFaults(store, monkeypatch)
        faulted.fail_after("/plans/1/experiment.json", KeyboardInterrupt())
        return faulted

    executed = experiments.run(faults=faults)

    error = executed.error
    assert error is not None and error.code == "command.interrupted"
    assert (executed.out / "plans/1/experiment.json").is_file()
    assert "Nothing was sent" in error.message
    assert "running the same command again resumes it" in error.message
    assert "remove the directory" not in error.message
    assert executed.received == ()


def test_a_quota_refusal_of_the_last_case_stops_nothing_else(experiments: Experiments) -> None:
    experiments.server.reply("/auth", AUTHENTICATED)
    experiments.server.reply("/screen/backtest", complete(), Reply(402))

    executed = experiments.run("default-only.yaml")

    assert outcomes(executed) == ["succeeded", "failed"]
    error = executed.error
    assert error is not None and error.code == "execution.partial"
    assert "provider.quota_exceeded" in error.message
    assert "no later case started" not in error.message
