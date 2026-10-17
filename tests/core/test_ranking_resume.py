"""A resume with a ranking definition, in the core: the records check of attempts that send a
definition, and of a plan's `definition.xml`, in a resume and in a complete run, which
`trialfolio report` reads; the attempt record a resume writes for an attempt stopped after its
update record, or after `started.json`; the budget across runs with both of a case's requests; a
repeat that sends both again; the revisions with a definition; and the ranking lock in a resume.

Traces to docs/contracts.md, sending a definition (an attempt stopped after its update record,
and counting the requests), running an experiment (a resumed experiment, step 7's ranking lock,
step 8, checking the records, and the cases that are due), the ranking lock (when it's taken),
uncertain completion, experiment plans and revisions (the budget across runs), plans with a
ranking definition (revisions), repeating a case (the budget), `experiment.json` 1.1.0, the
experiment manifest's version 1.1.0, weight rows, and reports (a complete run); and, at the core,
to R04-AC10 (each request counted, an attempt started only when both fit, an attempt stopped
after its update record recorded on resume as possibly charged and sent again only by a confirmed
repeat, which sends both requests, and no backtest sent but right after its own case's
`rank_update`), R04-AC12 (records with a ranking definition that are incomplete or changed fail
with `input.not_a_run`, send nothing, and reserve no session, and `trialfolio report`'s core
refuses such a run the same way; a record with no reader fails with
`artifact.unknown_schema_version`), and R04-AC05 (a resume with cases due meets the ranking lock
before its session record). The real client, `requests`, and `urllib3` run over the fake server,
whose end-of-test check reads every `POST /rank` body (R04-AC09); storage faults wrap the real
store; the clock is fixed; and the ranking lock's file is in the test's temporary directory.

Each experiment and run is built during the test, through the core, and stopped where the test
needs it: by a cancellation, by storage faults, or by an interrupt, as a stopped process leaves
it.
"""

import json
import shutil
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.support import canaries
from tests.support.clock import FixedClock
from tests.support.fake_portfolio123 import FakePortfolio123, Reply
from tests.support.storage_faults import StorageFaults
from trialfolio.canonical import sha256_hex
from trialfolio.configuration import (
    ExperimentConfigurationRead,
    read_experiment_configuration_v1_1,
    read_screen_configuration_v1_1,
)
from trialfolio.contracts.attempt import AttemptRecordV1_1, AttemptRecordV1_3, Exchange
from trialfolio.contracts.experiment_manifest import ExperimentManifest, ExperimentManifestV1_1
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.experiment_record import ExperimentRecord, ExperimentRecordV1_1
from trialfolio.contracts.manifest import CommandRecord
from trialfolio.contracts.plan import PlanV1_2
from trialfolio.errors import TrialFolioError
from trialfolio.execution import Execution
from trialfolio.experiment_execution import (
    AttemptEnded,
    Cancellation,
    ExperimentExecution,
    ProgressEvent,
    Repeat,
)
from trialfolio.experiment_records import SavedExperiment, open_experiment, read_experiment
from trialfolio.planning import (
    build_experiment_plan_v1_1,
    build_plan_v1_1,
    installed_versions,
    plan_hash,
    plan_revision_v1_1,
)
from trialfolio.provider import Credentials, P123ScreenBacktestClient, ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE, RankingLock
from trialfolio.report import HtmlReportRenderer
from trialfolio.runs import check_run, read_run
from trialfolio.storage import ArtifactStore, LocalArtifactStore
from trialfolio.tables import read_settings_csv_v1_1, settings_csv_v1_1

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CONFIGS = FIXTURES / "experiment-configs"
RESPONSES = FIXTURES / "responses"
SCREEN = FIXTURES / "screen-configs" / "definition.yaml"
DEFINITIONS = CONFIGS / "ranking"

AUTH, RANK, BACKTEST = "POST /auth", "POST /rank", "POST /screen/backtest"
COMMAND = CommandRecord(name="run", options={}, started_at=FixedClock()())
REVISED = "A revised ranking definition."

type Json = dict[str, Any]


def authenticated() -> Reply:
    return Reply(200, canaries.TOKEN.encode())


def updated() -> Reply:
    return Reply(200, (RESPONSES / "rank-update.json").read_bytes())


def complete() -> Reply:
    return Reply(200, (RESPONSES / "complete.json").read_bytes())


def exchange(request: str, status: int | None, result: str = "response", note: str | None = None):
    return Exchange.model_validate(
        {"request": request, "result": result, "status": status, "note": note}
    )


def configuration(name: str) -> tuple[bytes, ExperimentConfigurationRead]:
    """An experiment configuration's bytes, read as release 0.4.0's reader reads it, with its
    definition file read beside it."""
    path = CONFIGS / name
    content = path.read_bytes()
    return content, read_experiment_configuration_v1_1(content, path.name, path)


def ranked_plan(name: str) -> PlanV1_3:
    """The plan 1.3.0 an experiment configuration with a ranking definition gives."""
    _, read = configuration(name)
    plan = build_experiment_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_3)
    return plan


EXAMPLE = ranked_plan("ranking-example.yaml")


@dataclass(frozen=True)
class Ran:
    """One run of the experiment, new or resumed, and what it sent."""

    error: TrialFolioError | None
    execution: ExperimentExecution | None
    """None when the run was refused before it was built."""
    received: tuple[str, ...]
    published: tuple[str, ...]
    """Each file the run's store published, in order."""


type Arm = Callable[[StorageFaults], object]

type Built = tuple[ExperimentExecution, bool]
"""An execution, and whether its plan is 1.3.0, so it's given its definition's bytes."""


class Lab:
    """Runs one experiment into one output directory, new and then resumed, through the core, over
    one fake server, as another interface would, with the ranking lock's file in the test's
    temporary directory."""

    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.out = tmp / "experiment"
        self.lock = tmp / LOCK_FILE
        self.server = FakePortfolio123()
        self._monkeypatch = monkeypatch

    def new(
        self,
        name: str = "ranking-example.yaml",
        *,
        cancel_after: int | None = None,
        arm: Arm | None = None,
    ) -> Ran:
        content, read = configuration(name)
        plan = build_experiment_plan_v1_1(read, installed_versions())
        cancellation = Cancellation()
        events: list[ProgressEvent] = []

        def progress(event: ProgressEvent) -> None:
            events.append(event)
            ended = sum(isinstance(e, AttemptEnded) for e in events)
            if isinstance(event, AttemptEnded) and ended == cancel_after:
                cancellation.cancel()

        def build(store: ArtifactStore, client: ScreenBacktestClient) -> Built:
            return ExperimentExecution(
                plan,
                plan.plan_hash,
                "option",
                store,
                client,
                command=None,
                clock=FixedClock(),
                progress=progress,
                cancellation=cancellation,
                ranking_lock=self.lock if isinstance(plan, PlanV1_3) else None,
            ), isinstance(plan, PlanV1_3)

        return self._run(content, read, build, arm=arm)

    def resume(
        self,
        name: str = "ranking-example.yaml",
        *,
        reason: str | None = None,
        repeats: Sequence[Repeat] = (),
        arm: Arm | None = None,
    ) -> Ran:
        content, read = configuration(name)

        def build(store: ArtifactStore, client: ScreenBacktestClient) -> Built:
            saved = open_experiment(store, ranking=True)
            revision = plan_revision_v1_1(read, installed_versions(), saved.current.plan)
            plan = saved.current.plan if revision is None else revision.plan
            return ExperimentExecution(
                plan,
                plan.plan_hash,
                "option",
                store,
                client,
                command=None,
                clock=FixedClock(),
                experiment=saved,
                reason=reason,
                repeats=repeats,
                ranking_lock=self.lock if isinstance(plan, PlanV1_3) else None,
            ), isinstance(plan, PlanV1_3)

        return self._run(content, read, build, arm=arm)

    def _run(
        self,
        content: bytes,
        read: ExperimentConfigurationRead,
        build: Callable[[ArtifactStore, ScreenBacktestClient], Built],
        *,
        arm: Arm | None,
    ) -> Ran:
        before = len(self.server.received)
        real = LocalArtifactStore(self.out)
        store = StorageFaults(real, self._monkeypatch)
        if arm is not None:
            arm(store)
        credentials = Credentials(canaries.API_ID, canaries.API_KEY)
        client = P123ScreenBacktestClient(credentials, endpoint=self.server.endpoint)
        definition = None if read.definition is None else read.definition.content
        execution: ExperimentExecution | None = None
        try:
            execution, ranked = build(store, client)
            error = execution.run(content, definition=definition if ranked else None)
        except TrialFolioError as refused:
            error = refused
        finally:
            client.close()
            real.close()
        received = tuple(f"{r.method} {r.path}" for r in self.server.received[before:])
        return Ran(error, execution, received, tuple(store.published))

    # Reading the records

    def read(self) -> SavedExperiment:
        with LocalArtifactStore(self.out) as store:
            return read_experiment(store, ranking=True)

    def manifest(self, session: int) -> ExperimentManifestV1_1:
        return ExperimentManifestV1_1.model_validate_json(
            (self.out / f"sessions/{session}/manifest.json").read_bytes()
        )

    def attempts(self, case_id: str) -> list[AttemptRecordV1_3]:
        """The case's attempt records 1.3.0, by session and then sequence."""
        records = [
            AttemptRecordV1_3.model_validate_json((path / "attempt.json").read_bytes())
            for path in (self.out / "cases" / case_id / "attempts").iterdir()
            if (path / "attempt.json").exists()
        ]
        return sorted(records, key=lambda record: (record.session, record.sequence))

    def directory(self, case_id: str) -> Path:
        """The directory of the case's one attempt."""
        (directory,) = sorted((self.out / "cases" / case_id / "attempts").iterdir())
        return directory


