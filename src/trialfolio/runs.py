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
  and drawn from the run's own configuration and saved response.

Otherwise `read_run` raises `input.not_a_run`, or `artifact.unknown_schema_version` for a schema
version with no reader. The message names the problem, never a value.

A `SavedRun` is also what the report renders when `run` writes it, before the manifest.
"""

import json
import re
import uuid
from dataclasses import dataclass
from typing import Final, cast

from pydantic import BaseModel, ValidationError

from trialfolio.attempts import (
    ATTEMPT_RECORD,
    START_RECORD,
    AttemptStatus,
    attempt_status,
    check_records,
)
from trialfolio.canonical import sha256_hex
from trialfolio.contracts.attempt import ArtifactReference, AttemptRecord, StartRecord
from trialfolio.contracts.manifest import ArtifactRole, ManifestArtifact, RunManifest
from trialfolio.contracts.plan import Plan
from trialfolio.contracts.tables import TABLES_SCHEMA_VERSION, MetricsRow, SettingsRow
from trialfolio.display import visible
from trialfolio.errors import TrialFolioError
from trialfolio.normalization import METRICS_PATH, SETTINGS_PATH
from trialfolio.planning import plan_hash
from trialfolio.storage import ArtifactStore
from trialfolio.tables import read_metrics_csv, read_settings_csv

MANIFEST_PATH: Final = "manifest.json"
PLAN_PATH: Final = "plan.json"
CONFIGURATION_PATH: Final = "configuration.yaml"

_SCHEMA_VERSIONS: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "manifest": ("run manifests", ("1.0.0",)),
    "plan": ("plans", ("1.0.0",)),
    "start_record": ("start records", ("1.0.0",)),
    "attempt_record": ("attempt records", ("1.0.0",)),
    "metrics": ("metrics.csv", (TABLES_SCHEMA_VERSION,)),
    "settings": ("settings.csv", (TABLES_SCHEMA_VERSION,)),
}
"""The schema versions `read_run` has a reader for, for the manifest and each role it reads, with
what they're called in messages."""

_ATTEMPT_DIRECTORY: Final = re.compile(
    r"cases/(?P<case_id>case-[0-9a-f]{16})/attempts/"
    r"(?P<attempt_id>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
)
_RESPONSE_ROLES: Final[dict[str, ArtifactRole]] = {
    "decoded": "provider_response",
    "undecoded": "provider_response_undecoded",
}


@dataclass(frozen=True)
class SavedAttempt:
    """An attempt's records: its start record, its attempt record, or both."""

    start: StartRecord | None
    record: AttemptRecord | None

    def __post_init__(self) -> None:
        if self.start is None and self.record is None:
            raise ValueError("an attempt has a start record, an attempt record, or both")

    @property
    def status(self) -> AttemptStatus:
        """How the attempt reads: `running` when it has only a start record."""
        return cast("AttemptStatus", attempt_status(self.start, self.record))


@dataclass(frozen=True)
class SavedRun:
    """What a run's report shows: its manifest, plan, attempts, and normalized tables.

    For a run read back, the manifest is the saved one. When `run` writes the report, the manifest
    isn't written yet, so it's the manifest as it will be written, without the report.
    """

    manifest: RunManifest
    plan: Plan
    attempts: tuple[SavedAttempt, ...]
    metrics: tuple[MetricsRow, ...] | None
    settings: tuple[SettingsRow, ...] | None
    """The tables' rows: both, or neither when the run has no normalized result."""

    def __post_init__(self) -> None:
        if (self.metrics is None) != (self.settings is None):
            raise ValueError("a run has both normalized tables, or neither")


def read_run(store: ArtifactStore) -> SavedRun:
    """Reads a saved run from `store`, rooted at its output directory, and checks it's complete.

    Raises `TrialFolioError` with `input.not_a_run` when it isn't a complete run, and with
    `artifact.unknown_schema_version` when one of its artifacts has a schema version with no
    reader. Writes nothing.
    """
    manifest = _manifest(store)
    contents = {artifact.path: _listed(store, artifact) for artifact in manifest.artifacts}
    plan = _plan(manifest, contents)
    attempts = _attempts(manifest, contents, plan)
    metrics, settings = _tables(manifest, contents, plan, attempts)
    return SavedRun(manifest, plan, attempts, metrics, settings)


