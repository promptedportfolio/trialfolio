"""Ranking snapshots read back: the directory a configuration's `ranking.snapshot` names, read and
checked offline, when the configuration is validated, in step 2 (docs/contracts.md, ranking
snapshot output, reading a snapshot; release 0.4.0's R04-T10).

`read_snapshot` reads only through an `ArtifactStore`, and only the files the snapshot's manifest
lists, as `trialfolio report` reads a run. A snapshot can be a configuration's ranking when:

1. **It's complete.** Its `manifest.json` is a snapshot manifest, valid, with the `outcome`
   `completed`; each file it lists has the size and `artifact_id` it records; it lists
   `definition.xml` and `snapshot.json`; and `snapshot.json` is valid, and its `definition` is
   `definition.xml`'s `artifact_id`. Otherwise it's `input.not_a_run`, whose message says the
   directory isn't a complete ranking snapshot, and what's wrong, or
   `artifact.unknown_schema_version` for a manifest or record of a schema version with no reader.
2. **It can be a ranking.** It isn't synthetic, which is refused first, whatever its definition
   holds: the demo's client invented its system, so a run that sent its definition would send an
   invented system's definition as one Portfolio123 returned. Its `definition.xml` follows the
   rules of a definition file (`trialfolio.ranking_definitions`), and its record's ranking method
   is 2 or 4, its currency `USD`, and its type `Stock`. Otherwise `NotARanking` gives each rule it
   breaks, which the configuration's reader reports with `config.invalid`, naming its key.

`snapshot_from` reads a snapshot's two files from their bytes, read and checked already, as an
executor is given them, and `ranking_problems` gives the rules of the second step but the
synthetic one, which `trialfolio run` of a snapshot configuration says of the snapshot it took.

It checks its records as `trialfolio.record_checks` checks a run's, with its own few checks:
importing that module here would import the configuration's reader, which imports this one.

Messages name a file by its path in the snapshot, never a value: not the system's name, its ID,
or its definition, which hold the user's strategy definition.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, cast

from pydantic import BaseModel, ValidationError

from trialfolio.canonical import sha256_hex
from trialfolio.contracts.common import RANKING_METHOD_NUMBERS, RankingMethod
from trialfolio.contracts.ranking_snapshot import (
    RankingSnapshotManifest,
    RankingSnapshotRecord,
    SnapshotArtifact,
    SnapshotSystem,
)
from trialfolio.display import visible
from trialfolio.errors import TrialFolioError, reason_of
from trialfolio.ranking_definitions import DefinitionProblem, RankingDefinition, read_definition
from trialfolio.storage import ArtifactStore

MANIFEST: Final = "manifest.json"
DEFINITION: Final = "definition.xml"
"""The snapshot's copy of the system's definition, as `rank_get` returned it."""
RECORD: Final = "snapshot.json"
"""The snapshot record."""

_READABLE: Final = ("1.0.0",)
"""The schema versions this version reads of a snapshot's manifest and of its record."""

_METHODS: Final[dict[int, RankingMethod]] = {
    number: method for method, number in RANKING_METHOD_NUMBERS.items()
}
"""The ranking methods a ranking takes, by the number Portfolio123 gives them."""

SYNTHETIC_PROBLEM: Final = (
    "that's synthetic: the demo's client invented its system and its definition, so a run that"
    " sent it would send an invented system's definition as one Portfolio123 returned. Name a"
    " snapshot that trialfolio run of a ranking snapshot configuration took"
)
"""Why a synthetic snapshot can't be a ranking, after "names a snapshot "."""


@dataclass(frozen=True)
class SnapshotName:
    """How a refusal names the snapshot it read: in its message, and in its logged message, which
    leaves out the path as the configuration gives it."""

    shown: str
    logged: str


@dataclass(frozen=True)
class SnapshotFiles:
    """The bytes of a snapshot's `definition.xml` and `snapshot.json`, as read and checked when a
    configuration that names it was validated: a plan's copies hold them, byte for byte."""

    definition: bytes
    record: bytes


@dataclass(frozen=True)
class SnapshotRead:
    """A snapshot that can be a ranking: its files, its record, its definition, read by the rules
    of a definition file, and the ranking method its system gives."""

    files: SnapshotFiles
    record: RankingSnapshotRecord
    definition: RankingDefinition
    ranking_method: RankingMethod

    @property
    def record_id(self) -> str:
        """The `artifact_id` of its `snapshot.json`, which a plan's `ranking_source` records."""
        return artifact_id(self.files.record)

    @property
    def definition_id(self) -> str:
        """The `artifact_id` of its `definition.xml`, which a plan's `ranking_source` records."""
        return artifact_id(self.files.definition)


