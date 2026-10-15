"""Ranking system definitions: reading one, naming its nodes, and applying a ranking variant
(docs/contracts.md, ranking definitions, node paths, and ranking variants; release 0.4.0's
R04-T06).

- `read_definition` reads a definition from the bytes of its file, by the rules of its text and
  its form, into a `RankingDefinition`: its text, with each line end read as a line feed, and
  its nodes, in the definition's order, each with its canonical path. It raises
  `DefinitionProblem`, which gives the rule broken and the line at fault, and never quotes the
  definition, which is the user's strategy definition.
- `parse_node_path` reads a node path into its segments, names and positions, and
  `RankingDefinition.node` finds the one node a path names. Each raises `NodePathProblem`, which
  gives the segment at fault by its number, counted from 1, never the path's text.
- `apply_ranking_variant` gives a ranking variant's case: its definition, the baseline's with
  the variant's change, made by the text rules, and the nodes it sets and removes, by the
  baseline's nodes. `check_node_paths` checks only how a variant's paths are written, for a
  baseline whose definition isn't read yet. Each raises `VariantProblem`, which names the entry
  at fault by its place in the configuration, such as `variants.ranking[0].set[1]`.

The configuration's readers, in `trialfolio.configuration`, read the file a configuration names,
and turn these problems into `config.invalid`.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final, Literal, NoReturn, cast
from xml.parsers import expat

from trialfolio.canonical import sha256_hex
from trialfolio.contracts.experiment_configuration import RankingVariant
from trialfolio.contracts.screen_configuration import normalize_decimal
from trialfolio.display import series

type NodeKind = Literal["Composite", "StockFormula", "StockFactor"]
"""A node's type: the three types R04-T01 read in the owner's saved systems."""

NODE_KINDS: Final[tuple[NodeKind, ...]] = ("Composite", "StockFormula", "StockFactor")

_FACTOR_ELEMENTS: Final = {"StockFormula": "Formula", "StockFactor": "Factor"}
"""The one element each factor may hold."""

_XML_SPACE: Final = b" \t\n\r"
"""XML 1.0's white space, its production S: what a ranking system or a composite may hold
between its nodes."""

_DECIMAL: Final = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]+)?")
"""A decimal in plain notation (screen configuration, decimals)."""

_POSITION: Final = re.compile(r"0|[1-9][0-9]*")
"""A position's number, after its `#`: a whole number without a leading zero."""

_ATTRIBUTE: Final = re.compile(
    rb"[ \t\n\r]+([^ \t\n\r=/>]+)[ \t\n\r]*=[ \t\n\r]*(\"[^\"]*\"|'[^']*')"
)
"""An attribute in a start tag that expat has found well-formed, with its value in quotes."""

_JUNK_AFTER_ROOT: Final = expat.errors.codes[expat.errors.XML_ERROR_JUNK_AFTER_DOC_ELEMENT]


class DefinitionProblem(Exception):
    """A definition breaks a rule of its text or its form. `problem` says which, in words that
    hold nothing from the definition, and `line`, counted from 1, is where: the line of the
    element at fault, or of the text or byte at fault; None for the file as a whole."""

    def __init__(self, problem: str, line: int | None = None) -> None:
        super().__init__(problem)
        self.problem = problem
        self.line = line


class NodePathProblem(Exception):
    """A node path is written wrongly, or names no node, or more than one. `segment` is the
    segment at fault, counted from 1, and `problem` says what's wrong with it, without the path's
    text."""

    def __init__(self, segment: int, problem: str) -> None:
        super().__init__(problem)
        self.segment = segment
        self.problem = problem


class VariantProblem(Exception):
    """A ranking variant breaks a rule. `where` is the entry at fault, by its place in the
    configuration, such as `variants.ranking[0].set[1]`, and `problem` what follows it in the
    message, without a path, a name, a weight, or the definition."""

    def __init__(self, where: str, problem: str) -> None:
        super().__init__(problem)
        self.where = where
        self.problem = problem


