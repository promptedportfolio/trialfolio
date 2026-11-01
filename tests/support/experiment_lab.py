"""The experiment lab: runs an experiment through the core, as another interface would, with no
CLI, new and then resumed, into one output directory, over the fake Portfolio123 server or with the
demo's client; and reads what it wrote.

Each run reads and plans the configuration as a release does (`Reader`). `RELEASE_0_3_0` reads it
through `read_experiment_configuration` and `build_experiment_plan`, which still serve a plan
without a ranking definition, and opens the records as 0.3.0 does, which reads 0.3.0's versions
only. `RELEASE_0_4_0` reads it through 0.4.0's reader and planner, which give a plan 1.3.0 for a
ranking definition or a snapshot, whose bytes the session is given, and opens the records with
`ranking`. A resume plans the configuration again, and runs the current plan, or the revision it
gives.

A run's store is the real one, wrapped in storage faults when the lab has a `monkeypatch`, which the
test can arm before the run, and which records each file the store publishes. The real client,
`requests`, and `urllib3` send to the fake server with the canary credentials, unless the run is
synthetic. The clock is fixed. The ranking lock's file is in the test's directory, given exactly
for a plan 1.3.0, and the pause is `no_wait()`, unless the test gives its own.

A `TrialFolioError` a run raises propagates, as it did from eight of the ten drivers, whether it's
raised while the records are read, while the execution is built, or by the session, such as the
claim's `output.not_empty`: so a test that expects one catches it, and a test fails when an error
the session returns, such as `storage.write_failed`, is raised instead. A lab made with `catch`, as
the resume modules' are, gives it as the run's error, as their `Lab`s did, so a test reads a
refusal as it reads the session's own error, without telling the two apart.

The readers of what it wrote take the model each record is read with, such as `AttemptRecordV1_1`
or `AttemptRecordV1_3`, which pins its `schema_version`, as `saved_records.py`'s do.

TS-T04 wrote it once, from the ten drivers of nine core modules: the `Lab`s of
`tests/core/test_experiment_resume.py`, `test_ranking_resume.py`, and `test_stale_backtests.py`;
`Experiments` in `test_experiment_execution.py`, and `Experiment` in `test_experiment_report.py`;
`run_experiment` in `test_ranking_execution.py` and `test_ranking_pause.py`; `write_experiment` and
`write_synthetic_sessions` in `test_ranking_report.py`; and `new_experiment` in
`test_ranking_snapshot.py`. It keeps what only one of them had: the reader as a parameter; the
events, a progress callback, and a cancellation; the synthetic client and its response; the
approval, its hash, and the command; the store's wrapper; and the ranking lock and the pause.

`unknown_baseline` runs `default-only.yaml` so that its baseline awaits a repeat. TS-T07 moved it
here from tests/core/test_experiment_resume.py, whose repeats and records check, now
tests/core/test_experiment_records.py, both use it.
"""

import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import pytest
from pydantic import BaseModel

from tests.support.clock import FixedClock, no_wait
from tests.support.fake_portfolio123 import (
    AUTHENTICATED,
    BACKTEST,
    CREDENTIALS,
    FakePortfolio123,
    Received,
    Reply,
    response,
)
from tests.support.paths import EXPERIMENT_CONFIGS
from tests.support.plans import Planned, experiment_plan, planned_experiment, with_ranking
from tests.support.saved_records import attempt_directories, attempt_records, session_manifest
from tests.support.storage_faults import StorageFaults
from trialfolio.configuration import (
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
)
from trialfolio.contracts.attempt import AttemptRecordV1_1, AttemptRecordV1_3
from trialfolio.contracts.common import Approval
from trialfolio.contracts.experiment_manifest import ExperimentCommandRecord
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.demo import SyntheticScreenBacktestClient, response_bytes
from trialfolio.errors import TrialFolioError
from trialfolio.experiment_execution import (
    AttemptEnded,
    Cancellation,
    ExperimentExecution,
    ProgressEvent,
)
from trialfolio.experiment_records import SavedExperiment, open_experiment, read_experiment
from trialfolio.experiment_repeats import Repeat
from trialfolio.pause import Pause
from trialfolio.planning import (
    build_experiment_plan,
    installed_versions,
    plan_revision,
    plan_revision_v1_1,
)
from trialfolio.provider import P123ScreenBacktestClient, ScreenBacktestClient
from trialfolio.ranking_lock import LOCK_FILE
from trialfolio.storage import LOCK_PATH, ArtifactStore, LocalArtifactStore

