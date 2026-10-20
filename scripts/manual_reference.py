"""Generates the user manual's reference tables from their sources, and checks them for drift
(docs/user-manual.md, rule 2, UM-T02, and UM-AC08).

A reference page holds generated regions, each between two comments on lines of their own:

    <!-- generated: <region-id> -->
    ...
    <!-- end generated: <region-id> -->

Everything outside them is hand-written. This script holds the registry of regions, and what
generates each:

- manual/reference/cli.md: the usage lines, commands, arguments, and options, from the CLI's
  parser, `parser` in src/trialfolio/cli/arguments.py, which `trialfolio.cli` gives as `_parser`;
- the three configuration pages: each object's keys, from the configuration's schema in schemas/;
- outputs.md: the columns of metrics.csv, settings.csv, and differences.csv, from their row
  schemas;
- output-fields.md: the fields of each JSON file Trial Folio writes, from its schema;
- json-summary.md: the summary's keys, from json-summary-1.2.0.schema.json;
- errors.md: the error codes, from docs/contracts.md's "Errors" table, which must agree with
  `EXIT_CODES` in src/trialfolio/errors.py, and the exit codes, from the exit-code table in its
  "CLI behavior".

Some tables end with one hand-written column, such as an error's remedy, or what a key is for.
Regenerating keeps each of its cells, matched by the row's key, the first column. A row whose key
is new gets an empty cell, which fails the check until someone writes it, and a row whose key has
left the source goes, with its cell.

    uv run python scripts/manual_reference.py            rewrites the regions in manual/
    uv run python scripts/manual_reference.py --check    writes nothing, and lists each problem

The check, which scripts/check runs, exits 1 when a region differs from what it generates, a page
names an unknown region, a registered region is on no page or on more than one, the markers are
unbalanced or nested, or a hand-written cell is empty. Both exit 1, and the rewrite writes
nothing, when a source holds something the generator can't put in plain words, or when
contracts.md's errors disagree with `EXIT_CODES`. The output depends on the sources only: never
on the terminal's width, the locale, the date, or the installed version.
"""

import argparse
import json
import os
import posixpath
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from trialfolio.cli import _parser
from trialfolio.errors import EXIT_CODES

ROOT: Final = Path(__file__).resolve().parents[1]
MANUAL: Final = ROOT / "manual"
SCHEMAS: Final = ROOT / "schemas"
CONTRACTS: Final = ROOT / "docs" / "contracts.md"
# Where a link from contracts.md leads once it's on the site: its file on GitHub.
GITHUB: Final = "https://github.com/promptedportfolio/trialfolio/blob/main/"

START: Final = re.compile(r"<!-- generated: ([a-z0-9][a-z0-9-]*) -->")
END: Final = re.compile(r"<!-- end generated: ([a-z0-9][a-z0-9-]*) -->")
# Anything else that looks like a marker is a mistake, such as a missing space.
MARKER: Final = re.compile(r"<!--\s*(?:end\s+)?generated\b", re.IGNORECASE)


class GenerationError(Exception):
    """A source holds something the generator can't put in plain words, or the sources disagree."""


@dataclass(frozen=True)
class Table:
    """A Markdown table. With `hand_written`, its last column is hand-written: the rows hold every
    cell but that one, which comes from the page, by the row's key, its first cell."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    hand_written: bool = False


type Block = str | Table


@dataclass(frozen=True)
class Region:
    """What one region generates: Markdown blocks, separated by blank lines. At most one table
    has a hand-written column, and only in a region that holds no other table."""

    blocks: tuple[Block, ...]

    def __post_init__(self) -> None:
        tables = [block for block in self.blocks if isinstance(block, Table)]
        if any(table.hand_written for table in tables) and len(tables) != 1:
            raise GenerationError("a region with a hand-written column holds one table only")


# The sources


@dataclass(frozen=True)
class Sources:
    """What the regions are generated from."""

    parser: argparse.ArgumentParser
    schemas: Path
    contracts: str
    exit_codes: Mapping[str, int]


# argparse's own help texts, for -h and --version, go through gettext, which would translate them
# where the environment names a language with argparse's messages installed. The manual is in
# English wherever it's generated.
@contextmanager
def _english_messages() -> Iterator[None]:
    saved = os.environ.get("LANGUAGE")
    os.environ["LANGUAGE"] = "C"
    try:
        yield
    finally:
        if saved is None:
            del os.environ["LANGUAGE"]
        else:
            os.environ["LANGUAGE"] = saved


def default_sources() -> Sources:
    """The repository's sources. The parser gets a version that isn't the installed one: only
    `--version`'s output holds it, and no page shows that."""
    with _english_messages():
        parser = _parser("0.0.0")
    exit_codes: dict[str, int] = {code: exit_code for code, exit_code in EXIT_CODES.items()}
    return Sources(
        parser=parser,
        schemas=SCHEMAS,
        contracts=CONTRACTS.read_text(encoding="utf-8"),
        exit_codes=exit_codes,
    )


def generate(sources: Sources) -> dict[str, Region]:
    """Every registered region, by its ID."""
    regions: dict[str, Region] = {}
    parts = [cli_regions(sources.parser), error_regions(sources.contracts, sources.exit_codes)]
    for page in SCHEMA_PAGES:
        schema = json.loads((sources.schemas / page.schema).read_text(encoding="utf-8"))
        parts.append(schema_regions(page, schema))
    for part in parts:
        for region_id, region in part.items():
            if region_id in regions:
                raise GenerationError(f"two regions have the ID {region_id}")
            regions[region_id] = region
    return regions


# Markdown


def _code(value: object) -> str:
    """A value as code: a string as it is, and anything else as JSON writes it."""
    text = value if isinstance(value, str) else json.dumps(value)
    if "`" in text:
        raise GenerationError(f"can't write {text!r} as code: it holds a backtick")
    return f"`{text}`"


