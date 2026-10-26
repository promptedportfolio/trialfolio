"""Executing an approved ranking snapshot's plan into a new output directory: the steps of
`trialfolio run` of a ranking snapshot configuration after approval (docs/contracts.md, ranking
snapshot output; release 0.4.0's R04-T10).

`SnapshotExecution.run`:

1. Claims the output directory with `plan.json` (`output.not_empty`). Nothing is written before.
2. Writes `configuration.yaml`, the configuration's bytes: the first atomic write.
3. Runs the attempt (`trialfolio.attempts.SnapshotAttempt`): authenticates, writes the start record,
   sends the `rank_get` that reads the ranking system the configuration names, at most once, saves
   its response, and writes the attempt record, 1.2.0, with no case.
4. After a 200 whose response has the structure a snapshot needs, writes `definition.xml`, the
   response's `xml` as UTF-8, byte for byte, and then `snapshot.json`, the snapshot record; after
   any other ending, neither. A response without that structure, or saved undecoded, or whose text
   UTF-8 can't encode, is `provider.response_invalid`.
5. Writes `manifest.json` last, the snapshot manifest, listing every file. A snapshot has no
   report: it holds no metric to show.

Step 5 follows any attempt whose record was written, so a failed `rank_get` is accounted for,
unless an interrupt or a storage failure decided the error code, or the attempt ended before
`configuration.yaml` was saved: the output then stays visibly incomplete, without a manifest, as a
run's does (endings that decide the error code), and the message says so, as a run's does.

A snapshot writes nothing to the account, so it takes no lock. A snapshot without a command is one
the core takes with the demo's client, which sends nothing and answers the `rank_get` with an
invented system: it's synthetic, with the approval `not_required`, and no configuration can name
it as its ranking. Nothing here prompts, reads the environment, or reads secrets.

Logs name the snapshot by its plan hash and its attempt ID, never by the system's name, which is
configuration text, or its ID, which comes from the provider's response.

Its reader of the `rank_get`'s response, `p123api-rank-get` version 1, is parser version 1: it
reads the six fields a snapshot needs, and preserves the others without interpreting them. The
manifest lists it, and gives the source records of the `rank_get`'s files, from the snapshot
manifest's tables, which its model checks them against (`trialfolio.contracts.ranking_snapshot`).
"""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Final, Literal, cast

from trialfolio.attempts import (
    AttemptResult,
    Clock,
    SnapshotAttempt,
    prevailing,
    provider_requests,
    record_detail,
    reported_cost,
    utc_now,
)
from trialfolio.configuration import read_ranking_snapshot_configuration
from trialfolio.contracts.attempt import AttemptRecordV1_2
from trialfolio.contracts.common import ErrorDetail
from trialfolio.contracts.manifest_parts import AttemptCounts, SourceRecordV1_1
from trialfolio.contracts.ranking_snapshot import (
    SNAPSHOT_CONFIGURATION_FORMAT,
    SNAPSHOT_PARSERS,
    RankingSnapshotManifest,
    RankingSnapshotPlan,
    RankingSnapshotRecord,
    SnapshotArtifact,
    SnapshotArtifactRole,
    SnapshotCommandRecord,
    SnapshotCounts,
    SnapshotSystem,
)
from trialfolio.demo import SyntheticScreenBacktestClient
from trialfolio.errors import TrialFolioError
from trialfolio.manifests import (
    EndingWithoutManifest,
    ManifestDetails,
    ManifestFile,
    attempt_source,
    configuration_source,
    ends_without_manifest,
    model_json,
    running_detail,
    snapshot_definition_source,
    source_v1_1,
    utc,
)
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION
from trialfolio.planning import Versions, build_snapshot_plan, check_approval
from trialfolio.provider import DecodedResponse, ScreenBacktestClient, UndecodedResponse
from trialfolio.snapshots import DEFINITION, MANIFEST, RECORD, ranking_problems
from trialfolio.storage import ArtifactStore, StoredFile

