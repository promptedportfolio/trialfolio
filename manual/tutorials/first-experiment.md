# Your first experiment

This tutorial runs your first experiment: a baseline screen and a few variants of it, each changing one setting of the baseline, under one plan, one approval, and one budget. You write the configuration, review the plan, run it, and read the results.

Trial Folio compiles every case before it sends anything, runs the cases one at a time, and records every attempt, including those that fail. It doesn't rank the cases, or say which is better.

## What you need

- **The setup from [your first backtest](first-backtest.md):** Trial Folio, a workspace to run the commands from, and the license acknowledged, as its steps 1 to 3 do.
- **A Portfolio123 subscription with the appropriate access, and your API ID and key,** set as in [its step 7](first-backtest.md#step-7-set-your-credentials).
- **API credits.** Each case is a screen backtest, sent just as a screen configuration with its settings would be, so each costs 5 API credits. The example below has five cases and a budget of 6 provider requests, so it can use up to 30 credits. [The smallest experiment](#the-smallest-experiment) has two cases, and uses at most 10.

Steps 1 and 2 send nothing, and need no credentials.

## Step 1: Write an experiment configuration

An experiment configuration is a YAML file. In your workspace, write this example to `experiment.yaml`. Portfolio123 accepted each of its cases in a live call.

```yaml
kind: experiment
schema_version: 1.0.0
experiment_id: earnyield-sensitivity                 # names the experiment; never sent
title: Earnings yield sensitivity
purpose: How do holdings, slippage, and a stricter liquidity rule change the earnings-yield screen's results?
prior_research:
  status: partial                                    # complete, partial, or unknown
  description: Earlier backtests of this screen in the Portfolio123 website compared 25 and 50 holdings. Other variations tried there weren't recorded.
baseline:
  universe: 'SP500'
  rules:
    - 'AvgDailyTot(30) > 1000000'
  ranking:
    formula: 'EarnYield'
    lower_is_better: false
  max_holdings: 25
  benchmark: 'SPY'
  start_date: 2016-01-01
  end_date: 2025-12-31
  rebalance_weeks: 4
  transaction_price: open
  slippage_percent: 0.25
  pit_method: complete
  precision: 4
variants:
  rules:
    - key: liquidity-100m
      description: A stricter liquidity floor, 100 million dollars a day.   # optional
      replace: 'AvgDailyTot(30) > 1000000'
      with: 'AvgDailyTot(30) > 100000000'
  max_holdings:
    - key: holdings-50
      value: 50
  slippage_percent:
    - key: slippage-050
      value: 0.5
budget:
  provider_requests: 6
```

As you read it, notice:

- **The research context.** `experiment_id` names the experiment: lowercase letters, digits, `-`, and `_`, as a review's labels are. `purpose`, the question the experiment addresses, is required. `prior_research` declares the earlier work on the same idea whose results you saw, in Trial Folio or anywhere else: `complete` when its description accounts for all of it, or says there was none; `partial` when there was more than it describes; or `unknown`. A description is required with `complete` or `partial`. Trial Folio records the declaration as you wrote it, and can't verify it. None of these is sent.
- **The baseline** holds a screen's settings: the keys of a [screen configuration](../reference/screen-configuration.md) from `universe` to `data_vendor`, with the same rules, so the text Portfolio123 receives goes in quotes. It has no `kind`, `schema_version`, `title`, or `purpose`: those are the experiment's. Every case uses the baseline's universe, ranking, benchmark, and dates.
- **Each variant changes one setting** of the baseline, and is listed under that setting, with a `key` that names its case, and an optional `description`. Four settings can vary, those live calls verified:
    - `rules`: `replace` one of the baseline's rules, written exactly as it is there, `with` another, as for a stricter liquidity floor; or `add` a rule, such as `'MktCap > 300'`, which excludes microcaps.
    - `max_holdings`, `rebalance_weeks` (1 or 4), and `slippage_percent`: a `value` other than the baseline's.

    A variant of any other setting, such as `universe`, fails with `config.invalid`. Another universe, or another `experiment_id`, is another experiment.

- **The default variant.** Without a `rebalance_weeks` list, Trial Folio adds a case for the other verified rebalance frequency: `rebalance-weeks-1` here, since the baseline rebalances every 4 weeks. It costs 5 credits, like any case. `rebalance_weeks: []` turns it off.
- **The budget** is the most provider requests the experiment may send, across every run of it, repeats included. It must be at least the number of cases, so each can be sent once. One more, as here, leaves room for one [repeat](../how-to/repeat-a-case.md). The plan shows its credits, at 5 a request.
- **The cases run in this order:** the baseline, then the variants of `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, each list in its order. This example has five: `baseline`, `liquidity-100m`, `holdings-50`, `rebalance-weeks-1`, and `slippage-050`.

[The experiment configuration reference](../reference/experiment-configuration.md) gives every key's rules.

### The smallest experiment

The smallest experiment is a baseline with no `variants`: the baseline and the default variant, two cases and 10 credits. To spend at most 10 credits, write this to `experiment.yaml` instead. Its budget, 2, lets each case be sent once, and leaves no room for a repeat.

```yaml
kind: experiment
schema_version: 1.0.0
experiment_id: earnyield-rebalancing
title: Earnings yield rebalancing
purpose: Does rebalancing every week, instead of every 4 weeks, change the earnings-yield screen's results?
prior_research:
  status: unknown                                    # complete, partial, or unknown
baseline:
  universe: 'SP500'
  rules:
    - 'AvgDailyTot(30) > 1000000'
  ranking:
    formula: 'EarnYield'
    lower_is_better: false
  max_holdings: 25
  benchmark: 'SPY'
  start_date: 2016-01-01
  end_date: 2025-12-31
  rebalance_weeks: 4
  transaction_price: open
  slippage_percent: 0.25
  pit_method: complete
  precision: 4
budget:
  provider_requests: 2
```

With it, the steps below are the same, except that the plan has two cases, `baseline` and `rebalance-weeks-1`, its budget is 2 provider requests, 10 credits, and step 2's check of the budget lowers it from 2 to 1, then restores 2.

## Step 2: Review the plan

Write the experiment under `runs/`, which the workspace's `.gitignore` keeps out of Git, because an experiment holds Portfolio123 data, as a run does.

1. In a terminal, run the configuration:

    ```sh
    trialfolio run experiment.yaml --out runs/study/
    ```

    It shows the whole plan, and asks you to type `approve`, as for a screen. The plan shows:

    - the experiment's ID, title, purpose, and prior research, which Trial Folio can't verify
    - the baseline's settings, once, with the provenance each value will have
    - each case, in the order it runs, with its key, its `case_id`, its change from the baseline, its description, and its request, exactly as it will be sent
    - the budget: the provider requests and authentication calls, and the credits at Portfolio123's documented cost
    - what's sent to Portfolio123, and what isn't, such as the experiment's ID, title, purpose, and prior research, and each case's key and description
    - the plan hash. One approval covers every case and the whole budget.

    The plan lists the five cases in the order above, each with its `case_id`, the default `rebalance-weeks-1` among them.

2. Type anything but `approve`, such as `stop`, to stop. It fails with `plan.approval_required`, exit code 2, and `runs/study/` doesn't exist.

3. See what a script would see. As in [your first backtest](first-backtest.md#step-6-review-the-plan), the pipe through `cat` makes the error output not a terminal, and the parentheses print the command's exit code:

    ```sh
    (trialfolio run experiment.yaml --out runs/study/ 2>&1; echo "Exit code: $?") | cat
    ```

    Without approval, from a script, it fails with `plan.approval_required`, exit code 2, and shows only the plan hash and the budget: 6 provider requests, 30 credits. `runs/study/` doesn't exist.

4. See how Trial Folio checks the budget. In `experiment.yaml`, change `provider_requests: 6` to `provider_requests: 4`, below the five cases, and run step 3's command again. For the smallest experiment, change `provider_requests: 2` to `provider_requests: 1`.

    A budget below the number of cases fails with `config.invalid`, exit code 3, and the message gives the number of cases. So does a variant of `universe`, and the message names the settings a variant may change.

5. Change `provider_requests` back to `6`, or to `2` for the smallest experiment.

## Step 3: Run the experiment

!!! warning "May be charged"
    Each case's request may be charged even if it fails. The plan's budget is the most the experiment can send: here, 6 provider requests, 30 credits at Portfolio123's documented cost. [Credits and uncertain charges](../explanation/credits-and-uncertain-charges.md) explains why Trial Folio counts requests this way.

1. Run the configuration in a terminal, and type `approve`. Or give the plan's hash with `--approve sha256:<the plan hash>`.

    ```sh
    trialfolio run experiment.yaml --out runs/study/
    ```

    Approved without credentials, it fails with `provider.auth_failed`, exit code 5. Nothing was sent, and `runs/study/` doesn't exist.

2. Wait. Trial Folio runs the cases one at a time, in order. It authenticates before the first request, and again only before a request that follows a 401 or 403, which drops its token. A case that fails is recorded, and the next one runs. Progress goes to the terminal.

    When every case succeeds, it exits 0. stdout says "Experiment completed", the session, where its report is, the plan hash, and that statistical validation and trading readiness are not assessed.

When a case doesn't succeed, the run exits 6, with `execution.partial`. stdout is empty, and the message on stderr lists each case that didn't succeed, with its outcome and error code.

- **A case awaiting a repeat** is one whose request may have reached Portfolio123, and none of whose attempts succeeded. The message gives the option that repeats each one. [Repeat a case](../how-to/repeat-a-case.md) shows how.
- **A case whose response was saved but failed validation,** `failed` with `provider.response_invalid`, has no tables and gets no option: its attempt succeeded, so the case is complete, and is never sent again. Its response stays in its attempt's folder, for you to report, as [the errors reference](../reference/errors.md) says.
- **Either way,** the run writes its report and manifest.

Two failures stop the run before its later cases, since each of those would fail the same way: Trial Folio's own authentication call failing, as with wrong credentials, and `provider.quota_exceeded`. The run ends with exit 6, and once you've fixed the cause, running the same command again runs the cases it didn't start. [Recover from an interrupt](../how-to/recover-from-an-interrupt.md) shows how to resume an experiment.

## Step 4: Read the results

An experiment's directory grows with each run of its command. `runs/study/` holds:

- `experiment.lock`, the lock, which claims the directory for the experiment, so that only one process runs it at a time. It isn't evidence.
- `plans/<n>/`, one for each plan you approved, numbered from 1: `configuration.yaml`, your configuration byte for byte; `plan.json`; and `experiment.json`, the experiment's research record as of that plan, with every plan before it and the reason for each revision
- `cases/<case_id>/attempts/<attempt_id>/`, each attempt's records, as a run's are. The attempt that authenticated also has `authenticating.json`.
- `cases/<case_id>/normalized/`, the case's `metrics.csv` and `settings.csv`, as a run's, once its attempt succeeds
- `sessions/<s>/`, one for each run of the command that passed its checks and its approval, numbered from 1: `session.json`, `report.html`, and `manifest.json`, which is written last
- `logs/trialfolio.log`, the log of every session

[Outputs](../reference/outputs.md) describes each file. Keep in mind:

- **A case's folder is named by its `case_id`,** never its key. The plan display and the report give each case's key beside its `case_id`.
- **The newest session's report and manifest supersede the earlier ones.** A session without a manifest, because its command was interrupted, reads as incomplete until the same command resumes the experiment.
- **It isn't a run.** `trialfolio report` and `trialfolio review` read runs only, and fail with `input.not_a_run` given an experiment. Each session writes its own report.

Your first run of the command is the experiment's first session, so its files are in `sessions/1/`.

1. Open `runs/study/sessions/1/report.html` in a browser. It holds:

    - the research notice, the Portfolio123 data statement, and "Not assessed", as in a run's report
    - the research context: the purpose, the prior research, and every plan, with its reason and what it changed
    - each case's change from the baseline, and its coverage
    - the metrics side by side, with a column for each case that has results. The report computes no difference between cases, and orders, ranks, and marks no case by a value.
    - the counts of cases and attempts; every case with its outcome and attempts; the cases awaiting a repeat, each with the option that repeats it; and the retired cases
    - in its limitations, that a prior-research declaration other than `complete` limits any claim drawn from the cases

2. Open `runs/study/sessions/1/manifest.json`. Its planned cases equal those that succeeded, failed, were skipped, are unknown, and haven't run yet, and the report gives the same counts.

3. Look in `runs/study/cases/`. Each case that succeeded has `metrics.csv` and `settings.csv` in its own `normalized/` folder, labeled with its `case_id`.

4. Open the log, `runs/study/logs/trialfolio.log`. It names cases by their `case_id`, and holds no case key or description, formula, or result.

## Next steps

- Resume the experiment after an interrupt or a failed case: [Recover from an interrupt](../how-to/recover-from-an-interrupt.md).
- Send a case awaiting a repeat again: [Repeat a case](../how-to/repeat-a-case.md).
- Change the configuration of an experiment you've run: [Revise an experiment](../how-to/revise-an-experiment.md).
- Run it from a script, with `--json`: [Use Trial Folio from a script](../how-to/use-from-a-script.md).
