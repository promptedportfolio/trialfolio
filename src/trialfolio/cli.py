"""The `trialfolio` command (docs/contracts.md, CLI behavior; release 0.1.0).

The CLI parses arguments, reads configuration files and the environment, presents the license
acknowledgment and the plan, injects credentials, calls the core, formats output, and maps errors
to exit codes (REQ-03). Commands:

- `trialfolio init [<dir>]` sets up a workspace: a new or empty folder, the current one by
  default, with a starter screen configuration, a README, and a `.gitignore`. It processes no
  data, so it needs no acknowledgment, and logs to the per-user log directory, so the workspace
  holds only its starter files.
- `trialfolio run <config> --out <dir> [--approve <plan-hash>]` plans and executes one screen
  backtest, once its plan is approved, in the order of steps docs/contracts.md's approval gives.
  Given an experiment's configuration, by its `kind`, it plans and executes the experiment
  instead, and run again into the experiment's directory, it resumes or revises it, with
  `--revision-reason` and `--repeat` (release 0.3.0; running an experiment). Given a ranking
  snapshot configuration, it reads the ranking system the configuration names, with one
  `rank_get`, into a ranking snapshot, once its plan is approved (release 0.4.0; ranking snapshot
  output). From release 0.4.0's R04-T12, it reads a screen's and an experiment's configuration
  1.0.0 or 1.1.0, whose ranking may be a ranking system's definition, in a file or a snapshot:
  each case's attempt then writes its definition into `ApiRankingSystem` with `rank_update`,
  before its backtest, and the run holds the ranking lock, on the file `TRIALFOLIO_LOCK_DIR`,
  `/tmp`, or `%ProgramData%` gives, which the CLI gives the core (sending a definition, the
  ranking lock).
- `trialfolio report <run-dir> --out <dir>` re-renders a saved run's report offline.
- `trialfolio demo --out <dir>` writes a synthetic example run offline, labeled synthetic.
- `trialfolio review <config> --out <dir>` compares saved runs with a baseline offline, as a
  review configuration names them (release 0.2.0).
- `trialfolio license [--accept]` prints the license, the full notice, and the acknowledgment
  status; `--accept` records the acknowledgment.
- `trialfolio --version` and `--help`, which, with `init` and `license`, need no acknowledgment.

stdout carries the result: a short summary, or, with `--json`, exactly one JSON summary, on
success and on failure. stderr carries progress, warnings, and errors, and the plan display and
prompts, which are never logged. `TrialFolioError` codes map to exit codes through `EXIT_CODES`;
an unexpected exception is `internal.unexpected`, exit 1, and its message names the log file
and, once `run` or `demo` has claimed its output directory, says what the run's records say about
the request and the manifest, as an interrupt's does, and once `review` has, that the review has
no manifest.

`run` and `demo` import the modules that import `p123api`, `requests`, or `urllib3` only once
`installed_versions` has checked and imported them, so a missing or broken one is
`environment.unsupported`, never an `ImportError`. `report` sends nothing, so it checks no
versions, but it reads runs with modules that import them: an `ImportError` there is
`environment.unsupported` too, as it is for `review`.
"""

import argparse
import importlib.metadata
import json
import logging
import os
import re
import sys
import time
import traceback
import uuid
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NoReturn, TextIO, cast

from pydantic import TypeAdapter, ValidationError

from trialfolio import acknowledgment
from trialfolio.approval import obtain_approval
from trialfolio.configuration import (
    ExperimentConfigurationRead,
    ScreenConfigurationRead,
    read_review_configuration,
    read_run_configuration,
    read_screen_configuration,
)
from trialfolio.contracts.attempt import Exchange
from trialfolio.contracts.common import (
    LABEL_PATTERN,
    AttemptId,
    ErrorDetail,
    RevisionReason,
)
from trialfolio.contracts.experiment_configuration import (
    ExperimentConfiguration,
    ExperimentConfigurationV1_1,
    configured_variants,
    configured_variants_v1_1,
)
from trialfolio.contracts.experiment_manifest import (
    ExperimentCommandRecord,
    ExperimentManifestCounts,
)
from trialfolio.contracts.experiment_plan import PlanV1_1, PlanV1_3
from trialfolio.contracts.manifest import CommandRecord
from trialfolio.contracts.plan import Plan, PlanV1_2
from trialfolio.contracts.ranking_snapshot import RankingSnapshotPlan, SnapshotCommandRecord
from trialfolio.contracts.ranking_snapshot_configuration import RankingSnapshotConfiguration
from trialfolio.contracts.review_manifest import ReviewCommandRecord
from trialfolio.contracts.summary import (
    ExperimentCounts,
    JsonSummaryV1_2,
    NoCounts,
    ReviewCounts,
    RunCounts,
    SummaryCase,
    SummaryIdsV1_2,
)
from trialfolio.display import visible
from trialfolio.errors import EXIT_CODES, TrialFolioError, interrupted, reason_of
from trialfolio.logs import LOGS_DIRECTORY, CommandLogs
from trialfolio.notices import CONCISE_NOTICE, FULL_NOTICE, LICENSE_ID, LICENSE_NAME, NOTICE_VERSION
from trialfolio.paths import existing_path
from trialfolio.planning import build_plan, build_plan_v1_1, build_snapshot_plan, installed_versions
from trialfolio.ranking_lock import ranking_lock_path
from trialfolio.starter import CONFIGURATION, starter_files
from trialfolio.storage import LOCK_PATH, ArtifactStore, LocalArtifactStore

if TYPE_CHECKING:
    from trialfolio.case_state import CaseOutcome
    from trialfolio.execution import Execution
    from trialfolio.experiment_approval import ExperimentRun
    from trialfolio.experiment_execution import ExperimentExecution
    from trialfolio.experiment_records import SavedExperiment
    from trialfolio.provider import Credentials, P123ScreenBacktestClient, ScreenBacktestClient
    from trialfolio.review import Review
    from trialfolio.snapshot_execution import SnapshotExecution
    from trialfolio.snapshots import SnapshotFiles

_logger = logging.getLogger(__name__)

type Clock = Callable[[], datetime]
"""Gives the current time in UTC. Tests inject a fixed one."""

type StoreFactory = Callable[[str], ArtifactStore]
"""Makes the `ArtifactStore` of an output directory, from the path given on the command line."""

type CommandName = Literal["init", "run", "report", "demo", "review", "license"]

API_ID_VARIABLE: Final = "TRIALFOLIO_P123_API_ID"
API_KEY_VARIABLE: Final = "TRIALFOLIO_P123_API_KEY"
KEY_LOG_VARIABLE: Final = "SSLKEYLOGFILE"
"""`urllib3` writes TLS session keys to the file it names, so the CLI removes it (credentials)."""

SUMMARY_SCHEMA_VERSION: Final = "1.2.0"


def utc_now() -> datetime:
    """The current time in UTC: the clock the installed command uses."""
    return datetime.now(UTC)