def _manifest(store: ArtifactStore) -> RunManifest:
    try:
        content = store.read(MANIFEST_PATH)
    except FileNotFoundError:
        raise _not_a_run(
            "it has no manifest.json. Trial Folio writes a run's manifest last, so a run without"
            " one didn't finish."
        ) from None
    except NotADirectoryError:
        raise _not_a_run("it isn't a directory.") from None
    except OSError as error:
        raise _not_a_run(f"its manifest.json can't be read ({_reason(error)}).") from None
    fields = _json_object(content, MANIFEST_PATH)
    if fields.get("artifact_type") != "run":
        raise _not_a_run("its manifest.json isn't a run's manifest.")
    _check_version(fields.get("schema_version"), MANIFEST_PATH, "manifest")
    return _validated(RunManifest, content, MANIFEST_PATH, "run manifest")


def _listed(store: ArtifactStore, artifact: ManifestArtifact) -> bytes:
    """The bytes of a file the manifest lists, checked against its size and `artifact_id`."""
    try:
        content = store.read(artifact.path)
    except FileNotFoundError:
        raise _not_a_run(f"its manifest lists {_named(artifact.path)}, which is missing.") from None
    except OSError as error:
        raise _not_a_run(
            f"{_named(artifact.path)}, which its manifest lists, can't be read ({_reason(error)})."
        ) from None
    if len(content) != artifact.size or "sha256:" + sha256_hex(content) != artifact.artifact_id:
        raise _not_a_run(
            f"{_named(artifact.path)} doesn't match its artifact_id in the manifest, so it changed"
            " after the run wrote it."
        )
    return content


def _plan(manifest: RunManifest, contents: dict[str, bytes]) -> Plan:
    _only(manifest, "plan", PLAN_PATH)
    _only(manifest, "configuration", CONFIGURATION_PATH)
    content = contents[PLAN_PATH]
    _check_version(_json_object(content, PLAN_PATH).get("schema_version"), PLAN_PATH, "plan")
    plan = _validated(Plan, content, PLAN_PATH, "plan")
    try:
        recomputed = plan_hash(plan)
    except ValueError as error:
        # The message names the kind of value canonical JSON can't write, never the value.
        raise _not_a_run(f"its plan.json can't be hashed ({error}).") from None
    if recomputed != plan.plan_hash:
        raise _not_a_run(
            "its plan.json doesn't recompute to its plan_hash, so the plan changed after it was"
            " approved."
        )
    if manifest.plan_hash != plan.plan_hash:
        raise _not_a_run("its manifest names another plan than its plan.json.")
    return plan


def _only(manifest: RunManifest, role: ArtifactRole, path: str) -> ManifestArtifact:
    listed = [artifact for artifact in manifest.artifacts if artifact.role == role]
    if len(listed) != 1 or listed[0].path != path:
        raise _not_a_run(f"its manifest doesn't list {path} as the run's one {role}.")
    _check_version(listed[0].schema_version, listed[0].path, role, listed=True)
    return listed[0]


def _attempts(
    manifest: RunManifest, contents: dict[str, bytes], plan: Plan
) -> tuple[SavedAttempt, ...]:
    (case,) = plan.cases
    records: dict[str, tuple[StartRecord | None, AttemptRecord | None]] = {}
    for artifact in manifest.artifacts:
        if artifact.role not in ("start_record", "attempt_record"):
            continue
        directory, _, name = artifact.path.rpartition("/")
        place = _ATTEMPT_DIRECTORY.fullmatch(directory)
        expected = START_RECORD if artifact.role == "start_record" else ATTEMPT_RECORD
        if place is None or place["case_id"] != case.case_id or name != expected:
            raise _not_a_run(
                f"its manifest lists {_named(artifact.path)} as an attempt's {expected}, but it"
                " isn't one in an attempt's directory of the plan's case."
            )
        _check_version(artifact.schema_version, artifact.path, artifact.role, listed=True)
        content = contents[artifact.path]
        version = _json_object(content, artifact.path).get("schema_version")
        _check_version(version, artifact.path, artifact.role)
        start, record = records.get(directory, (None, None))
        if artifact.role == "start_record":
            start = _validated(StartRecord, content, artifact.path, "start record")
        else:
            record = _validated(AttemptRecord, content, artifact.path, "attempt record")
        records[directory] = (start, record)
    listed = {artifact.path: artifact for artifact in manifest.artifacts}
    attempts: list[SavedAttempt] = []
    for directory, (start, record) in records.items():
        attempt_id = cast("re.Match[str]", _ATTEMPT_DIRECTORY.fullmatch(directory))["attempt_id"]
        try:
            check_records(start, record, case.case_id, uuid.UUID(attempt_id))
        except ValueError as error:
            raise _not_a_run(f"the records in {_named(directory)} don't agree: {error}.") from None
        for read in (start, record):
            if read is not None and read.plan_hash != plan.plan_hash:
                raise _not_a_run(f"the records in {_named(directory)} name another plan.")
        if record is not None:
            _check_references(record, listed)
        attempts.append(SavedAttempt(start, record))
    return tuple(attempts)