class NotARanking(Exception):
    """A complete snapshot that can't be a ranking: each rule it breaks, as a clause that follows
    "names a snapshot ", naming no value."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = tuple(problems)


def read_snapshot(store: ArtifactStore, name: SnapshotName) -> SnapshotRead:
    """Reads the snapshot in `store`, rooted at its directory, and checks that it's complete,
    and can be a ranking, as the module says. Its errors name it as `name` says.

    Raises `TrialFolioError` with `input.not_a_run` when it isn't a complete snapshot, and with
    `artifact.unknown_schema_version` when its manifest or its record has a schema version with
    no reader; and `NotARanking` when it can't be a ranking. Writes nothing.
    """
    manifest = _manifest(store, name)
    contents = {artifact.path: _listed(store, name, artifact) for artifact in manifest.artifacts}
    if DEFINITION not in contents or RECORD not in contents:
        raise _not_a_snapshot(name, f"its manifest doesn't list its {DEFINITION} and {RECORD}.")
    (entry,) = (a for a in manifest.artifacts if a.role == "ranking_snapshot_record")
    if entry.schema_version not in _READABLE:
        raise _unknown_version(name, RECORD, "its manifest gives it")
    files = SnapshotFiles(definition=contents[DEFINITION], record=contents[RECORD])
    fields = _json_object(name, files.record, RECORD)
    _check_version(name, fields.get("schema_version"), RECORD)
    record = _validated(name, RankingSnapshotRecord, files.record, RECORD, "snapshot record")
    if record.definition != artifact_id(files.definition):
        raise _not_a_snapshot(
            name, f"its {RECORD} doesn't name its {DEFINITION} by that file's artifact_id."
        )
    if manifest.synthetic:
        raise NotARanking([SYNTHETIC_PROBLEM])
    return _ranking(files, record)


def snapshot_from(files: SnapshotFiles) -> SnapshotRead:
    """The snapshot whose `definition.xml` and `snapshot.json` are `files`, read and checked
    already, when a configuration that names it was validated, as an executor is given them.

    Raises `ValueError` when `snapshot.json` isn't a valid snapshot record, or doesn't name
    `definition.xml` by its `artifact_id`, and `NotARanking` when it can't be a ranking.
    """
    record = RankingSnapshotRecord.model_validate_json(files.record)
    if record.definition != artifact_id(files.definition):
        raise ValueError("the snapshot record names another definition.xml")
    return _ranking(files, record)


def ranking_problems(system: SnapshotSystem, definition: bytes) -> list[str]:
    """Each rule that keeps a snapshot of `system`, whose `definition.xml` holds `definition`,
    from being a ranking, as a clause that follows "names a snapshot "; none when it can be one.
    The synthetic rule isn't among them: a snapshot's own record can't show it."""
    problems: list[str] = []
    try:
        read_definition(definition)
    except DefinitionProblem as problem:
        at = "" if problem.line is None else f", at line {problem.line}"
        problems.append(f"whose definition Trial Folio can't read{at}: {problem.problem}")
    if system.ranking_method not in _METHODS:
        problems.append(
            "whose ranking method isn't one a ranking takes: 2, percentile_nas_negative, or 4,"
            " percentile_nas_neutral"
        )
    if system.currency != "USD":
        problems.append("whose system's currency isn't USD, which every backtest sends")
    if system.type != "Stock":
        problems.append("whose system's type isn't Stock")
    return problems


def _ranking(files: SnapshotFiles, record: RankingSnapshotRecord) -> SnapshotRead:
    problems = ranking_problems(record.system, files.definition)
    if problems:
        raise NotARanking(problems)
    return SnapshotRead(
        files=files,
        record=record,
        definition=read_definition(files.definition),
        ranking_method=_METHODS[record.system.ranking_method],
    )


def artifact_id(content: bytes) -> str:
    """The `artifact_id` of a file that holds `content`: `sha256:` and the hex SHA-256 of its
    bytes."""
    return "sha256:" + sha256_hex(content)


