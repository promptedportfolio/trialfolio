"""Reads configuration files: YAML text in, validated models out (docs/contracts.md,
configuration files). `read_screen_configuration` reads a `kind: screen` file,
`read_review_configuration` a `kind: review` one, and `read_experiment_configuration` a
`kind: experiment` one. `read_run_configuration` reads the configuration `trialfolio run` takes, a
screen's, an experiment's, or, from release 0.4.0, a ranking snapshot's, choosing the reader by
its `kind` (D-24).

Release 0.4.0's readers read its versions too: `read_screen_configuration_v1_1` reads a screen
configuration 1.0.0 or 1.1.0, `read_experiment_configuration_v1_1` an experiment configuration
1.0.0 or 1.1.0, each by its `schema_version`, and `read_ranking_snapshot_configuration` a
`kind: ranking-snapshot` file. Version 1.1.0 adds a ranking given as a ranking system's
definition or a ranking snapshot, and ranking variants. `trialfolio run` reads a screen's and an
experiment's configuration with 0.4.0's readers, from release 0.4.0's R04-T12, so it reads 1.1.0
too, and tells a 1.0.0 file that a key it gives needs 1.1.0; and a ranking snapshot
configuration from R04-T10. 0.3.0's readers, which read 1.0.0 only, give 0.3.0's messages, and
only 0.4.0's readers read a ranking variant's node paths, below.

0.4.0's readers of a screen and an experiment take the configuration file's path too, and read
the definition file its `ranking.definition`, or its baseline's, names, from the configuration's
directory, once, in step 2, by the rules of `trialfolio.ranking_definitions` (docs/contracts.md,
ranking definitions). A ranking named by a snapshot is read the same way, from the snapshot's
directory, by `trialfolio.snapshots`: it's complete, and can be a ranking, and its definition
is its `definition.xml`, with the ranking method its record gives (ranking snapshot output,
reading a snapshot). An experiment's reader then applies each ranking variant to the baseline's
definition, which gives each ranking variant's case its definition (ranking variants). They give
the configuration with what they read: `ScreenConfigurationRead` and
`ExperimentConfigurationRead`.

Reading is a named adapter step before model validation (ADR 0002): `trialfolio.strict_yaml`
reads the file's YAML into plain values, refusing ambiguous forms, and each reader then checks
the rules of its kind, and validates the values as its model. The readers' own rules of the YAML:

- In a screen configuration, the text Portfolio123 receives must be quoted or a block scalar:
  each rule, the ranking's `formula` or `name`, the universe, and the benchmark. A plain one is
  rejected, because outside quotes YAML reads a space and `#` as the start of a comment, so
  `name: Core Combo #2` would send `Core Combo`, and Portfolio123 formulas can hold `#`, as in
  `#Industry`. Fixed words, such as `open`, and the title and purpose, which are never sent, may
  be plain. In an experiment configuration, the same holds for the baseline's text, and for each
  rule variant's `add`, `replace`, and `with`, which are written as rules are. In a ranking
  snapshot configuration, it holds for `system`.
- In 0.4.0's readers, a ranking variant's node paths, the keys of its `set` and its `remove`,
  are quoted too, since a node's name can hold a space and `#` (node paths). They hold the
  user's strategy definition, so every message of those readers names a `set` entry by its
  place, such as `variants.ranking[0].set[1]`, never by its path. 0.3.0's readers, for which
  `ranking` isn't a setting a variant may change, read those keys as they read any other.

`experiment_schema_version` gives the schema version an experiment configuration declares, once
its YAML rules and its `kind` are checked, and before anything else is.

`original_values` gives each top-level value's text exactly as the file writes it, for
`settings.csv`'s `original_value` (docs/contracts.md, settings.csv), and
`experiment_original_values` an experiment case's, with the key path that writes each one, such
as `baseline.max_holdings` or `variants.max_holdings[0].value` (an experiment's normalized
tables). For a configuration 0.4.0's readers read, `screen_original_values_v1_1` and
`experiment_original_values_v1_1` give the same, and each weight row's original key and value,
by its node's canonical path: the definition's `Weight` attribute, or the `set` entry of a
ranking variant that changes it (weight rows).

The core reads no file, so 0.4.0's readers can also be given a definition's bytes, or a
snapshot's two files', read when the configuration was validated, in place of reading the file or
the directory it names again: the executors check the configuration they're given that way, and
copy those bytes (ranking definitions, reading a snapshot).

Error messages name the offending key and never include its value, so they're safe to log. A
key's control and formatting characters and lone surrogates are written as escapes.
`trialfolio.configuration_messages` gives the messages of a model's errors, and of text written
without quotes.

`__all__` lists the public names this module had before `trialfolio.strict_yaml` was split out of
it, so each still imports from here: among them `KeyPath` and the YAML reader's limits,
`CREDENTIAL_WORDS`, `MAX_DIGITS`, and `MAX_DEPTH`, which `strict_yaml` now defines.
"""

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from pydantic import BaseModel, ValidationError

