"""What a screen run's execution and a ranking snapshot's share: the steps of a command of one
attempt, after approval (docs/contracts.md, approval's order of steps, artifact storage, endings
that decide the error code; ranking snapshot output).

`SingleAttemptExecution` takes the steps both take, in their order, and each executor gives what's
its own: `Execution`, in `trialfolio.execution`, a screen run's, and `SnapshotExecution`, in
`trialfolio.snapshot_execution`, a snapshot's.

1. Claims the output directory with `plan.json` (`output.not_empty`). Nothing is written before.
2. Writes `configuration.yaml`, the configuration's bytes, the first atomic write, then what the
   executor writes beside it, such as a definition's copy.
3. Runs the executor's attempt with a new client, which it closes whatever happens. An ending
   after the claim and before the attempt authenticates is recorded by the attempt.
4. Takes the executor's steps that end with its manifest, after an attempt whose record was
   written, unless an interrupt or a storage failure decided the error code, or a file every
   manifest lists wasn't written; and then logs how the execution ended, under the executor's
   logger, so the event keeps its `component`.

Every other ending is returned without a manifest, with what the records say of the manifest, and
`ending_detail` says what the attempt's records say of its requests, in the executor's words.
`single_counts` gives the attempt's counts, which a run's manifest and a snapshot's both give.

Nothing here logs under its own name, prompts, reads the environment, or reads secrets.
"""

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from trialfolio.attempts import (
    Attempt,
    AttemptResult,
    AttemptRole,
    Clock,
    RankingAttempt,
    SnapshotAttempt,
    prevailing,
    provider_requests,
    record_detail,
    reported_cost,
)
from trialfolio.contracts.attempt import AttemptRecord, AttemptRecordV1_2
from trialfolio.contracts.manifest_parts import AttemptCounts
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotPlan
from trialfolio.demo import SyntheticScreenBacktestClient
from trialfolio.errors import TrialFolioError
from trialfolio.manifests import (
    EndingWithoutManifest,
    ManifestFile,
    ends_without_manifest,
    model_json,
    utc,
)
from trialfolio.planning import check_approval
from trialfolio.provider import ScreenBacktestClient
from trialfolio.runs import CONFIGURATION_PATH, PLAN_PATH
from trialfolio.storage import ArtifactStore, StoredFile

type ClientFactory = Callable[[], ScreenBacktestClient]
"""Makes the attempt's new client, once the configuration is saved."""


@dataclass(frozen=True)
class Kind:
    """What an executor's messages call what it executes, and how it logs its ending."""

    name: str
    """Such as "run", in "a run without a command is synthetic"."""
    event: str
    """The event of the log record that says how the execution ended."""
    logger: logging.Logger
    """The executor's own logger, whose name is the event's `component`."""

    @property
    def ended(self) -> str:
        """The message that says how the execution ended, as in "Run ended completed: no
        error."."""
        return f"{self.name.capitalize()} ended %s: %s."


class SingleCounts(TypedDict):
    """The counts of an output of one attempt, as a run's manifest and a snapshot's give them."""

    attempts: AttemptCounts
    provider_requests: int
    retries: Literal[0]
    cost: int | None


def single_counts(record: AttemptRecord | AttemptRecordV1_2) -> SingleCounts:
    """The counts of the one attempt whose record is `record`: the attempt, by its outcome; the
    sends of its requests that may have reached Portfolio123; no retry, since Trial Folio never
    resends a request on its own; and the credits Portfolio123 reported charging."""
    return SingleCounts(
        attempts=AttemptCounts(
            succeeded=int(record.outcome == "succeeded"),
            failed=int(record.outcome == "failed"),
            unknown=int(record.outcome == "unknown"),
            running=0,
        ),
        provider_requests=provider_requests(record),
        retries=0,
        cost=reported_cost(record),
    )