type AnyPlan = PlanV1_1 | PlanV1_3
type Arm = Callable[[StorageFaults], object]
"""Sets up the storage faults of a run's store, before the run."""
type Wrap = Callable[[LocalArtifactStore], StorageFaults]
"""Wraps a run's real store in storage faults of the test's own, such as a subclass."""


class Reader(Protocol):
    """How a release reads an experiment configuration, plans it, and opens an experiment's
    records."""

    example: str
    """The name of the configuration in `experiment-configs/` that its tests run by default."""

    def plan(self, content: bytes, path: Path, source: str) -> Planned[AnyPlan]:
        """The plan of a new experiment of the configuration `content`, read from `path` under the
        name `source`."""
        ...

    def resumed(
        self, content: bytes, path: Path, source: str, saved: SavedExperiment
    ) -> Planned[AnyPlan]:
        """The plan a resume of `saved` with the configuration `content` runs: its current plan,
        or the revision the configuration gives."""
        ...

    def open(self, store: ArtifactStore) -> SavedExperiment:
        """The experiment's records, read and checked while taking its lock, to resume it."""
        ...

    def read(self, store: ArtifactStore) -> SavedExperiment:
        """The experiment's records, read and checked, as `trialfolio report` reads them."""
        ...


class _Release030:
    example = "example.yaml"

    def plan(self, content: bytes, path: Path, source: str) -> Planned[AnyPlan]:
        configuration = read_experiment_configuration(content, source)
        return Planned(content, build_experiment_plan(configuration, installed_versions()))

    def resumed(
        self, content: bytes, path: Path, source: str, saved: SavedExperiment
    ) -> Planned[AnyPlan]:
        configuration = read_experiment_configuration(content, source)
        revision = plan_revision(configuration, installed_versions(), saved.plan)
        return Planned(content, saved.plan if revision is None else revision.plan)

    def open(self, store: ArtifactStore) -> SavedExperiment:
        return open_experiment(store)

    def read(self, store: ArtifactStore) -> SavedExperiment:
        return read_experiment(store)


class _Release040:
    example = "ranking-example.yaml"

    def plan(self, content: bytes, path: Path, source: str) -> Planned[AnyPlan]:
        return planned_experiment(path, content=content, source=source)

    def resumed(
        self, content: bytes, path: Path, source: str, saved: SavedExperiment
    ) -> Planned[AnyPlan]:
        read = read_experiment_configuration_v1_1(content, source, path)
        revision = plan_revision_v1_1(read, installed_versions(), saved.current.plan)
        return with_ranking(
            content, read, saved.current.plan if revision is None else revision.plan
        )

    def open(self, store: ArtifactStore) -> SavedExperiment:
        return open_experiment(store, ranking=True)

    def read(self, store: ArtifactStore) -> SavedExperiment:
        return read_experiment(store, ranking=True)


RELEASE_0_3_0: Final[Reader] = _Release030()
RELEASE_0_4_0: Final[Reader] = _Release040()


