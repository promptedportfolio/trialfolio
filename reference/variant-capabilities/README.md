# Live checks: variant capabilities

These are the live checks of task R03-T01, which verifies the variant types [release 0.3.0](../../docs/releases/0.3.0-experiments.md#completing-this-specification) may offer, as [D-20](../../docs/spec.md#decisions) requires. Each check is a real `trialfolio run` of a screen configuration that changes one setting from its baseline, followed by a `trialfolio review` that compares the two.

This run record and the configurations beside it are committed. The runs and the reviews hold Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from a response except the credits used and which metrics changed. The review configurations name their runs by paths relative to themselves, in `payloads/runs/`.

## Settings

On 2026-10-07 the owner approved five live runs with a budget of 35 credits, 25 of them expected, and was present for them. The owner also decided:

- **What verified means.** A variant type is verified only when Portfolio123 accepts its value and at least one metric changes against its baseline, as [R01-T05](../p123api-screen-backtest-values/README.md#checks-against-the-response-layout) checked. A value that's accepted and silently ignored doesn't pass.
- **Holdings.** The [0.2.0 live exercise](../review-live-exercise/README.md)'s run with `max_holdings: 50` counts as the evidence for holdings, so no new run was needed.
- **The broad universe.** The microcap and slice checks use `Easy to Trade US`, a universe Portfolio123 provides. On SP500, a microcap rule would remove nothing, so it couldn't show the rule works.

Every check keeps the [live check](../p123api-live-check/README.md)'s settings, those of [`formula.yaml`](../../tests/fixtures/screen-configs/formula.yaml): `AvgDailyTot(30) > 1000000`, ranked by `EarnYield`, 25 holdings, `SPY`, 2016-01-01 to 2025-12-31, every 4 weeks, at the open, with 0.25% slippage. Each changes one thing:

| Configuration | Change | Baseline |
|---|---|---|
| [`slippage-050.yaml`](slippage-050.yaml) | `slippage_percent: 0.5` | The live check's run, on SP500 |
| [`liquidity-100m.yaml`](liquidity-100m.yaml) | The liquidity rule's threshold, from 1 million to 100 million dollars a day: `AvgDailyTot(30) > 100000000` | The live check's run |
| [`easy-to-trade.yaml`](easy-to-trade.yaml) | `universe: 'Easy to Trade US'` | The live check's run. The universe isn't a variant ([D-19](../../docs/spec.md#decisions)): this run is the baseline of the next two, and its review shows that Portfolio123 used the universe it names. |
| [`no-microcaps.yaml`](no-microcaps.yaml) | An added rule, `MktCap > 300`, which excludes stocks with a market cap of 300 million dollars or less | `easy-to-trade` |
| [`slice-0.yaml`](slice-0.yaml) | An added rule, `Mod(StockID,4) = 0`, the first of four universe slices ([METH-09.5](../../docs/methodology.md#meth-09-reproducing-published-research)) | `easy-to-trade` |

Each ranks by a single formula, so nothing in the account was created or changed. The live check's run was reviewed as a copy in `payloads/runs/live-check`, at no cost.

## Run record

Date: 2026-10-07, 13:19 to 13:22 UTC. Trial Folio 0.2.1, from `main` at 9c23c31; macOS 26.6.2, Python 3.14.8, and the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0. Each command ran with `TRIALFOLIO_ACCEPT_LICENSE` set, and only the runs had the credentials, injected as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes. Before the live runs, each configuration ran without `--approve`, which checked it and gave its plan hash, sent nothing, and created no output.

Each run was `trialfolio run <configuration> --out payloads/runs/<name> --approve <plan hash> --json`:

| Run | Plan hash | Outcome |
|---|---|---|
| `slippage-050` | `sha256:dc9298ebd6bcbd17cca40ee5d5b3b034df0d54bda991c843f5dcc20b8e1bdf9e` | Exit 0, `completed`: one attempt, `succeeded`, and one provider request. 5 credits, as Portfolio123 reported. All 20 metrics available. |
| `liquidity-100m` | `sha256:ad51007865a44fa1f96a980514c92efbd9de7051483f20187b56a2bfb6dd2c78` | The same, 5 credits |
| `easy-to-trade` | `sha256:ee876d1859ff8e1f922ae042259614490c7d596814b2f6280db9686605f65fc0` | The same, 5 credits |
| `no-microcaps` | `sha256:a64dc4b851e5f08fbe727b4b35c121bdd7ad235286e70c9ef5e456a80e0ed641` | The same, 5 credits |
| `slice-0` | `sha256:f56cb57a6a9cabb4b2630352ca0d700df98e2dc6baefcbfdc8ac8609cb9cd030` | The same, 5 credits |

Twice, the secret manager's authorization didn't complete, once by timeout and once dismissed, before `no-microcaps` and `slice-0`. Each time the command stopped before Trial Folio started: no output directory was created, and nothing was sent. Each was run again, once.

**Credits:** 25, as Portfolio123 reported, within the budget of 35. The broad universe cost the same 5 credits as SP500. Authentication's cost wasn't measured. No request failed, so whether a failed request is charged is still unknown.

## The reviews

| Review | Outcome |
|---|---|
| `trialfolio review review-sp500.yaml --out payloads/reviews/sp500 --json`: [`review-sp500.yaml`](review-sp500.yaml), the first three runs against the live check's | Exit 0, no warning, `settings_flagged` 0. Each result's declared setting is an `intended_change`, and each of its other 22 settings is `same`. `universe` is flagged `not_snapshotted`, as every universe is. |
| `trialfolio review review-easy-to-trade.yaml --out payloads/reviews/easy-to-trade --json`: [`review-easy-to-trade.yaml`](review-easy-to-trade.yaml), the microcap and slice runs against `easy-to-trade` | Exit 0, no warning, `settings_flagged` 0. Each result's `rules` is an `intended_change`, and each of its other 22 settings is `same`. |

All 20 metrics of every result were differenced. The metrics that changed, out of 20:

| Result | Changed | Unchanged |
|---|---|---|
| `slippage-050` | 9 | The coverage (3), the risk samples, the benchmark's six, and `r_squared`. Slippage lowers each period's return without changing how the returns move with the benchmark's. |
| `liquidity-100m` | 10 | The coverage, the risk samples, and the benchmark's six, which no change to the strategy can move |
| `easy-to-trade` | 10 | The same |
| `no-microcaps` | 10 | The same |
| `slice-0` | 10 | The same |

So every strategy metric changed, and the [0.2.0 live exercise](../review-live-exercise/README.md)'s `max_holdings: 50` changed the same 10.

**The credentials.** A scan after the runs found the API key in no file of the runs or the reviews, and nowhere in the commands' stderr or JSON summaries. The API ID matched inside the six saved responses, Portfolio123's own data, and nowhere else: not in the logs, the reports, the normalized tables, the plans, the configurations, the attempts' other records, or the reviews.

## Findings for R03-T01

- **Slippage is verified as a variant.** Portfolio123 accepted 0.5%, and the strategy's metrics changed.
- **A liquidity rule is verified as a variant.** A changed threshold in a rule was accepted and took effect.
- **Added rules are verified.** Portfolio123 accepted a screen of two rules, and each added rule, the microcap cutoff and the slice, took effect. So microcap exclusion and universe slices can be written as screen rules.
- **`StockID`'s stability isn't verified.** One backtest of one slice can't show that `StockID` stays the same for a stock across the test period, which [METH-09.5](../../docs/methodology.md#meth-09-reproducing-published-research) requires before a study relies on the slices.
- **A universe other than SP500 works,** and Portfolio123 used the one it names: the strategy's metrics differ from SP500's.
- **Holdings and rebalancing were already verified:** `max_holdings` by the 0.2.0 live exercise, and `rebalance_weeks` 1 and 4 by R01-T05 and R01-T01.