def main(
    argv: Sequence[str] | None = None,
    *,
    endpoint: str | None = None,
    timeout: int | None = None,
    clock: Clock = utc_now,
    store_factory: StoreFactory = LocalArtifactStore,
) -> int:
    """Runs one `trialfolio` command, and returns its exit code.

    `argv` is the arguments after the program's name; `sys.argv[1:]` when None. The keyword
    parameters are for tests only (docs/contracts.md, credentials), and the installed command
    never passes them: `endpoint`, Portfolio123's API in its place, which the fake server takes;
    `timeout`, the request's timeout in whole seconds, instead of 300; `clock`, for the records'
    and manifest's times; and `store_factory`, which makes the output directory's store.
    Standard input, output, and error are `sys.stdin`, `sys.stdout`, and `sys.stderr` as they are
    when it's called.
    """
    version = importlib.metadata.version("trialfolio")
    try:
        args = _parser(version).parse_args(argv)
    except SystemExit as stop:  # --help, --version, or a usage error, which argparse reported.
        return stop.code if isinstance(stop.code, int) else 2
    invocation = _Invocation(
        name=args.command,
        args=args,
        version=version,
        environ=os.environ,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        endpoint=endpoint,
        timeout=timeout,
        clock=clock,
        store_factory=store_factory,
    )
    with CommandLogs(version, os.environ, invocation.stderr) as logs:
        invocation.logs = logs
        return invocation.execute()


def run_installed() -> NoReturn:
    """The installed `trialfolio` command."""
    sys.exit(main())


# Arguments


def _parser(version: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trialfolio",
        description=(
            "Plan, run, and record Portfolio123 screen backtests, keeping each run's settings with"
            " its results, run experiments of a screen's variants, and compare saved runs with a"
            " baseline."
        ),
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"trialfolio {version}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def command(name: str, summary: str) -> argparse.ArgumentParser:
        return commands.add_parser(name, help=summary, description=summary, allow_abbrev=False)

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
    _json(init)

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
    _json(run)

    report = command("report", "Re-render a saved run's report offline.")
    report.add_argument("run_dir", metavar="run-dir", help="the saved run's output directory")
    _out(report, "the new output directory for the report")
    _json(report)

    demo = command(
        "demo",
        "Write a synthetic example run offline, labeled synthetic, with its report.",
    )
    _out(demo, "the new output directory for the synthetic run")
    _json(demo)

    review = command("review", "Compare saved runs with a baseline offline.")
    review.add_argument(
        "config", help="the review configuration, a YAML file naming the runs and the baseline"
    )
    _out(review, "the new output directory for the review")
    _json(review)

    license_ = command(
        "license",
        "Print the license, the full notice, and whether you've acknowledged them.",
    )
    license_.add_argument(
        "--accept",
        action="store_true",
        help=f"record your acknowledgment of {LICENSE_ID} and notice version {NOTICE_VERSION}",
    )
    _json(license_)
    return parser


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


def _json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json", action="store_true", help="write the result to stdout as one JSON summary"
    )


# One invocation


@dataclass
class _Experiment:
    """What `run` has done so far with an experiment's configuration, for its summary."""

    configuration: ExperimentConfiguration | ExperimentConfigurationV1_1
    resume: bool = False
    """Whether the output directory holds the experiment, which the run resumes or revises."""
    experiment: "SavedExperiment | None" = None
    """The experiment's records, once a resume has read and checked them, and found them this
    configuration's experiment's, and not synthetic (running an experiment, step 4)."""
    plan: PlanV1_1 | PlanV1_3 | None = None
    """The plan this run builds, once it's built: the current plan, or its revision."""
    run: "ExperimentRun | None" = None
    execution: "ExperimentExecution | None" = None

    @property
    def counts_known(self) -> bool:
        """Whether the experiment's counts are known: once a new experiment's configuration is
        valid, and once a resumed experiment's records are read and checked."""
        return not self.resume or self.experiment is not None


