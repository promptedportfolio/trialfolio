"""Showing text in messages and reports.

`visible` shows text Trial Folio didn't write, such as a configuration's title and formulas, or a
path a saved run names, so that it can't act on a terminal or reorder what's shown
(docs/contracts.md, reports). `series` lists items in a sentence.
"""

import unicodedata
from collections.abc import Sequence
from typing import Final

_ESCAPED_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
"""Control and formatting characters, lone surrogates, and the line and paragraph separators."""


def visible(text: str, *, keep: str = "") -> str:
    """`text` with each control or formatting character, lone surrogate, and line or paragraph
    separator written as an escape, such as `\\u202e`, except the characters in `keep`."""
    return "".join(
        (f"\\u{ord(char):04x}" if ord(char) <= 0xFFFF else f"\\U{ord(char):08x}")
        if char not in keep and unicodedata.category(char) in _ESCAPED_CATEGORIES
        else char
        for char in text
    )


def series(items: Sequence[str]) -> str:
    """The items as a sentence lists them: `a`, `a and b`, or `a, b, and c`."""
    if len(items) <= 2:
        return " and ".join(items)
    return f"{', '.join(items[:-1])}, and {items[-1]}"