@dataclass(frozen=True)
class RankingNode:
    """A node of a ranking definition: a composite, or a factor."""

    index: int
    """Its place in the definition's order, from 0: each node before the nodes it holds."""
    parent: int | None
    """The `index` of the composite that holds it, or None for a top-level node."""
    position: int
    """Its position among its parent's nodes, from 1."""
    kind: NodeKind
    name: str | None
    """Its `Name` attribute, as XML reads it, with its references replaced; None when it has
    none, or an empty one."""
    weight: Decimal
    """Its `Weight`, normalized as a configuration's decimal is: `40.0` is 40."""
    weight_text: str
    """Its `Weight` as the definition writes it, between its quotes, such as `40.0`."""
    path: str
    """Its canonical path (node paths): by its name where no other node of its parent has it,
    and by its position otherwise, with escapes."""
    line: int
    """The line of its start tag, from 1."""
    span: tuple[int, int]
    """Where its element is in the definition's UTF-8 text: from the `<` of its start tag to
    just after the `>` that ends its end tag, or its empty-element tag."""
    weight_span: tuple[int, int]
    """Where its `Weight` attribute's value is in the definition's UTF-8 text, between its
    quotes."""


@dataclass(frozen=True)
class RankingDefinition:
    """A ranking system's definition, read and checked."""

    content: bytes
    """The bytes it was read from: a file's, which a plan's `definition.xml` copies, or, for a
    ranking variant's case, its text's."""
    text: str
    """The definition: `content` as UTF-8, with each carriage return and line feed, and each
    carriage return alone, read as a line feed. It's what `rank_update` sends."""
    nodes: tuple[RankingNode, ...]
    """Every node, in the definition's order: each node before the nodes it holds, as the
    weight rows give them."""

    @property
    def hash(self) -> str:
        """`sha256:` and the hex SHA-256 of its UTF-8 text, as an `artifact_id` is formed: the
        `definition` of the case's `ranking` setting."""
        return "sha256:" + sha256_hex(self.text.encode("utf-8"))

    def children(self, parent: RankingNode | None) -> tuple[RankingNode, ...]:
        """The nodes `parent` holds, in order; the top-level nodes for None."""
        index = None if parent is None else parent.index
        return tuple(node for node in self.nodes if node.parent == index)

    def node(self, path: str) -> RankingNode:
        """The one node `path` names. Raises `NodePathProblem` when the path is written wrongly,
        or one of its segments names no node, or more than one."""
        first, *rest = parse_node_path(path)  # a path has at least one segment
        node = self._child(None, 1, first)
        for number, segment in enumerate(rest, start=2):
            node = self._child(node, number, segment)
        return node

    def _child(self, parent: RankingNode | None, number: int, segment: str | int) -> RankingNode:
        """The one node of `parent` that `segment`, the path's segment `number`, names."""
        nodes = self.children(parent)
        if isinstance(segment, int):
            if segment > len(nodes):
                raise NodePathProblem(number, "is a position past its parent's last node")
            return nodes[segment - 1]
        named = [node for node in nodes if node.name == segment]
        if not named:
            raise NodePathProblem(
                number, "names none of its parent's nodes in the baseline's definition"
            )
        if len(named) > 1:
            raise NodePathProblem(
                number,
                "names more than one of its parent's nodes. Name the one it means by its "
                "position instead, such as #2",
            )
        return named[0]


def read_definition(content: bytes) -> RankingDefinition:
    """The definition in `content`, a file's bytes, read by the rules of its text and its form
    (docs/contracts.md, ranking definitions). Raises `DefinitionProblem` for the first rule it
    finds broken."""
    if content.startswith(b"\xef\xbb\xbf"):
        raise DefinitionProblem(
            "the file starts with a byte-order mark, which the definition sent would hold. Save "
            "it as UTF-8 without one",
            1,
        )
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as error:
        valid = content[: error.start].decode("utf-8")
        raise DefinitionProblem(
            "the file isn't UTF-8 text. Save it as UTF-8, without a byte-order mark",
            _line_ends(valid).count("\n") + 1,
        ) from None
    text = _line_ends(decoded)
    # Before the parse: expat reads a file that starts with `<` and a NUL, or a NUL and `<`, as
    # UTF-16, whatever encoding it's told, and the elements' places would then be wrong.
    nul = text.find("\0")
    if nul >= 0:
        raise DefinitionProblem(
            "the file holds a NUL character, which XML 1.0 doesn't allow. A file saved as "
            "UTF-16 holds them: save it as UTF-8, without a byte-order mark",
            text.count("\n", 0, nul) + 1,
        )
    raw = text.encode("utf-8")
    root = _Tree(raw).root()
    if root.name != "RankingSystem":
        raise DefinitionProblem(
            "its root element isn't RankingSystem. A definition is the RankingSystem element "
            "that the website's Text Editor shows, under Ranking System, Factors",
            root.line,
        )
    elements: list[tuple[_Element, int | None, int]] = []
    _check_nodes(raw, root, None, elements)
    return RankingDefinition(content, text, _nodes(raw, elements))