@dataclass
class _Invocation:
    """One command: its arguments, its context, and what it has done so far, for its summary."""

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
    logs: CommandLogs | None = None
    ids: SummaryIdsV1_2 = field(default_factory=lambda: SummaryIdsV1_2())
    output_dir: str | None = None
    """The output directory as given, once the command has claimed it."""
    execution: "Execution | None" = None
    snapshot: "SnapshotExecution | None" = None
    """A ranking snapshot's execution, once `run` of a snapshot configuration has one."""
    report: str | None = None
    """`report.html`, once `trialfolio report` has written it."""
    review: "Review | None" = None
    experiment: _Experiment | None = None
    lock_holder: ArtifactStore | None = None
    """The store that holds an experiment's lock, which the command closes once it has written
    its result, so it holds the lock until it ends."""
    results: int = 0
    """The results a valid review configuration names, once it's read."""
    result: list[str] = field(default_factory=list[str])
    """The human summary, for stdout on success."""

    @property
    def log(self) -> CommandLogs:
        if self.logs is None:
            raise RuntimeError("the command's logs aren't set up")
        return self.logs

    def execute(self) -> int:
        """Runs the command, and writes its result and any error. Returns the exit code."""
        started = time.monotonic()
        _logger.info(
            "Started trialfolio %s.", self.name, extra=_event("cli.command.started", False)
        )
        error: TrialFolioError | None
        try:
            error = _COMMANDS[self.name](self)
        except TrialFolioError as failure:
            error = failure
        except KeyboardInterrupt:
            error = self._interrupted()
        except Exception as failure:  # noqa: BLE001 - a defect, reported as one.
            error = self._unexpected(failure)
        if error is not None and error.code == "internal.unexpected":
            # Before the claim, the held events go to the per-user log directory.
            path = self.log.path or self.log.attach_to_user_directory()
            where = (
                "Its log couldn't be written." if path is None else f"Its log is {_shown(path)}."
            )
            error = error.with_detail(where)
        exit_code = 0 if error is None else EXIT_CODES[error.code]
        detail = "no error" if error is None else f"{error.code}: {error.log_message}"
        _logger.log(
            logging.INFO if error is None else logging.ERROR,
            "trialfolio %s ended after %.3f s with exit code %d: %s",
            self.name,
            time.monotonic() - started,
            exit_code,
            # A message ends with its own period.
            detail if detail.endswith(".") else f"{detail}.",
            extra={**_event("cli.command.completed", False), **self._linked_ids()},
        )
        try:
            self._write_result(error, exit_code)
        finally:
            # An experiment's lock is held until the command ends, its summary written.
            if self.lock_holder is not None:
                self.lock_holder.close()
        return exit_code

    def _write_result(self, error: TrialFolioError | None, exit_code: int) -> None:
        # Built before writing, so that a summary that fails validation, a defect, is never
        # taken for a closed stream and silently left out.
        if self.args.json:
            result = json.dumps(self._summary(error, exit_code).model_dump(mode="json")) + "\n"
        else:
            result = "".join(f"{line}\n" for line in self.result) if error is None else ""
        try:
            if error is not None:
                self.stderr.write(f"Error ({error.code}): {error.message}\n")
                # `--out` as given, escaped as an error message escapes a path, so it can't act
                # on the terminal; the summary's `output_dir` keeps it as given.
                output_dir = self._output_dir()
                if self.experiment is not None and output_dir is not None:
                    self.stderr.write(f"The experiment's records are in {_shown(output_dir)}.\n")
                elif self.output_dir is not None and self.snapshot is not None:
                    self.stderr.write(f"The snapshot's records are in {_shown(self.output_dir)}.\n")
                elif self.output_dir is not None and self.name in ("run", "demo"):
                    self.stderr.write(f"The run's records are in {_shown(self.output_dir)}.\n")
                self.stderr.flush()
            self.stdout.write(result)
            self.stdout.flush()
        except (OSError, ValueError):  # A closed stream: nothing more can be shown.
            pass

    def _summary(self, error: TrialFolioError | None, exit_code: int) -> JsonSummaryV1_2:
        outcome = (
            "completed"
            if error is None
            else "partial"
            if error.code == "execution.partial"
            else "failed"
        )
        cases = self._cases()
        return JsonSummaryV1_2.model_validate(
            {
                "schema_version": SUMMARY_SCHEMA_VERSION,
                "command": self.name,
                "trialfolio_version": self.version,
                "outcome": outcome,
                "exit_code": exit_code,
                "ids": self._ids(),
                "output_dir": self._output_dir(),
                "outputs": self._outputs(),
                **({} if cases is None else {"cases": cases}),
                "counts": self._counts(error),
                "statistical_validation": "not_assessed",
                "trading_readiness": "not_assessed",
                "error": None
                if error is None
                else ErrorDetail(code=error.code, message=error.message),
            }
        )

    def _output_dir(self) -> str | None:
        """`output_dir`, or a review's once it has claimed its directory. A review's claim is
        read from the review, as its `review_id` is, so the summary gives both even when an
        interrupt stops the review before `claimed` has run. A resumed experiment's is given
        once its session record is written: the command writes nothing into it before."""
        if self.review is not None and self.review.claimed:
            return self.args.out
        experiment = self.experiment
        if experiment is not None and experiment.resume:
            execution = experiment.execution
            return None if execution is None or execution.session is None else self.args.out
        return self.output_dir

    def _ids(self) -> SummaryIdsV1_2:
        ids = SummaryIdsV1_2(**self.ids)
        if self.review is not None and self.review.claimed:
            ids["review_id"] = self.review.review_id
        experiment = self.experiment
        execution = None if experiment is None else experiment.execution
        if execution is not None and execution.session is not None:
            ids["session"] = execution.session
        ran = self._ran()
        attempt = None if ran is None else ran.attempt
        result = None if ran is None else ran.result
        if attempt is not None and (
            _start_records(attempt) or (result is not None and result.recorded)
        ):
            ids["attempt_id"] = attempt.attempt_id
        return ids

    def _outputs(self) -> dict[str, str]:  # noqa: C901 - RF-T08 shortens it.
        if self._output_dir() is None:
            return {}
        if self.name == "init":
            return {"configuration": CONFIGURATION}
        if self.report is not None:
            return {"report": self.report}
        outputs: dict[str, str] = {}
        if self.review is not None:
            for role, stored in (
                ("manifest", self.review.manifest),
                ("report", self.review.report),
                ("differences", self.review.differences_file),
            ):
                if stored is not None:
                    outputs[role] = stored.path
            return outputs
        if self.experiment is not None:
            ran = self.experiment.execution
            if ran is not None and ran.manifest is not None:
                outputs["manifest"] = _session_file(ran.manifest.session, "manifest.json")
            if ran is not None and ran.report is not None:
                outputs["report"] = ran.report.path
            return outputs
        if self.snapshot is not None and self.snapshot.manifest is not None:
            return {"manifest": self.snapshot.manifest.path}
        execution = self.execution
        if execution is None:
            return outputs
        if execution.manifest is not None:
            outputs["manifest"] = execution.manifest.path
        if execution.report is not None:
            outputs["report"] = execution.report.path
        if execution.tables is not None:
            outputs["metrics"] = execution.tables.metrics.path
            outputs["settings"] = execution.tables.settings.path
        return outputs

    def _counts(
        self, error: TrialFolioError | None
    ) -> RunCounts | ReviewCounts | ExperimentCounts | NoCounts:
        if self.experiment is not None:
            return self._experiment_counts(error)
        if self.name == "review":
            differences = None if self.review is None else self.review.differences
            return ReviewCounts(
                results=self.results,
                settings_flagged=0 if differences is None else differences.setting_counts.flagged,
                metrics_unavailable=(
                    0 if differences is None else differences.metric_counts.unavailable
                ),
                warnings=self.log.warnings,
            )
        if self.name not in ("run", "demo"):
            return NoCounts()
        attempts = sent = unavailable = 0
        cost: int | None = None
        ran = self._ran()
        if ran is not None and ran.attempt is not None:
            from trialfolio.attempts import provider_requests, reported_cost

            result = ran.result
            if result is not None and result.recorded:
                attempts, sent = 1, provider_requests(result.record)
                # Each rank_update's cost too, for a run with a ranking definition.
                cost = reported_cost(result.record)
            elif _start_records(ran.attempt):
                # It reads as running: one possible send for each start record it wrote, its
                # update record and its start record (uncertain completion, counting the
                # requests).
                attempts, sent = 1, _start_records(ran.attempt)
        if self.execution is not None and self.execution.tables is not None:
            unavailable = self.execution.tables.metrics_unavailable
        return RunCounts(
            attempts=attempts,
            provider_requests=sent,
            metrics_unavailable=unavailable,
            warnings=self.log.warnings,
            cost=cost,
        )

    def _cases(self) -> tuple[SummaryCase, ...] | None:
        """An experiment's `cases`, once its plan is built: each case of the plan this run
        builds, with its outcome as the records give it, as the command leaves them, and the
        attempt that confirms a repeat of a case awaiting one."""
        experiment = self.experiment
        plan = None if experiment is None else experiment.plan
        if experiment is None or plan is None:
            return None
        execution, run = experiment.execution, experiment.run
        outcomes: dict[str, CaseOutcome]
        if execution is not None:
            outcomes = {case.case_id: outcome for case, outcome in execution.outcomes}
            repeats = execution.repeat_attempts
        elif run is not None:
            outcomes = {saved.case.case_id: saved.outcome for saved in run.cases}
            repeats = {
                saved.case.case_id: attempt.attempt_id for saved, attempt in run.awaiting_repeat()
            }
        else:  # Built, and not yet approved: no record read gives it an attempt.
            outcomes, repeats = {}, {}
        return tuple(
            SummaryCase(
                case_key=case.case_key,
                case_id=case.case_id,
                outcome=outcomes.get(case.case_id, "not_yet_run"),
                repeat_attempt_id=repeats.get(case.case_id),
            )
            for case in plan.cases
        )

    def _experiment_counts(self, error: TrialFolioError | None) -> ExperimentCounts | NoCounts:
        """An experiment's counts, as its manifest counts them: the session's manifest's, once
        it's written, and otherwise as the records give them, over the plan this run builds, or
        the current plan before it's built. `{}` until they're known, and after
        `experiment.locked`, whose run read nothing."""
        experiment = self.experiment
        if experiment is None:
            raise RuntimeError("the counts of an experiment's run")
        if not experiment.counts_known or (error is not None and error.code == "experiment.locked"):
            return NoCounts()
        warnings = self.log.warnings
        execution = experiment.execution
        if execution is not None:
            return _flattened(execution.counts, execution.metrics_unavailable, warnings)
        saved = experiment.experiment
        if saved is None:  # a new experiment's, before anything is sent
            plan = experiment.plan
            configuration = experiment.configuration
            variants = (
                configured_variants_v1_1(configuration)
                if isinstance(configuration, ExperimentConfigurationV1_1)
                else configured_variants(configuration)
            )
            planned = len(plan.cases) if plan is not None else len(variants) + 1
            return ExperimentCounts(
                cases_planned=planned,
                cases_succeeded=0,
                cases_failed=0,
                cases_skipped=0,
                cases_unknown=0,
                cases_not_yet_run=planned,
                cases_retired=0,
                attempts=0,
                repeats=0,
                provider_requests=0,
                authentication_calls=0,
                cost=None,
                metrics_unavailable=0,
                warnings=warnings,
            )
        plan = saved.current.plan if experiment.plan is None else experiment.plan
        return _flattened(saved.counts(plan), saved.metrics_unavailable(plan), warnings)

    def _ran(self) -> "Execution | SnapshotExecution | None":
        """A screen run's execution, or a snapshot's, once `run` or `demo` has one."""
        return self.execution if self.execution is not None else self.snapshot

    def _linked_ids(self) -> dict[str, str]:
        ids = self._ids()
        return {name: str(value) for name, value in ids.items()}

    def _interrupted(self) -> TrialFolioError:
        """`command.interrupted` for an interrupt the command didn't record itself: before the
        claim, or a second one while the attempt ended."""
        return interrupted(
            self._execution_detail() or "Nothing was sent, and no output was created."
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
            extra={**_event("cli.command.unexpected", False), **self._linked_ids()},
        )
        detail = self._execution_detail()
        return TrialFolioError(
            "internal.unexpected",
            f"Trial Folio failed unexpectedly ({type(failure).__name__})."
            f"{'' if detail is None else f' {detail}'} This is a defect in Trial Folio; please"
            " report it.",
        )

    def _execution_detail(self) -> str | None:
        """What the run's records say about the request and the manifest, once `run` or `demo`
        has claimed its output directory, and whether the review has its manifest, once `review`
        has; None before."""
        if self.review is not None:
            return self.review.ending_detail() if self.review.claimed else None
        if self.experiment is not None:
            ran = self.experiment.execution
            return ran.ending_detail() if ran is not None and ran.claimed else None
        execution = self._ran()
        if execution is None or not execution.claimed:
            return None
        return execution.ending_detail()

    def claimed(self, out: str) -> None:
        """Called once the command has claimed its output directory: logs go there from now."""
        self.output_dir = out
        self.log.attach(Path(os.path.abspath(out)) / LOGS_DIRECTORY)
        _logger.info(
            "Claimed the output directory.",
            extra={**_event("cli.output.claimed", True), **self._linked_ids()},
        )

    def resuming(self, out: str) -> None:
        """Called once a resumed experiment begins writing into its output directory, which it
        holds the lock of: logs go there from now. Its summary's `output_dir` comes from its
        session record."""
        self.log.attach(Path(os.path.abspath(out)) / LOGS_DIRECTORY)


