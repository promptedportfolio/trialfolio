"""Reads configuration files: YAML text in, validated models out (docs/contracts.md,
configuration files). `read_screen_configuration` reads a `kind: screen` file,
`read_review_configuration` a `kind: review` one, and `read_experiment_configuration` a
`kind: experiment` one. `read_run_configuration` reads the configuration `trialfolio run` takes, a
screen's or an experiment's, choosing the reader by its `kind` (D-24).

Release 0.4.0's readers read its versions too: `read_screen_configuration_v1_1` reads a screen
configuration 1.0.0 or 1.1.0, `read_experiment_configuration_v1_1` an experiment configuration
1.0.0 or 1.1.0, each by its `schema_version`, and `read_ranking_snapshot_configuration` a
`kind: ranking-snapshot` file. Version 1.1.0 adds a ranking given as a ranking system's
definition or a ranking snapshot, and ranking variants. Until the CLI's path for them is built
(R04-T10 and R04-T12), `trialfolio run` reads with 0.3.0's readers, which read 1.0.0 only, and
give 0.3.0's messages: only 0.4.0's readers tell a 1.0.0 file that a key it gives needs 1.1.0,
since `run` refuses 1.1.0 until then, and only they read a ranking variant's node paths, below.

0.4.0's readers of a screen and an experiment take the configuration file's path too, and read
the definition file its `ranking.definition`, or its baseline's, names, from the configuration's
directory, once, in step 2, by the rules of `trialfolio.ranking_definitions` (docs/contracts.md,
ranking definitions). An experiment's reader then applies each ranking variant to it, which
gives each ranking variant's case its definition (ranking variants). They give the configuration
with what they read: `ScreenConfigurationRead` and `ExperimentConfigurationRead`. A snapshot's
directory isn't read here: release 0.4.0's R04-T10 reads it, so until then a baseline named by a
snapshot has no definition here, and its ranking variants' paths are checked only for how
they're written.

Reading is a named adapter step before model validation (ADR 0002). It builds plain values from
PyYAML's parse events, never through PyYAML's constructors, so it decides what each scalar means:

- A quoted or block scalar is text.
- A plain scalar is resolved as a YAML 1.1 safe loader would resolve it, and kept only when that
  reading is unambiguous: `true` or `false`; an integer in plain decimal digits; a decimal in
  plain notation, as a `Decimal` read from its text; or a date written `YYYY-MM-DD`. Any other
  form a YAML 1.1 loader would convert, such as `010`, `1:30`, `yes`, or `2.5e-1`, is rejected.
- Null values, duplicate keys, non-text keys, anchors, aliases, explicit tags, and credential-like
  keys are rejected.
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
tables).

Error messages name the offending key and never include its value, so they're safe to log. A
key's control and formatting characters and lone surrogates are written as escapes.
"""

import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Final, NoReturn, Protocol, cast

import yaml
from pydantic import BaseModel, ValidationError
from pydantic_core import ErrorDetails
from yaml.events import (
    AliasEvent,
    DocumentEndEvent,
    DocumentStartEvent,
    Event,
    MappingEndEvent,
    MappingStartEvent,
    NodeEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
    StreamEndEvent,
    StreamStartEvent,
)
from yaml.nodes import Node, ScalarNode

from trialfolio.contracts.common import (
    BASELINE_CASE_KEY,
    DATE_PATTERN,
    INTEGER_PATTERN,
    LABEL_PATTERN,
    NOT_BLANK,
)
from trialfolio.contracts.experiment_configuration import (
    EXPERIMENT_SCHEMA_VERSIONS,
    EXPERIMENT_SCHEMA_VERSIONS_V1_1,
    VARIANT_SETTINGS,
    VARIANT_SETTINGS_V1_1,
    ExperimentConfiguration,
    ExperimentConfigurationV1_1,
    RuleVariant,
    configured_variants,
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
    check_node_paths,
    read_definition,
)

type KeyPath = tuple[str | int, ...]

CREDENTIAL_WORDS: Final = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "authorization",
    "bearer",
    "api_key",
    "apikey",
    "api_id",
    "apiid",
)
"""A key whose name contains one of these, ignoring case and reading `-` as `_`, is
credential-like, and is rejected wherever it appears."""

