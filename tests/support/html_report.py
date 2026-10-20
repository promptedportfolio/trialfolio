"""A report parsed with the standard library's `html.parser` into a tree of elements, so a test can
check what each element holds and where it sits (release 0.1.0, test pairing: R01-AC13 parses
each report with `html.parser`). It isn't a double: it replaces nothing.

From release 0.4.0's R04-T13, it also parses the parts of a report of a ranking definition: its
weights, its definition's source, and each attempt's exchanges, its `POST /rank` among them, with
its cost (release 0.4.0, test pairing: the report parser).
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

    @property
    def lines(self) -> list[str]:
        """The text inside, split at each `<br>`, each line as `text` gives it."""
        lines: list[list[str]] = [[]]

        def walk(element: Element) -> None:
            for child in element.children:
                if isinstance(child, str):
                    lines[-1].append(child)
                elif child.tag == "br":
                    lines.append([])
                else:
                    walk(child)

        walk(self)
        return [" ".join("".join(parts).split()) for parts in lines]

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

    def table_after(self, heading: str) -> Element:
        """The first table after the `<h3>` whose text starts with `heading`."""
        (h3,) = (h for h in self.root.find_all("h3") if h.text.startswith(heading))
        return next(t for t in self.root.find_all("table") if self.before(h3, t))

    def rows(self, table: Element) -> list[list[Element]]:
        """Each row's cells, `<th>` or `<td>`, header row included."""
        return [
            [cell for cell in row.children if isinstance(cell, Element)]
            for row in table.find_all("tr")
        ]

    def texts(self, table: Element) -> list[list[str]]:
        """The text of each cell of each row of `table`, its header row first."""
        return [[cell.text for cell in row] for row in self.rows(table)]

    def heading(self, text: str) -> Element:
        """The one `<h3>` whose text is exactly `text`."""
        (found,) = (h for h in self.root.find_all("h3") if h.text == text)
        return found

    def has_heading(self, text: str) -> bool:
        """Whether an `<h3>` has exactly the text `text`."""
        return any(h.text == text for h in self.root.find_all("h3"))

    def under(self, heading: str) -> list[Element]:
        """The elements that follow the `<h3>` whose text is exactly `heading`, beside it in its
        section, up to the next heading."""
        h3 = self.heading(heading)
        assert h3.parent is not None
        siblings = [child for child in h3.parent.children if isinstance(child, Element)]
        after = siblings[siblings.index(h3) + 1 :]
        end = next((i for i, e in enumerate(after) if e.tag in ("h2", "h3")), len(after))
        return after[:end]

    def items_under(self, heading: str) -> list[str]:
        """The text of each item of the lists under the `<h3>` `heading`, such as
        "Limitations"."""
        return [li.text for e in self.under(heading) for li in e.find_all("li")]

    # A ranking definition's parts (release 0.4.0)

    def ranking_weights(self) -> list[list[str]]:
        """The weights a report of a ranking definition shows, header row first: a run's table of
        each node's weight, under "The ranking definition", or an experiment session's of each
        case's, under "The ranking's weights"."""
        for heading in ("The ranking definition", "The ranking's weights"):
            if self.has_heading(heading):
                (table,) = (t for e in self.under(heading) for t in e.find_all("table"))
                return self.texts(table)
        raise AssertionError("the report shows no ranking weights")

    def ranking_sources(self) -> list[tuple[str | None, str]]:
        """The ranking definition's source, under "The ranking definition's source", as
        `(plan, source)` pairs: a run's, its paragraph, with no plan, or an experiment session's,
        each plan's row of its table, oldest first."""
        under = self.under("The ranking definition's source")
        tables = [t for e in under for t in e.find_all("table")]
        if not tables:
            (paragraph, *_) = (p for e in under for p in e.find_all("p"))
            return [(None, paragraph.text)]
        (table,) = tables
        header, *rows = self.texts(table)
        assert header == ["Plan", "Source"], header
        return [(plan, source) for plan, source in rows]

    def attempts_shown(self) -> list["AttemptShown"]:
        """Each attempt a report shows, in its order: a run's, each `Attempt <id>` with its
        exchanges' table and its cost; or an experiment session's, each row of its cases' tables
        of attempts, whose caption names the case."""
        shown: list[AttemptShown] = []
        for h3 in self.root.find_all("h3"):
            if not h3.text.startswith("Attempt "):
                continue
            under = self.under(h3.text)
            (cost,) = (
                dd.text
                for e in under
                for dt, dd in pairwise(c for c in e.children if isinstance(c, Element))
                if dt.tag == "dt" and dd.tag == "dd" and dt.text == "Cost"
            )
            (table,) = (t for e in under for t in e.find_all("table"))
            exchanges = tuple(
                f"{request}: {result} {status}".rstrip()
                for _, request, result, status, _ in self.texts(table)[1:]
            )
            shown.append(AttemptShown(None, h3.text.removeprefix("Attempt "), exchanges, cost))
        for table in self.root.find_all("table"):
            rows = self.rows(table)
            if not rows or [cell.text for cell in rows[0]][:1] != ["Attempt"]:
                continue
            names = [cell.text for cell in rows[0]]
            (caption,) = table.find_all("caption")
            for row in rows[1:]:
                cells = dict(zip(names, row, strict=True))
                cost = cells["Cost"].text if "Cost" in cells else ""
                shown.append(
                    AttemptShown(
                        caption.text,
                        cells["Attempt"].text,
                        tuple(cells["Exchanges"].lines),
                        cost,
                    )
                )
        return shown


@dataclass(frozen=True)
class AttemptShown:
    """An attempt as a report shows it."""

    case: str | None
    """An experiment's case, as its table's caption names it, `<case-key>, <case_id>`; None in a
    run's report, which has one case."""
    attempt_id: str
    exchanges: tuple[str, ...]
    """Each exchange, in order, as `<request>: <result> <status>`, such as
    `POST /rank: Response 200`."""
    cost: str
    """Its cost, as the report gives it; empty in a table of attempts without a `Cost` column."""


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
