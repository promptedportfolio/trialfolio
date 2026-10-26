"""What an execution tells its caller as it goes, and what the caller tells it: the progress
events, and the cancellation (docs/contracts.md, progress and cancellation).

The events name each case by its `case_id`, and hold no text from the configuration.
"""

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from trialfolio.contracts.experiment_manifest import ExperimentManifestCounts


@dataclass(frozen=True)
class SessionStarted:
    """The session has reserved its number and recorded its plan, and is about to run its cases."""

    session: int
    cases: tuple[str, ...]
    """The `case_id`s it will send or repeat, in the plan's order."""


@dataclass(frozen=True)
class AttemptStarted:
    case_id: str
    attempt_id: uuid.UUID


@dataclass(frozen=True)
class AttemptEnded:
    """An attempt ended, its attempt record was written, and so were its case's tables, if it
    succeeded."""

    case_id: str
    attempt_id: uuid.UUID
    outcome: Literal["succeeded", "failed", "unknown"]
    possibly_charged: bool


@dataclass(frozen=True)
class SessionEnded:
    """The session wrote its report and its manifest, whose counts these are, so it's complete,
    whatever the callback does with this event."""

    session: int
    counts: ExperimentManifestCounts


type ProgressEvent = SessionStarted | AttemptStarted | AttemptEnded | SessionEnded

type Progress = Callable[[ProgressEvent], object]
"""Receives each progress event, in order, in the thread that runs the execution. An exception
it raises propagates from `run`, as an unexpected exception would. Raised at an event before the
session's end, it ends the session without its manifest. Raised at `SessionEnded`, which comes
once the manifest is written, it leaves the session complete, with its manifest: no record is
ever removed."""


def emit(progress: Progress | None, event: ProgressEvent) -> None:
    """Gives `event` to the caller's callback, when it gave one."""
    if progress is not None:
        progress(event)


class Cancellation:
    """A request, from any thread, that an execution stop between attempts. Execution checks it
    before each attempt starts, never during one: a send in flight finishes, and is recorded."""

    def __init__(self) -> None:
        self._requested = threading.Event()

    def cancel(self) -> None:
        self._requested.set()

    @property
    def requested(self) -> bool:
        return self._requested.is_set()
