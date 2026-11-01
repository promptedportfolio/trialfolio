"""The mutations, the second half of the check of the tests, which TS-AC05 runs
(docs/test-refactoring.md, the check of the tests): applies each of a list of changes to a module
of `src/`, one at a time, runs the tests the list names against it, and records which of them fail,
so that a task of the tests' refactor can run the same list on its base and on its branch, and show
that each change a test caught at the base, a test still catches on the branch.

A list is a TOML file, such as `tests/mutations/ts-t01.toml`:

    tests = ["tests/core/test_run_report.py"]  # the tests each mutation runs, unless it names its own
    base_tests = ["..."]                    # optional: those tests' names at the base, if they moved
    marker = "reference"                    # optional: the -m that selects them, if not the default's

    [[mutation]]
    name = "the report leaves out its notice"   # unique in the list
    file = "src/trialfolio/report/page.py"      # a module of src/
    old = '''...'''                             # text that occurs once in the module
    new = '''...'''                             # what replaces it
    tests = ["..."]                             # optional, with base_tests: its own tests
    caught_by = ["tests/...::test_x"]           # optional: tests that must fail with it on the branch

A test is named as pytest takes it: a path, or a test's ID. A test in `caught_by` may be the start of
an ID, up to a `::` or a `[`, so a test's name stands for each of its parameters.

`run [--base] <list> <out>` runs the list in this checkout, which must be a linked Git worktree,
not the repository's main checkout, which other agents may share, and whose `src/` must have no
changes, so a restored module is the committed one. It first checks that the tests import each
module the list changes from this checkout's `src/`, and not from another checkout's, which an
environment synced elsewhere would give. It then runs every test the list names, unchanged, which
must pass, since a skipped test catches nothing: it refuses when none passes, as when each skips,
and, for a list that gives a marker, such as the reference tests', when any skips. For each
mutation, it saves the module's bytes, applies the change, runs the mutation's tests, records which
of them fail, then writes the saved bytes back, never with `git checkout`, and checks them, whatever
stops the run. Before each run, and after each restore, it removes each `__pycache__` under `src/`,
since a change of the same size, within the same second, could leave stale bytecode that still
runs, and the tests run without `PYTHONPYCACHEPREFIX`, which would put their bytecode elsewhere. A
mutation is caught when its tests don't pass, or time out, at five times the unchanged run's time,
and at least a minute. It writes the results into `<out>`, a new JSON file. `--base` runs each
mutation's `base_tests` where the list gives them.

`compare <before> <after>` compares the base's results with the branch's. It lists each mutation as
kept, caught at the base and on the branch; lost, caught at the base only; gained, caught on the
branch only; or missed, caught by neither; and each test in `caught_by` that didn't fail with its
mutation on the branch: pytest's summary gives as failed neither it, nor one of its parameters, nor
its module, as for a module that doesn't import. A mutation whose tests timed out has no summary,
so it lists each such mutation that gives `caught_by`, whose tests can't be shown to have failed.
It fails when a mutation is lost, or a test in `caught_by` didn't fail, or can't be shown to have.
It fails too, with the error, and exit code 2, as for a wrong usage, when it can't read either
file, or the two didn't run the same mutations.

For a task, run its list on its base and on its branch, each in a worktree of its own, synced with
`uv sync`, then compare them from the branch:

    uv run python -m tests.support.mutations run --base <branch>/tests/mutations/<task>.toml \\
        <scratch>/before.json                                                  # on the base
    uv run python -m tests.support.mutations run tests/mutations/<task>.toml <scratch>/after.json
    uv run python -m tests.support.mutations compare <scratch>/before.json <scratch>/after.json

Run it in the foreground, never with a shell's `&`: a process started that way ignores SIGINT, and
so do the tests it runs, so `tests/interface/test_interrupts.py` would wait until its time ran out.

TS-T01 wrote it. Its base had no copy, so it ran there from a copy of this file.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from tests.support.inventory import ROOT, CollectionFailed, collected, covers, environment

_TIMEOUT_FACTOR: Final = 5
_SHORTEST_TIMEOUT_SECONDS: Final = 60.0
_FAILURES: Final = ("FAILED ", "ERROR ")
"""The words that start a line of pytest's short summary for a test that failed or erred."""
_COUNTS: Final = re.compile(r"^(?:=+ )?\d+ \w+.* in [\d.]+s\b")
"""pytest's last line, such as `3 passed, 1 skipped in 0.12s`."""
_COUNT: Final = re.compile(r"(\d+) (\w+)")


