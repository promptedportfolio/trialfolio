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

### A ranking example

This is the documented [ranking example](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-example), in `schema_version` `1.1.0`. Its baseline is ranked by a ranking system's definition, in the file `ranking/value-momentum.xml` beside the configuration, and its variants change the definition's weights, or remove a factor. [Ranking definitions](ranking-definitions.md#an-example) shows the definition, and [vary a ranking system's weights](../how-to/vary-a-ranking-systems-weights.md) runs it.

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
    definition: 'ranking/value-momentum.xml'         # the definition's file
    ranking_method: percentile_nas_negative
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
  rebalance_weeks: []
budget:
  provider_requests: 8                               # two requests a case
```

It has four cases, in this order: `baseline`, `value-heavy`, `tilt-earnings-yield`, and `no-sales-yield`. Each case sends two requests: a `rank_update`, which writes its definition into `ApiRankingSystem` in your account, then its backtest, ranked by that system. So its plan's budget is 8 provider requests, 24 credits.

## Two versions

An experiment configuration is version `1.0.0` or `1.1.0`, as its `schema_version` says, and `trialfolio run` reads both.

- **`1.0.0`,** the version of the first example, has every key on this page but two: its baseline's `ranking` takes a formula, or a ranking system in your account by name or by ID, and its `variants` have no `ranking`.
- **`1.1.0`,** from release 0.4.0, adds a baseline ranked by a ranking system's definition, in a file, or by a ranking snapshot, as a [screen configuration](screen-configuration.md#ranking) `1.1.0` can be, and, with one, [ranking variants](#ranking-variants). It adds nothing else.

A `1.0.0` file that gives `definition`, `snapshot`, or ranking variants fails with `config.invalid`, and the message says they need `1.1.0`.

## Keys

The Key, Required, and Value columns of each table on this page are generated from version `1.1.0`'s schema, [`schemas/experiment-configuration-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/experiment-configuration-1.1.0.schema.json), and What it's for is written here. [Version `1.0.0`'s schema](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/experiment-configuration-1.0.0.schema.json) has the same keys, but those [two versions](#two-versions) names.

<!-- generated: experiment-configuration -->

| Key | Required | Value | What it's for |
|---|---|---|---|
| `kind` | Yes | `experiment` | Marks the file as an experiment configuration |
| `schema_version` | Yes | `1.1.0` | The version of the configuration's format: `1.1.0`, or `1.0.0`, without a baseline ranked by a definition or a snapshot, or ranking variants ([two versions](#two-versions)). Any other value fails with `config.invalid`, and the message names the supported versions. |
| `experiment_id` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`. The experiment's identity. | The experiment's name, as [the research context](#the-research-context) describes |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | It heads the report |
| `purpose` | Yes | Text, 1 to 2,000 characters, not all whitespace. The question the experiment addresses. Required: it's part of the research history. | The question the experiment addresses |
| `prior_research` | Yes | An [object](#experiment-configuration-prior-research) | The [prior-research declaration](#the-research-context) |
| `baseline` | Yes | An [object](#experiment-configuration-baseline) | The [baseline](#the-baseline) screen's settings |
| `variants` | No | An [object](#experiment-configuration-variants). When it's absent, the only variant is the default. | The [variants](#variants), by the setting each one changes. Without it, the only variant is the [default](#the-default-variant). |
| `budget` | Yes | An [object](#experiment-configuration-budget). With a ranking definition, at least two requests a case: its `rank_update` and its backtest. | The [budget](#the-budget) |

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

A screen's settings in screen configuration 1.1.0, and in an experiment configuration 1.1.0's baseline: 1.0.0's, with a ranking that may also be a ranking system's definition, in a file, or a ranking snapshot (docs/contracts.md, ranking forms).

| Key | Required | Value | What it's for |
|---|---|---|---|
| `universe` | Yes | Text, not all whitespace | A Portfolio123 universe, by name, in quotes, such as `'SP500'`. Every case uses it. |
| `rules` | Yes | A list of at least one item, each text, not all whitespace | The screening formulas, each in quotes. Their order is kept. |
| `ranking` | Yes | One of these objects: [`baseline.ranking` with `formula`](#experiment-configuration-baseline-ranking-formula), [`baseline.ranking` with `name`](#experiment-configuration-baseline-ranking-name), [`baseline.ranking` with `id`](#experiment-configuration-baseline-ranking-id), [`baseline.ranking` with `definition`](#experiment-configuration-baseline-ranking-definition), or [`baseline.ranking` with `snapshot`](#experiment-configuration-baseline-ranking-snapshot) | How the screen ranks stocks: one of the five forms below, as in a [screen configuration](screen-configuration.md#ranking). Every case uses it, but a ranking variant's case, which changes its definition. |
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

<!-- generated: experiment-configuration-baseline-ranking-definition -->

### `baseline.ranking` with `definition` { #experiment-configuration-baseline-ranking-definition }

A ranking system's definition, from 1.1.0: the XML in a file beside the configuration. Each case writes it into `ApiRankingSystem` with `rank_update`, and its backtest ranks by that system's name.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `definition` | Yes | Text, not all whitespace. The path of the file that holds the definition, relative to the configuration file. | The definition's file, in quotes, such as `'ranking/value-momentum.xml'`: the XML that Portfolio123's website shows in the ranking system's Text Editor, as [ranking definitions](ranking-definitions.md) describes |
| `ranking_method` | Yes | `percentile_nas_negative` or `percentile_nas_neutral`. Required, so the method is always explicit: `percentile_nas_negative`, sent as 2, or `percentile_nas_neutral`, sent as 4. | How the system ranks a stock whose value is missing: Percentile NAs Negative or Percentile NAs Neutral, as the website names them. Every case uses it. |

<!-- end generated: experiment-configuration-baseline-ranking-definition -->

<!-- generated: experiment-configuration-baseline-ranking-snapshot -->

### `baseline.ranking` with `snapshot` { #experiment-configuration-baseline-ranking-snapshot }

A ranking snapshot, from 1.1.0: a ranking system saved in the account, as an earlier `trialfolio run` of a snapshot configuration read it. The definition and the ranking method are the snapshot's.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `snapshot` | Yes | Text, not all whitespace. The path of the snapshot's directory, relative to the configuration file. | The directory of a [ranking snapshot](../how-to/take-a-ranking-snapshot.md), in quotes, such as `'runs/snapshots/value-momentum/'`. The snapshot gives the definition and the ranking method. |

<!-- end generated: experiment-configuration-baseline-ranking-snapshot -->

## Variants

**Each variant changes one setting** of the baseline, and is listed under that setting, with a `key` that names its case, and an optional `description`. Five settings can vary, those that live calls verified: the rules, the maximum holdings, the rebalance frequency, and the slippage, and, in `1.1.0`, with a baseline ranked by a definition or a snapshot, the ranking. A variant of any other setting, such as `universe`, fails with `config.invalid`, and the message names the settings a variant may change.

<!-- generated: experiment-configuration-variants -->

### `variants` { #experiment-configuration-variants }

The variants of an experiment configuration 1.1.0: 1.0.0's, and the ranking's, by the setting each one changes, in lists whose order is kept.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `rules` | No | A list of at least one [object](#experiment-configuration-variants-rules) | Variants that `replace` one of the baseline's rules, written exactly as it is there, `with` another, as for a stricter liquidity floor; or `add` a rule, such as `'MktCap > 300'`, which excludes microcaps |
| `ranking` | No | A list of at least one [object](#experiment-configuration-variants-ranking). Only with a baseline ranked by a definition or a snapshot. | [Ranking variants](#ranking-variants), each of which changes the weights of one parent's nodes, or removes a factor |
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

<!-- generated: experiment-configuration-variants-ranking -->

### Each of `variants.ranking` { #experiment-configuration-variants-ranking }

A variant of the baseline's ranking definition, from experiment configuration 1.1.0: the weights of the nodes of one parent, with `set`; or the removal of one factor, with `remove`, and the weights of the nodes left beside it, with `set` (ranking variants).

| Key | Required | Value | What it's for |
|---|---|---|---|
| `key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`. The case's `case_key`: unique among the experiment's cases, the default's included, and not `baseline`. | Its case's key, in the same form as `experiment_id`. It's unique among the experiment's cases, the default variant's included, and isn't `baseline`. |
| `description` | No | Text, 1 to 500 characters, not all whitespace. Up to 500 characters, shown in the report. | What the variant is, shown in the report |
| `set` | Yes | An object with at least one key, each with a value that's a number, more than 0, and less than 10,000,000,000,000,000. Node paths, each with the weight its node gets: every node of one parent, each once, summing to what the same nodes' weights sum to in the baseline. | Each node of one parent, the top level or one composite, by its [node path](ranking-definitions.md#node-paths) in quotes, with its weight in the case, such as `{'Value': 60, 'Momentum': 20, 'Quality': 20}`. In a removal, the nodes the parent keeps. |
| `remove` | No | Text. The path of the factor the variant removes, a `StockFormula` or a `StockFactor`. | The factor the variant removes, by its node path in quotes, such as `'Value/Sales Yield'`. Give it with `set`. |

<!-- end generated: experiment-configuration-variants-ranking -->

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

- **One change per variant.** A variant in `rules` holds `add`, or `replace` and `with`, never both. A ranking variant changes only the ranking.
- **A variant changes something.** A `value` differs from the baseline's: `0.250` is the baseline's `0.25`. `add` and `with` aren't the same text as any of the baseline's rules. A ranking variant changes at least one weight, or removes a factor. No two cases have the same settings, and no two ranking variants give the same definition.
- **A variant that breaks a rule** fails with `config.invalid`, and the message names it by its place in the file, such as `variants.max_holdings[0]`, never by its key.
- **Not offered:** a variant that removes one of the baseline's rules.

## Ranking variants

In `1.1.0`, when the baseline's ranking is a ranking system's definition, in a file or a snapshot, `variants.ranking` lists variants of that definition. Each case's definition is the baseline's with its variant's change, and nothing else: its other settings, its ranking method included, are the baseline's. Two kinds are offered, those that live calls verified:

- **A weight variant** gives `set`: the weight of every node of one parent, the top level or one composite, each once. The weights sum to what the same nodes' weights sum to in the baseline, and each is a number greater than 0. In the [ranking example](#a-ranking-example), `value-heavy` sets the three top-level composites' weights, which sum to 100, as the baseline's do, and `tilt-earnings-yield` the two factors of the composite named Value.
- **A removal variant** gives `remove`, the path of one factor, a `StockFormula` or a `StockFactor`, and `set`, the weights of the nodes left beside it, which sum to what the parent's nodes summed to with it. The parent keeps at least one node. A composite can't be removed. In the example, `no-sales-yield` removes Sales Yield from Value, and gives Earnings Yield, the factor left, 100.

**Node paths.** A `set`'s keys and a `remove` are node paths: each node's name from the top level down, separated by `/`, such as `'Value/Sales Yield'`, or a position, such as `#2`, for a node without a name, or one of two that share a name. Write each in quotes, since a name can hold a space followed by `#`. [Node paths](ranking-definitions.md#node-paths) gives every rule.

**What changes in the definition.** A weight variant rewrites only the weights that differ from the baseline's, between their attribute's quotes. A removal also takes the factor's element out, with its line. Nothing else in the definition's text changes, so the plan shows each case's whole definition, and each node's weight ([ranking variants](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-variants)).

**Messages** about a ranking variant name it by its place in the file, such as `variants.ranking[0]`, or a `set` entry as `variants.ranking[0].set[1]`, counted from 0, and the rule it breaks. They never quote a path, a name, a weight, or the definition, which are your strategy's definition.

## The default variant

- **Without a `rebalance_weeks` list,** Trial Folio adds a case for the other verified rebalance frequency: `rebalance-weeks-1` in the example, since the baseline rebalances every 4 weeks, or `rebalance-weeks-4` for a baseline that rebalances every week. It has no description.
- **It costs 5 credits,** like any case, or 6 when the baseline's ranking is a definition, since it sends a `rank_update` too. The plan shows it, and the budget must cover it.
- **`rebalance_weeks: []`** turns it off. A `rebalance_weeks` list of your own replaces it.

## The budget

<!-- generated: experiment-configuration-budget -->

### `budget` { #experiment-configuration-budget }

The experiment's request budget, across every `run` that resumes it.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `provider_requests` | Yes | An integer, from 1 to 1,801,439,850,948,198. The most provider requests the experiment may send: at least the number of cases, and few enough that the plan's credits can be hashed. | The most provider requests the experiment may send, across every run of it, repeats included |

<!-- end generated: experiment-configuration-budget -->

- **At least one per case,** so each can be sent once. A smaller budget fails with `config.invalid`, exit code 3, and the message gives the number of requests the cases need.
- **Two per case when the baseline's ranking is a definition or a snapshot,** since each case then sends a `rank_update` and its backtest, as in the [ranking example](#a-ranking-example).
- **More,** as in the first example, leaves room to [repeat](../how-to/repeat-a-case.md) a case: one more request for a case ranked another way, and two for a case with a definition.
- **Requests, not credits.** The plan shows its credits, at 5 a backtest, and, with a definition, 1 a `rank_update`, so 6 a case. [Credits and uncertain charges](../explanation/credits-and-uncertain-charges.md) explains why.

## Cases and their order

- **Each case is a screen backtest,** sent just as a screen configuration with its settings would be, so each costs 5 API credits. When the baseline's ranking is a definition, each case writes its definition into `ApiRankingSystem` first, with a `rank_update`, at 1 credit, so each costs 6 ([`ApiRankingSystem` and the ranking lock](../explanation/apirankingsystem-and-the-ranking-lock.md)).
- **The cases run in this order:** the baseline, then the variants of `rules`, `ranking`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, each list in its order. The default variant comes in `rebalance_weeks`'s place. The order of the keys in `variants` doesn't matter.
- **The smallest experiment** is a baseline with no `variants`: the baseline and the default variant, two cases and 10 credits.
- **At least two cases.** An experiment whose only case is its baseline, such as one with `rebalance_weeks: []` and no other variant, fails with `config.invalid`. A [screen configuration](screen-configuration.md) runs one screen.

## What's rejected

Each of these fails with `config.invalid`, exit code 3, and nothing is sent or created:

- a budget below the requests the cases need: the message gives that number;
- a variant of a setting that can't vary, such as `universe`, or ranking variants with a baseline whose ranking isn't a definition or a snapshot: the message names the settings a variant may change;
- a ranking variant that breaks a rule above, such as a path that names no node, or more than one, a weight of 0, weights whose sum differs from the baseline's, or a removal that leaves a composite empty: the message names the variant by its place in the file, and the rule;
- anything a [screen configuration](screen-configuration.md#whats-rejected) rejects, in the baseline, or a [definition](ranking-definitions.md#whats-rejected) that Trial Folio can't send.
