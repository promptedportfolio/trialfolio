# Live checks: screen backtest values

These are the live checks [D-20](../../docs/spec.md#decisions) requires before release 0.1.0 is Ready, under task R01-T05 ([0.1.0 spec](../../docs/releases/0.1.0-api-execution.md#specification-tasks-before-ready)). Each check verifies one screen configuration value. It sends [R01-T01's request](../p123api-screen-backtest/request.json) with that one change.

The request files and this run record are committed. The responses contain Portfolio123 data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)).

## Settings

On 2026-10-01 the owner approved three checks with a budget of 15 credits, and supplied a ranking system for checks 2 and 3:

| Check | Change from R01-T01's request | Request |
|---|---|---|
| 1, weekly rebalancing | `rebalFreq`: `"Every Week"` | [request-weekly.json](request-weekly.json) |
| 2, ranking by name | `screen.ranking`: the name of an existing ranking system in the owner's account, as a string | [request-ranking-name.json](request-ranking-name.json) |
| 3, ranking by ID | `screen.ranking`: the same system's ID, as a JSON integer | [request-ranking-id.json](request-ranking-id.json) |

**Placeholders.** The ranking system's name and ID are account information, so the owner chose to keep them local. The committed requests for checks 2 and 3 show `"<ranking system name>"` and `0` instead. The `0` keeps the type that was sent, a JSON integer. Trial Folio's configuration rejects it as an ID, so it can't be mistaken for a real one. The exact requests are in `payloads/`. The weekly request is committed exactly.

Nothing in the account was created or changed.

## Run record

Date: 2026-10-01, 23:41 to 23:42 UTC. Python 3.12.13, with the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0. `simplejson` wasn't importable.

Each check used a new client, set to one HTTP attempt per call. A minimal transport adapter recorded each exchange, and refused any second exchange within a call, as [ADR 0006](../../docs/adrs/0006-observe-the-wrappers-http-exchanges.md) describes. Each check authenticated with its own `POST /auth` call, and then sent its request once.

| Check | Exchanges | Outcome | Duration | Saved | Credits |
|---|---|---|---|---|---|
| 1 | `POST /auth` 200, then `POST /screen/backtest` 200 | Succeeded | 1.4 seconds | 202,069 bytes, `payloads/response-weekly.json` | 5, as reported in the response |
| 2 | The same | Succeeded | 0.8 seconds | 139,309 bytes, `payloads/response-ranking-name.json` | 5, as reported |
| 3 | The same | Succeeded | 0.6 seconds | 139,309 bytes, `payloads/response-ranking-id.json` | 5, as reported |

In total, the checks used 15 credits, within the budget.

**Authentication's cost.** Between consecutive checks, `quotaRemaining` dropped by exactly 5: from check 1's response to check 2's, and again from check 2's to check 3's. Each drop covers the later check's authentication and its request, and Portfolio123 reported a cost of 5 for each request. So the second and third authentications cost 0 credits. The first check's authentication had no earlier reading to compare with, so it wasn't measured. That assumes nothing else used the account's credits during the 19-second run. The absolute `quotaRemaining` values are account information, so they aren't recorded here.

## Checks against the response layout

These checks compare each response with [`p123api-screen-backtest` version 1](../../docs/contracts.md#p123api-screen-backtest-version-1) and with R01-T01's response. A short, uncommitted Python standard-library script ran them, reading numbers as decimals. Only the outcomes are recorded here, not Portfolio123's values.

| Check | Weekly | By name | By ID |
|---|---|---|---|
| The response has layout version 1's required structure | Passed | Passed | Passed |
| The keys at the top level, in `stats`, `stats.port`, `stats.bench`, `results`, and `chart`, and the 19 `results.columns`, equal R01-T01's | Passed | Passed | Passed |
| Every metric value is a JSON number. `cost` and `quotaRemaining` are integers. | Passed | Passed | Passed |
| No numeric value has more than 4 decimal places, the requested precision | Passed | Passed | Passed |
| Rebalance periods, and the median days from `Tran Dt` to `End Dt` | 523 periods, 7 days | 131 periods, 28 days | 131 periods, 28 days |
| The earliest `Tran Dt` and the latest `End Dt` equal the requested dates. Each period's `End Dt` is the next period's `Tran Dt`. | Passed | Passed | Passed |
| Rows are newest first, and `#` is 1 for the earliest period | Passed | Passed | Passed |
| `results.average`, `upMarkets`, and `downMarkets` are one element shorter than `columns`. The up- and down-market period counts add up to the number of periods. | Passed | Passed | Passed |
| `Turn` equals `Sold Pos` divided by `#Pos`, times 100, within 0.005. `Excess%` equals `Ret%` minus `Bench%`, within 0.0001. | Passed | Passed | Passed |
| `chart` holds 2,609 points in parallel arrays, from 2016-01-01 to 2025-12-31. Both levels start at 100, and each last level minus 100 equals its `total_return` exactly. | Passed | Passed | Passed |
| `stats.bench` and `chart.benchReturns` equal R01-T01's | Passed | Passed | Passed |
| `stats.port` differs from R01-T01's, so the changed setting took effect | Passed | Passed | Passed |
| Checks 2 and 3 return identical responses, apart from `quotaRemaining` | — | Passed | Passed |

**A benchmark return of zero.** One weekly period has a `Bench%` of exactly `0` at 4 decimal places. It's counted in `upMarkets`, and the up-market mean of `Ret%` reproduces only with it included. Its unrounded return isn't in the response: it may be slightly above zero or exactly zero, or Portfolio123 may compare rounded values. So the rule for a return at or near zero is still unverified.

## Findings for R01-T05

- **Weekly rebalancing is verified.** Portfolio123 accepted `rebalFreq` `"Every Week"` and returned one period per week.
- **Ranking by name and by ID are verified.** Portfolio123 accepted a ranking system's name as a string, and its ID as a JSON integer. Both gave the same response, so they resolved to the same system.
- **Layout version 1 covers all three responses.** None of them has a key that R01-T01's lacks, or lacks one that it has, so no parser change is needed.
- **Authentication cost no credits** in the two cases that could be measured, the second and third checks.
- **Whether failed requests are charged is still unknown,** because no request failed.
