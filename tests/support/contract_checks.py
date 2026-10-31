"""The contract tests' shared checks, which TS-T06 wrote once (docs/test-refactoring.md, finding 9):
a model's valid document, changed, and whether the model accepts it; and a configuration file's
refusal, `config.invalid`, with its message, which names the offending key and never its value.

Each is the strictest form the contract modules' copies had. A refusal's log message is its
message, which the screen configuration's copy didn't check, and an invalid file's message holds
neither the value on its `# Value:` line nor any long value it gives, which the screen's and the
snapshot's copies didn't check (copies that check less, items 5 and 6).
"""

import json
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from trialfolio.errors import TrialFolioError

type Document = dict[str, Any]
"""A model's document, as JSON reads it."""
type Change = Callable[[Document], object]
"""A change to a document, in place."""
type Reader = Callable[[bytes, str], object]
"""A configuration's reader, given the file's bytes and the name it's read under."""


def digest(seed: str) -> str:
    """A `sha256:` digest, the two characters `seed` repeated."""
    return "sha256:" + seed * 32


def changed(build: Callable[[], Document], change: Change) -> Document:
    """A copy of the document `build` gives, with `change` made to it."""
    document = deepcopy(build())
    change(document)
    return document


def accepts(model: type[BaseModel], document: Document) -> None:
    model.model_validate_json(json.dumps(document))


def rejects(model: type[BaseModel], document: Document) -> None:
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(document))


@dataclass(frozen=True)
class Rejection:
    """Reads a configuration with `reader`, under `source_name`, unless a call gives another of
    each, and expects `config.invalid`, whose log message is its message. Gives the message."""

    reader: Reader
    source_name: str

    def __call__(
        self, content: bytes | str, source_name: str | None = None, reader: Reader | None = None
    ) -> str:
        if isinstance(content, str):
            content = content.encode()
        with pytest.raises(TrialFolioError) as caught:
            (reader or self.reader)(content, source_name or self.source_name)
        assert caught.value.code == "config.invalid"
        assert caught.value.log_message == caught.value.message
        return caught.value.message


def header(content: str, name: str) -> str:
    """The value of an invalid file's `# <name>:` line, such as `Key` or `Value`."""
    found = re.search(rf"^# {name}: (.+)$", content, re.MULTILINE)
    assert found, f"no '# {name}:' line"
    return found.group(1)


def contains_value(message: str, value: str) -> bool:
    """Whether `message` holds `value` as a whole, not inside a longer name: `max_holding` isn't
    in `max_holdings`, nor `25` in `0.25`. A full stop counts as part of a name, so a value that
    ends a sentence, as `25` in `is 25.`, isn't found either."""
    word = r"[A-Za-z0-9_.-]"
    return re.search(rf"(?<!{word}){re.escape(value)}(?!{word})", message) is not None


def assert_names_its_key_never_its_value(path: Path, message: str) -> None:
    """`message`, the refusal of the invalid file at `path`, says the file isn't a valid
    configuration, and names the key on its `# Key:` line, unless that's `-`, the file as a whole.
    It never holds the value on its `# Value:` line, unless that's `-`, no value to look for, nor
    any value of 20 characters or more the file gives."""
    content = path.read_text(encoding="utf-8")
    key, value = header(content, "Key"), header(content, "Value")
    body = "\n".join(line for line in content.splitlines() if not line.startswith("#"))

    assert message.startswith(f"{path.name} isn't a valid configuration:")
    if key != "-":
        assert f"`{key}`" in message
    if value != "-":
        assert not contains_value(message, value)
    for long_value in re.findall(r":[ \t]+'?([^'\n]{20,}?)'?$", body, re.MULTILINE):
        assert long_value not in message