def _line_ends(text: str) -> str:
    """`text` with each line end read as XML 1.0 reads it: a carriage return and line feed, and
    a carriage return alone, as a line feed."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


@dataclass
class _Element:
    """An element of the definition, as the parse found it."""

    name: str
    attributes: dict[str, str]
    """Its attributes, as XML reads them, with their references replaced."""
    start: int
    """Where its start tag's `<` is."""
    tag_end: int
    """Just after its start tag's `>`."""
    line: int
    empty: bool
    """Whether it's an empty-element tag, `<…/>`."""
    content_end: int = 0
    """Where its end tag starts: `tag_end` for an empty-element tag."""
    end: int = 0
    """Just after the `>` of its end tag: `tag_end` for an empty-element tag."""
    children: "list[_Element]" = field(default_factory=list["_Element"])


class _Tree:
    """The definition's elements, from expat's parse of its UTF-8 text, which checks that it's
    well-formed XML 1.0. A declaration, a document type declaration, a comment, or a processing
    instruction stops the parse: a document type declaration, before its entities are
    defined."""

    def __init__(self, raw: bytes) -> None:
        self._raw = raw
        self._parser = expat.ParserCreate(encoding="UTF-8")
        self._parser.ordered_attributes = True
        self._parser.StartElementHandler = self._start
        self._parser.EndElementHandler = self._end
        self._parser.XmlDeclHandler = self._declaration
        self._parser.StartDoctypeDeclHandler = self._doctype
        self._parser.CommentHandler = self._comment
        self._parser.ProcessingInstructionHandler = self._instruction
        self._open: list[_Element] = []
        self._root: _Element | None = None

    def root(self) -> _Element:
        try:
            self._parser.Parse(self._raw, True)
        except expat.ExpatError as error:
            if error.code == _JUNK_AFTER_ROOT:
                raise DefinitionProblem(
                    "it holds something other than white space after its RankingSystem element",
                    error.lineno,
                ) from None
            raise DefinitionProblem(
                f"it isn't well-formed XML 1.0: {expat.ErrorString(error.code)}", error.lineno
            ) from None
        if self._root is None:  # expat requires a root element
            raise DefinitionProblem("it holds no element")
        return self._root

    def _here(self) -> int:
        return self._parser.CurrentLineNumber

    def _start(self, name: str, attributes: list[str]) -> None:
        start = self._parser.CurrentByteIndex
        tag_end = _tag_end(self._raw, start)
        element = _Element(
            name,
            dict(zip(attributes[::2], attributes[1::2], strict=True)),
            start,
            tag_end,
            self._here(),
            empty=self._raw[tag_end - 2 : tag_end] == b"/>",
        )
        if self._open:
            self._open[-1].children.append(element)
        else:
            self._root = element
        self._open.append(element)

    def _end(self, _name: str) -> None:
        element = self._open.pop()
        if element.empty:
            element.content_end = element.end = element.tag_end
        else:
            element.content_end = self._parser.CurrentByteIndex
            element.end = self._raw.index(b">", element.content_end) + 1

    def _declaration(self, *_: object) -> NoReturn:
        raise DefinitionProblem(
            "it holds an XML declaration. A definition is its RankingSystem element alone, as "
            "the website's Text Editor shows it",
            self._here(),
        )

    def _doctype(self, *_: object) -> NoReturn:
        raise DefinitionProblem(
            "it holds a document type declaration, which could define entities that change the "
            "text Trial Folio reads",
            self._here(),
        )

    def _comment(self, _text: str) -> NoReturn:
        raise DefinitionProblem(
            "it holds a comment. A definition holds no comment, so what's sent is what the "
            "website's Text Editor shows",
            self._here(),
        )

    def _instruction(self, *_: object) -> NoReturn:
        raise DefinitionProblem("it holds a processing instruction", self._here())