def _start_records(attempt: object) -> int:
    """How many start records a screen run's, or a snapshot's, attempt has written: its update
    record, before a definition's `rank_update`, and its start record, before its request. An
    attempt without its attempt record counts one possible send for each (counting the
    requests)."""
    written = (getattr(attempt, "update_record", None), getattr(attempt, "start_record", None))
    return sum(record is not None for record in written)


def _event(name: str, terminal: bool) -> dict[str, object]:
    """A log event's name, and whether stderr shows it."""
    return {"event": name, "terminal": terminal}


def _flattened(
    counts: ExperimentManifestCounts, metrics_unavailable: int, warnings: int
) -> ExperimentCounts:
    """The JSON summary's counts of an experiment, from the counts its manifest gives, as the
    core counts them, the `unavailable` rows of its planned cases' `metrics.csv`, and the
    warnings this command logged."""
    attempts = counts.attempts
    return ExperimentCounts(
        cases_planned=counts.cases.planned,
        cases_succeeded=counts.cases.succeeded,
        cases_failed=counts.cases.failed,
        cases_skipped=counts.cases.skipped,
        cases_unknown=counts.cases.unknown,
        cases_not_yet_run=counts.cases.not_yet_run,
        cases_retired=counts.retired_cases,
        attempts=sum((attempts.succeeded, attempts.failed, attempts.unknown, attempts.running)),
        repeats=attempts.repeats,
        provider_requests=counts.provider_requests,
        authentication_calls=counts.authentication_calls,
        cost=counts.cost,
        metrics_unavailable=metrics_unavailable,
        warnings=warnings,
    )


# Commands


def _init(invocation: _Invocation) -> TrialFolioError | None:
    """Sets up a workspace. It processes no data, so it needs no acknowledgment, and its log goes
    to the per-user log directory, so the workspace holds only its starter files. When that
    directory is in the workspace, the command writes no log, so the workspace stays as it was if
    it's refused."""
    directory: str = invocation.args.dir
    invocation.log.keep_out_of(Path(directory))
    invocation.log.attach_to_user_directory()
    store = invocation.store_factory(directory)
    store.check_empty()
    (first, content), *rest = starter_files(invocation.version)
    store.claim(first, content)
    try:
        invocation.output_dir = directory
        _logger.info("Claimed the workspace.", extra=_event("cli.output.claimed", True))
        for name, data in rest:
            store.write(name, data)
    except (TrialFolioError, KeyboardInterrupt) as failure:
        # The claim succeeded, so the workspace isn't empty any more.
        left = (
            f"{_shown(directory)} holds some of the starter files: remove them, then run"
            " trialfolio init there again."
        )
        if isinstance(failure, KeyboardInterrupt):
            return interrupted(f"Nothing was sent. {left}")
        return failure.with_detail(f"Nothing was sent. {left}")
    where = "the current directory" if directory == "." else directory
    invocation.result = [
        f"Set up a workspace in {where}: {CONFIGURATION}, README.md, and .gitignore.",
        (
            f"Next, change {CONFIGURATION}. Then, from the workspace, review its plan with:"
            f" trialfolio run {CONFIGURATION} --out runs/first/"
        ),
        "README.md lists the steps.",
    ]
    return None


def _run(invocation: _Invocation) -> TrialFolioError | None:
    """Runs a screen's configuration, an experiment's, or a ranking snapshot's, by its `kind`
    (D-24, D-36)."""
    args = invocation.args
    _ignore_key_log(invocation.environ)
    _require_acknowledgment(invocation)
    started_at = _started(invocation)
    content = _read_input(args.config)
    # Release 0.4.0's readers, which read 1.0.0 or 1.1.0, and the definition file, or the
    # snapshot, a ranking names, in step 2, before the output directory is checked (R04-T12).
    configuration = read_run_configuration(content, _shown(args.config), args.config)
    if isinstance(configuration, ExperimentConfigurationRead):
        return _run_experiment(invocation, configuration, content, started_at)
    if isinstance(configuration, RankingSnapshotConfiguration):
        return _run_snapshot(invocation, configuration, content, started_at)
    store = invocation.store_factory(args.out)
    store.check_empty()
    plan = _plan(invocation, build_plan_v1_1(configuration, installed_versions()))
    snapshot = configuration.snapshot
    approval = obtain_approval(
        plan,
        args.approve,
        stdin=invocation.stdin,
        stderr=invocation.stderr,
        refused=_experiment_options(args),
        snapshot=None if snapshot is None else snapshot.record,
    )
    _logger.info(
        "Plan approved (%s).",
        approval.method,
        extra={**_event("plan.approved", False), **invocation.ids},
    )
    credentials = _credentials(invocation.environ)

    from trialfolio.execution import Execution

    execution = Execution(
        plan,
        approval.plan_hash,
        approval.method,
        store,
        CommandRecord(
            name="run",
            # No path: one can name the user, and the manifest is in the output directory.
            options={"approve": args.approve, "json": args.json},
            started_at=started_at,
        ),
        clock=invocation.clock,
        ranking_lock=_ranking_lock(invocation, plan),
    )
    invocation.execution = execution
    definition, files = _definition_bytes(configuration)
    error = execution.run(
        content,
        lambda: _provider_client(invocation, credentials),
        definition=definition,
        snapshot=files,
        on_claimed=lambda: invocation.claimed(args.out),
    )
    if error is None:
        invocation.result = _run_result(args.out, plan, execution, synthetic=False)
    return error


