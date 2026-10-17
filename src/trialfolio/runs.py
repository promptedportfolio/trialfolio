"""Saved runs: a run's output directory read back and checked against its manifest, as
`trialfolio report` reads it (release 0.1.0; docs/contracts.md, artifact storage, plan hashing,
and artifact compatibility).

`read_run` reads only through an `ArtifactStore`, and only the files the manifest lists, so a run
reads the same way wherever it's stored. A directory is a complete run when:

- its `manifest.json` is a run manifest whose schema version has a reader. The manifest is written
  last, so a run without one is incomplete.
- each file the manifest lists exists, with the size and `artifact_id` it records.
- its `plan.json` recomputes to its `plan_hash`, which the manifest names.
- each attempt's records are valid, belong to their directory, and name the plan's case and hash,
  and each file they reference is listed with the same `artifact_id`.
- its normalized tables, if it has them, are both listed and valid, labeled with the plan's case,
  hold one row for each of the layout's metrics, in its unit, and each of the plan's settings, in
  order, and are drawn from the run's own configuration and saved response.

From 0.4.0, `read_run` also reads a run whose ranking is a definition (docs/contracts.md, a
complete run; release 0.4.0's R04-T09): its manifest 1.1.0, its plan 1.2.0, its records 1.2.0,
and its `settings.csv` 1.1.0, each the version a run of its plan writes. Such a run also lists
its `definition.xml`, which, read as a definition's file is read, has the hash its plan's
`ranking_source` gives; each attempt that wrote its update record, `updating.json`, lists it, and
it agrees with its other records; each file an attempt record's `ranking_update` references is
listed, with the `rank_update`'s roles, and an attempt listed without its attempt record lists the
files written before its start records; and its weight rows are its plan's, drawn from its
`definition.xml`. A snapshot's records are release 0.4.0's R04-T10's, so a plan whose ranking is
a snapshot is refused until then.

Otherwise `read_run` raises `input.not_a_run`, or `artifact.unknown_schema_version` for a schema
version with no reader. The message names the problem, never a value, and names the run as a
`RunName` says: `trialfolio report` reads one run, "the run directory", and a review names each
result's run by its label and path, and in logs by its position.

`check_run` reads it the same way, and also gives back the bytes it checked, from which a review
writes its copies, so a file changed after the check can't be copied. A review compares no weight
rows until release 0.4.0's R04-T11, so `check_run` reads 0.3.0's versions only, unless it's told
to read a run with a ranking definition too, as `read_run` does.

The checks it shares with an experiment's reader, `experiment_records.py`, are in
`record_checks.py`.

A `SavedRun` is also what the report renders when `run` writes it, before the manifest.
"""

import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

from trialfolio.attempts import (
    ATTEMPT_RECORD,
    RANK_UPDATE_REQUEST_FILE,
    RANK_UPDATE_RESPONSE_FILE,
    RANK_UPDATE_RESPONSE_RAW,
    START_RECORD,
    UPDATE_RECORD,
    AttemptStatus,
    attempt_status,
    check_records,
)
from trialfolio.contracts.attempt import (
    ArtifactReference,
    AttemptRecord,
    AttemptRecordV1_2,
    StartRecord,
    StartRecordV1_2,
)
from trialfolio.contracts.common import RANK_UPDATE_REQUEST
from trialfolio.contracts.manifest import (
    ArtifactRole,
    ArtifactRoleV1_1,
    ManifestArtifact,
    ManifestArtifactV1_1,
    RunManifest,
    RunManifestV1_1,
)
from trialfolio.contracts.plan import Plan, PlanCase, PlanCaseV1_2, PlanV1_2
from trialfolio.contracts.tables import (
    TABLES_SCHEMA_VERSION,
    TABLES_SCHEMA_VERSION_V1_1,
    MetricsRow,
    SettingsRow,
    SettingsRowV1_1,
)
from trialfolio.errors import ErrorCode, TrialFolioError, reason_of
from trialfolio.experiment_paths import REQUEST
from trialfolio.normalization import METRICS_PATH, SETTINGS_PATH
from trialfolio.record_checks import (
    RecordChecks,
    definition_hash,
    drawn_from,
    holds_each_metric,
    holds_each_setting,
    holds_each_weight,
    labeled,
    matches,
    named,
)
from trialfolio.storage import ArtifactStore
from trialfolio.tables import read_metrics_csv, read_settings_csv, read_settings_csv_v1_1