MAX_DIGITS: Final = 16
"""The most digits a whole number can have and be accepted: 2^53 - 1 and 10^16 - 1 have 16."""

MAX_DEPTH: Final = 16
"""The deepest a value may be nested. A screen configuration needs 2 levels."""

_YAML_SPACE: Final = " \t\r\n\x85\u2028\u2029"
"""YAML's white space and line breaks, which PyYAML reads as such: a block scalar's span ends
after them."""

_TAG = "tag:yaml.org,2002:"
_STR = f"{_TAG}str"
_INTEGER = re.compile(INTEGER_PATTERN)
_DECIMAL = re.compile(r"(0|[1-9][0-9]*)\.[0-9]+")
_DATE = re.compile(DATE_PATTERN)


class _Invalid(Exception):
    def __init__(self, path: KeyPath, problem: str) -> None:
        super().__init__(problem)
        self.path = path
        self.problem = problem


def read_screen_configuration(content: bytes, source_name: str) -> ScreenConfiguration:
    """Reads a screen configuration 1.0.0 from the bytes of a file, named `source_name` in
    messages.

    Raises `TrialFolioError` with `config.invalid` when the file breaks any rule of the screen
    configuration. The message lists each problem, names its key, and includes no value. It's
    0.3.0's, for a ranking given as a definition or a snapshot too, since `trialfolio run`, which
    reads with this reader until R04-T12, refuses 1.1.0.
    """
    document, plain = _read_document(content, source_name, "screen", SCREEN_SCHEMA_VERSIONS)
    return _validated(ScreenConfiguration, document, source_name, _unquoted(plain, _is_sent_text))


@dataclass(frozen=True)
class ScreenConfigurationRead:
    """A screen configuration, as 0.4.0's reader reads it in step 2: its model, and the
    definition its ranking names."""

    configuration: ScreenConfiguration | ScreenConfigurationV1_1
    definition: RankingDefinition | None
    """The definition `ranking.definition` names, read and checked, with the bytes it was read
    from, which a plan's `definition.xml` copies; None for every other ranking form, and, until
    release 0.4.0's R04-T10 reads it, for a snapshot."""


@dataclass(frozen=True)
class ExperimentConfigurationRead:
    """An experiment configuration, as 0.4.0's reader reads it in step 2: its model, the
    definition its baseline's ranking names, and each ranking variant's case."""

    configuration: ExperimentConfiguration | ExperimentConfigurationV1_1
    definition: RankingDefinition | None
    """The baseline's definition, as `ScreenConfigurationRead.definition` gives a screen's."""
    ranking_cases: tuple[RankingCase, ...]
    """Each ranking variant's case, in the order of `variants.ranking`, with its definition:
    the baseline's, with the variant's change. Empty without a definition, a snapshot's
    included, until R04-T10 reads it."""


def read_screen_configuration_v1_1(
    content: bytes, source_name: str, path: str | os.PathLike[str]
) -> ScreenConfigurationRead:
    """Reads a screen configuration of a version release 0.4.0 reads, 1.0.0 or 1.1.0, by its
    `schema_version`, from the bytes of the file at `path`, named `source_name` in messages.
    Version 1.1.0's `ranking` may also be a definition, named by its file's path, with its
    `ranking_method`, or a snapshot, named by its directory's path. A definition's file is read
    from `path`'s directory, unless its path is absolute, and checked (ranking definitions).

    Raises `TrialFolioError` with `config.invalid` as `read_screen_configuration` does, and
    for a definition that breaks a rule, or a path that names something other than a file; and
    with `input.not_found` when nothing exists where the definition's path leads, or the file
    there can't be read. A 1.0.0 file that gives `definition` or `snapshot` is told they need
    `schema_version` 1.1.0.
    """
    document, plain = _read_document(
        content, source_name, "screen", SCREEN_SCHEMA_VERSIONS_V1_1, node_paths=True
    )
    unquoted = _unquoted(plain, _is_sent_text)
    if document["schema_version"] == "1.0.0":
        configuration = _validated(
            ScreenConfiguration, document, source_name, unquoted, later_versions=True
        )
        return ScreenConfigurationRead(configuration, None)
    read = _validated(ScreenConfigurationV1_1, document, source_name, unquoted)
    return ScreenConfigurationRead(read, _definition(read.ranking, "ranking", source_name, path))