def _ranking_lock(
    invocation: _Invocation, plan: Plan | PlanV1_2 | PlanV1_1 | PlanV1_3
) -> Path | None:
    """The ranking lock's file, which the CLI gives the core for a plan with a ranking
    definition, and only for one: `trialfolio-ranking.lock`, in `TRIALFOLIO_LOCK_DIR` when it's
    set and not empty, and otherwise in `/tmp`, or in `%ProgramData%` on Windows (the ranking
    lock). The core takes it, and gives `experiment.locked` or `storage.write_failed` when it
    can't."""
    if not isinstance(plan, PlanV1_2 | PlanV1_3):
        return None
    return ranking_lock_path(invocation.environ)


def _definition_bytes(
    read: ScreenConfigurationRead | ExperimentConfigurationRead,
) -> tuple[bytes | None, "SnapshotFiles | None"]:
    """The bytes the core copies, as `definition.xml`, and `snapshot.json` for a snapshot, beside
    the plan's `configuration.yaml`: the definition file's that the reader read in step 2, or
    the two files' of the snapshot it read; neither for a ranking given another way. They're the
    bytes the configuration was validated with, never read again (ranking definitions)."""
    if read.snapshot is not None:
        return None, read.snapshot.files
    if read.definition is not None:
        return read.definition.content, None
    return None, None


def _run_snapshot(
    invocation: _Invocation,
    configuration: RankingSnapshotConfiguration,
    content: bytes,
    started_at: datetime,
) -> TrialFolioError | None:
    """Takes a ranking snapshot, as a screen's run takes its steps (ranking snapshot output): the
    output directory must be absent or empty, since a snapshot is never resumed or added to; its
    plan, with its one `rank_get`, is shown and approved; and its execution reads the system with
    the credentials, and writes nothing to the account, so it takes no lock."""
    args = invocation.args
    store = invocation.store_factory(args.out)
    store.check_empty()
    plan = build_snapshot_plan(configuration, installed_versions())
    invocation.ids["plan_hash"] = plan.plan_hash
    _logger.info("Built the plan.", extra={**_event("plan.created", False), **invocation.ids})
    approval = obtain_approval(
        plan,
        args.approve,
        stdin=invocation.stdin,
        stderr=invocation.stderr,
        refused=_experiment_options(args, "A ranking snapshot's run"),
    )
    _logger.info(
        "Plan approved (%s).",
        approval.method,
        extra={**_event("plan.approved", False), **invocation.ids},
    )
    credentials = _credentials(invocation.environ)

    from trialfolio.snapshot_execution import SnapshotExecution

    execution = SnapshotExecution(
        plan,
        approval.plan_hash,
        approval.method,
        store,
        SnapshotCommandRecord(
            name="run",
            # No path: one can name the user, and the manifest is in the output directory.
            options={"approve": args.approve, "json": args.json},
            started_at=started_at,
        ),
        clock=invocation.clock,
    )
    invocation.snapshot = execution
    error = execution.run(
        content,
        lambda: _provider_client(invocation, credentials, snapshot=True),
        on_claimed=lambda: invocation.claimed(args.out),
    )
    if error is None:
        invocation.result = _snapshot_result(args.out, plan, execution)
    return error


def _provider_client(
    invocation: _Invocation, credentials: "Credentials", *, snapshot: bool = False
) -> "P123ScreenBacktestClient":
    """Portfolio123's client, with the credentials, and the endpoint and the timeout tests give.
    `snapshot` is for a ranking snapshot's, whose authentication's messages name its `rank_get`."""
    from trialfolio.provider import REQUEST_TIMEOUT_SECONDS, P123ScreenBacktestClient

    return P123ScreenBacktestClient(
        credentials,
        endpoint=invocation.endpoint,
        timeout=REQUEST_TIMEOUT_SECONDS if invocation.timeout is None else invocation.timeout,
        snapshot=snapshot,
    )


def _experiment_options(args: argparse.Namespace, run: str = "A screen's run") -> str | None:
    """Why a screen's run, or a ranking snapshot's, refuses `--revision-reason` or `--repeat`,
    when either is given: each applies only to an experiment that has run already. `run` names
    the run that refuses them."""
    given = [
        option
        for option, value in (
            ("--revision-reason", args.revision_reason),
            ("--repeat", args.repeat),
        )
        if value
    ]
    if not given:
        return None
    return (
        f"{' and '.join(given)} {'applies' if len(given) == 1 else 'apply'} only to an"
        f" experiment's configuration, run again into its output directory. {run} has no"
        " plan to revise, and no case to repeat. Run the command without"
        f" {'it' if len(given) == 1 else 'them'}."
    )


