"""One command: its inputs, `Context`; what it did, its outcome; and `Invocation`, which runs it,
and writes its result and any error (docs/contracts.md, CLI behavior).

stdout carries the result: a short summary, or, with `--json`, exactly one JSON summary, on
success and on failure. stderr carries progress, warnings, and errors, and the plan display and
prompts, which are never logged. `TrialFolioError` codes map to exit codes through `EXIT_CODES`;
an unexpected exception is `internal.unexpected`, exit 1, and its message names the log file
and, once `run` or `demo` has claimed its output directory, says what the run's records say about
the request and the manifest, as an interrupt's does, and once `review` has, that the review has
no manifest.

Each command's handler gives the invocation its outcome, which holds what that command did, such
as its execution, its review, or its experiment, and gives what the summary and the messages read
of it. Each outcome matches `_Outcome` structurally, without importing it. A command that only
writes files, `init`, `report`, or `license`, has a `FilesOutcome`.

Each module of the package that logs, this one among them, logs as `trialfolio.cli`, so each
event's `component` is the CLI's (docs/refactoring.md, decision 11).
"""

import argparse
import json
import logging
import os
import time
import traceback
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, TextIO

from trialfolio.cli.arguments import CommandName
from trialfolio.cli.summary import Counts, json_summary
from trialfolio.contracts.summary import JsonSummaryV1_2, NoCounts, SummaryCase, SummaryIdsV1_2
from trialfolio.display import visible
from trialfolio.errors import EXIT_CODES, TrialFolioError, interrupted
from trialfolio.logs import LOGS_DIRECTORY, CommandLogs
from trialfolio.pause import Pause
from trialfolio.storage import ArtifactStore

_logger = logging.getLogger("trialfolio.cli")

type Clock = Callable[[], datetime]
"""Gives the current time in UTC. Tests inject a fixed one."""

type StoreFactory = Callable[[str], ArtifactStore]
"""Makes the `ArtifactStore` of an output directory, from the path given on the command line."""


def utc_now() -> datetime:
    """The current time in UTC: the clock the installed command uses."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Context:
    """A command's inputs: its name and arguments, the version, the process's environment and
    standard streams, and what the entry function's keyword parameters give, for tests only."""

    name: CommandName
    args: argparse.Namespace
    version: str
    environ: MutableMapping[str, str]
    stdin: TextIO
    stdout: TextIO
    stderr: TextIO
    endpoint: str | None
    timeout: int | None
    clock: Clock
    store_factory: StoreFactory
    pause: Pause
    """The wait between a `rank_update`'s 200 and its backtest (D-45)."""


class _Outcome(Protocol):
    """What a command did, as its summary and its messages read it. Each command's outcome holds
    what that command did so far, such as its execution, review, or experiment, whatever stopped
    it."""

    def output_dir(self, claimed: str | None) -> str | None:
        """The summary's `output_dir`, given the output directory as given once the command
        claimed it, or None before."""
        ...

    def ids(self) -> SummaryIdsV1_2:
        """The IDs the command's own records add to the summary's `ids`, after the command's."""
        ...

    def outputs(self) -> dict[str, str]:
        """The summary's `outputs`, once it gives an `output_dir`."""
        ...

    def cases(self) -> tuple[SummaryCase, ...] | None:
        """The summary's `cases`, which only an experiment gives, once its plan is built."""
        ...

    def counts(self, error: TrialFolioError | None, warnings: int) -> Counts:
        """The summary's `counts`, given the command's error, or None, and the warnings it
        logged."""
        ...

    def ending_detail(self) -> str | None:
        """What the records say about the request and the manifest, once the command has claimed
        its output directory, for an interrupt's or a defect's message; None before."""
        ...

    def records(self, output_dir: str) -> str | None:
        """The sentence stderr ends a failure with, which says where the records are in
        `output_dir`, the summary's, or None."""
        ...