def _tag_end(raw: bytes, start: int) -> int:
    """Just after the `>` of the start tag at `start`, past any `>` in its attributes' quoted
    values."""
    quote: int | None = None
    index = start + 1
    while True:
        byte = raw[index]
        if quote is not None:
            if byte == quote:
                quote = None
        elif byte in b"\"'":
            quote = byte
        elif byte == ord(">"):
            return index + 1
        index += 1


def _line_of(raw: bytes, offset: int) -> int:
    return raw.count(b"\n", 0, offset) + 1


def _check_nodes(
    raw: bytes,
    holder: _Element,
    parent: int | None,
    elements: list[tuple[_Element, int | None, int]],
) -> None:
    """Checks the nodes `holder`, the RankingSystem or a composite, holds, and what's between
    them, in the definition's order, and adds each node, with its parent's place in `elements`
    and its position, to `elements`."""
    children = holder.children
    if not children:
        what = "its RankingSystem element" if parent is None else "a Composite"
        raise DefinitionProblem(
            f"{what} holds no node. A ranking system, and each composite, holds at least one",
            holder.line,
        )
    gaps = [holder.tag_end, *(edge for child in children for edge in (child.start, child.end))]
    gaps.append(holder.content_end)
    for position, child in enumerate(children, start=1):
        _between_nodes(raw, gaps[2 * position - 2], gaps[2 * position - 1])
        if child.name not in NODE_KINDS:
            raise DefinitionProblem(
                "an element where a node goes isn't a Composite, a StockFormula, or a "
                "StockFactor, the node types a live check has read. Another type, such as a "
                "conditional node, fails until a live check verifies it (D-20)",
                child.line,
            )
        _weight(raw, child)
        index = len(elements)
        elements.append((child, parent, position))
        if child.name == "Composite":
            _check_nodes(raw, child, index, elements)
        else:
            _check_factor(child)
    _between_nodes(raw, gaps[-2], gaps[-1])


def _between_nodes(raw: bytes, start: int, end: int) -> None:
    for offset in range(start, end):
        if raw[offset] not in _XML_SPACE:
            raise DefinitionProblem(
                "it holds text between nodes, where a ranking system or a composite holds only "
                "white space",
                _line_of(raw, offset),
            )


def _check_factor(factor: _Element) -> None:
    """A StockFormula holds no element but Formula, a StockFactor none but Factor, and those
    hold no element. Their text isn't read."""
    allowed = _FACTOR_ELEMENTS[factor.name]
    for element in factor.children:
        if element.name != allowed:
            raise DefinitionProblem(
                f"a {factor.name} holds an element other than {allowed}, the one element it may "
                "hold",
                element.line,
            )
        if element.children:
            raise DefinitionProblem(
                f"a {allowed} holds an element, where it holds only text",
                element.children[0].line,
            )


def _weight(raw: bytes, node: _Element) -> tuple[Decimal, str, tuple[int, int]]:
    """The node's weight, normalized; its text as written; and where that text is. Raises
    `DefinitionProblem` when it has none, or it isn't a decimal greater than 0, written as the
    decimal itself."""
    span = _weight_span(raw, node)
    if span is None:
        raise DefinitionProblem(
            "a node has no Weight attribute. Every node has a weight, greater than 0", node.line
        )
    written = raw[span[0] : span[1]].decode("utf-8")
    if "&" in written:
        raise DefinitionProblem(
            "a node's Weight is written with a character or entity reference. Write the decimal "
            "itself, so a variant can rewrite it",
            node.line,
        )
    if not _DECIMAL.fullmatch(written):
        raise DefinitionProblem(
            "a node's Weight isn't a decimal in plain notation, such as 12.5: it's written "
            "without a percent sign, white space, a sign, or an exponent",
            node.line,
        )
    try:
        weight = normalize_decimal(Decimal(written))
    except ValueError as error:
        raise DefinitionProblem(f"a node's Weight {error}", node.line) from None
    if weight.is_zero():
        raise DefinitionProblem(
            "a node's Weight is 0, which Portfolio123 reads as equal weighting. A weight is "
            "greater than 0",
            node.line,
        )
    return weight, written, span


