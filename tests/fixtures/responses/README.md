# Responses

Synthetic screen backtest responses, and from 0.4.0 `rank_update` and `rank_get` responses, for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). Each backtest response mirrors the structure of [`p123api-screen-backtest` version 1](../../../docs/contracts.md#p123api-screen-backtest-version-1): its keys, its columns and their order, and the forms of its values. Each `rank_update` and `rank_get` response mirrors its own layout, as the table gives it. None of their data comes from a response.

- **Origin:** written for Trial Folio's tests. Every value is invented: the metrics, the periods and their dates, the summary rows, the chart, `cost`, `quotaRemaining`, the canaries, the text of `not-json.txt`, and each ranking system's name, ID, and group IDs. No value comes from Portfolio123 or from the owner's account.
- **Layout:** `p123api-screen-backtest` version 1, as the fake server sends it with a 200. `invalid-structure.json` breaks it on purpose, and `not-json.txt` isn't JSON at all. `rank-update.json` is `p123api-rank-update` version 1, and `rank-get.json` `p123api-rank-get` version 1, which each of its changes breaks one way on purpose.
- **Redistribution:** synthetic, so they may be committed and shared.

R01-T12 created the first five ahead of R01-T15, for the normalization tests. R01-T15 added `not-json.txt` and `canaries.json`. R02-T06 added `changed-metrics.json` and `same-metrics.json` ahead of R02-T09, for the comparison core's tests, which build runs with each response with the [run builder](../../support/run_builder.py). Release 0.5.0's R05-T06 added the [hand-checkable responses](#the-hand-checkable-responses), `one-date.json`, and `four-years.json`, for the series' and the analysis set's tests.

| File | Contents | Criteria |
|---|---|---|
| `complete.json` | A complete response: every metric present, with 1 to 4 decimal places, four rebalance periods, newest first, the summary rows, a short `chart`, `cost`, and `quotaRemaining`. Its coverage equals the [documented example](../../../docs/contracts.md#example)'s dates, 2016-01-01 to 2025-12-31. | R01-AC03, R01-AC07, R01-AC10, R01-AC12, R01-AC13, R01-AC14, R01-AC30, R01-AC31; the baseline's response, and the response of the runs with its settings, in R02-AC01, R02-AC02, R02-AC03, R02-AC04, R02-AC05, R02-AC07, R02-AC08, R02-AC09, R02-AC10, R02-AC11, R02-AC13, R02-AC15, R02-AC17, R02-AC18, and R02-AC19; from 0.3.0, the response to each case's request in the experiment tests, unless a test names another, through the experiment builder's `returns` |
| `missing-metrics.json` | `complete.json`, with `stats.port.sortino_ratio` absent, `stats.beta` `null`, and `stats.bench.sharpe_ratio` a string | R01-AC12, R01-AC14, R02-AC03, R02-AC04, R02-AC07, R02-AC13, R02-AC18, R03-AC08, R03-AC16, R03-AC18 |
| `coverage-mismatch.json` | `complete.json`, with its first `Tran Dt` 2016-01-04, after the requested start, and its last `End Dt` 2025-12-26, before the requested end | R01-AC14, R01-AC31, R02-AC08, R02-AC18, R03-AC18 |
| `no-periods.json` | `complete.json` with an empty `results.rows` | R01-AC31, R02-AC08, R02-AC18 |
| `invalid-structure.json` | `complete.json` without `stats` | R01-AC03, R02-AC13, R02-AC15, R02-AC18, R03-AC18 |
| `not-json.txt` | A short HTML page, a body that isn't JSON, which the fake server sends with a 200 for the backtest request. The response is saved undecoded, as `response.raw`. | R01-AC26, R02-AC13, R02-AC15, R02-AC18 |
| `canaries.json` | `complete.json`, with canary strings in an extra key, `canaryExtra.note`, and in `chart.label`, and canary numbers as `stats.port.total_return` and the newest period's `Ret%`. `tests/support/canaries.py` lists them. | R01-AC17, R02-AC12, R03-AC15 |
| `changed-metrics.json` | `complete.json` with the strategy's metrics changed, as the table below gives them. Its coverage, its periods, its chart, and the benchmark's own metrics are `complete.json`'s. | R02-AC01, R02-AC02, R02-AC03, R02-AC05, R02-AC07, R02-AC08, R02-AC09, R02-AC10, R02-AC11, R02-AC13, R02-AC16, R02-AC17, R02-AC18, R02-AC19, R03-AC11, R03-AC18 |
| `same-metrics.json` | `complete.json` with `quotaRemaining` 4316, as a second backtest of the same settings could return: its metrics and coverage are `complete.json`'s, but its bytes aren't | R02-AC03, R02-AC07, R02-AC13, R02-AC17, R02-AC18 |
| `rank-update.json` | A synthetic `rank_update` response, in the layout of [`p123api-rank-update` version 1](../../../docs/contracts.md#p123api-rank-update-version-1): an invented `cost` of 1 and `quotaRemaining`, the only keys R04-T01 saw. R04-T08 added it, for the tests of sending a definition. | R04-AC03, R04-AC09 |
| `rank-get.json` | A synthetic `rank_get` response, in the layout of [`p123api-rank-get` version 1](../../../docs/contracts.md#p123api-rank-get-version-1), with the fields R04-T01's step 8 saw: an invented name, `Value and momentum`, ID, `cost`, `quotaRemaining`, `groupUid`, and `resolveGroupUid`; `rankingMethod` 2; `USD`; `Stock`; and [`value-momentum.xml`](../experiment-configs/ranking/value-momentum.xml)'s definition, byte for byte, as its `xml`. The order of its keys is invented too. R04-T10 added it, and the changes below, for the snapshot's tests. | R04-AC08; the invented system of [`snapshots/synthetic-snapshot-1.0.0/`](../snapshots/README.md) |
| `rank-get-without-xml.json` | `rank-get.json` without `xml`, so it lacks the structure a snapshot needs | R04-AC08 |
| `rank-get-method-1.json` | `rank-get.json` with `rankingMethod` 1, Normal Distribution, which no ranking takes | R04-AC08 |
| `rank-get-currency-cad.json` | `rank-get.json` with the currency `CAD`, not `USD` | R04-AC08 |
| `rank-get-type-etf.json` | `rank-get.json` with the type `ETF`, not `Stock` | R04-AC08 |
| `rank-get-unknown-method.json` | `rank-get.json` with `rankingMethod` 3, which `p123api`'s `RankingMethod` doesn't hold, so the wrapper raises after the 200, and the response is saved as `response.raw` | R04-AC08 |
| `rank-get-not-a-definition.json` | `rank-get.json` with a comment before its third composite, at line 18 of its `xml`, which a definition Trial Folio reads can't hold | R04-AC08 |
| `rank-get-lone-surrogate.json` | `rank-get.json` whose `xml` holds a lone surrogate, written as the JSON escape `\ud800`, which UTF-8 can't encode | R04-AC08 |
| `rank-get-canaries.json` | `rank-get.json` with canaries: the name `canary-system-4d7a2c19`, which `ranking-snapshot-configs/canaries.yaml` names, an ID, `quotaRemaining`, `groupUid`, and `resolveGroupUid` with distinctive digits, and `experiment-configs/ranking/canaries.xml`'s definition as its `xml`. `tests/support/canaries.py` lists them. R04-T13 added it. | R04-AC11, in `tests/interface/test_logs.py` |

## `changed-metrics.json`'s differences

Against `complete.json`, as the baseline, each metric of `changed-metrics.json` gives the difference below ([differences between screen runs](../../../docs/contracts.md#differences-between-screen-runs)). `tests/core/test_differences.py` holds these differences as written here, never as the code computes them. Rows 1–3 are the coverage, which both responses share, and rows 15–20, the benchmark's own metrics, are unchanged, so their differences are zero, with the benchmark's decimals.

| Row | Metric | `complete.json` | `changed-metrics.json` | Difference | What it exercises |
|---|---|---|---|---|---|
| 1, 2 | `coverage_start`, `coverage_end` | 2016-01-01, 2025-12-31 | The same | `0` days | Dates differenced in days |
| 3 | `coverage_periods` | 4 | 4 | `0` count | |
| 4 | `total_return` | 151.7 | 151.68 | `0.0` pp | A difference that rounds to zero from below, `-0.0`, written without a sign |
| 5 | `annualized_return` | 9.6643 | 10.0 | `0.3` pp | A whole number saved as a float, whose `.0` counts as a decimal place: without it, the difference would be `0` |
| 6 | `max_drawdown` | -33.12 | -33.02 | `0.10` pp | A difference written with a trailing zero |
| 7 | `standard_deviation` | 18.217 | 17.5 | `-0.7` pp | A negative difference |
| 8 | `sharpe_ratio` | 0.61 | 0.635 | `0.02` ratio | A tie, `0.025`, rounded half to even, where rounding half up would give `0.03` |
| 9 | `sortino_ratio` | 0.8842 | 0.9105 | `0.0263` ratio | |
| 10 | `correlation` | 0.8123 | 0.79 | `-0.02` ratio | |
| 11 | `r_squared` | 0.6598 | 0.6241 | `-0.0357` ratio | The square of row 10's 0.79 |
| 12 | `beta` | 1.04 | 1.1 | `0.1` ratio | |
| 13 | `alpha` | -2.517 | -1.9 | `0.6` pp | |
| 14 | `risk_samples` | 119 | 120 | `1` count | |
| 15–20 | The benchmark's metrics | 238.05, 12.3, -24.5, 15.4, 0.7712, 1.0398 | The same | `0.00`, `0.0`, `0.0`, `0.0`, `0.0000`, `0.0000` | Zero differences with the source's decimals |

## The hand-checkable responses

Release 0.5.0's [test pairing](../../../docs/releases/0.5.0-return-analytics.md#test-pairing) gives each of these, and the criteria each exercises, in the modules it names. `hand-checkable.json` is methodology.md's [hand-checkable example](../../../docs/methodology.md#a-hand-checkable-example), which `tests/contract/test_analysis_example.py` checks it against, and each other `hand-checkable-<change>.json` is it changed one way. Every number is written as a saved `response.json` writes it, in its shortest round-trip form, so `100` keeps no decimal place, and `1.0` keeps one. R05-T06 wrote them, for the core's tests of the series and the analysis set, and the later tasks of the release read them too.

| File | Contents | Criteria |
|---|---|---|
| `hand-checkable.json` | The example in the layout `p123api-screen-backtest` version 1: a `chart` of the 10 weekdays from 2024-01-01 to 2024-01-12, with the example's levels, and invented `turnoverPct` and `positionCnt`; its two periods in `results.rows`, newest first, with the example's `Ret%`, `Bench%`, and `Excess%`, each `100 USD` column the level at its `End Dt`; and `stats` whose strategy's `total_return` is 10.0001 and `max_drawdown` −4.8078, within the range the reconciliation gives, and whose benchmark's are 1.0 and −1.9608. The other values are invented, in the layout's types. | R05-AC01, R05-AC03, R05-AC04, R05-AC08 |
| `hand-checkable-differs.json` | The strategy's `max_drawdown` −4.8079 and `total_return` 10.0002, each beyond that range | R05-AC04 |
| `hand-checkable-no-chart.json`, `-chart-without-dates.json` | No `chart`, and a `chart` without `dates`: `blank_in_source` | R05-AC02, R05-AC04 |
| `hand-checkable-chart-not-object.json`, `-chart-not-parallel.json`, `-chart-bad-date.json`, `-chart-date-repeated.json`, `-chart-level-zero.json`, `-chart-level-string.json`, `-chart-not-at-100.json` | `chart` an array; `benchReturns` one entry short; 2024-01-05 written 2024-01-32; 2024-01-03 written 2024-01-02, so it isn't later than the date before; the strategy's 2024-01-05 level 0; its 2024-01-02 level the string `"102"`; and the benchmark's first level 100.5: `unparseable_in_source` | R05-AC02 |
| `hand-checkable-chart-gap.json`, `-chart-weekend.json`, `-chart-short.json` | 2024-01-09 removed from each array; Saturday 2024-01-06 added; and 2024-01-12 removed: `not_daily` | R05-AC02 |
| `hand-checkable-chart-faults.json` | Without `benchReturns`, and with 2024-01-05 written 2024-01-32: `blank_in_source`, the first reason that applies | R05-AC02 |
| `hand-checkable-no-periods.json`, `-no-end-column.json` | `results.rows` empty, and `End Dt` missing from `results.columns` and from each row: no period, `blank_in_source` | R05-AC02, R05-AC08 |
| `hand-checkable-no-excess-column.json` | `Excess%` missing from `results.columns` and from each row: each period's excess `blank_in_source`, keeping its dates | R05-AC02 |
| `hand-checkable-period-null.json`, `-period-not-a-number.json` | The first period's `Ret%` `null`, `blank_in_source`, and the second's `Bench%` `NaN`, as Python's `json` writes it, `unparseable_in_source` | R05-AC02 |
| `hand-checkable-period-bad-date.json` | The second period's `Tran Dt` 2024-01-32: its cell empty, its three values `unparseable_in_source`, after the first period, and the coverage unavailable | R05-AC02 |
| `hand-checkable-variant.json` | Another case's response over the same dates: the strategy's levels 100, 103, 99.75, 101, 97.75, 101, 101.75, 101, 98.5, and 100, each after the first at least 1 from the example's, so each value from them differs from the example's; the benchmark's the same; and two weekly periods whose returns reproduce from the levels, the second with an `Excess%` of −0.99, one unit of its last digit from `Ret%` minus `Bench%`, −0.9901 | R05-AC01, R05-AC03, R05-AC05, R05-AC06 |
| `hand-checkable-four-weekly.json` | The example's `chart`, with one period, 2024-01-01 to 2024-01-12, whose `Ret%`, `Bench%`, and `Excess%` are 10, 1, and 9: a case rebalanced every 4 weeks | R05-AC03, R05-AC05 |
| `hand-checkable-late-start.json` | The first period's `Tran Dt` 2024-01-02, with its returns from the levels at it, −1.9608, 0, and −1.9608, so the coverage starts a day after the example's | R05-AC03, R05-AC05 |
| `hand-checkable-flat.json` | The example's dates with every level 100, and every return 0: a `max_drawdown` of 0, whose recovery is `not_applicable`, and a tracking error of 0, so the information ratio and the t-value are `not_applicable` | R05-AC03, R05-AC06 |
| `hand-checkable-canaries.json` | The example with levels and returns of distinctive digits, which `tests/support/canaries.py` lists as `HAND_CHECKABLE_RESPONSE`: the strategy's 2024-01-02 level 102.6481, the benchmark's 2024-01-03 level 101.3957, the first period's `Bench%` 1.2874, and the second's `Ret%` 10.5164 | R05-AC03; R05-AC15, in `tests/interface/test_logs.py` |
| `one-date.json` | A `chart` of one date, 2024-01-05, with both levels at 100, and no period, for `screen-configs/one-date.yaml`: a coverage of one date | R05-AC03, R05-AC06, R05-AC08 |
| `four-years.json` | A `chart` of the 1,044 weekdays from Wednesday 2020-01-01 to Monday 2024-01-01, 1,461 calendar days, 4 years of 365.25 days, with both levels at 100 on every date but the last, where the strategy's is 146.41 and the benchmark's 65.61; no period; and `stats` whose `total_return`, `annualized_return`, and `max_drawdown` are the values the levels give: 46.41, 10.0, and 0.0 for the strategy, and −34.39, −10.0, and −34.39 for the benchmark. The other values are invented. | R05-AC03, R05-AC04 |
