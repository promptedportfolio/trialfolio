"""R04-T01's provider-route checks: the `rank_get` and `rank_update` calls, through `p123api`, and
the offline weight changes between them (release 0.4.0, R04-T01).

The live calls read the credentials from `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`,
injected for the one command, as AGENTS.md describes. They configure `p123api`'s client as Trial
Folio's provider client does (ADR 0006): one attempt, no environment settings, authentication in a
call of its own, and Trial Folio's `ExchangeRecordingAdapter`, which allows one HTTP exchange in
each call, so a re-authentication after a 401 or 403, or a redirect, is refused before it's sent.
Every definition, each response's body as Portfolio123 sent it, and each call's exchanges are
saved in `payloads/`, which is git-ignored. Files are read and written with their line endings
unchanged.
What the script prints is only what the run record may hold: counts, positions, verdicts, the
exchanges' methods, paths, and statuses, and the credits Portfolio123 reports. It never prints a
node's name, formula, or weight, an amount moved, the XML, a ranking system's ID, the account's
remaining quota, or Portfolio123's message on a failure, which it saves with the credentials and
the token redacted.

The script changed after R04-T01's checks, in their pull request's review: the run record says
how.

    route.py get NAME LABEL [--compare XML --method M --currency C]   1 credit
    route.py update XML LABEL --method M --currency C                 1 credit
    route.py variant KIND SOURCE LABEL                                offline: top, nested, remove
    route.py review REVIEW_DIR                                        offline
"""

import argparse
import csv
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, cast

if TYPE_CHECKING:
    from trialfolio.provider import ExchangeRecordingAdapter

PAYLOADS = Path(__file__).resolve().parent / "payloads"
FORMULA_NODES = ("StockFormula", "IndFormula", "SecFormula", "StockFactor")
"""The factor nodes a removal may remove. `StockFactor` isn't in the ranking-definition article's
list of node types; R04-T01 found it in a saved system."""
WEIGHT = re.compile(r'(\bWeight\s*=\s*")([^"]*)(")')
MOVED = Decimal(10)


# The definition


@dataclass
class Node:
    element: ET.Element
    index: int
    """The node's place among the definition's weighted elements, in document order, from 0."""
    depth: int
    """1 for a top-level node."""


def nodes_of(xml: str) -> tuple[ET.Element, list[Node], dict[int, list[Node]]]:
    """The root, every node (an element with a `Weight`), and each element's child nodes, by the
    element's `id()`. Fails when the text's `Weight` attributes don't match the parsed nodes one to
    one, since the edits below rewrite them by position."""
    root = ET.fromstring(xml)
    found: list[Node] = []
    children: dict[int, list[Node]] = {}

    def walk(element: ET.Element, depth: int) -> None:
        for child in element:
            if "Weight" in child.attrib:
                node = Node(child, len(found), depth)
                found.append(node)
                children.setdefault(id(element), []).append(node)
                walk(child, depth + 1)
            else:
                walk(child, depth)

    walk(root, 1)
    if len(WEIGHT.findall(xml)) != len(found):
        sys.exit("The XML's Weight attributes don't match its nodes one to one; stopping.")
    return root, found, children


def weight(node: Node) -> Decimal:
    return Decimal(node.element.attrib["Weight"].strip().rstrip("%").strip())


def describe(xml: str) -> None:
    root, found, children = nodes_of(xml)
    kinds: dict[str, int] = {}
    for node in found:
        kinds[node.element.tag] = kinds.get(node.element.tag, 0) + 1
    top = children.get(id(root), [])
    composites = [n for n in found if n.element.tag == "Composite"]
    sums = []
    for parent in [root, *(n.element for n in composites)]:
        kids = children.get(id(parent), [])
        if kids:
            total = sum((weight(k) for k in kids), Decimal(0))
            sums.append(total == 100)
    zero = sum(1 for n in found if weight(n) == 0)
    suffix = {n.element.attrib["Weight"].strip()[-1:] == "%" for n in found}
    print(f"  XML parses: yes. Nodes: {len(found)}, by type: {dict(sorted(kinds.items()))}.")
    print(
        f"  Top-level nodes: {len(top)}. Composites: {len(composites)}, of which with 2 or more child nodes: "
        f"{sum(1 for c in composites if len(children.get(id(c.element), [])) >= 2)}, "
        f"and 3 or more: {sum(1 for c in composites if len(children.get(id(c.element), [])) >= 3)}. "
        f"Deepest node: depth {max((n.depth for n in found), default=0)}."
    )
    print(
        f"  Sets of sibling weights summing to 100: {sum(sums)} of {len(sums)}. Nodes with weight 0: {zero}. "
        f"Weights written with a percent sign: {sorted(suffix)}."
    )


