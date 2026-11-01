"""The ranking definitions R04-T01 saved read by the rules of ranking definitions, and each pair of
them that one ranking variant joins is joined by the variant the rules give, byte for byte.

Traces to release 0.4.0's verification commands, `TRIALFOLIO_REFERENCE_DIR=reference uv run
pytest -m reference`, and its test pairing's other checks, `tests/reference/
test_reference_ranking.py`. R04-T01 saved the definitions in the git-ignored
`ranking-weights/payloads/` (REQ-11): the owner's saved systems', and the variants its steps 4, 6,
and 7 sent. Each of the eight reads as a definition, by docs/contracts.md's ranking definitions.
For each two, the second of which differs from the first only in the weights of one parent's
nodes, or by one factor's element and the weights of the nodes beside it, the ranking variant
that sets the second's weights, and removes that factor, is accepted, and applied to the first,
gives the second byte for byte. At least three such pairs are found, of the three kinds R04-T01's
steps made: a weight moved between top-level nodes, one moved between a composite's factors, and
a factor removed. The files are named by the owner's labels, so the pairs are found by comparing
the definitions, without the variant: their nodes, by kind, name, and depth, and their text, which
must be the same but for the weights of the parent's nodes and, for a removal, the factor's
element with its line. So every pair found must give its second, and a variant that gives
anything else fails the test, as one that's refused does.

The definitions are the owner's strategy definitions, so no assertion here shows a definition, a
name, a weight, or a file's name: each gives only counts and verdicts, as R04-T02's check did.
Without the variable, or without the definitions, the test skips and says why. It reads only,
and writes nothing.
"""

from collections import Counter
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

import pytest

from trialfolio.contracts.experiment_configuration import RankingVariant
from trialfolio.ranking_definitions import (
    RankingDefinition,
    RankingNode,
    VariantProblem,
    apply_ranking_variant,
    read_definition,
)

pytestmark = pytest.mark.reference

PAYLOADS = Path("ranking-weights") / "payloads"
"""Where R04-T01's definitions are, under the reference directory."""

SAVED = 8
"""How many definitions R04-T01 saved: its run record's eight."""

KINDS = ("top-level weights", "a composite's weights", "a factor removed")
"""The kinds of pair, as R04-T01's steps 4, 6, and 7 made them."""

PLACE = "variants.ranking[0]"


def definitions(reference_dir: Path) -> list[bytes]:
    """The bytes of each `.xml` file R04-T01 saved, in no order the owner's labels give."""
    payloads = reference_dir / PAYLOADS
    files = sorted(payloads.glob("*.xml")) if payloads.is_dir() else []
    if not files:
        pytest.skip(f"no saved ranking definitions under {PAYLOADS}")
    return sorted(path.read_bytes() for path in files)


def _depth(definition: RankingDefinition, node: RankingNode) -> int:
    depth = 0
    while node.parent is not None:
        node = definition.nodes[node.parent]
        depth += 1
    return depth


def _shape(definition: RankingDefinition, nodes: list[RankingNode]) -> list[tuple[object, ...]]:
    """Each node's kind, name, and depth, in order: what a weight change leaves as it was."""
    return [(node.kind, node.name, _depth(definition, node)) for node in nodes]


def _lines(definition: RankingDefinition, unweighted: Iterable[RankingNode]) -> list[str]:
    """The definition's lines, with the weight of each node of `unweighted` left out, between its
    quotes: what a variant that sets their weights leaves as it was."""
    text = definition.text.encode("utf-8")
    for node in sorted(unweighted, key=lambda node: node.weight_span, reverse=True):
        start, end = node.weight_span
        text = text[:start] + text[end:]
    return text.decode("utf-8").split("\n")


def _element_lines(definition: RankingDefinition, node: RankingNode) -> range | None:
    """The lines, from 0, that the node's element fills alone, after spaces and tabs only: those
    its removal takes out with it. None when anything else is on them."""
    text = definition.text.encode("utf-8")
    start, end = node.span
    line_start = text.rfind(b"\n", 0, start) + 1
    line_end = text.find(b"\n", end)
    after = text[end:] if line_end == -1 else text[end:line_end]
    if line_start == 0 or text[line_start:start].strip(b" \t") or after:
        return None
    first = text.count(b"\n", 0, start)
    return range(first, first + text.count(b"\n", start, end) + 1)


class Between(NamedTuple):
    """Two definitions of the same shape, and the ranking variant that would join them."""

    kind: str
    """Which of `KINDS` the pair is."""
    variant: RankingVariant
    only: bool
    """Whether the second's text is the first's but for what the variant changes: the weights of
    its parent's nodes, and the factor it removes, with its line. A pair is one variant joins
    exactly when it is."""


