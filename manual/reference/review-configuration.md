# Review configuration

A review configuration is a YAML file that names the saved runs `trialfolio review` compares, and the baseline it compares them with. This page lists its keys, and the rules they follow.

[The review configuration](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#review-configuration), in the specification, gives every key's rules. [Comparing runs](../how-to/compare-runs.md) gives the steps.

## Example

Put the file in your workspace, and name each run by its path from there:

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

## Keys

**At the top level:**

| Key | Required | Value |
|---|---|---|
| `kind` | Yes | `review` |
| `schema_version` | Yes | `1.0.0`. Any other value fails with `config.invalid`, and the message names the supported versions. |
| `title` | Yes | 1 to 200 characters. It heads the report. |
| `purpose` | No | 1 to 2,000 characters, not all whitespace. Without one, the report says no purpose was declared. |
| `baseline` | Yes | The `label` of one of the `results` |
| `results` | Yes | A list of at least two results, below |

**Each of the `results`:**

| Key | Required | Value |
|---|---|---|
| `label` | Yes | The result's name in the review, as [labels](#labels) describes. Each label is unique in the file. |
| `run` | Yes | The path of a complete run, which `trialfolio run` or `trialfolio demo` wrote, as [`run` paths](#run-paths) describes |
| `description` | No | 1 to 500 characters, shown in the report |
| `intended_changes` | No | A list of the [changes you meant to make](#intended-changes). Not allowed on the baseline. |

**Each of a result's `intended_changes`:**

| Key | Required | Value |
|---|---|---|
| `setting` | Yes | One of the [12 settings you can declare](#settings-you-can-declare). A result lists each setting at most once. |
| `reason` | Yes | 1 to 500 characters, shown in the report |

The values follow the rules in [how values are written](screen-configuration.md#how-values-are-written).

## Labels

- **Labels** name the results in the review, and `baseline` is one of them.
- **A label** is lowercase letters, digits, `-`, and `_`, starts with a letter or a digit, and is at most 64 characters long.
- **It names a folder** in the review, `inputs/<label>/`, so it can't be a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`.

## `run` paths

- **A `run` path is read from the configuration's folder,** wherever you run the command from, unless it's absolute.
- **Keep it relative,** as in the example. The review keeps a byte-for-byte copy of its configuration, so an absolute path, such as `/Users/you/research/runs/hold25`, would show anyone you share the review with where you keep your runs.
- **It names a complete run.** A `run` directory that doesn't exist fails with `input.not_found`, and one that isn't a complete run with `input.not_a_run`, both with exit code 3. The message names the result's label and its `run` path, and nothing is written. An experiment's directory isn't a run, so it fails with `input.not_a_run`.

## Intended changes

- **Declare each change you meant to make,** under the result that makes it, with a reason. The baseline declares nothing.
- **A declared change** is shown as intended.
- **A difference you didn't declare** is an unexplained mismatch. It's flagged when it's in a critical category: the dates, the benchmark, the currency, the costs, the execution, the universe, the data source, or the strategy.
- **A declared change whose values are the same** is `same`, flagged `intended_change_not_observed`. `transaction_price`, `pit_method`, and `precision` each take only one value so far, so a change declared to one of them can't be observed yet: it's `same`, flagged `intended_change_not_observed`.

### Settings you can declare

You can declare 12 settings, each named by its [screen configuration](screen-configuration.md) key:

- `universe`
- `rules`
- `ranking`
- `max_holdings`
- `benchmark`
- `start_date`
- `end_date`
- `rebalance_weeks`
- `transaction_price`
- `slippage_percent`
- `pit_method`
- `precision`

Any other name, including a setting that can't be declared, fails with `config.invalid`, and the message lists the valid names.
