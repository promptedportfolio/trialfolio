"""The attempt classes (docs/contracts.md, execution outcomes and attempts, experiment attempts,
sending a definition, and ranking snapshot output): `_AttemptBase`, what every kind of attempt
shares, and the five kinds, each of which gives only its records, its sends, and its result.

- A screen run's: `Attempt`, with records 1.0.0, and `RankingAttempt`, with a definition, 1.2.0.
- A ranking snapshot's: `SnapshotAttempt`, with records 1.2.0 and no case.
- An experiment's: `ExperimentAttempt`, with records 1.1.0, and `RankingExperimentAttempt`, with
  a definition, 1.3.0.

A run's and a snapshot's attempt is its command's only one, with a new client of its own, which
it authenticates first (`_RunAttempt`). An experiment's attempts share their session's client,
and its token (`_SessionAttempt`).

- **`ended_at`** is the clock's time when the attempt ends, or its start time when the clock
  reads earlier, as after the wall clock moved backward during the attempt, so the attempt record
  can still be written.
- **Logs.** An attempt logs its start, its `rank_update`'s, and the pause before its backtest, as
  `trialfolio.attempts`, as its ending policy logs its end (docs/refactoring.md, decision 11).
- **The pause (D-45).** An attempt that sends a definition waits, after its `rank_update`'s 200,
  until at least 10 seconds have passed on a monotonic clock, before it writes its backtest's
  request and start record, and sends the backtest. The wait is injected, as the clock is.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final, Literal, TypedDict, cast

from trialfolio.attempts.endings import (
    AttemptEnding,
    Classifier,
    Ending,
    EndingFields,
    one_request_ending,
    ranking_ending,
    snapshot_ending,
)
from trialfolio.attempts.files import (
    AUTHENTICATION_RECORD,
    RANK_UPDATE_RESPONSE_RAW,
    START_RECORD,
    UPDATE_RECORD,
    AttemptFile,
    AttemptFiles,
    attempt_directory,
    snapshot_attempt_directory,
)
from trialfolio.contracts.attempt import (
    AttemptRecord,
    AttemptRecordV1_1,
    AttemptRecordV1_2,
    AttemptRecordV1_3,
    AuthenticationRecord,
    Exchange,
    StartRecord,
    StartRecordV1_1,
    StartRecordV1_2,
    StartRecordV1_3,
)
from trialfolio.contracts.common import TransportVersions, WrapperVersions
from trialfolio.contracts.experiment_plan import (
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanV1_1,
    PlanV1_3,
)
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotPlan
from trialfolio.errors import TrialFolioError
from trialfolio.manifests import model_json, utc
from trialfolio.pause import REAL_PAUSE, UPDATE_PAUSE_SECONDS, Pause
from trialfolio.planning import check_approval
from trialfolio.provider import (
    ProviderError,
    ScreenBacktestClient,
    ScreenBacktestResponse,
    UndecodedResponse,
)
from trialfolio.storage import ArtifactStore

_logger = logging.getLogger("trialfolio.attempts")

type Clock = Callable[[], datetime]
"""Gives the current time in UTC. Tests inject a fixed one."""

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of a screen run's start records and attempt records."""

EXPERIMENT_SCHEMA_VERSION: Final = "1.1.0"
"""The schema version of an experiment's start records and attempt records."""

RANKING_SCHEMA_VERSION: Final = "1.2.0"
"""The schema version of the start records and attempt records of a screen run's attempt that
sends a definition."""

RANKING_EXPERIMENT_SCHEMA_VERSION: Final = "1.3.0"
"""The schema version of the start records and attempt records of an experiment's attempt that
sends a definition."""

AUTHENTICATION_SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the authentication records an experiment's attempts write."""

type RankingOperation = Literal["rank_update", "screen_backtest"]


def utc_now() -> datetime:
    """The current time in UTC: the clock the installed command uses."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class AttemptResult:
    """How an attempt ended."""

    record: AttemptRecord | AttemptRecordV1_2
    """The attempt record: as written, or, when `recorded` is false, as it would have been. It's
    version 1.2.0 for an attempt that sends a definition."""
    recorded: bool
    """Whether `attempt.json` was written, or published whole before its write failed. If it
    wasn't, an attempt with a start record reads as `running`."""
    files: tuple[AttemptFile, ...]
    """Every file the attempt wrote, in order."""
    response: ScreenBacktestResponse | None
    """The saved response, exactly when the attempt succeeded. An undecoded one is a success for
    capture; normalizing it flags `provider.response_invalid`."""
    error: TrialFolioError | None
    """The error the command reports, or None. It's the record's, unless an interrupt or a storage
    failure decided the code, which it can even when the attempt succeeded."""