class Refused(Exception):
    """The list can't run here, or as given, and why."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Mutation(_Strict):
    """A change to a module of `src/`, and the tests it runs."""

    name: str = Field(min_length=1)
    file: str
    old: str = Field(min_length=1)
    new: str
    tests: list[str] | None = Field(default=None, min_length=1)
    base_tests: list[str] | None = Field(default=None, min_length=1)
    caught_by: list[str] = []

    @model_validator(mode="after")
    def _changes_a_module_of_src(self) -> "Mutation":
        path = PurePosixPath(self.file)
        if path.parts[:1] != ("src",) or ".." in path.parts or path.suffix != ".py":
            raise ValueError(f"{self.file} isn't a module of src/")
        if self.old == self.new:
            raise ValueError(f"{self.name!r} changes nothing")
        if self.base_tests is not None and self.tests is None:
            raise ValueError(f"{self.name!r} gives base_tests without its tests")
        return self


class MutationList(_Strict):
    """A list's file, as the module gives it."""

    tests: list[str] | None = Field(default=None, min_length=1)
    base_tests: list[str] | None = Field(default=None, min_length=1)
    marker: str | None = None
    mutation: list[Mutation] = Field(min_length=1)

    @model_validator(mode="after")
    def _each_mutation_has_its_tests(self) -> "MutationList":
        names = [mutation.name for mutation in self.mutation]
        if len(set(names)) != len(names):
            raise ValueError("two mutations have the same name")
        if self.base_tests is not None and self.tests is None:
            raise ValueError("the list gives base_tests without its tests")
        if self.tests is None and any(mutation.tests is None for mutation in self.mutation):
            raise ValueError("a mutation names no tests, and the list gives none")
        return self

    def tests_of(self, mutation: Mutation, *, base: bool) -> list[str]:
        """The tests `mutation` runs, on the branch, or at the base."""
        tests, base_tests = (
            (mutation.tests, mutation.base_tests)
            if mutation.tests is not None
            else (self.tests, self.base_tests)
        )
        assert tests is not None
        return base_tests if base and base_tests is not None else tests


class Outcome(_Strict):
    """What a mutation's tests did."""

    name: str
    file: str
    old: str
    new: str
    tests: list[str]
    caught_by: list[str]
    exit_code: int | None
    """pytest's exit code, or None when it timed out."""
    failed: list[str]
    """The tests that failed or erred, as pytest's short summary gives them."""
    seconds: float

    @property
    def caught(self) -> bool:
        return self.exit_code != 0


class Results(_Strict):
    """What `run` writes."""

    side: Literal["base", "branch"]
    unchanged_seconds: float
    """How long every test the list names took, unchanged."""
    timeout_seconds: float
    mutations: list[Outcome]


def read_list(path: Path) -> MutationList:
    """The list in `path`. Raises an `OSError` when it can't be read, and a `Refused` when it isn't
    a list, as the module gives it."""
    try:
        return MutationList.model_validate(tomllib.loads(path.read_text(encoding="utf-8")))
    except (tomllib.TOMLDecodeError, ValidationError) as error:
        raise Refused(f"{path} isn't a list of mutations: {error}") from error


