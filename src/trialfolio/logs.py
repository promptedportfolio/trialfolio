"""The CLI's logging configuration (docs/contracts.md, logging and local diagnostics; REQ-06,
INV-14).

Core modules log through `logging.getLogger(__name__)` and never configure handlers. For the
length of one command, `CommandLogs` gives the `trialfolio` logger two handlers:

- **The log file,** one JSON object per line, at INFO and above, or at the level
  `TRIALFOLIO_LOG_LEVEL` names: `DEBUG`, `INFO`, `WARNING`, or `ERROR`. Any other value is ignored,
  with a warning. Until `attach` names a directory, the events are held in memory. A command with
  an output directory attaches once it has claimed the directory, and writes into `logs/` there.
  If it stops before then, it writes no log file, except after an internal error, when its held
  events go to the per-user log directory. A command without an output directory, such as
  `trialfolio license`, attaches to the per-user log directory from the start. `trialfolio init`
  does too, but keeps the log out of its workspace: when the per-user log directory is in the
  workspace, it writes no log file.
- **The terminal,** stderr, showing progress at INFO and warnings, in human-readable form, from the
  same events. Errors are the command's to show: it writes its error with the full message, which
  can hold Portfolio123's own text, while its log event holds only the loggable message.

Logs never hold credentials, strategy definitions, formulas, configuration values, provider
payloads, results, or input file contents. That's up to what each module logs; nothing here adds
an exception's message or a traceback's local variables. Log size is bounded by rotation.
"""

import json
import logging
import logging.handlers
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final, Self, TextIO
from unicodedata import normalize

from trialfolio.userdirs import log_directory

LEVEL_VARIABLE: Final = "TRIALFOLIO_LOG_LEVEL"
LOG_FILE: Final = "trialfolio.log"
LOGS_DIRECTORY: Final = "logs"
"""The directory in an output directory that holds its logs. It's diagnostics, not evidence, so
the manifest doesn't list it."""

_LEVELS: Final = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}
_DEFAULT_LEVEL: Final = logging.INFO
_MAX_BYTES: Final = 1_000_000
_BACKUPS: Final = 3
_LINKED_IDS: Final = ("review_id", "plan_hash", "case_id", "attempt_id", "request_id", "parent_id")
"""The IDs an event carries when they apply, which link its events into a trace."""


class JsonLineFormatter(logging.Formatter):
    """Formats an event as one JSON object, with the fields logging and local diagnostics
    names. The message is the event's own: no exception text or stack is added."""

    def __init__(self, trialfolio_version: str) -> None:
        super().__init__()
        self._version = trialfolio_version

    def format(self, record: logging.LogRecord) -> str:
        moment = datetime.fromtimestamp(record.created, UTC)
        entry: dict[str, object] = {
            "timestamp": moment.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "event": getattr(record, "event", "log.message"),
            "message": record.getMessage(),
            "trialfolio_version": self._version,
            "component": record.name,
        }
        for name in _LINKED_IDS:
            value: object = getattr(record, name, None)
            if value is not None:
                entry[name] = str(value)
        return json.dumps(entry)


class _FileSink(logging.Handler):
    """Holds events until a file is attached, then writes them, and every later one, to it."""

    def __init__(self, formatter: logging.Formatter, level: int) -> None:
        super().__init__(level)
        self.setFormatter(formatter)
        self.held: list[logging.LogRecord] = []
        self.file: logging.Handler | None = None

    def emit(self, record: logging.LogRecord) -> None:
        if self.file is None:
            self.held.append(record)
        else:
            self.file.handle(record)

    def close(self) -> None:
        if self.file is not None:
            self.file.close()
        super().close()


class _Terminal(logging.Handler):
    """Shows progress and warnings on stderr, and counts the warnings."""

    def __init__(self, stream: TextIO) -> None:
        super().__init__(logging.INFO)
        self._stream = stream
        self.warnings = 0

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno == logging.WARNING:
            self.warnings += 1
        if record.levelno > logging.WARNING or not getattr(record, "terminal", True):
            return
        prefix = "Warning: " if record.levelno == logging.WARNING else ""
        try:
            self._stream.write(f"{prefix}{record.getMessage()}\n")
            self._stream.flush()
        except (OSError, ValueError):
            self.handleError(record)