_logger = logging.getLogger(__name__)

type ClientFactory = Callable[[], ScreenBacktestClient]
"""Makes the attempt's new client, once the configuration is saved."""

type ApprovalMethod = Literal["interactive", "option", "not_required"]

PLAN_PATH: Final = "plan.json"
CONFIGURATION_PATH: Final = "configuration.yaml"

SCHEMA_VERSION: Final = "1.0.0"
"""The schema version of the snapshot's plan, its record, and its manifest."""

RECORDS_SCHEMA_VERSION: Final = "1.2.0"
"""The schema version of the attempt's start and attempt records."""

_SCHEMA_VERSIONS: Final[dict[SnapshotArtifactRole, str]] = {
    "plan": SCHEMA_VERSION,
    "start_record": RECORDS_SCHEMA_VERSION,
    "attempt_record": RECORDS_SCHEMA_VERSION,
    "ranking_snapshot_record": SCHEMA_VERSION,
}
"""The schema version the manifest records for each role whose files have one, apart from the
configuration, which gives its own."""

_TEXTS: Final = ("name", "xml", "currency", "type")
_INTEGERS: Final = ("id", "rankingMethod")
"""The fields a snapshot needs of a `rank_get`'s response, as text and as integers (ranking
snapshot output, the response)."""

_MANIFEST: Final = ManifestDetails(
    written="The snapshot's manifest was written, so its output is complete.",
    left=(
        "The snapshot's manifest.json was published before the failure, and couldn't be removed,"
        " so the snapshot reads as complete although the command failed."
    ),
    missing="The snapshot has no manifest, so its output is incomplete.",
)