@dataclass
class FilesOutcome:
    """The outcome of a command that only writes files, and counts nothing: `init`, `report`, or
    `license`. `files` is the summary's `outputs`, by role, once the summary gives an
    `output_dir`."""

    files: dict[str, str] = field(default_factory=dict[str, str])

    def output_dir(self, claimed: str | None) -> str | None:
        return claimed

    def ids(self) -> SummaryIdsV1_2:
        return SummaryIdsV1_2()

    def outputs(self) -> dict[str, str]:
        return dict(self.files)

    def cases(self) -> tuple[SummaryCase, ...] | None:
        return None

    def counts(self, error: TrialFolioError | None, warnings: int) -> Counts:
        return NoCounts()

    def ending_detail(self) -> str | None:
        return None

    def records(self, output_dir: str) -> str | None:
        return None


type Command = Callable[["Invocation"], TrialFolioError | None]
"""A command's handler: it runs the command, and returns its error, or None when it succeeded."""


@dataclass
class Invocation:
    """One command: its inputs, and what it has done so far, for its summary."""

    context: Context
    logs: CommandLogs | None = None
    ids: SummaryIdsV1_2 = field(default_factory=lambda: SummaryIdsV1_2())
    output_dir: str | None = None
    """The output directory as given, once the command has claimed it."""
    outcome: _Outcome = field(default_factory=FilesOutcome)
    """What the command did so far, which its handler sets."""
    lock_holder: ArtifactStore | None = None
    """The store that holds an experiment's lock, which the command closes once it has written
    its result, so it holds the lock until it ends."""
    result: list[str] = field(default_factory=list[str])
    """The human summary, for stdout on success."""

    @property
    def log(self) -> CommandLogs:
        if self.logs is None:
            raise RuntimeError("the command's logs aren't set up")
        return self.logs

    def execute(self, command: Command) -> int:
        """Runs the command with its handler, and writes its result and any error. Returns the
        exit code."""
        started = time.monotonic()
        name = self.context.name
        _logger.info("Started trialfolio %s.", name, extra=event("cli.command.started", False))
        error: TrialFolioError | None
        try:
            error = command(self)
        except TrialFolioError as failure:
            error = failure
        except KeyboardInterrupt:
            error = self._interrupted()
        except Exception as failure:  # noqa: BLE001 - a defect, reported as one.
            error = self._unexpected(failure)
        if error is not None and error.code == "internal.unexpected":
            # Before the claim, the held events go to the per-user log directory.
            path = self.log.path or self.log.attach_to_user_directory()
            where = "Its log couldn't be written." if path is None else f"Its log is {shown(path)}."
            error = error.with_detail(where)
        exit_code = 0 if error is None else EXIT_CODES[error.code]
        detail = "no error" if error is None else f"{error.code}: {error.log_message}"
        _logger.log(
            logging.INFO if error is None else logging.ERROR,
            "trialfolio %s ended after %.3f s with exit code %d: %s",
            name,
            time.monotonic() - started,
            exit_code,
            # A message ends with its own period.
            detail if detail.endswith(".") else f"{detail}.",
            extra={**event("cli.command.completed", False), **self._linked_ids()},
        )
        try:
            self._write_result(error, exit_code)
        finally:
            # An experiment's lock is held until the command ends, its summary written.
            if self.lock_holder is not None:
                self.lock_holder.close()
        return exit_code

    def ended(
        self, error: TrialFolioError | None, result: Callable[[], list[str]]
    ) -> TrialFolioError | None:
        """How a handler ends once its command has run: it gives the command's error, or None
        when it succeeded, with the human summary that `result` then gives."""
        if error is None:
            self.result = result()
        return error

    def claimed(self, out: str) -> None:
        """Called once the command has claimed its output directory: logs go there from now."""
        self.output_dir = out
        self.log.attach(Path(os.path.abspath(out)) / LOGS_DIRECTORY)
        _logger.info(
            "Claimed the output directory.",
            extra={**event("cli.output.claimed", True), **self._linked_ids()},
        )

    def resuming(self, out: str) -> None:
        """Called once a resumed experiment begins writing into its output directory, which it
        holds the lock of: logs go there from now. Its summary's `output_dir` comes from its
        session record."""
        self.log.attach(Path(os.path.abspath(out)) / LOGS_DIRECTORY)

    def _write_result(self, error: TrialFolioError | None, exit_code: int) -> None:
        # Built before writing, so that a summary that fails validation, a defect, is never
        # taken for a closed stream and silently left out.
        context = self.context
        if context.args.json:
            summary = self._summary(error, exit_code)
            result = json.dumps(summary.model_dump(mode="json")) + "\n"
        else:
            result = "".join(f"{line}\n" for line in self.result) if error is None else ""
        try:
            if error is not None:
                context.stderr.write(f"Error ({error.code}): {error.message}\n")
                # `--out` as given, escaped as an error message escapes a path, so it can't act
                # on the terminal; the summary's `output_dir` keeps it as given.
                output_dir = self._output_dir()
                records = None if output_dir is None else self.outcome.records(output_dir)
                if records is not None:
                    context.stderr.write(f"{records}\n")
                context.stderr.flush()
            context.stdout.write(result)
            context.stdout.flush()
        except (OSError, ValueError):  # A closed stream: nothing more can be shown.
            pass

    def _summary(self, error: TrialFolioError | None, exit_code: int) -> JsonSummaryV1_2:
        cases = self.outcome.cases()
        ids = self._ids()
        output_dir = self._output_dir()
        return json_summary(
            self.context.name,
            self.context.version,
            error,
            exit_code,
            ids=ids,
            output_dir=output_dir,
            outputs={} if output_dir is None else self.outcome.outputs(),
            cases=cases,
            counts=self.outcome.counts(error, self.log.warnings),
        )

    def _output_dir(self) -> str | None:
        return self.outcome.output_dir(self.output_dir)

    def _ids(self) -> SummaryIdsV1_2:
        ids = SummaryIdsV1_2(**self.ids)
        ids.update(self.outcome.ids())
        return ids

    def _linked_ids(self) -> dict[str, str]:
        ids = self._ids()
        return {name: str(value) for name, value in ids.items()}

    def _interrupted(self) -> TrialFolioError:
        """`command.interrupted` for an interrupt the command didn't record itself: before the
        claim, or a second one while the attempt ended."""
        return interrupted(
            self.outcome.ending_detail() or "Nothing was sent, and no output was created."
        )

    def _unexpected(self, failure: Exception) -> TrialFolioError:
        """`internal.unexpected` for a defect. Its log gives the exception's type and frames,
        never its message, which could hold a value, and the IDs the command has so far, such as
        a review's `review_id` after its claim. After the claim, its message says what the run's
        records say, so a request that may have been charged is never hidden."""
        _logger.error(
            "Unexpected %s, at:\n%s",
            type(failure).__name__,
            "".join(traceback.format_tb(failure.__traceback__)),
            extra={**event("cli.command.unexpected", False), **self._linked_ids()},
        )
        detail = self.outcome.ending_detail()
        return TrialFolioError(
            "internal.unexpected",
            f"Trial Folio failed unexpectedly ({type(failure).__name__})."
            f"{'' if detail is None else f' {detail}'} This is a defect in Trial Folio; please"
            " report it.",
        )


def event(name: str, terminal: bool) -> dict[str, object]:
    """A log event's name, and whether stderr shows it."""
    return {"event": name, "terminal": terminal}


def shown(path: str | os.PathLike[str]) -> str:
    """A path from the command line or the environment, as an error message shows it. A name in
    another encoding than UTF-8 reaches Python with lone surrogates, which the JSON summary can't
    hold, so they're written as escapes, as control characters are, which could act on a
    terminal."""
    return visible(os.fspath(path))
