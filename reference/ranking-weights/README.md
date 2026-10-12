# Live checks: the ranking-system route

These are the live checks of task R04-T01, which verifies how [release 0.4.0](../../docs/releases/0.4.0-ranking-weights.md) can send a ranking system's definition to a screen backtest, and which ranking variants Portfolio123 accepts and uses, as [D-20](../../docs/spec.md#decisions) requires. Each check writes a definition into `ApiRankingSystem` with `rank_update`, then backtests the live check's screen ranked by that system, and `trialfolio review` compares the runs.

This run record, the script, and the configurations beside it are committed. The ranking systems' definitions, the responses, the runs, and the reviews hold the owner's account information and Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from them except counts, positions, which metrics changed, and the credits used. No ranking system is named here, and no weight, formula, or result is given.

## Settings

- **The budget.**
  - The owner approved 25 credits on 2026-10-12, and raised the budget to 37 the same day, to check a weight change within a composite and a factor removal too ([D-34](../../docs/spec.md#decisions)).
  - During the checks, the first two saved systems turned out to have no composite. The owner then approved up to 100 credits, "but only use as many as needed".
  - The checks used 39.
  - The owner was present throughout.
- **The ranking systems.** Three of the owner's saved systems, whose names and IDs stay in `payloads/`, because they're account information:
  - **A:** 8 top-level factors, no composite.
  - **B:** 4 top-level factors, no composite.
  - **C:** 3 top-level composites, each holding 2 factors.

  Steps 6 and 7 need a composite, so step 1 read all three, and steps 2 to 7 ran on C.
- **The screen.** The [live check](../p123api-live-check/README.md)'s, [`formula.yaml`](../../tests/fixtures/screen-configs/formula.yaml)'s settings, ranked by a system's name:
  - [`api-ranking-system.yaml`](api-ranking-system.yaml), ranked by `ApiRankingSystem`;
  - a copy ranked by C's name, kept in `payloads/`.
- **The calls.**
  - [`route.py`](route.py) makes the `rank_get` and `rank_update` calls through `p123api`, with one HTTP attempt per call. It also makes the offline weight changes.
  - `trialfolio run` ran each backtest, with `--approve` and the plan hash.
  - `trialfolio review` compared each run with its baseline: [`review-step3.yaml`](review-step3.yaml) to [`review-step7.yaml`](review-step7.yaml).
  - The credentials were injected for each command, as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes.
- **Before the checks,** the owner looked at the account's ranking systems in the website: `ApiRankingSystem` wasn't among them.

## Run record

Date: 2026-10-12, 12:25:23 to 12:37:15 UTC, on macOS 26.6.2 with Python 3.14.8, on the branch `docs/r04-t01-ranking-route`, from `main` at 33853ec. The versions were:
- Trial Folio 0.3.0;
- the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0.

| Step | Calls | Outcome | Credits, as Portfolio123 reported |
|---|---|---|---|
| 1 | `rank_get` of A, B, and C | Each succeeded. Each returned the name asked for, an ID, ranking method 2 (Percentile NAs Negative), currency USD, type Stock, and XML that reads as nodes with names and weights, written as plain numbers. A's 8 factors are 5 `StockFormula` nodes and 3 `StockFactor` nodes, a node type Portfolio123's [ranking-definition article](https://portfolio123.customerly.help/en/articles/13793-dataminer-ranking-definition) doesn't list. B's and C's are `StockFormula` nodes. C's composites each hold factors whose weights sum to 100. C's three top-level weights are whole numbers that don't sum to 100. | 1 + 1 + 1 |
| 2 | `rank_update` with C's XML, `rankingMethod` 2, and currency `USD`; then `rank_get` of `ApiRankingSystem` | The update succeeded, and its response held only `cost` and `quotaRemaining`, with no ID. The owner then found `ApiRankingSystem` in the website, under that name. `rank_get` by that name returned it with its ID, kept in `payloads/`. It held the XML sent, byte for byte, ranking method 2, and USD. | 1 + 1 |
| 3 | Backtest ranked by `ApiRankingSystem`; backtest ranked by C | Both completed, every metric available. The review found only the `ranking` setting different, as declared, and all 20 metrics equal. | 5 + 5 |
| 4 | Move weight between two top-level composites, keeping their sum; `rank_update`; backtest ranked by `ApiRankingSystem` | The script moved 0.5 points, half of the largest top-level weight, so two weights were sent with a decimal; Portfolio123 accepted them. The review against step 3's `ApiRankingSystem` run found 10 metrics changed: the strategy's total and annualized return, maximum drawdown, standard deviation, Sharpe and Sortino ratios, correlation, R-squared, beta, and alpha. The benchmark's 6 metrics and the 4 coverage rows were equal. | 1 + 5 |
| 5 | `rank_update` with C's XML again; backtest | All 20 metrics equal step 3's: the backtest used the definition just written, not cached ranks | 1 + 5 |
| 6 | From C's XML, move 10 points between the two factors of one composite, keeping their sum; `rank_update`; backtest | The same 10 strategy metrics changed against step 3's run | 1 + 5 |
| 7 | From C's XML, remove one of a composite's two factors; the one left gets 100, its weight scaled in proportion; `rank_update`; backtest | Portfolio123 accepted a composite with one factor. The same 10 strategy metrics changed against step 3's run. | 1 + 5 |

**Credits:** 39, each as Portfolio123 reported it in the call's response: 1 for each `rank_get` and `rank_update`, and 5 for each backtest, as documented. Authentication's cost wasn't measured.

**After the checks,** `ApiRankingSystem` holds step 7's definition, the last one written. The owner's comparison of the account's ranking systems after the checks is pending.

**A scan of every file the checks wrote,** 156 files, found the API key in none. The API ID matched once, inside a longer number in step 4's saved response: digits that happen to coincide.

## Findings for R04-T02 and R04-T03

- **The route works.** `rank_update` writes the definition into `ApiRankingSystem`, and a backtest ranked by that name uses it at once. No `rank_touch` was needed between them, within about a minute (step 5).
- **The name is `ApiRankingSystem`,** the Rank API documentation's spelling. The first `rank_update` creates it: it wasn't in the account before step 2, and was after.
- **`rank_update` takes `rankingMethod` and `currency`, and stores them.** `rank_get` returns the XML byte for byte, so a case can record the definition it sent, and needn't read it back.
- **`rank_update`'s response** holds only `cost` and `quotaRemaining`: no ID, and no echo of the definition.
- **Weights:**
  - The XML writes them as plain numbers.
  - A saved system's top-level weights needn't sum to 100.
  - Portfolio123 accepts weights with a decimal.
  - A composite with one factor is accepted.
- **Node types:** `StockFactor` exists beside `StockFormula`, holding a `Factor` element where a `StockFormula` holds a `Formula`.
- **Composites aren't universal.** Two of the owner's three saved systems are flat, so a weight change within a composite, and the removal of a composite's factor, need a system that has one.
