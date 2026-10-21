# Live checks: a stale backtest after `rank_update`

These are the live checks that followed the [walk-through of 0.4.0](../ranking-walkthrough/README.md), which found an experiment's backtest ranked by the definition `ApiRankingSystem` held before its `rank_update`, though the `rank_update` got a 200. The owner decided on 2026-10-20 to measure it before deciding the fix: how often a backtest sent right after a `rank_update` ranks by the previous definition, whether `rank_touch` prevents it, and whether a pause does. Portfolio123's Rank API page says that `rank_touch` "Forces a flush of all cached ranks", at 1 credit.

This run record and the script, [`diagnose.py`](diagnose.py), are committed. The definitions, the responses, and the system's ID hold the owner's account information and Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from them except counts, times, labels, and the credits used. No ranking system is named here, and no weight, formula, or result is given.

## Settings

- **The budget.** The owner approved 61 credits for stage 1 on 2026-10-20, and up to 140 for what followed, sized after stage 1. The owner chose stage 2's size, 10 writes, and stage 3's settings on 2026-10-21, and was present for each stage.
- **The definitions.** Two, each written into `ApiRankingSystem`:
  - **A,** the walk-through's baseline: the definition of C, of [R04-T01's checks](../ranking-weights/README.md#settings), as its snapshot read it.
  - **B,** the walk-through's V1, which moved weight among A's three top-level composites.
- **The backtest.** The request the walk-through's experiment sent for its baseline case, byte for byte: the starter screen's settings, ranked by `ApiRankingSystem`.
- **The script.** Each stage is one command of `diagnose.py writes`, which authenticates once, then writes B, A, B, and so on into `ApiRankingSystem`, each `rank_update` followed by the backtest. Its calls go through Trial Folio's own provider client, each allowed one HTTP exchange, with no retry. It labels each backtest by the response it returns, compared without `cost` and `quotaRemaining`: `fresh` when it's the response most of the writes of its own definition return in the stage, and `stale` when it's the other definition's. `diagnose.py id` read the system's ID, which `rank_touch` needs, with one `rank_get`. The script was checked offline, against the fake Portfolio123 server, before stage 1, and again once `--pause` was added.
- **The credentials** were injected for each command alone, as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes.

## Run record

Date: 2026-10-21, on macOS 26.6.2 with Python 3.14.8, from the branch `fix/ranking-stale-backtest`: stages 1 and 2 at eb6bf2d, and stage 3 at a91e994, which added `--pause`. The versions were Trial Folio 0.4.0, and the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0.

| Stage | Between the `rank_update`'s 200 and the backtest | Writes | Stale | Credits, as Portfolio123 reported |
|---|---|---|---|---|
| 1, 11:32:52 to 11:32:58 UTC | Nothing | 10 | 4: writes 3 and 5 (B), and 8 and 10 (A) | 60 |
| The ID, 11:33:45 UTC | One `rank_get` of `ApiRankingSystem` | | | 1 |
| 2, 12:13:33 to 12:13:40 UTC | `rank_touch` of `ApiRankingSystem`, by its ID; 0.04 to 0.05 seconds in all | 10 | 3: writes 4 and 10 (A), and 7 (B) | 60 |
| 3, 12:30:03 to 12:31:50 UTC | A pause of 10 seconds, without `rank_touch` | 10 | 0 | 60 |

- **Every stale backtest was stale by one:** it returned exactly the response of the definition written before it.
- **The store isn't stale.** The `rank_get` after stage 1 returned A, byte for byte, the definition write 10 sent, though write 10's backtest had returned B's response. So a read-back can't tell a stale backtest from a fresh one.
- **`rank_touch` doesn't prevent it.** Stage 2 sent it between every `rank_update` and its backtest, and each touch got a 200, but 3 of 10 backtests were still stale. Portfolio123 reported 60 credits for stage 2's writes and backtests, and the remaining credits it reported fell by 60, so the touches cost nothing, though the page gives 1 credit.
- **A pause of 10 seconds prevented it** in stage 3's 10 writes. Without a pause, 8 of 25 backtests were stale, counting the walk-through's 5 that could be checked. At that rate, 10 fresh backtests in a row would happen by chance about 2% of the time. No shorter pause was measured.
- **Portfolio123's data changed overnight.** A's response in stage 1 differed from the walk-through's response for the same definition in 2 of its 2,609 daily returns, and B's was the same. So each stage labels its backtests by its own responses, not by the walk-through's.

**Credits:** 181, as Portfolio123 reported, within the 201 approved: 60 for each stage, and 1 for the ID's `rank_get`. With the walk-through's 37, 218. Authentication's cost wasn't measured.

The owner decided on 2026-10-21 to drop `rank_touch`, to wait 10 seconds between each `rank_update`'s 200 and its backtest, and to flag a backtest whose response repeats the previous case's ([D-45](../../docs/spec.md#decisions)).

## The files

`payloads/` holds, for each stage, `stage-1/` to `stage-3/`, each write's `rank_update` and backtest, with their exchanges, and the stage's `summary.json`; and the ID's `rank_get`, in `id-rank-get.json` and `api-ranking-system.json`.