class Records:
    """Readers of the experiment in `out`, each with the model the test gives."""

    out: Path

    def manifest[M: BaseModel](self, session: int, model: type[M]) -> M:
        """The manifest of the session `session`."""
        return session_manifest(self.out, session, model)

    def attempts[R: (AttemptRecordV1_1, AttemptRecordV1_3)](
        self, case_id: str, model: type[R]
    ) -> list[R]:
        """The case's attempt records, by session and then sequence."""
        return attempt_records(self.out, case_id, model)

    def record[R: (AttemptRecordV1_1, AttemptRecordV1_3)](self, case_id: str, model: type[R]) -> R:
        """The attempt record of the case's one attempt."""
        return model.model_validate_json((self.attempt(case_id) / "attempt.json").read_bytes())

    def attempt_directories(self, case_id: str) -> list[Path]:
        """The directories of the case's attempts, by name."""
        return attempt_directories(self.out, case_id)

    def attempt(self, case_id: str) -> Path:
        """The directory of the case's one attempt."""
        (directory,) = self.attempt_directories(case_id)
        return directory

    def tables(self, case_id: str) -> Path:
        """The directory of the case's normalized tables."""
        return self.out / "cases" / case_id / "normalized"

    def json(self, path: str) -> dict[str, object]:
        return json.loads((self.out / path).read_bytes())


@dataclass(frozen=True)
class Ran(Records):
    """One session of the experiment, new or resumed, and what it sent and wrote."""

    out: Path
    planned: AnyPlan | None
    """The plan the session ran; None when the run was refused before its plan was read."""
    error: TrialFolioError | None
    """The error the session returned, None when every planned case succeeded; or, in a lab made
    with `catch`, the error the run raised."""
    execution: ExperimentExecution | None
    """None when the run was refused before its execution was built."""
    requests: tuple[Received, ...]
    """The requests the fake server received during the run, in order."""
    events: tuple[ProgressEvent, ...]
    published: tuple[str, ...]
    """Each file the run's store published, in order, when it had storage faults."""

    @property
    def received(self) -> tuple[str, ...]:
        """Each request the fake server received during the run, as its method and path."""
        return tuple(request.request for request in self.requests)

    @property
    def bodies(self) -> tuple[dict[str, object], ...]:
        """The body of each backtest the fake server received during the run, in order."""
        return tuple(json.loads(r.body) for r in self.requests if r.request == BACKTEST)

    @property
    def plan(self) -> AnyPlan:
        """The plan the session ran, which must have been read."""
        assert self.planned is not None, self.error
        return self.planned

    @property
    def executed(self) -> ExperimentExecution:
        """The execution, which must have been built."""
        assert self.execution is not None, self.error
        return self.execution

    def refused(self, code: str) -> TrialFolioError:
        """The run's error, which must have `code`."""
        error = self.error
        assert error is not None and error.code == code, error
        return error

    @property
    def outcomes(self) -> list[str]:
        """Each case's outcome, in the plan's order, as the session ended it."""
        return [outcome for _, outcome in self.executed.outcomes]


