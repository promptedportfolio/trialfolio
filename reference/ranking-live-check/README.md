# Live check: ranking-weight variants

This is the run record of [release 0.4.0](../../docs/releases/0.4.0-ranking-weights.md)'s live check, R04-AC07, which R04-T13 ran with [`tests/live/test_ranking.py`](../../tests/live/test_ranking.py), as the release's [verification commands](../../docs/releases/0.4.0-ranking-weights.md#verification-commands-and-expected-evidence) describe. Its experiment writes each case's ranking definition into `ApiRankingSystem` with `rank_update`, then backtests the screen ranked by that system; a screen run then writes the baseline's definition again; and a snapshot of `ApiRankingSystem` reads back what the account holds.

This record is committed. The runs, the experiment, and the snapshot hold Portfolio123's data and the account's, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from them except outcomes, counts, which metrics changed, the credits used, and how Portfolio123 stores a definition it's sent. No result, ID, or account value is given. The definition sent, [`live.xml`](../../tests/fixtures/experiment-configs/ranking/live.xml), is a committed, synthetic one.

## Settings

- **The budget.** The owner approved 19 credits on 2026-10-19, for the check's three plans: 12 for the experiment, 6 for the restore, and 1 for the snapshot, at the documented costs. After the first run, the owner approved 19 more the same day, to run the corrected check again. The owner was present for both runs.
- **The configurations:**
  - the experiment, [`experiment-configs/ranking-live.yaml`](../../tests/fixtures/experiment-configs/ranking-live.yaml): [`formula.yaml`](../../tests/fixtures/screen-configs/formula.yaml)'s screen settings, ranked by `live.xml`, two top-level composites at 50 each, each holding one factor, `EarnYield` and `AvgDailyTot(30)`, with `percentile_nas_negative`; and one ranking variant, `earnings-heavy`, which sets the composites to 80 and 20;
  - the restore, [`screen-configs/ranking-live.yaml`](../../tests/fixtures/screen-configs/ranking-live.yaml): the experiment's baseline as a screen run;
  - the snapshot, [`ranking-snapshot-configs/api-ranking-system.yaml`](../../tests/fixtures/ranking-snapshot-configs/api-ranking-system.yaml): `ApiRankingSystem`, the system Trial Folio writes.
- **The commands.** The installed `trialfolio run`, with `--approve` and each plan's hash, into new directories under `payloads/`, with the credentials injected for the command, as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes. Only the three runs could reach Portfolio123's API host, besides localhost, and they took the machine's ranking lock. The offline steps ran without the credentials, so nothing could be sent: under the full guard in the second run, and by hand, without the guard, after the first.
- **Before the checks,** the owner noted the account's ranking systems in the website. `ApiRankingSystem` was among them, since R04-T01.

## Run record

Both runs were on 2026-10-19, on macOS 26.6.2 with Python 3.14.8, on the branch `test/r04-t13-tests-and-verification`, from `main` at de5b187. The versions were:
- Trial Folio 0.4.0;
- the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0.

**The first run,** from 17:46:35 to 17:46:40 UTC, at 3e9a5ad, with the offline steps run by hand afterwards, from 17:48 UTC:

| Step | Outcome | Credits, as Portfolio123 reported |
|---|---|---|
| 1. The experiment | Exit 0, `completed`. Both cases succeeded, after one `POST /auth`: each sent `POST /rank` and then `POST /screen/backtest`, each a 200. 4 provider requests. `earnings-heavy`'s `metrics.csv` differs from the baseline's in 10 metrics: the strategy's total and annualized return, maximum drawdown, standard deviation, Sharpe and Sortino ratios, correlation, R-squared, beta, and alpha. | 12 |
| 2. The restore | Exit 0, `completed`, after `POST /auth`, `POST /rank`, and `POST /screen/backtest`, each a 200. Its case is the experiment's baseline case, by its `case_id`, and all 20 values of its `metrics.csv` equal the baseline case's. | 6 |
| 3. The snapshot | Exit 0, `completed`, with ranking method 2, `USD`, and `Stock`. Its `definition.xml` isn't the definition the restore sent, byte for byte, so the check failed here, as it was written then. As XML it is the same, by its canonical form, with the same elements, attributes, values, and text: Portfolio123 stored the definition in its own serialization. It wrote each `StockFormula`'s attributes in the order `Weight`, `RankType`, `Name`, `Description`, and `Scope`, where `live.xml` writes `Name` first, and left out the final line feed. Each composite's attributes, which `live.xml` writes in the order Portfolio123 does, kept their bytes. Run by hand, without credentials, the restore's configuration with the snapshot in place of its definition planned offline, with the restore's weights, and created nothing; its `case_id` isn't the restore's, since a case is identified by its definition's bytes. | 1 |
| 4. The resume | Run by hand, without credentials: exit 0, `completed`, `sessions/2/`, nothing sent, and no ranking lock taken. | 0 |

**The second run,** from 18:23:45 to 18:23:50 UTC, with the check corrected as the owner decided after the first ([changes after sign-off](../../docs/releases/0.4.0-ranking-weights.md#changes-after-sign-off)), at f382136: the snapshot's `definition.xml` is checked as the restore's definition as XML, and the restore's configuration naming it as planning offline with the restore's weights, as the restore's case exactly when the snapshot holds the definition's bytes. The check passed, every step:

| Step | Outcome | Credits, as Portfolio123 reported |
|---|---|---|
| 1. The experiment | As in the first run: both cases succeeded after one `POST /auth`, 4 provider requests, and the same 10 metrics of `earnings-heavy` differ from the baseline's. The baseline's metrics equal the first run's. | 12 |
| 2. The restore | As in the first run: the baseline's case, and all 20 values equal the baseline case's. | 6 |
| 3. The snapshot | Ranking method 2, `USD`, and `Stock`. Its `definition.xml` is the restore's definition as XML, and byte for byte the first run's snapshot's, so Portfolio123 serialized it the same way both times. The restore's configuration naming it planned offline, without credentials, with the restore's weights, as another case, and created nothing. | 1 |
| 4. The resume | Exit 0, `completed`, `sessions/2/`, under the full guard and without credentials, nothing sent, and no ranking lock taken: the experiment's log names one `ranking.lock.taken`, the first session's. | 0 |

**Credits:** 38 in all, 19 for each run, each as Portfolio123 reported it in the call's response: 1 for each `rank_update` and `rank_get`, and 5 for each backtest, as documented. Authentication's cost wasn't measured. Each run used its approved budget of 19, and no more.

**After each run,** the owner compared the account's ranking systems with the list from before the checks: none but `ApiRankingSystem` had changed, so Trial Folio wrote no other ranking system (R04-AC07, R04-AC09). It now holds `live.xml`'s definition, as Portfolio123 stores it, with ranking method 2.

## Findings

- **The route works with a definition Trial Folio sends** (R04-AC07): a changed weight, written into `ApiRankingSystem`, changed 10 of the strategy's metrics, and the baseline's definition, written again, restored every metric of the baseline case, in both runs. So a backtest uses the definition just written, as R04-T01 found.
- **Portfolio123 stores a definition as equivalent XML, not always byte for byte.** R04-T01's step 2 found that `rank_get` returns the XML `rank_update` sent, byte for byte. It had sent a saved system's XML, as Portfolio123 itself wrote it. Sent `live.xml`, which writes its factors' attributes in another order and ends with a line feed, Portfolio123 returned it in its own serialization. The owner decided on 2026-10-19 that Trial Folio's documents say so, and that the live check expects the definition back as XML ([changes after sign-off](../../docs/releases/0.4.0-ranking-weights.md#changes-after-sign-off)). A case's records hold the definition it sent, byte for byte, as before; a snapshot of `ApiRankingSystem` holds the definition as Portfolio123 stores it.
