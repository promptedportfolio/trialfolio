"""The YAML reader that refuses ambiguous forms: a configuration file's bytes in, plain values
out (docs/contracts.md, configuration files; ADR 0002). `trialfolio.configuration`'s readers
read every configuration file with it, before they validate its values as their model.

It builds plain values from PyYAML's parse events, never through PyYAML's constructors, so it
decides what each scalar means:

- A quoted or block scalar is text.
- A plain scalar is resolved as a YAML 1.1 safe loader would resolve it, and kept only when that
  reading is unambiguous: `true` or `false`; an integer in plain decimal digits; a decimal in
  plain notation, as a `Decimal` read from its text; or a date written `YYYY-MM-DD`. Any other
  form a YAML 1.1 loader would convert, such as `010`, `1:30`, `yes`, or `2.5e-1`, is rejected.
- Null values, duplicate keys, non-text keys, anchors, aliases, explicit tags, and credential-like
  keys are rejected.

It also gives where the file writes each value, for the readers' rules and records: each
top-level value's text, and every value's, by its key path, exactly as the file writes it; and
where a plain scalar is read as text, for the readers' rule that the text Portfolio123 receives
is quoted.

A reader can say which mappings are keyed by node paths, such as a ranking variant's `set`,
whose keys hold the user's strategy definition (docs/contracts.md, node paths). Each entry of
such a mapping is named by its place, counted from 0, never by its key, in the paths it gives
and in its messages.

Its messages, `YamlRefused`'s, name the offending key and never include its value. A key's
control and formatting characters and lone surrogates are written as escapes (`format_path`).
"""

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final, NoReturn, Protocol, cast

import yaml
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

from trialfolio.contracts.common import DATE_PATTERN, INTEGER_PATTERN
from trialfolio.display import visible

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


class YamlRefused(Exception):
    """The file breaks a rule of the reader: `problem`, at the key `path`, or at the file as a
    whole when `path` is empty. The problem is a sentence's predicate, such as "is an alias.
    Write the value out instead.", which its subject, the key or the file, completes."""

    def __init__(self, path: KeyPath, problem: str) -> None:
        super().__init__(problem)
        self.path = path
        self.problem = problem


@dataclass(frozen=True)
class ReadYaml:
    """What the reader read from a file."""

    document: object
    """The document's value."""
    originals: Mapping[str, str]
    """Each top-level value's text, by key, from its first character to its last one that isn't
    YAML white space or a line break: so it keeps quotes, block indicators, and, inside a block
    list or mapping, the line breaks, indentation, and comments between its items."""
    plain_text: tuple[KeyPath, ...]
    """Where a plain scalar, without quotes or a block indicator, was read as text, in the
    file's order. An entry of a mapping keyed by node paths is there, by its place, when its key
    is written that way."""
    values: Mapping[str, str]
    """Every value's text, as `originals` gives a top-level one's, by its key path as
    `format_path` writes it, such as `variants.rules[0].add`."""


def read_yaml(content: bytes, *, by_place: Callable[[KeyPath], bool] | None = None) -> ReadYaml:
    """Reads a configuration file's bytes, which must be UTF-8 text, with an optional BOM, and
    one YAML document, by the module's rules. `by_place` says which mappings, by their key path,
    are keyed by node paths; none without it.

    Raises `YamlRefused` when the file breaks a rule, isn't UTF-8 text, or isn't valid YAML.
    PyYAML's own wording can quote characters of a value, so its messages are left out, apart
    from where the problem is.
    """
    try:
        text = content.decode("utf-8").removeprefix("\ufeff")
    except UnicodeDecodeError:
        raise YamlRefused((), "isn't UTF-8 text.") from None
    try:
        builder = _Builder(text, by_place=by_place)
        document = builder.document()
    except yaml.MarkedYAMLError as error:
        mark = error.problem_mark
        place = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
        raise YamlRefused((), f"isn't valid YAML{place}.") from None
    except yaml.YAMLError:
        raise YamlRefused((), "isn't valid YAML.") from None
    return ReadYaml(
        document=document,
        originals=builder.originals,
        plain_text=tuple(builder.plain_text),
        values=builder.values,
    )


def format_path(path: KeyPath) -> str:
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


class _Mark(Protocol):
    """A position in the text, as PyYAML marks an event's start or end."""

    @property
    def index(self) -> int: ...


