# Compare runs with a review

`trialfolio review` compares saved runs with a baseline you choose. It shows which settings differ, as changes you declared or as unexplained mismatches, and how each metric moved. Use it when you've run versions of a screen, and want to see how they differ from one of them.

It doesn't rank the runs, or say which strategy is better.

## Before you start

- **Runs that finished,** written by `trialfolio run` or `trialfolio demo`. An experiment isn't a run: `trialfolio review` fails with `input.not_a_run` given one, and each of its sessions writes its own report.
- **No credentials.** A review reads the runs offline, and sends nothing to Portfolio123. Like `trialfolio run`, it needs your [acknowledgment of the license](../tutorials/first-backtest.md).

## Steps

1. Write a review configuration, a YAML file that names the runs and the baseline. Put it in your workspace, such as `review.yaml`, and name each run by its path from there:

    ```yaml
    kind: review
    schema_version: 1.0.0
    title: Holdings 25 versus 50
    purpose: Check whether doubling holdings changes risk as expected.   # optional
    baseline: hold25
    results:
      - label: hold25
        run: runs/hold25
      - label: hold50
        run: runs/hold50
        description: The same screen, with 50 holdings.                 # optional
        intended_changes:
          - setting: max_holdings
            reason: Doubling holdings is the change under review.
    ```

    - **Labels** name the results in the review, and `baseline` is one of them. A label is lowercase letters, digits, `-`, and `_`, starts with a letter or a digit, and is at most 64 characters long. It names a folder in the review, so it can't be a name Windows reserves, such as `con` or `nul`.
    - **A `run` path is read from the configuration's folder,** wherever you run the command from, unless it's absolute. Keep it relative, as above. The review keeps a byte-for-byte copy of its configuration, so an absolute path, such as `/Users/you/research/runs/hold25`, would show anyone you share the review with where you keep your runs.
    - **Declare each change you meant to make,** under the result that makes it, with a reason. A declared change is shown as intended. A difference you didn't declare is an unexplained mismatch, and it's flagged in a critical category: the dates, the benchmark, the currency, the costs, the execution, the universe, the data source, and the strategy. The baseline declares nothing. You can declare 12 settings: `universe`, `rules`, `ranking`, `max_holdings`, `benchmark`, `start_date`, `end_date`, `rebalance_weeks`, `transaction_price`, `slippage_percent`, `pit_method`, and `precision`.

    [The review configuration](../reference/review-configuration.md) gives every key's rules.

2. Review the runs, into a new or empty directory under `reviews/`, which [keeps the review out of Git](#keep-reviews-out-of-git):

    ```sh
    trialfolio review review.yaml --out reviews/holdings/
    ```

3. Open `reviews/holdings/report.html` in a browser. [Outputs](../reference/outputs.md) describes what a review's directory holds, and what its report shows.

## Runs ranked by a definition

When either run's ranking is a ranking system's definition, given in a file or by a snapshot, the review compares its weights node by node: `differences.csv` has a `ranking_weight` row for each node, right after `ranking`, named by its path in the `node` column.

- **Declare `ranking`** in `intended_changes` to show the changed weights as the change you meant. Each weight that differs is then `intended_change`, with `ranking`'s reason. Without the declaration, each is an `unexplained_mismatch`, flagged as critical.
- **A node one run's definition lacks** is `absent` in that run, or `unknown` against a ranking by name or ID, whose definition wasn't recorded.
- **Such a review** writes `differences.csv` 1.1.0, with its `node` column, and its report says how the weights are compared.

[Vary a ranking system's weights](vary-a-ranking-systems-weights.md#compare-runs-weights) shows an example. A removal shifts the positions of the nodes after it, so a node without a name may be compared with another node: an experiment's report, which aligns each case's weights by the baseline's nodes, doesn't have that limit ([differences between screen runs](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#differences-between-screen-runs)).

## Try it with two demo runs

You can try a review without credentials, on two demo runs.

1. Write two demo runs:

    ```sh
    trialfolio demo --out runs/demo-a/
    trialfolio demo --out runs/demo-b/
    ```

2. Write a review configuration that names them, such as `demo-review.yaml`:

    ```yaml
    kind: review
    schema_version: 1.0.0
    title: Two demo runs
    baseline: demo-a
    results:
      - label: demo-a
        run: runs/demo-a
      - label: demo-b
        run: runs/demo-b
    ```

3. Review them:

    ```sh
    trialfolio review demo-review.yaml --out reviews/demo/
    ```

The two demo runs saved byte-identical responses, so the review warns that they share one, as the [checks](#check) say. Its report names the synthetic results before any result, and labels them synthetic wherever their values appear.

## Keep reviews out of Git

A review of real runs holds Portfolio123 data, in its copies of their tables, as a run does. The `.gitignore` that `trialfolio init` writes keeps `reviews/` out of Git, as it does `runs/` and `reports/`, so write reviews there.

A workspace that Trial Folio 0.1.0 set up lacks that line. If you keep it in Git, add `/reviews/` to its `.gitignore`.

## Check

- It exits 0. stdout says "Review completed", where the report is, how many setting rows are flagged and how many metric rows are unavailable, the review ID, and that statistical validation and trading readiness are not assessed.
- In the review's `normalized/differences.csv`, the `intended_change` rows are the changes you declared. A declared change whose values are the same is `same`, flagged `intended_change_not_observed`.
- When two results' runs saved byte-identical responses, as two demo runs do, it warns that they share one response, and the metric rows of each but the baseline are flagged `identical_source`.
- The runs' directories aren't changed.
- A `run` directory that doesn't exist fails with `input.not_found`, and one that isn't a complete run with `input.not_a_run`, both with exit code 3. The message names the result's label and its `run` path, and nothing is written.
- Reviewing into a directory that isn't empty fails with `output.not_empty`, exit code 4, and changes nothing in it.