def _weight_span(raw: bytes, element: _Element) -> tuple[int, int] | None:
    """Where the value of the element's `Weight` attribute is, between its quotes; None when it
    has none."""
    tag = raw[element.start : element.tag_end]
    # Each attribute follows the one before it, or the element's name, after white space.
    found = _ATTRIBUTE.match(tag, 1 + len(element.name.encode("utf-8")))
    while found is not None:
        if found.group(1) == b"Weight":
            return element.start + found.start(2) + 1, element.start + found.end(2) - 1
        found = _ATTRIBUTE.match(tag, found.end())
    return None


def _nodes(raw: bytes, elements: list[tuple[_Element, int | None, int]]) -> tuple[RankingNode, ...]:
    """The checked nodes, in the definition's order, each with its canonical path."""
    names = Counter((parent, element.attributes.get("Name")) for element, parent, _ in elements)
    nodes: list[RankingNode] = []
    for index, (element, parent, position) in enumerate(elements):
        name = element.attributes.get("Name") or None
        unique = name is not None and names[(parent, name)] == 1
        segment = _escaped(name) if unique and name is not None else f"#{position}"
        weight, written, span = _weight(raw, element)
        nodes.append(
            RankingNode(
                index=index,
                parent=parent,
                position=position,
                kind=cast("NodeKind", element.name),
                name=name,
                weight=weight,
                weight_text=written,
                path=segment if parent is None else f"{nodes[parent].path}/{segment}",
                line=element.line,
                span=(element.start, element.end),
                weight_span=span,
            )
        )
    return tuple(nodes)


def _escaped(name: str) -> str:
    """A name as a path's segment writes it: `\\` as `\\\\`, `/` as `\\/`, and a leading `#` as
    `\\#`."""
    segment = name.replace("\\", "\\\\").replace("/", "\\/")
    return "\\" + segment if segment.startswith("#") else segment


def parse_node_path(path: str) -> tuple[str | int, ...]:
    """The segments of a node path (docs/contracts.md, node paths): each a node's name, with its
    escapes read, or a position, counted from 1. Raises `NodePathProblem` for the first segment
    written wrongly: an empty one, a `\\` that starts no escape, or one that starts with `#` and
    isn't a valid position."""
    pieces: list[str] = []
    piece = ""
    index = 0
    while index < len(path):
        char = path[index]
        if char == "\\":
            piece += path[index : index + 2]
            index += 2
        elif char == "/":
            pieces.append(piece)
            piece = ""
            index += 1
        else:
            piece += char
            index += 1
    pieces.append(piece)
    return tuple(_segment(number, piece) for number, piece in enumerate(pieces, start=1))


def _segment(number: int, written: str) -> str | int:
    if not written:
        raise NodePathProblem(
            number,
            "is empty. A path's segments are separated by single slashes, with none at its "
            "start or end",
        )
    if written.startswith("#"):
        if not _POSITION.fullmatch(written[1:]):
            raise NodePathProblem(
                number,
                "starts with # but isn't a position: # and a whole number without a leading "
                "zero, such as #2. A name that starts with # is written \\#",
            )
        position = int(written[1:])
        if position == 0:
            raise NodePathProblem(number, "is position 0. Positions count from 1")
        return position
    name = ""
    index = 0
    while index < len(written):
        char = written[index]
        if char != "\\":
            name += char
            index += 1
            continue
        escaped = written[index + 1 : index + 2]
        if escaped in ("/", "\\") or (escaped == "#" and index == 0):
            name += escaped
            index += 2
            continue
        raise NodePathProblem(
            number,
            "holds a \\ that starts no escape. In a node path, \\/ stands for /, \\\\ for \\, "
            "and \\# at a segment's start for #. Inside double quotes, YAML reads its own "
            "escapes first, so each \\ of a path is written \\\\ there",
        )
    return name