def _index(mark: _Mark | None) -> int:
    """Where a mark is, as an index into the text."""
    if mark is None:  # PyYAML's parser marks every event; its stubs allow none
        raise YamlRefused((), "isn't valid YAML.")
    return mark.index


class _Parser(Protocol):
    """The parts of PyYAML's `SafeLoader` the builder uses, which its stubs leave untyped."""

    def get_event(self) -> Event: ...
    def peek_event(self) -> Event: ...
    def resolve(self, kind: type[Node], value: str, implicit: tuple[bool, bool]) -> str: ...
    def dispose(self) -> None: ...


def _never(path: KeyPath) -> bool:
    return False


class _Builder:
    """Builds plain values from parse events, keeping where each is written: the traversal and
    the source spans. The rules of a key's name and of a plain scalar are module functions,
    `_check_key` and `_plain_value`."""

    def __init__(self, text: str, *, by_place: Callable[[KeyPath], bool] | None = None) -> None:
        self._text = text
        self._by_place = _never if by_place is None else by_place
        """Whether the mapping at a key path is keyed by node paths, so its entries are named by
        their place."""
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
        """Where a plain scalar, without quotes or a block indicator, was read as text. An entry of
        a mapping keyed by node paths is there, by its place, when its key is written that way."""

    def document(self) -> object:
        try:
            self._expect(StreamStartEvent)
            if isinstance(self._loader.peek_event(), StreamEndEvent):
                raise YamlRefused((), "is empty.")
            self._expect(DocumentStartEvent)
            value = self._value(())
            self._expect(DocumentEndEvent)
            if not isinstance(self._loader.peek_event(), StreamEndEvent):
                raise YamlRefused((), "must hold one YAML document, not several.")
            return value
        finally:
            self._loader.dispose()

    def _expect(self, kind: type[Event]) -> None:
        event = self._loader.get_event()
        if not isinstance(event, kind):  # PyYAML's parser guarantees the order
            raise YamlRefused((), "isn't valid YAML.")

    def _value(self, path: KeyPath) -> object:
        if len(path) > MAX_DEPTH:
            raise YamlRefused(path[:1], f"is nested more than {MAX_DEPTH} levels deep.")
        event = self._loader.get_event()
        if isinstance(event, AliasEvent):
            raise YamlRefused(path, "is an alias. Write the value out instead.")
        if not isinstance(event, NodeEvent):  # the parser yields a node here
            raise YamlRefused(path, "has no value.")
        if event.anchor is not None:
            raise YamlRefused(path, "has an anchor. Anchors and aliases aren't accepted.")
        value = self._node(event, path)
        if path:
            span = self._text[_index(event.start_mark) : self._end].rstrip(_YAML_SPACE)
            self.values[format_path(path)] = span
            if len(path) == 1 and isinstance(path[0], str):
                self.originals[path[0]] = span
        return value

    def _node(self, event: NodeEvent, path: KeyPath) -> object:
        if isinstance(event, ScalarEvent):
            self._end = _index(event.end_mark)
            return self._scalar(event, path)
        if isinstance(event, SequenceStartEvent):
            _no_tag(event.tag, path)
            items: list[object] = []
            while not isinstance(self._loader.peek_event(), SequenceEndEvent):
                items.append(self._value((*path, len(items))))
            self._close(event)
            return items
        if isinstance(event, MappingStartEvent):
            _no_tag(event.tag, path)
            mapping: dict[str, object] = {}
            # A mapping keyed by node paths, such as a ranking variant's `set`: each entry is
            # named by its place, never by its key.
            by_place = self._by_place(path)
            while not isinstance(self._loader.peek_event(), MappingEndEvent):
                place: KeyPath | None = (*path, len(mapping)) if by_place else None
                key = self._key(path, place)
                where = (*path, key) if place is None else place
                if key in mapping:
                    raise YamlRefused(
                        where,
                        "appears more than once."
                        if place is None
                        else "repeats the path of an earlier entry of the same set. Write each "
                        "path once.",
                    )
                mapping[key] = self._value(where)
            self._close(event)
            return mapping
        raise YamlRefused(path, "isn't a value this reader accepts.")

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
            raise YamlRefused(path, "has a key that isn't plain text.")
        key = event.value
        plain = event.style is None
        tag = self._loader.resolve(ScalarNode, key, (True, False)) if plain else None
        _check_key(key, tag, path, place)
        if place is not None and plain:
            self.plain_text.append(place)
        return key

    def _scalar(self, event: ScalarEvent, path: KeyPath) -> object:
        _no_tag(event.tag, path)
        text = event.value
        if event.style is not None:
            return text
        tag = self._loader.resolve(ScalarNode, text, (True, False))
        # An entry of a mapping keyed by node paths is named by its place, which `_key` records
        # when its node path is written without quotes. Its value is a weight, never text, which
        # the model reports, so it isn't recorded there too.
        if tag == _STR and not self._by_place(path[:-1]):
            self.plain_text.append(path)
        return _plain_value(text, tag, path)


