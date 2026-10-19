# Experiment configuration

An experiment configuration is a YAML file that describes a baseline screen and a few variants of it, each changing one setting of the baseline, for `trialfolio run` to run under one plan, one approval, and one budget. This page lists its keys, and the rules they follow.

[The experiment configuration](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-configuration), in the specification, gives every key's rules. [Your first experiment](../tutorials/first-experiment.md) runs one.

## Example

This is the documented example. Portfolio123 accepted each of its cases in a live call.

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

It has five cases, in this order: `baseline`, `liquidity-100m`, `holdings-50`, `rebalance-weeks-1`, and `slippage-050`. Its plan's budget is 6 provider requests, 30 credits.

## Keys

The Key, Required, and Value columns of each table on this page are generated from the configuration's schema, [`schemas/experiment-configuration-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/experiment-configuration-1.0.0.schema.json), and What it's for is written here.

<!-- generated: experiment-configuration -->

| Key | Required | Value | What it's for |
|---|---|---|---|
| `kind` | Yes | `experiment` | Marks the file as an experiment configuration |
| `schema_version` | Yes | `1.0.0` | The version of the configuration's format. Any other value fails with `config.invalid`, and the message names the supported versions. From release 0.4.0, `trialfolio run` also reads `1.1.0`, which adds a baseline ranked by a ranking system's definition, and ranking variants ([experiment configuration](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-configuration)). |
| `experiment_id` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`. The experiment's identity. | The experiment's name, as [the research context](#the-research-context) describes |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | It heads the report |
| `purpose` | Yes | Text, 1 to 2,000 characters, not all whitespace. The question the experiment addresses. Required: it's part of the research history. | The question the experiment addresses |
| `prior_research` | Yes | An [object](#experiment-configuration-prior-research) | The [prior-research declaration](#the-research-context) |
| `baseline` | Yes | An [object](#experiment-configuration-baseline) | The [baseline](#the-baseline) screen's settings |
| `variants` | No | An [object](#experiment-configuration-variants). When it's absent, the only variant is the default. | The [variants](#variants), by the setting each one changes. Without it, the only variant is the [default](#the-default-variant). |
| `budget` | Yes | An [object](#experiment-configuration-budget) | The [budget](#the-budget) |

<!-- end generated: experiment-configuration -->

**Sent to Portfolio123:** the baseline's settings, in each case's request, and each variant's change, in its case's request. Trial Folio never sends `kind`, `schema_version`, `experiment_id`, `title`, `purpose`, `prior_research`, `budget`, or a variant's `key` and `description`.

The values follow the rules in [how values are written](screen-configuration.md#how-values-are-written).

## The research context

None of these is sent.

- **`experiment_id`** names the experiment, as a review's labels name results. Its Value, [above](#keys), gives its form. Another `experiment_id` is another experiment.
- **`purpose`,** the question the experiment addresses, is required.
- **`prior_research`** declares the earlier work on the same idea whose results you saw, in Trial Folio or anywhere else. Trial Folio records the declaration as you wrote it, and can't verify it.

<!-- generated: experiment-configuration-prior-research -->

### `prior_research` { #experiment-configuration-prior-research }

The prior-research declaration: earlier work on the same idea whose outcomes the user saw, in Trial Folio or anywhere else. Trial Folio can't verify it, and records it as written.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `status` | Yes | `complete`, `partial`, or `unknown`. `complete`: the description accounts for all of it, or says there was none. `partial`: for some of it. `unknown`: the user can't say what earlier work there was. | How much of the earlier work the description accounts for |
| `description` | No | Text, 1 to 5,000 characters, not all whitespace. Required with `complete` or `partial`: 1 to 5,000 characters. | The earlier work. It may also be given with `unknown`. |

<!-- end generated: experiment-configuration-prior-research -->

## The baseline

- **`baseline` holds a screen's settings:** the keys of a [screen configuration](screen-configuration.md#keys) from `universe` to `data_vendor`, with the same rules. So the text Portfolio123 receives goes in quotes.
- **It has no `kind`, `schema_version`, `title`, or `purpose`:** those are the experiment's.
- **Every case uses the baseline's universe, ranking, benchmark, and dates.** Another universe is another experiment.
- **Its case's key is `baseline`.**

<!-- generated: experiment-configuration-baseline -->

### `baseline` { #experiment-configuration-baseline }

A screen's settings: a screen configuration's keys from `universe` to `data_vendor`, with their types, rules, and verified values. An experiment's baseline is one (docs/contracts.md, the baseline).

| Key | Required | Value | What it's for |
|---|---|---|---|
| `universe` | Yes | Text, not all whitespace | A Portfolio123 universe, by name, in quotes, such as `'SP500'`. Every case uses it. |
| `rules` | Yes | A list of at least one item, each text, not all whitespace | The screening formulas, each in quotes. Their order is kept. |
| `ranking` | Yes | One of these objects: [`baseline.ranking` with `formula`](#experiment-configuration-baseline-ranking-formula), [`baseline.ranking` with `name`](#experiment-configuration-baseline-ranking-name), or [`baseline.ranking` with `id`](#experiment-configuration-baseline-ranking-id) | How the screen ranks stocks: one of the three forms below, as in a [screen configuration](screen-configuration.md#ranking). Every case uses it. |
| `max_holdings` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The most stocks held |
| `benchmark` | Yes | Text, not all whitespace | A Portfolio123 benchmark symbol, in quotes, such as `'SPY'`. Every case uses it. |
| `start_date` | Yes | A date, `YYYY-MM-DD` | The backtest's first day. Every case uses it. |
| `end_date` | Yes | A date, `YYYY-MM-DD` | The backtest's last day, later than `start_date`. Every case uses it. There's no default of today. |
| `rebalance_weeks` | Yes | `1` or `4` | The weeks between rebalances |
| `transaction_price` | Yes | `open` | The price trades use |
| `slippage_percent` | Yes | A number, 0 or more, and less than 10,000,000,000,000,000. Plain notation, with at most 4 digits after the decimal point and 15 significant digits. Never a string. | The slippage, a decimal in percent: `0.25` means 0.25%. There's no default of zero. |
| `pit_method` | Yes | `complete` | Portfolio123's point-in-time method |
| `precision` | Yes | `4` | The decimal places in results |
| `data_vendor` | No | `FactSet` | The data vendor: `FactSet`, the [only value accepted](screen-configuration.md#data_vendor) |

<!-- end generated: experiment-configuration-baseline -->

<!-- generated: experiment-configuration-baseline-ranking-formula -->

### `baseline.ranking` with `formula` { #experiment-configuration-baseline-ranking-formula }

A ranking by a single formula, the recommended form.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | The formula, in quotes, such as `'EarnYield'` |
| `lower_is_better` | Yes | `true` or `false` | Whether the formula's lower values rank higher, such as `false` |

<!-- end generated: experiment-configuration-baseline-ranking-formula -->

<!-- generated: experiment-configuration-baseline-ranking-name -->

### `baseline.ranking` with `name` { #experiment-configuration-baseline-ranking-name }

An existing ranking system in the account, by name. It's recorded as not snapshotted.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `name` | Yes | Text, not all whitespace | The name of an existing ranking system in your account, in quotes, such as `'My ranking system'` |

<!-- end generated: experiment-configuration-baseline-ranking-name -->

<!-- generated: experiment-configuration-baseline-ranking-id -->

### `baseline.ranking` with `id` { #experiment-configuration-baseline-ranking-id }

An existing ranking system in the account, by ID. It's recorded as not snapshotted.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `id` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The ID of an existing ranking system in your account, such as `12345` |

<!-- end generated: experiment-configuration-baseline-ranking-id -->

## Variants

**Each variant changes one setting** of the baseline, and is listed under that setting, with a `key` that names its case, and an optional `description`. Four settings can vary, those that live calls verified. A variant of any other setting, such as `universe`, fails with `config.invalid`, and the message names the settings a variant may change.

<!-- generated: experiment-configuration-variants -->

### `variants` { #experiment-configuration-variants }

The variants, by the setting each one changes, in lists whose order is kept. Each list holds at least one variant, except `rebalance_weeks`'s, where an empty list turns the default variant off.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `rules` | No | A list of at least one [object](#experiment-configuration-variants-rules) | Variants that `replace` one of the baseline's rules, written exactly as it is there, `with` another, as for a stricter liquidity floor; or `add` a rule, such as `'MktCap > 300'`, which excludes microcaps |
| `max_holdings` | No | A list of at least one [object](#experiment-configuration-variants-max-holdings) | Variants whose `value` is another number of holdings than the baseline's |
| `rebalance_weeks` | No | A list of [objects](#experiment-configuration-variants-rebalance-weeks). Replaces the default rebalance variant. An empty list turns it off. | Variants whose `value` is another rebalance frequency than the baseline's |
| `slippage_percent` | No | A list of at least one [object](#experiment-configuration-variants-slippage-percent) | Variants whose `value` is another slippage than the baseline's, in percent |

<!-- end generated: experiment-configuration-variants -->

<!-- generated: experiment-configuration-variants-rules -->

### Each of `variants.rules` { #experiment-configuration-variants-rules }

A variant of the rules: one of the baseline's rules replaced, with `replace` and `with`, or a rule added, with `add`.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`. The case's `case_key`: unique among the experiment's cases, the default's included, and not `baseline`. | Its case's key, in the same form as `experiment_id`. It's unique among the experiment's cases, the default variant's included, and isn't `baseline`. |
| `description` | No | Text, 1 to 500 characters, not all whitespace. Up to 500 characters, shown in the report. | What the variant is, shown in the report |
| `add` | No | Text, not all whitespace. A screening formula, added after the baseline's rules. | A screening formula, in quotes, added after the baseline's rules. Give it, or `replace` and `with`. |
| `replace` | No | Text, not all whitespace. One of the baseline's rules, the same text, character for character. | One of the baseline's rules, in quotes, written exactly as it is there. Give it with `with`, unless `add` is given. |
| `with` | No | Text, not all whitespace. The formula that takes `replace`'s place, so the rules keep their order. | The formula, in quotes, that takes the replaced rule's place, so the rules keep their order. Give it with `replace`. |

