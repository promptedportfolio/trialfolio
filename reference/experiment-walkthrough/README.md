# Live runs: the owner's walk-through of 0.3.0

These are the live runs from the step-by-step walk-through of [the user guide](../../docs/user-guide.md) under release 0.3.0 on 2026-10-12, which an agent ran with the owner present, before the owner's own private use. Section 7 ran one real screen backtest, and sections 11 and 12 one real experiment, which was resumed, repeated, revised, and interrupted. The [verification record](../../docs/releases/0.3.0-verification.md#the-live-walk-through) gives the walk-through's other results, and what it found.

This run record is committed. The runs hold Portfolio123's data, so they stay in `payloads/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)). Nothing here comes from the responses except the credits used, and Portfolio123's message for a rejected rule, which repeats only the rule's own text.

## Settings

On 2026-10-12 the owner approved live calls with a budget of 45 credits, and was present for them. Every ranking was a single formula, so nothing in the account was created or changed.

The walk-through ran from a new clone of `main` at 9caeb3f, with `trialfolio` set up as the guide's section 1 says, in a workspace that `trialfolio init` set up. Its home directory was a temporary one, so the license record and the per-user logs were too, and the owner's were untouched. The credentials were injected for each command alone, as [AGENTS.md](../../AGENTS.md#credentials-and-reference-data) describes, from a file of references in the workspace, as the guide's section 6 says for a password manager.

- **The screen run** used the starter `screen.yaml` that `trialfolio init` writes, unchanged.
- **The experiment** started from the guide's documented example, `earnyield-sensitivity`, copied from section 11 unchanged: the baseline, `liquidity-100m`, `holdings-50`, the default `rebalance-weeks-1`, and `slippage-050`, with a budget of 6 provider requests. Four revisions followed:
  - **Plan 2:** `slippage-050`'s value changed to 0.75, as the guide's section 12 does; a variant `microcap-typo` added, adding the rule `MktCapp > 300`, whose factor is misspelled on purpose; and the budget raised to 8.
  - **Plan 3:** `microcap-typo` replaced by `microcap-300`, adding `MktCap > 300`, and the budget raised to 10.
  - **Plan 4:** a variant `holdings-40` added, with the value 40.
  - **Plan 5:** `holdings-40` removed.

## Run record

Date: 2026-10-12, 17:35:29 to 17:41:49 UTC. Trial Folio 0.3.0, at commit 9caeb3f; macOS 26.6.2, Python 3.14.8, and the verified versions: `p123api` 3.1.0, `requests` 2.34.2, and `urllib3` 2.8.0.

| Step | Outcome |
|---|---|
| Section 7: `trialfolio run screen.yaml --out runs/first/ --approve <plan hash>` | Exit 0, `completed`: `POST /auth` 200, then `POST /screen/backtest` 200, in 1.1 seconds. 5 credits. The plan hash was `sha256:7f2517aa08e93f7c14e7161ce8cbd5567c47f3861b3f1f56ebe476d45b8d0ba8`. |
| Section 8: reading the results | `settings.csv` has its 23 rows, commission `not_modeled`, the five parameters not sent `unknown`, and only the universe's `not_snapshotted` and two `inferred_default` flags, so reproducibility is `incomplete`. `metrics.csv` has its 20 rows. `attempt.json` gives `succeeded`, possibly charged, and the cost Portfolio123 reported. |
| Section 9: `trialfolio report runs/first/ --out reports/first/`, without credentials | Exit 0. Its numbers equal the run's report's, and the run was left unchanged. |
| Section 11: `trialfolio run experiment.yaml --out runs/study/ --approve <plan 1's hash>` | Exit 0, `completed`, session 1: the five cases succeeded, each with one attempt and one request, and one `POST /auth`, before the first, served them all. 25 credits. Plan 1's hash was `sha256:07fd2f0967d63fe0ab84486a7d220430390e744c109777a9222cc3fd40e89853`. |
| Section 12: the same command, while another waited at its approval prompt | The second failed with `experiment.locked`, exit 4. |
| The same command, without credentials | Exit 0, session 2: it resumed plan 1, sent nothing, and wrote its report and manifest. |
| Plan 2, approved with its reason and hash | Exit 6, `execution.partial`, session 3. `microcap-typo`'s request got HTTP 409, `failed`, possibly charged, with `provider.request_rejected` and Portfolio123's message, "ERROR: Invalid criteria in Rule 2. Error near 'MktCapp': Invalid command 'MktCapp'". The new `slippage-050` succeeded, 5 credits, and the old one was retired. |
| The same command, without credentials, then `--repeat microcap-typo` alone with `--approve` | Session 4 resumed, sent nothing, and exited 6, giving `microcap-typo`'s `--repeat` option. The key alone failed with `plan.approval_required`, exit 2, and gave the option with the attempt ID. |
| `--repeat microcap-typo:<attempt-id>`, then the same command again without credentials | Session 5 repeated the case: HTTP 409 again, exit 6, with the repeat's own option. Session 6 said the confirmation was used, repeated nothing, and exited 6. |
| Plan 3, approved with its reason and hash | Exit 0, `completed`, session 7: `microcap-300` succeeded, 5 credits, and `microcap-typo` was retired, with its two attempts. |
| Plan 4, approved in a terminal session, with Ctrl-C typed once the request was sent | Exit 130, `command.interrupted`, about 0.1 seconds after the request was sent, and no manifest. |
| The same command, without credentials | Exit 6, session 9: `holdings-40` recorded `unknown`, possibly charged, with `command.interrupted`, awaiting a repeat, and its option given. |
| `--repeat holdings-40:<attempt-id>`, without credentials, with the budget's 10 requests counted | `provider.auth_failed`, exit 5, before saying the budget couldn't cover the repeat. |
| Plan 5, approved with its reason and hash, without credentials | Exit 0, `completed`, session 10: `holdings-40` retired, and nothing sent. |
| Counts after session 10 | 6 planned cases succeeded, and 3 retired. 10 attempts: 7 succeeded, 2 failed, 1 unknown, 1 of them a repeat. 10 provider requests and 5 authentication calls. |
| Credits | 40, as Portfolio123 reported: 5 for the screen run, and 35 for the experiment's seven successful requests. It reported no cost for either 409, and the credits it reported remaining fell by exactly the costs it reported around them, so neither 409 was charged. Whether the interrupted request was charged is unknown, so the total is 40 or 45, within the budget of 45. Authentication's cost wasn't measured. |

Before plan 3 and plan 4, two attempts to interrupt a request failed because of how the agent sent the signal, not because of Trial Folio: the first signal reached the agent's own shell, and the second a process started in the background, which ignores it. Each case ran to completion, and used 5 credits. Those are plan 2's `slippage-050` and plan 3's `microcap-300`, both counted above. The interrupt that worked was typed in a terminal session, as a user would.

A scan of the workspace and the temporary home directory after the runs found the API key in no file. Neither credential appears in the logs, the reports, the manifests, the session records, the normalized tables, the plans, the configurations, or the attempts' records.

## What it found

Two things, which the owner decided to fix before 0.3.0's private use ([D-38](../../docs/spec.md#decisions)):

- **Portfolio123 answers a rule that names no factor with HTTP 409,** which the specification didn't expect: it gave a rejected setting a 400. So Trial Folio gave it `provider.request_rejected`, the code for a status no other code covers, whose message said to wait before running the command again, and which the user guide's table of errors didn't list.
- **An experiment's failed case didn't say why on the terminal.** The progress showed the 409 and went on to the next case. The terminal shows no error event, and `execution.partial`'s message gave only the code, so Portfolio123's reason was in the session's report and the attempt record alone, and the message's only next step was `--repeat`, which would send the misspelled rule again.

## The files

The runs and the report were written in the walk-through's temporary workspace. On 2026-10-12 they were moved, byte for byte, into `payloads/`, keeping their relative positions, so the reports' links still resolve:

- `payloads/runs/first/`: section 7's run.
- `payloads/reports/first/`: section 9's re-rendered report and its log.
- `payloads/runs/study/`: the experiment, with its five plans, each with its configuration, and its ten sessions.
