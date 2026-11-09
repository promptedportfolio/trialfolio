"""The long response: a screen backtest response in the layout `p123api-screen-backtest`
version 1, built in memory during a test and never committed, over the demo's dates (release
0.5.0, test pairing).

Its `chart` has an entry for each of the 2,609 weekdays from 2016-01-01 to 2025-12-31, both
levels starting at 100, each later level from the one before by a step from `random.Random`, with
a fixed seed, rounded to 4 decimals; and its 131 periods of 28 days, the last shorter, as the
demo's response has, give `Ret%` and `Bench%` that reproduce from the levels, at 4 decimals, and
an `Excess%` that's their difference. Its other values, such as `turnoverPct`, `positionCnt`, and
`stats`, are invented, in the layout's types. So the checks of the series and of the reference
calculation have windows of every length, the long windows of 30 days or more among them, which no
hand-checkable fixture has, before R05-T11 writes the demo's response. It isn't a double.

R05-T06 wrote it, for R05-AC01 and R05-AC03.
"""

import json
import random
from datetime import date, timedelta
from typing import Final

START: Final = date(2016, 1, 1)
END: Final = date(2025, 12, 31)
SEED: Final = 20260105
"""The fixed seed: the same response every time."""

PERIOD_DAYS: Final = 28

COLUMNS: Final = (
    "#",
    "As Of Dt",
    "Rank Dt",
    "Tran Dt",
    "End Dt",
    "#Pos",
    "New Pos",
    "Sold Pos",
    "Turn",
    "Ret%",
    "Bench%",
    "Excess%",
    "100 USD Investment",
    "100 USD in SPY:USA",
    "Costs",
    "Cash",
    "Min % no slip",
    "Max % no slip",
    "StdDev",
)


def weekdays() -> list[date]:
    """Every weekday from `START` to `END`, both included: 2,609 of them."""
    days = (START + timedelta(n) for n in range((END - START).days + 1))
    return [day for day in days if day.weekday() < 5]


def _levels(steps: random.Random, count: int, drift: float) -> list[float]:
    levels = [100.0]
    for _ in range(count - 1):
        levels.append(round(levels[-1] * (1 + steps.gauss(drift, 0.011)), 4))
    return levels


def _period_dates() -> list[tuple[date, date]]:
    """131 periods of 28 days from `START`, the last ending at `END`, shorter."""
    periods: list[tuple[date, date]] = []
    start = START
    while start < END:
        end = min(start + timedelta(PERIOD_DAYS), END)
        periods.append((start, end))
        start = end
    return periods


def long_response() -> bytes:
    """The long response, as `response.json` saves it."""
    steps = random.Random(SEED)
    days = weekdays()
    strategy = _levels(steps, len(days), 0.0004)
    benchmark = _levels(steps, len(days), 0.0003)
    at = {day: n for n, day in enumerate(days)}
    rows: list[list[object]] = []
    for number, (start, end) in enumerate(_period_dates(), start=1):
        ret = round((strategy[at[end]] / strategy[at[start]] - 1) * 100, 4)
        bench = round((benchmark[at[end]] / benchmark[at[start]] - 1) * 100, 4)
        as_of = (start - timedelta(3)).isoformat()
        rows.append(
            [
                number,
                as_of,
                as_of,
                start.isoformat(),
                end.isoformat(),
                25,
                3,
                3,
                12.0,
                ret,
                bench,
                round(ret - bench, 4),
                strategy[at[end]],
                benchmark[at[end]],
                0.04,
                0.1,
                -4.2,
                9.3,
                2.7,
            ]
        )
    rows.reverse()
    response = {
        "cost": 5,
        "quotaRemaining": 4316,
        "stats": {
            "samples": 119,
            "correlation": 0.6112,
            "r_squared": 0.3736,
            "beta": 0.81,
            "alpha": 1.2044,
            "port": {
                "standard_dev": 17.442,
                "sharpe_ratio": 0.57,
                "sortino_ratio": 0.8213,
                "total_return": round(strategy[-1] - 100, 4),
                "annualized_return": 7.1308,
                "max_drawdown": -31.0422,
            },
            "bench": {
                "standard_dev": 16.871,
                "sharpe_ratio": 0.4917,
                "sortino_ratio": 0.7105,
                "total_return": round(benchmark[-1] - 100, 4),
                "annualized_return": 5.8219,
                "max_drawdown": -29.6033,
            },
        },
        "results": {
            "columns": list(COLUMNS),
            "rows": rows,
            "average": [None] * (len(COLUMNS) - 1),
            "upMarkets": [None] * (len(COLUMNS) - 1),
            "downMarkets": [None] * (len(COLUMNS) - 1),
        },
        "chart": {
            "dates": [day.isoformat() for day in days],
            "screenReturns": strategy,
            "benchReturns": benchmark,
            "turnoverPct": [100.0] + [0.0] * (len(days) - 1),
            "positionCnt": [25.0] * len(days),
        },
    }
    return json.dumps(response, indent=2).encode("utf-8")
