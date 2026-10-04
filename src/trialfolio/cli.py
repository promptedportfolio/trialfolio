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
- `trialfolio report <run-dir> --out <dir>` re-renders a saved run's report offline.
- `trialfolio demo --out <dir>` writes a synthetic example run offline, labeled synthetic.
- `trialfolio license [--accept]` prints the license, the full notice, and the acknowledgment
  status; `--accept` records the acknowledgment.
- `trialfolio --version` and `--help`, which, with `init` and `license`, need no acknowledgment.

stdout carries the result: a short summary, or, with `--json`, exactly one JSON summary, on
success and on failure. stderr carries progress, warnings, and errors, and the plan display and
prompts, which are never logged. `TrialFolioError` codes map to exit codes through `EXIT_CODES`;
an unexpected exception is `internal.unexpected`, exit 1, and its message names the log file
and, once `run` or `demo` has claimed its output directory, says what the run's records say about
the request and the manifest, as an interrupt's does.

`run` and `demo` import the modules that import `p123api`, `requests`, or `urllib3` only once
`installed_versions` has checked and imported them, so a missing or broken one is
`environment.unsupported`, never an `ImportError`. `report` sends nothing, so it checks no
versions, but it reads runs with modules that import them: an `ImportError` there is
`environment.unsupported` too.
"""

import argparse
import importlib.metadata
import json
import logging
import os
import sys
import time
import traceback
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, NoReturn, TextIO

from trialfolio import acknowledgment
from trialfolio.approval import obtain_approval
from trialfolio.configuration import read_screen_configuration
from trialfolio.contracts.common import ErrorDetail
from trialfolio.contracts.manifest import CommandRecord
from trialfolio.contracts.plan import Plan
from trialfolio.contracts.summary import JsonSummary, NoCounts, RunCounts, SummaryIds
from trialfolio.display import visible
from trialfolio.errors import EXIT_CODES, TrialFolioError
from trialfolio.logs import LOGS_DIRECTORY, CommandLogs
from trialfolio.notices import CONCISE_NOTICE, FULL_NOTICE, LICENSE_ID, LICENSE_NAME, NOTICE_VERSION
from trialfolio.planning import build_plan, installed_versions
from trialfolio.starter import CONFIGURATION, starter_files
from trialfolio.storage import ArtifactStore, LocalArtifactStore

if TYPE_CHECKING:
    from trialfolio.execution import Execution
    from trialfolio.provider import Credentials

_logger = logging.getLogger(__name__)

type Clock = Callable[[], datetime]
"""Gives the current time in UTC. Tests inject a fixed one."""

type StoreFactory = Callable[[str], ArtifactStore]
"""Makes the `ArtifactStore` of an output directory, from the path given on the command line."""

type CommandName = Literal["init", "run", "report", "demo", "license"]

API_ID_VARIABLE: Final = "TRIALFOLIO_P123_API_ID"
API_KEY_VARIABLE: Final = "TRIALFOLIO_P123_API_KEY"
KEY_LOG_VARIABLE: Final = "SSLKEYLOGFILE"
"""`urllib3` writes TLS session keys to the file it names, so the CLI removes it (credentials)."""

SUMMARY_SCHEMA_VERSION: Final = "1.0.0"


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
            "Plan, run, and record one Portfolio123 screen backtest, and keep the relationship"
            " between its settings and its results."
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
        "Plan and execute one screen backtest, once its plan is approved.",
    )
    run.add_argument("config", help="the screen configuration, a YAML file")
    _out(run, "the new output directory for the run")
    run.add_argument(
        "--approve",
        metavar="PLAN_HASH",
        help="approve the plan with its full hash, as shown, without asking",
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


def _json(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json", action="store_true", help="write the result to stdout as one JSON summary"
    )


# One invocation


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
    ids: SummaryIds = field(default_factory=lambda: SummaryIds())
    output_dir: str | None = None
    """The output directory as given, once the command has claimed it."""
    execution: "Execution | None" = None
    report: str | None = None
    """`report.html`, once `trialfolio report` has written it."""
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
            error = TrialFolioError(
                error.code, f"{error.message} {where}", f"{error.log_message} {where}"
            )
        exit_code = 0 if error is None else EXIT_CODES[error.code]
        _logger.log(
            logging.INFO if error is None else logging.ERROR,
            "trialfolio %s ended after %.3f s with exit code %d: %s.",
            self.name,
            time.monotonic() - started,
            exit_code,
            "no error" if error is None else f"{error.code}: {error.log_message}",
            extra={**_event("cli.command.completed", False), **self._linked_ids()},
        )
        self._write_result(error, exit_code)
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
                if self.output_dir is not None and self.name in ("run", "demo"):
                    self.stderr.write(f"The run's records are in {self.output_dir}.\n")
                self.stderr.flush()
            self.stdout.write(result)
            self.stdout.flush()
        except (OSError, ValueError):  # A closed stream: nothing more can be shown.
            pass

    def _summary(self, error: TrialFolioError | None, exit_code: int) -> JsonSummary:
        outcome = (
            "completed"
            if error is None
            else "partial"
            if error.code == "execution.partial"
            else "failed"
        )
        return JsonSummary.model_validate(
            {
                "schema_version": SUMMARY_SCHEMA_VERSION,
                "command": self.name,
                "trialfolio_version": self.version,
                "outcome": outcome,
                "exit_code": exit_code,
                "ids": self._ids(),
                "output_dir": self.output_dir,
                "outputs": self._outputs(),
                "counts": self._counts(),
                "statistical_validation": "not_assessed",
                "trading_readiness": "not_assessed",
                "error": None
                if error is None
                else ErrorDetail(code=error.code, message=error.message),
            }
        )

    def _ids(self) -> SummaryIds:
        ids = SummaryIds(**self.ids)
        attempt = self.execution.attempt if self.execution is not None else None
        result = self.execution.result if self.execution is not None else None
        if attempt is not None and (
            attempt.start_record is not None or (result is not None and result.recorded)
        ):
            ids["attempt_id"] = attempt.attempt_id
        return ids

    def _outputs(self) -> dict[str, str]:
        if self.output_dir is None:
            return {}
        if self.name == "init":
            return {"configuration": CONFIGURATION}
        if self.report is not None:
            return {"report": self.report}
        outputs: dict[str, str] = {}
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

    def _counts(self) -> RunCounts | NoCounts:
        if self.name not in ("run", "demo"):
            return NoCounts()
        attempts = sent = unavailable = 0
        cost: int | None = None
        execution = self.execution
        if execution is not None and execution.attempt is not None:
            from trialfolio.attempts import provider_requests

            result = execution.result
            if result is not None and result.recorded:
                attempts, sent = 1, provider_requests(result.record)
                cost = result.record.provider_metadata.cost
            elif execution.attempt.start_record is not None:
                # It reads as running: one possible send (uncertain completion).
                attempts, sent = 1, 1
            if execution.tables is not None:
                unavailable = execution.tables.metrics_unavailable
        return RunCounts(
            attempts=attempts,
            provider_requests=sent,
            metrics_unavailable=unavailable,
            warnings=self.log.warnings,
            cost=cost,
        )

    def _linked_ids(self) -> dict[str, str]:
        ids = self._ids()
        return {name: str(value) for name, value in ids.items()}

    def _interrupted(self) -> TrialFolioError:
        """`command.interrupted` for an interrupt the command didn't record itself: before the
        claim, or a second one while the attempt ended."""
        detail = self._execution_detail() or "Nothing was sent, and no output was created."
        return TrialFolioError("command.interrupted", f"Trial Folio was interrupted. {detail}")

    def _unexpected(self, failure: Exception) -> TrialFolioError:
        """`internal.unexpected` for a defect. Its log gives the exception's type and frames,
        never its message, which could hold a value. After the claim, its message says what the
        run's records say, so a request that may have been charged is never hidden."""
        _logger.error(
            "Unexpected %s, at:\n%s",
            type(failure).__name__,
            "".join(traceback.format_tb(failure.__traceback__)),
            extra=_event("cli.command.unexpected", False),
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
        has claimed its output directory; None before."""
        execution = self.execution
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


def _event(name: str, terminal: bool) -> dict[str, object]:
    """A log event's name, and whether stderr shows it."""
    return {"event": name, "terminal": terminal}


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
            return TrialFolioError(
                "command.interrupted", f"Trial Folio was interrupted. Nothing was sent. {left}"
            )
        return TrialFolioError(
            failure.code,
            f"{failure.message} Nothing was sent. {left}",
            f"{failure.log_message} Nothing was sent. {left}",
        )
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
    args = invocation.args
    _ignore_key_log(invocation.environ)
    _require_acknowledgment(invocation)
    started_at = _started(invocation)
    content = _read_input(args.config)
    configuration = read_screen_configuration(content, _shown(args.config))
    store = invocation.store_factory(args.out)
    store.check_empty()
    plan = _plan(invocation, build_plan(configuration, installed_versions()))
    approval = obtain_approval(plan, args.approve, stdin=invocation.stdin, stderr=invocation.stderr)
    _logger.info(
        "Plan approved (%s).",
        approval.method,
        extra={**_event("plan.approved", False), **invocation.ids},
    )
    credentials = _credentials(invocation.environ)

    from trialfolio.execution import Execution
    from trialfolio.provider import P123ScreenBacktestClient

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
    )
    invocation.execution = execution
    timeout = {} if invocation.timeout is None else {"timeout": invocation.timeout}
    error = execution.run(
        content,
        lambda: P123ScreenBacktestClient(credentials, endpoint=invocation.endpoint, **timeout),
        on_claimed=lambda: invocation.claimed(args.out),
    )
    if error is None:
        invocation.result = _run_result(args.out, plan, execution, synthetic=False)
    return error


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
    if not os.path.exists(args.run_dir):
        raise TrialFolioError(
            "input.not_found",
            f"The run directory {_shown(args.run_dir)} doesn't exist. Give the output directory of"
            " a run that trialfolio run or trialfolio demo wrote. No output was created.",
        )

    try:
        from trialfolio.report import HtmlReportRenderer, rerender_report
    except ImportError as failure:
        missing = "a package it needs" if failure.name is None else failure.name
        raise TrialFolioError(
            "environment.unsupported",
            f"Trial Folio can't read runs in this environment: {missing} can't be imported,"
            " because its files, or a package it needs, are missing or broken. No output was"
            " created. Reinstall Trial Folio, whose package pins its dependencies exactly, for"
            " example in a new virtual environment.",
        ) from None

    report = rerender_report(
        LocalArtifactStore(args.run_dir),
        invocation.store_factory(args.out),
        HtmlReportRenderer(invocation.version),
        run_path=_run_path(args.run_dir, args.out),
    )
    invocation.report = report.path
    invocation.claimed(args.out)
    invocation.result = [f"Report written: {os.path.join(args.out, report.path)}"]
    return None


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
    """When `run` or `demo` started, as the manifest records it, and when it acquired the
    configuration: once the license is acknowledged, before the configuration is read, so the
    run's duration includes planning and any wait for approval."""
    return invocation.clock()


