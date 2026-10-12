# Live check: R03-AC12

This is the live check of release 0.3.0's [verification commands](../../docs/releases/0.3.0-experiments.md#verification-commands-and-expected-evidence), task R03-T11: a real experiment of two cases with the owner's account, run by the installed `trialfolio` within its budget, with one authentication call for both requests, then resumed offline. The test is [`tests/live/test_experiment.py`](../../tests/live/test_experiment.py).

This run record is committed. The experiment holds Portfolio123's data, so it stays in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from the responses except the credits used, and nothing comes from the account except whether its ranking systems changed.

## Settings

On 2026-10-11 the owner approved one live check with a budget of 10 credits, and was present for it. The configuration is [`default-only.yaml`](../../tests/fixtures/experiment-configs/default-only.yaml): the documented example's baseline, ranked by a single formula, and the default variant, `rebalance-weeks-1`. Its two requests are those R01-T01 and R01-T05 verified, and its budget is 2 provider requests, 10 credits at the documented cost.

The command was `TRIALFOLIO_LIVE_BUDGET_CREDITS=10 uv run pytest -m live tests/live/test_experiment.py`, with the credentials injected as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes.

Before the run, the owner noted the account's ranking systems in the Portfolio123 website.

## Run record

Date: 2026-10-11, 23:01:20 to 23:01:25 UTC. Trial Folio 0.3.0, at commit 67a9abb on the branch `test/r03-t11-experiment-tests`; macOS 26.6.2, Python 3.14.8, and the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0. The test passed, in 4.8 seconds.

| Step | Outcome |
|---|---|
| `trialfolio run default-only.yaml --out <payloads>/experiment-20261011T230120Z --approve <plan hash> --json`, the installed command, with the default endpoint and the 300-second timeout. Only this process could reach Portfolio123's API host, besides localhost. | Exit 0, outcome `completed`, session 1. The plan hash was `sha256:53a9d361a34a8aefa0162b78264ebfc1ae09684f5e77c084de43546407a2a403`, and the manifest records the approval as `option`, and the experiment as not synthetic. |
| `baseline`, `case-e29404ddebf86363` | `succeeded`, possibly charged: `POST /auth` 200, then `POST /screen/backtest` 200, in 1.6 seconds. One attempt, and one provider request. |
| `rebalance-weeks-1`, `case-0492159b4461ceff` | `succeeded`, possibly charged: `POST /screen/backtest` 200, sent with the token of `baseline`'s attempt, in 2.4 seconds. One attempt, and one provider request. |
| Counts | 2 cases succeeded, 2 attempts, 2 provider requests, and 1 authentication call, against a budget of 2 provider requests and 2 authentication calls. No retry, no repeat, and no case retired. |
| Credits | 10, 5 for each request, as Portfolio123 reported in each response's `cost`, within the budget of 10. Authentication's cost wasn't measured. |
| What was saved | Each case's decoded response, as `response.json`: 139,172 bytes for `baseline`, and 202,090 for `rebalance-weeks-1`. Each case's `metrics.csv` has its 20 rows, all available, and its `settings.csv` its 23 rows. Reproducibility is `incomplete`. |
| The same command again, under the full network guard, without the credentials | Exit 0, outcome `completed`, session 2. No case was due, so nothing was sent and no authentication call was made: the counts are the same 2 attempts, 2 provider requests, and 1 authentication call. It wrote `sessions/2/`, with its report and manifest, from the records alone, and the attempts' IDs are those of session 1. |
| The reports | Each session's `report.html` was written. The 18 links of each to the experiment's files resolve. |

A scan of the experiment's 24 files after the run found the API key in no file. Neither credential appears in the logs, the reports, the manifests, the session records, the normalized tables, the plan, the configuration, or the attempts' records.

## The account's ranking systems

After the run, the owner compared the account's ranking systems in the Portfolio123 website with the note from before: none was added, removed, or changed. So the experiment's formula-ranked backtests updated no shared object in the account, and 0.3.0 needs no per-account lock ([the lock](../../docs/contracts.md#the-lock)).

R03-AC12 passed.