def read_review_configuration(content: bytes, source_name: str) -> ReviewConfiguration:
    """Reads a review configuration from the bytes of a file, named `source_name` in messages.

    Raises `TrialFolioError` with `config.invalid` when the file breaks any rule of the review
    configuration. The message lists each problem, names its key, and includes no value. A review
    sends nothing to Portfolio123, so its text may be written without quotes.
    """
    document, _ = _read_document(content, source_name, "review", REVIEW_SCHEMA_VERSIONS)
    return _validated(ReviewConfiguration, document, source_name, [])


def read_experiment_configuration(content: bytes, source_name: str) -> ExperimentConfiguration:
    """Reads an experiment configuration from the bytes of a file, named `source_name` in
    messages.

    Raises `TrialFolioError` with `config.invalid` when the file breaks any rule of the experiment
    configuration. The message lists each problem, names its key, or a variant by its place, such
    as `variants.max_holdings[0]`, and includes no value: never a variant's key either, which is
    the user's text. It's 0.3.0's, for a ranking variant, or a baseline ranked by a definition or a
    snapshot, too, and so is how it reads a ranking variant's keys, since `trialfolio run`, which
    reads with this reader until R04-T12, refuses 1.1.0.
    """
    document, plain = _read_document(content, source_name, "experiment", EXPERIMENT_SCHEMA_VERSIONS)
    unquoted = _unquoted(plain, _is_sent_experiment_text)
    return _validated(ExperimentConfiguration, document, source_name, unquoted)