from trialfolio.configuration_messages import (
    fail,
    is_node_path,
    model_problems,
    names_by_place,
    unquoted_text,
)
from trialfolio.contracts.common import BASELINE_CASE_KEY
from trialfolio.contracts.experiment_configuration import (
    EXPERIMENT_SCHEMA_VERSIONS,
    EXPERIMENT_SCHEMA_VERSIONS_V1_1,
    VARIANT_SETTINGS,
    VARIANT_SETTINGS_V1_1,
    ConfiguredVariantV1_1,
    ExperimentConfiguration,
    ExperimentConfigurationV1_1,
    RankingVariant,
    RuleVariant,
    configured_variants,
    configured_variants_v1_1,
)
from trialfolio.contracts.ranking_snapshot_configuration import (
    RANKING_SNAPSHOT_SCHEMA_VERSIONS,
    RankingSnapshotConfiguration,
)
from trialfolio.contracts.review_configuration import REVIEW_SCHEMA_VERSIONS, ReviewConfiguration
from trialfolio.contracts.screen_configuration import (
    LATER_VERSIONS,
    SCREEN_SCHEMA_VERSIONS,
    SCREEN_SCHEMA_VERSIONS_V1_1,
    DefinitionRanking,
    RankingV1_1,
    ScreenConfiguration,
    ScreenConfigurationV1_1,
    SnapshotRanking,
)
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS
from trialfolio.display import visible
from trialfolio.errors import TrialFolioError, reason_of
from trialfolio.paths import resolve_existing
from trialfolio.ranking_definitions import (
    DefinitionProblem,
    RankingCase,
    RankingDefinition,
    VariantProblem,
    apply_ranking_variant,
    read_definition,
)
from trialfolio.snapshots import (
    NotARanking,
    SnapshotFiles,
    SnapshotName,
    SnapshotRead,
    read_snapshot,
    snapshot_from,
)
from trialfolio.storage import LocalArtifactStore
from trialfolio.strict_yaml import (
    CREDENTIAL_WORDS,
    MAX_DEPTH,
    MAX_DIGITS,
    KeyPath,
    ReadYaml,
    YamlRefused,
    format_path,
    read_yaml,
)

__all__ = [
    "CREDENTIAL_WORDS",
    "MAX_DEPTH",
    "MAX_DIGITS",
    "ExperimentConfigurationRead",
    "KeyPath",
    "ScreenConfigurationRead",
    "WeightOriginal",
    "experiment_original_values",
    "experiment_original_values_v1_1",
    "experiment_schema_version",
    "original_values",
    "read_experiment_configuration",
    "read_experiment_configuration_v1_1",
    "read_ranking_snapshot_configuration",
    "read_review_configuration",
    "read_run_configuration",
    "read_screen_configuration",
    "read_screen_configuration_v1_1",
    "screen_original_values_v1_1",
]


def read_screen_configuration(content: bytes, source_name: str) -> ScreenConfiguration:
    """Reads a screen configuration 1.0.0 from the bytes of a file, named `source_name` in
    messages.

    Raises `TrialFolioError` with `config.invalid` when the file breaks any rule of the screen
    configuration. The message lists each problem, names its key, and includes no value. It's
    0.3.0's, for a ranking given as a definition or a snapshot too: `read_screen_configuration_v1_1`
    is release 0.4.0's, which `trialfolio run` reads with.
    """
    return _read_configuration(
        ScreenConfiguration, content, source_name, "screen", SCREEN_SCHEMA_VERSIONS, _is_sent_text
    )


@dataclass(frozen=True)
class ScreenConfigurationRead:
    """A screen configuration, as 0.4.0's reader reads it in step 2: its model, and the
    definition its ranking names."""

    configuration: ScreenConfiguration | ScreenConfigurationV1_1
    definition: RankingDefinition | None
    """The definition `ranking.definition` names, read and checked, with the bytes it was read
    from, which a plan's `definition.xml` copies, or the definition of the snapshot
    `ranking.snapshot` names; None for every other ranking form."""
    snapshot: SnapshotRead | None = None
    """The snapshot `ranking.snapshot` names, read and checked, whose definition `definition`
    is; None for every other ranking form."""


@dataclass(frozen=True)
class ExperimentConfigurationRead:
    """An experiment configuration, as 0.4.0's reader reads it in step 2: its model, the
    definition its baseline's ranking names, and each ranking variant's case."""

    configuration: ExperimentConfiguration | ExperimentConfigurationV1_1
    definition: RankingDefinition | None
    """The baseline's definition, as `ScreenConfigurationRead.definition` gives a screen's."""
    ranking_cases: tuple[RankingCase, ...]
    """Each ranking variant's case, in the order of `variants.ranking`, with its definition:
    the baseline's, with the variant's change. Empty without a definition."""
    snapshot: SnapshotRead | None = None
    """The snapshot the baseline's `ranking.snapshot` names, as `ScreenConfigurationRead.snapshot`
    gives a screen's."""


