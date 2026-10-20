"""The license acknowledgment, which each command that processes data requires before it does
(docs/contracts.md, license acknowledgment), and `trialfolio license`, which prints the license,
the full notice, and the acknowledgment's status, and with `--accept` records the acknowledgment.
"""

import importlib.metadata
import logging
from collections.abc import MutableMapping
from pathlib import Path
from typing import Literal

from trialfolio import acknowledgment
from trialfolio.cli.invocation import Invocation, event, shown
from trialfolio.errors import TrialFolioError, reason_of
from trialfolio.notices import CONCISE_NOTICE, FULL_NOTICE, LICENSE_ID, LICENSE_NAME, NOTICE_VERSION

_logger = logging.getLogger("trialfolio.cli")


def license_(invocation: Invocation) -> TrialFolioError | None:
    """Prints the license, the full notice, and the acknowledgment's status, or, with
    `--accept`, records the acknowledgment. Its log goes to the per-user log directory."""
    invocation.log.attach_to_user_directory()
    environ = invocation.context.environ
    path = acknowledgment.record_path(environ)
    if invocation.context.args.accept:
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
        _acknowledgment_status(environ, path),
    ]
    return None


def require_acknowledgment(invocation: Invocation) -> None:
    """Checks the license acknowledgment before the command processes any data: from
    `TRIALFOLIO_ACCEPT_LICENSE`, the record, or by asking on a terminal (license acknowledgment).
    Raises `TrialFolioError` with `license.not_acknowledged` otherwise, having written nothing."""
    context = invocation.context
    by_environment = acknowledgment.environment_acknowledgment(context.environ)
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
    path = acknowledgment.record_path(context.environ)
    if acknowledgment.is_current(acknowledgment.read_record(path)):
        return
    if context.stdin.isatty() and context.stderr.isatty():
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


def _ask_acknowledgment(invocation: Invocation, path: Path) -> None:
    stderr = invocation.context.stderr
    stderr.write(
        f"{CONCISE_NOTICE}\n\n"
        f"License: {LICENSE_NAME}, {LICENSE_ID}. Notice version {NOTICE_VERSION}.\n"
        "Read the full license and notice with: trialfolio license\n\n"
        f"Type {acknowledgment.ACCEPT_ANSWER} to acknowledge them, or anything else to stop: "
    )
    stderr.flush()
    try:
        answer: str | None = (
            invocation.context.stdin.readline().removesuffix("\n").removesuffix("\r")
        )
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
    invocation: Invocation,
    path: Path,
    method: Literal["interactive", "command"],
    *,
    required: bool,
) -> None:
    """Records the acknowledgment. When it can't be written, `trialfolio license --accept` fails,
    and an interactive acknowledgment carries on for this run, with a warning."""
    try:
        acknowledgment.write_record(path, method, invocation.context.clock())
    except OSError as error:
        reason = reason_of(error)
        if required:
            raise TrialFolioError(
                "storage.write_failed",
                f"Couldn't record your acknowledgment in {shown(path)}: {reason}. Check the"
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
        extra=event("license.acknowledged", False),
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
