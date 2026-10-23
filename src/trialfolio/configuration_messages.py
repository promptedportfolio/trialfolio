"""The messages of the configuration's readers, `config.invalid`'s (docs/contracts.md,
configuration files): a problem for each error a model finds, and for each text written without
quotes that must be quoted, and the error that lists them. `trialfolio.configuration`'s readers
give each problem of a step of their own, such as a missing `kind`, at its site.

Every message names the offending key and never includes its value, so it's safe to log. A key's
control and formatting characters and lone surrogates are written as escapes
(`trialfolio.strict_yaml.format_path`).

A ranking variant's `set` is keyed by node paths, which hold the user's strategy definition, so
every message names a `set` entry by its place, such as `variants.ranking[0].set[1]`, never by
its path (node paths). `names_by_place` and `is_node_path` give where those paths are, for the
readers and the YAML reader too.
"""

import re
from collections.abc import Sequence
from typing import Final, NoReturn, cast

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from trialfolio.contracts.common import LABEL_PATTERN, NOT_BLANK
from trialfolio.contracts.experiment_configuration import VARIANT_SETTINGS
from trialfolio.errors import TrialFolioError
from trialfolio.strict_yaml import KeyPath, format_path

_HEADER_KEYS: Final = frozenset({("kind",), ("schema_version",), ("title",), ("purpose",)})
"""The keys a screen configuration has before its settings, which an experiment's baseline
doesn't: the experiment's own are at the top level."""


def fail(source_name: str, problems: Sequence[str]) -> NoReturn:
    """Raises `TrialFolioError` with `config.invalid`, listing each problem of the file named
    `source_name`."""
    lines = "\n".join(f"- {problem}" for problem in problems)
    raise TrialFolioError(
        "config.invalid", f"{source_name} isn't a valid configuration:\n{lines}"
    ) from None


def model_problems(
    error: ValidationError,
    document: object,
    variant_settings: tuple[str, ...] = VARIANT_SETTINGS,
    *,
    later_versions: bool = False,
) -> list[str]:
    """A problem for each error the model found in `document`, as `describe` gives it, apart
    from a list's that's too short only because its items failed."""
    details = error.errors(include_input=False)
    return [
        describe(detail, document, variant_settings, later_versions=later_versions)
        for detail in details
        if not _follows(detail, details)
    ]


def describe(
    detail: ErrorDetails,
    document: object = None,
    variant_settings: tuple[str, ...] = VARIANT_SETTINGS,
    *,
    later_versions: bool = False,
) -> str:
    """The problem a model's error gives, naming its key, with a ranking variant's `set` entry
    named by its place in `document`. `variant_settings` are the settings the file's version lets
    a variant change. With `later_versions`, as 0.4.0's readers read a 1.0.0 file, a key that only
    1.1.0 allows is told it needs that version; without it, the messages are 0.3.0's."""
    location = _placed(detail["loc"], document)
    key = format_path(location)
    message = detail["msg"].removeprefix("Value error, ").rstrip(".")
    if not location:
        return f"{message}."
    if detail["type"] == "missing":
        return f"`{key}` is required."
    if detail["type"] == "extra_forbidden":
        return _not_accepted(location, key, variant_settings, later_versions=later_versions)
    return _particular(detail, location, key, message) or (
        f"`{key}` {message[0].lower()}{message[1:]}."
    )


def _not_accepted(
    location: KeyPath, key: str, variant_settings: tuple[str, ...], *, later_versions: bool
) -> str:
    """The problem of a key the model doesn't accept, at `location`."""
    settings = f"{', '.join(variant_settings[:-1])}, or {variant_settings[-1]}"
    if later_versions and location == ("variants", "ranking"):
        return (
            f"`{key}` needs schema_version 1.1.0, with a baseline ranked by a definition or a "
            f"snapshot. In 1.0.0, a variant may change {settings}."
        )
    if location[:1] == ("variants",) and len(location) == 2:
        return f"`{key}` isn't a setting a variant may change. A variant may change {settings}."
    if location[0] == "baseline" and location[1:] in _HEADER_KEYS:
        return (
            f"`{key}` isn't a key of the baseline: an experiment's kind, schema_version, "
            "title, and purpose are written at the top level."
        )
    return f"`{key}` isn't a key this configuration accepts. Check its spelling."


def _particular(detail: ErrorDetails, location: KeyPath, key: str, message: str) -> str | None:
    """The problem of an error that has words of its own: a blank text, a label, a rule that
    spans a mapping's keys, and a list that's too short. None for any other, which gives the
    model's message after the key."""
    kind = detail["type"]
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
    return None


def unquoted_text(path: KeyPath) -> str:
    """The problem of text at `path`, written without quotes, that must be quoted: a node path,
    or text Portfolio123 receives."""
    if is_node_path(path):
        return (
            f"`{format_path(path)}` is a node path written without quotes. Write it in single"
            " quotes: outside quotes, YAML reads a space and # as the start of a comment, and a"
            " node's name can hold both."
        )
    return (
        f"`{format_path(path)}` is text Portfolio123 receives, written without quotes. Write it in"
        " single quotes: outside quotes, YAML reads a space and # as the start of a comment, so"
        " the text could be cut short without an error."
    )


def is_node_path(path: KeyPath) -> bool:
    """A ranking variant's node path: a key of its `set`, named by its place, or its `remove`."""
    if len(path) < 4 or path[:2] != ("variants", "ranking") or not isinstance(path[2], int):
        return False
    return path[3:] == ("remove",) or (len(path) == 5 and names_by_place(path[:4]))


def names_by_place(path: KeyPath) -> bool:
    """Whether `path` is a ranking variant's `set`, whose keys are node paths, which the user's
    strategy definition names, so messages name each entry by its place in the file."""
    return (
        len(path) == 4
        and path[:2] == ("variants", "ranking")
        and isinstance(path[2], int)
        and path[3] == "set"
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


def _placed(location: KeyPath, document: object) -> KeyPath:
    """`location`, with a ranking variant's `set` entry named by its place, counted from 0, in
    place of its node path, which is the user's strategy definition. An entry that can't be
    found is named by its `set`."""
    if len(location) < 5 or not names_by_place(location[:4]) or not isinstance(location[4], str):
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