def _manifest(store: ArtifactStore, name: SnapshotName) -> RankingSnapshotManifest:
    try:
        content = store.read(MANIFEST)
    except FileNotFoundError:
        raise _not_a_snapshot(
            name,
            f"it has no {MANIFEST}. Trial Folio writes a snapshot's manifest last, so a snapshot"
            " without one didn't finish.",
        ) from None
    except NotADirectoryError:
        raise _not_a_snapshot(name, "it isn't a directory.") from None
    except OSError as error:
        raise _not_a_snapshot(name, f"its {MANIFEST} can't be read ({reason_of(error)}).") from None
    fields = _json_object(name, content, MANIFEST)
    if fields.get("artifact_type") != "ranking-snapshot":
        raise _not_a_snapshot(name, f"its {MANIFEST} isn't a ranking snapshot's manifest.")
    _check_version(name, fields.get("schema_version"), MANIFEST)
    manifest = _validated(
        name, RankingSnapshotManifest, content, MANIFEST, "ranking snapshot manifest"
    )
    if manifest.outcome != "completed":
        raise _not_a_snapshot(
            name,
            "its manifest's outcome is failed: its rank_get didn't give a definition Trial Folio"
            " saved.",
        )
    return manifest


def _listed(store: ArtifactStore, name: SnapshotName, entry: SnapshotArtifact) -> bytes:
    """The bytes of a file the manifest lists, checked against its size and `artifact_id`."""
    try:
        content = store.read(entry.path)
    except FileNotFoundError:
        raise _not_a_snapshot(
            name, f"its manifest lists {named(entry.path)}, which is missing."
        ) from None
    except OSError as error:
        raise _not_a_snapshot(
            name,
            f"{named(entry.path)}, which its manifest lists, can't be read ({reason_of(error)}).",
        ) from None
    if len(content) != entry.size or artifact_id(content) != entry.artifact_id:
        raise _not_a_snapshot(
            name,
            f"{named(entry.path)} doesn't match its artifact_id in the manifest, so it changed"
            " after the snapshot was taken.",
        )
    return content


def _json_object(name: SnapshotName, content: bytes, path: str) -> dict[str, object]:
    """The JSON object in `content`, the snapshot's file at `path`."""
    try:
        loaded: object = json.loads(content)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _not_a_snapshot(name, f"its {named(path)} isn't JSON.") from None
    if not isinstance(loaded, dict):
        raise _not_a_snapshot(name, f"its {named(path)} isn't a JSON object.")
    return cast("dict[str, object]", loaded)


def _check_version(name: SnapshotName, version: object, path: str) -> None:
    """Checks the schema version a snapshot's manifest or record holds: one this version reads."""
    if version in _READABLE:
        return
    if not isinstance(version, str):
        raise _not_a_snapshot(name, f"its {named(path)} has no schema version.")
    raise _unknown_version(name, path, "it has")


def _validated[M: BaseModel](
    name: SnapshotName, model: type[M], content: bytes, path: str, what: str
) -> M:
    """`content`, the snapshot's file at `path`, as `model`, which `what` names in a message.
    Only the model's own fields are named: an unexpected key is text from the file."""
    try:
        return model.model_validate_json(content)
    except ValidationError as error:
        details = error.errors(include_url=False, include_input=False, include_context=False)
        fields = sorted(
            {
                str(detail["loc"][0])
                for detail in details
                if detail["loc"] and detail["loc"][0] in model.model_fields
            }
        )
        check = f"check `{'`, `'.join(fields)}`" if fields else "check its fields"
        raise _not_a_snapshot(name, f"its {named(path)} isn't a valid {what}: {check}.") from None


def named(path: str) -> str:
    """A path as a message names it: in backticks, with each character that isn't visible
    escaped."""
    return f"`{visible(path)}`"


_TAKE_ONE: Final = (
    "Name the directory of a snapshot that finished, as trialfolio run of a ranking snapshot"
    " configuration wrote it. Nothing was sent, and no output was created."
)


def _not_a_snapshot(name: SnapshotName, problem: str) -> TrialFolioError:
    return TrialFolioError(
        "input.not_a_run",
        f"{name.shown} isn't a complete ranking snapshot: {problem} {_TAKE_ONE}",
        f"{name.logged} isn't a complete ranking snapshot: {problem} {_TAKE_ONE}",
    )


def _unknown_version(name: SnapshotName, path: str, where: str) -> TrialFolioError:
    """`artifact.unknown_schema_version` for the snapshot's file at `path`, whose schema version
    `where` gives: "it has", or "its manifest gives it". The message never gives the version,
    which is text from the file."""

    def message(snapshot: str) -> str:
        return (
            f"{snapshot}: Trial Folio can't read the snapshot's {named(path)}: {where} a schema"
            f" version this version has no reader for. It reads {' or '.join(_READABLE)}. Read it"
            " with a version of Trial Folio that has one. Nothing was sent, and no output was"
            " created."
        )

    return TrialFolioError(
        "artifact.unknown_schema_version", message(name.shown), message(name.logged)
    )
