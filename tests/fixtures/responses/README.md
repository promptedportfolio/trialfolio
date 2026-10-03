# Responses

Synthetic screen backtest responses for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). Each one mirrors the structure of [`p123api-screen-backtest` version 1](../../../docs/contracts.md#p123api-screen-backtest-version-1): its keys, its columns and their order, and the forms of its values. None of its data comes from a response.

- **Origin:** written for Trial Folio's tests. Every value is invented: the metrics, the periods and their dates, the summary rows, the chart, `cost`, and `quotaRemaining`. No value comes from Portfolio123 or from the owner's account.
- **Layout:** `p123api-screen-backtest` version 1, as the fake server sends it with a 200. `invalid-structure.json` breaks it on purpose.
- **Redistribution:** synthetic, so they may be committed and shared.

R01-T12 created these ahead of R01-T15, for the normalization tests. R01-T15 adds `not-json.txt` and `canaries.json`.

| File | Contents | Criteria |
|---|---|---|
| `complete.json` | A complete response: every metric present, with 1 to 4 decimal places, four rebalance periods, newest first, the summary rows, a short `chart`, `cost`, and `quotaRemaining`. Its coverage equals the [documented example](../../../docs/contracts.md#example)'s dates, 2016-01-01 to 2025-12-31. | R01-AC10, R01-AC12, R01-AC14, R01-AC30, R01-AC31 |
| `missing-metrics.json` | `complete.json`, with `stats.port.sortino_ratio` absent, `stats.beta` `null`, and `stats.bench.sharpe_ratio` a string | R01-AC12, R01-AC14 |
| `coverage-mismatch.json` | `complete.json`, with its first `Tran Dt` 2016-01-04, after the requested start, and its last `End Dt` 2025-12-26, before the requested end | R01-AC14, R01-AC31 |
| `no-periods.json` | `complete.json` with an empty `results.rows` | R01-AC31 |
| `invalid-structure.json` | `complete.json` without `stats` | R01-AC03 |