def read_experiment_configuration_v1_1(
    content: bytes, source_name: str, path: str | os.PathLike[str]
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
    """
    document, plain = _read_document(
        content, source_name, "experiment", EXPERIMENT_SCHEMA_VERSIONS_V1_1, node_paths=True
    )
    unquoted = _unquoted(plain, _is_sent_experiment_text_v1_1)
    if document["schema_version"] == "1.0.0":
        configuration = _validated(
            ExperimentConfiguration, document, source_name, unquoted, later_versions=True
        )
        return ExperimentConfigurationRead(configuration, None, ())
    read = _validated(
        ExperimentConfigurationV1_1,
        document,
        source_name,
        unquoted,
        variant_settings=VARIANT_SETTINGS_V1_1,
    )
    definition = _definition(read.baseline.ranking, "baseline.ranking", source_name, path)
    return ExperimentConfigurationRead(
        read, definition, _ranking_cases(read, definition, source_name)
    )


def _definition(
    ranking: RankingV1_1, key: str, source_name: str, path: str | os.PathLike[str]
) -> RankingDefinition | None:
    """The definition a ranking given as a definition names, read once from its file, at the
    one path the file system resolves, from the configuration's directory unless the path is
    absolute, and checked (docs/contracts.md, ranking definitions). None for any other form."""
    if not isinstance(ranking, DefinitionRanking):
        return None
    where = f"{key}.definition"
    given = visible(ranking.definition)
    try:
        resolved = resolve_existing(Path(path).parent / ranking.definition)
    except OSError as error:
        # The file system can't follow the path, such as through a folder the user may not
        # search, so a file there, if there is one, can't be read.
        raise _unreadable(source_name, where, given, error) from None
    if resolved is None:
        raise TrialFolioError(
            "input.not_found",
            f"{source_name}: the file `{where}` names (`{given}`) doesn't exist. "
            f"{_DEFINITION_PATH}",
            f"{source_name}: the file `{where}` names doesn't exist. {_DEFINITION_PATH}",
        )
    if not os.path.isfile(resolved):
        _fail(
            source_name,
            [
                f"`{where}` names something that isn't a file, such as a directory. {_DEFINITION_PATH}"
            ],
        )
    try:
        definition = Path(resolved).read_bytes()
    except OSError as error:
        raise _unreadable(source_name, where, given, error) from None
    try:
        return read_definition(definition)
    except DefinitionProblem as problem:
        at = "" if problem.line is None else f", at line {problem.line}"
        _fail(
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
    definition. Without one, as for a snapshot until R04-T10 reads it, only how each variant's
    paths are written is checked, and there's no case. Raises `TrialFolioError` with
    `config.invalid` listing the first problem of each variant that breaks a rule, and each
    variant whose definition another's gives already, byte for byte."""
    variants = configuration.variants
    listed = () if variants is None or variants.ranking is None else variants.ranking
    problems: list[str] = []
    cases: list[RankingCase] = []
    for number, variant in enumerate(listed):
        place = f"variants.ranking[{number}]"
        try:
            if definition is None:
                check_node_paths(variant, place)
            else:
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
        _fail(source_name, problems)
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
    document, plain = _read_document(
        content, source_name, "ranking-snapshot", RANKING_SNAPSHOT_SCHEMA_VERSIONS, node_paths=True
    )
    unquoted = _unquoted(plain, lambda path: path == ("system",))
    return _validated(RankingSnapshotConfiguration, document, source_name, unquoted)


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
        details = error.errors(include_input=False)
        problems = [
            _describe(detail, document, variant_settings, later_versions=later_versions)
            for detail in details
            if not _follows(detail, details)
        ]
        _fail(source_name, problems + unquoted)
    if unquoted:
        _fail(source_name, unquoted)
    return configuration


def _unquoted(plain: list[KeyPath], quoted: Callable[[KeyPath], bool]) -> list[str]:
    """A message for each text in `plain`, written without quotes, that must be quoted."""
    return [_unquoted_text(path) for path in plain if quoted(path)]


def read_run_configuration(
    content: bytes, source_name: str
) -> ScreenConfiguration | ExperimentConfiguration:
    """Reads the configuration `trialfolio run` takes, from the bytes of a file named
    `source_name` in messages: a screen configuration, or an experiment configuration, by its
    `kind` (D-24).

    Raises `TrialFolioError` with `config.invalid` as the screen's or the experiment's reader
    does. A file that breaks a YAML rule, isn't a mapping, or whose `kind` is missing or is
    neither, such as `review`, fails before either reads it, and the message names both kinds.
    """
    document, _ = _read_kind(content, source_name, ("screen", "experiment"))
    if document["kind"] == "experiment":
        return read_experiment_configuration(content, source_name)
    return read_screen_configuration(content, source_name)


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
) -> tuple[dict[str, object], list[KeyPath]]:
    """The document of a configuration of `kind`, once its YAML rules, its `kind`, and its
    `schema_version` are checked; and where it writes text as a plain scalar. With `node_paths`,
    as 0.4.0's readers read, a ranking variant's `set` keys are read as node paths."""
    document, plain = _read_kind(content, source_name, (kind,), node_paths=node_paths)
    supported = ", ".join(versions)
    if "schema_version" not in document:
        _fail(source_name, [f"`schema_version` is required. Supported versions: {supported}."])
    if document["schema_version"] not in versions:
        _fail(
            source_name,
            [f"`schema_version` isn't a supported version. Supported versions: {supported}."],
        )
    return document, plain


def _read_kind(
    content: bytes, source_name: str, kinds: tuple[str, ...], *, node_paths: bool = False
) -> tuple[dict[str, object], list[KeyPath]]:
    """The document of a configuration of one of `kinds`, once its YAML rules and its `kind` are
    checked; and where it writes text as a plain scalar. `node_paths` is `_read_document`'s."""
    loaded, _, plain, _ = _read_yaml(content, source_name, node_paths=node_paths)
    if not isinstance(loaded, dict):
        _fail(source_name, ["The file must be a mapping of keys to values."])
    document = cast("dict[str, object]", loaded)
    if "kind" not in document:
        named = [
            f"{'an' if kind[0] in 'aeiou' else 'a'} {kind} configuration has `kind: {kind}`"
            for kind in kinds
        ]
        listed = ", and ".join(named)
        _fail(source_name, [f"`kind` is required. {listed[0].upper()}{listed[1:]}."])
    if document["kind"] not in kinds:
        _fail(source_name, [f"`kind` must be {' or '.join(kinds)}."])
    return document, plain