@dataclass(frozen=True)
class ExperimentAttemptResult:
    """How an experiment's attempt ended."""

    record: AttemptRecordV1_1 | AttemptRecordV1_3
    """The attempt record: as written, or, when `recorded` is false, as it would have been. It's
    version 1.3.0 for an attempt that sends a definition."""
    recorded: bool
    """Whether `attempt.json` was written, or published whole before its write failed. If it
    wasn't, an attempt with a start record reads as `running`, one with only its update record
    stopped during or after its `rank_update`, and one with only its authentication record
    stopped before its send."""
    start: StartRecordV1_1 | StartRecordV1_3 | None
    """The start record, `started.json`, when it was written."""
    files: tuple[AttemptFile, ...]
    """Every file the attempt wrote, in order."""
    response: ScreenBacktestResponse | None
    """The saved response, exactly when the attempt succeeded."""
    published: ScreenBacktestResponse | None
    """A response whose write failed after the store published it: `files` lists it, but the
    attempt record doesn't reference it, so the attempt is `unknown`. The session's manifest
    reads it all the same, for `return_series`."""
    error: TrialFolioError | None
    """The error the session reports for this attempt, or None. It's the record's, unless an
    interrupt or a storage failure decided the code."""
    authenticated: bool
    """Whether the attempt made Trial Folio's own authentication call, so the budget counts it."""
    authentication_failed: bool
    """Whether that call failed, whatever its result, which stops the session (D-32)."""
    update: StartRecordV1_3 | None = None
    """The update record, `updating.json`, of an attempt that sends a definition, when it was
    written."""
    update_saved: bool = False
    """Whether the `rank_update`'s response is in the attempt's directory, saved or published
    before its write failed, so an attempt whose latest record is its update record reads as a
    resume records it: `failed`, and otherwise `unknown`."""


class _Identity(TypedDict):
    """The fields every attempt's records share but `schema_version`, `case_id`, and an
    experiment's place in its session."""

    trialfolio_version: str
    attempt_id: uuid.UUID
    plan_hash: str
    started_at: datetime
    provider_wrapper: WrapperVersions
    transport: TransportVersions