MANIFEST_PATH: Final = "manifest.json"
PLAN_PATH: Final = "plan.json"
CONFIGURATION_PATH: Final = "configuration.yaml"
DEFINITION_PATH: Final = "definition.xml"
"""A run's copy of its ranking definition, beside its `configuration.yaml`."""

type AnyManifest = RunManifest | RunManifestV1_1
type AnyArtifact = ManifestArtifact | ManifestArtifactV1_1
type AnyStart = StartRecord | StartRecordV1_2
type AnyRecord = AttemptRecord | AttemptRecordV1_2

_SCHEMA_VERSIONS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "manifest": ("run manifests", ("1.0.0",)),
    "plan": ("plans", ("1.0.0",)),
    "start_record": ("start records", ("1.0.0",)),
    "attempt_record": ("attempt records", ("1.0.0",)),
    "metrics": ("metrics.csv", (TABLES_SCHEMA_VERSION,)),
    "settings": ("settings.csv", (TABLES_SCHEMA_VERSION,)),
}
"""The schema versions `check_run` has a reader for, for the manifest and each role it reads, with
what they're called in messages: 0.3.0's, which a review reads."""

_RANKING_VERSIONS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "manifest": ("run manifests", ("1.0.0", "1.1.0")),
    "plan": ("plans", ("1.0.0", "1.2.0")),
    "update_record": ("update records", ("1.2.0",)),
    "start_record": ("start records", ("1.0.0", "1.2.0")),
    "attempt_record": ("attempt records", ("1.0.0", "1.2.0")),
    "metrics": ("metrics.csv", (TABLES_SCHEMA_VERSION,)),
    "settings": ("settings.csv", (TABLES_SCHEMA_VERSION, TABLES_SCHEMA_VERSION_V1_1)),
}
"""The same, for `read_run`, which also reads a run whose ranking is a definition."""

_RECORD_FILES: Final[dict[str, str]] = {
    "update_record": UPDATE_RECORD,
    "start_record": START_RECORD,
    "attempt_record": ATTEMPT_RECORD,
}
"""The file of each role of an attempt's records."""

_ATTEMPT_DIRECTORY: Final = re.compile(
    r"cases/(?P<case_id>case-[0-9a-f]{16})/attempts/"
    r"(?P<attempt_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
_RESPONSE_ROLES: Final[dict[str, ArtifactRole]] = {
    "decoded": "provider_response",
    "undecoded": "provider_response_undecoded",
}
_RANK_UPDATE_ROLES: Final[dict[str, ArtifactRoleV1_1]] = {
    "decoded": "rank_update_response",
    "undecoded": "rank_update_response_undecoded",
}


@dataclass(frozen=True)
class SavedAttempt:
    """An attempt's records: its start record, its attempt record, or both. They're version 1.2.0
    for an attempt that sends a definition, whose start record is its backtest's, and whose
    update record, `updating.json`, is its `rank_update`'s."""

    start: StartRecord | StartRecordV1_2 | None
    record: AttemptRecord | AttemptRecordV1_2 | None
    update: StartRecordV1_2 | None = None
    """The update record of an attempt that sends a definition, when it wrote one."""

    def __post_init__(self) -> None:
        if self.start is None and self.record is None and self.update is None:
            raise ValueError("an attempt has a start record, an attempt record, or both")

    @property
    def status(self) -> AttemptStatus:
        """How the attempt reads: `running` when it has a start record, or only an update
        record, and no attempt record."""
        return cast("AttemptStatus", attempt_status(self.start, self.record, self.update))


@dataclass(frozen=True)
class SavedRun:
    """What a run's report shows: its manifest, plan, attempts, and normalized tables.

    For a run read back, the manifest is the saved one. When `run` writes the report, the manifest
    isn't written yet, so it's the manifest as it will be written, without the report.
    """

    manifest: RunManifest | RunManifestV1_1
    plan: Plan | PlanV1_2
    attempts: tuple[SavedAttempt, ...]
    metrics: tuple[MetricsRow, ...] | None
    settings: tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...] | None
    """The tables' rows: both, or neither when the run has no normalized result."""

    def __post_init__(self) -> None:
        if (self.metrics is None) != (self.settings is None):
            raise ValueError("a run has both normalized tables, or neither")