def _plain(text: str) -> str:
    """Plain text, such as the parser's help, escaped for Markdown."""
    for character, escaped in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;")):
        text = text.replace(character, escaped)
    return re.sub(r"([\\`*_\[\]|])", r"\\\1", text)


def _markdown(text: str) -> str:
    """A source's own Markdown, such as a schema's description, on one line, for a table's cell."""
    return " ".join(text.split()).replace("|", "\\|")


def _number(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}" if isinstance(value, int) else repr(value)


def _count(value: int) -> str:
    return "one" if value == 1 else _number(value)


def _alternatives(items: Sequence[str], conjunction: str = "or") -> str:
    """`a`, `a or b`, or `a, b, or c`."""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    return f"{', '.join(items[:-1])}, {conjunction} {items[-1]}"


def _choices(parts: Sequence[str]) -> str:
    """Alternatives, separated by semicolons once one of them holds a comma, an `and`, or an
    `or`, so each reads as one."""
    if len(parts) > 1 and any(re.search(r",| and | or ", part) for part in parts):
        return f"{'; '.join(parts[:-1])}; or {parts[-1]}"
    return _alternatives(parts)


def _capitalized(text: str) -> str:
    return text[:1].upper() + text[1:]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _cells(line: str) -> list[str]:
    """A table row's cells, as Markdown splits them: at each `|` that isn't escaped."""
    body = line.strip().removeprefix("|")
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)]


def _row(cells: Sequence[str]) -> str:
    return "|" + "|".join(f" {cell} " if cell else " " for cell in cells) + "|"


def _table_text(table: Table, kept: Mapping[str, str]) -> str:
    lines = [_row(table.header), "|" + "---|" * len(table.header)]
    for row in table.rows:
        if len(row) + table.hand_written != len(table.header):
            raise GenerationError(f"a row of {len(row)} cells, under {len(table.header)} headers")
        lines.append(_row([*row, kept.get(row[0], "")] if table.hand_written else row))
    return "\n".join(lines)


def _kept_cells(existing: str) -> dict[str, str]:
    """The hand-written cells of the first table in a region's text as it is, by key."""
    kept: dict[str, str] = {}
    rows = [line for line in _first_table(existing.split("\n")) if line.strip()]
    for line in rows[2:]:
        cells = _cells(line)
        if len(cells) >= 2:
            kept.setdefault(cells[0], cells[-1])
    return kept


def _first_table(lines: Sequence[str]) -> list[str]:
    table: list[str] = []
    for line in lines:
        if line.lstrip().startswith("|"):
            table.append(line)
        elif table:
            break
    return table


def render(region: Region, existing: str = "") -> str:
    """The region's text between its markers, with the hand-written cells `existing` holds."""
    kept = _kept_cells(existing) if _hand_written_table(region) else {}
    blocks = [
        _table_text(block, kept) if isinstance(block, Table) else block for block in region.blocks
    ]
    return "\n" + "\n\n".join(blocks) + "\n"


def _hand_written_table(region: Region) -> Table | None:
    for block in region.blocks:
        if isinstance(block, Table) and block.hand_written:
            return block
    return None


def _empty_cells(region: Region, text: str) -> list[str]:
    """The keys of the rows whose hand-written cell is empty in the region's text."""
    table = _hand_written_table(region)
    if table is None:
        return []
    kept = _kept_cells(text)
    return [row[0] for row in table.rows if not kept.get(row[0])]


# The CLI's parser

# argparse wraps a usage line at the terminal's width. The pages show it as an 80-column terminal
# does: argparse leaves two columns spare. It's wrapped after `usage: `, as the terminal shows it,
# then the pages leave that out, and the columns it takes from each line.
USAGE_WIDTH: Final = 78
USAGE_PREFIX: Final = "usage: "
ARGUMENT_HEADER: Final = ("Argument or option", "Required", "Default", "What it is")

# argparse has no public way to list a parser's arguments and commands, so this reads its
# `_actions` and `_SubParsersAction`, as its own help formatter does.


def _commands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            choices: Mapping[str, argparse.ArgumentParser] = action.choices
            return dict(choices)
    raise GenerationError("the parser has no commands")


def _usage(parser: argparse.ArgumentParser) -> str:
    formatter = argparse.HelpFormatter(parser.prog, width=USAGE_WIDTH)
    # Python 3.14 colors help when the terminal or the environment allows it. A page never is.
    set_color = getattr(formatter, "_set_color", None)
    if set_color is not None:
        set_color(False)
    formatter.add_usage(
        parser.usage,
        parser._actions,
        parser._mutually_exclusive_groups,
        prefix=USAGE_PREFIX,
    )
    first, *rest = formatter.format_help().rstrip("\n").split("\n")
    margin = " " * len(USAGE_PREFIX)
    if not first.startswith(USAGE_PREFIX) or not all(line.startswith(margin) for line in rest):
        raise GenerationError(f"{parser.prog}'s usage line isn't wrapped after its prefix")
    usage = "\n".join(
        [first.removeprefix(USAGE_PREFIX), *(line.removeprefix(margin) for line in rest)]
    )
    if "\x1b" in usage or "```" in usage:
        raise GenerationError(f"{parser.prog}'s usage line can't go in a code block")
    return f"```text\n{usage}\n```"


def _help(action: argparse.Action) -> str:
    text = action.help or ""
    if "%" in text:
        raise GenerationError(f"{action.dest}'s help holds a format that argparse would expand")
    return _plain(_capitalized(text))


def _argument(action: argparse.Action) -> str:
    if not action.option_strings:
        return _code(action.metavar or action.dest)
    if action.nargs == 0:
        return ", ".join(_code(option) for option in action.option_strings)
    if action.nargs is not None or isinstance(action.metavar, tuple):
        raise GenerationError(f"{action.dest} takes values the table can't show")
    metavar = action.metavar or action.dest.upper()
    return ", ".join(_code(f"{option} {metavar}") for option in action.option_strings)


