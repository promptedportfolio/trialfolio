# Recover from an interrupt

Use this page when a command stopped before it ended, such as after Ctrl-C, a storage failure, or a crash, or when an experiment ended with cases left to send. It shows what Trial Folio kept, and how to go on: by resuming the experiment, or by sending a screen run again.

## What a stopped command leaves

- **After a Portfolio123 error,** the run's directory still has its report and manifest, which record the failure.
- **After an interrupt, a storage failure, or an internal error,** there's no manifest, so the run, or the review, reads as incomplete.
- **An experiment's session** is the same: it ends with its report and manifest even when cases fail, and without them after an interrupt, until the same command resumes the experiment.
- **After Ctrl-C,** the command fails with `command.interrupted`, exit code 130. The message says whether a request may have been sent. For an experiment, run the same command again to resume it.

[Errors](../reference/errors.md) lists every error code, and what to do about each.

## Send a screen run again

A screen run isn't resumed, and Trial Folio never sends its request again on its own.

!!! warning "May be charged again"
    Running a screen's command again is a new attempt, and may be charged again.

1. Read the message. It says whether the request was sent, and whether it may have been charged. When the request's outcome is unknown, it suggests checking your account's API credits on Portfolio123's website before you run the command again.
2. To send the request again, run the command into a new directory. `--out` must name a new or empty directory, and `trialfolio run` resumes only an experiment:

    ```sh
    trialfolio run screen.yaml --out runs/first-again/
    ```

## Resume an experiment

To go on with an experiment, run the same command again, into the same directory. Trial Folio reads and checks the experiment's records, then shows the plan with each case's outcome so far, and the budget counted so far. It needs the plan's approval again, by the same hash, so the same `--approve` approves it. Each run that's approved is a new session of the same experiment.

1. Run the same command, into the same directory:

    ```sh
    trialfolio run experiment.yaml --out runs/study/
    ```

2. Review the plan, with each case's outcome so far, and type `approve`. Or give the same `--approve sha256:<the plan hash>` as before.

A case awaiting a repeat isn't sent again by a resume: [repeat it](repeat-a-case.md) on purpose. If you've changed the configuration, the command builds a revision instead: [revise the experiment](revise-an-experiment.md).

### What a resume does with each case

A resume treats each case by its state:

| State | What a resume does with it |
|---|---|
| **Complete:** one of its attempts succeeded, so its response was saved, even one that then failed validation | Skips it. It's never sent again. |
| **Due:** it has no attempt, or each failed before its request could reach Portfolio123, as after a failed authentication | Sends it |
| **Awaiting a repeat:** its request may have reached Portfolio123, and may have been charged, but none of its attempts succeeded. It's `unknown`, as after a timeout or an interrupt while waiting for Portfolio123, or `failed`, as after Portfolio123 rejected it. | Never sends it on its own. Only a [repeat](repeat-a-case.md) sends it again. |

### After an interrupt

After an interrupt, such as Ctrl-C, a storage failure, or a crash, the attempts recorded so far are kept. Run the same command again. It records what the stopped run left, such as an attempt interrupted while it waited for Portfolio123, which becomes `unknown`. It writes the tables the stopped run didn't, and sends the cases that are due.

If the first run was interrupted before its plan was recorded, nothing was sent, and the message says to remove the directory and run the command again.

With a ranking definition, each attempt writes a start record before each of its two requests: `updating.json` before its `rank_update`, and `started.json` before its backtest. So a resume finds which of the two may have gone out. An attempt stopped during its `rank_update`, or after it and before its backtest was sent, is recorded as possibly charged, and its case awaits a [repeat](repeat-a-case.md), since sending it again sends the `rank_update` again ([sending a definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#sending-a-definition)).

### After a run that ends with `execution.partial`

An experiment that ends with a planned case that didn't succeed exits 6, with `execution.partial`, and its message lists each such case, with Portfolio123's own message for each it gave one, and where the session's report is. Run the same command again to send the cases that are due, and repeat each case awaiting a repeat with the option the message gives.

Two failures stop the run before its later cases: Trial Folio's own authentication call failing, as with wrong credentials, and `provider.quota_exceeded`. Once you've fixed the cause, running the same command again runs the cases it didn't start.

### A resume that sends nothing

A resume that sends nothing needs no credentials. When no case is due and no repeat is to be made, it writes a new session's report and manifest, and sends nothing.

### The records are checked first

If a record is missing or changed, as after an incomplete copy, the resume fails with `input.not_a_run`, exit code 3, and sends nothing.

### One process at a time

While one command runs the experiment, or waits for your approval, another fails with `experiment.locked`, exit code 4. Wait for the first to end, and run the command again.

With a ranking definition, a resume that sends a case also takes the [ranking lock](../explanation/apirankingsystem-and-the-ranking-lock.md#the-ranking-lock), so it fails the same way while another Trial Folio process on the machine is writing `ApiRankingSystem`. A resume that sends nothing doesn't take it.

[Running an experiment](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#running-an-experiment) gives the rules.

## Check

- After a run that ends, the same command resumes. stderr says the plan is the experiment's current plan, plan 1, which this run resumes, and gives the provider requests counted so far. It skips the complete cases, and writes `sessions/2/`.
- A resume with no case due and no repeat to make sends nothing, needs no credentials, and writes its session's report and manifest.
- An `unknown` or rejected case isn't sent again without `--repeat`, and the plan display gives its option, `--repeat <case-key>:<attempt-id>`.
- While a command waits for approval, the same command in another terminal fails with `experiment.locked`, exit code 4.