@dataclass(frozen=True)
class RunName:
    """How a refusal names the run it read: in its message, and in its logged message, which
    holds no configuration value. Each starts lowercase, as in "the run directory"."""

    shown: str
    logged: str


THE_RUN_DIRECTORY: Final = RunName("the run directory", "the run directory")
"""How `trialfolio report`, which reads one run, names it."""


@dataclass(frozen=True)
class CheckedRun:
    """A saved run, and the bytes `check_run` read and checked."""

    saved: SavedRun
    contents: Mapping[str, bytes]
    """By path in the run: `manifest.json`'s bytes, and each listed file's."""


def read_run(store: ArtifactStore) -> SavedRun:
    """Reads a saved run from `store`, rooted at its output directory, and checks it's complete,
    a run whose ranking is a definition included, as `trialfolio report` reads it.

    Raises `TrialFolioError` with `input.not_a_run` when it isn't a complete run, and with
    `artifact.unknown_schema_version` when one of its artifacts has a schema version with no
    reader. Writes nothing.
    """
    return check_run(store, ranking=True).saved


def check_run(
    store: ArtifactStore, name: RunName = THE_RUN_DIRECTORY, *, ranking: bool = False
) -> CheckedRun:
    """Reads and checks a saved run as `read_run` does, reading each file once, and returns it
    with the bytes it checked. Its errors name the run as `name` says.

    Without `ranking`, it reads 0.3.0's versions only, as a review does until release 0.4.0's
    R04-T11 compares weight rows, so a run whose ranking is a definition has a manifest version
    with no reader."""
    checks = _RANKING_CHECKS if ranking else _CHECKS
    try:
        content = _read_manifest(store)
        manifest = _manifest(content, checks)
        contents = {artifact.path: _listed(store, artifact) for artifact in manifest.artifacts}
        plan = _plan(manifest, contents, checks)
        definition = _definition(manifest, contents, plan)
        attempts = _attempts(manifest, contents, plan, checks)
        metrics, settings = _tables(manifest, contents, plan, attempts, definition, checks)
    except _Refused as refused:
        raise refused.error(name) from None
    saved = SavedRun(manifest, plan, attempts, metrics, settings)
    return CheckedRun(saved, MappingProxyType({MANIFEST_PATH: content, **contents}))


def not_a_run(name: RunName, problem: str) -> TrialFolioError:
    """The `input.not_a_run` error for the run `name` names, for `problem`: a sentence that names
    no value, such as "it has no manifest.json."."""
    return _not_a_run(problem).error(name)


def _read_manifest(store: ArtifactStore) -> bytes:
    try:
        return store.read(MANIFEST_PATH)
    except FileNotFoundError:
        raise _not_a_run(
            "it has no manifest.json. Trial Folio writes a run's manifest last, so a run without"
            " one didn't finish."
        ) from None
    except NotADirectoryError:
        raise _not_a_run("it isn't a directory.") from None
    except OSError as error:
        raise _not_a_run(f"its manifest.json can't be read ({reason_of(error)}).") from None


def _manifest(content: bytes, checks: RecordChecks) -> AnyManifest:
    fields = checks.json_object(content, MANIFEST_PATH)
    if fields.get("artifact_type") != "run":
        raise _not_a_run("its manifest.json isn't a run's manifest.")
    version = fields.get("schema_version")
    checks.check_version(version, MANIFEST_PATH, "manifest")
    if version == "1.1.0":
        return checks.validated(RunManifestV1_1, content, MANIFEST_PATH, "run manifest")
    return checks.validated(RunManifest, content, MANIFEST_PATH, "run manifest")


def _listed(store: ArtifactStore, artifact: AnyArtifact) -> bytes:
    """The bytes of a file the manifest lists, checked against its size and `artifact_id`."""
    try:
        content = store.read(artifact.path)
    except FileNotFoundError:
        raise _not_a_run(f"its manifest lists {named(artifact.path)}, which is missing.") from None
    except OSError as error:
        raise _not_a_run(
            f"{named(artifact.path)}, which its manifest lists, can't be read ({reason_of(error)})."
        ) from None
    if not matches(content, artifact):
        raise _not_a_run(
            f"{named(artifact.path)} doesn't match its artifact_id in the manifest, so it changed"
            " after the run wrote it."
        )
    return content