class SingleAttemptExecution[
    P: Plan | PlanV1_2 | RankingSnapshotPlan,
    A: Attempt | RankingAttempt | SnapshotAttempt,
](ABC):
    """One execution of an approved plan `P` of one attempt `A` into the output directory of
    `store`, by the steps the module lists.

    Its properties stay readable whatever happens, so a command interrupted while it runs still
    knows what it wrote: whether it claimed the directory, the attempt, and each file.
    """

    def __init__(
        self,
        plan: P,
        approved_hash: str,
        store: ArtifactStore,
        manifest: ManifestFile,
        *,
        command_started: datetime | None,
        clock: Clock,
        kind: Kind,
    ) -> None:
        """Writes nothing. `command_started` is when the command that runs it started, and None
        for an execution no command runs, which the core runs with the demo's client.

        Raises `TrialFolioError` with `plan.approval_required` unless `approved_hash` is the
        plan's hash, recomputed from its contents (approval).
        """
        check_approval(plan, approved_hash)
        self._plan = plan
        self._approved_hash = approved_hash
        self._store = store
        self._manifest = manifest
        self._command_started = command_started
        self._clock = clock
        self._kind = kind
        self._claimed = False
        self._attempt: A | None = None
        self._result: AttemptResult | None = None
        self._configuration: StoredFile | None = None
        self._started_at: datetime | None = None
        """When the execution began, for one no command runs, which dates its configuration by
        it, since no command started."""

    @property
    def claimed(self) -> bool:
        """Whether the output directory was claimed. Before then, nothing was written."""
        return self._claimed

    @property
    def attempt(self) -> A | None:
        """The attempt, once the directory is claimed."""
        return self._attempt

    @property
    def result(self) -> AttemptResult | None:
        """How the attempt ended, once it has."""
        return self._result

    @property
    def manifest(self) -> StoredFile | None:
        """The manifest, once it's written: the output is then complete."""
        return self._manifest.written

    def ending_detail(self) -> str:
        """What the records say, for the message of an ending after the claim that the execution
        didn't record itself: whether the attempt's requests were sent and may have been charged,
        as its records read, and whether the output has its manifest."""
        return f"{self._request_detail()} {self._manifest.detail}"

    def _check_unrun(self) -> None:
        if self._claimed:
            raise RuntimeError("an execution runs once")

    def _begin(self) -> None:
        """Dates an execution no command runs, once its configuration is checked."""
        if self._command_started is None:
            self._started_at = utc(self._clock())

    def _run_claimed(
        self,
        configuration: bytes,
        client: ClientFactory,
        on_claimed: Callable[[], object] | None,
    ) -> TrialFolioError | None:
        """The steps the module lists, once what the executor holds while it runs, such as the
        ranking lock, is held."""
        plan_file = self._store.claim(PLAN_PATH, model_json(self._plan))
        self._claimed = True
        self._list("plan", plan_file)
        result = self._attempt_run(configuration, client, on_claimed)
        self._result = result
        for file in result.files:
            self._list(file.role, file.file)
        error = result.error
        if (
            ends_without_manifest(recorded=result.recorded, error=error)
            # Every manifest lists the configuration, and what the executor writes beside it, so
            # without them there's none to write.
            or self._configuration is None
            or not self._copies_written()
        ):
            return self._without_manifest(error)
        with EndingWithoutManifest(after="the attempt ended") as ended:
            error = self._end(configuration, result, error)
        if ended.error is not None:
            return prevailing(ended.error.with_detail(self.ending_detail()), error)
        self._kind.logger.log(
            logging.INFO if error is None else logging.ERROR,
            self._kind.ended,
            "completed" if error is None else "failed",
            "no error" if error is None else error.code,
            extra=self._log_fields(self._kind.event),
        )
        return error

    def _attempt_run(
        self,
        configuration: bytes,
        client: ClientFactory,
        on_claimed: Callable[[], object] | None,
    ) -> AttemptResult:
        made: ScreenBacktestClient | None = None
        try:
            if on_claimed is not None:
                on_claimed()
            self._attempt = self._new_attempt()
            self._configuration = self._store.write(CONFIGURATION_PATH, configuration)
            self._list("configuration", self._configuration)
            self._write_copies()
            made = client()
        except (KeyboardInterrupt, Exception) as ending:  # noqa: BLE001 - every ending is recorded.
            if made is not None:
                made.close()
            if self._attempt is None:
                self._attempt = self._new_attempt()
            return self._attempt.end_before_authenticating(ending)
        if self._command_started is None and not isinstance(made, SyntheticScreenBacktestClient):
            # Its manifest would call the output synthetic, and what it holds invented.
            made.close()
            raise ValueError(
                f"a {self._kind.name} without a command is synthetic: its client is the demo's"
            )
        try:
            return self._attempt.run(made)
        finally:
            made.close()

    def _without_manifest(self, error: TrialFolioError | None) -> TrialFolioError | None:
        """The error of an execution whose attempt ended without the execution writing its
        manifest, with what the records say of the manifest (what a run writes after its
        attempt, R04-AC13). The attempt's own error already says what happened to its requests,
        its attempt record written or not: when the record's write fails, the attempt adds its
        ending's detail. So the start record's detail, which then reads as running, isn't added
        too: neither a run nor a snapshot is ever resumed, so nothing reads it, unlike an
        experiment session's."""
        if error is None:
            return None
        detail = self._manifest.detail
        if error.message.endswith(detail):
            return error
        return error.with_detail(detail)

    def _request_detail(self) -> str:
        result = self._result
        if result is not None and result.recorded:
            return record_detail(result.record)
        attempt = self._attempt
        if attempt is not None and attempt.start_record is not None:
            return self._running_detail(attempt)
        return self._unsent_detail(attempt)

    def _acquired(self) -> datetime:
        """When the configuration was acquired: when the command started, or, for an execution
        no command runs, when it began."""
        if self._command_started is not None:
            return self._command_started
        if self._started_at is None:  # set when an execution without a command begins
            raise RuntimeError(f"the {self._kind.name}'s configuration is acquired once it begins")
        return self._started_at

    def _log_fields(self, event: str) -> dict[str, str]:
        fields = {"event": event, "plan_hash": self._plan.plan_hash}
        if self._case_id is not None:
            fields["case_id"] = self._case_id
        if self._attempt is not None:
            fields["attempt_id"] = str(self._attempt.attempt_id)
        return fields

    # What each executor gives

    @property
    def _case_id(self) -> str | None:
        """The case its logs name, when it has one."""
        return None

    @abstractmethod
    def _new_attempt(self) -> A: ...

    @abstractmethod
    def _list(self, role: Literal["plan", "configuration"] | AttemptRole, file: StoredFile) -> None:
        """Lists a file the execution wrote, which its manifest lists."""

    def _write_copies(self) -> None:
        """Writes what the executor writes beside `configuration.yaml`, before the attempt."""

    def _copies_written(self) -> bool:
        """Whether `_write_copies` wrote each of its files."""
        return True

    @abstractmethod
    def _end(
        self, configuration: bytes, result: AttemptResult, error: TrialFolioError | None
    ) -> TrialFolioError | None:
        """The executor's steps after its attempt, which end by writing its manifest. Returns the
        error the command reports."""

    @abstractmethod
    def _running_detail(self, attempt: A) -> str:
        """What the attempt's start record says of its requests, without its attempt record."""

    @abstractmethod
    def _unsent_detail(self, attempt: A | None) -> str:
        """What the records say of the attempt's requests, without its start record."""