def read_screen_configuration_v1_1(
    content: bytes,
    source_name: str,
    path: str | os.PathLike[str],
    *,
    definition: bytes | None = None,
    snapshot: SnapshotFiles | None = None,
    files: bool = True,
) -> ScreenConfigurationRead:
    """Reads a screen configuration of a version release 0.4.0 reads, 1.0.0 or 1.1.0, by its
    `schema_version`, from the bytes of the file at `path`, named `source_name` in messages.
    Version 1.1.0's `ranking` may also be a definition, named by its file's path, with its
    `ranking_method`, or a snapshot, named by its directory's path. A definition's file, and a
    snapshot's directory, are read from `path`'s directory, unless the path is absolute, and
    checked (ranking definitions, reading a snapshot).

    Raises `TrialFolioError` with `config.invalid` as `read_screen_configuration` does, and
    for a definition that breaks a rule, a path that names something other than a file, or a
    snapshot that can't be a ranking; with `input.not_found` when nothing exists where the
    definition's path or the snapshot's leads, or the file there can't be read; and with
    `input.not_a_run` or `artifact.unknown_schema_version` when the snapshot isn't complete. A
    1.0.0 file that gives `definition` or `snapshot` is told they need `schema_version` 1.1.0.

    `definition` is the bytes of the file `ranking.definition` names, and `snapshot` those of the
    two files of the snapshot `ranking.snapshot` names, read when the configuration was
    validated: they're read in their place, and no file is read. Raises `ValueError` when either
    is given for a configuration whose ranking doesn't name its kind, or a snapshot's files
    given can't be a ranking. With `files` false, as the core reads the configuration of a plan
    without a ranking definition, it reads no file either: a ranking given as a definition, or
    named by a snapshot, without their bytes, is a `ValueError` (release 0.4.0's R04-T12).
    """
    document, plain = _read_document(
        content, source_name, "screen", SCREEN_SCHEMA_VERSIONS_V1_1, node_paths=True
    )
    unquoted = _unquoted(plain, _is_sent_text)
    if document["schema_version"] == "1.0.0":
        configuration = _validated(
            ScreenConfiguration, document, source_name, unquoted, later_versions=True
        )
        _no_definition_given(definition, snapshot)
        return ScreenConfigurationRead(configuration, None)
    read = _validated(ScreenConfigurationV1_1, document, source_name, unquoted)
    _no_files(read.ranking, files, definition, snapshot)
    ranking = _ranking_read(read.ranking, "ranking", source_name, path, definition, snapshot)
    return ScreenConfigurationRead(read, *ranking)


def read_review_configuration(content: bytes, source_name: str) -> ReviewConfiguration:
    """Reads a review configuration from the bytes of a file, named `source_name` in messages.

    Raises `TrialFolioError` with `config.invalid` when the file breaks any rule of the review
    configuration. The message lists each problem, names its key, and includes no value. A review
    sends nothing to Portfolio123, so its text may be written without quotes.
    """
    return _read_configuration(
        ReviewConfiguration, content, source_name, "review", REVIEW_SCHEMA_VERSIONS
    )


def read_experiment_configuration(content: bytes, source_name: str) -> ExperimentConfiguration:
    """Reads an experiment configuration from the bytes of a file, named `source_name` in
    messages.

    Raises `TrialFolioError` with `config.invalid` when the file breaks any rule of the experiment
    configuration. The message lists each problem, names its key, or a variant by its place, such
    as `variants.max_holdings[0]`, and includes no value: never a variant's key either, which is
    the user's text. It's 0.3.0's, for a ranking variant, or a baseline ranked by a definition or a
    snapshot, too, and so is how it reads a ranking variant's keys:
    `read_experiment_configuration_v1_1` is release 0.4.0's, which `trialfolio run` reads with.
    """
    return _read_configuration(
        ExperimentConfiguration,
        content,
        source_name,
        "experiment",
        EXPERIMENT_SCHEMA_VERSIONS,
        _is_sent_experiment_text,
    )


def read_experiment_configuration_v1_1(
    content: bytes,
    source_name: str,
    path: str | os.PathLike[str],
    *,
    definition: bytes | None = None,
    snapshot: SnapshotFiles | None = None,
    files: bool = True,
) -> ExperimentConfigurationRead:
    """Reads an experiment configuration of a version release 0.4.0 reads, 1.0.0 or 1.1.0, by its
    `schema_version`, from the bytes of the file at `path`, named `source_name` in messages.
    Version 1.1.0's baseline may be ranked by a definition or a snapshot, and then its
    `variants` may hold ranking variants, and its budget is at least two requests a case. The
    baseline's definition is read as `read_screen_configuration_v1_1` reads a screen's, and each
    ranking variant is applied to it (ranking variants).

    Raises `TrialFolioError` as `read_screen_configuration_v1_1` does, and with `config.invalid`
    for each ranking variant that breaks a rule. Every message names a ranking variant's `set`
    entry by its place, such as `variants.ranking[0].set[1]`, never by its path. A 1.0.0 file
    with a ranking variant, or a baseline ranked by a definition or a snapshot, is told they need
    `schema_version` 1.1.0.

    `definition` is the bytes of the baseline's definition file, and `snapshot` those of its
    snapshot's two files, as `read_screen_configuration_v1_1` takes a screen's, and `files` is
    as that function takes it.
    """
    document, plain = _read_document(
        content, source_name, "experiment", EXPERIMENT_SCHEMA_VERSIONS_V1_1, node_paths=True
    )
    unquoted = _unquoted(plain, _is_sent_experiment_text_v1_1)
    if document["schema_version"] == "1.0.0":
        configuration = _validated(
            ExperimentConfiguration, document, source_name, unquoted, later_versions=True
        )
        _no_definition_given(definition, snapshot)
        return ExperimentConfigurationRead(configuration, None, ())
    read = _validated(
        ExperimentConfigurationV1_1,
        document,
        source_name,
        unquoted,
        variant_settings=VARIANT_SETTINGS_V1_1,
    )
    _no_files(read.baseline.ranking, files, definition, snapshot)
    baseline, read_snapshot = _ranking_read(
        read.baseline.ranking, "baseline.ranking", source_name, path, definition, snapshot
    )
    return ExperimentConfigurationRead(
        read, baseline, _ranking_cases(read, baseline, source_name), read_snapshot
    )