def _git(root: Path, *argv: str) -> str:
    """What Git writes for `argv` in `root`, without the variables, such as a hook's `GIT_DIR`,
    that would point it at another repository."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    finished = subprocess.run(
        ["git", *argv], cwd=root, env=env, capture_output=True, text=True, check=False
    )
    if finished.returncode != 0:
        raise Refused(f"git {' '.join(argv)} failed in {root}: {finished.stderr.strip()}")
    return finished.stdout


def check_checkout(root: Path) -> None:
    """Refuses unless `root` is a linked worktree whose `src/` has no changes."""
    git_dir, common_dir = _git(
        root, "rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir"
    ).splitlines()
    if Path(git_dir) == Path(common_dir):
        raise Refused(
            f"{root} is the repository's main checkout, which other agents may share. Run the "
            "mutations in a worktree of their own: git worktree add <path> <commit>."
        )
    if changes := _git(root, "status", "--porcelain", "--untracked-files=all", "--", "src"):
        raise Refused(f"src/ has changes, which a restore would lose:\n{changes}")


def _module_of(file: str) -> str:
    parts = PurePosixPath(file).with_suffix("").parts[1:]
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def check_imports(root: Path, files: Sequence[str], env: dict[str, str]) -> None:
    """Refuses unless Python, run as the tests run, imports each of `files` from `root`."""
    modules = sorted({_module_of(file) for file in files})
    script = (
        "import importlib.util, json, sys\n"
        "print(json.dumps([importlib.util.find_spec(name).origin for name in sys.argv[1:]]))\n"
    )
    finished = subprocess.run(
        [sys.executable, "-c", script, *modules],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if finished.returncode != 0:
        raise Refused(f"Python can't import {', '.join(modules)}:\n{finished.stderr}")
    for module, origin in zip(modules, json.loads(finished.stdout), strict=True):
        expected = root.joinpath("src", *module.split("."))
        if Path(origin).resolve() not in {
            expected.with_suffix(".py").resolve(),
            (expected / "__init__.py").resolve(),
        }:
            raise Refused(
                f"the tests would import {module} from {origin}, not from this checkout's src/. "
                "Run the mutations with this checkout's own environment, as uv run gives it."
            )


def _remove_bytecode(root: Path) -> None:
    for cache in (root / "src").rglob("__pycache__"):
        shutil.rmtree(cache)


def _run_tests(
    root: Path,
    tests: Sequence[str],
    marker: str | None,
    env: dict[str, str],
    timeout: float | None,
) -> tuple[int | None, str, float]:
    """pytest's exit code for `tests`, or None when it timed out, what it wrote, and how long it
    took. Its output goes to a file, not a pipe, so a process a test leaves running can't hold the
    run open."""
    command = [sys.executable, "-m", "pytest", "-q", "--tb=no", "-rfEs", "-p", "no:cacheprovider"]
    command += ["-m", marker] if marker else []
    started = time.monotonic()
    with tempfile.TemporaryFile("w+", encoding="utf-8") as output:
        try:
            exit_code = subprocess.run(
                [*command, *tests],
                cwd=root,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            exit_code = None
        output.seek(0)
        return exit_code, output.read(), time.monotonic() - started


def _counts(output: str) -> Counter[str]:
    """How many tests passed, skipped, and so on, as pytest's last line, in `output`, gives them,
    or none when it gives no such line."""
    lines = [line for line in output.splitlines() if _COUNTS.match(line)]
    counts = _COUNT.findall(lines[-1].split(" in ")[0]) if lines else []
    return Counter({word: int(count) for count, word in counts})


def failed_tests(output: str, known: set[str]) -> list[str]:
    """The tests pytest's short summary, in `output`, gives as failed or erred. A line gives the
    test's ID, then, after " - ", its error, and an ID may itself hold " - ", so the ID is the
    longest of `known`, the IDs collected, that the line gives before a " - ", or, for a module that
    didn't import, which isn't among them, the line up to its first " - "."""
    found: list[str] = []
    for line in output.splitlines():
        if not line.startswith(_FAILURES):
            continue
        rest = line.split(" ", 1)[1]
        ends = [len(rest)] + [i for i in range(len(rest)) if rest.startswith(" - ", i)]
        known_ids = [rest[:end] for end in ends if rest[:end] in known]
        found.append(max(known_ids, key=len) if known_ids else rest.split(" - ", 1)[0])
    return found


@contextmanager
def applied(path: Path, mutation: Mutation) -> Iterator[None]:
    """Applies `mutation` to `path` for the block, then writes the saved bytes back, and checks
    them, whatever the change or the block raised, a SIGTERM's `SystemExit` or a Ctrl-C's
    `KeyboardInterrupt` included."""
    saved = path.read_bytes()
    try:
        path.write_bytes(saved.replace(mutation.old.encode(), mutation.new.encode(), 1))
        yield
    finally:
        path.write_bytes(saved)
        if path.read_bytes() != saved:
            raise Refused(f"{path} didn't take back its saved bytes")


def _terminated(signum: int, frame: object) -> None:
    raise SystemExit(128 + signum)


def _checked(listed: MutationList, *, base: bool, root: Path, env: dict[str, str]) -> set[str]:
    """Refuses unless `listed` can run in `root`: each mutation's old text occurs once in its
    module, the tests import those modules from `root`, and each mutation's tests collect. Gives
    the IDs of every test the list runs."""
    check_checkout(root)
    for mutation in listed.mutation:
        count = (root / mutation.file).read_bytes().count(mutation.old.encode())
        if count != 1:
            raise Refused(
                f"{mutation.name!r}: its old text occurs {count} times in {mutation.file}"
            )
    check_imports(root, [mutation.file for mutation in listed.mutation], env)
    marker = ("-m", listed.marker) if listed.marker else ()
    known: set[str] = set()
    for tests in dict.fromkeys(tuple(listed.tests_of(m, base=base)) for m in listed.mutation):
        try:
            ids = collected(root, *marker, *tests, env=env)
        except CollectionFailed as error:
            raise Refused(str(error)) from error
        if not ids:
            raise Refused(f"the tests {list(tests)} collect nothing")
        known.update(ids)
    return known


@dataclass(frozen=True)
class _Run:
    """What each mutation's run shares: the tests' environment, the IDs collected, and the time
    a run may take."""

    env: dict[str, str]
    known: set[str]
    timeout: float


def _mutated(
    listed: MutationList, mutation: Mutation, *, base: bool, root: Path, run: _Run
) -> Outcome:
    """Runs `mutation`'s tests with it applied, and gives what they did."""
    tests = listed.tests_of(mutation, base=base)
    try:
        with applied(root / mutation.file, mutation):
            _remove_bytecode(root)
            exit_code, output, seconds = _run_tests(
                root, tests, listed.marker, run.env, run.timeout
            )
    finally:
        _remove_bytecode(root)
    return Outcome(
        name=mutation.name,
        file=mutation.file,
        old=mutation.old,
        new=mutation.new,
        tests=tests,
        caught_by=mutation.caught_by,
        exit_code=exit_code,
        failed=failed_tests(output, run.known),
        seconds=round(seconds, 1),
    )


