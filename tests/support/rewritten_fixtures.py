"""The check of the reports, which RF-AC04 runs (docs/refactoring.md, the check of the reports):
writes the committed fixtures again through the real code, so that a task of the readability
refactor can write them with the code before its change and with the code after it, and compare
the two.

`write <out>` writes, into `<out>`, a new or empty directory:

- `run/`, as `trialfolio demo` wrote `runs/synthetic-run-1.0.0/`;
- `review/`, as `trialfolio review` wrote `reviews/synthetic-review-1.0.0/`, from
  `review-configs/synthetic-only.yaml`, over a copy of the committed run at the `run` path it
  gives, `runs/demo`. The configuration and the copy are in `inputs/`;
- `report/`, the committed run's report, rendered again from its records by `trialfolio report`,
  from that copy;
- `experiment/`, as the synthetic experiment's writer, `tests/support/synthetic_experiment.py`,
  wrote `experiments/synthetic-experiment-1.0.0/`, with both sessions' reports.

The commands run through the CLI's entry function, in this process, with the license acknowledged
by `TRIALFOLIO_ACCEPT_LICENSE`, and in an environment without the other variables Trial Folio
reads, apart from `HOME`, which is a temporary directory. Each fixture is written with a new fixed
clock, and with a fixed sequence of version 4 UUIDs in place of `uuid.uuid4`, which gives the
attempts' and the review's IDs. So the same code writes the same bytes, apart from the files in
`logs/`, whose timestamps come from the wall clock. The inputs sit beside the outputs, so the
paths between them, which the reports give, don't depend on where `<out>` is.

`compare <before> <after>` compares two such directories: it lists each file that's in only one,
or whose bytes differ, leaving out `logs/`, and fails when it lists any. It fails too, with the
error, and exit code 2, as for a wrong usage, when either isn't a directory, or a file or folder
under it can't be read, rather than leave out what it can't read.

For a task, write the fixtures again on its base and on its branch, each in a worktree of its own
synced with `uv sync`, on the same Python, since the manifests record the installed packages'
versions:

    uv run python -m tests.support.rewritten_fixtures write <scratch>/before    # on the base
    uv run python -m tests.support.rewritten_fixtures write <scratch>/after     # on the branch
    uv run python -m tests.support.rewritten_fixtures compare <scratch>/before <scratch>/after

RF-T01 wrote it. Its base had no copy, so it ran there from a copy of this file.
"""

import contextlib
import io
import itertools
import os
import shutil
import sys
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Final, NoReturn
from unittest import mock

FIXTURES: Final = Path(__file__).resolve().parents[1] / "fixtures"
RUN: Final = FIXTURES / "runs" / "synthetic-run-1.0.0"
"""The committed run, which `trialfolio demo` wrote, and which the review and the report read."""
REVIEW_CONFIGURATION: Final = FIXTURES / "review-configs" / "synthetic-only.yaml"
"""The configuration of the committed review, which names the run at `runs/demo`."""

WRITTEN: Final = ("run", "review", "report", "experiment")
"""The directories `write` writes, apart from `inputs/`, in the order it writes them."""

LOGS: Final = "logs"
"""The directory `compare` leaves out, wherever it is."""


@contextlib.contextmanager
def fixed_ids() -> Iterator[None]:
    """Gives version 4 UUIDs in a fixed sequence, from `00000000-0000-4000-8000-000000000001`,
    in place of `uuid.uuid4`, which Trial Folio calls through the module."""
    numbers = itertools.count(1)

    def next_id() -> uuid.UUID:
        return uuid.UUID(f"00000000-0000-4000-8000-{next(numbers):012x}")

    with mock.patch.object(uuid, "uuid4", next_id):
        yield


