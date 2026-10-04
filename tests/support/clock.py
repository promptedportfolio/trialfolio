"""The clock: the double for the time the records and the manifest hold (release 0.1.0, test
pairing). Tests inject it through the CLI's entry function, in the test process; the test
launcher installs none, so a command it runs reads the real clock.
"""

from datetime import UTC, datetime, timedelta
from typing import Final

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
