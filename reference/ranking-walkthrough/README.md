# Live runs: the owner's walk-through of 0.4.0

These are the live runs from the walk-through of [release 0.4.0](../../docs/releases/0.4.0-ranking-weights.md)'s ranking definitions, ranking variants, and snapshots, which an agent ran with the owner present on 2026-10-20, before the owner's own private use. It took a snapshot of a saved ranking system, ran an experiment of three ranking variants of its definition, and ran two screens to check what the experiment found. The [verification record](../../docs/releases/0.4.0-verification.md#the-live-walk-through) gives what it found, and the [diagnostic's run record](../ranking-touch/README.md) the live checks that followed.

This run record is committed. The runs hold the owner's account information and Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from them except counts, times, which metrics changed, and the credits used. No ranking system is named here, and no weight, formula, or result is given.

## Settings

On 2026-10-20 the owner approved live calls with a budget of 40 credits, and was present for them. Every run with a definition wrote only `ApiRankingSystem`, which the owner approved, and the snapshot read a saved system and wrote nothing.

The walk-through ran from a new clone of `main` at 3f3e1d9, in a workspace that `trialfolio init` set up. Its home directory was a temporary one, so the license record and the per-user logs were too, and the owner's were untouched. The credentials were injected for each command alone, as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes.

- **The ranking system** was C of [R04-T01's checks](../ranking-weights/README.md#settings): 3 top-level composites, each holding 2 factors.
- **The snapshot** read C by its name.
- **The experiment's baseline** ranked by a definition file holding the snapshot's `definition.xml`, byte for byte, with the starter screen's other settings. Its only variants were three ranking variants:
  - **V1** moved weight among the three top-level composites, keeping their sum;
  - **V2** moved weight between one composite's two factors, keeping their sum;
  - **V3** removed one of a composite's two factors.
- **The two screens** ranked by V1's definition alone, and by the snapshot alone.

## Run record

Date: 2026-10-20, 20:42:00 to 20:48:41 UTC. Trial Folio 0.4.0, at commit 3f3e1d9; macOS 26.6.2, Python 3.14.8, and the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0.

| Step | Outcome |
|---|---|
| The snapshot, approved by its hash | Exit 0, `completed`: `POST /auth`, then `GET /rank`, each a 200, from 20:42:00 to 20:42:01 UTC. 1 credit. Ranking method 2, `USD`, and `Stock`; stdout said the definition can be a ranking. |
| Two configurations with a mistake, offline | Each failed with `config.invalid`, exit 3, before the plan was shown, and sent nothing: a variant whose node path names no node of the baseline's definition, and one whose weights don't keep the same nodes' sum. Each message named the variant by its place in the file, and quoted no path, name, or weight. |
| The experiment's plan | It showed that the run overwrites `ApiRankingSystem`, what the ranking lock doesn't exclude, and each case's definition and weights. |
| The experiment, approved by its hash | Exit 0, `completed`, session 1, from 20:43:31 to 20:43:35 UTC. One `POST /auth` served the four cases, and each sent `POST /rank`, then `POST /screen/backtest`, each a 200, the backtest 0.03 to 0.04 seconds after the `rank_update`'s 200: 8 provider requests and 24 credits. V2's and V3's `metrics.csv` each differ from the baseline's in 10 metrics. **V1's differs in none:** its backtest's response equals the baseline's, apart from `cost` and `quotaRemaining`, though its `rank_update` sent a different definition. |
| A screen ranked by V1's definition alone, approved by its hash | Exit 0, `completed`, from 20:46:31 to 20:46:33 UTC: 2 requests and 6 credits. Its `metrics.csv` differs from the baseline case's in 10 metrics. So the experiment's V1 backtest hadn't ranked by V1's definition. |
| A screen ranked by the snapshot, approved by its hash | Exit 0, `completed`, from 20:48:03 to 20:48:04 UTC: 2 requests and 6 credits. Every one of its 20 metrics equals the baseline case's. |
| The experiment's command again, without credentials | Exit 0, `completed`, session 2: it resumed the plan, sent nothing, and took no ranking lock. Its display still said "This run overwrites ApiRankingSystem", although the run sent no case. |
| `trialfolio review`, offline, of the two screens | Exit 0: the ranking and three weight rows `intended_change`, the other 28 settings the same, and 10 of the 20 metrics different. |
| `trialfolio report` of V1's screen, offline | Exit 0, with the run's weights, the definition's source, and the `POST /rank` beside the backtest. |
| Credits | 37, as Portfolio123 reported: 1 for the snapshot, 24 for the experiment, and 6 for each screen, within the budget of 40. Authentication's cost wasn't measured. |

A scan of the workspace and the temporary home directory after the runs found the API key in no file. The API ID matched only inside longer numbers, in 2 saved responses: digits that happen to coincide.

## What it found

- **A backtest may rank by the previous definition.** Portfolio123 answered V1's `rank_update` with a 200, but the backtest sent right after it ranked by the baseline's definition, which `ApiRankingSystem` held before. Run alone, V1's definition gave different results. That contradicted the specification, which, from [R04-T01's step 5](../ranking-weights/README.md#run-record), sent the backtest right after the `rank_update`, with nothing between them. Of the 5 backtests whose previous definition the walk-through knew, all but the experiment's first case, 1 was stale: none of the other 4 gave the results of the definition before it. The [diagnostic](../ranking-touch/README.md) then measured how often, and what prevents it.
- **A resume that sends nothing said it overwrites `ApiRankingSystem`.**

The owner decided both fixes on 2026-10-21 ([D-45](../../docs/spec.md#decisions)).

## The files

The runs, the review, and the report were written in the walk-through's temporary workspace. On 2026-10-20 they were copied, byte for byte, into `payloads/`, keeping their relative positions:

- `payloads/runs/snapshots/`: the snapshot.
- `payloads/runs/weights/`: the experiment, with its plan, its two sessions, and its four cases.
- `payloads/runs/value-heavy/` and `payloads/runs/by-snapshot/`: the two screens.
- `payloads/reviews/weights/` and `payloads/reports/value-heavy/`: the review and the re-rendered report.
- `payloads/ranking/`: the baseline's and V1's definitions.
- The configurations of the snapshot, the experiment, the two screens, and the review.