class SnapshotExecution:
    """One execution of an approved snapshot plan into the output directory of `store`.

    Its properties stay readable whatever happens, so a command interrupted while it runs still
    knows what it wrote: whether it claimed the directory, the attempt, and each file.
    """

    def __init__(
        self,
        plan: RankingSnapshotPlan,
        approved_hash: str,
        approval: ApprovalMethod,
        store: ArtifactStore,
        command: SnapshotCommandRecord | None,
        *,
        clock: Clock = utc_now,
    ) -> None:
        """Writes nothing.

        `approval` is how the plan was approved, as the manifest records it: `not_required`
        exactly for a synthetic snapshot, which the core takes with the demo's client, and whose
        `command` is None, since no command takes it.

        Raises `TrialFolioError` with `plan.approval_required` unless `approved_hash` is the
        plan's hash, recomputed from its contents (approval), and `ValueError` if `approval` and
        `command` disagree about whether the snapshot is synthetic.
        """
        check_approval(plan, approved_hash)
        if (approval == "not_required") != (command is None):
            raise ValueError("only a synthetic snapshot, which no command takes, needs no approval")
        self._plan = plan
        self._approved_hash = approved_hash
        self._approval: ApprovalMethod = approval
        self._store = store
        self._command = command
        self._clock = clock
        self._claimed = False
        self._attempt: SnapshotAttempt | None = None
        self._result: AttemptResult | None = None
        self._configuration: StoredFile | None = None
        self._record: RankingSnapshotRecord | None = None
        self._problems: tuple[str, ...] = ()
        self._manifest = ManifestFile(store, MANIFEST, _MANIFEST)
        self._files: list[tuple[SnapshotArtifactRole, StoredFile]] = []
        self._started_at: datetime | None = None
        """When the execution began, for a snapshot without a command, which dates its
        configuration by it, since no command started."""

    @property
    def claimed(self) -> bool:
        """Whether the output directory was claimed. Before then, nothing was written."""
        return self._claimed

    @property
    def attempt(self) -> SnapshotAttempt | None:
        """The attempt, once the directory is claimed."""
        return self._attempt

    @property
    def result(self) -> AttemptResult | None:
        """How the attempt ended, once it has."""
        return self._result

    @property
    def record(self) -> RankingSnapshotRecord | None:
        """The snapshot record, `snapshot.json`, once it's written."""
        return self._record

    @property
    def problems(self) -> tuple[str, ...]:
        """Once `snapshot.json` is written, each rule that keeps the snapshot from being a
        ranking, as a clause that follows "names a snapshot "; none when it can be one
        (`trialfolio.snapshots.ranking_problems`)."""
        return self._problems

    @property
    def manifest(self) -> StoredFile | None:
        """The manifest, once it's written: the snapshot is then complete."""
        return self._manifest.written

    def run(
        self,
        configuration: bytes,
        client: ClientFactory,
        *,
        on_claimed: Callable[[], object] | None = None,
    ) -> TrialFolioError | None:
        """Takes the steps the module lists. `configuration` is the configuration file's bytes,
        as the plan was built from them. `on_claimed` is called once the directory is claimed,
        before anything else is written into it, such as to start writing logs there.

        Returns the error the command reports, or None when the snapshot completed. Raises the
        claim's `TrialFolioError`, `output.not_empty` or `storage.write_failed`, and a
        `KeyboardInterrupt` during the claim, which removes what the claim created. Raises
        `ValueError`, before anything else, when `configuration` doesn't give the plan. A
        snapshot without a command is synthetic, so `client` makes the demo's client: another one
        is closed unused, and is a `ValueError` once it's made, before anything is sent. After
        the claim, every ending is returned, as `Execution.run` returns a run's, and
        `ending_detail` says what an ending without a manifest means for the snapshot.
        """
        if self._claimed:
            raise RuntimeError("an execution runs once")
        self._check_configuration(configuration)
        if self._command is None:
            self._started_at = utc(self._clock())
        plan_file = self._store.claim(PLAN_PATH, model_json(self._plan))
        self._claimed = True
        self._files.append(("plan", plan_file))
        result = self._attempt_run(configuration, client, on_claimed)
        self._result = result
        self._files.extend((cast("SnapshotArtifactRole", f.role), f.file) for f in result.files)
        error = result.error
        if (
            ends_without_manifest(recorded=result.recorded, error=error)
            # Every manifest lists the configuration, so without it there's none to write.
            or self._configuration is None
        ):
            return self._without_manifest(error)
        record = result.record
        if not isinstance(record, AttemptRecordV1_2):  # a snapshot's attempt writes 1.2.0
            raise TypeError("a snapshot's attempt record is version 1.2.0")
        with EndingWithoutManifest(after="the attempt ended") as ended:
            error = self._save_system(result, error)
            self._manifest.write(self._build_manifest(record, error))
        if ended.error is not None:
            return prevailing(ended.error.with_detail(self.ending_detail()), error)
        _logger.log(
            logging.INFO if error is None else logging.ERROR,
            "Snapshot ended %s: %s.",
            "completed" if error is None else "failed",
            "no error" if error is None else error.code,
            extra=self._log_fields("snapshot.completed"),
        )
        return error

    def ending_detail(self) -> str:
        """What the snapshot's records say, for the message of an ending after the claim that it
        didn't record itself: whether the `rank_get` was sent and may have been charged, as the
        attempt's records read, and whether the snapshot has its manifest."""
        return f"{self._request_detail()} {self._manifest.detail}"

    def _without_manifest(self, error: TrialFolioError | None) -> TrialFolioError | None:
        """The error of a snapshot whose attempt ended without the snapshot writing its manifest,
        with what the records say of the manifest, as a screen run's says it (`Execution`): the
        attempt's own error already says what happened to its `rank_get`, its attempt record
        written or not, and a snapshot is never resumed, so nothing reads a start record left
        running."""
        if error is None:
            return None
        detail = self._manifest.detail
        if error.message.endswith(detail):
            return error
        return error.with_detail(detail)

    def _check_configuration(self, configuration: bytes) -> None:
        """Checks that the configuration's bytes give the plan, with the plan's versions."""
        # Validated already, when the plan was built from it.
        read = read_ranking_snapshot_configuration(configuration, CONFIGURATION_PATH)
        plan = self._plan
        versions = Versions.of(plan)
        if build_snapshot_plan(read, versions).plan_hash != plan.plan_hash:
            raise ValueError("the configuration doesn't give the plan")

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
            self._files.append(("configuration", self._configuration))
            made = client()
        except (KeyboardInterrupt, Exception) as ending:  # noqa: BLE001 - every ending is recorded.
            if made is not None:
                made.close()
            if self._attempt is None:
                self._attempt = self._new_attempt()
            return self._attempt.end_before_authenticating(ending)
        if self._command is None and not isinstance(made, SyntheticScreenBacktestClient):
            # Its manifest would call the snapshot synthetic, and its system invented.
            made.close()
            raise ValueError("a snapshot without a command is synthetic: its client is the demo's")
        try:
            return self._attempt.run(made)
        finally:
            made.close()

    def _new_attempt(self) -> SnapshotAttempt:
        return SnapshotAttempt(
            self._plan,
            self._approved_hash,
            self._store,
            clock=self._clock,
            synthetic=self._command is None,
        )

    def _save_system(
        self, result: AttemptResult, error: TrialFolioError | None
    ) -> TrialFolioError | None:
        """Writes `definition.xml`, then `snapshot.json`, from a saved response that has the
        structure a snapshot needs. Returns the snapshot's error: `provider.response_invalid`
        when the response doesn't have it."""
        response = result.response
        if error is not None or response is None:
            return error
        saved = next(f.file for f in result.files if f.role.startswith("provider_response"))
        if isinstance(response, UndecodedResponse):
            return _invalid(
                f"p123api couldn't read Portfolio123's answer to the rank_get request, as for a"
                f" ranking method it doesn't know, so it was saved as it came, as {saved.path}."
            )
        system, xml = _system(response)
        if system is None or xml is None:
            return _invalid(
                f"Portfolio123's answer to the rank_get request was saved, as {saved.path}, but it"
                " doesn't have the structure a snapshot needs: an object with name, xml,"
                " currency, and type as text that UTF-8 can encode, and id and rankingMethod as"
                " integers."
            )
        definition = self._store.write(DEFINITION, xml)
        self._files.append(("ranking_definition", definition))
        record = RankingSnapshotRecord(
            schema_version=SCHEMA_VERSION,
            trialfolio_version=self._plan.trialfolio_version,
            requested=self._plan.system,
            system=system,
            taken_at=result.record.ended_at,
            attempt_id=result.record.attempt_id,
            plan_hash=self._plan.plan_hash,
            definition=definition.artifact_id,
            response=saved.artifact_id,
        )
        stored = self._store.write(RECORD, model_json(record))
        self._files.append(("ranking_snapshot_record", stored))
        self._record = record
        self._problems = tuple(ranking_problems(system, xml))
        return None

    def _request_detail(self) -> str:
        result = self._result
        if result is not None and result.recorded:
            return record_detail(result.record)
        attempt = self._attempt
        if attempt is not None and attempt.start_record is not None:
            return running_detail(name="rank_get request")
        return "The rank_get request wasn't sent."

    def _build_manifest(
        self, record: AttemptRecordV1_2, error: TrialFolioError | None
    ) -> RankingSnapshotManifest:
        """The manifest of the files written so far, for the attempt `record` ended."""
        return RankingSnapshotManifest(
            schema_version=SCHEMA_VERSION,
            artifact_type="ranking-snapshot",
            trialfolio_version=self._plan.trialfolio_version,
            created_at=utc(self._clock()),
            command=self._command,
            synthetic=self._command is None,
            plan_hash=self._plan.plan_hash,
            approval=self._approval,
            outcome="completed" if error is None else "failed",
            error=None if error is None else ErrorDetail(code=error.code, message=error.message),
            artifacts=tuple(self._listed(role, file, record) for role, file in self._files),
            parsers=SNAPSHOT_PARSERS,
            license_id=LICENSE_ID,
            notice_version=NOTICE_VERSION,
            counts=SnapshotCounts(
                attempts=AttemptCounts(
                    succeeded=int(record.outcome == "succeeded"),
                    failed=int(record.outcome == "failed"),
                    unknown=int(record.outcome == "unknown"),
                    running=0,
                ),
                provider_requests=provider_requests(record),
                retries=0,
                cost=reported_cost(record),
            ),
        )

    def _listed(
        self, role: SnapshotArtifactRole, stored: StoredFile, record: AttemptRecordV1_2
    ) -> SnapshotArtifact:
        return SnapshotArtifact(
            path=stored.path,
            artifact_id=stored.artifact_id,
            size=stored.size,
            role=role,
            schema_version=SCHEMA_VERSION
            if role == "configuration"
            else _SCHEMA_VERSIONS.get(role),
            source=self._source(role, record),
        )

    def _source(
        self, role: SnapshotArtifactRole, record: AttemptRecordV1_2
    ) -> SourceRecordV1_1 | None:
        """The source record of a source artifact: the configuration, which the user supplied;
        the `rank_get`'s request and response, dated by the attempt's times; and the definition,
        which the `rank_get` read, dated when the snapshot was taken (ranking snapshot output,
        the manifest). None for any other role."""
        if role == "configuration":
            # The version of the snapshot's own records, where a run's gives its configuration's
            # schema version: both are 1.0.0, and the snapshot records what it always has.
            source = configuration_source(
                SNAPSHOT_CONFIGURATION_FORMAT, SCHEMA_VERSION, self._acquired()
            )
            return source_v1_1(source)
        if role == "ranking_definition":
            return snapshot_definition_source(record.ended_at)
        return attempt_source(role, lambda: (record.started_at, record.ended_at), snapshot=True)

    def _acquired(self) -> datetime:
        """When the configuration was acquired: when the command started, or, for a snapshot
        without a command, when its execution began."""
        if self._command is not None:
            return self._command.started_at
        if self._started_at is None:  # set when a snapshot without a command begins
            raise RuntimeError("the snapshot's configuration is acquired once it begins")
        return self._started_at

    def _log_fields(self, event: str) -> dict[str, str]:
        fields = {"event": event, "plan_hash": self._plan.plan_hash}
        if self._attempt is not None:
            fields["attempt_id"] = str(self._attempt.attempt_id)
        return fields


