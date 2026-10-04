# Live check: R01-AC24

This is the live check of release 0.1.0's [verification commands](../../docs/releases/0.1.0-api-execution.md#verification-commands-and-expected-evidence), task R01-T16: one real screen backtest with the owner's account, run by the installed `trialfolio`, within its budget, and its output re-rendered offline. The test is [`tests/live/test_screen_backtest.py`](../../tests/live/test_screen_backtest.py).

This run record is committed. The run and its re-rendered report hold Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from the response except the credits used.

## Settings

On 2026-10-04 the owner approved one live check with a budget of 5 credits, and was present for it. The configuration is [`formula.yaml`](../../tests/fixtures/screen-configs/formula.yaml), the documented example, so its request is R01-T01's [`request.json`](../p123api-screen-backtest/request.json): a test in the default suite checks that it resolves to that request. Its ranking is a single formula, so nothing in the account was created or changed.

The command was `TRIALFOLIO_LIVE_BUDGET_CREDITS=5 uv run pytest -m live`, with the credentials injected as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes.

## Run record

Date: 2026-10-04, 08:31:01 to 08:31:03 UTC. Trial Folio 0.1.0, at commit bfecffe on the branch `test/remaining-tests`; macOS 26.6.2, Python 3.12.13, and the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0.

| Step | Outcome |
|---|---|
| `trialfolio run formula.yaml --out <payloads>/run-20261004T083101Z --approve <plan hash> --json`, the installed command, with the default endpoint and the 300-second timeout. Only this process could reach `api.portfolio123.com`, besides localhost. | Exit 0, outcome `completed`. The plan hash was `sha256:8770a706d75fdd0ea4e7f671b2cee908ac50f33ae0313f60dbbad2c9aebb1c47`, and the manifest records the approval as `option`. |
| The attempt | `succeeded`, possibly charged: `POST /auth` 200, then `POST /screen/backtest` 200, in 1.2 seconds. One attempt, and one provider request. |
| Credits | 5, as Portfolio123 reported in the response's `cost`, within the budget of 5. Authentication's cost wasn't measured. |
| What was saved | The decoded response, 139,187 bytes, as `response.json`. `metrics.csv` has its 20 rows, all available, with coverage equal to the requested dates, and `settings.csv` its 23 rows. The only flags are `inferred_default` and the universe's `not_snapshotted`, so reproducibility is `incomplete`. The saved run reads back as a complete run. |
| `trialfolio report <payloads>/run-20261004T083101Z --out <payloads>/report-20261004T083101Z --json`, under the full network guard, without credentials | Exit 0, outcome `completed`, and `report.html` written. Its 9 links to the run's files resolve. |

A scan after the run found the API key in no file. Neither credential appears in the logs, the report, the normalized tables, the plan, the configuration, or the attempt's records.

R01-AC24 passed.