<!-- end generated: experiment-configuration-variants-rules -->

<!-- generated: experiment-configuration-variants-max-holdings -->

### Each of `variants.max_holdings` { #experiment-configuration-variants-max-holdings }

A variant of the maximum holdings.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`. The case's `case_key`: unique among the experiment's cases, the default's included, and not `baseline`. | Its case's key, in the same form as `experiment_id`. It's unique among the experiment's cases, the default variant's included, and isn't `baseline`. |
| `description` | No | Text, 1 to 500 characters, not all whitespace. Up to 500 characters, shown in the report. | What the variant is, shown in the report |
| `value` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The case's maximum holdings |

<!-- end generated: experiment-configuration-variants-max-holdings -->

<!-- generated: experiment-configuration-variants-rebalance-weeks -->

### Each of `variants.rebalance_weeks` { #experiment-configuration-variants-rebalance-weeks }

A variant of the rebalance frequency.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`. The case's `case_key`: unique among the experiment's cases, the default's included, and not `baseline`. | Its case's key, in the same form as `experiment_id`. It's unique among the experiment's cases, the default variant's included, and isn't `baseline`. |
| `description` | No | Text, 1 to 500 characters, not all whitespace. Up to 500 characters, shown in the report. | What the variant is, shown in the report |
| `value` | Yes | `1` or `4` | The case's weeks between rebalances |

