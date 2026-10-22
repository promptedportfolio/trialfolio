"""The clock: the double for the time the records and the manifest hold (release 0.1.0, test
pairing). Tests inject it through the CLI's entry function, in the test process; the test
launcher installs none, so a command it runs reads the real clock.

From D-45, `FakePause` is the double for the pause between a `rank_update`'s 200 and its
backtest, a monotonic clock and a sleep: its clock moves only when it sleeps, or when a test moves
it, so no test waits 10 seconds. Tests inject it through the CLI's entry function, or the core's
`pause`, as they do the clock, and the test launcher installs one that never waits (release 0.4.0,
test pairing).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final, Protocol

from trialfolio.pause import Pause

STARTED: Final = datetime(2026, 10, 3, 14, 0, 0, tzinfo=UTC)
"""A fixed clock's first time, unless it's given another."""


class FixedClock:
    """Fixed timestamps: `start` at the first reading, and a second later at each reading after
    it, so the records' and the manifest's times are known and in order."""

    def __init__(self, start: datetime = STARTED) -> None:
        self._next = start

    def __call__(self) -> datetime:
        now = self._next
        self._next = now + timedelta(seconds=1)
        return now


class BackwardClock:
    """A wall clock that moves backward, as when the system sets it back: `start` at the first
    reading, and a second earlier at each reading after it, so an attempt ends, by the clock,
    before it started."""

    def __init__(self, start: datetime = STARTED) -> None:
        self._next = start

    def __call__(self) -> datetime:
        now = self._next
        self._next = now - timedelta(seconds=1)
        return now


class _Server(Protocol):
    def requests(self) -> list[str]: ...


@dataclass(frozen=True)
class Slept:
    """One sleep of the pause: the seconds it was asked for, and the requests the fake server had
    received when it began, each as its method and path."""

    seconds: float
    received: tuple[str, ...]


@dataclass
class FakePause:
    """A monotonic clock, in seconds, that only `sleep` and `advance` move, and a sleep that moves
    it by the seconds asked, at once, recording each with what `server` had received then.
    `on_sleep`, when it's set, runs after each sleep is recorded, as when an interrupt or a
    cancellation arrives during the pause."""

    server: _Server | None = None
    now: float = 1000.0
    slept: list[Slept] = field(default_factory=list[Slept])
    on_sleep: Callable[[], object] | None = None
    shortfalls: list[float] = field(default_factory=list[float])
    """How much shorter than asked each of the first sleeps is, in order, as a sleep that ends
    early would be. Each later one is as long as asked."""

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        received = () if self.server is None else tuple(self.server.requests())
        self.slept.append(Slept(seconds, received))
        short = self.shortfalls.pop(0) if self.shortfalls else 0.0
        self.now += max(0.0, seconds - short)
        if self.on_sleep is not None:
            self.on_sleep()

    def advance(self, seconds: float) -> None:
        """Moves the clock, as time passing outside the pause does."""
        self.now += seconds

    @property
    def pause(self) -> Pause:
        """The pause the core takes."""
        return Pause(monotonic=self.monotonic, sleep=self.sleep)


def no_wait() -> Pause:
    """A new `FakePause`'s pause, for a test that doesn't look at its waits."""
    return FakePause().pause