class Lab(Records):
    """Runs one experiment into one output directory, `<tmp>/experiment`, new and then resumed,
    through the core, over the fake server, as the module says. With `catch`, a `TrialFolioError`
    a run raises is its error, rather than propagating."""

    def __init__(
        self,
        tmp: Path,
        server: FakePortfolio123 | None = None,
        monkeypatch: pytest.MonkeyPatch | None = None,
        *,
        reader: Reader = RELEASE_0_4_0,
        catch: bool = False,
    ) -> None:
        self.out = tmp / "experiment"
        self.lock = tmp / LOCK_FILE
        """The ranking lock's file, which a plan 1.3.0's session takes."""
        self._server = server
        self.reader = reader
        self._monkeypatch = monkeypatch
        self._catch = catch

    @property
    def server(self) -> FakePortfolio123:
        """The fake server, which a lab that runs only synthetic experiments needn't have."""
        assert self._server is not None, "a run that isn't synthetic needs the fake server"
        return self._server

    def new(
        self,
        configuration: str | Path | None = None,
        *,
        content: bytes | None = None,
        source: str | None = None,
        plan: AnyPlan | None = None,
        approve: str | None = None,
        approval: Approval | None = None,
        synthetic: bool = False,
        invented: bytes | None = None,
        cancel_after: int | None = None,
        cancellation: Cancellation | None = None,
        progress: Callable[[ProgressEvent], object] | None = None,
        arm: Arm | None = None,
        wrap: Wrap | None = None,
        pause: Pause | None = None,
    ) -> Ran:
        """Runs a new experiment of `configuration`, a name in `experiment-configs/` or a path,
        the reader's example by default: of its bytes, or of `content` in their place, read under
        its file's name, or `source`. `plan`, when it's given, is the plan 1.1.0 the test built
        from them, which the session runs. It's approved with the plan's hash, or `approve`, as
        `approval` gives, `option` by default, or `not_required` for a synthetic experiment,
        which the demo's client runs, answering each backtest with `invented`, the demo's
        response by default. The session is cancelled once `cancel_after` attempts have ended,
        or as `cancellation` is; `progress` is called with each event, after the lab records it.
        `arm` sets up the store's storage faults, which `wrap` makes, when it's given."""
        path, content, source = self._configuration(configuration, content, source)

        def planned(store: ArtifactStore) -> tuple[Planned[AnyPlan], SavedExperiment | None]:
            if plan is None:
                return self.reader.plan(content, path, source), None
            return Planned(content, plan), None

        return self._run(
            planned,
            approve=approve,
            approval=approval,
            synthetic=synthetic,
            invented=invented,
            cancel_after=cancel_after,
            cancellation=cancellation,
            progress=progress,
            arm=arm,
            wrap=wrap,
            pause=pause,
        )

    def resume(
        self,
        configuration: str | Path | None = None,
        *,
        content: bytes | None = None,
        source: str | None = None,
        approve: str | None = None,
        approval: Approval | None = None,
        reason: str | None = None,
        repeats: Sequence[Repeat] = (),
        command: ExperimentCommandRecord | None = None,
        synthetic: bool = False,
        invented: bytes | None = None,
        cancel_after: int | None = None,
        progress: Callable[[ProgressEvent], object] | None = None,
        arm: Arm | None = None,
        wrap: Wrap | None = None,
        pause: Pause | None = None,
    ) -> Ran:
        """Resumes the experiment in the output directory, or revises it, with `configuration`,
        as `new` reads it: its records are read and checked under its lock, and the session runs
        the current plan, or the revision the configuration gives, with `reason`, the confirmed
        `repeats`, and `command`, the `trialfolio` command that runs it, None by default, as for
        another interface. The rest is as for `new`."""
        path, content, source = self._configuration(configuration, content, source)

        def planned(store: ArtifactStore) -> tuple[Planned[AnyPlan], SavedExperiment | None]:
            saved = self.reader.open(store)
            return self.reader.resumed(content, path, source, saved), saved

        return self._run(
            planned,
            approve=approve,
            approval=approval,
            reason=reason,
            repeats=repeats,
            command=command,
            synthetic=synthetic,
            invented=invented,
            cancel_after=cancel_after,
            progress=progress,
            arm=arm,
            wrap=wrap,
            pause=pause,
        )

    def run(
        self,
        configuration: str | Path | None = None,
        *,
        reason: str | None = None,
        repeats: Sequence[Repeat] = (),
        synthetic: bool = False,
        invented: bytes | None = None,
        cancellation: Cancellation | None = None,
        arm: Arm | None = None,
        pause: Pause | None = None,
    ) -> Ran:
        """A new experiment of `configuration`, as `new` runs it, or, when the output directory
        holds an experiment, a resume or revision of it, as `resume` runs it."""
        if not (self.out / LOCK_PATH).exists():
            return self.new(
                configuration,
                synthetic=synthetic,
                invented=invented,
                cancellation=cancellation,
                arm=arm,
                pause=pause,
            )
        return self.resume(
            configuration,
            reason=reason,
            repeats=repeats,
            synthetic=synthetic,
            invented=invented,
            arm=arm,
            pause=pause,
        )

    def read(self) -> SavedExperiment:
        """The experiment's records, read and checked as the lab's reader reads them."""
        with LocalArtifactStore(self.out) as store:
            return self.reader.read(store)

    def _configuration(
        self, configuration: str | Path | None, content: bytes | None, source: str | None
    ) -> tuple[Path, bytes, str]:
        path = EXPERIMENT_CONFIGS / (configuration or self.reader.example)
        return path, path.read_bytes() if content is None else content, source or path.name

    def _run(
        self,
        planned: Callable[[ArtifactStore], tuple[Planned[AnyPlan], SavedExperiment | None]],
        *,
        approve: str | None,
        approval: Approval | None,
        reason: str | None = None,
        repeats: Sequence[Repeat] = (),
        command: ExperimentCommandRecord | None = None,
        synthetic: bool,
        invented: bytes | None,
        cancel_after: int | None,
        cancellation: Cancellation | None = None,
        progress: Callable[[ProgressEvent], object] | None,
        arm: Arm | None,
        wrap: Wrap | None,
        pause: Pause | None,
    ) -> Ran:
        before = 0 if self._server is None else len(self._server.received)
        events: list[ProgressEvent] = []
        cancellation = cancellation or Cancellation()

        def record(event: ProgressEvent) -> None:
            events.append(event)
            if progress is not None:
                progress(event)
            ended = sum(isinstance(e, AttemptEnded) for e in events)
            if isinstance(event, AttemptEnded) and ended == cancel_after:
                cancellation.cancel()

        real = LocalArtifactStore(self.out)
        store: ArtifactStore = real
        if wrap is not None:
            store = wrap(real)
        elif self._monkeypatch is not None:
            store = StorageFaults(real, self._monkeypatch)
        if arm is not None:
            assert isinstance(store, StorageFaults), "arming storage faults needs a monkeypatch"
            arm(store)
        client = self._client(synthetic, invented)
        plan: AnyPlan | None = None
        execution: ExperimentExecution | None = None
        try:
            given, saved = planned(store)
            plan = given.plan
            execution = ExperimentExecution(
                plan,
                plan.plan_hash if approve is None else approve,
                approval or ("not_required" if synthetic else "option"),
                store,
                client,
                command=command,
                clock=FixedClock(),
                progress=record,
                cancellation=cancellation,
                experiment=saved,
                reason=reason,
                repeats=repeats,
                ranking_lock=self.lock if isinstance(plan, PlanV1_3) else None,
                pause=no_wait() if pause is None else pause,
            )
            error = execution.run(
                given.content, definition=given.definition, snapshot=given.snapshot
            )
        except TrialFolioError as refused:
            if not self._catch:
                raise
            error = refused
        finally:
            client.close()
            real.close()
        requests = () if self._server is None else self._server.received[before:]
        published = tuple(store.published) if isinstance(store, StorageFaults) else ()
        return Ran(self.out, plan, error, execution, requests, tuple(events), published)

    def _client(self, synthetic: bool, invented: bytes | None) -> ScreenBacktestClient:
        if synthetic:
            return SyntheticScreenBacktestClient(invented or response_bytes())
        return P123ScreenBacktestClient(CREDENTIALS, endpoint=self.server.endpoint)


def unknown_baseline(lab: Lab) -> uuid.UUID:
    """Runs `default-only.yaml` with a 503 to the baseline's request, which leaves it `unknown`,
    awaiting a repeat, and returns its attempt's ID."""
    baseline = experiment_plan(EXPERIMENT_CONFIGS / "default-only.yaml").cases[0].case_id
    lab.server.reply("/auth", AUTHENTICATED)
    lab.server.reply("/screen/backtest", Reply(503), response("complete.json"))
    assert lab.new("default-only.yaml").refused("execution.partial")
    (record,) = lab.attempts(baseline, AttemptRecordV1_1)
    assert record.outcome == "unknown"
    return record.attempt_id
