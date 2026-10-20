"""The `trialfolio` command's arguments: its parser, with a function that adds each command, and
the types of its options (docs/contracts.md, CLI behavior).

scripts/manual_reference.py generates the user manual's reference pages from the parser, which it
imports as `trialfolio.cli._parser` (docs/user-manual.md, UM-AC08).
"""

import argparse
import re
import uuid
from collections.abc import Callable
from typing import Final, Literal, cast

from pydantic import TypeAdapter, ValidationError

from trialfolio.contracts.common import LABEL_PATTERN, AttemptId, RevisionReason
from trialfolio.notices import LICENSE_ID, NOTICE_VERSION

type CommandName = Literal["init", "run", "report", "demo", "review", "license"]

type _Command = Callable[[str, str], argparse.ArgumentParser]
"""Adds a command to the parser, by its name and its summary, which is its help and description."""


def parser(version: str) -> argparse.ArgumentParser:
    """The parser of `trialfolio`'s arguments, with each command, in the order its help lists
    them. Every command takes `--json`, after its other arguments."""
    top = argparse.ArgumentParser(
        prog="trialfolio",
        description=(
            "Plan, run, and record Portfolio123 screen backtests, keeping each run's settings with"
            " its results, run experiments of a screen's variants, and compare saved runs with a"
            " baseline."
        ),
        allow_abbrev=False,
    )
    top.add_argument("--version", action="version", version=f"trialfolio {version}")
    commands = top.add_subparsers(dest="command", required=True, metavar="<command>")

    def command(name: str, summary: str) -> argparse.ArgumentParser:
        return commands.add_parser(name, help=summary, description=summary, allow_abbrev=False)

    for add in (_add_init, _add_run, _add_report, _add_demo, _add_review, _add_license):
        add(command).add_argument(
            "--json", action="store_true", help="write the result to stdout as one JSON summary"
        )
    return top


def _add_init(command: _Command) -> argparse.ArgumentParser:
    init = command(
        "init",
        "Set up a workspace: a folder with a starter screen configuration, a README, and a"
        " .gitignore.",
    )
    init.add_argument(
        "dir",
        nargs="?",
        default=".",
        type=_directory,
        help="the workspace: absent, or an empty directory; the current directory by default",
    )
    return init


def _add_run(command: _Command) -> argparse.ArgumentParser:
    run = command(
        "run",
        "Plan and execute a screen backtest, or an experiment, once its plan is approved. Run an"
        " experiment's configuration again into its output directory to resume or revise it. A"
        " ranking snapshot configuration reads a ranking system saved in the account into a"
        " ranking snapshot.",
    )
    run.add_argument(
        "config", help="the screen, experiment, or ranking snapshot configuration, a YAML file"
    )
    run.add_argument(
        "--out",
        required=True,
        metavar="DIR",
        type=_directory,
        help=(
            "the output directory: absent, or an empty directory, or, for an experiment, its own"
            " output directory, to resume or revise it"
        ),
    )
    run.add_argument(
        "--approve",
        metavar="PLAN_HASH",
        help="approve the plan with its full hash, as shown, without asking",
    )
    run.add_argument(
        "--revision-reason",
        metavar="TEXT",
        type=_revision_reason,
        help=(
            "why the experiment's plan changed: needed, with the revision's approval, when the"
            " configuration or the installed versions no longer give the current plan"
        ),
    )
    run.add_argument(
        "--repeat",
        metavar="CASE_KEY[:ATTEMPT_ID]",
        type=_repeat,
        action=_Repeats,
        help=(
            "send again the request of an experiment's case that may already have been charged,"
            " which may be charged again: once for each case, with the attempt ID the plan shows"
            " to confirm it, or asked to confirm in a terminal"
        ),
    )
    return run


def _add_report(command: _Command) -> argparse.ArgumentParser:
    report = command("report", "Re-render a saved run's report offline.")
    report.add_argument("run_dir", metavar="run-dir", help="the saved run's output directory")
    _out(report, "the new output directory for the report")
    return report


def _add_demo(command: _Command) -> argparse.ArgumentParser:
    demo = command(
        "demo",
        "Write a synthetic example run offline, labeled synthetic, with its report.",
    )
    _out(demo, "the new output directory for the synthetic run")
    return demo


def _add_review(command: _Command) -> argparse.ArgumentParser:
    review = command("review", "Compare saved runs with a baseline offline.")
    review.add_argument(
        "config", help="the review configuration, a YAML file naming the runs and the baseline"
    )
    _out(review, "the new output directory for the review")
    return review


def _add_license(command: _Command) -> argparse.ArgumentParser:
    license_ = command(
        "license",
        "Print the license, the full notice, and whether you've acknowledged them.",
    )
    license_.add_argument(
        "--accept",
        action="store_true",
        help=f"record your acknowledgment of {LICENSE_ID} and notice version {NOTICE_VERSION}",
    )
    return license_


def _out(parser: argparse.ArgumentParser, meaning: str) -> None:
    parser.add_argument(
        "--out",
        required=True,
        metavar="DIR",
        type=_directory,
        help=f"{meaning}: absent, or an empty directory",
    )


def _directory(value: str) -> str:
    """`--out` as given, unless it's blank or isn't valid text: a blank path names no directory
    of its own, an empty one is the current directory to the file system, and the JSON summary's
    `output_dir` can hold neither, nor a name in another encoding than UTF-8, which Python reads
    with lone surrogates."""
    if not value.strip():
        raise argparse.ArgumentTypeError("it's blank, and must name the output directory")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise argparse.ArgumentTypeError(
            "it isn't valid UTF-8 text, so the JSON summary couldn't name it; choose a name in UTF-8"
        ) from None
    return value


_REASON: Final = TypeAdapter[str](RevisionReason)
_ATTEMPT_ID: Final = TypeAdapter[uuid.UUID](AttemptId)
_CASE_KEY: Final = re.compile(LABEL_PATTERN)


def _revision_reason(value: str) -> str:
    """`--revision-reason` as given, unless it isn't a valid reason: 1 to 2,000 characters, not
    all whitespace, in valid UTF-8 text, which `experiment.json` can hold."""
    try:
        return _REASON.validate_python(value)
    except ValidationError:
        raise argparse.ArgumentTypeError(
            "it must be 1 to 2,000 characters of text, not all whitespace, in UTF-8"
        ) from None


def _repeat(value: str) -> tuple[str, uuid.UUID | None]:
    """`--repeat` as given: a case key, and the attempt ID after a colon, if there's one."""
    key, colon, attempt = value.partition(":")
    if not _CASE_KEY.fullmatch(key):
        raise argparse.ArgumentTypeError(
            "it must be a case key, such as holdings-50, or a case key, a colon, and an attempt"
            " ID, as the plan shows it"
        )
    if not colon:
        return key, None
    try:
        return key, _ATTEMPT_ID.validate_python(attempt)
    except ValidationError:
        raise argparse.ArgumentTypeError(
            "the attempt ID after the colon must be a version 4 UUID in canonical form, as the"
            " plan shows it"
        ) from None


class _Repeats(argparse.Action):
    """Collects each `--repeat`, and refuses a case key given twice, as a usage error."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        given: list[tuple[str, uuid.UUID | None]] = getattr(namespace, self.dest) or []
        key, attempt = cast("tuple[str, uuid.UUID | None]", values)
        if any(other == key for other, _ in given):
            raise argparse.ArgumentError(self, f"case {key} is given more than once")
        setattr(namespace, self.dest, [*given, (key, attempt)])