def _read_input(path: str) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as error:
        reason = error.strerror or type(error).__name__
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


def _plan(invocation: _Invocation, plan: Plan) -> Plan:
    invocation.ids["plan_hash"] = plan.plan_hash
    invocation.ids["case_id"] = plan.cases[0].case_id
    _logger.info("Built the plan.", extra={**_event("plan.created", False), **invocation.ids})
    return plan


def _credentials(environ: MutableMapping[str, str]) -> "Credentials":
    from trialfolio.provider import Credentials

    api_id = environ.get(API_ID_VARIABLE, "")
    api_key = environ.get(API_KEY_VARIABLE, "")
    missing = [
        name
        for name, value in ((API_ID_VARIABLE, api_id), (API_KEY_VARIABLE, api_key))
        if not value.strip()
    ]
    if missing:
        raise TrialFolioError(
            "provider.auth_failed",
            f"Portfolio123 credentials are missing: set {' and '.join(missing)} to your API ID"
            " and API key, which Portfolio123's website lists under DataMiner & API. Nothing was"
            " sent, and no output was created.",
        )
    return Credentials(api_id, api_key)


def _run_result(out: str, plan: Plan, execution: "Execution", *, synthetic: bool) -> list[str]:
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


def _run_path(run_dir: str, out: str) -> str | None:
    """The run's directory relative to the report's, with `/` separators, or None when there's
    no relative path, as between two Windows drives."""
    try:
        relative = os.path.relpath(os.path.abspath(run_dir), os.path.abspath(out))
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
        reason = error.strerror or type(error).__name__
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