def formatted(value: Decimal, like: str) -> str:
    text = format(value.normalize(), "f") if value != value.to_integral() else str(int(value))
    return text + ("%" if like.strip().endswith("%") else "")


def rewrite(xml: str, changes: dict[int, Decimal]) -> str:
    """`xml` with the `Weight` of each node index in `changes` replaced, and nothing else."""
    position = -1
    originals = {}

    def replace(match: re.Match[str]) -> str:
        nonlocal position
        position += 1
        if position in changes:
            originals[position] = match.group(2)
            return match.group(1) + formatted(changes[position], match.group(2)) + match.group(3)
        return match.group(0)

    return WEIGHT.sub(replace, xml)


def without(xml: str, node_index: int) -> str:
    """`xml` without the element of node `node_index`, a formula node, and its line's indentation."""
    matches = list(WEIGHT.finditer(xml))
    start = xml.rfind("<", 0, matches[node_index].start())
    opening = re.match(r"<([A-Za-z]+)", xml[start:])
    if opening is None:
        sys.exit("The node to remove has no opening tag where expected; stopping.")
    tag = opening.group(1)
    if tag not in FORMULA_NODES:
        sys.exit("The node to remove isn't a formula node; stopping.")
    opening_end = xml.find(">", start)
    if xml[opening_end - 1] == "/":
        end = opening_end + 1
    else:
        close = xml.find(f"</{tag}>", opening_end)
        nested = xml.find(f"<{tag}", opening_end)
        if close < 0 or (0 <= nested < close):
            sys.exit("The node to remove has an unexpected structure; stopping.")
        end = close + len(f"</{tag}>")
    line_start = xml.rfind("\n", 0, start)
    if line_start >= 0 and xml[line_start + 1 : start].strip() == "":
        # The line ending before it goes too, a carriage return included.
        start = line_start - 1 if xml[line_start - 1 : line_start] == "\r" else line_start
    return xml[:start] + xml[end:]


def scaled(weights: list[Decimal], whole: bool) -> list[Decimal]:
    """`weights` in their proportions, scaled to sum to 100: in whole points, by the largest
    remainder, when `whole`, and otherwise to 2 decimal places, the same way."""
    total = sum(weights, Decimal(0))
    unit = Decimal(1) if whole else Decimal("0.01")
    exact = [w * 100 / total for w in weights]
    floored = [(e / unit).to_integral_value(rounding=ROUND_FLOOR) * unit for e in exact]
    left = int((Decimal(100) - sum(floored, Decimal(0))) / unit)
    order = sorted(range(len(weights)), key=lambda i: exact[i] - floored[i], reverse=True)
    for i in order[:left]:
        floored[i] += unit
    return floored


def read(path: Path) -> str:
    """`path`'s text, with its line endings as they are: `read_text` would make a `\\r\\n` or a
    `\\r` a `\\n`, and the XML sent would no longer be the file's."""
    return path.read_bytes().decode("utf-8")


def write(path: Path, text: str) -> None:
    """`text` in `path`, with its line endings as they are."""
    path.write_text(text, encoding="utf-8", newline="")