def original_values(content: bytes, source_name: str) -> Mapping[str, str]:
    """Each top-level key's value as the file writes it, by key: its text from its first
    character to its last one that isn't YAML white space or a line break. That keeps quotes,
    block indicators, and, inside a block list or mapping, the line breaks, indentation, and
    comments between its items (docs/contracts.md, settings.csv's `original_value`).

    For a file `read_screen_configuration` accepted. Raises `TrialFolioError` with
    `config.invalid` when the file breaks a YAML rule, as that function does.
    """
    _, originals, _, _ = _read_yaml(content, source_name)
    return originals


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
    _, _, _, values = _read_yaml(content, source_name)
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
    return _is_sent_experiment_text(path) or _is_node_path(path)


def _is_node_path(path: KeyPath) -> bool:
    """A ranking variant's node path: a key of its `set`, named by its place, or its `remove`."""
    if len(path) < 4 or path[:2] != ("variants", "ranking") or not isinstance(path[2], int):
        return False
    return path[3:] == ("remove",) or (len(path) == 5 and _names_by_place(path[:4]))


def _names_by_place(path: KeyPath) -> bool:
    """Whether `path` is a ranking variant's `set`, whose keys are node paths, which the user's
    strategy definition names, so messages name each entry by its place in the file."""
    return (
        len(path) == 4
        and path[:2] == ("variants", "ranking")
        and isinstance(path[2], int)
        and path[3] == "set"
    )


def _unquoted_text(path: KeyPath) -> str:
    if _is_node_path(path):
        return (
            f"`{_format_path(path)}` is a node path written without quotes. Write it in single"
            " quotes: outside quotes, YAML reads a space and # as the start of a comment, and a"
            " node's name can hold both."
        )
    return (
        f"`{_format_path(path)}` is text Portfolio123 receives, written without quotes. Write it in"
        " single quotes: outside quotes, YAML reads a space and # as the start of a comment, so"
        " the text could be cut short without an error."
    )


def _follows(detail: ErrorDetails, details: list[ErrorDetails]) -> bool:
    """A list that's too short only because its items failed: `rules: [5]` holds one rule.
    Pydantic counts only the items that passed, so a list that holds too few even with its failed
    items, as `results` with one entry, keeps its error."""
    if detail["type"] != "too_short":
        return False
    location = detail["loc"]
    failed = {
        other["loc"][len(location)]
        for other in details
        if other["loc"][: len(location)] == location and len(other["loc"]) > len(location)
    }
    context = detail.get("ctx", {})
    return bool(failed) and context["actual_length"] + len(failed) >= context["min_length"]


def _fail(source_name: str, problems: Sequence[str]) -> NoReturn:
    lines = "\n".join(f"- {problem}" for problem in problems)
    raise TrialFolioError(
        "config.invalid", f"{source_name} isn't a valid configuration:\n{lines}"
    ) from None


def _format_path(path: KeyPath) -> str:
    """The key path as messages name it, such as `variants.rules[0].add`. A key's control and
    formatting characters and lone surrogates are written as escapes, as the plan display writes
    text from the configuration, so a key can't act on a terminal, and the JSON summary can hold
    the message."""
    text = ""
    for part in path:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            name = visible(part) or "''"
            text += f".{name}" if text else name
    return text


_HEADER_KEYS: Final = frozenset({("kind",), ("schema_version",), ("title",), ("purpose",)})
"""The keys a screen configuration has before its settings, which an experiment's baseline
doesn't: the experiment's own are at the top level."""


def _placed(location: KeyPath, document: object) -> KeyPath:
    """`location`, with a ranking variant's `set` entry named by its place, counted from 0, in
    place of its node path, which is the user's strategy definition. An entry that can't be
    found is named by its `set`."""
    if len(location) < 5 or not _names_by_place(location[:4]) or not isinstance(location[4], str):
        return location
    entries: object = document
    for part in location[:4]:
        if isinstance(entries, dict) and isinstance(part, str):
            entries = cast("dict[str, object]", entries).get(part)
        elif isinstance(entries, list) and isinstance(part, int):
            listed = cast("list[object]", entries)
            entries = listed[part] if part < len(listed) else None
        else:
            entries = None
    if not isinstance(entries, dict) or location[4] not in entries:
        return location[:4]
    return (*location[:4], list(cast("dict[str, object]", entries)).index(location[4]))


