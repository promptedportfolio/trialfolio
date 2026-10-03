"""Reads configuration files: YAML text in, validated models out (docs/contracts.md,
configuration files).

Reading is a named adapter step before model validation (ADR 0002). It builds plain values from
PyYAML's parse events, never through PyYAML's constructors, so it decides what each scalar means:

- A quoted or block scalar is text.
- A plain scalar is resolved as a YAML 1.1 safe loader would resolve it, and kept only when that
  reading is unambiguous: `true` or `false`; an integer in plain decimal digits; a decimal in
  plain notation, as a `Decimal` read from its text; or a date written `YYYY-MM-DD`. Any other
  form a YAML 1.1 loader would convert, such as `010`, `1:30`, `yes`, or `2.5e-1`, is rejected.
- Null values, duplicate keys, non-text keys, anchors, aliases, explicit tags, and credential-like
  keys are rejected.

`original_values` gives each top-level value's text exactly as the file writes it, for
`settings.csv`'s `original_value` (docs/contracts.md, settings.csv).

Error messages name the offending key and never include its value, so they're safe to log.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Final, NoReturn, Protocol, cast

import yaml
from pydantic import ValidationError
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

from trialfolio.contracts.common import DATE_PATTERN, INTEGER_PATTERN, NOT_BLANK
from trialfolio.contracts.screen_configuration import SCREEN_SCHEMA_VERSIONS, ScreenConfiguration
from trialfolio.errors import TrialFolioError

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
    """Reads a screen configuration from the bytes of a file, named `source_name` in messages.

    Raises `TrialFolioError` with `config.invalid` when the file breaks any rule of the screen
    configuration. The message lists each problem, names its key, and includes no value.
    """
    loaded, _ = _read_yaml(content, source_name)
    if not isinstance(loaded, dict):
        _fail(source_name, ["The file must be a mapping of keys to values."])
    document = cast("dict[str, object]", loaded)
    if "kind" not in document:
        _fail(source_name, ["`kind` is required. A screen configuration has `kind: screen`."])
    if document["kind"] != "screen":
        _fail(source_name, ["`kind` must be screen."])
    supported = ", ".join(SCREEN_SCHEMA_VERSIONS)
    if "schema_version" not in document:
        _fail(source_name, [f"`schema_version` is required. Supported versions: {supported}."])
    if document["schema_version"] not in SCREEN_SCHEMA_VERSIONS:
        _fail(
            source_name,
            [f"`schema_version` isn't a supported version. Supported versions: {supported}."],
        )
    try:
        return ScreenConfiguration.model_validate(document)
    except ValidationError as error:
        details = error.errors(include_input=False)
        _fail(
            source_name, [_describe(detail) for detail in details if not _follows(detail, details)]
        )


def original_values(content: bytes, source_name: str) -> Mapping[str, str]:
    """Each top-level key's value as the file writes it, by key: its text from its first
    character to its last one that isn't YAML white space or a line break. That keeps quotes,
    block indicators, and, inside a block list or mapping, the line breaks, indentation, and
    comments between its items (docs/contracts.md, settings.csv's `original_value`).

    For a file `read_screen_configuration` accepted. Raises `TrialFolioError` with
    `config.invalid` when the file breaks a YAML rule, as that function does.
    """
    _, originals = _read_yaml(content, source_name)
    return originals


def _follows(detail: ErrorDetails, details: list[ErrorDetails]) -> bool:
    """A list that's too short only because its items failed: `rules: [5]` holds one rule."""
    location = detail["loc"]
    return detail["type"] == "too_short" and any(
        other["loc"][: len(location)] == location and len(other["loc"]) > len(location)
        for other in details
    )


def _fail(source_name: str, problems: Sequence[str]) -> NoReturn:
    lines = "\n".join(f"- {problem}" for problem in problems)
    raise TrialFolioError(
        "config.invalid", f"{source_name} isn't a valid configuration:\n{lines}"
    ) from None


def _format_path(path: KeyPath) -> str:
    text = ""
    for part in path:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            name = part or "''"
            text += f".{name}" if text else name
    return text


def _describe(detail: ErrorDetails) -> str:
    key = _format_path(detail["loc"])
    kind = detail["type"]
    message = detail["msg"].removeprefix("Value error, ").rstrip(".")
    if not detail["loc"]:
        return f"{message}."
    if kind == "missing":
        return f"`{key}` is required."
    if kind == "extra_forbidden":
        return f"`{key}` isn't a key this configuration accepts. Check its spelling."
    context = detail.get("ctx", {})
    if kind == "string_pattern_mismatch" and context.get("pattern") == NOT_BLANK:
        return f"`{key}` is blank. Give it text that isn't only whitespace."
    if kind == "too_short":
        least = context.get("min_length")
        return f"`{key}` must hold at least {least} item{'' if least == 1 else 's'}."
    return f"`{key}` {message[0].lower()}{message[1:]}."


def _read_yaml(content: bytes, source_name: str) -> tuple[object, dict[str, str]]:
    """The document's value, and each top-level value's text as `original_values` gives it."""
    try:
        text = content.decode("utf-8").removeprefix("\ufeff")
    except UnicodeDecodeError:
        _fail(source_name, ["The file isn't UTF-8 text."])
    try:
        builder = _Builder(text)
        return builder.document(), builder.originals
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

    def __init__(self, text: str) -> None:
        self._text = text
        self._loader = cast("_Parser", yaml.SafeLoader(text))
        self._end = 0
        """Where the last scalar or flow collection ended, as an index into the text. A block
        collection ends where its last item does."""
        self.originals: dict[str, str] = {}
        """Each top-level value's text, by key, once `document` has returned."""

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
        if len(path) == 1 and isinstance(path[0], str):
            span = self._text[_index(event.start_mark) : self._end]
            self.originals[path[0]] = span.rstrip(_YAML_SPACE)
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
            while not isinstance(self._loader.peek_event(), MappingEndEvent):
                key = self._key(path)
                if key in mapping:
                    raise _Invalid((*path, key), "appears more than once.")
                mapping[key] = self._value((*path, key))
            self._close(event)
            return mapping
        raise _Invalid(path, "isn't a value this reader accepts.")

    def _close(self, start: SequenceStartEvent | MappingStartEvent) -> None:
        end = self._loader.get_event()
        # A flow collection ends at its bracket. A block one has no closing mark: its end event
        # sits where the next token starts, after any comment, so it ends with its last item.
        if start.flow_style:
            self._end = _index(end.end_mark)

    def _key(self, path: KeyPath) -> str:
        event = self._loader.get_event()
        if not isinstance(event, ScalarEvent) or event.anchor is not None or event.tag is not None:
            raise _Invalid(path, "has a key that isn't plain text.")
        key = event.value
        if event.style is None and self._loader.resolve(ScalarNode, key, (True, False)) != _STR:
            raise _Invalid(path, "has a key that YAML doesn't read as text. Quote it.")
        folded = key.lower().replace("-", "_")
        if any(word in folded for word in CREDENTIAL_WORDS):
            raise _Invalid(
                (*path, key),
                "looks like a credential. A configuration never holds credentials: the CLI "
                "reads them from TRIALFOLIO_P123_API_ID and TRIALFOLIO_P123_API_KEY.",
            )
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
