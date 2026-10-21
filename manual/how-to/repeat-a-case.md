# Repeat a case

Use this page to send an experiment's case again, on purpose, when it's awaiting a repeat. Its request may have reached Portfolio123, and may have been charged, but none of its attempts succeeded with a response that passed validation: it's `unknown`, as after a timeout or an interrupt while waiting for Portfolio123; `failed`, as after Portfolio123 rejected it; or `failed` with `provider.response_invalid`, when its attempt succeeded, but its response failed validation. A resume never sends such a case on its own.

From release 0.4.0, a case whose response failed validation can be repeated, where it had counted as complete: its response couldn't be read, lacked the layout's structure, or, in an experiment with a ranking definition, repeated the results of the case before it in the same run, which Portfolio123 may have ranked by that case's definition ([why it waits 10 seconds](../explanation/apirankingsystem-and-the-ranking-lock.md#why-it-waits-10-seconds)). The plan display, and the prompt that confirms a repeat, say that its attempt succeeded, but its response failed validation. Its option names that attempt. A repeat whose response passes validation completes the case, and its tables are written from that response.

A case awaiting a repeat is sent again only when `--repeat` names it and you confirm that its request may be charged again.

!!! warning "May be charged again"
    Whether Portfolio123 charges for a request that fails is unknown, and an `unknown` request may have gone through. Before you repeat one, you can check your API credits on Portfolio123's website, as an interrupt's message suggests.

## Before you start

- **The case's option.** The plan display, the message of a run that leaves such a case, the report, and the [JSON summary](../reference/json-summary.md) each give its exact option, `--repeat <case-key>:<attempt-id>`.
- **Room in the budget.** A repeat counts against the experiment's budget: one request, or, with a ranking definition, two, since it sends the case's `rank_update` and its backtest again.
- **Your credentials,** since a repeat sends the request again ([store your credentials](store-credentials.md)).

## Steps

Repeat the case in a terminal, or with its attempt ID. Give `--repeat` once for each case you repeat.

### In a terminal

1. Name the case by its key alone, without `--approve`:

    ```sh
    trialfolio run experiment.yaml --out runs/study/ --repeat holdings-50
    ```

2. Review the plan, and type `approve`.
3. The prompt lists each case to repeat, with its latest attempt whose request may have been charged, and the budget that would remain. Type `repeat`.

### With the attempt ID

Give the option with the attempt ID, exactly as the plan display or the message gives it:

```sh
trialfolio run experiment.yaml --out runs/study/ --approve sha256:<the plan hash> --repeat holdings-50:<attempt-id>
```

With the attempt ID, the option is the confirmation, and Trial Folio doesn't ask. With `--approve`, or from a script, a repeat needs it.

## How a repeat counts

A repeat is a new attempt of the same case, and counts against the budget. When the budget can't cover it, it doesn't start, and neither do the cases after it. A run that starts nothing for that reason needs no credentials. A [revision](revise-an-experiment.md) that raises the budget lets the same option repeat it.

## Running the command again

One confirmation, one repeat. Once the repeat may have reached Portfolio123, running the same command again never repeats the case on the same confirmation:

- **With the attempt ID,** it says the case was repeated already, and resumes the rest. A repeat that didn't succeed needs a new confirmation, which names the repeat's own attempt.
- **With the key alone,** when the repeat succeeded, it says the case is complete, and resumes the rest. When the repeat didn't succeed, the case awaits a repeat again, and in a terminal the command asks you to type `repeat` again, for the repeat's own attempt. That's a new confirmation, and typing it repeats the case again.

[Repeating a case](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#repeating-a-case) gives the rules.

## Check

- An `unknown` or rejected case, or one whose response failed validation, isn't sent again without `--repeat`, and the plan display gives its option, `--repeat <case-key>:<attempt-id>`.
- `--repeat <case-key>` alone, with `--approve` or from a script, fails with `plan.approval_required`, exit code 2, and the message gives the option with the attempt ID. Nothing was sent.
- After a repeat confirmed by its attempt ID may have reached Portfolio123, the same command again says the case isn't repeated, because its confirmation was used, and sends nothing for it. A repeat that sent nothing, such as one whose authentication failed, leaves its confirmation unused, and the same command tries it again.
