"""Write the synthetic responses that show each of `check_series.py`'s checks can fail (R05-T01).

Each is a screen-backtest response, in a folder of its own with the request beside it, as
`check_series.py --fixtures` reads it. None is derived from a saved response. The levels run in
equal steps, rounded to 4 decimals, between round anchor values on given dates, so every reported
value can be checked by hand from the anchors. Each failure is planted on purpose, as each
function's docstring gives it, and the run record (`../README.md`) gives what the script reports
for each.

- `every-weekday/`: one `chart` entry per weekday from 2016-01-01 to 2016-04-29, with four
  periods, a month each, so that the metric, closure, `100 USD`, and precision checks run.
- `gaps/`: a `chart` with a gap of a week and a Saturday, whose windows are longer than the bound.
- `not-parallel/`: a `chart` whose arrays aren't the same length.

Numbers are written as Trial Folio saves them, in their shortest round-trip form, which drops
trailing zeros (docs/contracts.md, "Numbers and precision").

    uv run python reference/return-series/synthetic/generate.py
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
FOUR = Decimal("0.0001")
D = Decimal

COLUMNS = [
    "#",
    "Tran Dt",
    "End Dt",
    "Ret%",
    "Bench%",
    "Excess%",
    "100 USD Investment",
    "100 USD in SPY:USA",
]


def weekdays(start: date, end: date) -> list[date]:
    days = (start + timedelta(days=i) for i in range((end - start).days + 1))
    return [d for d in days if d.weekday() < 5]


def levels(dates: list[date], anchors: dict[date, Decimal], flat: set[date]) -> list[Decimal]:
    """Each anchor's value on its date, and, between two anchors, equal steps over the dates that
    aren't flat, rounded to 4 decimals. A flat date repeats the level before it."""
    value = {dates[0]: anchors[dates[0]]}
    for a, b in pairwise(sorted(anchors)):
        span = [d for d in dates if a < d <= b]
        step = (anchors[b] - anchors[a]) / sum(d not in flat for d in span)
        moved = 0
        for d in span:
            moved += d not in flat
            value[d] = (anchors[a] + step * moved).quantize(FOUR)
        assert value[b] == anchors[b], b
    return [value[d] for d in dates]


def rounded(value: Decimal) -> Decimal:
    return value.quantize(FOUR)


def written(value: Any) -> Any:
    """A decimal as the float Trial Folio saves, so that its text drops trailing zeros."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: written(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [written(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def request(start: date, end: date) -> dict[str, Any]:
    return {
        "screen": {
            "type": "stock",
            "universe": "SP500",
            "maxNumHoldings": 25,
            "method": "long",
            "currency": "USD",
            "benchmark": "SPY",
            "ranking": {"formula": "EarnYield", "lowerIsBetter": False},
            "rules": [{"formula": "AvgDailyTot(30) > 1000000"}],
        },
        "startDt": str(start),
        "endDt": str(end),
        "pitMethod": "Complete",
        "precision": 4,
        "transPrice": 1,
        "slippage": 0.25,
        "rebalFreq": "Every 4 Weeks",
    }


def response(
    dates: list[date],
    port: list[Decimal],
    bench: list[Decimal],
    rows: list[list[Any]],
    stats: dict[str, Any],
    turnover: list[Decimal] | None = None,
) -> dict[str, Any]:
    return {
        "stats": stats,
        "results": {"columns": COLUMNS, "rows": rows},
        "chart": {
            "dates": [str(d) for d in dates],
            "screenReturns": port,
            "benchReturns": bench,
            "turnoverPct": turnover or [D(0)] * len(dates),
            "positionCnt": [D(25)] * len(dates),
        },
    }


def every_weekday() -> tuple[dict[str, Any], dict[str, Any]]:
    """Four monthly periods. The strategy's month ends are 100, 110, 99, 108.9, and 100: periods
    of 10%, -10%, 10%, and 100/108.9 - 1; a maximum drawdown of -10%, from 110 to 99; monthly
    changes, from the end of January to the end of March, of -10% and 10%, so a standard
    deviation of the square root of 200, times the square root of 12; and total and annualized
    returns of 0. The benchmark's are 100, 102.5, 97.375, 101.27, and 100: periods of 2.5%, -5%,
    4%, and 100/101.27 - 1; a maximum drawdown of -5%; monthly changes of -5% and 4%, so a
    standard deviation of the square root of 40.5, times the square root of 12; and total and
    annualized returns of 0. Like the saved responses, the benchmark repeats its level on the
    weekday after each closure, and the strategy does too, except after 2016-01-01, the first
    period's Tran Dt.

    Planted: the first period's Excess% is 7.51, where Ret% minus Bench% is 7.5; the last
    period's 100 USD Investment is 100.0002, two units from the level, 100; the strategy's
    annualized_return is 1.5, and its max_drawdown -10.1234; the benchmark's standard_dev is
    22.05, which is 22.0500 at the precision, where the levels give 22.0454; turnoverPct's second
    entry, 12.34567, has 5 decimals; and the strategy's level repeats the entry before on a
    closure, 2016-02-15. The Excess% and the standard_dev differ from the values by less than half
    a unit of the digits they're written with, as a saved value without its trailing zeros can."""
    start, end = date(2016, 1, 1), date(2016, 4, 29)
    dates = weekdays(start, end)
    month_ends = [date(2016, 1, 29), date(2016, 2, 29), date(2016, 3, 31), end]
    after = {date(2016, 1, 4), date(2016, 1, 19), date(2016, 2, 16), date(2016, 3, 28)}
    port_ends = dict(zip([start, *month_ends], map(D, ("100", "110", "99", "108.9", "100"))))
    bench_ends = dict(
        zip([start, *month_ends], map(D, ("100", "102.5", "97.375", "101.27", "100")))
    )
    closure_repeat = date(2016, 2, 15)
    port = levels(dates, port_ends, (after - {date(2016, 1, 4)}) | {closure_repeat})
    bench = levels(dates, bench_ends, after)
    last_ret = rounded((D(100) / D("108.9") - 1) * 100)
    last_bench = rounded((D(100) / D("101.27") - 1) * 100)
    rows: list[list[Any]] = [
        [1, "2016-01-01", "2016-01-29", D("10"), D("2.5"), D("7.51"), D("110"), D("102.5")],
        [2, "2016-01-29", "2016-02-29", D("-10"), D("-5"), D("-5"), D("99"), D("97.375")],
        [3, "2016-02-29", "2016-03-31", D("10"), D("4"), D("6"), D("108.9"), D("101.27")],
        [
            4,
            "2016-03-31",
            "2016-04-29",
            last_ret,
            last_bench,
            last_ret - last_bench,
            D("100.0002"),
            D("100"),
        ],
    ]
    stats = {
        "samples": 2,
        "port": {
            "total_return": D(0),
            "annualized_return": D("1.5"),
            "max_drawdown": D("-10.1234"),
            "standard_dev": rounded(D(2400).sqrt()),
        },
        "bench": {
            "total_return": D(0),
            "annualized_return": D(0),
            "max_drawdown": D(-5),
            "standard_dev": D("22.05"),
        },
    }
    turnover = [D(0)] * len(dates)
    turnover[1] = D("12.34567")
    return response(dates, port, bench, rows, stats, turnover), request(start, end)