def run(
    listed: MutationList,
    *,
    base: bool,
    root: Path = ROOT,
    env: dict[str, str] | None = None,
    shortest_timeout: float = _SHORTEST_TIMEOUT_SECONDS,
) -> Results:
    """Runs `listed` in `root`, as the module says, with `env` for the tests, and gives the
    results. A mutation's tests time out at `_TIMEOUT_FACTOR` times the unchanged run's time, and
    at least `shortest_timeout` seconds. Raises `Refused` when it can't run them, before any
    mutation is applied. The tests run without `PYTHONPYCACHEPREFIX`, so their bytecode of `src/`
    is in the `__pycache__` folders the run removes."""
    env = {
        name: value
        for name, value in (environment() if env is None else env).items()
        if name != "PYTHONPYCACHEPREFIX"
    }
    every = list(
        dict.fromkeys(
            test for mutation in listed.mutation for test in listed.tests_of(mutation, base=base)
        )
    )
    known = _checked(listed, base=base, root=root, env=env)
    _remove_bytecode(root)
    exit_code, output, unchanged = _run_tests(root, every, listed.marker, env, None)
    if exit_code != 0:
        raise Refused(f"the tests don't pass unchanged, so no mutation runs:\n{output}")
    counts = _counts(output)
    if not counts["passed"]:
        raise Refused(
            f"no test passes unchanged, as when each skips, so no mutation runs:\n{output}"
        )
    if listed.marker and counts["skipped"]:
        raise Refused(
            f"{counts['skipped']} of the tests skip unchanged, and a list with a marker runs only "
            f"when none does, so no mutation runs:\n{output}"
        )
    shared = _Run(env, known, max(shortest_timeout, _TIMEOUT_FACTOR * unchanged))
    outcomes: list[Outcome] = []
    previous = signal.signal(signal.SIGTERM, _terminated)
    try:
        for number, mutation in enumerate(listed.mutation, 1):
            outcomes.append(_mutated(listed, mutation, base=base, root=root, run=shared))
            print(f"{number}/{len(listed.mutation)} {_described(outcomes[-1])}: {mutation.name}")
    finally:
        signal.signal(signal.SIGTERM, previous)
    return Results(
        side="base" if base else "branch",
        unchanged_seconds=round(unchanged, 1),
        timeout_seconds=round(shared.timeout, 1),
        mutations=outcomes,
    )


