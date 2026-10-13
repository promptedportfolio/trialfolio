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

The Key, Required, and Value columns of each table on this page are generated from the configuration's schema, [`schemas/review-configuration-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/review-configuration-1.0.0.schema.json), and What it's for is written here.

<!-- generated: review-configuration -->

| Key | Required | Value | What it's for |
|---|---|---|---|
| `kind` | Yes | `review` | Marks the file as a review configuration |
| `schema_version` | Yes | `1.0.0` | The version of the configuration's format. Any other value fails with `config.invalid`, and the message names the supported versions. |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | It heads the report |
| `purpose` | No | Text, 1 to 2,000 characters, not all whitespace | Why you're comparing the runs. Without one, the report says no purpose was declared. |
| `baseline` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`. The label of the result the others are compared with. | The `label` of one of the `results`, which the others are compared with |
| `results` | Yes | A list of at least 2 [objects](#review-configuration-results). At least two results, in the order the review's outputs list them. | The runs to compare, below |

<!-- end generated: review-configuration -->

<!-- generated: review-configuration-results -->

### Each of `results` { #review-configuration-results }

One compared result: a saved run, by its label.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `label` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | The result's name in the review, as [labels](#labels) describes. Each label is unique in the file. |
| `run` | Yes | Text, not all whitespace. The run's directory, as `trialfolio run` wrote it. A relative path is relative to the configuration file. | The path of a complete run, which `trialfolio run` or `trialfolio demo` wrote, as [`run` paths](#run-paths) describes |
| `description` | No | Text, 1 to 500 characters, not all whitespace. Up to 500 characters, shown in the report. | What the result is, shown in the report |
| `intended_changes` | No | A list of at least one [object](#review-configuration-results-intended-changes). The settings this result changes on purpose. Never on the baseline. | The [changes you meant to make](#intended-changes). Not allowed on the baseline. |

<!-- end generated: review-configuration-results -->

<!-- generated: review-configuration-results-intended-changes -->

### Each of `results[].intended_changes` { #review-configuration-results-intended-changes }

A change to one setting that a result declares, against the baseline.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `setting` | Yes | `universe`, `rules`, `ranking`, `max_holdings`, `benchmark`, `start_date`, `end_date`, `rebalance_weeks`, `transaction_price`, `slippage_percent`, `pit_method`, or `precision` | The setting changed, by its [screen configuration](screen-configuration.md) key: one of the [settings you can declare](#settings-you-can-declare). A result lists each setting at most once. |
| `reason` | Yes | Text, 1 to 500 characters, not all whitespace. Why the setting was changed, shown in the report: 1 to 500 characters. | Why you changed it, shown in the report |

<!-- end generated: review-configuration-results-intended-changes -->

The values follow the rules in [how values are written](screen-configuration.md#how-values-are-written).

## Labels

- **Labels** name the results in the review, and `baseline` is one of them. A label's Value, [above](#review-configuration-results), gives its form.
- **It names a folder** in the review, `inputs/<label>/`, which is why it can't be a name Windows reserves.

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

The settings you can declare are those that [`setting`](#review-configuration-results-intended-changes)'s Value lists, each named by its [screen configuration](screen-configuration.md) key. Any other name, including a setting that can't be declared, fails with `config.invalid`, and the message lists the valid names.
