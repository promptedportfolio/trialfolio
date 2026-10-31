"""A report parsed with the standard library's `html.parser` into a tree of elements, so a test can
check what each element holds and where it sits (release 0.1.0, test pairing: R01-AC13 parses
each report with `html.parser`). It isn't a double: it replaces nothing.

From release 0.4.0's R04-T13, it also parses the parts of a report of a ranking definition: its
weights, its definition's source, and each attempt's exchanges, its `POST /rank` among them, with
its cost (release 0.4.0, test pairing: the report parser).

TS-T06 wrote here, once, the checks of the rules every kind of report keeps, R01-AC13's and, for a
review's, R02-AC09's, each in the strictest form any kind's copy had, which each kind's test calls
(docs/test-refactoring.md, finding 10): the concise notice, the full notice, the closing section,
the links, that it runs and loads nothing, "Not assessed", that no case is called best, and that
it renders again the same. Their expected values are written here by hand, or read from LICENSE,
apart from the notices' text, which tests/contract/test_notices.py checks against the documents.
"""

import json
import posixpath
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path
from typing import Final, override
from urllib.parse import unquote, urlsplit

from tests.support.paths import ROOT
from trialfolio.notices import (
    CONCISE_NOTICE,
    FULL_NOTICE,
    PORTFOLIO123_DATA_LABEL,
    PORTFOLIO123_DATA_STATEMENT,
)
from trialfolio.report import FULL_NOTICE_ID

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
    source: str
    """The report as it was parsed."""

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
    return Document(
        parser.root,
        parser.order,
        tuple(parser.declarations),
        tuple(parser.comments),
        document,
    )


# The rules every report keeps (R01-AC13, and R02-AC09 for a review's)