def _no_definition_given(definition: bytes | None, snapshot: SnapshotFiles | None = None) -> None:
    if definition is not None:
        raise ValueError("a definition's bytes are given only for a ranking given as a definition")
    if snapshot is not None:
        raise ValueError("a snapshot's files are given only for a ranking named by a snapshot")


def _no_files(
    ranking: RankingV1_1, files: bool, definition: bytes | None, snapshot: SnapshotFiles | None
) -> None:
    """Without `files`, a ranking that names a file or a directory, given without its bytes, is a
    `ValueError`, so the reader reads no file."""
    named = isinstance(ranking, DefinitionRanking | SnapshotRanking)
    if not files and named and definition is None and snapshot is None:
        raise ValueError("the configuration's ranking names a file, which isn't read here")


def _ranking_read(
    ranking: RankingV1_1,
    key: str,
    source_name: str,
    path: str | os.PathLike[str],
    definition: bytes | None,
    snapshot: SnapshotFiles | None,
) -> tuple[RankingDefinition | None, SnapshotRead | None]:
    """What a ranking given as a definition, or named by a snapshot, reads: the definition, and
    the snapshot whose definition it is. Neither for any other form."""
    if not isinstance(ranking, SnapshotRanking):
        _no_definition_given(None, snapshot)
        return _definition(ranking, key, source_name, path, definition), None
    _no_definition_given(definition)
    read = _snapshot(ranking, key, source_name, path, snapshot)
    return read.definition, read


def _snapshot(
    ranking: SnapshotRanking,
    key: str,
    source_name: str,
    path: str | os.PathLike[str],
    given: SnapshotFiles | None,
) -> SnapshotRead:
    """The snapshot a ranking names, read once from its directory, at the one path the file
    system resolves, from the configuration's directory unless the path is absolute, and checked
    (reading a snapshot); or from `given`, its two files' bytes, read already."""
    where = f"{key}.snapshot"
    if given is not None:
        try:
            return snapshot_from(given)
        except NotARanking as refused:
            raise ValueError("the snapshot's files given can't be a ranking") from refused
    shown = visible(ranking.snapshot)
    try:
        resolved = resolve_existing(Path(path).parent / ranking.snapshot)
    except OSError as error:
        reason = reason_of(error)
        raise TrialFolioError(
            "input.not_found",
            f"{source_name}: couldn't read the directory `{where}` names (`{shown}`): {reason}.",
            f"{source_name}: couldn't read the directory `{where}` names: {reason}.",
        ) from None
    if resolved is None:
        raise TrialFolioError(
            "input.not_found",
            f"{source_name}: the directory `{where}` names (`{shown}`) doesn't exist. {_SNAPSHOT_PATH}",
            f"{source_name}: the directory `{where}` names doesn't exist. {_SNAPSHOT_PATH}",
        )
    name = SnapshotName(
        shown=f"{source_name}: the directory `{where}` names (`{shown}`)",
        logged=f"{source_name}: the directory `{where}` names",
    )
    try:
        return read_snapshot(LocalArtifactStore(resolved), name)
    except NotARanking as refused:
        fail(
            source_name, [f"`{where}` names a snapshot {problem}." for problem in refused.problems]
        )


_SNAPSHOT_PATH: Final = (
    "A snapshot's path is read from the configuration's directory, unless it's absolute: give the"
    " directory trialfolio run of a ranking snapshot configuration wrote."
)