@pytest.fixture
def lab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Lab]:
    made = Lab(tmp_path, monkeypatch)
    yield made
    made.server.close()


def script(
    server: FakePortfolio123,
    *,
    auths: int = 1,
    ranks: Sequence[Reply] = (),
    backtests: Sequence[Reply] = (),
) -> None:
    server.reply("/auth", *(authenticated() for _ in range(auths)))
    server.reply("/rank", *ranks, method="POST")
    server.reply("/screen/backtest", *backtests)


def refused(ran: Ran, code: str) -> TrialFolioError:
    error = ran.error
    assert error is not None and error.code == code, error
    return error


def ids(plan: PlanV1_1 | PlanV1_3) -> list[str]:
    return [case.case_id for case in plan.cases]


def each_backtest_follows_its_cases_rank_update(
    server: FakePortfolio123, *plans: PlanV1_3, since: int = 0
) -> None:
    """Every `POST /screen/backtest` the server received, from its request `since` on, came right
    after a `POST /rank`, and the two are one case's: its `rank_update`'s params, and its
    backtest's (R04-AC10)."""
    sent = {
        (
            json.dumps(case.requests[0].params.model_dump(mode="json"), sort_keys=True),
            json.dumps(case.requests[1].params.model_dump(mode="json"), sort_keys=True),
        )
        for plan in plans
        for case in plan.cases
    }
    received = server.received
    for place, request in enumerate(received):
        if place < since or request.path != "/screen/backtest":
            continue
        previous = received[place - 1]
        assert place > 0 and previous.path == "/rank", "a backtest was sent without its rank_update"
        pair = (
            json.dumps(json.loads(previous.body), sort_keys=True),
            json.dumps(json.loads(request.body), sort_keys=True),
        )
        assert pair in sent, "a backtest followed another case's rank_update"


# An attempt a stopped run left without its attempt record


def first_case_faults(*faults: tuple[str, str]) -> Arm:
    """Faults at the first case's attempt only: `os` fails the write with a full disk,
    `unexpected` raises an unexpected exception before it, and `interrupt` an interrupt."""
    first = EXAMPLE.cases[0].case_id

    def arm(store: StorageFaults) -> None:
        for name, fault in faults:
            key = f"{first}/{name}"
            match fault:
                case "os":
                    store.fail_os(key)
                case "interrupt":
                    store.fail_before(key, KeyboardInterrupt())
                case _:
                    store.fail_before(key, RuntimeError())

    return arm


def test_an_attempt_stopped_after_its_update_record_is_recorded_unknown_and_not_sent_again(
    lab: Lab,
) -> None:
    # The rank_update was sent, and its response wasn't saved: the process stopped after the
    # update record, its last write before the send, as a killed process leaves it.
    script(lab.server, auths=2, ranks=[updated() for _ in range(4)], backtests=[complete()] * 3)
    first = lab.new(
        arm=first_case_faults(("rank-update-response.json", "os"), ("attempt.json", ""))
    )
    assert first.received == (AUTH, RANK)
    baseline = EXAMPLE.cases[0].case_id
    directory = lab.directory(baseline)
    assert sorted(p.name for p in directory.iterdir()) == [
        "authenticating.json",
        "rank-update-request.json",
        "updating.json",
    ]
    saved = lab.read()
    (stopped,) = saved.attempts_of(baseline)
    assert (stopped.outcome, stopped.possibly_charged, stopped.provider_requests) == (
        "unknown",
        True,
        1,
    )
    assert saved.cases(EXAMPLE)[0].state == "awaiting_repeat"

    resumed = lab.resume()

    # It isn't sent again, and every other case is, each rank_update right before its backtest.
    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    each_backtest_follows_its_cases_rank_update(lab.server, EXAMPLE)
    (record,) = lab.attempts(baseline)
    assert (record.outcome, record.possibly_charged, record.session) == ("unknown", True, 1)
    assert record.error is not None and record.error.code == "command.interrupted"
    assert record.exchanges == (exchange(AUTH, 200), exchange(RANK, None, "interrupted"))
    assert record.ranking_update.request is not None
    assert record.ranking_update.request.path.endswith("/rank-update-request.json")
    assert (record.ranking_update.response, record.request, record.response) == (None, None, None)
    assert "The screen backtest request wasn't sent" in record.error.message
    manifest = lab.manifest(2)
    assert manifest.counts.provider_requests == 1 + 2 * 3
    assert (manifest.counts.cases.unknown, manifest.counts.cases.succeeded) == (1, 3)
    error = refused(resumed, "execution.partial")
    assert "never sent again automatically" in error.message


@pytest.mark.parametrize(
    ("faults", "code"),
    [
        ((("request.json", "unexpected"), ("attempt.json", "unexpected")), "command.interrupted"),
        ((("request.json", "interrupt"), ("attempt.json", "os")), "command.interrupted"),
    ],
    ids=["an unexpected failure", "an interrupt, and a full disk at its attempt record"],
)
def test_an_attempt_stopped_after_its_rank_updates_response_is_recorded_failed(
    lab: Lab, faults: tuple[tuple[str, str], ...], code: str
) -> None:
    # The rank_update's 200 was saved, and the backtest's request.json wasn't written, so the
    # backtest wasn't sent; and the attempt's record wasn't either.
    script(lab.server, auths=2, ranks=[updated() for _ in range(4)], backtests=[complete()] * 3)
    lab.new(arm=first_case_faults(*faults))
    baseline = EXAMPLE.cases[0].case_id
    assert not (lab.directory(baseline) / "attempt.json").exists()
    # Before the resume records it, it reads as the resume will record it.
    (stopped,) = lab.read().attempts_of(baseline)
    assert (
        stopped.outcome,
        stopped.possibly_charged,
        stopped.provider_requests,
        stopped.error_code,
    ) == ("failed", True, 1, code)

    resumed = lab.resume()

    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    (record,) = lab.attempts(baseline)
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == code
    assert record.exchanges == (
        exchange(AUTH, 200),
        exchange(RANK, 200, note="completed_from_saved_response"),
    )
    response = record.ranking_update.response
    assert response is not None and response.form == "decoded"
    assert response.path.endswith("/rank-update-response.json")
    assert record.ranking_update.provider_metadata.cost == 1
    assert (record.request, record.response) == (None, None)
    assert lab.manifest(2).counts.provider_requests == 1 + 2 * 3
    assert lab.read().cases(EXAMPLE)[0].state == "awaiting_repeat"