def _describe(
    detail: ErrorDetails,
    document: object = None,
    variant_settings: tuple[str, ...] = VARIANT_SETTINGS,
    *,
    later_versions: bool = False,
) -> str:
    location = _placed(detail["loc"], document)
    key = _format_path(location)
    kind = detail["type"]
    message = detail["msg"].removeprefix("Value error, ").rstrip(".")
    if not location:
        return f"{message}."
    if kind == "missing":
        return f"`{key}` is required."
    settings = f"{', '.join(variant_settings[:-1])}, or {variant_settings[-1]}"
    if later_versions and kind == "extra_forbidden" and location == ("variants", "ranking"):
        return (
            f"`{key}` needs schema_version 1.1.0, with a baseline ranked by a definition or a "
            f"snapshot. In 1.0.0, a variant may change {settings}."
        )
    if kind == "extra_forbidden" and location[:1] == ("variants",) and len(location) == 2:
        return f"`{key}` isn't a setting a variant may change. A variant may change {settings}."
    if kind == "extra_forbidden" and location[0] == "baseline" and location[1:] in _HEADER_KEYS:
        return (
            f"`{key}` isn't a key of the baseline: an experiment's kind, schema_version, "
            "title, and purpose are written at the top level."
        )
    if kind == "extra_forbidden":
        return f"`{key}` isn't a key this configuration accepts. Check its spelling."
    context = detail.get("ctx", {})
    if kind == "string_pattern_mismatch" and context.get("pattern") == NOT_BLANK:
        return f"`{key}` is blank. Give it text that isn't only whitespace."
    if kind == "string_pattern_mismatch" and context.get("pattern") == LABEL_PATTERN:
        what = "a label of " if location[-1] == "label" else ""
        return (
            f"`{key}` must be {what}1 to 64 characters: lowercase letters, digits, _, and -,"
            " starting with a letter or a digit."
        )
    if kind == "value_error" and message.startswith("`"):
        # A rule that spans the keys of a mapping inside the file names them within it, as
        # `end_date` in the baseline: each becomes its path, such as `baseline.end_date`.
        return re.sub(r"`([^`]+)`", lambda name: f"`{key}.{name.group(1)}`", message) + "."
    if kind == "too_short" and detail["loc"][-1] == "intended_changes":
        return f"`{key}` is empty. A result that declares no change leaves the key out."
    if kind == "too_short":
        least = context.get("min_length")
        return f"`{key}` must hold at least {least} item{'' if least == 1 else 's'}."
    return f"`{key}` {message[0].lower()}{message[1:]}."


def _read_yaml(
    content: bytes, source_name: str, *, node_paths: bool = False
) -> tuple[object, dict[str, str], list[KeyPath], dict[str, str]]:
    """The document's value; each top-level value's text, as `original_values` gives it; where
    the file writes text as a plain scalar, without quotes, in the file's order; and every
    value's text, by its key path, such as `variants.rules[0].add`. `node_paths` is
    `_read_document`'s."""
    try:
        text = content.decode("utf-8").removeprefix("\ufeff")
    except UnicodeDecodeError:
        _fail(source_name, ["The file isn't UTF-8 text."])
    try:
        builder = _Builder(text, node_paths=node_paths)
        return builder.document(), builder.originals, builder.plain_text, builder.values
    except _Invalid as error:
        where = f"`{_format_path(error.path)}`" if error.path else "The file"
        _fail(source_name, [f"{where} {error.problem}"])
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        place = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        # PyYAML's own wording can quote characters of a value, so it's left out.
        _fail(source_name, [f"The file isn't valid YAML{place}."])
    except yaml.YAMLError:
        _fail(source_name, ["The file isn't valid YAML."])


class _Mark(Protocol):
    """A position in the text, as PyYAML marks an event's start or end."""

    @property
    def index(self) -> int: ...


def _index(mark: _Mark | None) -> int:
    """Where a mark is, as an index into the text."""
    if mark is None:  # PyYAML's parser marks every event; its stubs allow none
        raise _Invalid((), "isn't valid YAML.")
    return mark.index


