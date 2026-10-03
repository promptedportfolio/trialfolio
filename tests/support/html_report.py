"""A report parsed with the standard library's `html.parser` into a tree of elements, so a test can
check what each element holds and where it sits (release 0.1.0, test pairing: R01-AC13 parses
each report with `html.parser`). It isn't a double: it replaces nothing.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from itertools import pairwise
from typing import override

VOID: frozenset[str] = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)
"""Elements that have no end tag."""


@dataclass(eq=False)
class Element:
    """One element, with its attributes and its children, elements and text, in order."""

    tag: str
    attrs: dict[str, str | None]
    parent: "Element | None" = None
    children: list["Element | str"] = field(default_factory=list["Element | str"])

    @property
    def text(self) -> str:
        """All the text inside, with each run of whitespace made one space, and a `<br>` read as
        one."""
        return " ".join(self._raw().split())

    def _raw(self) -> str:
        if self.tag == "br":
            return " "
        return "".join(child if isinstance(child, str) else child._raw() for child in self.children)

    def iter(self) -> Iterator["Element"]:
        """This element and every element inside it, in document order."""
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.iter()

    def find_all(self, tag: str) -> list["Element"]:
        return [element for element in self.iter() if element.tag == tag]

    def by_id(self, element_id: str) -> "Element":
        (found,) = (element for element in self.iter() if element.attrs.get("id") == element_id)
        return found

    def ancestors(self) -> Iterator["Element"]:
        parent = self.parent
        while parent is not None:
            yield parent
            parent = parent.parent

    def inside(self, other: "Element") -> bool:
        return any(ancestor is other for ancestor in self.ancestors())


@dataclass(frozen=True)
class Document:
    root: Element
    """The document's elements, under an unnamed root."""
    order: dict[int, int]
    """Each element's position in document order, by `id()`."""
    declarations: tuple[str, ...]
    comments: tuple[str, ...]

    def before(self, first: Element, second: Element) -> bool:
        return self.order[id(first)] < self.order[id(second)]

    def dd(self, term: str) -> list[str]:
        """The text of each `<dd>` that follows a `<dt>` whose text is `term`."""
        found: list[str] = []
        for definitions in self.root.find_all("dl"):
            children = [child for child in definitions.children if isinstance(child, Element)]
            for dt, dd in pairwise(children):
                if dt.tag == "dt" and dd.tag == "dd" and dt.text == term:
                    found.append(dd.text)
        return found

    def rows(self, table: Element) -> list[list[Element]]:
        """Each row's cells, `<th>` or `<td>`, header row included."""
        return [
            [cell for cell in row.children if isinstance(cell, Element)]
            for row in table.find_all("tr")
        ]


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("", {})
        self.current = self.root
        self.order: dict[int, int] = {}
        self.declarations: list[str] = []
        self.comments: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, dict(attrs), self.current)
        self.order[id(element)] = len(self.order)
        self.current.children.append(element)
        if tag not in VOID:
            self.current = element

    @override
    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag in VOID:
            return
        if self.current.tag != tag:
            raise AssertionError(f"</{tag}> closes <{self.current.tag}>")
        assert self.current.parent is not None
        self.current = self.current.parent

    @override
    def handle_data(self, data: str) -> None:
        self.current.children.append(data)

    @override
    def handle_decl(self, decl: str) -> None:
        self.declarations.append(decl)

    @override
    def handle_comment(self, data: str) -> None:
        self.comments.append(data)


def parse(document: str) -> Document:
    """Parses a report. Raises `AssertionError` if an element is closed out of order, or left
    open."""
    parser = _Parser()
    parser.feed(document)
    parser.close()
    if parser.current is not parser.root:
        raise AssertionError(f"<{parser.current.tag}> is never closed")
    return Document(parser.root, parser.order, tuple(parser.declarations), tuple(parser.comments))