@dataclass(frozen=True)
class WeightEntry:
    """An entry of a ranking variant's `set`: the node it names, and the weight it gives it."""

    place: str
    """Where the configuration writes it, such as `variants.ranking[0].set[1]`, counted from 0
    in the file's order."""
    node: RankingNode
    """The node its path names, in the baseline's definition."""
    weight: Decimal
    """Normalized, as a configuration's decimal is."""


@dataclass(frozen=True)
class RankingCase:
    """A ranking variant's case: the baseline's definition with the variant's change."""

    place: str
    """Where the configuration writes the variant, such as `variants.ranking[0]`."""
    set: tuple[WeightEntry, ...]
    """Each entry of its `set`, in the baseline definition's order of their nodes."""
    remove: RankingNode | None
    """The factor it removes, in the baseline's definition, or None."""
    definition: RankingDefinition
    """The case's definition, read by the same rules as the baseline's."""


def apply_ranking_variant(
    baseline: RankingDefinition, variant: RankingVariant, place: str
) -> RankingCase:
    """The case `variant`, written at `place`, such as `variants.ranking[0]`, gives from the
    baseline's definition, by the rules of ranking variants: a weight variant sets the weight of
    every node of one parent, and a removal variant removes a factor and sets the weights of the
    nodes left beside it, each keeping their sum in the baseline. The case's text is the
    baseline's, with the removed element taken out with its line, and each weight that differs
    rewritten in its normalized form, and nothing else changed.

    Raises `VariantProblem` for the first rule the variant breaks, in this order: the factor it
    removes, each of its `set`'s paths, one parent, each node once, every node of the parent,
    the sum, and that it changes something."""
    removed = None
    if variant.remove is not None:
        removed = _named(baseline, variant.remove, f"{place}.remove")
        if removed.kind == "Composite":
            raise VariantProblem(
                f"{place}.remove",
                "names a composite. A variant removes one factor, a StockFormula or a "
                "StockFactor, never a composite with the factors it holds",
            )
        if len(baseline.children(_parent(baseline, removed))) == 1:
            raise VariantProblem(
                f"{place}.remove",
                "names its parent's only node, so the removal would leave the parent without "
                "one. A removal leaves at least one node beside the factor it removes",
            )
    entries = [
        WeightEntry(
            f"{place}.set[{number}]", _named(baseline, path, f"{place}.set[{number}]"), weight
        )
        for number, (path, weight) in enumerate(variant.set.items())
    ]
    parent = entries[0].node.parent if removed is None else removed.parent
    _check_parent(entries, removed, parent)
    _check_each_once(entries)
    kept = [
        node
        for node in baseline.children(None if parent is None else baseline.nodes[parent])
        if removed is None or node.index != removed.index
    ]
    _check_every_node(entries, kept, place, removed)
    _check_sum(entries, kept, place, removed)
    changed = [entry for entry in entries if entry.weight != entry.node.weight]
    if removed is None and not changed:
        raise VariantProblem(
            f"{place}.set",
            "gives every node the weight it has in the baseline's definition, so the variant "
            "changes nothing. A ranking variant changes at least one weight, or removes a factor",
        )
    text = _changed_text(baseline, removed, changed)
    # The case's text keeps every rule of a definition, by these rules, and reading it gives its
    # nodes, with their canonical paths, which a removal can change.
    definition = read_definition(text.encode("utf-8"))
    ordered = tuple(sorted(entries, key=lambda entry: entry.node.index))
    return RankingCase(place, ordered, removed, definition)


def check_node_paths(variant: RankingVariant, place: str) -> None:
    """Checks only how the variant's paths are written, for a baseline whose definition isn't
    read here: a ranking snapshot's, until release 0.4.0's R04-T10 reads it. Raises
    `VariantProblem` for the first path written wrongly."""
    paths = [(f"{place}.remove", variant.remove)] if variant.remove is not None else []
    paths += [(f"{place}.set[{number}]", path) for number, path in enumerate(variant.set)]
    for where, path in paths:
        try:
            parse_node_path(path)
        except NodePathProblem as problem:
            raise _path_problem(where, problem) from None