def _definition(
    ranking: RankingV1_1,
    key: str,
    source_name: str,
    path: str | os.PathLike[str],
    given: bytes | None = None,
) -> RankingDefinition | None:
    """The definition a ranking given as a definition names, read once from its file, at the
    one path the file system resolves, from the configuration's directory unless the path is
    absolute, and checked (docs/contracts.md, ranking definitions); or from `given`, its bytes,
    read already. None for any form but a definition and a snapshot, which `_snapshot` reads."""
    if not isinstance(ranking, DefinitionRanking):
        _no_definition_given(given)
        return None
    where = f"{key}.definition"
    if given is not None:
        return _checked_definition(given, source_name, where)
    shown = visible(ranking.definition)
    try:
        resolved = resolve_existing(Path(path).parent / ranking.definition)
    except OSError as error:
        # The file system can't follow the path, such as through a folder the user may not
        # search, so a file there, if there is one, can't be read.
        raise _unreadable(source_name, where, shown, error) from None
    if resolved is None:
        raise TrialFolioError(
            "input.not_found",
            f"{source_name}: the file `{where}` names (`{shown}`) doesn't exist. "
            f"{_DEFINITION_PATH}",
            f"{source_name}: the file `{where}` names doesn't exist. {_DEFINITION_PATH}",
        )
    if not os.path.isfile(resolved):
        fail(
            source_name,
            [
                f"`{where}` names something that isn't a file, such as a directory. {_DEFINITION_PATH}"
            ],
        )
    try:
        definition = Path(resolved).read_bytes()
    except OSError as error:
        raise _unreadable(source_name, where, shown, error) from None
    return _checked_definition(definition, source_name, where)


def _checked_definition(content: bytes, source_name: str, where: str) -> RankingDefinition:
    """The definition in `content`, read and checked: `config.invalid` names `where`, the key that
    names it, when it breaks a rule."""
    try:
        return read_definition(content)
    except DefinitionProblem as problem:
        at = "" if problem.line is None else f", at line {problem.line}"
        fail(
            source_name,
            [f"`{where}` names a definition Trial Folio can't read{at}: {problem.problem}."],
        )


_DEFINITION_PATH: Final = (
    "A definition's path is read from the configuration's directory, unless it's absolute: give "
    "the path of the file that holds the ranking system's definition, the XML the website's Text "
    "Editor shows."
)


def _unreadable(source_name: str, where: str, given: str, error: OSError) -> TrialFolioError:
    """`input.not_found` for a definition's file that can't be read, with the reason, as a
    configuration file that can't be read gives it; the logged message leaves out the path."""
    reason = reason_of(error)
    return TrialFolioError(
        "input.not_found",
        f"{source_name}: couldn't read the file `{where}` names (`{given}`): {reason}.",
        f"{source_name}: couldn't read the file `{where}` names: {reason}.",
    )


def _ranking_cases(
    configuration: ExperimentConfigurationV1_1,
    definition: RankingDefinition | None,
    source_name: str,
) -> tuple[RankingCase, ...]:
    """Each ranking variant's case, by the rules of ranking variants, from the baseline's
    definition, its file's or its snapshot's. Without one, there's no ranking variant: the model
    allows one only with a baseline ranked by a definition or a snapshot. Raises
    `TrialFolioError` with `config.invalid` listing the first problem of each variant that breaks
    a rule, and each variant whose definition another's gives already, byte for byte."""
    variants = configuration.variants
    listed = () if variants is None or variants.ranking is None else variants.ranking
    if definition is None:
        if listed:  # the model's rule, which a reader's result keeps
            raise ValueError("a ranking variant needs the baseline's definition")
        return ()
    problems: list[str] = []
    cases: list[RankingCase] = []
    for number, variant in enumerate(listed):
        place = f"variants.ranking[{number}]"
        try:
            cases.append(apply_ranking_variant(definition, variant, place))
        except VariantProblem as problem:
            problems.append(f"`{problem.where}` {problem.problem}.")
    first: dict[str, RankingCase] = {}
    for case in cases:
        earlier = first.setdefault(case.definition.text, case)
        if earlier is not case:
            problems.append(
                f"`{case.place}` gives the same definition as `{earlier.place}`, so the two "
                "would be one case. Each case has settings of its own."
            )
    if problems:
        fail(source_name, problems)
    return tuple(cases)


def read_ranking_snapshot_configuration(
    content: bytes, source_name: str
) -> RankingSnapshotConfiguration:
    """Reads a ranking snapshot configuration, `kind: ranking-snapshot`, from the bytes of a file
    named `source_name` in messages (docs/contracts.md, ranking snapshot configuration).

    Raises `TrialFolioError` with `config.invalid` when the file breaks any rule of the snapshot
    configuration, or of every configuration file. `system`, the name Portfolio123 receives, is
    written in quotes or as a block scalar. The message names each key, and includes no value.
    """
    return _read_configuration(
        RankingSnapshotConfiguration,
        content,
        source_name,
        "ranking-snapshot",
        RANKING_SNAPSHOT_SCHEMA_VERSIONS,
        lambda path: path == ("system",),
        node_paths=True,
    )


def _read_configuration[M: BaseModel](
    model: type[M],
    content: bytes,
    source_name: str,
    kind: str,
    versions: tuple[str, ...],
    quoted: Callable[[KeyPath], bool] | None = None,
    *,
    node_paths: bool = False,
) -> M:
    """A configuration of `kind`, of one of `versions`, which `model` validates: the steps of a
    reader of one model, `_read_document`'s, then `_validated`'s, with a problem for each text
    written without quotes that `quoted` says must be quoted, none without it."""
    document, plain = _read_document(content, source_name, kind, versions, node_paths=node_paths)
    unquoted = [] if quoted is None else _unquoted(plain, quoted)
    return _validated(model, document, source_name, unquoted)