class _AttemptBase[
    C: (str, None),
    S: (StartRecord, StartRecordV1_1, StartRecordV1_2, StartRecordV1_3),
    R: (AttemptRecord, AttemptRecordV1_1, AttemptRecordV1_2, AttemptRecordV1_3),
    T: (AttemptResult, ExperimentAttemptResult),
](ABC):
    """What every kind of attempt shares: its identity, its file writer and its ending policy,
    the guard that ends it once, the wrapper of its steps that records every ending, and the
    assembly of its ending. `C` is its case's ID, or None for a snapshot's, which plans no case;
    `S` and `R` are its start record and its attempt record; and `T` is what it returns.

    The plan must have been built in this process, from the installed versions: the records name
    its versions as the ones that sent the request. The properties stay readable whatever
    happens, so a command interrupted again while the attempt ends still knows its ID and what it
    wrote.
    """

    def __init__(
        self,
        plan: Plan | PlanV1_1 | PlanV1_2 | PlanV1_3 | RankingSnapshotPlan,
        plan_hash: str,
        case_id: C,
        store: ArtifactStore,
        *,
        clock: Clock,
        synthetic: bool,
        classify: Classifier,
        experiment: bool = False,
    ) -> None:
        """Starts the attempt: gives it an ID and its start time. Writes nothing.

        `classify` gives how its exchanges end it, and `experiment` is for an experiment's,
        whose ending's line names its case. Raises `ValueError` if `clock` doesn't give a UTC
        time.
        """
        attempt_id = uuid.uuid4()
        self._identity = _Identity(
            trialfolio_version=plan.trialfolio_version,
            attempt_id=attempt_id,
            plan_hash=plan_hash,
            started_at=utc(clock()),
            provider_wrapper=plan.provider_wrapper,
            transport=plan.transport,
        )
        self._case_id: C = case_id
        self._clock = clock
        self._directory = (
            snapshot_attempt_directory(attempt_id)
            if case_id is None
            else attempt_directory(case_id, attempt_id)
        )
        self._files = AttemptFiles(store, self._directory)
        self._synthetic = synthetic
        self._ending = AttemptEnding(
            self._files,
            self._log_fields,
            classify,
            synthetic=synthetic,
            experiment_case=case_id if experiment else None,
        )
        self._start: S | None = None
        self._update: S | None = None
        """The update record, for an attempt that sends a definition, once it's written."""
        self._first = 0
        self._ended = False
        _logger.info("Attempt started.", extra=self._log_fields("attempt.started"))

    @property
    def attempt_id(self) -> uuid.UUID:
        return self._identity["attempt_id"]

    @property
    def case_id(self) -> C:
        """The case's ID; None for a snapshot's attempt."""
        return self._case_id

    @property
    def plan_hash(self) -> str:
        return self._identity["plan_hash"]

    @property
    def started_at(self) -> datetime:
        return self._identity["started_at"]

    @property
    def directory(self) -> str:
        """`cases/<case_id>/attempts/<attempt_id>`, or a snapshot's `attempts/<attempt_id>`,
        relative to the output root."""
        return self._directory

    @property
    def files(self) -> tuple[AttemptFile, ...]:
        """Every file written so far, in order."""
        return self._files.files

    @property
    def start_record(self) -> S | None:
        """The start record, `started.json`, once it's written: the backtest's, for an attempt
        that sends a definition."""
        return self._start

    def _run(self, client: ScreenBacktestClient, steps: Callable[[], None]) -> T:
        """Ends the attempt, once, after its `steps`, whatever ended them, and records how it
        ended: every kind's `run`."""
        self._end_once()
        self._first = len(client.exchanges)
        ending: BaseException | None = None
        try:
            steps()
        except KeyboardInterrupt as interrupt:
            ending = interrupt
        # Every ending is recorded. An unexpected one is classified, and logged by its frames.
        except Exception as error:  # noqa: BLE001
            ending = error
        return self._end(self._exchanges(client), ending)

    def _exchanges(self, client: ScreenBacktestClient) -> tuple[Exchange, ...]:
        """The attempt's exchanges: the client's since `run` began, so an experiment's leave out
        its session's earlier attempts'."""
        return client.exchanges[self._first :]

    def _end_once(self) -> None:
        if self._ended:
            raise RuntimeError("an attempt ends once")
        self._ended = True

    def _write_start(self, start: S) -> None:
        """Writes the start record, the last write before the request's send. After a failure
        while it's written, whatever the failure, a record the store published counts as
        written, so the attempt record agrees with it."""

        def keep() -> None:
            self._start = start

        self._files.write_record(START_RECORD, start, "start_record", keep)

    def _write_before(self, operation: RankingOperation, record: S) -> None:
        """Writes the start record of `operation`, for an attempt that sends a definition, as
        `_write_start` writes it: the update record, `updating.json`, before the `rank_update`,
        and `started.json` before the backtest."""
        if operation == "screen_backtest":
            self._write_start(record)
            return

        def keep() -> None:
            self._update = record

        self._files.write_record(UPDATE_RECORD, record, "update_record", keep)

    def _send_definition(
        self,
        client: ScreenBacktestClient,
        params: tuple[dict[str, object], dict[str, object]],
        write_start: Callable[[RankingOperation], None],
        pause: Pause,
    ) -> None:
        """An authenticated attempt's sends of a definition (sending a definition): writes the
        `rank_update`'s request and its update record, sends it, and saves its response; then,
        only after a 200 the wrapper decoded, whose response was saved, waits until at least 10
        seconds have passed since that 200 arrived, on `pause`'s monotonic clock (D-45), writes
        the backtest's request and start record, sends it, and saves its response. A synthetic
        attempt, which sends nothing, doesn't wait. `write_start` writes the start record of the
        operation it's given, the last write before its send. `params` are the two requests'."""
        update, backtest = params
        self._files.write_rank_update_request(update)
        write_start("rank_update")
        _logger.info(
            "Writing the case's ranking definition into ApiRankingSystem with rank_update.",
            extra=self._log_fields("attempt.rank_update.started"),
        )
        response = client.rank_update(update)
        received = pause.monotonic()
        self._files.save_rank_update(response)
        if isinstance(response, UndecodedResponse):
            raise _undecoded_update()
        if not self._synthetic:
            self._wait_before_backtest(pause, received)
        self._files.write_request(backtest, list_published=True)
        write_start("screen_backtest")
        self._files.save(client.screen_backtest(backtest), list_published=True)

    def _wait_before_backtest(self, pause: Pause, received: float) -> None:
        """Waits until at least 10 seconds have passed since the `rank_update`'s 200 arrived, at
        `received` on `pause`'s monotonic clock, so Portfolio123 ranks the backtest by the
        definition just written (D-45). It says so first, as progress. Cancellation isn't
        checked here: an execution checks it only before an attempt, never between its two
        calls."""
        if pause.monotonic() - received >= UPDATE_PAUSE_SECONDS:
            return
        _logger.info(
            "Waiting %d seconds after the rank_update before sending the backtest, so"
            " Portfolio123 ranks by the definition just written.",
            UPDATE_PAUSE_SECONDS,
            extra=self._log_fields("attempt.backtest.waiting"),
        )
        pause.wait_from(received)

    def _end(self, exchanges: tuple[Exchange, ...], ending: BaseException | None) -> T:
        def record(end: Ending, error: TrialFolioError | None) -> R:
            return self._record(self._ending.fields(end, error, self._ended_at()), exchanges)

        written, recorded, error = self._ending.end(exchanges, ending, record)
        saved = self._files.response if written.outcome == "succeeded" else None
        return self._result(written, recorded, None if saved is None else saved[1], error)

    def _ended_at(self) -> datetime:
        """When the attempt ended, for its record: the clock's time, or its start time when the
        clock reads earlier, as after the wall clock moved backward during the attempt. An
        attempt record never ends before it starts, so it can still be written."""
        return max(utc(self._clock()), self.started_at)

    @abstractmethod
    def _record(self, fields: EndingFields, exchanges: tuple[Exchange, ...]) -> R:
        """The attempt record, with `fields`, which say how the attempt ended, and its
        `exchanges`."""

    @abstractmethod
    def _result(
        self,
        record: R,
        recorded: bool,
        response: ScreenBacktestResponse | None,
        error: TrialFolioError | None,
    ) -> T:
        """What `run` returns, from the attempt record, whether it was written, the saved
        response, exactly when the attempt succeeded, and the command's error."""

    def _log_fields(self, event: str) -> dict[str, str]:
        fields = {"event": event, "plan_hash": self.plan_hash}
        # A snapshot plans no case, and its logs never name its system (ranking snapshot output).
        if self._case_id is not None:
            fields["case_id"] = self._case_id
        fields["attempt_id"] = str(self.attempt_id)
        return fields