LICENSE_NAME: Final = (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()[0]
"""The license's name, as LICENSE's first line gives it."""
LICENSE_ID: Final = "LicenseRef-NSPRL-1.1"
NOTICE_VERSION: Final = "1.0"
TERMS_URL: Final = "https://www.portfolio123.com/legal"
"""Portfolio123's terms, one of the two outside links D-21 allows a report."""
LOADERS: Final = ("script", "link", "iframe", "object", "embed", "img", "base", "form", "svg")
"""The elements that could run or load something, none of which a report holds."""
RANKING_WORDS: Final = re.compile(
    r"[^.]*\b(?:best|better|worse|ranks?|ranked|top|winner|wins|outperforms?)\b[^.]*\.",
    re.IGNORECASE,
)
"""A sentence with a word that could call a case best or rank it."""


def license_link(version: str) -> str:
    """The LICENSE published with Trial Folio `version`, by its tag: the other outside link D-21
    allows a report."""
    return f"https://github.com/promptedportfolio/trialfolio/blob/v{version}/LICENSE"


def assert_concise_notice_first(document: Document) -> None:
    """The concise notice, `#notice`, is the one paragraph with its text, before every section and
    table, and its one link is to the full notice, in the page, a `<details>` element."""
    notice = document.root.by_id("notice")
    (paragraph,) = (p for p in document.root.find_all("p") if p.text == CONCISE_NOTICE)
    (link,) = notice.find_all("a")

    assert paragraph is notice
    assert link.attrs["href"] == f"#{FULL_NOTICE_ID}"
    assert document.root.by_id(FULL_NOTICE_ID).tag == "details"
    for later in (*document.root.find_all("section"), *document.root.find_all("table")):
        assert document.before(notice, later)


def assert_full_notice(document: Document, version: str) -> None:
    """The full notice is the one `<details>` element, with the full notice's paragraphs first, the
    license's name and identifier, and the notice's version, and its one link is to the LICENSE
    published with `version`, the version that rendered the report."""
    (details,) = document.root.find_all("details")
    paragraphs = [p.text for p in details.find_all("p")]

    assert details is document.root.by_id(FULL_NOTICE_ID)
    assert paragraphs[: len(FULL_NOTICE)] == list(FULL_NOTICE)
    assert LICENSE_NAME in details.text
    assert LICENSE_ID in details.text
    assert f"Notice version {NOTICE_VERSION}." in details.text
    assert [a.attrs["href"] for a in details.find_all("a")] == [license_link(version)]


def assert_closing(document: Document) -> None:
    """The closing section, `#closing`, is the one `<footer>`, after every section. It holds the
    Portfolio123 data statement, whose one link is to Portfolio123's terms, and then the full
    notice, outside which the statement is."""
    (footer,) = document.root.find_all("footer")
    (details,) = document.root.find_all("details")
    (statement,) = (p for p in footer.find_all("p") if p.text.startswith(PORTFOLIO123_DATA_LABEL))
    (terms,) = statement.find_all("a")

    assert footer is document.root.by_id("closing")
    assert statement.text == f"{PORTFOLIO123_DATA_LABEL} {PORTFOLIO123_DATA_STATEMENT}"
    assert terms.text == "Portfolio123's terms"
    assert terms.attrs["href"] == TERMS_URL
    assert not statement.inside(details)
    assert document.before(statement, details)
    assert details.inside(footer)
    for section in document.root.find_all("section"):
        assert document.before(section, footer)


def listed_files(root: Path, manifest: str) -> set[str]:
    """The files a report links, by their paths in `root`, the directory of its run, review, or
    experiment: the manifest at `manifest` in `root`, which lists the report, and each other file
    it lists."""
    content = json.loads((root / manifest).read_bytes())
    return {manifest} | {a["path"] for a in content["artifacts"] if a["role"] != "report"}


def assert_links(document: Document, version: str, report: Path, root: Path, manifest: str) -> None:
    """The report at `report` links only these. Its outside links, those with a scheme or a host,
    are the LICENSE published with `version` and Portfolio123's terms, each once. Each link in the
    page names an element's ID. Each other link is a file in `root`, the directory of its run,
    review, or experiment, by the path from the report's directory to `root`, then the file's path
    in `root`, without an empty, `.`, or `..` part; and they're the files the manifest at
    `manifest` in `root` lists, other than the report, and that manifest."""
    hrefs = [a.attrs["href"] or "" for a in document.root.find_all("a")]
    ids = {element.attrs.get("id") for element in document.root.iter()}
    outside = [href for href in hrefs if urlsplit(href).scheme or urlsplit(href).netloc]
    up = posixpath.relpath(root.resolve(), report.parent.resolve())
    prefix = "" if up == "." else f"{up}/"

    assert sorted(outside) == sorted([license_link(version), TERMS_URL])
    linked: set[str] = set()
    for href in hrefs:
        if href in outside:
            continue
        if href.startswith("#"):
            assert href[1:] in ids, href
            continue
        path = unquote(href)
        assert path.startswith(prefix), href
        path = path.removeprefix(prefix)
        assert all(part not in ("", ".", "..") for part in path.split("/")), href
        assert (root / path).is_file(), href
        linked.add(path)
    assert linked == listed_files(root, manifest)


def assert_loads_nothing(document: Document) -> None:
    """The report runs and loads nothing: it declares only `<!DOCTYPE html>`; it has none of the
    `LOADERS`, no event attribute, no `src` or `style` attribute, and no `<meta http-equiv>`; its
    one stylesheet loads and imports nothing; and no `<script` is in its text, a comment's
    included."""
    elements = list(document.root.iter())
    (style,) = document.root.find_all("style")

    assert document.declarations == ("DOCTYPE html",)
    assert not [e for e in elements if e.tag in LOADERS]
    assert not [name for e in elements for name in e.attrs if name.lower().startswith("on")]
    assert not [e for e in elements if "src" in e.attrs or "style" in e.attrs]
    assert not [e for e in elements if e.tag == "meta" and "http-equiv" in e.attrs]
    assert not re.search(r"url\s*\(|@import", style.text, re.IGNORECASE)
    assert "<script" not in document.source.lower()


def assert_not_assessed(document: Document) -> None:
    """Statistical validation and trading readiness read "Not assessed", in each list of facts that
    names them and in their sections, and so does the section on robustness and concentration."""
    assert set(document.dd("Statistical validation")) == {"Not assessed"}
    assert set(document.dd("Trading readiness")) == {"Not assessed"}
    assert "Statistical validation: Not assessed." in document.root.by_id("statistics").text
    assert "Trading readiness: Not assessed." in document.root.by_id("feasibility").text
    assert document.root.by_id("robustness").text.startswith(
        "6. Robustness and concentration Not assessed."
    )


def assert_no_case_is_called_best(text: str, *allowed: str) -> list[str]:
    """No sentence of `text`, a report's `<main>`, calls a case best or ranks it: each sentence with
    one of the `RANKING_WORDS` says that no case is, or holds one of the phrases `allowed`, and at
    least one says that no case is. Gives those sentences."""
    said = RANKING_WORDS.findall(text)

    assert any("no case" in sentence.lower() for sentence in said), said
    assert all(
        "no case" in sentence.lower() or any(phrase in sentence for phrase in allowed)
        for sentence in said
    ), said
    return said


def assert_renders_the_same_again(
    html: str, render: Callable[[str], str], version: str, later: str
) -> Document:
    """`render`, given a version of Trial Folio, renders the report again: with `version`, it gives
    `html`, byte for byte, and with `later`, a report that names `later` as the version that
    rendered it, with the LICENSE published with it. Gives that report, parsed."""
    assert render(version) == html
    document = parse(render(later))

    details = document.root.by_id(FULL_NOTICE_ID)
    assert [a.attrs["href"] for a in details.find_all("a")] == [license_link(later)]
    assert document.dd("Report rendered by") == [f"Trial Folio {later}"]
    return document
