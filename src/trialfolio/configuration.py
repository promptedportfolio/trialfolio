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

Error messages name the offending key and never include its value, so they're safe to log.
"""

import re
from collections.abc import Sequence
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

from trialfolio.contracts.common import MAX_SAFE_INTEGER
from trialfolio.contracts.screen_configuration import (
    RANKING_FORMS,
    SCREEN_SCHEMA_VERSIONS,
    ScreenConfiguration,
)
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

_TAG = "tag:yaml.org,2002:"
_STR = f"{_TAG}str"
_INTEGER = re.compile(r"0|[1-9][0-9]*")
_DECIMAL = re.compile(r"(0|[1-9][0-9]*)\.[0-9]+")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


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
    loaded = _read_yaml(content, source_name)
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
        _fail(source_name, [_describe(detail) for detail in error.errors(include_input=False)])


def _fail(source_name: str, problems: Sequence[str]) -> NoReturn:
    lines = "\n".join(f"- {problem}" for problem in problems)
    raise TrialFolioError(
        "config.invalid", f"{source_name} isn't a valid configuration:\n{lines}"
    ) from None


def _format_path(path: KeyPath) -> str:
    text = ""
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else f".{part}" if text else part
    return text


def _describe(detail: ErrorDetails) -> str:
    location = list(detail["loc"])
    # A ranking's form is a tag of the discriminated union, not a key: drop it.
    if len(location) > 2 and location[0] == "ranking" and location[1] in RANKING_FORMS:
        del location[1]
    key = _format_path(tuple(location))
    kind = detail["type"]
    message = detail["msg"].removeprefix("Value error, ").rstrip(".")
    if not key:
        return f"{message}."
    if kind == "missing":
        return f"`{key}` is required."
    if kind == "extra_forbidden":
        return f"`{key}` isn't a key this configuration accepts. Check its spelling."
    return f"`{key}` {message[0].lower()}{message[1:]}."


def _read_yaml(content: bytes, source_name: str) -> object:
    try:
        text = content.decode("utf-8").removeprefix("\ufeff")
    except UnicodeDecodeError:
        _fail(source_name, ["The file isn't UTF-8 text."])
    try:
        return _Builder(text).document()
    except _Invalid as error:
        where = f"`{_format_path(error.path)}`" if error.path else "The file"
        _fail(source_name, [f"{where} {error.problem}"])
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        place = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        _fail(source_name, [f"The file isn't valid YAML{place}: {error.problem or error.context}."])
    except yaml.YAMLError:
        _fail(source_name, ["The file isn't valid YAML."])


class _Parser(Protocol):
    """The parts of PyYAML's `SafeLoader` the builder uses, which its stubs leave untyped."""

    def get_event(self) -> Event: ...
    def peek_event(self) -> Event: ...
    def resolve(self, kind: type[Node], value: str, implicit: tuple[bool, bool]) -> str: ...
    def dispose(self) -> None: ...


class _Builder:
    """Builds plain values from parse events, applying the rules in the module docstring."""

    def __init__(self, text: str) -> None:
        self._loader = cast("_Parser", yaml.SafeLoader(text))

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
        event = self._loader.get_event()
        if isinstance(event, AliasEvent):
            raise _Invalid(path, "is an alias. Write the value out instead.")
        if not isinstance(event, NodeEvent):  # the parser yields a node here
            raise _Invalid(path, "has no value.")
        if event.anchor is not None:
            raise _Invalid(path, "has an anchor. Anchors and aliases aren't accepted.")
        if isinstance(event, ScalarEvent):
            return self._scalar(event, path)
        if isinstance(event, SequenceStartEvent):
            self._no_tag(event.tag, path)
            items: list[object] = []
            while not isinstance(self._loader.peek_event(), SequenceEndEvent):
                items.append(self._value((*path, len(items))))
            self._loader.get_event()
            return items
        if isinstance(event, MappingStartEvent):
            self._no_tag(event.tag, path)
            mapping: dict[str, object] = {}
            while not isinstance(self._loader.peek_event(), MappingEndEvent):
                key = self._key(path)
                if key in mapping:
                    raise _Invalid((*path, key), "appears more than once.")
                mapping[key] = self._value((*path, key))
            self._loader.get_event()
            return mapping
        raise _Invalid(path, "isn't a value this reader accepts.")

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
                path, "is a YAML 1.1 boolean other than true or false. Write true or false."
            )
        if tag == f"{_TAG}int":
            if not _INTEGER.fullmatch(text):
                raise _Invalid(
                    path,
                    "is a number in a form a YAML 1.1 loader converts, with a leading zero, an "
                    "underscore, a sign, a base prefix, or a colon. Write plain decimal digits, "
                    "or quote it if it's text.",
                )
            number = int(text)
            if number > MAX_SAFE_INTEGER:
                raise _Invalid(
                    path, f"is larger than {MAX_SAFE_INTEGER}, the largest integer accepted."
                )
            return number
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
