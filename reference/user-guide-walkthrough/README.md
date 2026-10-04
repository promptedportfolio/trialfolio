# Live run: the user guide's walk-through

This is the live run from the step-by-step walk-through of [the user guide](../../docs/user-guide.md) on 2026-10-04. Step 7 ran one real screen backtest with the owner's account, step 8 checked its results, and step 9 re-rendered its report. The [verification record](../../docs/releases/0.1.0-verification.md#the-user-guides-walk-through) gives the walk-through's other results.

This run record is committed. The run and its re-rendered report hold Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from the response except the credits used, the response's size, and the tables' row counts and flags.

## Settings

On 2026-10-04 the owner approved one live run with a budget of 5 credits, and was present for it. The configuration is the starter `screen.yaml` that `trialfolio init` writes, [`src/trialfolio/init_data/screen.yaml`](../../src/trialfolio/init_data/screen.yaml), unchanged. Its request was the same as R01-T01's [`request.json`](../p123api-screen-backtest/request.json). Its ranking is a single formula, so nothing in the account was created or changed.

The walk-through ran from a new clone of `main` at 90dce6e, with `trialfolio` set up as the guide's step 1 says, in a workspace that `trialfolio init` set up. The license record and the per-user logs were in temporary directories. The credentials were injected for the run's command alone, as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes.

## Run record

Date: 2026-10-04, 17:23:56 to 17:23:57 UTC. Trial Folio 0.1.0, at commit 90dce6e; macOS 26.6.2, Python 3.12.13, and the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0.

| Step | Outcome |
|---|---|
| 7: `trialfolio run screen.yaml --out runs/first/ --approve <plan hash>`, from the workspace | Exit 0, outcome `completed`. The plan hash was `sha256:227a894973ab31dcdab00792a1d24ea03aae14447cbdebe94ff681812b0e88b5`, and the manifest records the approval as `option`. |
| The attempt | `succeeded`, possibly charged: `POST /auth` 200, then `POST /screen/backtest` 200, in 1.1 seconds. One attempt, one provider request, and no retries. |
| Credits | 5, as Portfolio123 reported in the response's `cost`, within the budget of 5. Authentication's cost wasn't measured. |
| What was saved | The decoded response, 139,187 bytes, as `response.json`. `metrics.csv` has its 20 rows, all available, with coverage equal to the requested dates, and `settings.csv` its 23 rows. The only flags are `inferred_default` and the universe's `not_snapshotted`, so reproducibility is `incomplete`. |
| 8: reading the results | The report and the tables passed the guide's checks. |
| 9: `trialfolio report runs/first/ --out reports/first/`, without credentials | Exit 0, and `report.html` written, with the same text as the run's own report. Its 9 links to the run's files resolve, and the run was left unchanged. |

A scan after the run found the API key in no file. Neither credential appears in the logs, the report, the normalized tables, the plan, the configuration, or the attempt's records.

## The files

The run and the report were written in the walk-through's temporary workspace. Later on 2026-10-04 they were moved, byte for byte, into `payloads/`, keeping their relative positions, so the report's links still resolve:

- `payloads/runs/first/`: step 7's run.
- `payloads/reports/first/`: step 9's re-rendered report and its log.
- `payloads/terminal/`: step 7's terminal output. `run-stdout.txt` holds its summary, and `run-stderr.txt` the plan and its progress.