def test_an_interrupt_at_the_backtests_request_leaves_its_case_awaiting_a_repeat(
    lab: Lab,
) -> None:
    # The attempt records itself, failed and possibly charged, so a resume doesn't send it.
    script(lab.server, auths=2, ranks=[updated() for _ in range(4)], backtests=[complete()] * 3)
    first = lab.new(arm=first_case_faults(("request.json", "interrupt")))
    assert refused(first, "command.interrupted")
    baseline = EXAMPLE.cases[0].case_id
    (record,) = lab.attempts(baseline)
    assert (record.outcome, record.possibly_charged) == ("failed", True)

    resumed = lab.resume()

    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    assert lab.attempts(baseline) == [record]


def test_an_undecoded_rank_update_response_is_recorded_as_invalid(lab: Lab) -> None:
    script(
        lab.server,
        auths=2,
        ranks=[Reply(200, b"<html>not JSON</html>"), *(updated() for _ in range(3))],
        backtests=[complete()] * 3,
    )
    lab.new(arm=first_case_faults(("attempt.json", "unexpected")))
    baseline = EXAMPLE.cases[0].case_id
    assert (lab.directory(baseline) / "rank-update-response.raw").exists()
    (stopped,) = lab.read().attempts_of(baseline)
    assert (stopped.outcome, stopped.error_code) == ("failed", "provider.response_invalid")

    lab.resume()

    (record,) = lab.attempts(baseline)
    assert (record.outcome, record.possibly_charged) == ("failed", True)
    assert record.error is not None and record.error.code == "provider.response_invalid"
    response = record.ranking_update.response
    assert response is not None and response.form == "undecoded"
    assert record.ranking_update.provider_metadata.cost is None


@pytest.mark.parametrize("saved", [True, False], ids=["with its response", "without one"])
def test_a_running_attempt_is_recorded_from_its_start_record(lab: Lab, saved: bool) -> None:
    # `started.json` was written, so both requests count; with its saved response, the attempt
    # succeeded, and without one, its outcome is unknown, and its case awaits a repeat.
    faults = (
        (("attempt.json", "unexpected"),)
        if saved
        else (
            ("response.json", "os"),
            ("attempt.json", "unexpected"),
        )
    )
    script(
        lab.server,
        auths=2,
        ranks=[updated() for _ in range(4)],
        backtests=[complete()] * 4,
    )
    lab.new(arm=first_case_faults(*faults))
    baseline = EXAMPLE.cases[0].case_id
    stopped = lab.read().attempts_of(baseline)[0]
    assert (stopped.outcome, stopped.provider_requests) == (
        "succeeded" if saved else "unknown",
        2,
    )

    resumed = lab.resume()

    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    (record,) = lab.attempts(baseline)
    assert record.request is not None and record.request.path.endswith("/request.json")
    assert record.ranking_update.response is not None
    if saved:
        assert (record.outcome, record.error) == ("succeeded", None)
        assert record.exchanges[-1] == exchange(BACKTEST, 200, note="completed_from_saved_response")
        assert record.provider_metadata.cost == 5
        # The tables a stopped run didn't write: settings.csv 1.1.0, with each weight row.
        rows = read_settings_csv_v1_1(
            (lab.out / f"cases/{baseline}/normalized/settings.csv").read_bytes(), "settings"
        )
        assert len([row for row in rows if row.node is not None]) == 9
    else:
        assert record.outcome == "unknown"
        assert record.exchanges == (exchange(AUTH, 200), exchange(RANK, 200))
    assert record.possibly_charged
    assert lab.manifest(2).counts.provider_requests == 2 + 2 * 3