def _undecoded_update() -> ProviderError:
    """The ending of a `rank_update` that got a 200 the wrapper couldn't decode: its body is saved
    as it came, and the backtest isn't sent (sending a definition)."""
    return ProviderError(
        "provider.response_invalid",
        "Portfolio123 answered the rank_update request with a 200 whose body couldn't be decoded"
        f" as JSON, so it was saved as it came, as {RANK_UPDATE_RESPONSE_RAW}. The request may"
        " have been charged. That request writes the case's ranking definition into"
        " ApiRankingSystem, and Trial Folio sends the case's screen backtest only after one whose"
        " response it could read, so the backtest wasn't sent. Report the problem if it persists.",
    )


# A screen run's attempt, and a ranking snapshot's


class _RunAttempt[
    C: (str, None),
    S: (StartRecord, StartRecordV1_2),
    R: (AttemptRecord, AttemptRecordV1_2),
](_AttemptBase[C, S, R, AttemptResult]):
    """A screen run's attempt, or a snapshot's: its command's one attempt, writing into its
    claimed output directory, with a new client of its own, which it authenticates first."""

    def run(self, client: ScreenBacktestClient) -> AttemptResult:
        """Authenticates, sends the attempt's requests, each once, with their files, as the
        package says, and writes the attempt record.

        `client` must be new: its exchanges are the attempt's. Raises `RuntimeError` if the
        attempt has already ended or the client has made an exchange, and `KeyboardInterrupt`
        only as the package says.
        """
        if client.exchanges:
            raise RuntimeError("an attempt needs a new client: its exchanges are the attempt's")

        def steps() -> None:
            client.authenticate()
            self._send(client)

        return self._run(client, steps)

    def end_before_authenticating(self, ending: BaseException) -> AttemptResult:
        """Writes the attempt record of an attempt that ended after the claim and before it
        authenticated, as `failed`, not possibly charged: for example after an interrupt, or a
        failure to write `configuration.yaml` (interrupts).

        `ending` gives the error: `command.interrupted` for a `KeyboardInterrupt`, the code of a
        `TrialFolioError`, and `internal.unexpected` for anything else. Raises `RuntimeError` if
        the attempt has already ended, and `KeyboardInterrupt` only as the package says.
        """
        self._end_once()
        return self._end((), ending)

    @abstractmethod
    def _send(self, client: ScreenBacktestClient) -> None:
        """Sends the attempt's requests, with their files, once it has authenticated."""

    def _result(
        self,
        record: R,
        recorded: bool,
        response: ScreenBacktestResponse | None,
        error: TrialFolioError | None,
    ) -> AttemptResult:
        return AttemptResult(
            record=record, recorded=recorded, files=self.files, response=response, error=error
        )