class CommandLogs:
    """The `trialfolio` logger's handlers for one command, as the module says. It's a context
    manager: leaving it removes the handlers and restores the logger as it was."""

    def __init__(self, trialfolio_version: str, environ: Mapping[str, str], stderr: TextIO) -> None:
        self._environ = environ
        named = environ.get(LEVEL_VARIABLE)
        self._ignored_level = named if named is not None and named not in _LEVELS else None
        level = _LEVELS.get(named or "", _DEFAULT_LEVEL)
        self._logger = logging.getLogger("trialfolio")
        self._sink = _FileSink(JsonLineFormatter(trialfolio_version), level)
        self._terminal = _Terminal(stderr)
        self._saved: tuple[int, bool] = (self._logger.level, self._logger.propagate)
        self._workspace: Path | None = None
        self._declined = False
        """Whether `attach` refused the workspace: the command writes no log file."""
        self.path: Path | None = None
        """The log file, once one is attached."""

    @property
    def warnings(self) -> int:
        """The warnings logged so far: the JSON summary's `counts.warnings`."""
        return self._terminal.warnings

    def __enter__(self) -> Self:
        self._logger.addHandler(self._sink)
        self._logger.addHandler(self._terminal)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        if self._ignored_level is not None:
            self._logger.warning(
                "%s must be DEBUG, INFO, WARNING, or ERROR, so its value is ignored, and the log"
                " records INFO and above.",
                LEVEL_VARIABLE,
                extra={"event": "cli.environment.ignored"},
            )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._logger.removeHandler(self._sink)
        self._logger.removeHandler(self._terminal)
        self._sink.close()
        self._logger.setLevel(self._saved[0])
        self._logger.propagate = self._saved[1]

    def keep_out_of(self, workspace: Path) -> None:
        """Keeps the log file out of `workspace`, the folder `trialfolio init` sets up, which holds
        only its starter files, and which must stay as it was if the command refuses it. From
        now, attaching to `workspace`, or to a directory in it, writes no log file. The per-user
        log directory is in it when `TRIALFOLIO_LOG_DIR` names a directory there, or when the
        workspace holds the home directory's default."""
        self._workspace = workspace

    def attach(self, directory: Path) -> Path | None:
        """Starts writing the log file in `directory`, creating it if needed, with every event
        held so far. Returns the file, or None, with a warning, when it can't be opened, or when
        `directory` is in the workspace `keep_out_of` named: the command carries on without a log
        file."""
        if self._sink.file is not None or self._declined:
            return self.path
        if self._workspace is not None and _within(directory, self._workspace):
            self._logger.warning(
                "The log directory is in the workspace, which holds only the starter files, so"
                " this command writes no log.",
                extra={"event": "cli.log.unavailable"},
            )
            self._declined = True
            return None
        path = directory / LOG_FILE
        try:
            directory.mkdir(parents=True, exist_ok=True)
            file = logging.handlers.RotatingFileHandler(
                path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8"
            )
        except OSError as error:
            self._logger.warning(
                "Couldn't open a log file in %s (%s), so this command writes no log.",
                directory,
                error.strerror or type(error).__name__,
                extra={"event": "cli.log.unavailable"},
            )
            return None
        file.setFormatter(self._sink.formatter)
        held, self._sink.held = self._sink.held, []
        self._sink.file = file
        for record in held:
            file.handle(record)
        self.path = path
        return path

    def attach_to_user_directory(self) -> Path | None:
        """Attaches to the per-user log directory: for a command without an output directory,
        and for an internal error before a command claimed its own."""
        return self.attach(log_directory(self._environ))


def _within(path: Path, directory: Path) -> bool:
    """Whether `path` is `directory` or in it, where the file system puts each: `directory` as
    the output directory's claim reads a path, with `..` resolved as written, and `path` as
    creating it does, once symbolic links are resolved.

    The parts of each that exist are compared as the file system identifies them, so another
    spelling of the same folder counts: in another case, on a file system that ignores case, as
    macOS's and Windows' do by default, or in another Unicode normalization, on one that ignores
    that, as macOS's does. Names that don't exist yet are compared ignoring both, as such a file
    system would: on one that doesn't ignore them, a log directory that differs from the
    workspace only that way gets no log file either."""
    workspace = _existing(os.path.abspath(directory))
    log = _existing(os.path.realpath(path))
    if workspace is None or log is None:
        return False  # Where no part of a path exists, nothing can be created.
    _, status, unmade = workspace
    start, start_status, names = log
    if unmade:
        # The workspace doesn't exist yet: `path` is in it only if it will be made in the same
        # folder, through the same names.
        same_names = _folded(names[: len(unmade)]) == _folded(unmade)
        return same_names and os.path.samestat(start_status, status)
    return any(_is(part, status) for part in (start, *start.parents))


def _existing(path: str) -> tuple[Path, os.stat_result, tuple[str, ...]] | None:
    """`path`'s deepest part that exists, its status, and the names after it; None when no part
    of it exists."""
    whole = Path(path)
    for part in (whole, *whole.parents):
        try:
            status = os.stat(part)
        except OSError:
            continue
        return part, status, whole.parts[len(part.parts) :]
    return None


def _is(path: Path, status: os.stat_result) -> bool:
    """Whether `path` exists, and is the file `status` describes."""
    try:
        return os.path.samestat(os.stat(path), status)
    except OSError:
        return False


def _folded(names: tuple[str, ...]) -> tuple[str, ...]:
    """The names as a file system that ignores case and Unicode normalization compares them:
    Unicode's canonical caseless match."""
    return tuple(normalize("NFD", normalize("NFD", name).casefold()) for name in names)