<!-- end generated: experiment-configuration-variants-rebalance-weeks -->

<!-- generated: experiment-configuration-variants-slippage-percent -->

### Each of `variants.slippage_percent` { #experiment-configuration-variants-slippage-percent }

A variant of the slippage, in percent: a decimal, read and normalized by the decimals rules.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`. The case's `case_key`: unique among the experiment's cases, the default's included, and not `baseline`. | Its case's key, in the same form as `experiment_id`. It's unique among the experiment's cases, the default variant's included, and isn't `baseline`. |
| `description` | No | Text, 1 to 500 characters, not all whitespace. Up to 500 characters, shown in the report. | What the variant is, shown in the report |
| `value` | Yes | A number, 0 or more, and less than 10,000,000,000,000,000. Plain notation, with at most 4 digits after the decimal point and 15 significant digits. Never a string. | The case's slippage, a decimal in percent |

<!-- end generated: experiment-configuration-variants-slippage-percent -->

**Rules that span keys:**

- **One change per variant.** A variant in `rules` holds `add`, or `replace` and `with`, never both.
- **A variant changes something.** A `value` differs from the baseline's: `0.250` is the baseline's `0.25`. `add` and `with` aren't the same text as any of the baseline's rules. No two cases have the same settings.
- **A variant that breaks a rule** fails with `config.invalid`, and the message names it by its place in the file, such as `variants.max_holdings[0]`, never by its key.
- **Not offered:** a variant that removes one of the baseline's rules.

## The default variant

- **Without a `rebalance_weeks` list,** Trial Folio adds a case for the other verified rebalance frequency: `rebalance-weeks-1` in the example, since the baseline rebalances every 4 weeks, or `rebalance-weeks-4` for a baseline that rebalances every week. It has no description.
- **It costs 5 credits,** like any case. The plan shows it, and the budget must cover it.
- **`rebalance_weeks: []`** turns it off. A `rebalance_weeks` list of your own replaces it.

## The budget

<!-- generated: experiment-configuration-budget -->

### `budget` { #experiment-configuration-budget }

The experiment's request budget, across every `run` that resumes it.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `provider_requests` | Yes | An integer, from 1 to 1,801,439,850,948,198. The most provider requests the experiment may send: at least the number of cases, and few enough that the plan's credits can be hashed. | The most provider requests the experiment may send, across every run of it, repeats included |

<!-- end generated: experiment-configuration-budget -->

- **At least one per case,** so each can be sent once. A smaller budget fails with `config.invalid`, exit code 3, and the message gives the number of cases.
- **One more,** as in the example, leaves room for one [repeat](../how-to/repeat-a-case.md).
- **Requests, not credits.** The plan shows its credits, at 5 a request. [Credits and uncertain charges](../explanation/credits-and-uncertain-charges.md) explains why.

## Cases and their order

- **Each case is a screen backtest,** sent just as a screen configuration with its settings would be, so each costs 5 API credits.
- **The cases run in this order:** the baseline, then the variants of `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, each list in its order. The default variant comes in `rebalance_weeks`'s place. The order of the keys in `variants` doesn't matter.
- **The smallest experiment** is a baseline with no `variants`: the baseline and the default variant, two cases and 10 credits.
- **At least two cases.** An experiment whose only case is its baseline, such as one with `rebalance_weeks: []` and no other variant, fails with `config.invalid`. A [screen configuration](screen-configuration.md) runs one screen.

## What's rejected

Each of these fails with `config.invalid`, exit code 3, and nothing is sent or created:

- a budget below the number of cases: the message gives the number of cases;
- a variant of a setting that can't vary, such as `universe`: the message names the settings a variant may change;
- anything a [screen configuration](screen-configuration.md#whats-rejected) rejects, in the baseline.
