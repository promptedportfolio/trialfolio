# Responses

Synthetic screen backtest responses, and from 0.4.0 `rank_update` and `rank_get` responses, for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). Each backtest response mirrors the structure of [`p123api-screen-backtest` version 1](../../../docs/contracts.md#p123api-screen-backtest-version-1): its keys, its columns and their order, and the forms of its values. Each `rank_update` and `rank_get` response mirrors its own layout, as the table gives it. None of their data comes from a response.

- **Origin:** written for Trial Folio's tests. Every value is invented: the metrics, the periods and their dates, the summary rows, the chart, `cost`, `quotaRemaining`, the canaries, the text of `not-json.txt`, and each ranking system's name, ID, and group IDs. No value comes from Portfolio123 or from the owner's account.
- **Layout:** `p123api-screen-backtest` version 1, as the fake server sends it with a 200. `invalid-structure.json` breaks it on purpose, and `not-json.txt` isn't JSON at all. `rank-update.json` is `p123api-rank-update` version 1, and `rank-get.json` `p123api-rank-get` version 1, which each of its changes breaks one way on purpose.
- **Redistribution:** synthetic, so they may be committed and shared.

R01-T12 created the first five ahead of R01-T15, for the normalization tests. R01-T15 added `not-json.txt` and `canaries.json`. R02-T06 added `changed-metrics.json` and `same-metrics.json` ahead of R02-T09, for the comparison core's tests, which build runs with each response with the [run builder](../../support/run_builder.py).

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
| `rank-get.json` | A synthetic `rank_get` response, in the layout of [`p123api-rank-get` version 1](../../../docs/contracts.md#p123api-rank-get-version-1), with the fields R04-T01's step 8 saw: an invented name, `Value and momentum`, ID, `cost`, `quotaRemaining`, `groupUid`, and `resolveGroupUid`; `rankingMethod` 2; `USD`; `Stock`; and [`value-momentum.xml`](../experiment-configs/ranking/value-momentum.xml)'s definition, byte for byte, as its `xml`. The order of its keys is invented too. R04-T10 added it, and the changes below, for the snapshot's tests. | R04-AC08 |
| `rank-get-without-xml.json` | `rank-get.json` without `xml`, so it lacks the structure a snapshot needs | R04-AC08 |
| `rank-get-method-1.json` | `rank-get.json` with `rankingMethod` 1, Normal Distribution, which no ranking takes | R04-AC08 |
| `rank-get-currency-cad.json` | `rank-get.json` with the currency `CAD`, not `USD` | R04-AC08 |
| `rank-get-type-etf.json` | `rank-get.json` with the type `ETF`, not `Stock` | R04-AC08 |
| `rank-get-unknown-method.json` | `rank-get.json` with `rankingMethod` 3, which `p123api`'s `RankingMethod` doesn't hold, so the wrapper raises after the 200, and the response is saved as `response.raw` | R04-AC08 |
| `rank-get-not-a-definition.json` | `rank-get.json` with a comment before its third composite, at line 18 of its `xml`, which a definition Trial Folio reads can't hold | R04-AC08 |
| `rank-get-lone-surrogate.json` | `rank-get.json` whose `xml` holds a lone surrogate, written as the JSON escape `\ud800`, which UTF-8 can't encode | R04-AC08 |

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