def with_gaps() -> tuple[dict[str, Any], dict[str, Any]]:
    """Two periods, the levels rising by a fixed step at each entry: the strategy's by 0.5 from
    100.5, and the benchmark's by 0.25 from 100. Each period's values, and the total returns, are
    calculated from those levels, rounded to 4 decimals.

    Planted: no entry from 2016-01-11 to 2016-01-15, so each 7-day window that ends from
    2016-01-18 to 2016-01-23 starts on 2016-01-08, 3 to 8 days longer than its length; an entry
    on a Saturday, 2016-01-23; the strategy's level starts at 100.5; the second period starts on
    2016-01-19, not on the first's End Dt, 2016-01-18; and the periods end on 2016-01-29, though
    the request's end date is 2016-02-05."""
    days = weekdays(date(2016, 1, 4), date(2016, 1, 29))
    dates = sorted(
        {d for d in days if not date(2016, 1, 11) <= d <= date(2016, 1, 15)} | {date(2016, 1, 23)}
    )
    port = [D("100.5") + D("0.5") * i for i in range(len(dates))]
    bench = [D(100) + D("0.25") * i for i in range(len(dates))]
    index = {d: i for i, d in enumerate(dates)}
    rows: list[list[Any]] = []
    totals = {"port": D(1), "bench": D(1)}
    periods = ((date(2016, 1, 4), date(2016, 1, 18)), (date(2016, 1, 19), date(2016, 1, 29)))
    for number, (tran, end) in enumerate(periods, 1):
        ret = rounded((port[index[end]] / port[index[tran]] - 1) * 100)
        bench_ret = rounded((bench[index[end]] / bench[index[tran]] - 1) * 100)
        totals["port"] *= 1 + ret / 100
        totals["bench"] *= 1 + bench_ret / 100
        values = [ret, bench_ret, ret - bench_ret, port[index[end]], bench[index[end]]]
        rows.append([number, str(tran), str(end), *values])
    stats: dict[str, Any] = {
        "samples": 0,
        **{
            subject: {"total_return": rounded((total - 1) * 100)}
            for subject, total in totals.items()
        },
    }
    return response(dates, port, bench, rows, stats), request(date(2016, 1, 4), date(2016, 2, 5))


def not_parallel() -> tuple[dict[str, Any], dict[str, Any]]:
    """One period, from 2016-01-04 to 2016-01-06, of 1% for each level.

    Planted: screenReturns has 2 entries, and the other arrays 3."""
    dates = weekdays(date(2016, 1, 4), date(2016, 1, 6))
    port = [D(100), D(101)]
    bench = [D(100), D("100.5"), D(101)]
    rows: list[list[Any]] = [[1, "2016-01-04", "2016-01-06", D(1), D(1), D(0), D(101), D(101)]]
    stats = {"samples": 0, "port": {"total_return": D(1)}, "bench": {"total_return": D(1)}}
    return response(dates, port, bench, rows, stats), request(dates[0], dates[-1])


def main() -> None:
    made = {"every-weekday": every_weekday(), "gaps": with_gaps(), "not-parallel": not_parallel()}
    for name, (payload, sent) in made.items():
        folder = HERE / name
        folder.mkdir(exist_ok=True)
        for file, value in (("response.json", payload), ("request.json", sent)):
            text = json.dumps(written(value), indent=2) + "\n"
            (folder / file).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
