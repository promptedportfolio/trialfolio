"""The inventory, the first half of the check of the tests, which TS-AC04 runs
(docs/test-refactoring.md, the check of the tests): lists the IDs of the tests each suite
collects, so that a task of the tests' refactor can list them on its base and on its branch, and
show that every test is kept, or became what the task's map gives.

`list <out>` writes into `<out>`, a new JSON file, the IDs each suite collects, by suite, in the
order pytest collects them: the default suite, as `uv run pytest` selects it, and the tests that
`-m packaging`, `-m reference`, and `-m live` select. It collects only, so it runs no test, sends
nothing, and needs no credentials or reference data. Each suite is collected in a pytest process of
its own, in this checkout, with this interpreter, and without the `PYTEST_` variables, which could
add options to those pyproject.toml gives.

`compare <before> <after> [<task>]` compares two such files, suite by suite. Each ID at the base is
kept, when the branch collects it and no row of the task's map names the test itself, or moved, when
the map gives what it became and the branch collects that. It lists each ID that's dropped, at the
base and neither kept nor moved, and each that's added, on the branch and neither kept nor what the
map gives. It lists, too, each name the map gives that the base or the branch doesn't collect. It
fails when it lists a dropped test or a name the map gives, and not for an added one, since a task
may add tests. It fails too, with the error, and exit code 2, as for a wrong usage, when it can't
read either file or the map.

The map is the task's rows of the table in docs/test-refactoring.md's "Where the tests moved", whose
columns are Task, Had, and Has. Had gives one name in backticks, and Has the one or more it became,
each in backticks. A name is a test's ID, or the start of one, up to a `::` or a `[`: a module, such
as `tests/core/test_report.py`, stands for every test in it, and a test's name for each of its
parameters. The most specific of the task's rows that covers a test moves it, and each name the row
gives, with the rest of the test's ID kept, stands for what the test became, each of its parameters
included. A test in a module or a class the row names is moved when the branch collects it under
any of those names, so a separated module's row gives each module its tests went to. A test the row
names itself, with or without its parameters, is never kept: it's moved only when the branch
collects it under every one, even when one of them is its own name, so a test split in two keeps
each of its parameters in both, whichever part keeps the test's name. Without `<task>`, nothing is
moved.

For a task, list the tests on its base and on its branch, each in a worktree of its own, synced
with `uv sync`, then compare them from the branch:

    uv run python -m tests.support.inventory list <scratch>/before.json     # on the base
    uv run python -m tests.support.inventory list <scratch>/after.json      # on the branch
    uv run python -m tests.support.inventory compare <scratch>/before.json <scratch>/after.json <task>

TS-T01 wrote it. Its base had no copy, so it ran there from a copy of this file.
"""

import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from pydantic import TypeAdapter, ValidationError

ROOT: Final = Path(__file__).resolve().parents[2]
"""The checkout this file is in, whose tests it lists."""
MAP: Final = ROOT / "docs" / "test-refactoring.md"
"""The plan whose "Where the tests moved" holds each task's map."""

SUITES: Final = {
    "default": (),
    "packaging": ("-m", "packaging"),
    "reference": ("-m", "reference"),
    "live": ("-m", "live"),
}
"""Each suite, with the options that select it, as AGENTS.md's development commands give. The
default suite takes pyproject.toml's `-m`, which leaves out the other three."""

type Inventory = dict[str, list[str]]
"""The IDs each suite collects, by suite."""

_INVENTORY: Final = TypeAdapter[Inventory](dict[str, list[str]])
_SECTION: Final = "## Where the tests moved"
_COLUMNS: Final = ("Task", "Had", "Has")
_NAME: Final = re.compile(r"`([^`]+)`")
_NO_TESTS_COLLECTED: Final = 5
"""pytest's exit code when the options select no test."""


class CollectionFailed(Exception):
    """pytest couldn't collect the tests, with what it wrote."""


def environment() -> dict[str, str]:
    """This process's environment, without the `PYTEST_` variables, such as `PYTEST_ADDOPTS`,
    which would add options to those pyproject.toml gives."""
    return {name: value for name, value in os.environ.items() if not name.startswith("PYTEST_")}


