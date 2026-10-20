"""The `trialfolio` command (docs/contracts.md, CLI behavior; release 0.1.0).

The CLI parses arguments, reads configuration files and the environment, presents the license
acknowledgment and the plan, injects credentials, calls the core, formats output, and maps errors
to exit codes (REQ-03). Commands:

- `trialfolio init [<dir>]` sets up a workspace: a new or empty folder, the current one by
  default, with a starter screen configuration, a README, and a `.gitignore`.
- `trialfolio run <config> --out <dir> [--approve <plan-hash>]` plans and executes one screen
  backtest, once its plan is approved. Given an experiment's configuration, by its `kind`, it
  plans and executes the experiment instead, and run again into the experiment's directory, it
  resumes or revises it, with `--revision-reason` and `--repeat`. Given a ranking snapshot
  configuration, it reads a ranking system into a ranking snapshot.
- `trialfolio report <run-dir> --out <dir>` re-renders a saved run's report offline.
- `trialfolio demo --out <dir>` writes a synthetic example run offline, labeled synthetic.
- `trialfolio review <config> --out <dir>` compares saved runs with a baseline offline, as a
  review configuration names them (release 0.2.0).
- `trialfolio license [--accept]` prints the license, the full notice, and the acknowledgment
  status; `--accept` records the acknowledgment.
- `trialfolio --version` and `--help`, which, with `init` and `license`, need no acknowledgment.

`run` and `demo` import the modules that import `p123api`, `requests`, or `urllib3` only once
`installed_versions` has checked and imported them, so a missing or broken one is
`environment.unsupported`, never an `ImportError`. `report` sends nothing, so it checks no
versions, but it reads runs with modules that import them: an `ImportError` there is
`environment.unsupported` too, as it is for `review`. So importing `trialfolio.cli` imports none
of the three.

The package's modules, each importing only those before it:

- `arguments`: the parser, with a function that adds each command, and the types of its options.
- `summary`: the JSON summary, built from what a command did.
- `invocation`: one command: its inputs, `Context`; what it did, its outcome; and `Invocation`,
  which runs it, and writes its result and any error.
- `license`: the license acknowledgment, and `trialfolio license`.
- `steps`: the steps the commands share, such as their opening, the credentials, and
  Portfolio123's client.
- `experiment`: `trialfolio run` of an experiment's configuration.
- `screen`: `trialfolio run`, by the configuration's kind, of a screen's configuration and a
  ranking snapshot's; and `trialfolio demo`.
- `offline`: `trialfolio report` and `trialfolio review`, which send nothing.
- `workspace`: `trialfolio init`.

Each module that logs logs as `trialfolio.cli`, so each event's `component` is the CLI's
(docs/refactoring.md, decision 11). This module holds the entry function, `main`, the installed
command, and each command's handler, by its name. Every name the rest of Trial Folio, the tests,
and scripts/ import is imported from `trialfolio.cli`, as before it was a package, among them
`_parser`, from which scripts/manual_reference.py generates the user manual's reference pages,
and `_Invocation`, whose `claimed` a test replaces.
"""

import importlib.metadata
import os
import sys
from collections.abc import Sequence
from typing import Final, NoReturn

from trialfolio.cli import license, offline, screen, workspace
from trialfolio.cli.arguments import CommandName
from trialfolio.cli.arguments import parser as _parser
from trialfolio.cli.invocation import Clock, Command, Context, StoreFactory, utc_now
from trialfolio.cli.invocation import Invocation as _Invocation
from trialfolio.cli.steps import API_ID_VARIABLE, API_KEY_VARIABLE, KEY_LOG_VARIABLE
from trialfolio.cli.summary import SUMMARY_SCHEMA_VERSION
from trialfolio.logs import CommandLogs
from trialfolio.storage import LocalArtifactStore

__all__ = [
    "API_ID_VARIABLE",
    "API_KEY_VARIABLE",
    "KEY_LOG_VARIABLE",
    "SUMMARY_SCHEMA_VERSION",
    "Clock",
    "CommandName",
    "StoreFactory",
    "main",
    "run_installed",
    "utc_now",
]

_COMMANDS: Final[dict[CommandName, Command]] = {
    "init": workspace.init,
    "run": screen.run,
    "report": offline.report,
    "demo": screen.demo,
    "review": offline.review,
    "license": license.license_,
}


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
    name: CommandName = args.command
    invocation = _Invocation(
        Context(
            name=name,
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
    )
    with CommandLogs(version, os.environ, invocation.context.stderr) as logs:
        invocation.logs = logs
        return invocation.execute(_COMMANDS[name])


def run_installed() -> NoReturn:
    """The installed `trialfolio` command."""
    sys.exit(main())