def variant_between(first: RankingDefinition, second: RankingDefinition) -> Between | None:
    """The kind of pair, the ranking variant that would give `second` from `first`, whose `set`
    gives every node of one parent its weight in `second`, and whose `remove` the factor `second`
    lacks, and whether the two differ only there. None when no variant can give `second`'s
    nodes from `first`'s, by their kind, name, depth, and weight."""
    if len(second.nodes) == len(first.nodes):
        return _weights_changed(first, second)
    if len(second.nodes) == len(first.nodes) - 1:
        return _factor_removed(first, second)
    return None


def _weights_changed(first: RankingDefinition, second: RankingDefinition) -> Between | None:
    """For two definitions of as many nodes: the variant that sets the weights of the one parent
    whose nodes' weights differ, when the two have the same shape."""
    if _shape(first, list(first.nodes)) != _shape(second, list(second.nodes)):
        return None
    changed = [
        node for node, other in zip(first.nodes, second.nodes, strict=True)
        if node.weight != other.weight
    ]  # fmt: skip
    parents = {node.parent for node in changed}
    if len(parents) != 1:
        return None
    (parent,) = parents
    siblings = first.children(None if parent is None else first.nodes[parent])
    weights = {node.path: second.nodes[node.index].weight for node in siblings}
    kind = KINDS[0] if parent is None else KINDS[1]
    only = _lines(first, siblings) == _lines(
        second, [second.nodes[node.index] for node in siblings]
    )
    return Between(kind, _variant(weights, None), only)


def _factor_removed(first: RankingDefinition, second: RankingDefinition) -> Between | None:
    """For a second definition of one node fewer: the variant that removes the factor it lacks,
    and sets the weights of the nodes beside it, the first that gives the second's text whole, or
    else the first that gives its nodes."""
    # Two factors can have the same kind, name, and depth, so the text says which was removed.
    found: Between | None = None
    for removed in first.nodes:
        if removed.kind == "Composite":
            continue
        kept = [node for node in first.nodes if node.index != removed.index]
        if _shape(first, kept) != _shape(second, list(second.nodes)):
            continue
        parent = None if removed.parent is None else first.nodes[removed.parent]
        siblings = [node for node in first.children(parent) if node.index != removed.index]
        weights = {node.path: second.nodes[kept.index(node)].weight for node in siblings}
        others = [
            (node.weight, other.weight)
            for node, other in zip(kept, second.nodes, strict=True)
            if node not in siblings
        ]
        if not all(before == after for before, after in others):
            continue
        taken = _element_lines(first, removed)
        left = [
            line for number, line in enumerate(_lines(first, siblings))
            if taken is not None and number not in taken
        ]  # fmt: skip
        only = taken is not None and left == _lines(
            second, [second.nodes[kept.index(node)] for node in siblings]
        )
        between = Between(KINDS[2], _variant(weights, removed.path), only)
        if only:
            return between
        found = found or between
    return found


def _variant(weights: dict[str, Decimal], remove: str | None) -> RankingVariant:
    fields: dict[str, object] = {"key": "reference", "set": weights}
    if remove is not None:
        fields["remove"] = remove
    return RankingVariant.model_validate(fields)


def test_r04_t01s_definitions_read_and_each_pair_is_joined_by_its_variant(
    reference_dir: Path,
) -> None:
    contents = definitions(reference_dir)
    assert len(contents) == SAVED, f"{len(contents)} definitions found, where {SAVED} were saved"
    read = [read_definition(content) for content in contents]
    # Two steps sent a system's definition unchanged, so some files hold the same definition.
    distinct = [definition for number, definition in enumerate(read) if contents.index(
        definition.content
    ) == number]  # fmt: skip

    found: Counter[str] = Counter()
    joined = 0
    refused = 0
    # Pairs of the same nodes whose text differs in more than a variant changes, such as a
    # formula: not pairs a variant joins.
    other = 0
    mismatched = 0
    for first in distinct:
        for second in distinct:
            if first is second:
                continue
            between = variant_between(first, second)
            if between is None:
                continue
            if not between.only:
                other += 1
                continue
            try:
                case = apply_ranking_variant(first, between.variant, PLACE)
            except VariantProblem:
                refused += 1
                continue
            if case.definition.content == second.content:
                joined += 1
                found[between.kind] += 1
            else:
                mismatched += 1

    print(
        f"{len(read)} definitions read, {len(distinct)} distinct; pairs joined byte for byte: "
        + ", ".join(f"{found[kind]} of {kind}" for kind in KINDS)
        + f"; {refused} refused; {mismatched} not giving the second byte for byte; {other} of the"
        " same nodes that differ in more than a variant changes."
    )
    assert refused == 0, f"{refused} variants refused"
    assert mismatched == 0, f"{mismatched} variants didn't give the second byte for byte"
    assert joined >= 3, f"{joined} pairs joined, where R04-T01 made at least 3"
    missing = [kind for kind in KINDS if found[kind] == 0]
    assert not missing, f"no pair of: {', '.join(missing)}"
