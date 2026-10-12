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

| Key | Required | Value | Sent to Portfolio123 |
|---|---|---|---|
| `kind` | Yes | `experiment` | No |
| `schema_version` | Yes | `1.0.0`. Any other value fails with `config.invalid`, and the message names the supported versions. | No |
| `experiment_id` | Yes | The experiment's name, as [the research context](#the-research-context) describes | No |
| `title` | Yes | 1 to 200 characters. It heads the report. | No |
| `purpose` | Yes | The question the experiment addresses: 1 to 2,000 characters, not all whitespace | No |
| `prior_research` | Yes | The [prior-research declaration](#the-research-context) | No |
| `baseline` | Yes | The [baseline](#the-baseline) screen's settings | Yes, in each case's request |
| `variants` | No | The [variants](#variants), by the setting each one changes. Without it, the only variant is the [default](#the-default-variant). | Each variant's change is, in its case's request. Its `key` and `description` aren't. |
| `budget` | Yes | The [budget](#the-budget) | No |

The values follow the rules in [how values are written](screen-configuration.md#how-values-are-written).

## The research context

None of these is sent.

- **`experiment_id`** names the experiment, as a review's labels name results: lowercase letters, digits, `-`, and `_`. It starts with a letter or a digit, is at most 64 characters long, and isn't a name Windows reserves, such as `con` or `nul`. Another `experiment_id` is another experiment.
- **`purpose`,** the question the experiment addresses, is required.
- **`prior_research`** declares the earlier work on the same idea whose results you saw, in Trial Folio or anywhere else. Trial Folio records the declaration as you wrote it, and can't verify it.

| `prior_research` key | Required | Value |
|---|---|---|
| `status` | Yes | `complete`, when the description accounts for all of it, or says there was none; `partial`, when there was more than it describes; or `unknown` |
| `description` | With `complete` or `partial` | 1 to 5,000 characters, not all whitespace. It may also be given with `unknown`. |

## The baseline

- **`baseline` holds a screen's settings:** the keys of a [screen configuration](screen-configuration.md#keys) from `universe` to `data_vendor`, with the same rules. So the text Portfolio123 receives goes in quotes.
- **It has no `kind`, `schema_version`, `title`, or `purpose`:** those are the experiment's.
- **Every case uses the baseline's universe, ranking, benchmark, and dates.** Another universe is another experiment.
- **Its case's key is `baseline`.**

## Variants

**Each variant changes one setting** of the baseline, and is listed under that setting, with a `key` that names its case, and an optional `description`. Four settings can vary, those that live calls verified:

| Key in `variants` | Each variant's change |
|---|---|
| `rules` | `replace` one of the baseline's rules, written exactly as it is there, `with` another, as for a stricter liquidity floor; or `add` a rule, such as `'MktCap > 300'`, which excludes microcaps |
| `max_holdings` | A `value` other than the baseline's: an integer, 1 or more |
| `rebalance_weeks` | A `value` other than the baseline's: `1` or `4` |
| `slippage_percent` | A `value` other than the baseline's: a decimal, 0 or more, in percent |

A variant of any other setting, such as `universe`, fails with `config.invalid`, and the message names the settings a variant may change.

**Each variant's keys:**

| Key | Required | Value |
|---|---|---|
| `key` | Yes | Its case's key: the same form as `experiment_id`. It's unique among the experiment's cases, the default variant's included, and isn't `baseline`. |
| `description` | No | 1 to 500 characters, shown in the report |
| `value` | In `max_holdings`, `rebalance_weeks`, and `slippage_percent` | The setting's value in this case |
| `add` | In `rules`, unless `replace` is given | A screening formula, in quotes, added after the baseline's rules |
| `replace` | In `rules`, unless `add` is given | One of the baseline's rules, in quotes, written exactly as it is there |
| `with` | With `replace` | The formula, in quotes, that takes the replaced rule's place, so the rules keep their order |

**Rules that span keys:**

- **One change per variant.** A variant in `rules` holds `add`, or `replace` and `with`, never both.
- **A variant changes something.** A `value` differs from the baseline's: `0.250` is the baseline's `0.25`. `add` and `with` aren't the same text as any of the baseline's rules. No two cases have the same settings.
- **Lists.** Each list holds at least one variant, except `rebalance_weeks`, where an empty list turns the [default variant](#the-default-variant) off.
- **A variant that breaks a rule** fails with `config.invalid`, and the message names it by its place in the file, such as `variants.max_holdings[0]`, never by its key.
- **Not offered:** a variant that removes one of the baseline's rules.

## The default variant

- **Without a `rebalance_weeks` list,** Trial Folio adds a case for the other verified rebalance frequency: `rebalance-weeks-1` in the example, since the baseline rebalances every 4 weeks, or `rebalance-weeks-4` for a baseline that rebalances every week. It has no description.
- **It costs 5 credits,** like any case. The plan shows it, and the budget must cover it.
- **`rebalance_weeks: []`** turns it off. A `rebalance_weeks` list of your own replaces it.

## The budget

| `budget` key | Required | Value |
|---|---|---|
| `provider_requests` | Yes | The most provider requests the experiment may send, across every run of it, repeats included. At least the number of cases, and at most 1801439850948198. |

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