class _Parser(Protocol):
    """The parts of PyYAML's `SafeLoader` the builder uses, which its stubs leave untyped."""

    def get_event(self) -> Event: ...
    def peek_event(self) -> Event: ...
    def resolve(self, kind: type[Node], value: str, implicit: tuple[bool, bool]) -> str: ...
    def dispose(self) -> None: ...


class _Builder:
    """Builds plain values from parse events, applying the rules in the module docstring."""

    def __init__(self, text: str, *, node_paths: bool = False) -> None:
        self._text = text
        self._node_paths = node_paths
        """Whether a ranking variant's `set` keys are node paths, named by their place, as 0.4.0's
        readers read them. 0.3.0's read them as any other key."""
        self._loader = cast("_Parser", yaml.SafeLoader(text))
        self._end = 0
        """Where the last scalar or flow collection ended, as an index into the text. A block
        collection ends where its last item does."""
        self.originals: dict[str, str] = {}
        """Each top-level value's text, by key, once `document` has returned."""
        self.values: dict[str, str] = {}
        """Every value's text, by its key path as messages write it, once `document` has
        returned."""
        self.plain_text: list[KeyPath] = []
        """Where a plain scalar, without quotes or a block indicator, was read as text. With
        `node_paths`, a ranking variant's `set` entry is there, by its place, when its key, a node
        path, is written that way."""

    def document(self) -> object:
        try:
            self._expect(StreamStartEvent)
            if isinstance(self._loader.peek_event(), StreamEndEvent):
                raise _Invalid((), "is empty.")
            self._expect(DocumentStartEvent)
            value = self._value(())
            self._expect(DocumentEndEvent)
            if not isinstance(self._loader.peek_event(), StreamEndEvent):
                raise _Invalid((), "must hold one YAML document, not several.")
            return value
        finally:
            self._loader.dispose()

    def _expect(self, kind: type[Event]) -> None:
        event = self._loader.get_event()
        if not isinstance(event, kind):  # PyYAML's parser guarantees the order
            raise _Invalid((), "isn't valid YAML.")

    def _value(self, path: KeyPath) -> object:
        if len(path) > MAX_DEPTH:
            raise _Invalid(path[:1], f"is nested more than {MAX_DEPTH} levels deep.")
        event = self._loader.get_event()
        if isinstance(event, AliasEvent):
            raise _Invalid(path, "is an alias. Write the value out instead.")
        if not isinstance(event, NodeEvent):  # the parser yields a node here
            raise _Invalid(path, "has no value.")
        if event.anchor is not None:
            raise _Invalid(path, "has an anchor. Anchors and aliases aren't accepted.")
        value = self._node(event, path)
        if path:
            span = self._text[_index(event.start_mark) : self._end].rstrip(_YAML_SPACE)
            self.values[_format_path(path)] = span
            if len(path) == 1 and isinstance(path[0], str):
                self.originals[path[0]] = span
        return value

    def _node(self, event: NodeEvent, path: KeyPath) -> object:
        if isinstance(event, ScalarEvent):
            self._end = _index(event.end_mark)
            return self._scalar(event, path)
        if isinstance(event, SequenceStartEvent):
            self._no_tag(event.tag, path)
            items: list[object] = []
            while not isinstance(self._loader.peek_event(), SequenceEndEvent):
                items.append(self._value((*path, len(items))))
            self._close(event)
            return items
        if isinstance(event, MappingStartEvent):
            self._no_tag(event.tag, path)
            mapping: dict[str, object] = {}
            # A ranking variant's `set` is keyed by node paths, so each entry is named by its
            # place, never by its key.
            by_place = self._node_paths and _names_by_place(path)
            while not isinstance(self._loader.peek_event(), MappingEndEvent):
                place: KeyPath | None = (*path, len(mapping)) if by_place else None
                key = self._key(path, place)
                where = (*path, key) if place is None else place
                if key in mapping:
                    raise _Invalid(
                        where,
                        "appears more than once."
                        if place is None
                        else "repeats the path of an earlier entry of the same set. Write each "
                        "path once.",
                    )
                mapping[key] = self._value(where)
            self._close(event)
            return mapping
        raise _Invalid(path, "isn't a value this reader accepts.")

    def _close(self, start: SequenceStartEvent | MappingStartEvent) -> None:
        end = self._loader.get_event()
        # A flow collection ends at its bracket. A block one has no closing mark: its end event
        # sits where the next token starts, after any comment, so it ends with its last item.
        if start.flow_style:
            self._end = _index(end.end_mark)

    def _key(self, path: KeyPath, place: KeyPath | None = None) -> str:
        """The next key of the mapping at `path`. `place` names it by its place, for a key that's
        a node path, which messages never quote."""
        event = self._loader.get_event()
        if not isinstance(event, ScalarEvent) or event.anchor is not None or event.tag is not None:
            raise _Invalid(path, "has a key that isn't plain text.")
        key = event.value
        if event.style is None and self._loader.resolve(ScalarNode, key, (True, False)) != _STR:
            raise _Invalid(path, "has a key that YAML doesn't read as text. Quote it.")
        folded = key.lower().replace("-", "_")
        if any(word in folded for word in CREDENTIAL_WORDS):
            if place is not None:
                raise _Invalid(
                    place,
                    "is a node path that holds a word a credential's key would, which no "
                    "configuration's key may hold. Name the node whose name holds it by its "
                    "position instead, such as #2.",
                )
            raise _Invalid(
                (*path, key),
                "looks like a credential. A configuration never holds credentials: the CLI "
                "reads them from TRIALFOLIO_P123_API_ID and TRIALFOLIO_P123_API_KEY.",
            )
        if place is not None and event.style is None:
            self.plain_text.append(place)
        return key

    @staticmethod
    def _no_tag(tag: str | None, path: KeyPath) -> None:
        if tag is not None:
            raise _Invalid(path, "has an explicit YAML tag. Tags aren't accepted.")

    def _scalar(self, event: ScalarEvent, path: KeyPath) -> object:
        self._no_tag(event.tag, path)
        text = event.value
        if event.style is not None:
            return text
        tag = self._loader.resolve(ScalarNode, text, (True, False))
        if tag == _STR:
            # With `node_paths`, a ranking variant's `set` entry is named by its place, which
            # `_key` records when its node path is written without quotes. Its value is a weight,
            # never text, which the model reports, so it isn't recorded there too.
            if not (self._node_paths and _names_by_place(path[:-1])):
                self.plain_text.append(path)
            return text
        if tag == f"{_TAG}null":
            raise _Invalid(path, "has no value. Give it one, or leave the key out.")
        if tag == f"{_TAG}bool":
            if text in ("true", "false"):
                return text == "true"
            raise _Invalid(
                path,
                "is a YAML 1.1 boolean other than true or false. Write true or false, or quote "
                "it if it's text.",
            )
        if tag == f"{_TAG}int":
            if not _INTEGER.fullmatch(text):
                raise _Invalid(
                    path,
                    "is a number in a form a YAML 1.1 loader converts, with a leading zero, an "
                    "underscore, a sign, a base prefix, or a colon. Write plain decimal digits, "
                    "or quote it if it's text.",
                )
            # The models check each key's limit. This one keeps int() from text it can't
            # convert: Python refuses more than 4300 digits.
            if len(text) > MAX_DIGITS:
                raise _Invalid(path, f"has more than {MAX_DIGITS} digits, more than any key takes.")
            return int(text)
        if tag == f"{_TAG}float":
            if not _DECIMAL.fullmatch(text):
                raise _Invalid(
                    path,
                    "is a number in a form that isn't accepted, with an exponent, a sign, a "
                    "leading point, a leading zero, or a colon, or an infinity or NaN. Write it "
                    "in plain notation, such as 0.25.",
                )
            return Decimal(text)
        if tag == f"{_TAG}timestamp":
            if not _DATE.fullmatch(text):
                raise _Invalid(
                    path, "is a date with a time part. Write the date alone, YYYY-MM-DD."
                )
            try:
                return date.fromisoformat(text)
            except ValueError:
                raise _Invalid(path, "isn't a valid date.") from None
        raise _Invalid(path, "is a YAML form that isn't accepted. Quote it if it's text.")