def collected(root: Path, *options: str, env: dict[str, str] | None = None) -> list[str]:
    """The IDs of the tests pytest collects in `root` with `options`, in the order it collects
    them, or none when it selects none. Runs no test. Raises `CollectionFailed` when pytest can't
    collect them, such as for a module that doesn't import, or a path that isn't there."""
    finished = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *options,
        ],
        cwd=root,
        env=environment() if env is None else env,
        capture_output=True,
        text=True,
        check=False,
    )
    if finished.returncode == _NO_TESTS_COLLECTED:
        return []
    if finished.returncode != 0:
        raise CollectionFailed(
            f"pytest {' '.join(options)} exited with {finished.returncode} while collecting:\n"
            f"{finished.stdout}{finished.stderr}"
        )
    ids: list[str] = []
    for line in finished.stdout.splitlines():
        if not line:
            break
        if "::" not in line:
            raise CollectionFailed(f"pytest gave a line that isn't a test's ID: {line!r}")
        ids.append(line)
    return ids


def inventory(root: Path = ROOT) -> Inventory:
    """The IDs each suite collects in `root`, by suite."""
    return {suite: collected(root, *options) for suite, options in SUITES.items()}


def read(path: Path) -> Inventory:
    """The inventory `list` wrote into `path`. Raises an `OSError` when it can't be read, and a
    `ValueError` when it isn't an inventory of each suite."""
    try:
        found = _INVENTORY.validate_json(path.read_bytes())
    except ValidationError as error:
        raise ValueError(f"{path} isn't an inventory: {error}") from error
    if list(found) != list(SUITES):
        raise ValueError(f"{path} lists the suites {list(found)}, not {list(SUITES)}")
    return found


@dataclass(frozen=True)
class Move:
    """A row of a task's map: the name a test had, and the one or more it has."""

    had: str
    has: tuple[str, ...]


def covers(name: str, test_id: str) -> bool:
    """Whether `name` is `test_id`, or its start up to a `::` or a `[`, so that a module stands for
    each of its tests, and a test's name for each of its parameters."""
    return test_id == name or test_id.startswith((f"{name}::", f"{name}["))


def moves_of(text: str, task: str) -> list[Move]:
    """The rows for `task` of the table in `text`'s "Where the tests moved", a Markdown file such as
    docs/test-refactoring.md. Raises a `ValueError` for a table whose columns aren't Task, Had, and
    Has, or a row that doesn't give one name it had and at least one it has, whichever its task."""
    _, found, section = f"\n{text}".partition(f"\n{_SECTION}\n")
    if not found:
        raise ValueError(f"no section {_SECTION!r}")
    section = section.split("\n## ", 1)[0]
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("|")
    ]
    if not rows:
        return []
    separated = len(rows) > 1 and all(set(cell) <= set("-:") for cell in rows[1])
    if tuple(rows[0]) != _COLUMNS or not separated:
        raise ValueError(f"the map's table has the columns {rows[0]}, not {list(_COLUMNS)}")
    moves: list[Move] = []
    for row in rows[2:]:
        if len(row) != len(_COLUMNS):
            raise ValueError(f"the map's row {row} doesn't have {len(_COLUMNS)} cells")
        had, has = _NAME.findall(row[1]), _NAME.findall(row[2])
        if len(had) != 1 or not has:
            raise ValueError(f"the map's row {row} doesn't give one name it had, and what it has")
        if row[0] == task:
            moves.append(Move(had[0], tuple(has)))
    return moves


def _move_of(test_id: str, moves: Sequence[Move]) -> Move | None:
    """The most specific of `moves` that covers `test_id`, if any does."""
    covering = [move for move in moves if covers(move.had, test_id)]
    return max(covering, key=lambda move: len(move.had), default=None)


def _names(move: Move, test_id: str) -> bool:
    """Whether `move` names the test `test_id` itself, with or without its parameters, rather than
    its module or its class."""
    return not test_id[len(move.had) :].startswith("::")