def _no_tag(tag: str | None, path: KeyPath) -> None:
    if tag is not None:
        raise YamlRefused(path, "has an explicit YAML tag. Tags aren't accepted.")


def _check_key(key: str, tag: str | None, path: KeyPath, place: KeyPath | None) -> None:
    """The rules of the name of a key of the mapping at `path`: YAML reads it as text, and it
    isn't credential-like. `tag` is the tag a plain key resolves to, and None for a quoted one.
    `place` names a key that's a node path by its place, which messages never quote."""
    if tag is not None and tag != _STR:
        raise YamlRefused(path, "has a key that YAML doesn't read as text. Quote it.")
    folded = key.lower().replace("-", "_")
    if any(word in folded for word in CREDENTIAL_WORDS):
        if place is not None:
            raise YamlRefused(
                place,
                "is a node path that holds a word a credential's key would, which no "
                "configuration's key may hold. Name the node whose name holds it by its "
                "position instead, such as #2.",
            )
        raise YamlRefused(
            (*path, key),
            "looks like a credential. A configuration never holds credentials: the CLI "
            "reads them from TRIALFOLIO_P123_API_ID and TRIALFOLIO_P123_API_KEY.",
        )


def _plain_value(text: str, tag: str, path: KeyPath) -> object:
    """A plain scalar's value, by the tag a YAML 1.1 safe loader resolves it to: text, or a
    boolean, an integer, a decimal, or a date in the one form of each that isn't ambiguous.
    Raises `YamlRefused` for a null, any other form, and any other tag."""
    if tag == _STR:
        return text
    plain = _PLAIN.get(tag)
    if plain is None:
        raise YamlRefused(path, "is a YAML form that isn't accepted. Quote it if it's text.")
    return plain(text, path)


def _null(text: str, path: KeyPath) -> NoReturn:
    raise YamlRefused(path, "has no value. Give it one, or leave the key out.")


def _boolean(text: str, path: KeyPath) -> bool:
    if text in ("true", "false"):
        return text == "true"
    raise YamlRefused(
        path,
        "is a YAML 1.1 boolean other than true or false. Write true or false, or quote "
        "it if it's text.",
    )


def _integer(text: str, path: KeyPath) -> int:
    if not _INTEGER.fullmatch(text):
        raise YamlRefused(
            path,
            "is a number in a form a YAML 1.1 loader converts, with a leading zero, an "
            "underscore, a sign, a base prefix, or a colon. Write plain decimal digits, "
            "or quote it if it's text.",
        )
    # The models check each key's limit. This one keeps int() from text it can't convert:
    # Python refuses more than 4300 digits.
    if len(text) > MAX_DIGITS:
        raise YamlRefused(path, f"has more than {MAX_DIGITS} digits, more than any key takes.")
    return int(text)


def _decimal(text: str, path: KeyPath) -> Decimal:
    if not _DECIMAL.fullmatch(text):
        raise YamlRefused(
            path,
            "is a number in a form that isn't accepted, with an exponent, a sign, a "
            "leading point, a leading zero, or a colon, or an infinity or NaN. Write it "
            "in plain notation, such as 0.25.",
        )
    return Decimal(text)


def _date(text: str, path: KeyPath) -> date:
    if not _DATE.fullmatch(text):
        raise YamlRefused(path, "is a date with a time part. Write the date alone, YYYY-MM-DD.")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise YamlRefused(path, "isn't a valid date.") from None


_PLAIN: Final[Mapping[str, Callable[[str, KeyPath], object]]] = {
    f"{_TAG}null": _null,
    f"{_TAG}bool": _boolean,
    f"{_TAG}int": _integer,
    f"{_TAG}float": _decimal,
    f"{_TAG}timestamp": _date,
}
"""The helper of each tag a plain scalar may resolve to, besides text's, by the tag."""