def _validated[M: BaseModel](
    model: type[M],
    document: dict[str, object],
    source_name: str,
    unquoted: list[str],
    *,
    variant_settings: tuple[str, ...] = VARIANT_SETTINGS,
    later_versions: bool = False,
) -> M:
    """`document` validated as `model`. Raises `TrialFolioError` with `config.invalid`, listing
    each problem the model finds, then each text written without quotes. `variant_settings` are
    the settings the file's version lets a variant change. With `later_versions`, as 0.4.0's
    readers read a 1.0.0 file, a key that only 1.1.0 allows is told it needs that version;
    without it, the messages are 0.3.0's."""
    context = {LATER_VERSIONS: True} if later_versions else None
    try:
        configuration = model.model_validate(document, context=context)
    except ValidationError as error:
        problems = model_problems(error, document, variant_settings, later_versions=later_versions)
        fail(source_name, problems + unquoted)
    if unquoted:
        fail(source_name, unquoted)
    return configuration


def _unquoted(plain: Sequence[KeyPath], quoted: Callable[[KeyPath], bool]) -> list[str]:
    """A message for each text in `plain`, written without quotes, that must be quoted."""
    return [unquoted_text(path) for path in plain if quoted(path)]


def read_run_configuration(
    content: bytes, source_name: str, path: str | os.PathLike[str]
) -> ScreenConfigurationRead | ExperimentConfigurationRead | RankingSnapshotConfiguration:
    """Reads the configuration `trialfolio run` takes, from the bytes of the file at `path`,
    named `source_name` in messages: a screen configuration or an experiment configuration, 1.0.0
    or 1.1.0, with release 0.4.0's readers, which read the definition file, or the snapshot's
    directory, its ranking names, from `path`'s directory; or, from release 0.4.0, a ranking
    snapshot configuration; by its `kind` (D-24, D-36). Release 0.4.0's R04-T12 made it read the
    screen's and the experiment's with 0.4.0's readers, where it had read them with 0.3.0's.

    Raises `TrialFolioError` as the reader of its kind does. A file that breaks a YAML rule, isn't
    a mapping, or whose `kind` is missing or is none of them, such as `review`, fails with
    `config.invalid` before any reads it, and the message names the three kinds.
    """
    # Read with node paths, as 0.4.0's readers read, so a ranking variant's `set` keys follow
    # their rules here too, and a message names an entry by its place, never by its path.
    document, _ = _read_kind(
        content, source_name, ("screen", "experiment", "ranking-snapshot"), node_paths=True
    )
    if document["kind"] == "experiment":
        return read_experiment_configuration_v1_1(content, source_name, path)
    if document["kind"] == "ranking-snapshot":
        return read_ranking_snapshot_configuration(content, source_name)
    return read_screen_configuration_v1_1(content, source_name, path)


def experiment_schema_version(content: bytes, source_name: str) -> object:
    """The `schema_version` an experiment configuration gives, as `read_experiment_configuration`
    reads it before it checks that the version is supported: the key's value, or None when the
    file has no such key. So a reader of an experiment's records can tell a saved configuration
    whose version it has no reader for (docs/contracts.md, artifact compatibility).

    Raises `TrialFolioError` with `config.invalid` when the file breaks a YAML rule, isn't a
    mapping, or isn't `kind: experiment`, as that function does.
    """
    document, _ = _read_kind(content, source_name, ("experiment",))
    return document.get("schema_version")


def _read_document(
    content: bytes,
    source_name: str,
    kind: str,
    versions: tuple[str, ...],
    *,
    node_paths: bool = False,
) -> tuple[dict[str, object], tuple[KeyPath, ...]]:
    """The document of a configuration of `kind`, once its YAML rules, its `kind`, and its
    `schema_version` are checked; and where it writes text as a plain scalar. With `node_paths`,
    as 0.4.0's readers read, a ranking variant's `set` keys are read as node paths."""
    document, plain = _read_kind(content, source_name, (kind,), node_paths=node_paths)
    supported = ", ".join(versions)
    if "schema_version" not in document:
        fail(source_name, [f"`schema_version` is required. Supported versions: {supported}."])
    if document["schema_version"] not in versions:
        fail(
            source_name,
            [f"`schema_version` isn't a supported version. Supported versions: {supported}."],
        )
    return document, plain


def _read_kind(
    content: bytes, source_name: str, kinds: tuple[str, ...], *, node_paths: bool = False
) -> tuple[dict[str, object], tuple[KeyPath, ...]]:
    """The document of a configuration of one of `kinds`, once its YAML rules and its `kind` are
    checked; and where it writes text as a plain scalar. `node_paths` is `_read_document`'s."""
    read = _read_yaml(content, source_name, node_paths=node_paths)
    loaded = read.document
    if not isinstance(loaded, dict):
        fail(source_name, ["The file must be a mapping of keys to values."])
    document = cast("dict[str, object]", loaded)
    if "kind" not in document:
        named = [
            f"{'an' if kind[0] in 'aeiou' else 'a'} {kind} configuration has `kind: {kind}`"
            for kind in kinds
        ]
        listed = named[0] if len(named) == 1 else f"{', '.join(named[:-1])}, and {named[-1]}"
        fail(source_name, [f"`kind` is required. {listed[0].upper()}{listed[1:]}."])
    if document["kind"] not in kinds:
        choices = (
            " or ".join(kinds) if len(kinds) <= 2 else f"{', '.join(kinds[:-1])}, or {kinds[-1]}"
        )
        fail(source_name, [f"`kind` must be {choices}."])
    return document, read.plain_text