@contextlib.contextmanager
def _environment(home: Path) -> Iterator[None]:
    """The environment of the tests' CLI, with the license acknowledged."""
    from tests.support.environment import VARIABLES
    from trialfolio.acknowledgment import ACCEPT_VALUE, ACCEPT_VARIABLE

    saved = dict(os.environ)
    try:
        for name in VARIABLES:
            os.environ.pop(name, None)
        os.environ["HOME"] = str(home)
        os.environ[ACCEPT_VARIABLE] = ACCEPT_VALUE
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _command(*argv: str | Path) -> None:
    """Runs `trialfolio` with `argv`, a new fixed clock, and the fixed IDs, and raises
    `AssertionError`, with what it wrote, unless it succeeds."""
    from tests.support.clock import FixedClock
    from trialfolio.cli import main

    out, err = io.StringIO(), io.StringIO()
    with (
        fixed_ids(),
        mock.patch.object(sys, "stdin", io.StringIO()),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = main([str(arg) for arg in argv], clock=FixedClock())
    if code != 0:
        raise AssertionError(
            f"trialfolio {' '.join(map(str, argv))} exited with {code}:\n"
            f"{out.getvalue()}{err.getvalue()}"
        )


def write(out: Path) -> None:
    """Writes the fixtures again into `out`, a new or empty directory, as the module says."""
    from tests.support.synthetic_experiment import write_synthetic_experiment

    if out.exists() and any(out.iterdir()):
        raise ValueError(f"{out} isn't empty")
    inputs = out / "inputs"
    configuration = inputs / REVIEW_CONFIGURATION.name
    run = inputs / "runs" / "demo"
    shutil.copytree(RUN, run)
    shutil.copyfile(REVIEW_CONFIGURATION, configuration)
    with tempfile.TemporaryDirectory() as home, _environment(Path(home)):
        _command("demo", "--out", out / "run")
        _command("review", configuration, "--out", out / "review")
        _command("report", run, "--out", out / "report")
        with fixed_ids():
            write_synthetic_experiment(out / "experiment")


def _raise(error: OSError) -> NoReturn:
    raise error


def _files(directory: Path) -> dict[str, Path]:
    """Each file under `directory`, by its path relative to it, with `/` separators, leaving out
    `logs/`. Raises the `OSError` when `directory` isn't a directory, or a folder under it can't
    be read, which `os.walk` would otherwise skip."""
    files: dict[str, Path] = {}
    for root, folders, names in os.walk(directory, onerror=_raise):
        folders[:] = [folder for folder in folders if folder != LOGS]
        for name in names:
            path = Path(root, name)
            files[path.relative_to(directory).as_posix()] = path
    return files


def differences(before: Path, after: Path) -> list[str]:
    """Each file that's in only one of `before` and `after`, or whose bytes differ, leaving out
    `logs/`, in order. Raises an `OSError` when either isn't a directory, or a file or folder
    under it can't be read."""
    first, second = _files(before), _files(after)
    found: list[str] = []
    for path in sorted(first.keys() | second.keys()):
        if path not in second:
            found.append(f"only before: {path}")
        elif path not in first:
            found.append(f"only after: {path}")
        elif first[path].read_bytes() != second[path].read_bytes():
            found.append(f"differs: {path}")
    return found


def compare(before: Path, after: Path) -> int:
    """Prints each difference `differences` finds. Returns 1 when there's any, and 0 otherwise.
    When either isn't a directory, or a file or folder under it can't be read, prints the error
    instead, and returns 2."""
    try:
        found = differences(before, after)
        compared = len(_files(after))
    except OSError as error:
        print(f"Can't compare: {error}", file=sys.stderr)
        return 2
    for line in found:
        print(line)
    print(f"{compared} files compared, {len(found)} differences.")
    return 1 if found else 0


_USAGE: Final = (
    "usage: python -m tests.support.rewritten_fixtures write <out>\n"
    "       python -m tests.support.rewritten_fixtures compare <before> <after>"
)


def main(argv: list[str]) -> int:
    match argv:
        case ["write", out]:
            write(Path(out))
            print(f"Wrote {', '.join(WRITTEN)}, and their inputs, into {out}.")
            return 0
        case ["compare", before, after]:
            return compare(Path(before), Path(after))
        case _:
            print(_USAGE, file=sys.stderr)
            return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