def _run_experiment(  # noqa: PLR0915 - RF-T08 shortens it.
    invocation: _Invocation,
    read: ExperimentConfigurationRead,
    content: bytes,
    started_at: datetime,
) -> TrialFolioError | None:
    """Plans and executes a new experiment, or resumes or revises one, in the order of steps
    docs/contracts.md's running an experiment gives. A directory that isn't empty is resumed
    when it holds `experiment.lock`, whose lock the store takes before anything else is read,
    and holds until the command ends. The installed versions are checked once it's taken, before
    the records are read, since the modules that read them import `p123api`, `requests`, and
    `urllib3`. From release 0.4.0's R04-T12, the configuration is read by 0.4.0's reader, and the
    records with `ranking`, so a plan 1.3.0, whose baseline's ranking is a definition, is planned,
    resumed, and revised too, and its execution is given the ranking lock's file."""
    args = invocation.args
    configuration = read.configuration
    invocation.ids["experiment_id"] = configuration.experiment_id
    state = _Experiment(configuration)
    invocation.experiment = state
    store = invocation.store_factory(args.out)
    invocation.lock_holder = store
    try:
        store.check_empty()
    except TrialFolioError as occupied:
        if occupied.code != "output.not_empty":
            raise
        # Its counts are unknown until its records are read, whatever stops the run first.
        state.resume = True
        try:
            store.lock(LOCK_PATH)
        except FileNotFoundError:
            # Anything else, and no experiment.lock: as for a screen.
            state.resume = False
            raise occupied from None
    versions = installed_versions()

    from trialfolio.experiment_approval import ExperimentRun, RepeatOption, approve_experiment
    from trialfolio.experiment_execution import ExperimentExecution
    from trialfolio.experiment_records import read_experiment
    from trialfolio.planning import build_experiment_plan_v1_1, plan_revision_v1_1

    changes = None
    if state.resume:
        saved = read_experiment(store, ranking=True)
        if saved.synthetic:
            raise TrialFolioError(
                "output.not_empty",
                "The output directory holds a synthetic experiment, whose values are invented,"
                " and trialfolio run doesn't resume one, so invented and real attempts never share"
                " an experiment. Nothing was sent or written. Run the configuration into another"
                " output directory.",
            )
        revision = plan_revision_v1_1(read, versions, saved.current.plan)
        # Only now are the records this experiment's: a synthetic experiment, or another
        # experiment, in the directory has counts that aren't this configuration's.
        state.experiment = saved
        plan = saved.current.plan if revision is None else revision.plan
        changes = None if revision is None else revision.changes
    else:
        saved = None
        plan = build_experiment_plan_v1_1(read, versions)
    state.plan = plan
    invocation.ids["plan_hash"] = plan.plan_hash
    _logger.info("Built the plan.", extra={**_event("plan.created", False), **invocation.ids})
    repeats = tuple(RepeatOption(key, attempt) for key, attempt in args.repeat or ())
    snapshot = None if read.snapshot is None else read.snapshot.record
    run = ExperimentRun(plan, saved, changes, args.revision_reason, repeats, snapshot)
    state.run = run
    approved = approve_experiment(
        run, args.approve, stdin=invocation.stdin, stderr=invocation.stderr
    )
    _logger.info(
        "Plan approved (%s).",
        approved.approval.method,
        extra={**_event("plan.approved", False), **invocation.ids},
    )
    client = _experiment_client(invocation, sends=approved.sends)
    execution = ExperimentExecution(
        plan,
        approved.approval.plan_hash,
        approved.approval.method,
        store,
        client,
        command=ExperimentCommandRecord(
            name="run",
            # No path: one can name the user, and the manifest is in the output directory.
            options={
                "approve": args.approve,
                "json": args.json,
                "revision_reason": args.revision_reason is not None,
                "repeat": bool(args.repeat),
            },
            started_at=started_at,
        ),
        clock=invocation.clock,
        experiment=saved,
        reason=args.revision_reason,
        repeats=approved.repeats,
        ranking_lock=_ranking_lock(invocation, plan),
    )
    state.execution = execution
    definition, files = _definition_bytes(read)
    try:
        error = execution.run(
            content,
            definition=definition,
            snapshot=files,
            on_claimed=lambda: (
                invocation.resuming(args.out) if state.resume else invocation.claimed(args.out)
            ),
        )
    finally:
        client.close()
    if error is not None and error.code == "execution.partial":
        error = _with_repeat_options(error, plan, execution.repeat_attempts)
        return _with_report(error, args.out, execution)
    if error is None:
        invocation.result = _experiment_result(args.out, plan, execution)
    return error


def _experiment_client(invocation: _Invocation, *, sends: bool) -> "ScreenBacktestClient":
    """The session's client: Portfolio123's, with the credentials, when a case is due or to be
    repeated, and otherwise one that sends nothing, so a run that sends nothing needs no
    credentials (running an experiment, step 7)."""
    if not sends:
        return _NothingToSend()
    return _provider_client(invocation, _credentials(invocation.environ))


class _NothingToSend:
    """The client of a session with no case due or to repeat, which sends nothing."""

    @property
    def authenticated(self) -> bool:
        return False

    @property
    def exchanges(self) -> tuple[Exchange, ...]:
        return ()

    def authenticate(self) -> None:
        raise RuntimeError("a session with nothing to send authenticated")

    def screen_backtest(self, params: object) -> NoReturn:
        raise RuntimeError("a session with nothing to send sent a request")

    def rank_update(self, params: object) -> NoReturn:
        raise RuntimeError("a session with nothing to send sent a request")

    def rank_get(self, name: str) -> NoReturn:
        raise RuntimeError("a session with nothing to send sent a request")

    def close(self) -> None:
        pass


def _with_repeat_options(
    error: TrialFolioError, plan: PlanV1_1 | PlanV1_3, repeat_attempts: dict[str, uuid.UUID]
) -> TrialFolioError:
    """`execution.partial`, with the exact `--repeat` option for each case awaiting a repeat."""
    awaiting = [case for case in plan.cases if case.case_id in repeat_attempts]
    if not awaiting:
        return error
    options = "; ".join(
        f"--repeat {case.case_key}:{repeat_attempts[case.case_id]}" for case in awaiting
    )
    each = "the case" if len(awaiting) == 1 else "each case"
    return TrialFolioError(
        error.code,
        f"{error.message} To repeat {each} awaiting a repeat, which may be charged again, run the"
        f" same command with its option: {options}.",
        f"{error.log_message} {len(awaiting)} of the planned cases await a repeat.",
    )


def _with_report(
    error: TrialFolioError, out: str, execution: "ExperimentExecution"
) -> TrialFolioError:
    """`execution.partial`, with where the session's report is, which gives each case's
    attempts. Its loggable message leaves the path out, as a log event's message does."""
    report = execution.report
    if report is None:
        return error
    where = _shown(os.path.join(out, report.path))
    return TrialFolioError(
        error.code,
        f"{error.message} Session {execution.session}'s report gives each case's attempts:"
        f" {where}.",
        error.log_message,
    )


def _experiment_result(
    out: str, plan: PlanV1_1 | PlanV1_3, execution: "ExperimentExecution"
) -> list[str]:
    report = execution.report
    lines = [
        f"Experiment completed: {out}",
        f"Session {execution.session}: every one of the {len(plan.cases)} planned cases succeeded.",
    ]
    if report is not None:
        lines.append(f"Report: {os.path.join(out, report.path)}")
    lines += [
        f"Plan hash: {plan.plan_hash}",
        "Statistical validation and trading readiness: not assessed.",
    ]
    return lines


def _session_file(session: int, name: str) -> str:
    return f"sessions/{session}/{name}"


def _demo(invocation: _Invocation) -> TrialFolioError | None:
    args = invocation.args
    _require_acknowledgment(invocation)
    started_at = _started(invocation)
    store = invocation.store_factory(args.out)
    store.check_empty()
    versions = installed_versions()

    from trialfolio import demo
    from trialfolio.execution import Execution

    content = demo.configuration_bytes()
    configuration = read_screen_configuration(content, demo.CONFIGURATION_NAME)
    plan = _plan(invocation, build_plan(configuration, versions))
    execution = Execution(
        plan,
        plan.plan_hash,
        "not_required",
        store,
        CommandRecord(
            name="demo",
            options={"json": args.json},
            started_at=started_at,
        ),
        clock=invocation.clock,
    )
    invocation.execution = execution
    error = execution.run(
        content,
        lambda: demo.SyntheticScreenBacktestClient(demo.response_bytes()),
        on_claimed=lambda: invocation.claimed(args.out),
    )
    if error is None:
        invocation.result = _run_result(args.out, plan, execution, synthetic=True)
    return error