def _plan(
    manifest: AnyManifest, contents: dict[str, bytes], checks: RecordChecks
) -> Plan | PlanV1_2:
    _only(manifest, "plan", PLAN_PATH, checks)
    _only(manifest, "configuration", CONFIGURATION_PATH, checks)
    content = contents[PLAN_PATH]
    version = checks.json_object(content, PLAN_PATH).get("schema_version")
    plan = (
        checks.record(PlanV1_2, content, PLAN_PATH, "plan")
        if version == "1.2.0"
        else checks.record(Plan, content, PLAN_PATH, "plan")
    )
    checks.check_plan_hash(plan, "its plan.json")
    if manifest.plan_hash != plan.plan_hash:
        raise _not_a_run("its manifest names another plan than its plan.json.")
    if isinstance(manifest, RunManifestV1_1) != isinstance(plan, PlanV1_2):
        raise _not_a_run(
            "its manifest.json isn't the version a run of its plan writes: 1.1.0 for a plan with"
            " a ranking definition, and 1.0.0 for any other."
        )
    return plan


def _only(
    manifest: AnyManifest, role: ArtifactRoleV1_1, path: str, checks: RecordChecks
) -> AnyArtifact:
    listed = [artifact for artifact in manifest.artifacts if artifact.role == role]
    if len(listed) != 1 or listed[0].path != path:
        raise _not_a_run(f"its manifest doesn't list {path} as the run's one {role}.")
    checks.check_version(listed[0].schema_version, listed[0].path, role, listed=True)
    return listed[0]


def _definition(
    manifest: AnyManifest, contents: dict[str, bytes], plan: Plan | PlanV1_2
) -> AnyArtifact | None:
    """The run's `definition.xml`, for a plan with a ranking definition, checked: listed once,
    and, read as a definition's file is read, with the hash its plan's `ranking_source` gives
    (a complete run). A snapshot's records are release 0.4.0's R04-T10's."""
    if not isinstance(plan, PlanV1_2):
        return None
    source = plan.ranking_source
    if source.form != "definition" or any(
        artifact.role == "ranking_snapshot_record" for artifact in manifest.artifacts
    ):
        raise _not_a_run(
            "its plan's ranking is a snapshot, whose records this version of Trial Folio doesn't"
            " read."
        )
    copy = _only(manifest, "ranking_definition", DEFINITION_PATH, _RANKING_CHECKS)
    if definition_hash(contents[DEFINITION_PATH]) != source.definition:
        raise _not_a_run(
            "its definition.xml isn't its plan's ranking definition: read as a definition's file"
            " is read, it doesn't have the hash its plan's ranking_source gives."
        )
    return copy


def _attempts(
    manifest: AnyManifest, contents: dict[str, bytes], plan: Plan | PlanV1_2, checks: RecordChecks
) -> tuple[SavedAttempt, ...]:
    (case,) = plan.cases
    records: dict[str, dict[str, AnyStart | AnyRecord]] = {}
    for artifact in manifest.artifacts:
        expected = _RECORD_FILES.get(artifact.role)
        if expected is None:
            continue
        directory, _, name = artifact.path.rpartition("/")
        place = _ATTEMPT_DIRECTORY.fullmatch(directory)
        if place is None or place["case_id"] != case.case_id or name != expected:
            raise _not_a_run(
                f"its manifest lists {named(artifact.path)} as an attempt's {expected}, but it"
                " isn't one in an attempt's directory of the plan's case."
            )
        checks.check_version(artifact.schema_version, artifact.path, artifact.role, listed=True)
        records.setdefault(directory, {})[artifact.role] = _record(
            contents[artifact.path], artifact.path, artifact.role, plan, checks
        )
    listed = {artifact.path: artifact for artifact in manifest.artifacts}
    attempts: list[SavedAttempt] = []
    for directory, read in records.items():
        attempt_id = cast("re.Match[str]", _ATTEMPT_DIRECTORY.fullmatch(directory))["attempt_id"]
        update = cast("StartRecordV1_2 | None", read.get("update_record"))
        start = cast("AnyStart | None", read.get("start_record"))
        record = cast("AnyRecord | None", read.get("attempt_record"))
        try:
            if isinstance(plan, PlanV1_2):
                _check_ranking_records(update, start, record, case.case_id, uuid.UUID(attempt_id))
            else:
                check_records(
                    cast("StartRecord | None", start),
                    cast("AttemptRecord | None", record),
                    case.case_id,
                    uuid.UUID(attempt_id),
                )
        except ValueError as error:
            raise _not_a_run(f"the records in {named(directory)} don't agree: {error}.") from None
        for found in (update, start, record):
            if found is not None and found.plan_hash != plan.plan_hash:
                raise _not_a_run(f"the records in {named(directory)} name another plan.")
        if record is not None:
            _check_references(record, listed)
        else:
            _check_unrecorded(directory, update, start, listed)
        attempts.append(SavedAttempt(start, record, update))
    return tuple(attempts)