class Attempt(_RunAttempt[str, StartRecord, AttemptRecord]):
    """One attempt of the case of an approved plan, writing into a claimed output directory, with
    start and attempt records 1.0.0: it writes the redacted request, then the start record, sends
    the request, and saves its response, as the package says."""

    def __init__(
        self,
        plan: Plan,
        approved_hash: str,
        store: ArtifactStore,
        *,
        clock: Clock = utc_now,
        synthetic: bool = False,
    ) -> None:
        """Starts the attempt: gives it an ID and its start time. Writes nothing.

        `synthetic` is for the attempt of the run `trialfolio demo` writes, which sends nothing.
        Its records are a real attempt's. Where they say it's possibly charged, its progress says
        they're invented.

        Raises `TrialFolioError` with `plan.approval_required` unless `approved_hash` is the
        plan's hash, recomputed from its contents (approval), and `ValueError` if `clock` doesn't
        give a UTC time.
        """
        plan_hash = check_approval(plan, approved_hash)
        (case,) = plan.cases
        (request,) = case.requests
        super().__init__(
            plan,
            plan_hash,
            case.case_id,
            store,
            clock=clock,
            synthetic=synthetic,
            classify=one_request_ending,
        )
        self._params: dict[str, object] = request.params.model_dump(mode="json")

    def _send(self, client: ScreenBacktestClient) -> None:
        self._files.write_request(self._params, list_published=True)
        # Exactly the authentication exchange; the model refuses anything else.
        exchanges = cast("tuple[Exchange]", self._exchanges(client))
        self._write_start(
            StartRecord(
                schema_version=SCHEMA_VERSION,
                case_id=self.case_id,
                **self._identity,
                exchanges=exchanges,
            )
        )
        self._files.save(client.screen_backtest(self._params), list_published=True)

    def _record(self, fields: EndingFields, exchanges: tuple[Exchange, ...]) -> AttemptRecord:
        return AttemptRecord(
            schema_version=SCHEMA_VERSION,
            case_id=self.case_id,
            **self._identity,
            **fields,
            exchanges=exchanges,
        )


class RankingAttempt(_RunAttempt[str, StartRecordV1_2, AttemptRecordV1_2]):
    """One attempt of the case of an approved plan 1.2.0, a screen run's whose ranking is a
    definition, writing into a claimed output directory. It sends the `rank_update` that writes
    the case's definition into `ApiRankingSystem`, then the backtest, as the package says, with
    start and attempt records 1.2.0, and ends as an `Attempt` does. The run holds the ranking lock
    meanwhile."""

    def __init__(
        self,
        plan: PlanV1_2,
        approved_hash: str,
        store: ArtifactStore,
        *,
        clock: Clock = utc_now,
        synthetic: bool = False,
        pause: Pause = REAL_PAUSE,
    ) -> None:
        """Starts the attempt: gives it an ID and its start time. Writes nothing.

        `synthetic` is for a run the core writes with the demo's client, which sends nothing, and
        doesn't wait. `pause` is the wait between the `rank_update`'s 200 and the backtest, which
        tests inject, as they do the clock. Raises as `Attempt` does.
        """
        plan_hash = check_approval(plan, approved_hash)
        (case,) = plan.cases
        update, backtest = case.requests
        super().__init__(
            plan,
            plan_hash,
            case.case_id,
            store,
            clock=clock,
            synthetic=synthetic,
            classify=ranking_ending,
        )
        self._params = (
            update.params.model_dump(mode="json"),
            backtest.params.model_dump(mode="json"),
        )
        self._pause = pause

    @property
    def update_record(self) -> StartRecordV1_2 | None:
        """The update record, `updating.json`, once it's written."""
        return self._update

    def _send(self, client: ScreenBacktestClient) -> None:
        def write_start(operation: RankingOperation) -> None:
            record = StartRecordV1_2(
                schema_version=RANKING_SCHEMA_VERSION,
                case_id=self.case_id,
                **self._identity,
                operation=operation,
                exchanges=self._exchanges(client),
            )
            self._write_before(operation, record)

        self._send_definition(client, self._params, write_start, self._pause)

    def _record(self, fields: EndingFields, exchanges: tuple[Exchange, ...]) -> AttemptRecordV1_2:
        return AttemptRecordV1_2(
            schema_version=RANKING_SCHEMA_VERSION,
            case_id=self.case_id,
            **self._identity,
            operation="screen_backtest",
            **fields,
            exchanges=exchanges,
            ranking_update=self._files.ranking_update(),
        )


