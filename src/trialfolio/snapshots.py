"""Ranking snapshots read back: the directory a configuration's `ranking.snapshot` names, read and
checked offline, when the configuration is validated, in step 2 (docs/contracts.md, ranking
snapshot output, reading a snapshot; release 0.4.0's R04-T10).

`read_snapshot` reads only through a `StoreReader`, the store's reads, and only the files the
snapshot's manifest lists, as `trialfolio report` reads a run. A snapshot can be a configuration's
ranking when:

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

It checks its manifest, its listed files, and its records with `trialfolio.file_checks`, as
`trialfolio.record_checks` checks a run's, in its own sentences: importing `record_checks` here
would import the configuration's reader, which imports this one.

Messages name a file by its path in the snapshot, never a value: not the system's name, its ID,
or its definition, which hold the user's strategy definition.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from trialfolio.contracts.common import RANKING_METHOD_NUMBERS, RankingMethod
from trialfolio.contracts.ranking_snapshot import (
    RankingSnapshotManifest,
    RankingSnapshotRecord,
    SnapshotSystem,
)
from trialfolio.errors import TrialFolioError
from trialfolio.file_checks import (
    Refused,
    artifact_id,
    check_version,
    json_object,
    named,
    read_listed,
    read_manifest,
    validated,
)
from trialfolio.ranking_definitions import DefinitionProblem, RankingDefinition, read_definition
from trialfolio.storage import StoreReader

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


def read_snapshot(store: StoreReader, name: SnapshotName) -> SnapshotRead:
    """Reads the snapshot in `store`, rooted at its directory, and checks that it's complete,
    and can be a ranking, as the module says. Its errors name it as `name` says.

    Raises `TrialFolioError` with `input.not_a_run` when it isn't a complete snapshot, and with
    `artifact.unknown_schema_version` when its manifest or its record has a schema version with
    no reader; and `NotARanking` when it can't be a ranking. Writes nothing.
    """
    refused = _refused(name)
    manifest = _manifest(store, name)
    contents = {
        artifact.path: read_listed(store, artifact, "the snapshot was taken", refused)
        for artifact in manifest.artifacts
    }
    if DEFINITION not in contents or RECORD not in contents:
        raise _not_a_snapshot(name, f"its manifest doesn't list its {DEFINITION} and {RECORD}.")
    (entry,) = (a for a in manifest.artifacts if a.role == "ranking_snapshot_record")
    if entry.schema_version not in _READABLE:
        raise _unknown_version(name, RECORD, "its manifest gives it")
    files = SnapshotFiles(definition=contents[DEFINITION], record=contents[RECORD])
    fields = json_object(files.record, _its(RECORD), refused)
    _check_version(name, fields.get("schema_version"), RECORD)
    record = validated(
        RankingSnapshotRecord, files.record, _its(RECORD), "snapshot record", refused
    )
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


def _manifest(store: StoreReader, name: SnapshotName) -> RankingSnapshotManifest:
    refused = _refused(name)
    content = read_manifest(store, MANIFEST, "snapshot", refused)
    fields = json_object(content, _its(MANIFEST), refused)
    if fields.get("artifact_type") != "ranking-snapshot":
        raise _not_a_snapshot(name, f"its {MANIFEST} isn't a ranking snapshot's manifest.")
    _check_version(name, fields.get("schema_version"), MANIFEST)
    manifest = validated(
        RankingSnapshotManifest, content, _its(MANIFEST), "ranking snapshot manifest", refused
    )
    if manifest.outcome != "completed":
        raise _not_a_snapshot(
            name,
            "its manifest's outcome is failed: its rank_get didn't give a definition Trial Folio"
            " saved.",
        )
    return manifest


def _check_version(name: SnapshotName, version: object, path: str) -> None:
    """Checks the schema version a snapshot's manifest or record holds: one this version reads."""
    check_version(
        version,
        _READABLE,
        _its(path),
        _refused(name),
        lambda: _unknown_version(name, path, "it has"),
    )


def _its(path: str) -> str:
    """How a message names the snapshot's file at `path`, as in "its `snapshot.json`"."""
    return f"its {named(path)}"


_TAKE_ONE: Final = (
    "Name the directory of a snapshot that finished, as trialfolio run of a ranking snapshot"
    " configuration wrote it. Nothing was sent, and no output was created."
)


def _refused(name: SnapshotName) -> Refused:
    """Makes `input.not_a_run` for the snapshot `name` names, for a problem."""
    return lambda problem: _not_a_snapshot(name, problem)


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