def _became(test_id: str, move: Move, branch: Sequence[str]) -> list[str]:
    """The IDs of `branch` that `test_id` became under `move`, or none when it didn't move. Each
    name the move gives, with the rest of `test_id` kept, covers the IDs it became. A test in a
    module or a class the move names became any of them, and a test the move names itself every
    one."""
    rest = test_id[len(move.had) :]
    each = [[new for new in branch if covers(name + rest, new)] for name in move.has]
    if _names(move, test_id) and not all(each):
        return []
    return [new for ids in each for new in ids]


@dataclass
class Comparison:
    """What `compare` lists, and its counts, suite by suite."""

    dropped: list[str] = field(default_factory=list[str])
    added: list[str] = field(default_factory=list[str])
    unmatched: list[str] = field(default_factory=list[str])
    """Each name the map gives that the base or the branch doesn't collect."""
    counts: list[str] = field(default_factory=list[str])

    @property
    def failed(self) -> bool:
        return bool(self.dropped or self.unmatched)


def _all(found: Inventory) -> Iterable[str]:
    return (test_id for ids in found.values() for test_id in ids)


def differences(before: Inventory, after: Inventory, moves: Sequence[Move] = ()) -> Comparison:
    """Compares the base's inventory, `before`, with the branch's, `after`, suite by suite, with the
    task's map, `moves`, as the module says."""
    comparison = Comparison()
    for suite in SUITES:
        base, branch = before[suite], set(after[suite])
        kept = moved = 0
        became: set[str] = set()
        for test_id in base:
            move = _move_of(test_id, moves)
            if test_id in branch and not (move and _names(move, test_id)):
                kept += 1
            elif move and (found := _became(test_id, move, after[suite])):
                moved += 1
                became.update(found)
            else:
                comparison.dropped.append(f"dropped from {suite}: {test_id}")
        known = set(base) | became
        added = [test_id for test_id in after[suite] if test_id not in known]
        comparison.added += [f"added to {suite}: {test_id}" for test_id in added]
        comparison.counts.append(
            f"{suite}: {len(base)} at the base, {len(after[suite])} on the branch; {kept} kept, "
            f"{moved} moved, {len(base) - kept - moved} dropped, {len(added)} added."
        )
    for move in moves:
        if not any(covers(move.had, test_id) for test_id in _all(before)):
            comparison.unmatched.append(f"the map's {move.had} isn't at the base")
        for name in move.has:
            if not any(covers(name, test_id) for test_id in _all(after)):
                comparison.unmatched.append(f"the map's {name} isn't on the branch")
    return comparison


def compare(before: Path, after: Path, task: str | None = None) -> int:
    """Prints what `differences` lists, and each suite's counts. Returns 1 when it lists a dropped
    test or a name the map gives, and 0 otherwise. When it can't read either file or the map,
    prints the error instead, and returns 2."""
    try:
        moves = moves_of(MAP.read_text(encoding="utf-8"), task) if task else []
        comparison = differences(read(before), read(after), moves)
    except (OSError, ValueError) as error:
        print(f"Can't compare: {error}", file=sys.stderr)
        return 2
    for line in comparison.dropped + comparison.unmatched + comparison.added:
        print(line)
    for line in comparison.counts:
        print(line)
    return 1 if comparison.failed else 0


_USAGE: Final = (
    "usage: python -m tests.support.inventory list <out>\n"
    "       python -m tests.support.inventory compare <before> <after> [<task>]"
)


def main(argv: list[str]) -> int:
    match argv:
        case ["list", out]:
            try:
                listed = inventory()
                with Path(out).open("x", encoding="utf-8") as file:
                    json.dump(listed, file, indent=2)
                    file.write("\n")
            except (OSError, CollectionFailed) as error:
                print(f"Can't list the tests: {error}", file=sys.stderr)
                return 2
            counts = ", ".join(f"{len(ids)} {suite}" for suite, ids in listed.items())
            print(f"Listed {counts} tests into {out}.")
            return 0
        case ["compare", before, after]:
            return compare(Path(before), Path(after))
        case ["compare", before, after, task]:
            return compare(Path(before), Path(after), task)
        case _:
            print(_USAGE, file=sys.stderr)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