class SnapshotAttempt(_RunAttempt[None, StartRecordV1_2, AttemptRecordV1_2]):
    """A ranking snapshot's one attempt, under its approved plan, writing into its claimed
    directory, in `attempts/<attempt_id>/`: an `Attempt`'s steps, with the `rank_get` that reads
    the ranking system its configuration names as its request, and start and attempt records
    1.2.0 with `operation` `rank_get` and no case (ranking snapshot output). It ends as an
    `Attempt` does, and writes nothing to the account."""

    def __init__(
        self,
        plan: RankingSnapshotPlan,
        approved_hash: str,
        store: ArtifactStore,
        *,
        clock: Clock = utc_now,
        synthetic: bool = False,
    ) -> None:
        """Starts the attempt: gives it an ID and its start time. Writes nothing.

        `synthetic` is for a snapshot the core takes with the demo's client, which sends nothing.
        Raises as `Attempt` does.
        """
        plan_hash = check_approval(plan, approved_hash)
        (request,) = plan.requests
        super().__init__(
            plan, plan_hash, None, store, clock=clock, synthetic=synthetic, classify=snapshot_ending
        )
        self._params: dict[str, object] = request.params.model_dump(mode="json")

    def _send(self, client: ScreenBacktestClient) -> None:
        self._files.write_request(self._params, list_published=True)
        self._write_start(
            StartRecordV1_2(
                schema_version=RANKING_SCHEMA_VERSION,
                case_id=None,
                **self._identity,
                operation="rank_get",
                exchanges=self._exchanges(client),
            )
        )
        name = cast("str", self._params["name"])
        self._files.save(client.rank_get(name), list_published=True)

    def _record(self, fields: EndingFields, exchanges: tuple[Exchange, ...]) -> AttemptRecordV1_2:
        return AttemptRecordV1_2(
            schema_version=RANKING_SCHEMA_VERSION,
            case_id=None,
            **self._identity,
            operation="rank_get",
            **fields,
            exchanges=exchanges,
            ranking_update=None,
        )


# An experiment's attempt


class _Placed(_Identity):
    """The fields an experiment's records share but `schema_version`, `operation`, and
    `authenticated_by`: the attempt, its plan, and its place in its session."""

    case_id: str
    session: int
    sequence: int
    repeat_of: uuid.UUID | None


