# Errors and exit codes

This page lists every error code Trial Folio gives, with what to do about it, the exit codes, and where the logs are.

Every error message says what failed, why, and what to do next. It names its code, and never holds a credential. [Errors](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#errors), in the specification, lists every code.

## Error codes

| Code | Exit code | What happened | What to do |
|---|---|---|---|
| `config.invalid` | 3 | The configuration has a problem; the message lists each one | Fix them. Nothing was sent. |
| `input.not_found` | 3 | `trialfolio report`'s run directory, or a review's `run` path, doesn't exist. A review's message names the result. | Give the output directory of a run that finished. Nothing was written. |
| `input.not_a_run` | 3 | `trialfolio report`'s run directory, or a review's `run` path, isn't a complete run, or is an experiment's directory. A review's message names the result. In a resumed experiment, a record is missing or changed, as after an incomplete copy. | Give the output directory of a run that finished. Nothing was written. A resumed experiment sends nothing. |
| `artifact.unknown_schema_version` | 3 | A saved file's schema version is one this version of Trial Folio has no reader for | Read the run, or resume the experiment, with a version of Trial Folio that has one. Nothing was written, and a resumed experiment sends nothing. |
| `environment.unsupported` | 3 | The installed `p123api`, `requests`, or `urllib3` isn't the verified version | Run `uv sync` in the repository to restore the locked versions |
| `license.not_acknowledged` | 2 | `run`, `report`, `demo`, or `review` ran without an acknowledgment of the current license and notice versions | Acknowledge them in one of the [three ways](cli.md#three-ways-to-acknowledge). Nothing was written. |
| `plan.approval_required` | 2 | The plan wasn't approved, or the hash didn't match. For an experiment, also a `--repeat` that names no case awaiting a repeat, or that wasn't confirmed, or a `--revision-reason` with no revision. | Approve it in a terminal, or give its full hash. For a repeat, give the option the message shows. Nothing was sent. |
| `plan.changed` | 3 | An experiment's configuration, or the installed versions, changed since its current plan, and the revision wasn't approved with a reason | Give `--revision-reason`, and approve the revision's hash, which the message gives. Nothing was sent. |
| `output.not_empty` | 4 | `--out`, or the folder given to `trialfolio init`, names a directory that isn't empty. For an experiment, it holds something other than an experiment, or another experiment, with another `experiment_id` or universe. | Choose a new or empty directory |
| `storage.write_failed` | 4 | A file couldn't be written durably, for example on macOS or Linux to an exFAT or FAT drive, which lacks hard links | Use another drive. If the request was sent, the attempt record says whether it may have been charged. |
| `experiment.locked` | 4 | Another process is running the experiment, or waiting for its approval | Wait for it to end, and run the command again. Nothing was sent. |
| `provider.auth_failed` | 5 | The credentials are missing, or Portfolio123 refused them | Check the API ID and key |
| `provider.unavailable` | 5 | Portfolio123 couldn't be reached; the request wasn't sent | Try again later |
| `provider.quota_exceeded` | 5 | Portfolio123 refused the request for quota or credits | Check your API credits. The request may have been charged. |
| `provider.unsupported_capability` | 5 | Portfolio123 rejected a setting; its own message follows | Change the setting. The request may have been charged. |
| `provider.request_rejected` | 5 | Portfolio123 answered the authentication call or the request with a status that no other code covers, such as a redirect, 404, or 429. The message gives the status. | After the authentication call, the request wasn't sent: try again later, and [report it](#reporting-a-problem) if it persists. After the request, it may have been charged: wait before running the command again, which is a new attempt. In an experiment, only a [repeat](../how-to/repeat-a-case.md) sends it again. |
| `provider.response_invalid` | 5 | A response was saved, but didn't have the expected layout | The response stays in the run. [Report it](#reporting-a-problem), because Portfolio123's response may have changed. |
| `provider.outcome_unknown` | 5 | The request may have been sent and charged, but no response was saved, for example after a timeout | Trial Folio never resends it on its own. Running a screen's command again is a new attempt, and may be charged again. In an experiment, only a [repeat](../how-to/repeat-a-case.md) sends it again. |
| `execution.partial` | 6 | An experiment ended with a planned case that didn't succeed; the message lists each one | Run the same command again to send the cases that are due, and repeat each case awaiting a repeat with the option the message gives |
| `command.interrupted` | 130 | You pressed Ctrl-C | The message says whether a request may have been sent. For an experiment, run the same command again to resume it. |
| `internal.unexpected` | 1 | A defect in Trial Folio | [Report it](#reporting-a-problem), with the log the message names |

**More about some codes:**

- **`plan.approval_required`:** a `--revision-reason` that's the reason the current plan recorded doesn't fail: it resumes that plan.
- **`output.not_empty`:** for an experiment, it's also a directory whose first run stopped before its plan was recorded, and a synthetic experiment, which `trialfolio run` doesn't resume. After a first run that stopped before its plan was recorded, nothing was sent, and the message says to remove the directory and run the command again.
- **`storage.write_failed`:** `trialfolio license --accept` also fails with it when it can't write its record.
- **`provider.auth_failed`:** with the credentials missing, the message names the missing variables, and nothing was sent or created. [Storing your credentials](../how-to/store-credentials.md) gives ways to set them.
- **`execution.partial`:** two failures stop an experiment before its later cases: Trial Folio's own authentication call failing, as with wrong credentials, and `provider.quota_exceeded`. Once you've fixed the cause, running the same command again runs the cases it didn't start. [Credits and uncertain charges](../explanation/credits-and-uncertain-charges.md) explains which requests may have been charged.

## What a failure leaves

- **After a Portfolio123 error,** the run's directory still has its report and manifest, which record the failure.
- **After an interrupt, a storage failure, or an internal error,** there's no manifest, so the run, or the review, reads as incomplete.
- **An experiment's session** is the same: it ends with its report and manifest even when cases fail, and without them after an interrupt, until the same command resumes the experiment. [Recovering from an interrupt](../how-to/recover-from-an-interrupt.md) gives the steps.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The command completed. It says nothing about the strategy. |
| 1 | An unexpected internal error |
| 2 | A usage error, a plan not approved, or the license not acknowledged |
| 3 | An invalid configuration, input, artifact, or environment |
| 4 | An output problem: the directory isn't empty, a write failed, or another process is running the experiment |
| 5 | A Portfolio123 error: authentication, Portfolio123 unavailable, quota, an unsupported setting, a rejected request, an uncertain outcome, or an invalid response |
| 6 | An experiment ended with a planned case that didn't succeed. Every case is accounted for. |
| 130 | Interrupted, for example with Ctrl-C |

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
