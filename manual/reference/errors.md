# Errors and exit codes

This page lists every error code Trial Folio gives, with what to do about it, the exit codes, and where the logs are.

Every error message says what failed, why, and what to do next. It names its code, and never holds a credential. [Errors](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#errors), in the specification, lists every code: each code, exit code, and meaning below is generated from it, and its links lead to the specification. What to do is advice, written here.

## Error codes

<!-- generated: errors-codes -->

| Code | Exit code | Meaning | What to do |
|---|---|---|---|
| `config.invalid` | 3 | Configuration fails validation, including unknown keys and cross-field rules | Fix each problem the message lists. Nothing was sent. |
| `input.not_found` | 3 | A referenced file does not exist | For a configuration file, a ranking definition's file, or a snapshot's directory, check its path: nothing was sent or created. For a run, give the output directory of a run that finished: nothing was written. |
| `input.not_a_run` | 3 | An input directory is not a complete Trial Folio run: its manifest is missing, or its files don't match their hashes. The message names the problem. From 0.4.0, also a configuration's ranking snapshot that isn't a complete snapshot ([reading a snapshot](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-snapshot-output)). | For `report` or a review, give the output directory of a run that finished: nothing was written. For a resumed experiment, restore its records from a complete copy, or run the configuration into a new output directory: nothing was sent or written. For a ranking snapshot, name the directory of a snapshot that finished, or [take it again](../how-to/take-a-ranking-snapshot.md): nothing was sent or created. |
| `artifact.unknown_schema_version` | 3 | An artifact's schema version has no reader | Read the run, or resume the experiment, with a version of Trial Folio that has one. Nothing was written, and a resumed experiment sends nothing. |
| `environment.unsupported` | 3 | The installed `p123api`, `requests`, or `urllib3` isn't a verified version, or `requests` would write request bodies with `simplejson` ([plan contents](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-contents)). It's found before the plan is shown, so nothing is sent and no output is created. The message names the verified versions and how to restore them. Exit 3, like an unsupported input, because the fix is local. | Run `uv sync` in the repository to restore the locked versions. If `simplejson` is importable, uninstall it from the environment, or run Trial Folio in its own virtual environment. |
| `license.not_acknowledged` | 2 | A data-processing command ran without an acknowledgment of the current license and notice versions | Acknowledge them in one of the [three ways](cli.md#three-ways-to-acknowledge). Nothing was written. |
| `plan.approval_required` | 2 | A charged or mutating operation was requested without the matching plan hash: no `--approve`, a different hash, or a refused confirmation. Also `--revision-reason` when there's no revision to give a reason for, unless it's the reason the current plan recorded, which resumes it ([experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions)). Also a `--repeat` that names no case awaiting a repeat, or a repeat that isn't confirmed ([repeating a case](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#repeating-a-case)). | Approve it in a terminal, or give its full hash. For a repeat, give the option the message shows. Nothing was sent. |
| `plan.changed` | 3 | The configuration or the installed versions no longer give an experiment's current plan, and the revision wasn't approved with a reason: no `--revision-reason`, no `--approve` with the revision's hash, or a refused confirmation ([experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions)). Otherwise, a hash given with `--approve` that doesn't match is `plan.approval_required`. | Give `--revision-reason`, and approve the revision's hash, which the message gives. Nothing was sent. |
| `output.not_empty` | 4 | The output directory exists and is not empty. For an experiment, it holds no `experiment.lock`, or it holds another experiment, by its `experiment_id` or its universe, one whose first plan was never recorded, or a synthetic experiment, which `run` doesn't resume ([running an experiment](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#running-an-experiment)). In the core, the demo's client given an experiment that isn't synthetic fails with it too ([the experiment manifest](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-experiment-manifest)). | Choose a new or empty directory |
| `storage.write_failed` | 4 | An artifact could not be written durably. This is the code even when a request was already sent; the attempt record still gives the outcome ([endings that decide the error code](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#endings-that-decide-the-error-code)). | On macOS or Linux, an exFAT or FAT drive, which lacks hard links, fails this way: use another drive. If the request was sent, the attempt record says whether it may have been charged. When the message names the ranking lock's file, `trialfolio-ranking.lock`, nothing was sent: set `TRIALFOLIO_LOCK_DIR` to a directory on a local file system that every Trial Folio process using the account sees ([the ranking lock](cli.md#the-ranking-lock)). |
| `experiment.locked` | 4 | Another process holds the experiment lock ([the lock](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-lock)). From 0.4.0, also another Trial Folio process holds the ranking lock, while it writes `ApiRankingSystem` for a ranking definition ([the ranking lock](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-ranking-lock)). | Wait for the other process to end, and run the command again: for the experiment lock, the process running the experiment or waiting for its approval; for the ranking lock, which the message names, the process writing `ApiRankingSystem`. Nothing was sent. |
| `provider.auth_failed` | 5 | Credentials were missing, Trial Folio's authentication call got a 400, 401, 402, 403, or 406, or Portfolio123 refused a request's authorization with a 401 or 403 | Check the API ID and key |
| `provider.unavailable` | 5 | Portfolio123 couldn't be reached, or didn't complete Trial Folio's authentication call: that call got a 5xx or no complete response, or the request's connection was never established ([HTTP exchanges](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#http-exchanges)). Either way, the request wasn't sent. | Try again later |
| `provider.quota_exceeded` | 5 | The provider refused the request because of quota or credits | Check your API credits. The request may have been charged. |
| `provider.unsupported_capability` | 5 | Portfolio123 rejected the request with a 400 or a 409: a setting or operation the verified provider path doesn't support, or a value it can't use, such as a rule that names no factor. The message gives the status and Portfolio123's sanitized message. The request may have been charged. A 409 is this code from 0.3.0 ([D-38](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)); 0.1.0 and 0.2.0 gave it `provider.request_rejected`. | Change the setting. Portfolio123's own message ends the error's message. The request may have been charged. In an experiment, [revise the plan](../how-to/revise-an-experiment.md) with the setting changed: a repeat would send the same request. |
| `provider.request_rejected` | 5 | Portfolio123 answered Trial Folio's authentication call or the request with a status below 500 that no other code covers, such as a 204, 3xx, 404, or 429. The message gives the status, and Portfolio123's sanitized message when the wrapper's exception message carries one. After a refused second exchange, such as a redirect, there's none ([HTTP exchanges](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#http-exchanges)). | After the authentication call, the request wasn't sent: try again later, and [report it](#reporting-a-problem) if it persists. After the request, it may have been charged: wait before running the command again, which is a new attempt. In an experiment, only a [repeat](../how-to/repeat-a-case.md) sends it again. |
| `provider.response_invalid` | 5 | The response was saved but failed validation, or couldn't be decoded and was saved undecoded as `response.raw` | The response stays in the run. [Report it](#reporting-a-problem), because Portfolio123's response may have changed. |
| `provider.outcome_unknown` | 5 | A request may have been sent, but no response was durably recorded: for example after a read timeout or a 5xx. It is never retried automatically. | The request may have been charged. Trial Folio never resends it on its own. Running a screen's command again is a new attempt, and may be charged again. In an experiment, only a [repeat](../how-to/repeat-a-case.md) sends it again. |
| `execution.partial` | 6 | Some planned cases did not succeed; all are accounted for | The experiment's message lists each case that didn't succeed, with Portfolio123's own message for each it gave one, and ends with where the session's report is. Run the same command again to send the cases that are due, and repeat each case awaiting a repeat with the option the message gives. For a case Portfolio123 rejected for a setting, change the setting and [revise the plan](../how-to/revise-an-experiment.md) instead. |
| `command.interrupted` | 130 | The user interrupted the command, for example with Ctrl-C. The message says whether a request may have been sent, as the attempt record does ([interrupts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#interrupts)). | The message says whether a request may have been sent. For an experiment, run the same command again to resume it. |
| `internal.unexpected` | 1 | A defect; the message asks the user to report it with the log location | [Report it](#reporting-a-problem), with the log the message names |

<!-- end generated: errors-codes -->

**More about some codes:**

- **`input.not_found`:** it's a configuration file that `trialfolio run` or `trialfolio review` couldn't read, as when it doesn't exist, or a run directory that doesn't exist: `trialfolio report`'s, or a review's `run` path. A review's message names the result.
- **`input.not_a_run`:** an experiment's directory isn't a run, so `trialfolio report` and a review fail with it. A review's message names the result. In a resumed experiment, it's a record that's missing or changed, as after an incomplete copy. For a configuration ranked by a snapshot, it's a snapshot that isn't complete, such as one whose `rank_get` failed: the message names the configuration's key, and the problem.
- **`config.invalid` with a ranking definition:** a definition Trial Folio can't send, a ranking variant that breaks a rule, or a snapshot that can't be a ranking, such as one of a system in another currency, or a synthetic one. The message names the configuration's key, the rule, and, for a definition, the line at fault, and never quotes the definition, a node path, or a weight ([ranking definitions](ranking-definitions.md#whats-rejected)).
- **A `rank_update` that fails** gives its case the code a request gets for the same ending, such as `provider.unsupported_capability` for a 400, whose message says Portfolio123 doesn't accept the ranking definition, or a value sent with it. Its case's backtest isn't sent. A `rank_update` that may have reached Portfolio123 may have been charged, so its case awaits a [repeat](../how-to/repeat-a-case.md).
- **`license.not_acknowledged`:** the commands that process data, and so need the acknowledgment, are `run`, `report`, `demo`, and `review`.
- **`output.not_empty`:** it's also the folder given to `trialfolio init`, when that isn't empty. After an experiment's first run that stopped before its plan was recorded, nothing was sent, and the message says to remove the directory and run the command again.
- **`storage.write_failed`:** `trialfolio license --accept` also fails with it when it can't write its record.
- **`provider.auth_failed`:** with the credentials missing, the message names the missing variables, and nothing was sent or created. [Storing your credentials](../how-to/store-credentials.md) gives ways to set them.
- **`execution.partial`:** two failures stop an experiment before its later cases: Trial Folio's own authentication call failing, as with wrong credentials, and `provider.quota_exceeded`. Once you've fixed the cause, running the same command again runs the cases it didn't start. [Credits and uncertain charges](../explanation/credits-and-uncertain-charges.md) explains which requests may have been charged.

## What a failure leaves

- **After a Portfolio123 error,** the run's directory still has its report and manifest, which record the failure.
- **After an interrupt, a storage failure, or an internal error,** there's no manifest, so the run, or the review, reads as incomplete.
- **An experiment's session** is the same: it ends with its report and manifest even when cases fail, and without them after an interrupt, until the same command resumes the experiment. [Recovering from an interrupt](../how-to/recover-from-an-interrupt.md) gives the steps.

## Exit codes

<!-- generated: errors-exit-codes -->

| Code | Meaning |
|---|---|
| 0 | Command completed and outputs were written. This says nothing about any strategy. |
| 1 | Unexpected internal error |
| 2 | Usage error: invalid arguments, missing plan approval, or license not acknowledged |
| 3 | Invalid or unsupported configuration, input, artifact, or environment, or an experiment's changed plan whose revision wasn't approved with a reason (`plan.changed`) |
| 4 | Output problem: directory not empty, write failure, or experiment locked by another process |
| 5 | Provider error: authentication, provider unavailable, quota, unsupported capability, rejected request, uncertain outcome, or invalid response |
| 6 | Partial completion: at least one planned case failed, was skipped, or is uncertain |
| 130 | Interrupted by the user |

<!-- end generated: errors-exit-codes -->

An argument the command line's parser rejects, such as a missing `--out`, is a usage error, exit code 2. The parser reports it on stderr, with no error code, and no [JSON summary](json-summary.md).

## Logs

- **A command with an output directory** logs to `logs/trialfolio.log` there.
- **`trialfolio init`, `trialfolio license`, and an internal error** before the output directory is claimed log to a per-user directory:

  | System | Per-user log directory |
  |---|---|
  | macOS | `~/Library/Logs/trialfolio` |
  | Linux | `~/.local/state/trialfolio/logs`, or `$XDG_STATE_HOME/trialfolio/logs` |
  | Windows | `%LOCALAPPDATA%\trialfolio\logs` |

  `TRIALFOLIO_LOG_DIR` names another. When the per-user log directory is the folder `trialfolio init` sets up, or is in it, `init` writes no log file, with a warning.
- **A command that stops before it claims its output directory,** other than with an internal error, writes no log file. Its messages appear only on stderr.
- **To delete the logs,** delete those directories. A log file is rotated at 1 MB, and the 3 older files are kept.
- **To see more detail,** set `TRIALFOLIO_LOG_LEVEL=DEBUG`. Log files record `INFO` and above otherwise.
- **At every level,** logs hold no credentials, configuration values, formulas, or results.

The README's [Your data stays on your machine](https://github.com/promptedportfolio/trialfolio/blob/main/README.md#your-data-stays-on-your-machine) lists the same locations.

## Reporting a problem

[CONTACT.md](https://github.com/promptedportfolio/trialfolio/blob/main/CONTACT.md) links to a form for bugs and questions.