def variant(kind: str, source: Path, label: str) -> None:
    xml = read(source)
    root, found, children = nodes_of(xml)

    def usable(parent: ET.Element, at_least: int) -> list[Node] | None:
        kids = children.get(id(parent), [])
        if len(kids) >= at_least and all(weight(k) > 0 for k in kids):
            return kids
        return None

    if kind in ("top", "nested"):
        if kind == "top":
            kids, where = usable(root, 2), "the top level"
        else:
            kids, where = None, ""
            for node in found:
                if node.element.tag == "Composite" and (k := usable(node.element, 2)):
                    kids, where = k, f"composite node {node.index + 1} (depth {node.depth})"
                    break
        if kids is None:
            sys.exit(
                f"No set of sibling nodes for a {kind} weight change, with explicit weights; stopping."
            )
        donor = max(kids, key=weight)
        recipient = next(k for k in kids if k is not donor)
        amount = min(MOVED, weight(donor) / 2)
        sent = {donor.index: weight(donor) - amount, recipient.index: weight(recipient) + amount}
        out = rewrite(xml, sent)
        # Not the amount: when it's half the largest weight, it gives that weight away.
        whole = all(w == w.to_integral() for w in sent.values())
        print(
            f"  At {where}, with {len(kids)} child nodes: moved weight from child "
            f"{kids.index(donor) + 1} (the largest weight) to child {kids.index(recipient) + 1}; their sum is unchanged. "
            f"The two new weights are {'whole numbers' if whole else 'written with a decimal'}."
        )
    else:
        kids, holder = None, None
        for at_least in (3, 2):
            for node in found:
                k = usable(node.element, at_least) if node.element.tag == "Composite" else None
                if k and any(c.element.tag in FORMULA_NODES for c in k):
                    kids, holder = k, node
                    break
            if kids:
                break
        if kids is None or holder is None:
            sys.exit("No composite with a formula node to remove, and explicit weights; stopping.")
        removed = [c for c in kids if c.element.tag in FORMULA_NODES][-1]
        left = [c for c in kids if c is not removed]
        whole = all(weight(c) == weight(c).to_integral() for c in kids)
        new = scaled([weight(c) for c in left], whole)
        out = rewrite(xml, {c.index: w for c, w in zip(left, new)})
        out = without(out, removed.index)
        print(
            f"  In composite node {holder.index + 1} (depth {holder.depth}), with {len(kids)} child nodes: removed "
            f"child {kids.index(removed) + 1}, a formula node. The {len(left)} left were scaled to sum to 100 in their "
            f"proportions, in {'whole points' if whole else 'hundredths'}, by the largest remainder."
        )
    _, check_found, _ = nodes_of(out)
    target = PAYLOADS / f"{label}.xml"
    write(target, out)
    print(
        f"  Saved {target.relative_to(PAYLOADS.parent)}: it parses, with {len(check_found)} nodes "
        f"(the source has {len(found)})."
    )
    describe(out)


# The calls


def sent_once(label: str, send: Callable[[Any], object]) -> dict[str, object]:
    """Authenticates, then makes the one call `send` makes, each in a call of its own, with the
    client configured as the module says. Saves the response's body as Portfolio123 sent it, in
    `{label}.json`, cost and quota included, and the exchanges in `{label}.exchanges.json`, and
    returns the body, decoded."""
    import p123api

    from trialfolio.provider import ExchangeRecordingAdapter

    secrets = (os.environ["TRIALFOLIO_P123_API_ID"], os.environ["TRIALFOLIO_P123_API_KEY"])
    made = p123api.Client(api_id=secrets[0], api_key=secrets[1])
    made.set_max_request_retries(1)
    # The private attribute ADR 0006 relies on (`Client._session` in 3.1.0).
    session = made._session
    session.trust_env = False
    adapter = ExchangeRecordingAdapter()
    session.adapters.clear()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    with made:
        try:
            with adapter.call("authentication"):
                made.auth()
            with adapter.call("request") as call:
                send(made)
        except Exception as error:  # noqa: BLE001
            failed(error, exchanges(adapter), (*secrets, made.get_token()))
    (PAYLOADS / f"{label}.exchanges.json").write_text(
        json.dumps([e.model_dump(mode="json") for e in adapter.exchanges], indent=2),
        encoding="utf-8",
    )
    if call.body is None:
        sys.exit("The call returned without a 200's body to save; stopping.")
    (PAYLOADS / f"{label}.json").write_bytes(call.body)
    print(f"  Exchanges: {exchanges(adapter)}.")
    decoded = json.loads(call.body)
    if not isinstance(decoded, dict):
        sys.exit(f"The response isn't a JSON object; it's saved in payloads/{label}.json.")
    return cast(dict[str, object], decoded)


def exchanges(adapter: "ExchangeRecordingAdapter") -> list[str]:
    """Each exchange's method, path, and status, or how it ended without one."""
    return [
        f"{e.request} {e.status if e.status is not None else e.result}" for e in adapter.exchanges
    ]