class _SessionAttempt[
    S: (StartRecordV1_1, StartRecordV1_3),
    R: (AttemptRecordV1_1, AttemptRecordV1_3),
](_AttemptBase[str, S, R, ExperimentAttemptResult]):
    """One attempt of an experiment's case, in a session that holds the experiment lock
    (docs/contracts.md, experiment attempts).

    A session authenticates once, and again only after a 401 or 403 drops its token, so the
    session's attempts share one client: an attempt sends with the token an earlier attempt
    obtained, or authenticates first, writing its authentication record, `authenticating.json`,
    durably before the call, so the budget counts the call even if the process is killed during
    it. It then writes its files in its kind's order, and `attempt.json` whatever ended it. An
    `ExperimentAttempt`'s are a run's: `request.json`, `started.json`, and the response. A
    `RankingExperimentAttempt` writes its `rank_update`'s first, `rank-update-request.json`,
    `updating.json`, and the response, then, only after a 200 the wrapper decoded, the
    backtest's, as a run's (sending a definition). Its records name its session, its place in
    the session, `sequence`, the attempt whose authentication gave its token, `authenticated_by`,
    and the attempt a repeat repeats, `repeat_of`.

    A file before the attempt record that the store published before its write failed, whatever
    the failure, is in `files` all the same, so the session's manifest lists every file the
    attempt wrote. The attempt record references a request or a response only when its write
    completed, so a 200 whose `response.json` was published that way is `unknown`, as one whose
    save failed.
    """

    def __init__(
        self,
        plan: PlanV1_1 | PlanV1_3,
        case: ExperimentPlanCase | ExperimentPlanCaseV1_3,
        store: ArtifactStore,
        *,
        session: int,
        sequence: int,
        repeat_of: uuid.UUID | None,
        clock: Clock,
        synthetic: bool,
        classify: Classifier,
    ) -> None:
        """Starts the attempt, as an `ExperimentAttempt` does, with `classify`, which gives how
        its exchanges end it."""
        if case not in plan.cases:
            raise ValueError("the attempt's case is one of the plan's")
        super().__init__(
            plan,
            plan.plan_hash,
            case.case_id,
            store,
            clock=clock,
            synthetic=synthetic,
            classify=classify,
            experiment=True,
        )
        self._placed = _Placed(
            **self._identity,
            case_id=case.case_id,
            session=session,
            sequence=sequence,
            repeat_of=repeat_of,
        )
        self._authenticated = False
        self._authentication_failed = False

    def run(
        self, client: ScreenBacktestClient, token_from: uuid.UUID | None
    ) -> ExperimentAttemptResult:
        """Sends the case's requests, each once, with the session's `client`, and records the
        attempt.

        `token_from` is the attempt whose successful authentication gave the token the client
        holds, or None when it holds none: the attempt then authenticates first. Raises
        `RuntimeError` if the attempt has already ended, or `token_from` is given while the
        client holds no token; and `KeyboardInterrupt` only while the attempt record is written
        once more after an interrupt, as an `Attempt` does.
        """
        if token_from is not None and not client.authenticated:
            raise RuntimeError("the client holds no token to send with")

        def steps() -> None:
            by = token_from
            if by is None:
                self._authenticate(client)
                by = self.attempt_id
            self._send(client, by)

        return self._run(client, steps)

    @abstractmethod
    def _send(self, client: ScreenBacktestClient, token_from: uuid.UUID) -> None:
        """Sends the case's requests, with their files, with the token whose authentication the
        attempt `token_from` made."""

    def _authenticate(self, client: ScreenBacktestClient) -> None:
        """Writes the authentication record durably, then makes Trial Folio's own
        authentication call."""
        placed = self._placed
        record = AuthenticationRecord(
            schema_version=AUTHENTICATION_SCHEMA_VERSION,
            trialfolio_version=placed["trialfolio_version"],
            attempt_id=placed["attempt_id"],
            case_id=placed["case_id"],
            plan_hash=placed["plan_hash"],
            session=placed["session"],
            sequence=placed["sequence"],
            repeat_of=placed["repeat_of"],
            started_at=placed["started_at"],
        )
        self._files.write(
            AUTHENTICATION_RECORD, model_json(record), "authentication_record", list_published=True
        )
        self._authenticated = True
        try:
            client.authenticate()
        except Exception:
            self._authentication_failed = True
            raise

    def _result(
        self,
        record: R,
        recorded: bool,
        response: ScreenBacktestResponse | None,
        error: TrialFolioError | None,
    ) -> ExperimentAttemptResult:
        return ExperimentAttemptResult(
            record=record,
            recorded=recorded,
            start=self._start,
            files=self.files,
            response=response,
            published=self._files.published_response,
            error=error,
            authenticated=self._authenticated,
            authentication_failed=self._authentication_failed,
        )


