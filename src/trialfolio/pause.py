"""The pause between a `rank_update`'s 200 and its backtest (docs/contracts.md, sending a
definition; D-45).

Portfolio123 sometimes ranks a backtest sent right after a `rank_update` by the definition
`ApiRankingSystem` held before it, although the `rank_update` got its 200, and the system already
holds the new definition. A pause of 10 seconds after the 200 prevented it in the 0.4.0
walk-through's diagnostic, and `rank_touch` didn't. So an attempt that sends a definition waits,
once it has saved the `rank_update`'s response, until at least `UPDATE_PAUSE_SECONDS` have passed
on a monotonic clock since that 200 arrived, and only then writes its backtest's request and start
record, and sends the backtest.

`Pause` holds the two things the wait needs, the monotonic clock and the sleep, and is injected
into the core as the clock is, so tests never wait: the installed command uses `REAL_PAUSE`, and a
test gives its own. The length isn't configurable.

This module imports nothing that imports `p123api`, `requests`, or `urllib3`, so the CLI can
import it before it checks the installed versions.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

UPDATE_PAUSE_SECONDS: Final = 10
"""How many seconds, at least, pass between receiving a `rank_update`'s 200 and sending the
backtest after it."""


@dataclass(frozen=True)
class Pause:
    """A monotonic clock, in seconds, and a sleep, which waits about the seconds it's given."""

    monotonic: Callable[[], float]
    sleep: Callable[[float], None]

    def wait_from(self, received: float) -> None:
        """Waits until at least `UPDATE_PAUSE_SECONDS` have passed on the monotonic clock since
        `received`, its reading when the `rank_update`'s 200 arrived. A sleep that ends early is
        followed by another, for the time left, so the pause is never shorter."""
        while (left := UPDATE_PAUSE_SECONDS - (self.monotonic() - received)) > 0:
            self.sleep(left)


REAL_PAUSE: Final = Pause(monotonic=time.monotonic, sleep=time.sleep)
"""The pause the installed command uses."""