def _required(action: argparse.Action) -> str:
    if action.option_strings:
        return "Yes" if action.required else "No"
    return "No" if action.nargs in ("?", "*") else "Yes"


def _default(action: argparse.Action) -> str:
    default: object = action.default
    if action.nargs == 0 and action.const is True and default is False:
        return "Off"
    if default is None or default == argparse.SUPPRESS:
        return "None"
    return _code(default)


def _arguments(actions: Sequence[argparse.Action]) -> Table:
    return Table(
        ARGUMENT_HEADER,
        tuple(
            (_argument(action), _required(action), _default(action), _help(action))
            for action in actions
        ),
    )


def cli_regions(parser: argparse.ArgumentParser) -> dict[str, Region]:
    """cli.md's regions: the usage, the commands, the options every command takes, and each
    command's usage and its other arguments and options."""
    commands = _commands(parser)

    def options(command: argparse.ArgumentParser) -> list[argparse.Action]:
        return [
            action
            for action in command._actions
            if not isinstance(action, argparse._SubParsersAction)
        ]

    def key(action: argparse.Action) -> tuple[tuple[str, ...], str | None]:
        return (tuple(action.option_strings), action.help)

    shared = set.intersection(
        *(
            {key(action) for action in options(command) if action.option_strings}
            for command in commands.values()
        )
    )
    first = next(iter(commands.values()))
    common = [action for action in options(first) if key(action) in shared]
    regions = {
        "cli-usage": Region((_usage(parser), _arguments(options(parser)))),
        "cli-commands": Region(
            (
                Table(
                    ("Command", "What it does"),
                    tuple(
                        (f"[{_code(name)}](#trialfolio-{name})", _plain(command.description or ""))
                        for name, command in commands.items()
                    ),
                ),
            )
        ),
        "cli-common-options": Region((_arguments(common),)),
    }
    for name, command in commands.items():
        own = [action for action in options(command) if key(action) not in shared]
        blocks: tuple[Block, ...] = (
            (_usage(command), _arguments(own)) if own else (_usage(command),)
        )
        regions[f"cli-command-{name}"] = Region(blocks)
    return regions


# The schemas

