# Offline check: the saved return series

This is the run record of task R05-T01 of [release 0.5.0](../../docs/releases/0.5.0-return-analytics.md#specification-tasks-before-ready). Before 0.5.0's analyses are specified, it checks, offline, the dated series in every saved screen-backtest response: the daily levels of 100 invested, in each response's `chart`, and each rebalance period's returns, in its `results.rows`, against the [verified layout](../../docs/contracts.md#p123api-screen-backtest-version-1). It sent no request, and spent no credit. It's the evidence on the saved series that the [statistics prototype](../../docs/statistics-prototype.md)'s SP-T02 cites ([D-43](../../docs/spec.md#decisions)).

This run record and the script that made the checks, [`check_series.py`](check_series.py), are committed. The responses hold Portfolio123's data and the owner's account information, so they stay in the `payloads/` folders beside the other run records, which are git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). The script read them there, and printed only dates, versions, counts, kinds of setting, and outcomes. That's all this record holds: no level, return, metric, or ranking system is given here, and nothing was copied out of `payloads/`.

## What was read

- **The owner's saved responses:** every screen-backtest response in the `payloads/` folders of the main checkout's `reference/`, from 0.1.0's reference calls, live check, and the user guide's walk-through, 0.2.0's live exercise, 0.3.0's variant checks, live check, and walk-through, and 0.4.0's route checks, live check, walk-through, and diagnostic. A response is a run's or an experiment's `response.json`, in `cases/<case_id>/attempts/<attempt_id>/`, or one that a script saved outside any attempt: [R01-T01's](../p123api-screen-backtest/README.md), [R01-T05's](../p123api-screen-backtest-values/README.md), and [the diagnostic's](../ranking-touch/README.md). A ranking snapshot holds none, and no folder has an `exports/`. Runs or experiments the owner keeps outside `reference/` weren't read.
- **Each response's request,** for its dates, precision, benchmark, and kind of ranking: the attempt's `request.json`; a script's `request-<x>.json` beside its `response-<x>.json`; for R01-T01's, the committed [`request.json`](../p123api-screen-backtest/request.json). The diagnostic saved none. Its [run record](../ranking-touch/README.md#settings) says it sent the request of the 0.4.0 walk-through's baseline case, byte for byte, so the script read that one, given with `--request`.
- **The committed synthetic responses:** every response under `tests/fixtures/`, the historical run and experiment fixtures' among them, and the demo's packaged `src/trialfolio/demo_data/response.json`.

## Run record

Date: 2026-11-01, 12:05:23 to 12:05:24 UTC, on macOS 26.6.2 with Python 3.14.8, from the branch `docs/r05-t01-saved-series`, based on `main` at 11a46a1, with the script as committed beside this record. It uses only Python's standard library. The same command under Python 3.12.13 printed the same output, apart from the line that names the Python version. Afterwards, no file in the main checkout's `reference/`, `tests/`, or `src/` had changed.

```sh
uv run python reference/return-series/check_series.py <main checkout>/reference --fixtures . \
  --request ranking-touch=ranking-walkthrough/payloads/runs/weights/cases/case-65f048fe2db85eda/attempts/33880737-9dba-4fcb-8fb2-c61213215056/request.json
```

**Comparisons.** A value reproduced from the series is *equal at the precision* when it's within half a unit of the fourth decimal of the reported value, the requests' `precision`. It's *equal at its digits* when it's within half a unit of the reported value's last saved decimal, which can be fewer, since Trial Folio saves numbers without trailing zeros. Otherwise, it's *within the rounding* when the reported value is in the range that the inputs' rounding allows, each level or period return to half a unit of the fourth decimal, widened by half a unit of the reported value's own digits. The script's docstring gives each range.

**Market closures.** The script's own calendar of the New York Stock Exchange's full-day closures, from the exchange's holiday rules, with the national days of mourning of 2018-12-05 and 2025-01-09: 95 weekdays from 2016-01-01 to 2025-12-31. It isn't Portfolio123's.

### The responses

| What | Count |
|---|---|
| Saved files with a backtest response | 77, in 12 folders |
| Distinct, by their bytes | 74. The other 3 are byte-for-byte copies of runs in other folders. |
| With layout version 1's required structure, and a `chart` | 74 |
| Distinct series of levels, by their values | 28 for the strategy, and 3 for the benchmark |
| Attempts without a response | 3, all the 0.3.0 walk-through's: the two that got HTTP 409, and the interrupted one |

Every request asked for 2016-01-01 to 2025-12-31, at precision 4, in USD. 73 had the benchmark SPY, and 1 IWM.

| Rebalancing | Ranking | Responses | Periods in each |
|---|---|---|---|
| Every week | A formula | 3 | 523 |
| Every 4 weeks | A formula | 18 | 131 |
| Every 4 weeks | A saved ranking system, by name or ID | 3 | 131 |
| Every 4 weeks | `ApiRankingSystem` by name, after R04-T01's script wrote a definition into it | 5 | 131 |
| Every 4 weeks | A ranking definition, which the attempt or the diagnostic sent with `rank_update` | 45 | 131 |

### The checks

Each outcome holds for every group of the table above, unless it says otherwise.

| Check | Outcome, in the 74 distinct responses |
|---|---|
| `chart` has its five arrays, parallel | 74 |
| Its dates are valid and increasing, and only weekdays | 74 |
| Its dates are every weekday from the requested start date to the end date | 74: 2,609 dates, from 2016-01-01 to 2025-12-31. The longest gap between two dates is 3 days, a weekend. |
| Both levels are positive numbers, and start at 100 | 74 |
| No numeric value has more decimals than the precision, 4 | 74 |
| The coverage, from the earliest `Tran Dt` to the latest `End Dt`, equals the requested dates, and each period's `End Dt` is the next one's `Tran Dt` | 74 |
| Each period's `Tran Dt` and `End Dt` is a `chart` date | All 10,870 periods |
| `Ret%` reproduces from the strategy's levels at `Tran Dt` and `End Dt` | All 10,870: 8,317 equal at the precision, 216 more at their digits, and the other 2,337 within the rounding |
| `Bench%` reproduces from the benchmark's levels | All 10,870: 9,017 equal at the precision, 196 more at their digits, and the other 1,657 within the rounding |
| `Excess%` is `Ret%` minus `Bench%` | 8,066 exactly, and the other 2,804 within the three values' rounding |
| `100 USD Investment`, and the benchmark's `100 USD in …`, is the level at `End Dt` | The strategy's: 10,542 exactly, and the other 328 one unit of the fourth decimal apart. The benchmark's: 10,638 exactly, and the other 232 one unit apart. None is further apart. |
| `total_return` is the last level minus 100 | 74 for the strategy and the benchmark, equal at the precision |
| `annualized_return` is the compound annual growth rate from the first to the last `chart` date, with 365.25-day years | The strategy's: 73 equal at the precision, and 1 within the rounding. The benchmark's: 74 equal. |
| `max_drawdown` is the largest decline from a peak in the daily levels | The strategy's: 48 equal at the precision, and 26 within the rounding. The benchmark's: 74 equal. |
| `standard_dev` is the sample standard deviation of the 118 monthly changes, from the end of the first month to the end of the next-to-last, times √12, and `stats.samples` is their count | The strategy's: 68 equal at the precision, and 6 within the rounding. The benchmark's: 74 equal. `stats.samples` is 118 in all 74. |
| The period returns, compounded, give `total_return` | 74, for the strategy and the benchmark: 1 equal at the precision, and the other 73 within the rounding of the period returns |

The four metrics reproduce at the precision, for the strategy and the benchmark, in R01-T01's reference response, as [R01-T02 found](../p123api-screen-backtest/README.md#checks-for-r01-t02). Its benchmark's `100 USD in SPY:USA` is the level at `End Dt` exactly in 126 of its 131 periods, and one unit of the fourth decimal apart in the other 5. R01-T02's record gives them as equal in all 131, without saying how closely it compared them.

### Market closures

Every one of the 95 closures from 2016-01-01 to 2025-12-31 has a `chart` entry, since every weekday has one. A closure shows as a repeated level in the entry after it, not in its own:

| Level | On a closure | On the weekday after a closure | On any other weekday |
|---|---|---|---|
| The benchmark's | It moves from the entry before at every closure after the first, 2016-01-01, which is the first entry: at all 94 in 73 responses, and at 93 in the one with IWM, where it repeats on 2019-12-25 | It repeats the closure's entry after all 95 closures, in all 74 responses | It repeats the entry before on 6 weekdays in the 73 responses with SPY, and on 4 in the one with IWM, besides 2019-12-25 |
| The strategy's | It moves at all 94 closures after the first, in all 74 | It repeats, except after a closure that's a period's `Tran Dt`: there, it moves in 1,561 cases in all, and never after any other closure. Each response that rebalances every 4 weeks has 20 periods whose `Tran Dt` is a closure, and moves after each of them. Each that rebalances every week has 54, and moves after 47. | It repeats on 1 weekday, in 9 responses |

- **Rebalance dates fall on closures.** 1,582 periods have a closure as their `Tran Dt`, and 1,508 as their `End Dt`.
- **A start on a closure.** Every `chart` starts on one, 2016-01-01, with both levels at 100. The benchmark's next entry, 2016-01-04, repeats it. The strategy's moves, since 2016-01-01 is the first period's `Tran Dt`.
- **An end on a closure isn't shown:** no response ends on one, as 2025-12-31 isn't.
- **At least two readings fit every count above.** Each level is the value at the close of the trading day before its date. Or each level is the value at its own date's close, and a closure's entry is valued at the next trading day's close, with the holdings from before that day's trades. The saved responses alone can't tell them apart, and Portfolio123 doesn't document which close a date's level is.

### Rolling windows

By the release outline's rule: a window ends at each `chart` date, and starts at the latest `chart` date at least its length earlier.

| Length, in calendar days | Windows in each response | Longer than the length by more than 2 days | The most days over the length |
|---|---|---|---|
| 7 | 2,604 | 0 | 0 |
| 30 | 2,588 | 0 | 2 |
| 90 | 2,545 | 0 | 1 |
| 180 | 2,481 | 0 | 2 |
| 365 | 2,348 | 0 | 2 |

So the bound holds in every saved `chart`: no window is more than 2 days longer than its length, and none crosses a gap. In each response, 150 to 203 windows of each length start or end on an entry that repeats the one before it, most of them on the weekday after a closure.

### The saved experiments

Every case with a response has the same 2,609 `chart` dates, from 2016-01-01 to 2025-12-31, so the window counts above, and 131 periods when it rebalances every 4 weeks, or 523 when it rebalances every week:

| Experiment, in `payloads/` | Its run record | Cases with a response | Periods |
|---|---|---|---|
| `experiment-live-check/`: `experiment-20261011T230120Z/` | [0.3.0's live check](../experiment-live-check/README.md) | 2: the baseline, every 4 weeks, and `rebalance-weeks-1`, every week | 131 and 523 |
| `experiment-walkthrough/`: `runs/study/` | [0.3.0's walk-through](../experiment-walkthrough/README.md) | 7: the 6 planned, 5 every 4 weeks and 1 every week, and 1 of the 3 retired. The other 2 retired cases have no response. | 131 in 6 of them, and 523 in 1 |
| `ranking-live-check/`: `experiment-20261019T174635Z/`, `experiment-20261019T182345Z/`, and `experiment-20261021T205735Z/` | [0.4.0's live check](../ranking-live-check/README.md), its three runs | 2 in each, with a ranking definition | 131 |
| `ranking-walkthrough/`: `runs/weights/` | [0.4.0's walk-through](../ranking-walkthrough/README.md) | 4, with a ranking definition | 131 |

### The committed synthetic responses

| Files | Outcome |
|---|---|
| The historical fixtures' 8 responses, in `synthetic-run-1.0.0/`, `synthetic-run-1.1.0/`, `synthetic-experiment-1.0.0/`, and `synthetic-experiment-1.1.0/`, byte for byte the same | `chart`'s five arrays hold 5 entries each, from 2016-01-01 to 2025-12-31, and both levels start at 100: not every weekday, as [R05-AC09](../../docs/releases/0.5.0-return-analytics.md#acceptance-criteria) expects. Each of the 4 periods' `Ret%` and `Bench%` reproduces from the 5 levels at its digits, and `Excess%` is their difference exactly. The benchmark's period returns, compounded, don't give its `total_return`. |
| The demo's packaged response | The same form of `chart`, with 5 dates. Its 4 periods reproduce, as above, and both compounded totals agree with `total_return`, within the rounding. |
| The 7 under `tests/fixtures/responses/` with the required structure | The same form of `chart`, with 5 dates; `coverage-mismatch.json`'s from 2016-01-04 to 2025-12-26. `no-periods.json` has no period. The periods of the others reproduce, except one of `canaries.json`'s, whose `Ret%` and `Excess%` don't. |
| `tests/fixtures/responses/invalid-structure.json` | Without the required structure |

## Findings for R05-T02

- **What 0.5.0 can compute from the saved responses.** Every one of the 74 holds what the proposed analyses read: a `chart` with one entry per weekday, with levels that start at 100, and period rows whose returns are numbers. So each saved run, and each case of a saved experiment with a response, can get every analysis of its daily levels and of its periods. The 3 attempts without a response can't. No saved run or experiment declares split dates, since 0.4.0's configurations have no key for them and reject unknown keys, so the period splits of each are unavailable. The historical fixtures and the demo's packaged data can get only their period analyses, as [D-47](../../docs/spec.md#decisions) gives it.
- **The rolling windows' bound holds,** in every saved `chart`.
- **Cases align by date.** Every case of each saved experiment has the same `chart` dates.
- **Portfolio123's values agree with the saved series only within its rounding.** Each period's `Ret%`, `Bench%`, `Excess%`, and `100 USD` values, and each metric, agrees with the value calculated from the four-decimal series, but often only within the series' rounding, as values calculated before rounding would:
  - **`Excess%`** differs from `Ret%` minus `Bench%` in 2,804 of 10,870 periods, by their rounding, so a series table that calculated it again would change it, as D-47 says it mustn't.
  - **A recalculated metric differs from Portfolio123's beyond its digits for rounding alone.** Calculated from the levels, the strategy's maximum drawdown differs from the reported value by more than half a unit of its last digit in 26 of the 74 responses, and its annualized return in 1 more, each within the range the levels' rounding allows. Read that way, [required behavior](../../docs/releases/0.5.0-return-analytics.md#required-behavior) 5's flag, a difference beyond the reported digits, would mark those 27 responses. The standard deviation, which the proposed analysis set doesn't recalculate, differs so in 6.
- **The date a level belongs to isn't documented.** A closure's own entry moves, and the next weekday's repeats it, and at least two readings fit. Either way, an analysis dated by the `chart` gives Portfolio123's dates, and a window that ends on the weekday after a closure ends at the same level as one that ends on the closure.
- **The responses aren't independent evidence.** The 74 distinct responses hold 28 distinct series of strategy levels, and 3 of benchmark levels. The diagnostic's 30 backtests, for example, each returned one of its two definitions' results, as [its run record](../ranking-touch/README.md#run-record) says.

## What wasn't checked

- **Runs and experiments outside the main checkout's `reference/`,** such as any of the owner's private use.
- **Other dates and settings.** Every saved request asked for 2016-01-01 to 2025-12-31, at precision 4, in USD, with SPY or IWM, rebalanced every week or every 4 weeks. So no response shows an end on a closure, a start on a trading day or a weekend, or another precision, currency, or rebalancing.
- **Which close a date's level is.** The saved responses can't tell, as above. A comparison with a published series of the benchmark's closes could.
- **Whether a response is stale** ([D-45](../../docs/spec.md#decisions)). The checks compare a response with itself and its request. A stale backtest's response, such as the 0.4.0 walk-through's, passes them.
- **The other arrays.** Of `turnoverPct` and `positionCnt`, only their lengths were checked.