def _record(
    content: bytes, path: str, role: str, plan: Plan | PlanV1_2, checks: RecordChecks
) -> AnyStart | AnyRecord:
    """One of an attempt's records, read by its schema version, which must be the one an
    attempt under `plan` writes: 1.2.0 for a plan with a ranking definition, and 1.0.0
    otherwise."""
    version = checks.json_object(content, path).get("schema_version")
    checks.check_version(version, path, role)
    expected = "1.2.0" if isinstance(plan, PlanV1_2) else "1.0.0"
    if version != expected:
        raise _not_a_run(
            f"{named(path)} isn't the version an attempt under its plan writes: records 1.2.0"
            " under a plan with a ranking definition, and 1.0.0 under any other."
        )
    if role == "attempt_record":
        model: type[AnyStart | AnyRecord] = (
            AttemptRecordV1_2 if expected == "1.2.0" else AttemptRecord
        )
    else:
        model = StartRecordV1_2 if expected == "1.2.0" else StartRecord
    return checks.record(model, content, path, role)


def _check_ranking_records(
    update: StartRecordV1_2 | None,
    start: AnyStart | None,
    record: AnyRecord | None,
    case_id: str,
    attempt_id: uuid.UUID,
) -> None:
    """Checks that the records 1.2.0 of an attempt that sends a definition belong together, in
    the directory of `case_id` and `attempt_id` (a complete run): each names its directory's
    attempt and case, and its own operation; the update record comes before `started.json`, whose
    exchanges are the update record's, then the `rank_update`'s 200; an attempt record with a
    `POST /rank` exchange has an update record; and the attempt record holds its start records'
    contents. Raises `ValueError` when they don't."""
    found = [read for read in (update, start, record) if read is not None]
    if any((read.case_id, read.attempt_id) != (case_id, attempt_id) for read in found):
        raise ValueError("a record names another attempt than its directory")
    operations = (
        (update, "rank_update"),
        (start, "screen_backtest"),
        (record, "screen_backtest"),
    )
    for read, operation in operations:
        if read is not None and getattr(read, "operation", None) != operation:
            raise ValueError("a record doesn't name the request it comes before or ends")
    if update is None and (
        start is not None
        or (record is not None and any(e.request == RANK_UPDATE_REQUEST for e in record.exchanges))
    ):
        raise ValueError("an attempt that sent its rank_update wrote its update record first")
    _check_held(update, start, record)


def _check_held(
    update: StartRecordV1_2 | None, start: AnyStart | None, record: AnyRecord | None
) -> None:
    """The update record and `started.json` hold the same values, `started.json`'s exchanges
    being the update record's, then the `rank_update`'s, and the attempt record holds both's.
    Raises `ValueError` when they don't."""
    shared = set(StartRecordV1_2.model_fields) - {"operation", "exchanges"}
    if (
        update is not None
        and start is not None
        and (
            update.model_dump(include=shared) != start.model_dump(include=shared)
            or start.exchanges[:-1] != update.exchanges
        )
    ):
        raise ValueError("the start record doesn't hold the update record's values and exchanges")
    latest = start if start is not None else update
    if (
        record is not None
        and latest is not None
        and (
            record.model_dump(include=shared) != latest.model_dump(include=shared)
            or record.exchanges[: len(latest.exchanges)] != latest.exchanges
        )
    ):
        raise ValueError("the attempt record doesn't hold its start records' contents")