# Each pattern the schemas use, in plain words. A "constraint" follows "text", and a "form" takes
# its place. A pattern that isn't here fails the generator.
NOT_ALL_WHITESPACE: Final = (
    "[^\\t\\n\\v\\f\\r \\u0085\\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]"
)
PATTERNS: Final[Mapping[str, tuple[str, str]]] = {
    NOT_ALL_WHITESPACE: ("constraint", "not all whitespace"),
    "^sha256:[0-9a-f]{64}$": ("form", "`sha256:` and 64 lowercase hexadecimal digits"),
    "^[^/\\\\:]+(/[^/\\\\:]+)*$": (
        "form",
        "a relative path: names separated by `/`, without `\\` or `:`",
    ),
    "^[a-z0-9][a-z0-9_-]{0,63}$": (
        "form",
        (
            "lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most"
            " 64 characters"
        ),
    ),
    "^[0-9][0-9A-Za-z.+!_-]*$": (
        "form",
        "a version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-`",
    ),
    "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$": (
        "form",
        "a version: three whole numbers, separated by `.`, such as `1.0.0`",
    ),
    "^case-[0-9a-f]{16}$": ("form", "`case-` and 16 lowercase hexadecimal digits"),
    "^[a-z][a-z0-9_]*$": ("form", "lowercase letters, digits, and `_`, starting with a letter"),
    "^[A-Z]+ /[^\\s]*$": (
        "form",
        "an HTTP method in capitals, a space, and a path that starts with `/`, without spaces",
    ),
    "^LicenseRef-[A-Za-z0-9.-]+$": ("form", "`LicenseRef-`, then letters, digits, `.`, and `-`"),
    "^[0-9]{4}-[0-9]{2}-[0-9]{2}$": ("form", "a date, `YYYY-MM-DD`"),
    "^(percent|ratio|count|days|date|currency:[A-Z]{3})$": (
        "form",
        "`percent`, `ratio`, `count`, `days`, `date`, or `currency:` and three capital letters",
    ),
    "^(pp|ratio|count|days|currency:[A-Z]{3})$": (
        "form",
        "`pp`, `ratio`, `count`, `days`, or `currency:` and three capital letters",
    ),
    "^https://[^\\s]+$": ("form", "an `https://` address, without spaces"),
}
FORMATS: Final[Mapping[str, str]] = {
    "date": "a date, `YYYY-MM-DD`",
    "date-time": "a date and time, with its time zone (RFC 3339)",
    "uuid4": "a version 4 UUID",
}
# The names Windows reserves, which a label, a key, and an experiment's ID can't be.
WINDOWS_RESERVED: Final = (
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{n}" for n in range(1, 10)),
    *(f"lpt{n}" for n in range(1, 10)),
)
# The keywords any value may use: a description and a default, which the pages give, and a title,
# the model's own name for it, which they leave out.
ANNOTATIONS: Final = frozenset({"default", "description", "title"})
_NUMBER: Final = frozenset({"type", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"})
# The keywords each kind of value may use, by the kind `_Walk.kind` gives it: those its words cover.
# Any other fails the generator, rather than being dropped. So a schema reaches a value inside it
# only where the words do: through `$ref`, `anyOf`, an object's `properties`, an array's `items`
# and `prefixItems`, a mapping's `patternProperties` and `propertyNames`, and a string's `not`.
# Beside `$ref` or `anyOf`, only the annotations: any other keyword there would narrow the value
# the reference or the alternatives give, unseen.
KEYWORDS: Final[Mapping[str, frozenset[str]]] = {
    kind: ANNOTATIONS | keywords
    for kind, keywords in {
        "object": frozenset({"type", "properties", "required", "additionalProperties"}),
        "reference": frozenset({"$ref"}),
        "alternatives": frozenset({"anyOf"}),
        "constant": frozenset({"type", "const"}),
        "enumeration": frozenset({"type", "enum"}),
        "string": frozenset({"type", "format", "pattern", "minLength", "maxLength", "not"}),
        "integer": _NUMBER,
        "number": _NUMBER,
        "boolean": frozenset({"type"}),
        "null": frozenset({"type"}),
        "array": frozenset({"type", "items", "prefixItems", "minItems", "maxItems"}),
        "mapping": frozenset(
            {"type", "properties", "patternProperties", "propertyNames", "additionalProperties"}
        ),
    }.items()
}
ROOT_KEYWORDS: Final = KEYWORDS["object"] | {"$schema", "$comment", "$defs"}
# The keywords a mapping's `propertyNames` may use: those that describe text.
NAME_KEYWORDS: Final = frozenset({"format", "maxLength", "minLength", "not", "pattern"})
NULL: Final = {"type": "null"}


@dataclass(frozen=True)
class SchemaPage:
    """How one schema becomes tables: one for its top level, and one for each object in it.

    `key` heads the first column. `required` adds the Required column. `description_column`
    gives each key's description a column of its own, rather than ending its Value. With
    `hand_written`, the tables end with that hand-written column, or only the top level's, with
    `top_only`. `split` gives each object a region of its own, its ID the top level's with the
    object's path; otherwise one region holds them all, after a link to the schema and the
    schema's own description. A nested object's table follows a heading at the level `heading`
    gives. `csv` describes a table's row, where null is an empty cell and a list's items are
    separated by semicolons.
    """

    prefix: str
    schema: str
    key: str = "Key"
    required: bool = True
    description_column: bool = True
    hand_written: str | None = None
    top_only: bool = False
    split: bool = True
    heading: str = "###"
    csv: bool = False


@dataclass
class _Object:
    """An object of the schema, which gets a table of its own."""

    title: str
    anchor: str
    schema: Mapping[str, Any]
    description: str
    top: bool = False


@dataclass
class _Walk:
    """Finds the objects of one schema, then describes their keys in plain words."""

    page: SchemaPage
    root: Mapping[str, Any]
    objects: list[_Object] = field(default_factory=list[_Object])
    by_ref: dict[str, _Object] = field(default_factory=dict[str, _Object])
    by_node: dict[int, _Object] = field(default_factory=dict[int, _Object])

    # Finding the objects

    def definition(self, ref: str) -> Mapping[str, Any]:
        prefix = "#/$defs/"
        definitions: Mapping[str, Any] = self.root.get("$defs", {})
        if not ref.startswith(prefix) or ref[len(prefix) :] not in definitions:
            raise GenerationError(f"{self.page.schema}: an unknown reference, {ref}")
        return definitions[ref[len(prefix) :]]

    def resolved(self, node: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.definition(node["$ref"]) if "$ref" in node else node

    def is_object(self, node: Mapping[str, Any]) -> bool:
        return bool(self.resolved(node).get("properties"))

    def object_of(self, node: Mapping[str, Any]) -> _Object:
        if "$ref" in node:
            return self.by_ref[node["$ref"]]
        return self.by_node[id(node)]

    def add(self, node: Mapping[str, Any], title: str, path: str) -> None:
        """Adds the object `node` holds, unless it's added already, then the objects in it. It
        checks `node` first, so the keywords beside a reference are checked each time it's
        reached, and from wherever."""
        self.check_keywords(node, path)
        if ("$ref" in node and node["$ref"] in self.by_ref) or id(node) in self.by_node:
            return
        schema = self.resolved(node)
        self.check_keywords(schema, path)
        anchor = f"{self.page.prefix}-{_slug(path)}"
        if any(found.anchor == anchor for found in self.objects):
            raise GenerationError(f"{self.page.schema}: two objects are named {path}")
        found = _Object(title, anchor, schema, _markdown(schema.get("description", "")))
        self.objects.append(found)
        if "$ref" in node:
            self.by_ref[node["$ref"]] = found
        else:
            self.by_node[id(node)] = found
        if schema.get("additionalProperties", True) is not False:
            raise GenerationError(f"{self.page.schema}: {path} allows any key")
        for name, value in schema["properties"].items():
            self.visit(value, f"{path}.{name}")

    def visit(self, node: Mapping[str, Any], path: str) -> None:
        """Adds the objects a key's value can hold, and checks each value the schema reaches
        from it."""
        kind = self.check_keywords(node, path)
        if self.is_object(node):
            self.add(node, self.title(path), path)
        elif kind == "reference":
            self.visit(self.definition(node["$ref"]), path)
        elif kind == "alternatives":
            objects = [option for option in node["anyOf"] if self.is_object(option)]
            for option in node["anyOf"]:
                if self.is_object(option) and len(objects) > 1:
                    first = self.resolved(option).get("required", [None])[0]
                    if first is None:
                        raise GenerationError(f"{self.page.schema}: {path} has no required key")
                    title = f"{self.title(path)} with {_code(first)}"
                    self.add(option, title, f"{path}-{first}")
                else:
                    self.visit(option, path)
        elif kind == "array":
            for item in [node.get("items"), *node.get("prefixItems", [])]:
                if item is not None:
                    self.visit(item, f"{path}[]")
        elif kind == "mapping":
            unknown = sorted(node.get("propertyNames", {}).keys() - NAME_KEYWORDS)
            if unknown:
                raise GenerationError(
                    f"{self.page.schema}: {path}'s keys use {', '.join(unknown)}, which the"
                    " generator can't put in plain words"
                )
            for value in node.get("patternProperties", {}).values():
                if self.is_object(value) or value.get("type") in ("array", "object"):
                    raise GenerationError(f"{self.page.schema}: {path} maps names to objects")
                self.visit(value, f"{path}.*")

    def title(self, path: str) -> str:
        if path.endswith("[]"):
            return f"Each of {_code(path[:-2])}"
        return _code(path)

    def kind(self, node: Mapping[str, Any], path: str) -> str:
        """The kind of value `node` allows, which says how it's put in words, and so which
        keywords it may use."""
        if isinstance(node.get("type"), list):
            raise GenerationError(f"{self.page.schema}: {path} has a list of types")
        if self.is_object(node):
            return "reference" if "$ref" in node else "object"
        for keyword, kind in (
            ("$ref", "reference"),
            ("anyOf", "alternatives"),
            ("const", "constant"),
            ("enum", "enumeration"),
        ):
            if keyword in node:
                return kind
        kind = node.get("type")
        if kind == "object":
            return "mapping"
        if kind not in ("string", "integer", "number", "boolean", "null", "array"):
            raise GenerationError(f"{self.page.schema}: {path} has no type the generator knows")
        return kind

    def check_keywords(self, node: Mapping[str, Any], path: str, top: bool = False) -> str:
        """Fails when `node` uses a keyword its kind of value doesn't, and gives the kind."""
        kind = "object" if top else self.kind(node, path)
        unknown = sorted(node.keys() - (ROOT_KEYWORDS if top else KEYWORDS[kind]))
        if unknown:
            raise GenerationError(
                f"{self.page.schema}: {path} uses {', '.join(unknown)}, which the generator can't"
                " put in plain words"
            )
        return kind

    # Describing a value

    def link(self, node: Mapping[str, Any], text: str) -> str:
        return f"[{text}](#{self.object_of(node).anchor})"

    def phrase(self, node: Mapping[str, Any], path: str) -> str:
        """The value `node` allows, in plain words, starting in lowercase."""
        words = self.value(node, path)
        if "default" in node:
            words = f"{words}; {_code(node['default'])} by default"
        return words

    def value(self, node: Mapping[str, Any], path: str) -> str:
        kind = self.kind(node, path)
        if self.is_object(node):
            return f"an {self.link(node, 'object')}"
        if kind == "reference":
            return self.phrase(self.definition(node["$ref"]), path)
        if kind == "alternatives":
            return self.any_of(node["anyOf"], path)
        if kind == "constant":
            return _code(node["const"])
        if kind == "enumeration":
            return _alternatives([_code(value) for value in node["enum"]])
        if kind == "string":
            return self.string(node, path)
        if kind in ("integer", "number"):
            return self.number(node, "an integer" if kind == "integer" else "a number")
        if kind == "boolean":
            return "`true` or `false`"
        if kind == "null":
            return "empty" if self.page.csv else "`null`"
        if kind == "array":
            return self.array(node, path)
        return self.mapping(node, path)

    def any_of(self, options: Sequence[Mapping[str, Any]], path: str) -> str:
        parts: list[str] = []
        objects: list[str] = []
        single: list[Mapping[str, Any]] = []
        for option in options:
            if self.is_object(option):
                if not objects:
                    parts.append("")  # the objects' place, filled in below
                objects.append(self.link(option, self.object_of(option).title))
                single.append(option)
            elif option != NULL:
                parts.append(self.phrase(option, path))
        if objects:
            together = (
                f"an {self.link(single[0], 'object')}"
                if len(single) == 1
                else f"one of these objects: {_alternatives(objects)}"
            )
            parts[parts.index("")] = together
        if NULL in options:
            parts.append("empty" if self.page.csv else "`null`")
        return _choices(parts)

    def string(self, node: Mapping[str, Any], path: str) -> str:
        base = "text"
        constraints: list[str] = []
        if "format" in node:
            if node["format"] not in FORMATS:
                raise GenerationError(f"{self.page.schema}: {path} has the format {node['format']}")
            base = FORMATS[node["format"]]
        pattern = node.get("pattern")
        if pattern is not None and pattern not in PATTERNS:
            raise GenerationError(
                f"{self.page.schema}: {path} has the pattern {pattern!r}, which the generator"
                " can't put in plain words"
            )
        kind, words = PATTERNS[pattern] if pattern is not None else ("", "")
        if kind == "form":
            if "format" in node:
                raise GenerationError(f"{self.page.schema}: {path} has a format and a pattern")
            base = words
        least, most = node.get("minLength"), node.get("maxLength")
        if least is not None and most is not None:
            constraints.append(f"{_number(least)} to {_number(most)} characters")
        elif most is not None:
            constraints.append(f"at most {_number(most)} characters")
        elif least is not None and not (least == 1 and pattern is not None):
            constraints.append(
                "not empty" if least == 1 else f"at least {_number(least)} characters"
            )
        if kind == "constraint":
            constraints.append(words)
        if "not" in node:
            constraints.append(self.excluded(node["not"], path))
        return ", ".join([base, *constraints])

    def excluded(self, node: Mapping[str, Any], path: str) -> str:
        if set(node) != {"enum"}:
            raise GenerationError(f"{self.page.schema}: {path} excludes more than a list of values")
        if tuple(node["enum"]) == WINDOWS_RESERVED:
            return (
                "not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or"
                " `lpt1` to `lpt9`"
            )
        return f"not {_alternatives([_code(value) for value in node['enum']])}"

    def number(self, node: Mapping[str, Any], base: str) -> str:
        bounds: list[str] = []
        least, most = node.get("minimum"), node.get("maximum")
        above, below = node.get("exclusiveMinimum"), node.get("exclusiveMaximum")
        if least is not None and most is not None:
            bounds.append(f"from {_number(least)} to {_number(most)}")
        elif least is not None:
            bounds.append(f"{_number(least)} or more")
        elif most is not None:
            bounds.append(f"at most {_number(most)}")
        if above is not None:
            bounds.append(f"more than {_number(above)}")
        if below is not None:
            bounds.append(f"less than {_number(below)}")
        if len(bounds) == 2:
            return f"{base}, {bounds[0]}, and {bounds[1]}"
        return ", ".join([base, *bounds])

    def array(self, node: Mapping[str, Any], path: str) -> str:
        least, most = node.get("minItems"), node.get("maxItems")
        items = node.get("items")
        if "prefixItems" in node:
            prefix = node["prefixItems"]
            if items is not None or len(prefix) != 1 or least != 1 or most != 1:
                raise GenerationError(f"{self.page.schema}: {path} is a tuple the generator can't")
            items = prefix[0]
        if items is None:
            raise GenerationError(f"{self.page.schema}: {path} is a list without its items")
        if least is not None and least == most:
            count = f"exactly {_count(least)}"
        elif least and most is not None:
            count = f"{_count(least)} to {_count(most)}"
        elif least:
            count = f"at least {_count(least)}"
        elif most is not None:
            count = f"at most {_count(most)}"
        else:
            count = ""
        one = count.endswith(" one")
        if self.is_object(items):
            if self.page.csv:
                raise GenerationError(f"{self.page.schema}: {path} is a list of objects in a table")
            noun = self.link(items, "object" if one else "objects")
            return f"a list of {count} {noun}" if count else f"a list of {noun}"
        words = self.phrase(items, f"{path}[]")
        if self.page.csv:
            separated = f"items separated by semicolons, each {words}"
            if count:
                return f"{count} {separated}"
            return f"{separated}; empty when there are none"
        noun = "item" if one else "items"
        return (
            f"a list of {count} {noun}, each {words}" if count else f"a list of items, each {words}"
        )

    def mapping(self, node: Mapping[str, Any], path: str) -> str:
        patterns: Mapping[str, Any] = node.get("patternProperties", {})
        if not patterns:
            if node.get("properties") or "propertyNames" in node:
                raise GenerationError(
                    f"{self.page.schema}: {path} is an object the generator can't"
                )
            if node.get("additionalProperties", True) is not False:
                raise GenerationError(f"{self.page.schema}: {path} allows any key")
            return "an empty object, `{}`"
        if len(patterns) != 1 or node.get("additionalProperties", True) is not True:
            raise GenerationError(f"{self.page.schema}: {path} is a mapping the generator can't")
        ((pattern, value),) = patterns.items()
        names = self.string({"type": "string", **node.get("propertyNames", {})}, f"{path} keys")
        matching = self.string({"type": "string", "pattern": pattern}, f"{path} keys")
        return (
            f"an object whose keys are {names}; each key that's {matching.removeprefix('text, ')}"
            f" has a value that's {self.phrase(value, f'{path}.*')}"
        )

    # The tables

    def table(self, found: _Object) -> Table:
        header = [self.page.key]
        if self.page.required:
            header.append("Required")
        header.append("Value")
        if self.page.description_column:
            header.append("Description")
        hand_written = self.page.hand_written is not None and (found.top or not self.page.top_only)
        if hand_written and self.page.hand_written is not None:
            header.append(self.page.hand_written)
        required: Sequence[str] = found.schema.get("required", [])
        rows: list[tuple[str, ...]] = []
        for name, node in found.schema["properties"].items():
            row = [_code(name)]
            if self.page.required:
                row.append("Yes" if name in required else "No")
            value = _capitalized(self.phrase(node, name))
            description = _markdown(node.get("description", ""))
            if self.page.description_column:
                row += [value, description]
            else:
                row.append(f"{value}. {description}" if description else value)
            rows.append(tuple(row))
        return Table(tuple(header), tuple(rows), hand_written)

    def regions(self) -> dict[str, Region]:
        self.check_keywords(self.root, "the top level", top=True)
        if self.root.get("type") != "object" or not self.root.get("properties"):
            raise GenerationError(f"{self.page.schema}: the top level isn't an object with keys")
        if self.root.get("additionalProperties", True) is not False:
            raise GenerationError(f"{self.page.schema}: the top level allows any key")
        description = _markdown(self.root.get("description", ""))
        top = _Object("", self.page.prefix, self.root, description, top=True)
        self.objects.append(top)
        for name, value in self.root["properties"].items():
            self.visit(value, name)
        tables = {found.anchor: self.table(found) for found in self.objects}
        nested = [found for found in self.objects if not found.top]

        def section(found: _Object) -> list[Block]:
            heading = f"{self.page.heading} {found.title} {{ #{found.anchor} }}"
            described = [found.description] if found.description else []
            return [heading, *described, tables[found.anchor]]

        if self.page.split:
            regions = {self.page.prefix: Region((tables[self.page.prefix],))}
            for found in nested:
                regions[found.anchor] = Region(tuple(section(found)))
            return regions
        source = f"{GITHUB}schemas/{self.page.schema}"
        blocks: list[Block] = [f"Its schema: [{_code(f'schemas/{self.page.schema}')}]({source})."]
        if top.description:
            blocks.append(top.description)
        blocks.append(tables[top.anchor])
        for found in nested:
            blocks += section(found)
        return {self.page.prefix: Region(tuple(blocks))}


def schema_regions(page: SchemaPage, schema: Mapping[str, Any]) -> dict[str, Region]:
    """The regions one schema generates, as `page` lays them out."""
    return _Walk(page, schema).regions()


def _configuration(prefix: str, schema: str) -> SchemaPage:
    return SchemaPage(prefix, schema, description_column=False, hand_written="What it's for")


def _output_file(prefix: str, schema: str) -> SchemaPage:
    return SchemaPage(prefix, schema, key="Field", split=False)


def _csv(prefix: str, schema: str) -> SchemaPage:
    return SchemaPage(prefix, schema, key="Column", required=False, csv=True)


# Each schema's page, by its regions' prefix. The output files are those Trial Folio writes, each
# at the version it writes now: a screen run's plan and records stay 1.0.0, and an experiment's
# are 1.1.0 (src/trialfolio/contracts/schema_files.py).
SCHEMA_PAGES: Final = (
    _configuration("screen-configuration", "screen-configuration-1.0.0.schema.json"),
    _configuration("review-configuration", "review-configuration-1.0.0.schema.json"),
    _configuration("experiment-configuration", "experiment-configuration-1.0.0.schema.json"),
    _csv("outputs-metrics-csv", "metrics-row-1.0.0.schema.json"),
    _csv("outputs-settings-csv", "settings-row-1.0.0.schema.json"),
    _csv("outputs-differences-csv", "differences-row-1.0.0.schema.json"),
    _output_file("output-fields-run-manifest", "run-manifest-1.0.0.schema.json"),
    _output_file("output-fields-run-plan", "plan-1.0.0.schema.json"),
    _output_file("output-fields-run-start-record", "start-record-1.0.0.schema.json"),
    _output_file("output-fields-run-attempt-record", "attempt-record-1.0.0.schema.json"),
    _output_file("output-fields-experiment-start-record", "start-record-1.1.0.schema.json"),
    _output_file("output-fields-experiment-attempt-record", "attempt-record-1.1.0.schema.json"),
    _output_file("output-fields-authentication-record", "authentication-record-1.0.0.schema.json"),
    _output_file("output-fields-experiment-plan", "plan-1.1.0.schema.json"),
    _output_file("output-fields-experiment-record", "experiment-record-1.0.0.schema.json"),
    _output_file("output-fields-session-record", "session-record-1.0.0.schema.json"),
    _output_file("output-fields-session-manifest", "experiment-manifest-1.0.0.schema.json"),
    _output_file("output-fields-review-manifest", "review-manifest-1.0.0.schema.json"),
    _output_file("output-fields-acknowledgment", "license-acknowledgment.schema.json"),
    SchemaPage(
        "json-summary",
        "json-summary-1.2.0.schema.json",
        hand_written="What it holds",
        top_only=True,
        heading="##",
    ),
)


# contracts.md's errors


def _sections(text: str, heading: str) -> list[str]:
    """The lines of the section that `heading` starts, up to the next heading, outside code."""
    lines = text.split("\n")
    if heading not in lines:
        raise GenerationError(f"contracts.md has no {heading!r}")
    section: list[str] = []
    fenced = False
    for line in lines[lines.index(heading) + 1 :]:
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("#"):
            break
        section.append(line)
    return section


def _contracts_table(text: str, heading: str, header: Sequence[str]) -> list[list[str]]:
    """The rows of the one table under `heading` whose header is `header`."""
    tables: list[list[str]] = []
    for line in _sections(text, heading):
        if line.startswith("|"):
            if not tables or tables[-1][-1] == "":
                tables.append([])
            tables[-1].append(line)
        elif tables and tables[-1][-1] != "":
            tables[-1].append("")
    found = [
        [line for line in table if line] for table in tables if _cells(table[0]) == list(header)
    ]
    if len(found) != 1:
        raise GenerationError(
            f"contracts.md's {heading.lstrip('# ')!r} has {len(found)} tables headed"
            f" {', '.join(header)}, not one"
        )
    rows = [_cells(line) for line in found[0][2:]]
    for row in rows:
        if len(row) != len(header):
            raise GenerationError(f"contracts.md's {heading.lstrip('# ')!r} has a row of {row}")
    return rows


def _absolute(target: str) -> str:
    """A link in contracts.md, as it leads from the site: to the file on GitHub."""
    if re.match(r"[a-z][a-z0-9+.-]*:", target):
        return target
    path, hash_, fragment = target.partition("#")
    resolved = posixpath.normpath(posixpath.join("docs", path or "contracts.md"))
    if resolved.startswith("../") or resolved == "..":
        raise GenerationError(f"contracts.md links outside the repository: {target}")
    return f"{GITHUB}{resolved}{hash_}{fragment}"


def _absolute_links(text: str) -> str:
    return re.sub(r"\]\(([^)\s]+)\)", lambda match: f"]({_absolute(match.group(1))})", text)


def error_regions(contracts: str, exit_codes: Mapping[str, int]) -> dict[str, Region]:
    """errors.md's regions: the error codes, from contracts.md's errors table, which must give the
    codes and exit codes `exit_codes` gives, and the exit codes, from its exit-code table."""
    rows = _contracts_table(contracts, "## Errors", ("Code", "Exit", "Meaning"))
    problems: list[str] = []
    codes: dict[str, int] = {}
    for code_cell, exit_cell, _meaning in rows:
        code = code_cell.strip("`")
        if code in codes:
            problems.append(f"contracts.md's errors table lists {code} twice")
        if not exit_cell.isdigit():
            problems.append(f"contracts.md's errors table gives {code} the exit code {exit_cell}")
            continue
        codes[code] = int(exit_cell)
    for code, exit_code in exit_codes.items():
        if code not in codes:
            problems.append(f"EXIT_CODES has {code}, which contracts.md's errors table lacks")
        elif codes[code] != exit_code:
            problems.append(
                f"{code} exits {codes[code]} in contracts.md's errors table, and {exit_code} in"
                " EXIT_CODES"
            )
    for code in codes:
        if code not in exit_codes:
            problems.append(f"contracts.md's errors table has {code}, which EXIT_CODES lacks")

    exits = _contracts_table(contracts, "## CLI behavior", ("Code", "Meaning"))
    listed = [cells[0] for cells in exits]
    for exit_code in sorted({0, *exit_codes.values()}):
        if str(exit_code) not in listed:
            problems.append(f"contracts.md's exit-code table lacks {exit_code}")
    for exit_code in listed:
        if not exit_code.isdigit() or (
            int(exit_code) != 0 and int(exit_code) not in codes.values()
        ):
            problems.append(f"contracts.md's exit-code table has {exit_code}, which no error has")
    if problems:
        raise GenerationError("; ".join(problems))

    return {
        "errors-codes": Region(
            (
                Table(
                    ("Code", "Exit code", "Meaning", "What to do"),
                    tuple(
                        (code_cell, exit_cell, _absolute_links(meaning))
                        for code_cell, exit_cell, meaning in rows
                    ),
                    hand_written=True,
                ),
            )
        ),
        "errors-exit-codes": Region(
            (
                Table(
                    ("Code", "Meaning"),
                    tuple((code, _absolute_links(meaning)) for code, meaning in exits),
                ),
            )
        ),
    }


# The pages


@dataclass(frozen=True)
class _Found:
    """A region on a page: the lines of its markers."""

    page: Path
    region_id: str
    start: int
    end: int


def _name(manual: Path, page: Path) -> str:
    return f"{manual.name}/{page.relative_to(manual).as_posix()}"


def _scan(manual: Path) -> tuple[dict[Path, list[str]], list[_Found], list[str]]:
    """Every page's lines, every region found, and each problem with the markers."""
    pages: dict[Path, list[str]] = {}
    found: list[_Found] = []
    problems: list[str] = []
    for page in sorted(manual.rglob("*.md")):
        lines = page.read_text(encoding="utf-8").split("\n")
        pages[page] = lines
        name = _name(manual, page)
        open_: tuple[str, int] | None = None
        for number, line in enumerate(lines):
            start, end = START.fullmatch(line), END.fullmatch(line)
            if start is not None:
                if open_ is not None:
                    problems.append(
                        f"{name}:{number + 1}: region {start.group(1)} starts inside region"
                        f" {open_[0]}, which starts at line {open_[1] + 1}"
                    )
                else:
                    open_ = (start.group(1), number)
            elif end is not None:
                if open_ is None:
                    problems.append(
                        f"{name}:{number + 1}: region {end.group(1)} ends, but no region started"
                    )
                elif end.group(1) != open_[0]:
                    problems.append(
                        f"{name}:{number + 1}: region {end.group(1)} ends, but region {open_[0]}"
                        f" started at line {open_[1] + 1}"
                    )
                    open_ = None
                else:
                    found.append(_Found(page, open_[0], open_[1], number))
                    open_ = None
            elif MARKER.search(line):
                problems.append(f"{name}:{number + 1}: a marker that isn't one: {line.strip()}")
        if open_ is not None:
            problems.append(f"{name}:{open_[1] + 1}: region {open_[0]} starts, and never ends")
    return pages, found, problems


def _placed(
    manual: Path, generated: Mapping[str, Region]
) -> tuple[dict[Path, list[str]], list[_Found], list[str], list[str]]:
    """The pages; the regions on them that can be regenerated; each problem that keeps the pages
    from being regenerated: the markers, an unknown region, and a region that appears more than
    once, which is left out of the regions; and each registered region on no page."""
    pages, found, problems = _scan(manual)
    places: dict[str, list[_Found]] = {}
    for region in found:
        places.setdefault(region.region_id, []).append(region)
    for region_id, regions in places.items():
        where = ", ".join(f"{_name(manual, r.page)}:{r.start + 1}" for r in regions)
        if region_id not in generated:
            problems.append(f"{where}: names region {region_id}, which isn't registered")
        elif len(regions) > 1:
            problems.append(f"region {region_id} appears more than once: {where}")
    usable = [r for r in found if r.region_id in generated and len(places[r.region_id]) == 1]
    missing = [
        f"region {region_id} appears on no page in {manual.name}/"
        for region_id in generated
        if region_id not in places
    ]
    return pages, usable, problems, missing


def _empty(manual: Path, generated: Mapping[str, Region], region: _Found, text: str) -> list[str]:
    table = _hand_written_table(generated[region.region_id])
    column = table.header[-1] if table is not None else ""
    return [
        f"{_name(manual, region.page)}: region {region.region_id}: the row {key} has no"
        f" {column!r} yet; write it"
        for key in _empty_cells(generated[region.region_id], text)
    ]


def check(manual: Path, generated: Mapping[str, Region]) -> list[str]:
    """Every problem with the generated regions of the pages in `manual`, or none."""
    pages, found, problems, missing = _placed(manual, generated)
    problems += missing
    for region in found:
        lines = pages[region.page]
        existing = "\n".join(lines[region.start + 1 : region.end])
        if existing != render(generated[region.region_id], existing):
            problems.append(
                f"{_name(manual, region.page)}:{region.start + 1}: region {region.region_id}"
                " differs from what its source generates"
            )
        problems += _empty(manual, generated, region, existing)
    return problems


def rewrite(manual: Path, generated: Mapping[str, Region]) -> list[str]:
    """Rewrites each generated region of the pages in `manual`, keeping the hand-written cells,
    and returns each problem left. A problem with the markers, an unknown region, or a region
    that appears more than once leaves every page as it is."""
    pages, found, problems, missing = _placed(manual, generated)
    if problems:
        return problems + missing
    left: list[str] = []
    for page, lines in pages.items():
        regions = sorted((region for region in found if region.page == page), key=lambda r: r.start)
        if not regions:
            continue
        rewritten: list[str] = []
        position = 0
        for region in regions:
            existing = "\n".join(lines[region.start + 1 : region.end])
            text = render(generated[region.region_id], existing)
            rewritten += lines[position : region.start + 1]
            rewritten += text.split("\n")
            position = region.end
            left += _empty(manual, generated, region, text)
        rewritten += lines[position:]
        if rewritten != lines:
            page.write_bytes("\n".join(rewritten).encode("utf-8"))
    return missing + left


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/manual_reference.py",
        description=(
            "Generate the user manual's reference tables from their sources, or check them."
        ),
    )
    parser.add_argument("--check", action="store_true", help="compare only; write nothing")
    arguments = parser.parse_args(argv)
    try:
        generated = generate(default_sources())
    except GenerationError as error:
        print(f"manual_reference: {error}", file=sys.stderr)
        return 1
    problems = check(MANUAL, generated) if arguments.check else rewrite(MANUAL, generated)
    for problem in problems:
        print(f"manual_reference: {problem}", file=sys.stderr)
    if problems:
        if arguments.check:
            print(
                "manual_reference: to fix the regions, run uv run python"
                " scripts/manual_reference.py, then write each empty hand-written cell.",
                file=sys.stderr,
            )
        return 1
    if arguments.check:
        print(f"The {len(generated)} generated regions in manual/ match their sources.")
    else:
        print(f"Wrote the {len(generated)} generated regions in manual/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
