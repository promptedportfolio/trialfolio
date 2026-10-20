"""`trialfolio init [<dir>]`, which sets up a workspace: a new or empty folder, the current one by
default, with a starter screen configuration, a README, and a `.gitignore` (docs/contracts.md,
CLI behavior; R01-T19). It processes no data, so it needs no acknowledgment, and logs to the
per-user log directory, so the workspace holds only its starter files.
"""

import logging
from pathlib import Path

from trialfolio.cli.invocation import FilesOutcome, Invocation, event, shown
from trialfolio.cli.steps import empty_store
from trialfolio.errors import TrialFolioError, interrupted
from trialfolio.starter import CONFIGURATION, starter_files

_logger = logging.getLogger("trialfolio.cli")


def init(invocation: Invocation) -> TrialFolioError | None:
    """Sets up a workspace. It processes no data, so it needs no acknowledgment, and its log goes
    to the per-user log directory, so the workspace holds only its starter files. When that
    directory is in the workspace, the command writes no log, so the workspace stays as it was if
    it's refused."""
    invocation.outcome = FilesOutcome({"configuration": CONFIGURATION})
    context = invocation.context
    directory: str = context.args.dir
    invocation.log.keep_out_of(Path(directory))
    invocation.log.attach_to_user_directory()
    store = empty_store(context, directory)
    (first, content), *rest = starter_files(context.version)
    store.claim(first, content)
    try:
        invocation.output_dir = directory
        _logger.info("Claimed the workspace.", extra=event("cli.output.claimed", True))
        for name, data in rest:
            store.write(name, data)
    except (TrialFolioError, KeyboardInterrupt) as failure:
        # The claim succeeded, so the workspace isn't empty any more.
        left = (
            f"{shown(directory)} holds some of the starter files: remove them, then run"
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