def _check_unrecorded(
    directory: str,
    update: StartRecordV1_2 | None,
    start: AnyStart | None,
    listed: dict[str, AnyArtifact],
) -> None:
    """An attempt that sends a definition, listed without its attempt record, lists the files
    written before its start records, with their roles, as an experiment's attempt has them
    (resuming, in the core): the `rank-update-request.json` written before its update record, at
    most one saved `rank_update` response, and, with `started.json`, the decoded
    `rank-update-response.json` and the backtest's `request.json`, both written before it. Any
    other attempt without its attempt record, which has no update record, is read as before."""
    if update is None:
        return

    def lists(name: str, role: ArtifactRoleV1_1) -> bool:
        artifact = listed.get(f"{directory}/{name}")
        return artifact is not None and artifact.role == role

    if not lists(RANK_UPDATE_REQUEST_FILE, "rank_update_request"):
        raise _not_a_run(
            f"its manifest lists the update record in {named(directory)}, but not the"
            f" {RANK_UPDATE_REQUEST_FILE} written before it."
        )
    responses = (RANK_UPDATE_RESPONSE_FILE, RANK_UPDATE_RESPONSE_RAW)
    if all(f"{directory}/{name}" in listed for name in responses):
        raise _not_a_run(
            f"its manifest lists two saved rank_update responses in {named(directory)}."
        )
    if start is not None and not lists(RANK_UPDATE_RESPONSE_FILE, "rank_update_response"):
        raise _not_a_run(
            f"its manifest lists the start record in {named(directory)}, but not the"
            f" {RANK_UPDATE_RESPONSE_FILE} saved before it."
        )
    if start is not None and not lists(REQUEST, "provider_request"):
        raise _not_a_run(
            f"its manifest lists the start record in {named(directory)}, but not the {REQUEST}"
            " written before it."
        )


def _check_references(record: AnyRecord, listed: dict[str, AnyArtifact]) -> None:
    """Each file the attempt record references is listed, with the same `artifact_id` and the
    role of that file, the `rank_update`'s included."""
    references: list[tuple[ArtifactReference, ArtifactRoleV1_1]] = []
    if record.request is not None:
        references.append((record.request, "provider_request"))
    if record.response is not None:
        references.append((record.response, _RESPONSE_ROLES[record.response.form]))
    if isinstance(record, AttemptRecordV1_2) and record.ranking_update is not None:
        update = record.ranking_update
        if update.request is not None:
            references.append((update.request, "rank_update_request"))
        if update.response is not None:
            references.append((update.response, _RANK_UPDATE_ROLES[update.response.form]))
    for reference, role in references:
        artifact = listed.get(reference.path)
        if artifact is None or (artifact.artifact_id, artifact.role) != (
            reference.artifact_id,
            role,
        ):
            raise _not_a_run(
                f"an attempt record references {named(reference.path)}, which its manifest"
                " doesn't list as that file."
            )


