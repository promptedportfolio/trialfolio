# Vary a ranking system's weights

Use this page to test how a screen's results depend on its ranking system: run an experiment whose variants change the weights of the system's nodes, at the top level or within a composite, or remove one factor. Each case's whole ranking definition is in the plan you approve, and in its records. It's new in release 0.4.0.

Each case writes its definition into `ApiRankingSystem`, a ranking system in your Portfolio123 account, then, 10 seconds later, backtests ranked by it. [`ApiRankingSystem` and the ranking lock](../explanation/apirankingsystem-and-the-ranking-lock.md) explains why, and what that changes in your account.

!!! warning "It overwrites `ApiRankingSystem`"
    Every run with a ranking definition overwrites `ApiRankingSystem` in your account. Keep nothing of your own in it, and don't edit it in Portfolio123's website while a run runs.

## Before you start

- **A Portfolio123 subscription with the appropriate access, your credentials, and the license acknowledged,** as in [your first experiment](../tutorials/first-experiment.md#what-you-need).
- **API credits.** Each case sends two requests: a `rank_update`, at 1 credit, and its backtest, at 5, at Portfolio123's documented costs. So each case costs 6 credits. The example below has four cases, and a budget of 8 provider requests, 24 credits.
- **The ranking system's definition.** Open the ranking system in Portfolio123's website, and find its XML in the Text Editor, under Ranking System → Factors. Or take a [ranking snapshot](take-a-ranking-snapshot.md) of it, which reads the definition from your account, and records where it came from.

Steps 1 to 3 send nothing, and need no credentials.

## Step 1: Save the definition in a file

In your workspace, save the definition's XML, exactly as the Text Editor shows it, to a file of its own, such as `ranking/value-momentum.xml`. Save it as UTF-8 text.

The example uses the definition [ranking definitions](../reference/ranking-definitions.md#an-example) shows: three composites, Value, Momentum, and Quality, at 40, 30, and 30, of two factors each, at 50. Its names and weights are invented, and its formulas are left out, as `…`, so Portfolio123 wouldn't run it: use your own system's definition.

Trial Folio accepts a definition of the form live calls verified: one `RankingSystem` element, whose nodes are `Composite`, `StockFormula`, and `StockFactor` elements, each with a `Weight` greater than 0. [Ranking definitions](../reference/ranking-definitions.md) gives every rule.

## Step 2: Write the experiment configuration

Write an experiment configuration with `schema_version: 1.1.0`, whose baseline's `ranking` names the file, with the system's ranking method, and whose `variants` list ranking variants. Save it in your workspace, such as `experiment.yaml`:

```yaml
kind: experiment
schema_version: 1.1.0                                # 1.1.0 for a ranking definition
experiment_id: value-momentum-weights
title: Value, momentum, and quality weights
purpose: Does the screen's result depend on how its ranking weighs value, or on the sales-yield factor?
prior_research:
  status: unknown
baseline:
  universe: 'SP500'
  rules:
    - 'AvgDailyTot(30) > 1000000'
  ranking:
    definition: 'ranking/value-momentum.xml'         # the file from step 1
    ranking_method: percentile_nas_negative          # or percentile_nas_neutral
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
  ranking:
    - key: value-heavy
      description: More weight on value, taken equally from momentum and quality.
      set: {'Value': 60, 'Momentum': 20, 'Quality': 20}            # the top-level nodes
    - key: tilt-earnings-yield
      set: {'Value/Earnings Yield': 70, 'Value/Sales Yield': 30}   # within a composite
    - key: no-sales-yield
      remove: 'Value/Sales Yield'                                  # a factor removed,
      set: {'Value/Earnings Yield': 100}                           # with the weights left
  rebalance_weeks: []                                # no default rebalance variant
budget:
  provider_requests: 8                               # two requests a case
```

- **`ranking_method`** is the ranking system's method for a stock whose value is missing: `percentile_nas_negative` for Percentile NAs Negative, or `percentile_nas_neutral` for Percentile NAs Neutral. Give the one your system uses in the website: Trial Folio sends it with each case's definition.
- **A weight variant** gives `set`: the weight of every node of one parent, the top level or one composite, each once. The weights must sum to what the same nodes' weights sum to in the baseline, so a variant moves weight between siblings. `value-heavy` moves weight to Value from Momentum and Quality, and keeps their sum, 100; `tilt-earnings-yield` moves weight between Value's two factors.
- **A removal variant** gives `remove`, the path of one factor, and `set`, the weights of the nodes its parent keeps, which sum to what the parent's nodes summed to with it. `no-sales-yield` removes Sales Yield from Value, and gives its 50 to Earnings Yield, which gets 100. A composite can't be removed, and a composite must keep at least one node.
- **Each path names one node:** its name from the top level down, separated by `/`, in single quotes. A node without a name, such as a factor chosen from Portfolio123's list, or one of two nodes that share a name, is named by its position, such as `'Value/#2'`. [Node paths](../reference/ranking-definitions.md#node-paths) gives every rule.
- **`rebalance_weeks: []`** turns off the default rebalance variant, which would add a case of its own, at 6 credits. Leave it out to keep that case.
- **The budget** covers at least two requests a case. More leaves room to [repeat a case](repeat-a-case.md), at two requests each time.

Every other key is an experiment configuration's, as [your first experiment](../tutorials/first-experiment.md#step-1-write-an-experiment-configuration) explains, and [the experiment configuration](../reference/experiment-configuration.md#ranking-variants) gives every rule. A variant of another setting, such as `max_holdings`, can run beside the ranking variants: its case has the baseline's definition.

## Step 3: Review the plan

1. In a terminal, run the configuration into a new directory under `runs/`, which the workspace's `.gitignore` keeps out of Git:

    ```sh
    trialfolio run experiment.yaml --out runs/weights/
    ```

    Trial Folio reads the definition's file, checks the variants against it, and shows the whole plan. Besides what any experiment's plan shows ([your first experiment](../tutorials/first-experiment.md#step-2-review-the-plan)), it shows:

    - that the run overwrites `ApiRankingSystem` in your account, with each case's definition, before the case's backtest, which is sent 10 seconds after its `rank_update`, and what the [ranking lock](../explanation/apirankingsystem-and-the-ranking-lock.md#the-ranking-lock) can't exclude;
    - the definition's source: a file, by the definition's hash;
    - each node's weight, among the baseline's settings, as `ranking_weight` and the node's path, such as `ranking_weight Value/Earnings Yield: 50`;
    - each case's change, as in this excerpt of the example's plan. Its values are the example's, which are invented:

        ```text
        Case baseline (case-a8c9e5f0cbee31ad): the baseline
        Case value-heavy (case-3dbf62e2f8ee9d8e): ranking: sets the weights of Value to 60, Momentum to 20, Quality to 20
        Case tilt-earnings-yield (case-4aacdc96152316a0): ranking: sets the weights of Value/Earnings Yield to 70, Value/Sales Yield to 30
        Case no-sales-yield (case-600a63188a800a32): ranking: removes the factor Value/Sales Yield, and sets the weights of Value/Earnings Yield to 100
        ```

    - each case's `rank_update`, exactly as it will be sent, with the case's whole definition line by line, then its backtest, ranked by `ApiRankingSystem`;
    - the budget: 8 provider requests, 24 credits, with each case's two requests at 6 credits.

2. Check each case's definition: only the weights its variant changes differ from your file, and a removal leaves out the factor's element. Then type anything but `approve`, such as `stop`, to stop. Nothing is sent, and `runs/weights/` doesn't exist.

A path that names no node, or more than one, weights whose sum differs from the baseline's, a weight of 0, or a removal that would leave a composite empty fails with `config.invalid`, exit code 3, before the plan is shown. The message names the variant by its place in the file, such as `variants.ranking[1]`, and never quotes a path, a name, or a weight.

## Step 4: Run it

1. Run the same command in a terminal, and type `approve`. Or give the plan's hash with `--approve sha256:<the plan hash>`.

2. Wait. Trial Folio takes the ranking lock, then runs the cases one at a time. For each case, the terminal shows its `rank_update`, `POST /rank`, then that it waits 10 seconds, then its backtest, `POST /screen/backtest`, and how the attempt ended. A case's backtest is sent only after its `rank_update` succeeded, and 10 seconds after its response, so that Portfolio123 ranks it by the definition just written ([why it waits](../explanation/apirankingsystem-and-the-ranking-lock.md#why-it-waits-10-seconds)). So each case takes at least 10 seconds.

    When every case succeeds, it exits 0, and stdout says "Experiment completed", as for any experiment.

A case whose backtest returned the same results as the case before it in the run, apart from the cost and the remaining quota, though it was ranked by another definition, is `failed`, with `provider.response_invalid`: Portfolio123 may have ranked it by the earlier case's definition. Its response is kept, it has no tables, and the run ends with `execution.partial`, exit code 6, whose message says why, and gives the option that repeats it. Identical results can be genuine, as when a changed weight doesn't change which stocks the screen selects. [Repeat the case](repeat-a-case.md) to send it again.

Another Trial Folio process on your machine that's writing `ApiRankingSystem` makes the run fail with `experiment.locked`, exit code 4, before anything is sent: wait for it to end, and run the command again.

## Step 5: Read the results

An experiment with a ranking definition holds what any experiment holds ([your first experiment](../tutorials/first-experiment.md#step-4-read-the-results)), and:

- **`plans/<n>/definition.xml`,** your definition file, byte for byte, beside the plan's `configuration.yaml`;
- **in each attempt's folder,** `rank-update-request.json`, the `rank_update` with the case's whole definition, `updating.json`, its start record, and `rank-update-response.json`, Portfolio123's response, besides the backtest's files;
- **in each case's `normalized/settings.csv`,** a `ranking_weight` row for each node, right after `ranking`, with the node's path in the `node` column. A weight the case's variant changes takes its `original_key` from the variant, such as `variants.ranking[2].set[0]`, and every other from `baseline.ranking.definition`.

Open the newest session's `report.html`. Among the definitions and changes from the baseline, it shows a table of each case's weights, aligned by the baseline's nodes, with `Removed` for the factor a variant removes. This is the example's table, whose weights are invented:

| Node | baseline | value-heavy | tilt-earnings-yield | no-sales-yield |
|---|---|---|---|---|
| Value | 40 | 60 | 40 | 40 |
| Value/Earnings Yield | 50 | 50 | 70 | 100 |
| Value/Sales Yield | 50 | 50 | 30 | Removed |
| Momentum | 30 | 20 | 30 | 30 |
| Momentum/Six-Month Return | 50 | 50 | 50 | 50 |
| Momentum/Year Return | 50 | 50 | 50 | 50 |
| Quality | 30 | 20 | 30 | 30 |
| Quality/Return on Equity | 50 | 50 | 50 | 50 |
| Quality/Gross Margin | 50 | 50 | 50 | 50 |

The report also gives the definition's source, each attempt's `rank_update` with its cost beside the backtest's, and, among its limitations, that each case's definition was written into `ApiRankingSystem`, and what the ranking lock can't exclude. It orders, ranks, and marks no case.

## Run one screen with a definition

A [screen configuration](../reference/screen-configuration.md#ranking) with `schema_version: 1.1.0` can rank by a definition too:

```yaml
ranking:
  definition: 'ranking/value-momentum.xml'
  ranking_method: percentile_nas_negative
```

Its run sends a `rank_update`, then, 10 seconds after its response, its backtest: 2 provider requests, 6 credits. The run keeps `definition.xml` beside `configuration.yaml`, and its `settings.csv` has a weight row for each node. A screen run of the baseline's definition, with the baseline's settings, is the same case as the experiment's baseline, with the same `case_id`.

## Compare runs' weights

[`trialfolio review`](compare-runs.md) compares runs ranked by definitions node by node: `differences.csv` has a `ranking_weight` row for each node, after `ranking`, named by its path in the `node` column. To show changed weights as the change you meant, declare `ranking` in the result's `intended_changes`:

```yaml
    intended_changes:
      - setting: ranking
        reason: More weight on value.
```

Each weight that differs is then `intended_change`, with that reason. Without the declaration, each is an `unexplained_mismatch`, flagged as critical. A node one run's definition lacks is `absent` in it, or `unknown` against a ranking by name or ID, whose definition wasn't recorded.

## Resume, repeat, or revise it

- **Resume** with the same command, as for any experiment ([recover from an interrupt](recover-from-an-interrupt.md)). A resume that sends a case sends its `rank_update` and its backtest again, and takes the ranking lock first.
- **A case whose `rank_update` may have reached Portfolio123** is possibly charged, even when its backtest wasn't sent, so it waits for a [repeat](repeat-a-case.md). So does a case whose backtest returned the previous case's results, or whose response failed validation. A repeat sends both requests again, two requests from the budget.
- **A resume that sends no case,** because none is due and you name no repeat, says that it doesn't write `ApiRankingSystem`, rather than that it overwrites it.
- **Changing the definition's file, or the variants,** changes the plan, which you [revise](revise-an-experiment.md) with `--revision-reason`. A case whose definition changes is a new case, and the old one is retired. A ranking variant whose definition stays the same, byte for byte, keeps its results.

## Check

- The plan shows that the run overwrites `ApiRankingSystem`, that each backtest is sent 10 seconds after its `rank_update`, and each case's whole definition, before you approve it.
- It exits 0, and each case that succeeded has a `ranking_weight` row for each node of its definition in its `settings.csv`.
- `plans/1/definition.xml` is your definition file, byte for byte.
- The report shows each case's weights side by side, and ranks no case.