def _check_references(record: AttemptRecord, listed: dict[str, ManifestArtifact]) -> None:
    """Each file the attempt record references is listed, with the same `artifact_id`."""
    references: list[tuple[ArtifactReference, ArtifactRole]] = []
    if record.request is not None:
        references.append((record.request, "provider_request"))
    if record.response is not None:
        references.append((record.response, _RESPONSE_ROLES[record.response.form]))
    for reference, role in references:
        artifact = listed.get(reference.path)
        if artifact is None or (artifact.artifact_id, artifact.role) != (
            reference.artifact_id,
            role,
        ):
            raise _not_a_run(
                f"an attempt record references {_named(reference.path)}, which its manifest"
                " doesn't list as that file."
            )


def _tables(
    manifest: RunManifest,
    contents: dict[str, bytes],
    plan: Plan,
    attempts: tuple[SavedAttempt, ...],
) -> tuple[tuple[MetricsRow, ...] | None, tuple[SettingsRow, ...] | None]:
    roles = {artifact.role for artifact in manifest.artifacts}
    if not roles & {"metrics", "settings"}:
        return None, None
    _only(manifest, "metrics", METRICS_PATH)
    _only(manifest, "settings", SETTINGS_PATH)
    metrics = read_metrics_csv(contents[METRICS_PATH], METRICS_PATH)
    settings = read_settings_csv(contents[SETTINGS_PATH], SETTINGS_PATH)
    (case,) = plan.cases
    if any(row.label != case.case_id for row in (*metrics, *settings)):
        raise _not_a_run(
            "its normalized tables label their rows with another case than the plan's."
        )
    (configuration,) = (a for a in manifest.artifacts if a.role == "configuration")
    if any(row.source_artifact != configuration.artifact_id for row in settings):
        raise _not_a_run("its settings.csv was drawn from another configuration than the run's.")
    responses = {
        attempt.record.response.artifact_id
        for attempt in attempts
        if attempt.record is not None and attempt.record.response is not None
    }
    if any(row.source_artifact not in responses for row in metrics):
        raise _not_a_run("its metrics.csv was drawn from another response than the run's.")
    return metrics, settings


def _json_object(content: bytes, path: str) -> dict[str, object]:
    try:
        loaded: object = json.loads(content)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _not_a_run(f"{_named(path)} isn't JSON.") from None
    if not isinstance(loaded, dict):
        raise _not_a_run(f"{_named(path)} isn't a JSON object.")
    return cast("dict[str, object]", loaded)


def _check_version(version: object, path: str, kind: str, *, listed: bool = False) -> None:
    """Checks a schema version, from the file itself or, when `listed`, from its manifest entry,
    where a file without one has none."""
    if kind not in _SCHEMA_VERSIONS:
        return
    name, readable = _SCHEMA_VERSIONS[kind]
    if (listed and version is None) or version in readable:
        return
    if not isinstance(version, str):
        raise _not_a_run(f"{_named(path)} has no schema version.")
    where = "its manifest gives it" if listed else "it has"
    raise TrialFolioError(
        "artifact.unknown_schema_version",
        f"Trial Folio can't read {_named(path)}: {where} a schema version this version has no"
        f" reader for. It reads {name} {' or '.join(readable)}. Read the run"
        " with a version of Trial Folio that has one. Nothing was written.",
    )


def _validated[M: BaseModel](model: type[M], content: bytes, path: str, what: str) -> M:
    try:
        return model.model_validate_json(content)
    except ValidationError as error:
        # Only the model's own fields are named: an unexpected key is text from the file.
        details = error.errors(include_url=False, include_input=False, include_context=False)
        named = sorted(
            {
                str(detail["loc"][0])
                for detail in details
                if detail["loc"] and detail["loc"][0] in model.model_fields
            }
        )
        check = f"check `{'`, `'.join(named)}`" if named else "check its fields"
        raise _not_a_run(f"{_named(path)} isn't a valid {what}: {check}.") from None


def _named(path: str) -> str:
    return f"`{visible(path)}`"


def _reason(error: OSError) -> str:
    return error.strerror or type(error).__name__


def _not_a_run(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "input.not_a_run",
        f"The run directory isn't a complete Trial Folio run: {problem} Nothing was written. Give"
        " the output directory of a run that finished, as `trialfolio run` or `trialfolio demo`"
        " wrote it.",
    )