def test_a_metrics_table_without_its_settings_table_is_completed_with_its_weight_rows(
    lab: Lab,
) -> None:
    script(lab.server, auths=2, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    lab.new(arm=first_case_faults(("settings.csv", "os")))
    baseline = EXAMPLE.cases[0].case_id
    assert not (lab.out / f"cases/{baseline}/normalized/settings.csv").exists()

    resumed = lab.resume()

    assert resumed.error is None
    rows = read_settings_csv_v1_1(
        (lab.out / f"cases/{baseline}/normalized/settings.csv").read_bytes(), "settings"
    )
    manifest = lab.manifest(2)
    listed = {a.path: a for a in manifest.artifacts}
    definition = listed["plans/1/definition.xml"].artifact_id
    weights = [row for row in rows if row.node is not None]
    assert [row.source_artifact for row in weights] == [definition] * 9
    assert listed[f"cases/{baseline}/normalized/settings.csv"].schema_version == "1.1.0"


def test_an_attempt_with_only_its_authentication_record_is_failed_and_its_case_is_sent(
    lab: Lab,
) -> None:
    script(lab.server, auths=2, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    lab.new(
        arm=first_case_faults(
            ("rank-update-request.json", "unexpected"), ("attempt.json", "unexpected")
        )
    )
    baseline = EXAMPLE.cases[0].case_id
    assert [p.name for p in lab.directory(baseline).iterdir()] == ["authenticating.json"]

    resumed = lab.resume()

    assert resumed.error is None
    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 4)
    stopped, sent = lab.attempts(baseline)
    assert (stopped.outcome, stopped.possibly_charged) == ("failed", False)
    assert stopped.exchanges == (exchange(AUTH, None, "interrupted"),)
    assert stopped.ranking_update.request is None
    assert sent.outcome == "succeeded" and sent.repeat_of is None


def _stopped_after_update(lab: Lab) -> Path:
    """An experiment whose first case's attempt stopped after its update record, with the
    rank_update's response saved: the directory of that attempt."""
    script(lab.server, ranks=[updated() for _ in range(4)], backtests=[complete()] * 3)
    lab.new(arm=first_case_faults(("request.json", "unexpected"), ("attempt.json", "unexpected")))
    return lab.directory(EXAMPLE.cases[0].case_id)


def _stopped_after_start(lab: Lab) -> Path:
    """The same, stopped after `started.json`, without the backtest's response."""
    script(lab.server, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    lab.new(arm=first_case_faults(("response.json", "os"), ("attempt.json", "unexpected")))
    return lab.directory(EXAMPLE.cases[0].case_id)


def _no_update_record(directory: Path) -> None:
    (directory / "updating.json").unlink()


def _no_rank_request(directory: Path) -> None:
    (directory / "rank-update-request.json").unlink()


def _no_rank_response(directory: Path) -> None:
    (directory / "rank-update-response.json").unlink()


def _two_rank_responses(directory: Path) -> None:
    (directory / "rank-update-response.raw").write_bytes(b"not JSON")


def _rank_response_without_update(directory: Path) -> None:
    (directory / "updating.json").unlink()


@pytest.mark.parametrize(
    ("stop", "change", "problem"),
    [
        (_stopped_after_start, _no_update_record, "without the update record written before it"),
        (_stopped_after_update, _no_rank_request, "not the rank-update-request.json written"),
        (_stopped_after_update, _two_rank_responses, "holds two saved rank_update responses"),
        (_stopped_after_start, _no_rank_response, "not the rank-update-response.json saved"),
        (
            _stopped_after_update,
            _rank_response_without_update,
            "holds the rank_update's response, but not the update record",
        ),
    ],
    ids=[
        "a start record without its update record",
        "an update record without its request",
        "two saved rank_update responses",
        "a start record without the rank_update's response",
        "a rank_update's response without its update record",
    ],
)
def test_an_attempt_without_its_record_needs_the_files_written_before_it(
    lab: Lab, stop: Callable[[Lab], Path], change: Callable[[Path], None], problem: str
) -> None:
    # No manifest lists these files: the run that wrote them stopped before its manifest.
    change(stop(lab))

    ran = lab.resume()

    error = refused(ran, "input.not_a_run")
    assert problem in error.message, error.message
    assert ran.received == () and ran.published == ()


# A repeat sends both requests again


def unknown_baseline(lab: Lab) -> uuid.UUID:
    """An experiment whose baseline's rank_update timed out, so its case awaits a repeat, and
    whose other cases succeeded. Returns the attempt a repeat names."""
    script(
        lab.server,
        ranks=[Reply(503, b""), *(updated() for _ in range(3))],
        backtests=[complete()] * 3,
    )
    refused(lab.new(), "execution.partial")
    (record,) = lab.attempts(EXAMPLE.cases[0].case_id)
    assert (record.outcome, record.possibly_charged) == ("unknown", True)
    return record.attempt_id


def test_a_confirmed_repeat_sends_the_rank_update_then_the_backtest_once(lab: Lab) -> None:
    budget = (CONFIGS / "revisions/ranking-budget-raised.yaml").name
    attempt_id = unknown_baseline(lab)
    baseline = EXAMPLE.cases[0].case_id
    script(lab.server, ranks=[updated()], backtests=[complete()])
    # Seven requests are counted, so the repeat's two need the raised budget.
    raised = lab.resume(
        f"revisions/{budget}", reason="A raised budget.", repeats=[Repeat(baseline, attempt_id)]
    )

    assert raised.error is None
    assert raised.received == (AUTH, RANK, BACKTEST)
    each_backtest_follows_its_cases_rank_update(lab.server, EXAMPLE)
    _, repeat = lab.attempts(baseline)
    assert (repeat.outcome, repeat.repeat_of, repeat.session) == ("succeeded", attempt_id, 2)
    assert repeat.exchanges == (exchange(AUTH, 200), exchange(RANK, 200), exchange(BACKTEST, 200))
    assert lab.manifest(2).counts.attempts.repeats == 1

    # The same command, run again, doesn't repeat it: its confirmation is used.
    again = lab.resume(
        f"revisions/{budget}", reason="A raised budget.", repeats=[Repeat(baseline, attempt_id)]
    )

    assert again.error is None and again.received == ()
    assert again.execution is not None
    assert again.execution.repeats_used == (Repeat(baseline, attempt_id),)


# The budget across runs, with both requests


def test_both_kinds_of_request_are_counted_and_their_costs_summed(lab: Lab) -> None:
    script(lab.server, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    assert lab.new().error is None

    saved = lab.read()

    assert saved.provider_requests == 8
    assert saved.counts(EXAMPLE).cost == 4 * (1 + 5)
    assert [attempt.provider_requests for attempt in saved.attempts] == [2] * 4


def test_a_repeat_the_budget_cant_cover_waits_for_a_revision_that_raises_it(lab: Lab) -> None:
    # A 503 to the last case's backtest leaves it unknown, with 8 requests counted, so its
    # repeat's two don't fit, and its confirmation stays unused.
    script(
        lab.server,
        ranks=[updated() for _ in range(4)],
        backtests=[*(complete() for _ in range(3)), Reply(503, b"")],
    )
    refused(lab.new(), "execution.partial")
    last = EXAMPLE.cases[-1].case_id
    (record,) = lab.attempts(last)
    assert (record.outcome, lab.read().provider_requests) == ("unknown", 8)
    repeat = Repeat(last, record.attempt_id)

    spent = lab.resume(repeats=[repeat])

    error = refused(spent, "execution.partial")
    assert spent.received == ()
    assert "budget couldn't cover the next case" in error.message
    assert spent.execution is not None and spent.execution.repeats_used == ()

    script(lab.server, ranks=[updated()], backtests=[complete()])
    raised = lab.resume(
        "revisions/ranking-budget-raised.yaml", reason="A raised budget.", repeats=[repeat]
    )

    assert raised.error is None
    assert raised.received == (AUTH, RANK, BACKTEST)
    assert lab.read().provider_requests == 10


def one_request_left(lab: Lab) -> Repeat:
    """An experiment whose baseline's rank_update got a 400, which counts one request, and whose
    three other cases succeeded, six more: one of the budget's 8 remains. Returns the repeat that
    names the baseline's attempt."""
    script(
        lab.server,
        auths=2,
        ranks=[Reply(400, b"Invalid ranking system"), *(updated() for _ in range(3))],
        backtests=[complete()] * 3,
    )
    refused(lab.new(), "execution.partial")
    baseline = EXAMPLE.cases[0].case_id
    (record,) = lab.attempts(baseline)
    assert (record.outcome, record.possibly_charged, lab.read().provider_requests) == (
        "failed",
        True,
        7,
    )
    return Repeat(baseline, record.attempt_id)


def test_a_remaining_budget_of_one_request_never_sends_a_rank_update(lab: Lab) -> None:
    # A case's two requests don't fit the one request left, so the repeat isn't started: its
    # rank_update would be sent, and its backtest not.
    repeat = one_request_left(lab)

    resumed = lab.resume(repeats=[repeat])

    error = refused(resumed, "execution.partial")
    assert resumed.received == ()
    assert "budget couldn't cover the next case" in error.message
    assert lab.read().provider_requests == 7
    assert lab.manifest(2).counts.provider_requests == 7
    assert resumed.execution is not None and resumed.execution.repeats_used == ()


def test_a_resume_whose_budget_covers_no_send_doesnt_take_the_ranking_lock(lab: Lab) -> None:
    # It sends nothing, so it runs while another process holds the lock.
    repeat = one_request_left(lab)

    with RankingLock(lab.lock):
        resumed = lab.resume(repeats=[repeat])

    refused(resumed, "execution.partial")
    assert resumed.received == ()
    assert lab.manifest(2).session == 2


def test_a_changed_definition_retires_the_cases_it_changes_and_keeps_the_others(lab: Lab) -> None:
    script(lab.server, auths=2, ranks=[updated() for _ in range(6)], backtests=[complete()] * 6)
    assert lab.new().error is None
    before = {case.case_key: case.case_id for case in EXAMPLE.cases}

    revised = lab.resume("revisions/ranking-definition-changed.yaml", reason=REVISED)

    assert revised.error is None
    # Its two new cases are sent, each with both requests, beside the 8 counted, within 12.
    assert revised.received == (AUTH, *(RANK, BACKTEST) * 2)
    plan = lab.read().current.plan
    assert isinstance(plan, PlanV1_3)
    each_backtest_follows_its_cases_rank_update(lab.server, EXAMPLE, plan)
    after = {case.case_key: case.case_id for case in plan.cases}
    assert {key: after[key] == before[key] for key in before} == {
        "baseline": False,
        "value-heavy": False,
        "tilt-earnings-yield": True,
        "no-sales-yield": True,
    }
    record = ExperimentRecordV1_1.model_validate_json(
        (lab.out / "plans/2/experiment.json").read_bytes()
    )
    changes = record.plans[-1].changes
    assert changes is not None
    assert [case.case_key for case in changes.cases_retired] == ["baseline", "value-heavy"]
    assert len(lab.attempts(after["tilt-earnings-yield"])) == 1
    revised_definition = (DEFINITIONS / "value-momentum-revised.xml").read_bytes()
    assert (lab.out / "plans/2/definition.xml").read_bytes() == revised_definition
    manifest = lab.manifest(2)
    assert manifest.counts.provider_requests == 12
    assert manifest.counts.retired_cases == 2
    listed = {a.path: a for a in manifest.artifacts}
    assert listed["plans/2/definition.xml"].role == "ranking_definition"


def test_a_changed_ranking_method_retires_every_case(lab: Lab) -> None:
    script(lab.server, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    assert lab.new().error is None

    revised = lab.resume("revisions/ranking-method-changed.yaml", reason=REVISED)

    # Its budget of 8 is counted already, so none of its new cases is sent.
    refused(revised, "execution.partial")
    assert revised.received == ()
    plan = lab.read().current.plan
    assert set(ids(plan)).isdisjoint(ids(EXAMPLE))
    assert lab.manifest(2).counts.retired_cases == 4


def test_a_revision_from_a_formula_sends_two_requests_a_case(lab: Lab) -> None:
    # example.yaml's five cases, ranked by a formula, send one request each; its revision ranked
    # by a definition sends two for each of its five new cases, within a budget of 15.
    script(lab.server, auths=2, ranks=[updated() for _ in range(5)], backtests=[complete()] * 10)
    assert lab.new("example.yaml").error is None
    since = len(lab.server.received)

    # A time no entry rebuilt from the records would give, so a kept entry can't pass for one.
    def acquired_earlier(manifest: Json) -> None:
        for artifact in manifest["artifacts"]:
            if artifact["source"] is not None:
                artifact["source"]["acquired_at"] = "2026-10-01T00:00:00Z"

    _edit(lab.out, "sessions/1/manifest.json", acquired_earlier)
    earlier = ExperimentManifest.model_validate_json(
        (lab.out / "sessions/1/manifest.json").read_bytes()
    )

    revised = lab.resume("revisions/ranking-from-formula.yaml", reason=REVISED)

    assert revised.error is None
    assert revised.received == (AUTH, *(RANK, BACKTEST) * 5)
    saved = lab.read()
    plan = saved.current.plan
    assert isinstance(plan, PlanV1_3)
    each_backtest_follows_its_cases_rank_update(lab.server, plan, since=since)
    assert saved.provider_requests == 5 + 10
    assert isinstance(saved.current.record, ExperimentRecordV1_1)
    assert (lab.out / "plans/2/definition.xml").exists()
    # Session 2's manifest is 1.1.0, and lists the first plan's files, and its attempts', with
    # the versions they have.
    manifest = lab.manifest(2)
    versions = {a.path: a.schema_version for a in manifest.artifacts}
    assert versions["plans/1/plan.json"] == "1.1.0"
    assert versions["plans/1/experiment.json"] == "1.0.0"
    assert versions["plans/1/configuration.yaml"] == "1.0.0"
    assert versions["plans/2/plan.json"] == "1.3.0"
    assert versions["plans/2/experiment.json"] == "1.1.0"
    assert versions["plans/2/configuration.yaml"] == "1.1.0"
    records = {
        path.rsplit("/", 1)[-1] + ":" + version
        for path, version in versions.items()
        if path.startswith("cases/") and path.endswith("attempt.json") and version
    }
    assert records == {"attempt.json:1.1.0", "attempt.json:1.3.0"}
    settings = {v for p, v in versions.items() if p.endswith("settings.csv")}
    assert settings == {"1.0.0", "1.1.0"}
    # Each file session 1's manifest 1.0.0 lists is listed again as it was, in version 1.1.0's
    # form, its source record included.
    listed = {a.path: a for a in manifest.artifacts}
    for entry in earlier.artifacts:
        if not entry.path.startswith("sessions/"):
            assert listed[entry.path].model_dump(mode="json") == entry.model_dump(mode="json")

    # A revision back to the formula keeps the first plan's cases, which succeeded, and its
    # experiment.json and manifest stay 1.1.0, since an earlier plan has a definition.
    back = lab.resume("example.yaml", reason="The formula again.")

    assert back.error is None and back.received == ()
    third = {a.path: a.schema_version for a in lab.manifest(3).artifacts}
    assert (third["plans/3/plan.json"], third["plans/3/experiment.json"]) == ("1.1.0", "1.1.0")
    saved = lab.read()
    assert isinstance(saved.current.plan, PlanV1_1)
    assert isinstance(saved.current.record, ExperimentRecordV1_1)
    assert lab.manifest(3).counts.cases.succeeded == 5
    assert lab.resume("example.yaml").error is None


def test_a_manifest_1_1_0_lists_each_file_no_manifest_listed_with_its_own_version(
    lab: Lab,
) -> None:
    # Session 1, of example.yaml, ended without its manifest, so session 2's, the first, lists
    # every file anew: the first plan's and its attempts' with their versions 1.0.0 and 1.1.0,
    # beside the revision's 1.3.0 and 1.1.0.
    script(lab.server, auths=2, ranks=[updated() for _ in range(5)], backtests=[complete()] * 10)
    first = lab.new("example.yaml", arm=lambda store: store.fail_os("manifest.json"))
    refused(first, "storage.write_failed")
    assert not (lab.out / "sessions/1/manifest.json").exists()

    revised = lab.resume("revisions/ranking-from-formula.yaml", reason=REVISED)

    assert revised.error is None
    versions = {a.path: a.schema_version for a in lab.manifest(2).artifacts}
    assert (
        versions["plans/1/plan.json"],
        versions["plans/1/experiment.json"],
        versions["plans/1/configuration.yaml"],
        versions["plans/2/plan.json"],
        versions["plans/2/experiment.json"],
    ) == ("1.1.0", "1.0.0", "1.0.0", "1.3.0", "1.1.0")
    plans = {saved.plan.plan_hash: saved.number for saved in lab.read().plans}
    for path, version in versions.items():
        if path.endswith(("started.json", "attempt.json")):
            record = json.loads((lab.out / path).read_bytes())
            expected = "1.1.0" if plans[record["plan_hash"]] == 1 else "1.3.0"
            assert version == expected, path
    settings = {v for p, v in versions.items() if p.endswith("settings.csv")}
    assert settings == {"1.0.0", "1.1.0"}


def test_a_resume_of_an_experiment_without_a_definition_keeps_0_3_0s_records(lab: Lab) -> None:
    script(lab.server, auths=2, backtests=[complete()] * 5)
    assert refused(lab.new("example.yaml", cancel_after=2), "execution.partial")

    resumed = lab.resume("example.yaml")

    assert resumed.error is None
    assert (
        ExperimentManifest.model_validate_json(
            (lab.out / "sessions/2/manifest.json").read_bytes()
        ).counts.provider_requests
        == 5
    )
    assert isinstance(lab.read().current.record, ExperimentRecord)


# The ranking lock in a resume (R04-AC05)


def test_a_resume_with_cases_due_meets_the_ranking_lock_before_its_session_record(
    lab: Lab,
) -> None:
    script(lab.server, auths=2, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    refused(lab.new(cancel_after=1), "execution.partial")

    with RankingLock(lab.lock):
        held = lab.resume()

    error = refused(held, "experiment.locked")
    assert "ApiRankingSystem" in error.message
    assert held.received == () and held.published == ()
    assert not (lab.out / "sessions/2").exists()

    resumed = lab.resume()

    assert resumed.error is None
    assert resumed.received == (AUTH, *(RANK, BACKTEST) * 3)
    assert lab.manifest(2).session == 2


def test_a_resume_that_sends_nothing_doesnt_take_the_ranking_lock(lab: Lab) -> None:
    script(lab.server, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    assert lab.new().error is None

    with RankingLock(lab.lock):
        resumed = lab.resume()

    assert resumed.error is None and resumed.received == ()
    assert lab.manifest(2).counts == lab.manifest(1).counts


# The records check of an experiment with a definition (R04-AC12)


def _latest(out: Path) -> Path:
    manifests = sorted(out.glob("sessions/*/manifest.json"), key=lambda p: int(p.parent.name))
    return manifests[-1]


def _rewrite(out: Path, path: str, data: bytes, manifest: Path | None = None) -> None:
    """Replaces a file, and the manifest's entry for it, so only the check under test can catch
    the break: the experiment's latest manifest, or `manifest`."""
    (out / path).write_bytes(data)
    listing = manifest or _latest(out)
    content = json.loads(listing.read_bytes())
    for artifact in content["artifacts"]:
        if artifact["path"] == path:
            artifact.update(artifact_id="sha256:" + sha256_hex(data), size=len(data))
    listing.write_bytes((json.dumps(content, indent=2) + "\n").encode())


def _edit(out: Path, path: str, change: Callable[[Json], object], manifest: Path | None = None):
    """Changes a JSON file with `change`, as `_rewrite` replaces one."""
    content = json.loads((out / path).read_bytes())
    change(content)
    data = (json.dumps(content, indent=2) + "\n").encode()
    if (out / path) == (manifest or _latest(out)):
        (out / path).write_bytes(data)
    else:
        _rewrite(out, path, data, manifest)


def _unlisted(out: Path, path: str, manifest: Path | None = None) -> None:
    """Removes a file, and the manifest's entry for it."""
    (out / path).unlink()
    listing = manifest or _latest(out)
    content = json.loads(listing.read_bytes())
    content["artifacts"] = [a for a in content["artifacts"] if a["path"] != path]
    listing.write_bytes((json.dumps(content, indent=2) + "\n").encode())


def _attempt_of(out: Path, case: int) -> str:
    """The directory of the one attempt of `EXAMPLE`'s case at that place."""
    (directory,) = sorted((out / "cases" / EXAMPLE.cases[case].case_id / "attempts").iterdir())
    return directory.relative_to(out).as_posix()


def _completed(lab: Lab) -> None:
    """A complete experiment of `ranking-example.yaml`: its first two cases in session 1, the
    rest in session 2, each sent with its session's token but the first."""
    script(lab.server, auths=2, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    refused(lab.new(cancel_after=2), "execution.partial")
    assert lab.resume().error is None


def _weight_row_changed(out: Path) -> None:
    path = f"cases/{EXAMPLE.cases[1].case_id}/normalized/settings.csv"
    rows = read_settings_csv_v1_1((out / path).read_bytes(), "settings")
    changed = [
        row.model_copy(update={"value": "45"}) if row.node == "Value/Earnings Yield" else row
        for row in rows
    ]
    _rewrite(out, path, settings_csv_v1_1(changed))


def _weight_row_source(out: Path) -> None:
    path = f"cases/{EXAMPLE.cases[1].case_id}/normalized/settings.csv"
    rows = read_settings_csv_v1_1((out / path).read_bytes(), "settings")
    other = "sha256:" + "0" * 64
    changed = [
        row.model_copy(update={"source_artifact": other}) if row.node else row for row in rows
    ]
    _rewrite(out, path, settings_csv_v1_1(changed))


def _weight_row_drawn_from(case: int, node: str, file: str) -> Callable[[Path], None]:
    """Gives the weight row of `node`, in the settings.csv of `EXAMPLE`'s case at that place, the
    `artifact_id` of `file`, one of the plan's, as its source."""

    def change(out: Path) -> None:
        path = f"cases/{EXAMPLE.cases[case].case_id}/normalized/settings.csv"
        rows = read_settings_csv_v1_1((out / path).read_bytes(), "settings")
        source = "sha256:" + sha256_hex((out / file).read_bytes())
        assert any(row.node == node and row.source_artifact != source for row in rows)
        changed = [
            row.model_copy(update={"source_artifact": source}) if row.node == node else row
            for row in rows
        ]
        _rewrite(out, path, settings_csv_v1_1(changed))

    return change


def _start_record_as_update_record(out: Path) -> None:
    """The second case's `started.json`, replaced by its `updating.json`. The attempt sent with its
    session's token, so its update record holds no exchange, and both records then name the
    rank_update."""
    directory = _attempt_of(out, 1)
    _rewrite(out, f"{directory}/started.json", (out / directory / "updating.json").read_bytes())


def _update_record_as_start_record(out: Path) -> None:
    """The second case's `updating.json`, replaced by its `started.json`, which is gone: both
    records then name the backtest, and the update record holds the rank_update's 200."""
    directory = _attempt_of(out, 1)
    _rewrite(out, f"{directory}/updating.json", (out / directory / "started.json").read_bytes())
    _unlisted(out, f"{directory}/started.json")


def _record_1_1_0(out: Path) -> None:
    """An attempt record 1.1.0, valid, of an attempt that ended before it authenticated, under the
    plan 1.3.0, in a new attempt's directory, which no manifest lists."""
    record = json.loads((out / _attempt_of(out, 0) / "attempt.json").read_bytes())
    attempt_id = str(uuid.uuid4())
    old = AttemptRecordV1_1.model_validate_json(
        json.dumps(
            {
                "schema_version": "1.1.0",
                "trialfolio_version": record["trialfolio_version"],
                "attempt_id": attempt_id,
                "case_id": record["case_id"],
                "plan_hash": record["plan_hash"],
                "session": 2,
                "sequence": 9,
                "authenticated_by": None,
                "repeat_of": None,
                "started_at": record["started_at"],
                "provider_wrapper": record["provider_wrapper"],
                "transport": record["transport"],
                "ended_at": record["started_at"],
                "outcome": "failed",
                "error": {"code": "command.interrupted", "message": "Interrupted."},
                "exchanges": [],
                "possibly_charged": False,
                "request": None,
                "response": None,
                "provider_metadata": {"cost": None, "quota_remaining": None},
            }
        )
    )
    directory = out / "cases" / record["case_id"] / "attempts" / attempt_id
    directory.mkdir()
    (directory / "attempt.json").write_bytes(old.model_dump_json(indent=2).encode())


def _transport_changed(content: Json) -> None:
    content["transport"]["urllib3"] = "0.0.1"


def _rank_update_status(status: int) -> Callable[[Json], None]:
    def change(content: Json) -> None:
        (rank,) = [e for e in content["exchanges"] if e["request"] == RANK]
        rank["status"] = status

    return change


EXPERIMENT_BREAKS: dict[str, tuple[Callable[[Path], object], str]] = {
    "an attempt with started.json and no updating.json": (
        lambda out: _unlisted(out, f"{_attempt_of(out, 0)}/updating.json"),
        "without the update record written before it",
    ),
    "an update record that disagrees with its start record": (
        lambda out: _edit(out, f"{_attempt_of(out, 1)}/updating.json", _transport_changed),
        "the start record doesn't hold the update record's values",
    ),
    "a started.json that names the rank_update, as its updating.json does": (
        _start_record_as_update_record,
        "a start record doesn't name the request it comes before",
    ),
    "an updating.json that names the backtest, as its missing started.json did": (
        _update_record_as_start_record,
        "a start record doesn't name the request it comes before",
    ),
    "an attempt record that sent its backtest, without its started.json": (
        lambda out: _unlisted(out, f"{_attempt_of(out, 1)}/started.json"),
        "its backtest was sent, or may have been, without the start record written before it",
    ),
    "a started.json whose exchanges don't end with the rank_update's 200": (
        lambda out: _edit(out, f"{_attempt_of(out, 1)}/started.json", _rank_update_status(500)),
        "isn't a valid start record",
    ),
    "a rank-update-request.json whose bytes aren't what the attempt record records": (
        lambda out: _rewrite(out, f"{_attempt_of(out, 2)}/rank-update-request.json", b"{}\n"),
        "doesn't match the artifact_id its attempt record gives it",
    ),
    "an attempt record 1.1.0 under a plan 1.3.0": (
        _record_1_1_0,
        "aren't the version an attempt under their plan writes",
    ),
    "a backtest's exchange after a rank_update that didn't get a 200": (
        lambda out: _edit(out, f"{_attempt_of(out, 3)}/attempt.json", _rank_update_status(500)),
        "isn't a valid attempt record",
    ),
    "a plan whose definition.xml is missing": (
        lambda out: _unlisted(out, "plans/1/definition.xml"),
        "`plans/1/definition.xml` is missing",
    ),
    "a plan whose definition.xml isn't its ranking_source's": (
        lambda out: _rewrite(
            out, "plans/1/definition.xml", (DEFINITIONS / "value-heavy.xml").read_bytes()
        ),
        "isn't its plan's ranking definition",
    ),
    "a weight row that isn't its definition's": (
        _weight_row_changed,
        "weight rows aren't its case's definition's",
    ),
    "a weight row drawn from another file": (
        _weight_row_source,
        "weight rows aren't its case's definition's",
    ),
    "a weight row its ranking variant changes, drawn from the definition": (
        _weight_row_drawn_from(1, "Value", "plans/1/definition.xml"),
        "weight rows aren't its case's definition's",
    ),
    "a weight row its definition gives, drawn from the configuration": (
        _weight_row_drawn_from(0, "Value", "plans/1/configuration.yaml"),
        "weight rows aren't its case's definition's",
    ),
    "a settings.csv listed as 1.0.0 under a plan 1.3.0": (
        lambda out: _edit(
            out,
            "sessions/2/manifest.json",
            lambda d: next(a for a in d["artifacts"] if a["path"].endswith("settings.csv")).update(
                schema_version="1.0.0"
            ),
        ),
        "another version than its case's plan's",
    ),
}


def _files(out: Path) -> dict[str, bytes]:
    return {
        path.relative_to(out).as_posix(): path.read_bytes()
        for path in out.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("name", sorted(EXPERIMENT_BREAKS))
def test_an_experiments_broken_records_fail_the_check_and_nothing_is_sent(
    lab: Lab, name: str
) -> None:
    _completed(lab)
    breaking, problem = EXPERIMENT_BREAKS[name]
    breaking(lab.out)
    before = _files(lab.out)

    ran = lab.resume()

    error = refused(ran, "input.not_a_run")
    assert problem in error.message, error.message
    assert ran.received == () and ran.published == ()
    assert _files(lab.out) == before


def test_an_attempt_a_resume_recorded_from_its_started_json_needs_that_record(lab: Lab) -> None:
    # Only a resume from `started.json` records an attempt `unknown` after its rank_update's 200,
    # without a backtest exchange, so its backtest may have been sent: a copy that lost that start
    # record fails the check, as one that lost a sent backtest's does.
    script(lab.server, auths=2, ranks=[updated() for _ in range(4)], backtests=[complete()] * 4)
    lab.new(arm=first_case_faults(("response.json", "os"), ("attempt.json", "unexpected")))
    lab.resume()
    (record,) = lab.attempts(EXAMPLE.cases[0].case_id)
    assert (record.outcome, record.exchanges) == (
        "unknown",
        (exchange(AUTH, 200), exchange(RANK, 200)),
    )
    _unlisted(lab.out, f"{_attempt_of(lab.out, 0)}/started.json")
    before = _files(lab.out)

    ran = lab.resume()

    error = refused(ran, "input.not_a_run")
    assert "its backtest was sent, or may have been, without the start record" in error.message
    assert ran.received == () and ran.published == ()
    assert _files(lab.out) == before


def test_a_request_sent_with_a_token_a_401_to_a_rank_update_dropped_fails_the_check(
    lab: Lab,
) -> None:
    # The second case's rank_update got a 401, which dropped the token the first case obtained,
    # so the third case authenticated again. A copy of the fourth case's attempt that names the
    # first case's token can't have been sent.
    script(
        lab.server,
        auths=2,
        ranks=[updated(), Reply(401, b""), updated(), updated()],
        backtests=[complete()] * 3,
    )
    refused(lab.new(), "execution.partial")
    first = json.loads((lab.out / _attempt_of(lab.out, 0) / "attempt.json").read_bytes())
    source = lab.out / _attempt_of(lab.out, 3)
    attempt_id = str(uuid.uuid4())
    directory = f"cases/{EXAMPLE.cases[3].case_id}/attempts/{attempt_id}"
    shutil.copytree(source, lab.out / directory)
    for name in ("updating.json", "started.json", "attempt.json"):
        path = lab.out / directory / name
        record = json.loads(path.read_bytes())
        record.update(attempt_id=attempt_id, sequence=9, authenticated_by=first["attempt_id"])
        for holder in (record, record.get("ranking_update") or {}):
            for reference in ("request", "response"):
                if holder.get(reference):
                    file = holder[reference]["path"].rsplit("/", 1)[-1]
                    holder[reference]["path"] = f"{directory}/{file}"
        path.write_bytes((json.dumps(record, indent=2) + "\n").encode())

    ran = lab.resume()

    error = refused(ran, "input.not_a_run")
    assert "a token that a 401 or 403 to an earlier request had dropped" in error.message
    assert ran.received == () and ran.published == ()


@pytest.mark.parametrize(
    ("path", "listed"),
    [
        ("plans/1/plan.json", False),
        ("plans/1/experiment.json", False),
        ("sessions/2/manifest.json", False),
        ("{attempt}/updating.json", False),
        ("{attempt}/started.json", False),
        ("{attempt}/attempt.json", False),
        ("{settings}", True),
    ],
)
def test_a_record_0_4_0_adds_without_a_reader_fails_the_check(
    lab: Lab, path: str, listed: bool
) -> None:
    _completed(lab)
    settings = f"cases/{EXAMPLE.cases[0].case_id}/normalized/settings.csv"
    path = path.format(attempt=_attempt_of(lab.out, 1), settings=settings)
    if listed:
        _edit(
            lab.out,
            "sessions/2/manifest.json",
            lambda d: next(a for a in d["artifacts"] if a["path"] == path).update(
                schema_version="9.9.9"
            ),
        )
    else:
        _edit(lab.out, path, lambda d: d.update(schema_version="9.9.9"))

    ran = lab.resume()

    error = refused(ran, "artifact.unknown_schema_version")
    assert f"`{path}`" in error.message
    assert "9.9.9" not in error.message
    assert ran.received == () and ran.published == ()


def test_without_ranking_the_records_check_reads_0_3_0s_versions_only(lab: Lab) -> None:
    # As `trialfolio run` reads an experiment's records until release 0.4.0's R04-T12, so it
    # refuses one with a definition by its version, as before.
    _completed(lab)

    with LocalArtifactStore(lab.out) as store, pytest.raises(TrialFolioError) as caught:
        read_experiment(store)

    assert caught.value.code == "artifact.unknown_schema_version"
    assert "experiment manifests 1.0.0" in caught.value.message


def _labeled_1_1_0(content: Json) -> None:
    content["schema_version"] = "1.1.0"


def _record_labeled_1_1_0(content: Json) -> None:
    content["schema_version"] = "1.1.0"
    for case in (*content["planned_cases"], *content["retired_cases"]):
        if case["variant"] is not None:
            case["variant"].update(set=None, remove=None)


@pytest.mark.parametrize(
    ("path", "change", "problem"),
    [
        ("sessions/1/manifest.json", _labeled_1_1_0, "isn't the version its session's manifest is"),
        ("plans/1/experiment.json", _record_labeled_1_1_0, "isn't the version its plan's"),
    ],
    ids=["a manifest 1.1.0", "an experiment.json 1.1.0"],
)
def test_a_record_1_1_0_of_an_experiment_without_a_definition_fails_the_check(
    lab: Lab, path: str, change: Callable[[Json], None], problem: str
) -> None:
    # Each is valid as version 1.1.0, whose fields are 1.0.0's and more, but only an experiment
    # with a plan 1.3.0 writes it.
    script(lab.server, backtests=[complete()] * 5)
    assert lab.new("example.yaml").error is None
    _edit(lab.out, path, change)

    ran = lab.resume("example.yaml")

    error = refused(ran, "input.not_a_run")
    assert problem in error.message, error.message
    assert ran.received == () and ran.published == ()


def test_a_rank_updates_file_under_a_plan_without_a_definition_fails_the_check(lab: Lab) -> None:
    # Only an attempt that sends a definition writes the rank_update's files.
    script(lab.server, backtests=[complete()] * 5)
    assert lab.new("example.yaml").error is None
    (first,) = sorted((lab.out / "cases").iterdir())[:1]
    (directory,) = sorted((first / "attempts").iterdir())
    (directory / "rank-update-request.json").write_bytes(b"{}\n")

    ran = lab.resume("example.yaml")

    error = refused(ran, "input.not_a_run")
    assert "holds a file no attempt under its plan writes" in error.message
    assert ran.received == () and ran.published == ()


# The records check of a run with a definition, which `trialfolio report` reads (R04-AC12)


@dataclass(frozen=True)
class Screen:
    out: Path
    plan: PlanV1_2

    @property
    def attempt(self) -> str:
        case_id = self.plan.cases[0].case_id
        (directory,) = sorted((self.out / "cases" / case_id / "attempts").iterdir())
        return directory.relative_to(self.out).as_posix()

    @property
    def manifest(self) -> Path:
        return self.out / "manifest.json"


def write_screen(tmp: Path, server: FakePortfolio123, definition: bytes | None = None) -> Screen:
    """A screen run of `definition.yaml`, through the core, over the fake server, whose ranking
    is the definition the file names, or `definition`'s bytes."""
    content = SCREEN.read_bytes()
    read = read_screen_configuration_v1_1(content, SCREEN.name, SCREEN, definition=definition)
    plan = build_plan_v1_1(read, installed_versions())
    assert isinstance(plan, PlanV1_2) and read.definition is not None
    server.reply("/auth", authenticated())
    server.reply("/rank", updated(), method="POST")
    server.reply("/screen/backtest", complete())
    out = tmp / "run"
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    with LocalArtifactStore(out) as store:
        error = Execution(
            plan, plan.plan_hash, "option", store, COMMAND, ranking_lock=tmp / LOCK_FILE
        ).run(
            content,
            lambda: P123ScreenBacktestClient(credentials, endpoint=server.endpoint),
            definition=read.definition.content,
        )
    assert error is None
    return Screen(out, plan)


@pytest.fixture
def server() -> Iterator[FakePortfolio123]:
    fake = FakePortfolio123()
    yield fake
    fake.close()


def test_report_reads_a_run_with_a_definition_and_renders_its_own_report(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    run = write_screen(tmp_path, server)

    saved = read_run(LocalArtifactStore(run.out))

    assert saved.plan == run.plan
    (attempt,) = saved.attempts
    assert attempt.update is not None and attempt.update.operation == "rank_update"
    assert attempt.status.provider_requests == 2
    assert saved.settings is not None
    assert len([row for row in saved.settings if getattr(row, "node", None)]) == 9
    renderer = HtmlReportRenderer(run.plan.trialfolio_version)
    assert renderer.render(saved, "") == (run.out / "report.html").read_text(encoding="utf-8")


def test_report_reads_a_run_whose_definition_has_windows_line_endings(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # The copy holds the file's bytes, so its artifact_id differs from the definition's hash,
    # which reads each line end as a line feed.
    windows = (DEFINITIONS / "value-momentum.xml").read_bytes().replace(b"\n", b"\r\n")
    run = write_screen(tmp_path, server, definition=windows)

    saved = read_run(LocalArtifactStore(run.out))

    assert (run.out / "definition.xml").read_bytes() == windows
    assert saved.plan.plan_hash == plan_hash(run.plan)
    copy = "sha256:" + sha256_hex(windows)
    assert isinstance(saved.plan, PlanV1_2)
    assert saved.plan.ranking_source.definition != copy


def test_a_reviews_check_still_reads_0_3_0s_runs_only(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # A review compares weight rows only from release 0.4.0's R04-T11.
    run = write_screen(tmp_path, server)

    with pytest.raises(TrialFolioError) as caught:
        check_run(LocalArtifactStore(run.out))

    assert caught.value.code == "artifact.unknown_schema_version"


def _run_weight_row_changed(run: Screen) -> None:
    rows = read_settings_csv_v1_1((run.out / "normalized/settings.csv").read_bytes(), "settings")
    changed = [
        row.model_copy(update={"value": "45"}) if row.node == "Value" else row for row in rows
    ]
    _rewrite(run.out, "normalized/settings.csv", settings_csv_v1_1(changed), run.manifest)


def _run_record_1_0_0(run: Screen) -> None:
    _edit(
        run.out,
        f"{run.attempt}/attempt.json",
        lambda d: d.update(schema_version="1.0.0"),
        run.manifest,
    )


RUN_BREAKS: dict[str, tuple[Callable[[Screen], object], str]] = {
    "an attempt with started.json and no updating.json": (
        lambda run: _unlisted(run.out, f"{run.attempt}/updating.json", run.manifest),
        "wrote its update record first",
    ),
    "an update record that disagrees with its start record": (
        lambda run: _edit(
            run.out, f"{run.attempt}/updating.json", _transport_changed, run.manifest
        ),
        "doesn't hold the update record's values and exchanges",
    ),
    "a started.json whose exchanges don't end with the rank_update's 200": (
        lambda run: _edit(
            run.out, f"{run.attempt}/started.json", _rank_update_status(500), run.manifest
        ),
        "isn't a valid start record",
    ),
    "a rank-update-request.json whose bytes aren't what the attempt record records": (
        lambda run: _rewrite(
            run.out, f"{run.attempt}/rank-update-request.json", b"{}\n", run.manifest
        ),
        "which its manifest doesn't list as that file",
    ),
    "an attempt record 1.0.0 under a plan 1.2.0": (
        _run_record_1_0_0,
        "isn't the version an attempt under its plan writes",
    ),
    "a backtest's exchange after a rank_update that didn't get a 200": (
        lambda run: _edit(
            run.out, f"{run.attempt}/attempt.json", _rank_update_status(500), run.manifest
        ),
        "isn't a valid attempt record",
    ),
    "a run whose definition.xml is missing": (
        lambda run: _unlisted(run.out, "definition.xml", run.manifest),
        "doesn't list definition.xml as the run's one ranking_definition",
    ),
    "a run whose definition.xml isn't its ranking_source's": (
        lambda run: _rewrite(
            run.out, "definition.xml", (DEFINITIONS / "value-heavy.xml").read_bytes(), run.manifest
        ),
        "isn't its plan's ranking definition",
    ),
    "a weight row that isn't its definition's": (
        _run_weight_row_changed,
        "weight rows aren't its definition's",
    ),
}


@pytest.mark.parametrize("name", sorted(RUN_BREAKS))
def test_a_runs_broken_records_are_refused_and_nothing_is_written(
    tmp_path: Path, server: FakePortfolio123, name: str
) -> None:
    run = write_screen(tmp_path, server)
    breaking, problem = RUN_BREAKS[name]
    breaking(run)
    before = _files(run.out)

    with pytest.raises(TrialFolioError) as caught:
        read_run(LocalArtifactStore(run.out))

    assert caught.value.code == "input.not_a_run"
    assert problem in caught.value.message, caught.value.message
    assert _files(run.out) == before


def test_a_runs_attempt_with_only_its_update_record_reads_as_running(
    tmp_path: Path, server: FakePortfolio123
) -> None:
    # As a run's attempt with only its start record does: one request, possibly charged.
    run = write_screen(tmp_path, server)
    kept = (f"{run.attempt}/updating.json", f"{run.attempt}/rank-update-request.json")

    def update_only(content: Json) -> None:
        content["artifacts"] = [
            a
            for a in content["artifacts"]
            if a["path"] in ("plan.json", "configuration.yaml", "definition.xml", *kept)
        ]

    _edit(run.out, "manifest.json", update_only, run.manifest)

    saved = read_run(LocalArtifactStore(run.out))

    (attempt,) = saved.attempts
    assert (attempt.start, attempt.record) == (None, None)
    status = attempt.status
    assert (status.outcome, status.possibly_charged, status.provider_requests) == (
        "running",
        True,
        1,
    )


def _settings_listed_1_1_0(manifest: Json) -> None:
    (entry,) = [a for a in manifest["artifacts"] if a["role"] == "settings"]
    entry["schema_version"] = "1.1.0"


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (_labeled_1_1_0, "isn't the version a run of its plan writes"),
        (_settings_listed_1_1_0, "another version than a run of its plan writes"),
    ],
    ids=["its manifest 1.1.0", "its settings.csv listed as 1.1.0"],
)
def test_a_run_without_a_definition_refuses_versions_only_a_definition_gives(
    tmp_path: Path, server: FakePortfolio123, change: Callable[[Json], None], problem: str
) -> None:
    # Each version has a reader, and a run manifest 1.1.0 is valid with 1.0.0's fields, but only
    # a run of a plan 1.2.0 writes them.
    formula = FIXTURES / "screen-configs" / "formula.yaml"
    content = formula.read_bytes()
    read = read_screen_configuration_v1_1(content, formula.name, formula)
    plan = build_plan_v1_1(read, installed_versions())
    server.reply("/auth", authenticated())
    server.reply("/screen/backtest", complete())
    out = tmp_path / "run"
    credentials = Credentials(canaries.API_ID, canaries.API_KEY)
    with LocalArtifactStore(out) as store:
        assert (
            Execution(plan, plan.plan_hash, "option", store, COMMAND).run(
                content, lambda: P123ScreenBacktestClient(credentials, endpoint=server.endpoint)
            )
            is None
        )
    assert read_run(LocalArtifactStore(out)).plan == plan
    _edit(out, "manifest.json", change, out / "manifest.json")

    with pytest.raises(TrialFolioError) as caught:
        read_run(LocalArtifactStore(out))

    assert caught.value.code == "input.not_a_run"
    assert problem in caught.value.message, caught.value.message


@pytest.mark.parametrize(
    ("path", "listed"),
    [
        ("manifest.json", False),
        ("plan.json", False),
        ("{attempt}/updating.json", False),
        ("{attempt}/started.json", False),
        ("{attempt}/attempt.json", False),
        ("normalized/settings.csv", True),
    ],
)
def test_a_runs_record_0_4_0_adds_without_a_reader_is_unknown(
    tmp_path: Path, server: FakePortfolio123, path: str, listed: bool
) -> None:
    run = write_screen(tmp_path, server)
    path = path.format(attempt=run.attempt)
    if listed:
        _edit(
            run.out,
            "manifest.json",
            lambda d: next(a for a in d["artifacts"] if a["path"] == path).update(
                schema_version="9.9.9"
            ),
            run.manifest,
        )
    else:
        _edit(run.out, path, lambda d: d.update(schema_version="9.9.9"), run.manifest)

    with pytest.raises(TrialFolioError) as caught:
        read_run(LocalArtifactStore(run.out))

    assert caught.value.code == "artifact.unknown_schema_version"
    assert f"`{path}`" in caught.value.message
    assert "9.9.9" not in caught.value.message