def _report(invocation: _Invocation) -> TrialFolioError | None:
    args = invocation.args
    _require_acknowledgment(invocation)
    # Where the file system resolves it, as a review finds its runs.
    run_dir = existing_path(args.run_dir)
    if run_dir is None:
        raise TrialFolioError(
            "input.not_found",
            f"The run directory {_shown(args.run_dir)} doesn't exist. Give the output directory of"
            " a run that trialfolio run or trialfolio demo wrote. No output was created.",
        )

    try:
        from trialfolio.report import HtmlReportRenderer, rerender_report
    except ImportError as failure:
        raise _cant_read_runs(failure) from None

    report = rerender_report(
        LocalArtifactStore(run_dir),
        invocation.store_factory(args.out),
        HtmlReportRenderer(invocation.version),
        run_path=_run_path(run_dir, args.out),
    )
    invocation.report = report.path
    invocation.claimed(args.out)
    invocation.result = [f"Report written: {os.path.join(args.out, report.path)}"]
    return None


def _review(invocation: _Invocation) -> TrialFolioError | None:
    """Compares saved runs with a baseline, in the order of steps docs/contracts.md's review
    output gives: the configuration, each run, the output directory, and then the review's files,
    which `Review` writes."""
    args = invocation.args
    _require_acknowledgment(invocation)
    started_at = _started(invocation)
    content = _read_input(args.config)
    configuration = read_review_configuration(content, _shown(args.config))
    invocation.results = len(configuration.results)
    try:
        from trialfolio.review import Review
        from trialfolio.review_inputs import check_review_inputs, local_run_stores
    except ImportError as failure:
        raise _cant_read_runs(failure) from None

    inputs = check_review_inputs(configuration, local_run_stores(args.config))
    store = invocation.store_factory(args.out)
    store.check_empty()
    review = Review(
        configuration,
        content,
        inputs,
        store,
        # No path: one can name the user, and the manifest is in the output directory.
        ReviewCommandRecord(name="review", options={"json": args.json}, started_at=started_at),
        trialfolio_version=invocation.version,
        clock=invocation.clock,
    )
    invocation.review = review
    error = review.write(on_claimed=lambda: invocation.claimed(args.out))
    if error is None:
        invocation.result = _review_result(args.out, review)
    return error


def _license(invocation: _Invocation) -> TrialFolioError | None:
    invocation.log.attach_to_user_directory()
    path = acknowledgment.record_path(invocation.environ)
    if invocation.args.accept:
        _record_acknowledgment(invocation, path, "command", required=True)
        invocation.result = [
            (
                f"Recorded your acknowledgment of {LICENSE_ID}, notice version {NOTICE_VERSION},"
                f" in {path}."
            )
        ]
        return None
    text = _license_text()
    invocation.result = [
        text.rstrip("\n")
        if text is not None
        else f"The LICENSE file isn't in this installation. {LICENSE_NAME}, {LICENSE_ID}.",
        "",
        f"Full notice, version {NOTICE_VERSION}:",
        "",
        *(line for paragraph in FULL_NOTICE for line in (paragraph, "")),
        _acknowledgment_status(invocation.environ, path),
    ]
    return None


_COMMANDS: Final[dict[CommandName, Callable[[_Invocation], TrialFolioError | None]]] = {
    "init": _init,
    "run": _run,
    "report": _report,
    "demo": _demo,
    "review": _review,
    "license": _license,
}


# Steps


def _ignore_key_log(environ: MutableMapping[str, str]) -> None:
    """Removes `SSLKEYLOGFILE` from the process environment before any request, with a warning,
    so `urllib3` writes no TLS session keys (credentials)."""
    if environ.pop(KEY_LOG_VARIABLE, None) is not None:
        _logger.warning(
            "%s is set, so TLS session keys could be written to a file; Trial Folio ignores it,"
            " and removed it from its own environment. Your shell is unaffected.",
            KEY_LOG_VARIABLE,
            extra={"event": "cli.environment.ignored"},
        )


def _started(invocation: _Invocation) -> datetime:
    """When `run`, `demo`, or `review` started, as the manifest records it, and when it
    acquired the configuration: once the license is acknowledged, before the configuration is
    read, so a run's duration includes planning and any wait for approval."""
    return invocation.clock()


