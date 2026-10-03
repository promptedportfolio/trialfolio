"""Showing text Trial Folio didn't write, such as a configuration's title and formulas, or a path a
saved run names, so that it can't act on a terminal or reorder what's shown (docs/contracts.md,
reports)."""

import unicodedata
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