class ExperimentAttempt(_SessionAttempt[StartRecordV1_1, AttemptRecordV1_1]):
    """One attempt of an experiment's case, with start and attempt records 1.1.0: it
    authenticates, or sends with its session's token, then writes the redacted request and its
    start record, sends the request, and saves its response, as `_SessionAttempt` says. The
    properties stay readable whatever happens, as an `Attempt`'s do."""

    def __init__(
        self,
        plan: PlanV1_1,
        case: ExperimentPlanCase,
        store: ArtifactStore,
        *,
        session: int,
        sequence: int,
        repeat_of: uuid.UUID | None = None,
        clock: Clock = utc_now,
        synthetic: bool = False,
    ) -> None:
        """Starts the attempt of `case`, one of the approved `plan`'s cases, as the `sequence`th
        attempt of `session`: gives it an ID and its start time. Writes nothing.

        `repeat_of` is the attempt a confirmed repeat names, and `synthetic` is for an
        experiment executed with the demo's client, which sends nothing. Raises `ValueError` if
        `case` isn't one of the plan's, or `clock` doesn't give a UTC time.
        """
        super().__init__(
            plan,
            case,
            store,
            session=session,
            sequence=sequence,
            repeat_of=repeat_of,
            clock=clock,
            synthetic=synthetic,
            classify=one_request_ending,
        )
        (request,) = case.requests
        self._params: dict[str, object] = request.params.model_dump(mode="json")

    def _send(self, client: ScreenBacktestClient, token_from: uuid.UUID) -> None:
        self._files.write_request(self._params, list_published=True)
        start = StartRecordV1_1(
            schema_version=EXPERIMENT_SCHEMA_VERSION,
            **self._placed,
            authenticated_by=token_from,
            exchanges=self._exchanges(client),
        )
        self._write_start(start)
        self._files.save(client.screen_backtest(self._params), list_published=True)

    def _record(self, fields: EndingFields, exchanges: tuple[Exchange, ...]) -> AttemptRecordV1_1:
        return AttemptRecordV1_1(
            schema_version=EXPERIMENT_SCHEMA_VERSION,
            **self._placed,
            authenticated_by=None if self._start is None else self._start.authenticated_by,
            **fields,
            exchanges=exchanges,
        )


class RankingExperimentAttempt(_SessionAttempt[StartRecordV1_3, AttemptRecordV1_3]):
    """One attempt of an experiment's case whose ranking is a definition, under a plan 1.3.0, in
    a session that holds the experiment lock and the ranking lock. It authenticates, or sends with
    its session's token, as an `ExperimentAttempt` does, then sends the `rank_update` that writes
    the case's definition into `ApiRankingSystem`, then the backtest, as the package says, with
    start and attempt records 1.3.0. The properties stay readable whatever happens."""

    def __init__(
        self,
        plan: PlanV1_3,
        case: ExperimentPlanCaseV1_3,
        store: ArtifactStore,
        *,
        session: int,
        sequence: int,
        repeat_of: uuid.UUID | None = None,
        clock: Clock = utc_now,
        synthetic: bool = False,
        pause: Pause = REAL_PAUSE,
    ) -> None:
        """Starts the attempt, as an `ExperimentAttempt` does, with `pause`, the wait between
        the `rank_update`'s 200 and the backtest, as a `RankingAttempt` takes it. Writes nothing.
        Raises as an `ExperimentAttempt` does."""
        super().__init__(
            plan,
            case,
            store,
            session=session,
            sequence=sequence,
            repeat_of=repeat_of,
            clock=clock,
            synthetic=synthetic,
            classify=ranking_ending,
        )
        update, backtest = case.requests
        self._params = (
            update.params.model_dump(mode="json"),
            backtest.params.model_dump(mode="json"),
        )
        self._pause = pause

    @property
    def update_record(self) -> StartRecordV1_3 | None:
        """The update record, `updating.json`, once it's written."""
        return self._update

    def _send(self, client: ScreenBacktestClient, token_from: uuid.UUID) -> None:
        def write_start(operation: RankingOperation) -> None:
            record = StartRecordV1_3(
                schema_version=RANKING_EXPERIMENT_SCHEMA_VERSION,
                **self._placed,
                operation=operation,
                authenticated_by=token_from,
                exchanges=self._exchanges(client),
            )
            self._write_before(operation, record)

        self._send_definition(client, self._params, write_start, self._pause)

    def _record(self, fields: EndingFields, exchanges: tuple[Exchange, ...]) -> AttemptRecordV1_3:
        return AttemptRecordV1_3(
            schema_version=RANKING_EXPERIMENT_SCHEMA_VERSION,
            **self._placed,
            operation="screen_backtest",
            authenticated_by=None if self._update is None else self._update.authenticated_by,
            **fields,
            exchanges=exchanges,
            ranking_update=self._files.ranking_update(),
        )

    def _result(
        self,
        record: AttemptRecordV1_3,
        recorded: bool,
        response: ScreenBacktestResponse | None,
        error: TrialFolioError | None,
    ) -> ExperimentAttemptResult:
        return replace(
            super()._result(record, recorded, response, error),
            update=self._update,
            update_saved=self._files.rank_update_saved,
        )