def _described(outcome: Outcome) -> str:
    if outcome.exit_code is None:
        return "caught, timed out"
    if not outcome.caught:
        return "missed"
    return f"caught, exit {outcome.exit_code}, {len(outcome.failed)} failed"


def _read_results(path: Path) -> Results:
    try:
        return Results.model_validate_json(path.read_bytes())
    except ValidationError as error:
        raise ValueError(f"{path} isn't the results of a run: {error}") from error


def compared(before: Results, after: Results) -> tuple[list[str], bool]:
    """The lines `compare` prints, and whether it fails. Raises a `ValueError` unless `before` is
    the base's results and `after` the branch's, of the same mutations, in the same order."""
    if (before.side, after.side) != ("base", "branch"):
        raise ValueError(
            f"the results are the {before.side}'s and the {after.side}'s, in that order"
        )
    same = {"name", "file", "old", "new"}
    ran = [outcome.model_dump(include=same) for outcome in before.mutations]
    if ran != [outcome.model_dump(include=same) for outcome in after.mutations]:
        raise ValueError("the two didn't run the same mutations")
    lines: list[str] = []
    counts = Counter[str]()
    for at_the_base, on_the_branch in zip(before.mutations, after.mutations, strict=True):
        status = {
            (True, True): "kept",
            (True, False): "lost",
            (False, True): "gained",
            (False, False): "missed",
        }[(at_the_base.caught, on_the_branch.caught)]
        counts[status] += 1
        lines.append(
            f"{status}: {on_the_branch.name} (base: {_described(at_the_base)}; "
            f"branch: {_described(on_the_branch)})"
        )
    timed_out = [
        f"timed out, so it can't show its tests in caught_by failed: {outcome.name}"
        for outcome in after.mutations
        if outcome.caught_by and outcome.exit_code is None
    ]
    not_caught = [
        f"not caught by {test}: {outcome.name}"
        for outcome in after.mutations
        if outcome.exit_code is not None
        for test in outcome.caught_by
        if not any(covers(test, failed) or covers(failed, test) for failed in outcome.failed)
    ]
    lines += timed_out + not_caught
    lines.append(
        f"{len(after.mutations)} mutations: {counts['kept']} kept, {counts['lost']} lost, "
        f"{counts['gained']} gained, {counts['missed']} missed; "
        f"{len(not_caught)} tests in caught_by didn't fail, and {len(timed_out)} mutations with "
        "caught_by timed out."
    )
    return lines, bool(counts["lost"] or not_caught or timed_out)


def compare(before: Path, after: Path) -> int:
    """Prints what `compared` gives. Returns 1 when it fails, and 0 otherwise. When it can't read
    either file, or the two didn't run the same mutations, prints the error instead, and returns
    2."""
    try:
        lines, failed = compared(_read_results(before), _read_results(after))
    except (OSError, ValueError) as error:
        print(f"Can't compare: {error}", file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    return 1 if failed else 0


_USAGE: Final = (
    "usage: python -m tests.support.mutations run [--base] <list> <out>\n"
    "       python -m tests.support.mutations compare <before> <after>"
)


def _run(list_path: str, out: str, *, base: bool) -> int:
    try:
        if Path(out).exists():
            raise FileExistsError(f"{out} exists")
        results = run(read_list(Path(list_path)), base=base)
        with Path(out).open("x", encoding="utf-8") as file:
            file.write(results.model_dump_json(indent=2) + "\n")
    except (OSError, Refused) as error:
        print(f"Can't run the mutations: {error}", file=sys.stderr)
        return 2
    print(f"Wrote the results of {len(results.mutations)} mutations into {out}.")
    return 0


def main(argv: list[str]) -> int:
    match argv:
        case ["run", "--base", list_path, out]:
            return _run(list_path, out, base=True)
        case ["run", list_path, out]:
            return _run(list_path, out, base=False)
        case ["compare", before, after]:
            return compare(Path(before), Path(after))
        case _:
            print(_USAGE, file=sys.stderr)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