def original_values(content: bytes, source_name: str) -> Mapping[str, str]:
    """Each top-level key's value as the file writes it, by key: its text from its first
    character to its last one that isn't YAML white space or a line break. That keeps quotes,
    block indicators, and, inside a block list or mapping, the line breaks, indentation, and
    comments between its items (docs/contracts.md, settings.csv's `original_value`).

    For a file `read_screen_configuration` accepted. Raises `TrialFolioError` with
    `config.invalid` when the file breaks a YAML rule, as that function does.
    """
    return _read_yaml(content, source_name).originals


def experiment_original_values(
    content: bytes, source_name: str, case_key: str
) -> Mapping[str, tuple[str, str]]:
    """For the case `case_key` of an experiment configuration, each setting that a key of the file
    writes, with that key's path and its value's text as the file writes it, as `original_values`
    gives a screen's (docs/contracts.md, an experiment's normalized tables):

    - **The setting the case's variant changes:** the variant's change, such as
      `variants.max_holdings[0].value`, or, for a rule, `variants.rules[0].add` or
      `variants.rules[0].with`.
    - **Every other setting:** the baseline's key, such as `baseline.max_holdings`.
    - **The default variant's `rebalance_weeks`,** which no key writes, and a setting no key
      writes in a screen configuration either: left out.

    For a file `read_experiment_configuration` accepted. Raises `TrialFolioError` with
    `config.invalid` when the file isn't valid, and `ValueError` when it has no case keyed
    `case_key`.
    """
    configuration = read_experiment_configuration(content, source_name)
    values = _read_yaml(content, source_name).values
    variant = None
    if case_key != BASELINE_CASE_KEY:
        found = [v for v in configured_variants(configuration) if v.key == case_key]
        if not found:
            raise ValueError("the configuration has no case with this key")
        (variant,) = found
    originals: dict[str, tuple[str, str]] = {}
    for setting in SCREEN_SETTINGS:
        key = f"baseline.{setting.name}"
        if variant is not None and setting.name == variant.setting:
            if variant.place is None:
                continue  # The default variant, whose value no key writes.
            change = variant.variant
            if isinstance(change, RuleVariant):
                key = f"{variant.place}.{'add' if change.add is not None else 'with'}"
            else:
                key = f"{variant.place}.value"
        text = values.get(key)
        if text is not None:
            originals[setting.name] = (key, text)
    return originals


@dataclass(frozen=True)
class WeightOriginal:
    """Where a weight row's value comes from, for `settings.csv` (docs/contracts.md, weight rows):
    the key that names it and its text there, and whether that's the definition's copy,
    `definition.xml`, or the configuration."""

    key: str
    """`ranking.definition` or `ranking.snapshot`, `baseline.ranking.definition` or
    `baseline.ranking.snapshot`, or a ranking variant's `set` entry's place, such as
    `variants.ranking[0].set[1]`."""
    text: str
    """The node's `Weight` attribute as the definition writes it, between its quotes, or the
    `set` entry's weight as the configuration writes it."""
    in_definition: bool
    """Whether the definition gives it, so its source is the copy of the definition."""


def screen_original_values_v1_1(
    content: bytes, source_name: str, read: ScreenConfigurationRead
) -> tuple[Mapping[str, str], Mapping[str, WeightOriginal]]:
    """For a screen configuration that `read_screen_configuration_v1_1` read, as `read`, from
    `content`: each top-level value's text, as `original_values` gives it, and, for a ranking
    given as a definition, each weight row's original, by its node's canonical path, from the
    definition, named by `ranking.definition`, or `ranking.snapshot` for a snapshot's."""
    originals = original_values(content, source_name)
    if read.definition is None:
        return originals, {}
    key = "ranking.definition" if read.snapshot is None else "ranking.snapshot"
    return originals, _definition_weights(read.definition, key)