def _named(baseline: RankingDefinition, path: str, where: str) -> RankingNode:
    try:
        return baseline.node(path)
    except NodePathProblem as problem:
        raise _path_problem(where, problem) from None


def _path_problem(where: str, problem: NodePathProblem) -> VariantProblem:
    return VariantProblem(
        where, f"is a node path whose segment {problem.segment} {problem.problem}"
    )


def _parent(baseline: RankingDefinition, node: RankingNode) -> RankingNode | None:
    return None if node.parent is None else baseline.nodes[node.parent]


def _check_parent(
    entries: list[WeightEntry], removed: RankingNode | None, parent: int | None
) -> None:
    for entry in entries:
        if removed is not None and entry.node.index == removed.index:
            raise VariantProblem(
                entry.place,
                "names the factor the variant removes. A removal's set gives the weights of the "
                "nodes left beside it",
            )
        if entry.node.parent == parent:
            continue
        if removed is not None:
            raise VariantProblem(
                entry.place,
                "names a node of another parent than the factor the variant removes. A "
                "removal's set gives the weights of the nodes left beside it",
            )
        raise VariantProblem(
            entry.place,
            f"names a node of another parent than `{entries[0].place}` does. A variant sets the "
            "weights of one parent's nodes: every top-level node, or every node of one composite",
        )


def _check_each_once(entries: list[WeightEntry]) -> None:
    first: dict[int, WeightEntry] = {}
    for entry in entries:
        earlier = first.setdefault(entry.node.index, entry)
        if earlier is not entry:
            raise VariantProblem(
                entry.place,
                f"names the same node as `{earlier.place}`. A set gives each node's weight once",
            )


def _check_every_node(
    entries: list[WeightEntry], kept: list[RankingNode], place: str, removed: RankingNode | None
) -> None:
    named = {entry.node.index for entry in entries}
    missing = [str(node.position) for node in kept if node.index not in named]
    if not missing:
        return
    which = f"position {missing[0]}" if len(missing) == 1 else f"positions {series(missing)}"
    every = (
        "every node of the parent it changes"
        if removed is None
        else "every node its parent keeps beside the factor it removes"
    )
    raise VariantProblem(
        f"{place}.set",
        f"leaves out its parent's node at {which}. A variant gives the weight of {every}, each "
        "once, so none is left for Portfolio123 to rescale",
    )


def _check_sum(
    entries: list[WeightEntry], kept: list[RankingNode], place: str, removed: RankingNode | None
) -> None:
    baseline = sum((node.weight for node in kept), Decimal(0))
    if removed is not None:
        baseline += removed.weight
    if sum((entry.weight for entry in entries), Decimal(0)) == baseline:
        return
    if removed is None:
        raise VariantProblem(
            f"{place}.set",
            "gives weights that don't sum to what the same nodes' weights sum to in the "
            "baseline's definition. A variant moves weight between siblings and keeps their sum, "
            "so no result depends on how Portfolio123 treats another total",
        )
    raise VariantProblem(
        f"{place}.set",
        "gives weights that don't sum to what its parent's nodes, the factor it removes "
        "included, sum to in the baseline's definition. The removed factor's weight goes to the "
        "nodes left beside it",
    )


def _changed_text(
    baseline: RankingDefinition, removed: RankingNode | None, changed: list[WeightEntry]
) -> str:
    """The baseline's text, with the removed element taken out, and each changed weight's text
    between its quotes replaced by its normalized form."""
    raw = baseline.text.encode("utf-8")
    edits = [
        (*entry.node.weight_span, format(entry.weight, "f").encode("ascii")) for entry in changed
    ]
    if removed is not None:
        start, end = removed.span
        line_start = raw.rfind(b"\n", 0, start) + 1
        if line_start > 0 and not raw[line_start:start].strip(b" \t"):
            # Only spaces and tabs come before it on its line: they go too, with the line break
            # before them, so no blank line is left.
            start = line_start - 1
        edits.append((start, end, b""))
    for start, end, replacement in sorted(edits, reverse=True):
        raw = raw[:start] + replacement + raw[end:]
    return raw.decode("utf-8")
