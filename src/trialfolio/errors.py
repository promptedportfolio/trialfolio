"""Trial Folio's typed errors and their stable codes (docs/contracts.md, errors).

The core raises `TrialFolioError`. Only the CLI turns an error into an exit code, using
`EXIT_CODES`; the JSON summary model uses the same table to check a summary's `exit_code`.
`interrupted` builds `command.interrupted`, `TrialFolioError.with_detail` adds a sentence to an
error's messages, and `reason_of` says why a file system call failed, without its path.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, Literal

ErrorCode = Literal[
    "config.invalid",
    "input.not_found",
    "input.not_a_run",
    "artifact.unknown_schema_version",
    "environment.unsupported",
    "license.not_acknowledged",
    "plan.approval_required",
    "plan.changed",
    "output.not_empty",
    "storage.write_failed",
    "experiment.locked",
    "provider.auth_failed",
    "provider.unavailable",
    "provider.quota_exceeded",
    "provider.unsupported_capability",
    "provider.request_rejected",
    "provider.response_invalid",
    "provider.outcome_unknown",
    "execution.partial",
    "command.interrupted",
    "internal.unexpected",
]

EXIT_CODES: Final[Mapping[ErrorCode, int]] = MappingProxyType(
    {
        "config.invalid": 3,
        "input.not_found": 3,
        "input.not_a_run": 3,
        "artifact.unknown_schema_version": 3,
        "environment.unsupported": 3,
        "license.not_acknowledged": 2,
        "plan.approval_required": 2,
        "plan.changed": 3,
        "output.not_empty": 4,
        "storage.write_failed": 4,
        "experiment.locked": 4,
        "provider.auth_failed": 5,
        "provider.unavailable": 5,
        "provider.quota_exceeded": 5,
        "provider.unsupported_capability": 5,
        "provider.request_rejected": 5,
        "provider.response_invalid": 5,
        "provider.outcome_unknown": 5,
        "execution.partial": 6,
        "command.interrupted": 130,
        "internal.unexpected": 1,
    }
)
"""The exit code for each error code, from docs/contracts.md's errors table."""


class TrialFolioError(Exception):
    """An error with a stable dotted code and an actionable message.

    Messages say what failed, why, and what to do next. They never include credentials, and
    configuration errors never include the offending values. `message` is for the terminal and
    the attempt record. `log_message` is safe to log: it's `message` without any text logs must
    not hold, such as Portfolio123's own message in a provider error, and `message` itself when
    there's none (docs/contracts.md, errors). It's also the error's `str()`, so a traceback is
    safe to log too.
    """

    def __init__(self, code: ErrorCode, message: str, log_message: str | None = None) -> None:
        if log_message is None:
            log_message = message
        super().__init__(log_message)
        self.code: ErrorCode = code
        self.message = message
        self.log_message = log_message

    def __reduce__(self) -> tuple[type["TrialFolioError"], tuple[ErrorCode, str, str]]:
        # Pickling and copying rebuild an exception from its arguments, which hold only the
        # loggable message here.
        return (type(self), (self.code, self.message, self.log_message))

    def with_detail(self, detail: str) -> "TrialFolioError":
        """A `TrialFolioError` with this one's code, and `detail` appended, after a space, to both
        its messages. `detail` must be safe to log. The result is never a subclass, such as a
        provider error, whose own rules would build its messages again."""
        return TrialFolioError(
            self.code, f"{self.message} {detail}", f"{self.log_message} {detail}"
        )


def interrupted(detail: str | None = None, *, after: str | None = None) -> TrialFolioError:
    """`command.interrupted`, whose message is "Trial Folio was interrupted.", or, with `after`,
    such as "the attempt ended", "Trial Folio was interrupted after the attempt ended.". `detail`,
    which says what the interrupt left, follows it after a space. It must be safe to log."""
    when = "" if after is None else f" after {after}"
    message = f"Trial Folio was interrupted{when}."
    return TrialFolioError(
        "command.interrupted", message if detail is None else f"{message} {detail}"
    )


def reason_of(error: OSError) -> str:
    """Why a file system call failed, for a message: the error's `strerror`, which never holds
    the path, as the error's text would, or its type's name when it has none."""
    return error.strerror or type(error).__name__
