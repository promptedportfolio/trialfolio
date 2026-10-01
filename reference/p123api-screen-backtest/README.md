# Reference call: p123api screen backtest

This is the reference response for release 0.1.0, task R01-T01 ([0.1.0 spec](../../docs/releases/0.1.0-api-execution.md#specification-tasks-before-ready)). Task R01-T02 documents its layout in [contracts.md](../../docs/contracts.md#supported-provider-payloads).

The request files and this run record are committed. The response contains Portfolio123 data, so it stays in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)).

## Settings

The owner approved these settings and a 5-credit budget, then approved one further 5-credit attempt after the first failed. The settings were:

- universe `SP500`
- one liquidity rule, `AvgDailyTot(30) > 1000000`
- a single-formula `EarnYield` ranking, higher is better
- 2016-01-01 to 2025-12-31
- rebalance every 4 weeks
- 25 holdings
- benchmark SPY
- 0.25% slippage
- open prices (`transPrice: 1`)
- complete point-in-time data
- 4 decimal places

Two changes to the approved settings, both accepted by the owner:
- **No vendor parameter.** None is documented for this endpoint, so FactSet is recorded as an inferred default.
- **4 decimal places.** The approved settings didn't set a precision, so `precision: 4` was added.

## Run record

Date: 2026-10-01. Wrapper: `p123api` 3.1.0, configured for one HTTP attempt per call.

| Attempt | Endpoint | Request | Outcome | Credits |
|---|---|---|---|---|
| 1 | `screen_backtest` | [request-attempt-1.json](request-attempt-1.json) | Rejected: HTTP 400. The script didn't capture the server's message. Attempt 2 showed the cause. | Unknown; documented cost 5 |
| 2 | `screen_run`, diagnostic | [screen-run-request.json](screen-run-request.json) | Rejected: HTTP 400, "Rule type parameter should not be present" | Unknown; documented cost 2 |
| 3 | `screen_backtest` | [request.json](request.json) | Succeeded in 0.9 seconds; 189,680 bytes saved to `payloads/response.json` | 5, as reported in the response |

The only difference between attempts 1 and 3 is the rule. Attempt 1 sent `{"formula": …, "type": "common"}`, and attempt 3 sent `{"formula": …}`.

Whether rejected requests are charged is still unknown. The response's `quotaRemaining` value isn't recorded here, because it is account information.

## Findings for R01-T02

- **Rule type.** Portfolio123 rejects a `type` field on a common rule, although its [API documentation](https://portfolio123.customerly.help/en/articles/43324-api-screen) lists `common` as a valid value. A common rule is sent as `{"formula": "…"}`.
- **Top-level keys:** `cost`, `quotaRemaining`, `stats`, `results`, and `chart`.
- **`stats`** holds `samples`, `correlation`, `r_squared`, `beta`, and `alpha`. `port` and `bench` each hold `standard_dev`, `sharpe_ratio`, `sortino_ratio`, `total_return`, `annualized_return`, and `max_drawdown`.
- **`results`** is a table with 19 columns and one row per rebalance period: 131 rows here. It also has `average`, `upMarkets`, and `downMarkets` rows.
- **`chart`** is a daily series: 2,609 points of `dates`, `screenReturns`, `benchReturns`, `turnoverPct`, and `positionCnt`, from 2016-01-01 to 2025-12-31.
- **Vendor.** The response doesn't report the data vendor.

## Checks for R01-T02

R01-T02 documents the layout as [`p123api-screen-backtest` version 1](../../docs/contracts.md#p123api-screen-backtest-version-1). These checks ran against `payloads/response.json` with a short, uncommitted Python standard-library script. Portfolio123's values aren't recorded here; only the outcomes are.

"Monthly returns" means the changes in the `chart` levels between the last chart dates of consecutive months. The checks use the 118 such returns from the end of the first month to the end of the next-to-last month.

| Check | Outcome |
|---|---|
| No numeric value has more than 4 decimal places, the requested precision | Passed. `stats.port.standard_dev` has 3. |
| `chart.dates` holds every weekday from 2016-01-01 to 2025-12-31, market holidays included | Passed: 2,609 dates |
| Both `chart` level series start at 100, and the last level minus 100 equals `total_return` | Passed for the strategy and the benchmark |
| `annualized_return` equals the compound annual growth rate over the chart's calendar days, with 365.25-day years | Passed for both, at 4 decimal places |
| `max_drawdown` equals the largest peak-to-trough decline in the daily levels | Passed for both |
| `standard_dev` equals the sample standard deviation of the monthly returns, times √12 | Passed for both. `stats.samples` equals the count, 118. |
| `r_squared` equals `correlation` squared, rounded to 4 places | Passed |
| `correlation` and `beta` from the monthly returns | Close to the reported values, but not equal |
| `sharpe_ratio` and `sortino_ratio` from the monthly returns with a zero risk-free rate, and `alpha` from the monthly regression | Not reproduced |
| `100 USD Investment` and `100 USD in SPY:USA` equal the `chart` levels at each period's `End Dt` | Passed for all 131 periods |
| `Ret%` and `Bench%` equal the change in the `chart` levels from `Tran Dt` to `End Dt`, within 0.001 | Passed for all 131 periods |
| `Excess%` equals `Ret%` minus `Bench%`, within 0.0001 | Passed |
| `Turn` equals `Sold Pos` divided by `#Pos`, times 100 | Passed for all 131 periods |
| Each period's `End Dt` is the next period's `Tran Dt`. The earliest `Tran Dt` and the latest `End Dt` equal the requested dates. | Passed |
| Element *i* of `results.average`, `upMarkets`, and `downMarkets` is the mean of `columns[i+1]` over all periods, over periods with `Bench%` above zero, and over the rest | Passed for every non-null element. Element 1 of the up- and down-market rows is the period count. No period had a `Bench%` of zero. |
| `to_pandas=True` moves the summary rows one column to the left | Confirmed with synthetic rows under pandas 3.0.6, following the wrapper's source |
| The `p123api` 3.1.0 wheel from PyPI matches the source commit pinned in [ADR 0001](../../docs/adrs/0001-python-and-portfolio123-integration.md#verification-notes) | Passed: `client.py` is identical apart from line endings |
