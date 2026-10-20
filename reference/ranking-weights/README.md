# Live checks: the ranking-system route

These are the live checks of task R04-T01, which verifies how [release 0.4.0](../../docs/releases/0.4.0-ranking-weights.md) can send a ranking system's definition to a screen backtest, and which ranking variants Portfolio123 accepts and uses, as [D-20](../../docs/spec.md#decisions) requires. Each check writes a definition into `ApiRankingSystem` with `rank_update`, then backtests the live check's screen ranked by that system, and `trialfolio review` compares the runs.

This run record, the script, and the configurations beside it are committed. The ranking systems' definitions, the responses, the runs, and the reviews hold the owner's account information and Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from them except counts, positions, which metrics changed, and the credits used. No ranking system is named here, and no weight, formula, or result is given.

## Settings

- **The budget.**
  - The owner approved 25 credits on 2026-10-12, and raised the budget to 37 the same day, to check a weight change within a composite and a factor removal too ([D-34](../../docs/spec.md#decisions)).
  - During the checks, the first two saved systems turned out to have no composite. The owner then approved up to 100 credits, "but only use as many as needed".
  - Steps 1 to 7 used 39.
  - After the first review of the checks' pull request, the owner approved 2 more credits for step 8, which used them: 41 in all.
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
  - [`route.py`](route.py) made the `rank_get` and `rank_update` calls through `p123api`, with the wrapper's retries set to 1, and the offline weight changes. The review of R04-T01's pull request changed it after the checks: [the script after the checks](#the-script-after-the-checks) says how, and what that means for this record.
  - `trialfolio run` ran each backtest, with `--approve` and the plan hash.
  - `trialfolio review` compared each run with its baseline: [`review-step3.yaml`](review-step3.yaml) to [`review-step7.yaml`](review-step7.yaml). After the checks, offline and with no credits, [`review-step7-vs-step6.yaml`](review-step7-vs-step6.yaml) compared step 7's run with step 6's.
  - The credentials were injected for each command, as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes.
- **Before the checks,** the owner looked at the account's ranking systems in the website: `ApiRankingSystem` wasn't among them.

## Run record

Date: 2026-10-12, 12:25:23 to 12:37:15 UTC, on macOS 26.6.2 with Python 3.14.8, on the branch `docs/r04-t01-ranking-route`, from `main` at 33853ec. The versions were:
- Trial Folio 0.3.0;
- the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0.

| Step | Calls | Outcome | Credits, as Portfolio123 reported |
|---|---|---|---|
| 1 | `rank_get` of A, B, and C | Each succeeded. Each returned the name asked for, an ID, ranking method 2 (Percentile NAs Negative), currency USD, type Stock, and XML that reads as nodes with names and weights, written as plain numbers. A's 8 factors are 5 `StockFormula` nodes and 3 `StockFactor` nodes, a node type Portfolio123's [ranking-definition article](https://portfolio123.customerly.help/en/articles/13793-dataminer-ranking-definition) doesn't list. B's and C's are `StockFormula` nodes. C's composites each hold factors whose weights sum to 100. C's three top-level weights are whole numbers that don't sum to 100. | 1 + 1 + 1 |
| 2 | `rank_update` with C's XML, `rankingMethod` 2, and currency `USD`; then `rank_get` of `ApiRankingSystem` | The update succeeded, and its response held only `cost` and `quotaRemaining`, with no ID. The owner then found `ApiRankingSystem` in the website, under that name. `rank_get` by that name returned it with its ID, kept in `payloads/`. It held the XML sent, byte for byte, and ranking method 2 and USD, the values sent, which are also the three saved systems'. | 1 + 1 |
| 3 | Backtest ranked by `ApiRankingSystem`; backtest ranked by C | Both completed, every metric available. The review found only the `ranking` setting different, as declared, and all 20 metrics equal. | 5 + 5 |
| 4 | Move weight between two top-level composites, keeping their sum; `rank_update`; backtest ranked by `ApiRankingSystem` | The script moved weight from the top-level composite with the largest weight to another, and two weights were sent with a decimal; Portfolio123 accepted them. The review against step 3's `ApiRankingSystem` run found 10 metrics changed: the strategy's total and annualized return, maximum drawdown, standard deviation, Sharpe and Sortino ratios, correlation, R-squared, beta, and alpha. The benchmark's 6 metrics, the 3 coverage rows, and the strategy's `risk_samples` were equal. | 1 + 5 |
| 5 | `rank_update` with C's XML again; backtest | All 20 metrics equal step 3's: the backtest used the definition just written, not cached ranks | 1 + 5 |
| 6 | From C's XML, move 10 points between the two factors of one composite, keeping their sum; `rank_update`; backtest | The same 10 strategy metrics changed against step 3's run | 1 + 5 |
| 7 | From C's XML, remove one of a composite's two factors; the one left gets 100, its weight scaled in proportion; `rank_update`; backtest | Portfolio123 accepted a composite with one factor. The same 10 strategy metrics changed against step 3's run. After the checks, offline and with no credits, a review against step 6's run found no setting different, and the same 10 metrics changed, the other 10 equal. So step 7's backtest didn't use step 6's definition, which `ApiRankingSystem` held before step 7's `rank_update`: the removal took effect. | 1 + 5 |

**Step 8** ran after the first review of the checks' pull request, which found that steps 1 to 7 don't show that `rank_update` stores the ranking method it's sent. The owner decided to check it, approved 2 credits, and was present. It ran on 2026-10-12, 13:52:54 to 13:52:58 UTC, with `route.py` as changed after the checks, at 55dd62a ([the script after the checks](#the-script-after-the-checks)).

| Step | Calls | Outcome | Credits, as Portfolio123 reported |
|---|---|---|---|
| 8 | `rank_update` with C's XML, `rankingMethod` 4 (Percentile NAs Neutral), and currency `USD`, into `ApiRankingSystem`, which held ranking method 2; then `rank_get` of `ApiRankingSystem` | Each call made one exchange after authenticating: `POST /auth 200`, then `POST /rank 200` for the update and `GET /rank 200` for the read. The update's response held only `cost` and `quotaRemaining`. `rank_get`'s held `cost`, `currency`, `groupUid`, `id`, `name`, `quotaRemaining`, `rankingMethod`, `resolveGroupUid`, `type`, and `xml`: the name asked for, ranking method 4, currency USD, type Stock, and the XML sent, byte for byte. So `rank_update` stores the ranking method it's sent: the existing system's changed from 2 to 4. | 1 + 1 |

**Credits:** 41, 39 for steps 1 to 7 and 2 for step 8, each as Portfolio123 reported it in the call's response: 1 for each `rank_get` and `rank_update`, and 5 for each backtest, as documented. Authentication's cost wasn't measured.

**After steps 1 to 7,** the owner compared the account's ranking systems with the list from before: only `ApiRankingSystem` had changed, so `rank_update` touched no other ranking system. It then held step 7's definition. Step 8 wrote C's definition into it with ranking method 4, which it holds now. After step 8, the owner looked at C in the website: its ranking method was still 2, so step 8 too wrote only `ApiRankingSystem`, and no saved system was written by any step.

**A scan of every file steps 1 to 7 wrote,** 156 files, found the API key in none. The API ID matched once, inside a longer number in step 4's saved response: digits that happen to coincide.

## The script after the checks

The review of R04-T01's pull request found the following in [`route.py`](route.py) as it ran, and changed the script after the checks. The changed script was exercised offline, against a local fake server, before it made step 8's calls.

- **One HTTP attempt per call.** As run, the script set the wrapper's retries to 1. That stops its retries after a connection error or a 5xx, but not its re-authentication: after a 401 or a 403, `p123api` 3.1.0 authenticates again and sends the call again. So the script as run in steps 1 to 7 didn't ensure one attempt per call, and it recorded no exchanges. Every `rank_get` and `rank_update` in them succeeded, and Portfolio123 reported 1 credit for each. The script now authenticates in a call of its own, and sends each call through Trial Folio's `ExchangeRecordingAdapter` ([ADR 0006](../../docs/adrs/0006-observe-the-wrappers-http-exchanges.md)), which refuses a second exchange in a call before it's sent. It saves each call's exchanges.
- **The credits of the four reads.** As run, the script saved `rank_get`'s fields as `p123api` returns them, which leaves out `cost` and `quotaRemaining`. The credits it printed came from the same response, through the wrapper's `cost`, but the saved responses of the four `rank_get` calls, step 1's three and step 2's, don't hold them. The script now saves each response's body as Portfolio123 sent it.
- **A failure's message.** As run, the script would have printed Portfolio123's message on a failed call, unless the message named part of the definition sent, and saved it as it was. No call failed. The script now prints only the exception's type and the exchanges, and saves the message with the credentials and the token redacted.
- **Line endings.** As run, the script read the XML files with `read_text`, which makes a carriage return a line feed. Counted offline after the checks, step 1's saved XML of C and step 2's read-back each hold no carriage return. So the script's reading changed nothing: step 2 sent C's XML unchanged, and the byte-for-byte comparison holds for the website's own XML. The script now reads and writes files with their line endings unchanged. On XML without a carriage return, its variants are byte for byte the ones it wrote before.
- **The amount moved.** As run, the weight change printed the amount it moved, which can give a weight away. It now prints only whether the new weights are whole.

The pull request's third review, after step 8, found more in the script as step 8 ran it, and changed it again. The changed script was exercised offline, against a local fake server.

- **A failed call's evidence.** As step 8 ran it, the script saved a call's exchanges, and its 200's body, only when the call succeeded. A failed call kept only its message, even one that failed after a 200, on a body the wrapper couldn't decode, such as malformed JSON or a ranking method `p123api` doesn't know. The script now saves the exchanges, and any 200's body, however the call ended.
- **A file that can't be saved.** As step 8 ran it, the script saved a failure's message inside the handler of the wrapper's exception. Had that save failed, Python would have printed the exception, with Portfolio123's message unredacted. Only the exception's type and its redacted message now leave the handler, and a file the script can't save is reported with the operating system's reason alone.
- **The TLS key log.** Neither the script as step 8 ran it nor as steps 1 to 7 ran it removed `SSLKEYLOGFILE`. `urllib3` writes TLS session keys to the file it names, whatever `requests`' environment settings, and the keys would let anyone with a capture of the traffic read the credentials and the token. The script now removes it from its own environment before a call, with a warning, as Trial Folio's CLI does ([credentials](../../docs/contracts.md#credentials)).

The first two don't bear on steps 1 to 8: every call in them succeeded, so neither failure path ran. The key log would have only if `SSLKEYLOGFILE` was set when the script made a call, and this record doesn't say whether it was. It wasn't set in the environment this change was checked in, on the owner's machine, and none of the shell's startup files there sets it. The backtests ran through `trialfolio run`, which removes it.

## Findings for R04-T02 and R04-T03

- **The route works.** `rank_update` writes the definition into `ApiRankingSystem`, and a backtest ranked by that name uses it at once. No `rank_touch` was needed between them, within about a minute (step 5).
- **The name is `ApiRankingSystem`,** the Rank API documentation's spelling. The first `rank_update` creates it: it wasn't in the account before step 2, and was after.
- **`rank_get` returns the XML `rank_update` sent, byte for byte,** so a case can record the definition it sent, and needn't read the XML back. R04-T13's live check found on 2026-10-19 that this holds for XML Portfolio123 wrote itself, such as C's: Portfolio123 stores a definition it's sent as equivalent XML, in its own serialization ([its run record](../ranking-live-check/README.md)).
- **`rank_update` stores the ranking method it's sent.** Step 8 sent method 4 to the existing `ApiRankingSystem`, which held 2, and read back 4. Steps 1 to 7 couldn't show it: step 2 sent method 2, the three saved systems' method, to a system the call created.
- **`rank_update` accepts `currency`,** but every step sent USD, the saved systems' currency, so whether the call stores another currency isn't shown. That's left to R04-T02.
- **`rank_update`'s response** holds only `cost` and `quotaRemaining`: no ID, and no echo of the definition.
- **Weights:**
  - The XML writes them as plain numbers.
  - A saved system's top-level weights needn't sum to 100.
  - Portfolio123 accepts weights with a decimal.
  - A composite with one factor is accepted, and used (step 7).
- **Node types:** `StockFactor` exists beside `StockFormula`, holding a `Factor` element where a `StockFormula` holds a `Formula`.
- **Composites aren't universal.** Two of the owner's three saved systems are flat, so a weight change within a composite, and the removal of a composite's factor, need a system that has one.