def _read_input(path: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as error:
        reason = reason_of(error)
        raise TrialFolioError(
            "input.not_found",
            f"Couldn't read the configuration file {_shown(path)}: {reason}. Check the path."
            " Nothing was sent, and no output was created.",
        ) from None


def _shown(path: str | os.PathLike[str]) -> str:
    """A path from the command line or the environment, as an error message shows it. A name in
    another encoding than UTF-8 reaches Python with lone surrogates, which the JSON summary can't
    hold, so they're written as escapes, as control characters are, which could act on a
    terminal."""
    return visible(os.fspath(path))


def _plan[P: Plan | PlanV1_2](invocation: _Invocation, plan: P) -> P:
    invocation.ids["plan_hash"] = plan.plan_hash
    invocation.ids["case_id"] = plan.cases[0].case_id
    _logger.info("Built the plan.", extra={**_event("plan.created", False), **invocation.ids})
    return plan


def _credentials(environ: MutableMapping[str, str]) -> "Credentials":
    from trialfolio.provider import Credentials

    api_id = environ.get(API_ID_VARIABLE, "")
    api_key = environ.get(API_KEY_VARIABLE, "")
    missing = [
        (name, credential)
        for name, credential, value in (
            (API_ID_VARIABLE, "API ID", api_id),
            (API_KEY_VARIABLE, "API key", api_key),
        )
        if not value.strip()
    ]
    if missing:
        names = " and ".join(name for name, _ in missing)
        credentials = " and ".join(credential for _, credential in missing)
        listed = "lists it" if len(missing) == 1 else "lists both"
        raise TrialFolioError(
            "provider.auth_failed",
            f"Portfolio123 credentials are missing: set {names} to your {credentials}."
            f" Portfolio123's website {listed} under DataMiner & API. Nothing was sent, and no"
            " output was created.",
        )
    return Credentials(api_id, api_key)


def _run_result(
    out: str, plan: Plan | PlanV1_2, execution: "Execution", *, synthetic: bool
) -> list[str]:
    report = execution.report
    lines = (
        [
            (
                f"Synthetic example run written to {out}. Nothing was sent to Portfolio123: every"
                " value is invented."
            )
        ]
        if synthetic
        else [f"Run completed: {out}"]
    )
    if report is not None:
        lines.append(f"Report: {os.path.join(out, report.path)}")
    lines += [
        f"Plan hash: {plan.plan_hash}",
        "Statistical validation and trading readiness: not assessed.",
    ]
    return lines


def _snapshot_result(
    out: str, plan: RankingSnapshotPlan, execution: "SnapshotExecution"
) -> list[str]:
    """Where the snapshot is, the name of the system it read, and whether its definition, ranking
    method, currency, and type can be a ranking, and if not, which rule each breaks. It never
    shows the definition (ranking snapshot output, the result)."""
    record = execution.record
    if record is None:  # a snapshot completes only once its record is written
        raise RuntimeError("a completed snapshot has its record")
    lines = [
        f"Ranking snapshot taken: {out}",
        f"Ranking system read: {visible(record.system.name)}",
    ]
    if execution.problems:
        lines.append(
            "It can't be a ranking: a screen's or an experiment's configuration that named it"
            " would fail, as one names a snapshot"
        )
        lines += [f"- {problem}." for problem in execution.problems]
    else:
        lines.append(
            "Its definition, ranking method, currency, and type can be a ranking: name the"
            " snapshot's directory as ranking.snapshot in a screen's or an experiment's"
            " configuration, schema version 1.1.0."
        )
    lines.append(f"Plan hash: {plan.plan_hash}")
    return lines


def _review_result(out: str, review: "Review") -> list[str]:
    differences = review.differences
    report = review.report
    lines = [f"Review completed: {out}"]
    if report is not None:
        lines.append(f"Report: {os.path.join(out, report.path)}")
    if differences is not None:
        lines.append(
            f"Flagged setting rows: {differences.setting_counts.flagged}. Unavailable metric"
            f" rows: {differences.metric_counts.unavailable}."
        )
    if review.synthetic:
        lines.append(
            "It includes synthetic results, whose values are invented, never Portfolio123's. The"
            " report names them."
        )
    lines += [
        f"Review ID: {review.review_id}",
        "Statistical validation and trading readiness: not assessed.",
    ]
    return lines


def _cant_read_runs(failure: ImportError) -> TrialFolioError:
    """`environment.unsupported` for a module that reads runs, which imports `p123api`,
    `requests`, or `urllib3`, but can't be imported."""
    missing = "a package it needs" if failure.name is None else failure.name
    return TrialFolioError(
        "environment.unsupported",
        f"Trial Folio can't read runs in this environment: {missing} can't be imported,"
        " because its files, or a package it needs, are missing or broken. No output was"
        " created. Reinstall Trial Folio, whose package pins its dependencies exactly, for"
        " example in a new virtual environment. If you run it from a copy of its repository,"
        " run uv sync there instead.",
    )


def _run_path(run_dir: str, out: str) -> str | None:
    """The run's directory relative to the report's, with `/` separators, or None when there's
    no relative path, as between two Windows drives. Both are where the file system puts them:
    `run_dir` is resolved already, and the report's directory is resolved here, so the path
    reaches the run from where the report is, and a symbolic link above both, such as macOS's
    `/tmp`, stays out of it."""
    try:
        # The store's `abspath` first, which removes the output directory's `..` as text.
        report_dir = os.path.realpath(os.path.abspath(out))
        relative = os.path.relpath(run_dir, report_dir)
    except ValueError:
        return None
    return Path(relative).as_posix()


# The license acknowledgment


def _require_acknowledgment(invocation: _Invocation) -> None:
    """Checks the license acknowledgment before the command processes any data: from
    `TRIALFOLIO_ACCEPT_LICENSE`, the record, or by asking on a terminal (license acknowledgment).
    Raises `TrialFolioError` with `license.not_acknowledged` otherwise, having written nothing."""
    by_environment = acknowledgment.environment_acknowledgment(invocation.environ)
    if by_environment is not None:
        if by_environment:
            return
        raise TrialFolioError(
            "license.not_acknowledged",
            f"{acknowledgment.ACCEPT_VARIABLE} is set, but not to the exact value that"
            f" acknowledges the current license and notice version, so it's rejected. Set it to"
            f" {acknowledgment.ACCEPT_VALUE} to acknowledge them for this process, or unset it"
            " and run trialfolio license --accept to record your acknowledgment. Read them first"
            " with trialfolio license. Nothing was written.",
        )
    path = acknowledgment.record_path(invocation.environ)
    if acknowledgment.is_current(acknowledgment.read_record(path)):
        return
    if invocation.stdin.isatty() and invocation.stderr.isatty():
        _ask_acknowledgment(invocation, path)
        return
    raise TrialFolioError(
        "license.not_acknowledged",
        f"Before Trial Folio processes any data, acknowledge its license, {LICENSE_ID}, and its"
        f" research notice, version {NOTICE_VERSION}. Read them with trialfolio license. Then"
        " run trialfolio license --accept to record your acknowledgment, or set"
        f" {acknowledgment.ACCEPT_VARIABLE}={acknowledgment.ACCEPT_VALUE} to acknowledge them for"
        " one process. Nothing was written.",
    )


def _ask_acknowledgment(invocation: _Invocation, path: Path) -> None:
    stderr = invocation.stderr
    stderr.write(
        f"{CONCISE_NOTICE}\n\n"
        f"License: {LICENSE_NAME}, {LICENSE_ID}. Notice version {NOTICE_VERSION}.\n"
        "Read the full license and notice with: trialfolio license\n\n"
        f"Type {acknowledgment.ACCEPT_ANSWER} to acknowledge them, or anything else to stop: "
    )
    stderr.flush()
    try:
        answer: str | None = invocation.stdin.readline().removesuffix("\n").removesuffix("\r")
    except UnicodeDecodeError:  # It isn't text, so it isn't accept either.
        answer = None
    if answer != acknowledgment.ACCEPT_ANSWER:
        raise TrialFolioError(
            "license.not_acknowledged",
            f"The license and notice weren't acknowledged: the answer wasn't"
            f" {acknowledgment.ACCEPT_ANSWER}. Nothing was written.",
        )
    _record_acknowledgment(invocation, path, "interactive", required=False)


def _record_acknowledgment(
    invocation: _Invocation,
    path: Path,
    method: Literal["interactive", "command"],
    *,
    required: bool,
) -> None:
    """Records the acknowledgment. When it can't be written, `trialfolio license --accept` fails,
    and an interactive acknowledgment carries on for this run, with a warning."""
    try:
        acknowledgment.write_record(path, method, invocation.clock())
    except OSError as error:
        reason = reason_of(error)
        if required:
            raise TrialFolioError(
                "storage.write_failed",
                f"Couldn't record your acknowledgment in {_shown(path)}: {reason}. Check the"
                f" directory's permissions, or set {acknowledgment.ACCEPT_VARIABLE} instead.",
            ) from None
        _logger.warning(
            "Couldn't record your acknowledgment in %s (%s), so Trial Folio will ask again next"
            " time. It counts for this run.",
            path,
            reason,
            extra={"event": "license.record.failed"},
        )
        return
    _logger.info(
        "Recorded the acknowledgment of %s, notice version %s (%s).",
        LICENSE_ID,
        NOTICE_VERSION,
        method,
        extra=_event("license.acknowledged", False),
    )


def _acknowledgment_status(environ: MutableMapping[str, str], path: Path) -> str:
    by_environment = acknowledgment.environment_acknowledgment(environ)
    if by_environment:
        return (
            f"Acknowledged for this process: {acknowledgment.ACCEPT_VARIABLE} is"
            f" {acknowledgment.ACCEPT_VALUE}."
        )
    record = acknowledgment.read_record(path)
    if acknowledgment.is_current(record) and record is not None:
        status = (
            f"Acknowledged on {record.acknowledged_at.isoformat().replace('+00:00', 'Z')}"
            f" ({record.method}), recorded in {path}."
        )
    else:
        status = (
            f"Not acknowledged. Run trialfolio license --accept to record your acknowledgment,"
            f" or set {acknowledgment.ACCEPT_VARIABLE}={acknowledgment.ACCEPT_VALUE} to"
            " acknowledge them for one process."
        )
    if by_environment is False:
        status += f" {acknowledgment.ACCEPT_VARIABLE} is set to another value, which is rejected."
    return f"Acknowledgment of {LICENSE_ID}, notice version {NOTICE_VERSION}: {status}"


def _license_text() -> str | None:
    """The LICENSE published with this installation, which the wheel carries."""
    try:
        return importlib.metadata.distribution("trialfolio").read_text("licenses/LICENSE")
    except importlib.metadata.PackageNotFoundError:
        return None