def _tables(
    manifest: AnyManifest,
    contents: dict[str, bytes],
    plan: Plan | PlanV1_2,
    attempts: tuple[SavedAttempt, ...],
    definition: AnyArtifact | None,
    checks: RecordChecks,
) -> tuple[
    tuple[MetricsRow, ...] | None, tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...] | None
]:
    roles = {artifact.role for artifact in manifest.artifacts}
    if not roles & {"metrics", "settings"}:
        return None, None
    _only(manifest, "metrics", METRICS_PATH, checks)
    listed = _only(manifest, "settings", SETTINGS_PATH, checks)
    metrics = checks.table_rows(read_metrics_csv, contents[METRICS_PATH], METRICS_PATH)
    (case,) = plan.cases
    settings: tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...]
    expected = TABLES_SCHEMA_VERSION_V1_1 if isinstance(plan, PlanV1_2) else TABLES_SCHEMA_VERSION
    if listed.schema_version not in (None, expected):
        raise _not_a_run(
            "its manifest gives its settings.csv another version than a run of its plan writes:"
            " 1.1.0 for a plan with a ranking definition, and 1.0.0 for any other."
        )
    if isinstance(plan, PlanV1_2):
        settings = checks.table_rows(read_settings_csv_v1_1, contents[SETTINGS_PATH], SETTINGS_PATH)
    else:
        settings = checks.table_rows(read_settings_csv, contents[SETTINGS_PATH], SETTINGS_PATH)
    if not labeled((*metrics, *settings), case.case_id):
        raise _not_a_run(
            "its normalized tables label their rows with another case than the plan's."
        )
    if not holds_each_metric(metrics):
        raise _not_a_run(
            "its metrics.csv doesn't hold one row for each of the layout's metrics, in order,"
            " each in the metric's unit."
        )
    if not holds_each_setting(settings, case.settings):
        raise _not_a_run(
            "its settings.csv doesn't hold one row for each of the plan's settings, in order."
        )
    (configuration,) = (a for a in manifest.artifacts if a.role == "configuration")
    _check_settings_sources(settings, case, configuration, definition)
    responses = (
        attempt.record.response.artifact_id
        for attempt in attempts
        if attempt.record is not None and attempt.record.response is not None
    )
    if not drawn_from(metrics, *responses):
        raise _not_a_run("its metrics.csv was drawn from another response than the run's.")
    return metrics, settings


def _check_settings_sources(
    settings: tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...],
    case: PlanCase | PlanCaseV1_2,
    configuration: AnyArtifact,
    definition: AnyArtifact | None,
) -> None:
    """Each row of `settings.csv` was drawn from the run's configuration, and each weight row
    from its `definition.xml`, with the weight its plan gives its node (weight rows)."""
    weights = [row for row in settings if isinstance(row, SettingsRowV1_1) and row.node]
    others = [row for row in settings if not (isinstance(row, SettingsRowV1_1) and row.node)]
    if not drawn_from(others, configuration.artifact_id):
        raise _not_a_run("its settings.csv was drawn from another configuration than the run's.")
    if definition is None:
        return
    if not isinstance(case, PlanCaseV1_2):
        raise TypeError("only a plan with a ranking definition has its definition's copy")
    rows = [row for row in settings if isinstance(row, SettingsRowV1_1)]
    if not holds_each_weight(rows, case.settings) or not (
        drawn_from(weights, definition.artifact_id)
    ):
        raise _not_a_run(
            "its settings.csv's weight rows aren't its definition's: each gives the weight its"
            " plan gives its node, drawn from the run's definition.xml."
        )


class _Refused(Exception):
    """Why a run can't be read, before the error names the run: `message` gives the error's
    message for the run's name."""

    def __init__(self, code: ErrorCode, message: Callable[[str], str]) -> None:
        super().__init__(code)
        self.code: ErrorCode = code
        self.message = message

    def error(self, name: RunName) -> TrialFolioError:
        return TrialFolioError(self.code, self.message(name.shown), self.message(name.logged))


def _not_a_run(problem: str) -> _Refused:
    return _Refused(
        "input.not_a_run",
        lambda run: (
            f"{run[:1].upper()}{run[1:]} isn't a complete Trial Folio run: {problem}"
            " Nothing was written. Give the output directory of a run that finished, as"
            " `trialfolio run` or `trialfolio demo` wrote it."
        ),
    )


def _unknown_version(path: str, problem: str) -> _Refused:
    return _Refused(
        "artifact.unknown_schema_version",
        lambda run: (
            f"Trial Folio can't read {named(path)} in {run}: {problem} Read the run with a version"
            " of Trial Folio that has one. Nothing was written."
        ),
    )


_CHECKS: Final = RecordChecks(
    refused=_not_a_run,
    unknown_version=_unknown_version,
    readable=_SCHEMA_VERSIONS,
    manifest="its manifest",
)
"""The checks `check_run` shares with an experiment's reader, which refuse as it does."""

_RANKING_CHECKS: Final = RecordChecks(
    refused=_not_a_run,
    unknown_version=_unknown_version,
    readable=_RANKING_VERSIONS,
    manifest="its manifest",
)
"""The same, reading a run whose ranking is a definition too, as `read_run` does."""