def experiment_original_values_v1_1(
    content: bytes, source_name: str, read: ExperimentConfigurationRead, case_key: str
) -> tuple[Mapping[str, tuple[str, str]], Mapping[str, WeightOriginal]]:
    """For the case `case_key` of an experiment configuration that
    `read_experiment_configuration_v1_1` read, as `read`, from `content`: each setting's key path
    and text, as `experiment_original_values` gives them, with a ranking variant's `ranking`
    row's as its entry, `variants.ranking[<i>]`, and its text; and, for a baseline ranked by a
    definition, each weight row's original, by its node's canonical path in the case's
    definition. A weight the case's ranking variant changes comes from its `set` entry, and every
    other from the baseline's definition, named by `baseline.ranking.definition`.

    Raises `ValueError` when the configuration has no case keyed `case_key`.
    """
    configuration = read.configuration
    if isinstance(configuration, ExperimentConfiguration):
        return experiment_original_values(content, source_name, case_key), {}
    values = _read_yaml(content, source_name, node_paths=True).values
    variant = None
    if case_key != BASELINE_CASE_KEY:
        found = [v for v in configured_variants_v1_1(configuration) if v.key == case_key]
        if not found:
            raise ValueError("the configuration has no case with this key")
        (variant,) = found
    originals: dict[str, tuple[str, str]] = {}
    for setting in SCREEN_SETTINGS:
        key = _original_key(setting.name, variant)
        text = None if key is None else values.get(key)
        if key is not None and text is not None:
            originals[setting.name] = (key, text)
    return originals, _experiment_weights(read, values, variant)


def _original_key(setting: str, variant: ConfiguredVariantV1_1 | None) -> str | None:
    """The key that writes the setting's value for a case of `variant`, or the baseline's case;
    None for the default variant's `rebalance_weeks`, which no key writes."""
    if variant is None or setting != variant.setting:
        return f"baseline.{setting}"
    if variant.place is None:
        return None
    change = variant.variant
    if isinstance(change, RankingVariant):
        return variant.place
    if isinstance(change, RuleVariant):
        return f"{variant.place}.{'add' if change.add is not None else 'with'}"
    return f"{variant.place}.value"


def _definition_weights(definition: RankingDefinition, key: str) -> dict[str, WeightOriginal]:
    return {node.path: WeightOriginal(key, node.weight_text, True) for node in definition.nodes}


def _experiment_weights(
    read: ExperimentConfigurationRead,
    values: Mapping[str, str],
    variant: ConfiguredVariantV1_1 | None,
) -> dict[str, WeightOriginal]:
    """Each weight row's original for a case of `variant`, by its node's canonical path in the
    case's definition: the baseline's definition's, but for each weight a ranking variant's `set`
    changes. A removal leaves the other nodes in the baseline's order, so the case's nodes are
    the baseline's, without the factor removed."""
    baseline = read.definition
    if baseline is None:
        return {}
    key = "baseline.ranking.definition" if read.snapshot is None else "baseline.ranking.snapshot"
    if variant is None or not isinstance(variant.variant, RankingVariant):
        return _definition_weights(baseline, key)
    case = next(c for c in read.ranking_cases if c.place == variant.place)
    weights = _definition_weights(case.definition, key)
    removed = None if case.remove is None else case.remove.index
    kept = [node for node in baseline.nodes if node.index != removed]
    in_case = {node.index: own for node, own in zip(kept, case.definition.nodes, strict=True)}
    for entry in case.set:
        if entry.weight != entry.node.weight:
            node = in_case[entry.node.index]
            weights[node.path] = WeightOriginal(entry.place, values[entry.place], False)
    return weights


_SENT_TEXT: Final = frozenset(
    {("universe",), ("benchmark",), ("ranking", "formula"), ("ranking", "name")}
)
"""The free text Portfolio123 receives, besides the rules: names, symbols, and the formula."""


def _is_sent_text(path: KeyPath) -> bool:
    """Free text a screen configuration sends to Portfolio123: each rule, the ranking's formula or
    name, the universe, and the benchmark."""
    return path in _SENT_TEXT or (
        len(path) == 2 and path[0] == "rules" and isinstance(path[1], int)
    )


_RULE_CHANGES: Final = frozenset({"add", "replace", "with"})
"""A rule variant's keys, whose text is written as rules are."""


def _is_sent_experiment_text(path: KeyPath) -> bool:
    """An experiment configuration's text that's written as the text Portfolio123 receives: the
    baseline's, as a screen configuration's, and each rule variant's `add`, `replace`, and
    `with`."""
    if path[:1] == ("baseline",):
        return _is_sent_text(path[1:])
    return (
        len(path) == 4
        and path[:2] == ("variants", "rules")
        and isinstance(path[2], int)
        and path[3] in _RULE_CHANGES
    )


def _is_sent_experiment_text_v1_1(path: KeyPath) -> bool:
    """The text 0.4.0's reader of an experiment configuration has written as the text
    Portfolio123 receives: 0.3.0's, and each node path of a ranking variant, its `set`'s keys
    and its `remove`."""
    return _is_sent_experiment_text(path) or is_node_path(path)


def _read_yaml(content: bytes, source_name: str, *, node_paths: bool = False) -> ReadYaml:
    """The file's YAML, as `trialfolio.strict_yaml` reads it: with `node_paths`, as 0.4.0's
    readers read, a ranking variant's `set` is keyed by node paths. Raises `TrialFolioError` with
    `config.invalid` when the file breaks a rule of the YAML, naming its key, or the file."""
    try:
        return read_yaml(content, by_place=names_by_place if node_paths else None)
    except YamlRefused as error:
        where = f"`{format_path(error.path)}`" if error.path else "The file"
        fail(source_name, [f"{where} {error.problem}"])