def _system(response: DecodedResponse) -> tuple[SnapshotSystem | None, bytes | None]:
    """The system a `rank_get`'s decoded response gives, and its `xml` encoded as UTF-8, when it
    has the structure a snapshot needs: an object with `name`, `xml`, `currency`, and `type` as
    text that UTF-8 can encode, and `id` and `rankingMethod` as integers, never booleans; None
    for each otherwise (ranking snapshot output, the response)."""
    payload = response.payload
    if not isinstance(payload, dict):
        return None, None
    fields = cast("dict[str, object]", payload)
    texts = [fields.get(key) for key in _TEXTS]
    integers = [fields.get(key) for key in _INTEGERS]
    if not all(isinstance(text, str) for text in texts) or not all(
        type(number) is int for number in integers
    ):
        return None, None
    try:
        encoded = [cast("str", text).encode("utf-8") for text in texts]
    except UnicodeEncodeError:  # a lone surrogate, which a JSON escape can give
        return None, None
    name, _, currency, kind = (cast("str", text) for text in texts)
    system = SnapshotSystem(
        name=name,
        id=cast("int", integers[0]),
        ranking_method=cast("int", integers[1]),
        currency=currency,
        type=kind,
    )
    return system, encoded[1]


def _invalid(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "provider.response_invalid",
        f"{problem} The snapshot has no definition.xml or snapshot.json. The saved response is"
        " kept as it came; report the problem if it persists.",
    )