def failed(error: Exception, made: list[str], secrets: tuple[str | None, ...]) -> NoReturn:
    """Prints a failed call's exchanges and the exception's type, never its message, which can
    hold Portfolio123's text: part of the definition sent, or the account's details. Saves the
    message, with the credentials and the token redacted, longest first and in one pass, so
    replacing one can't leave part of another."""
    present = sorted({s for s in secrets if s}, key=len, reverse=True)
    message = str(error)
    if present:
        message = re.sub("|".join(re.escape(s) for s in present), "[redacted]", message)
    write(PAYLOADS / "last-error.txt", message)
    print(
        f"  Failed: {type(error).__name__}, after the exchanges {made}. Its message, with the "
        "credentials and the token redacted, is in payloads/last-error.txt."
    )
    sys.exit(1)


def get(
    name: str, label: str, compare: Path | None, method: int | None, currency: str | None
) -> None:
    record = sent_once(label, lambda made: made.rank_get(name=name))
    xml = str(record.get("xml") or "")
    write(PAYLOADS / f"{label}.xml", xml)
    print(
        f"  rank_get succeeded. Fields: {sorted(record)}. ID present: {record.get('id') is not None}. "
        f"Ranking method: {record.get('rankingMethod')}. Currency: {record.get('currency')}. Type: {record.get('type')}. "
        f"Name as Portfolio123 gives it equals the one asked for: {record.get('name') == name}. "
        f"Credits reported: {record.get('cost')}."
    )
    describe(xml)
    if compare is not None:
        sent = read(compare)
        same_bytes = sent == xml
        same_tree = ET.canonicalize(sent, strip_text=True) == ET.canonicalize(xml, strip_text=True)
        print(
            f"  Holds the XML sent: byte for byte: {same_bytes}; as parsed, ignoring whitespace: {same_tree}. "
            f"Ranking method sent: {method}, held: {record.get('rankingMethod')}, equal: {method == record.get('rankingMethod')}. "
            f"Currency sent: {currency}, held: {record.get('currency')}, equal: {currency == record.get('currency')}."
        )


def update(source: Path, label: str, method: int, currency: str) -> None:
    sent = read(source)
    params = {"type": "stock", "nodes": sent, "rankingMethod": method, "currency": currency}
    response = sent_once(label, lambda made: made.rank_update(params))
    print(
        f"  rank_update succeeded with {source.name}, ranking method {method}, currency {currency}. "
        f"Response: {sorted(response)}. Credits reported: {response.get('cost')}."
    )


# Comparing runs


def review(directory: Path) -> None:
    rows = list(
        csv.DictReader((directory / "normalized" / "differences.csv").open(encoding="utf-8"))
    )
    settings = [r for r in rows if r["kind"] == "setting" and r["classification"] != "same"]
    metrics = [r for r in rows if r["kind"] == "metric"]
    counts: dict[str, int] = {}
    for r in metrics:
        counts[r["classification"]] = counts.get(r["classification"], 0) + 1
    print(f"  Settings that differ: {[r['name'] for r in settings]}.")
    print(f"  Metric rows: {len(metrics)}, by classification: {dict(sorted(counts.items()))}.")
    equal, changed, unknown = [], [], []
    for r in metrics:
        name = f"{r['subject']}.{r['name']}"
        try:
            same = Decimal(r["value"]) == Decimal(r["baseline_value"])
        except ArithmeticError:
            same = r["value"] == r["baseline_value"]
            if not r["value"] or not r["baseline_value"]:
                unknown.append(name)
                continue
        (equal if same else changed).append(name)
    print(
        f"  Metrics equal to the baseline's: {len(equal)}. Changed: {len(changed)}: {changed}. "
        f"Without a value to compare: {unknown}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    g = sub.add_parser("get")
    g.add_argument("name")
    g.add_argument("label")
    g.add_argument("--compare", type=Path)
    g.add_argument("--method", type=int)
    g.add_argument("--currency")
    u = sub.add_parser("update")
    u.add_argument("source", type=Path)
    u.add_argument("label")
    u.add_argument("--method", type=int, required=True)
    u.add_argument("--currency", required=True)
    v = sub.add_parser("variant")
    v.add_argument("kind", choices=("top", "nested", "remove"))
    v.add_argument("source", type=Path)
    v.add_argument("label")
    r = sub.add_parser("review")
    r.add_argument("directory", type=Path)
    args = parser.parse_args()
    PAYLOADS.mkdir(exist_ok=True)
    if args.command == "get":
        get(args.name, args.label, args.compare, args.method, args.currency)
    elif args.command == "update":
        update(args.source, args.label, args.method, args.currency)
    elif args.command == "variant":
        variant(args.kind, args.source, args.label)
    else:
        review(args.directory)


if __name__ == "__main__":
    main()
