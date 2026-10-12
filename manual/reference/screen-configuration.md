# Screen configuration

A screen configuration is a YAML file that describes one long-only stock screen backtest, for `trialfolio run`. This page lists its keys, and the rules its values follow.

[The screen configuration](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#screen-configuration), in the specification, gives every key's rules.

## Example

This example has the settings that Portfolio123 accepted in a live call, with a comment on each key. The `screen.yaml` that `trialfolio init` writes has the same settings, without `purpose`.

```yaml
kind: screen
schema_version: 1.0.0
title: Earnings yield with a liquidity floor           # yours; never sent
purpose: Reference backtest for the 0.1.0 response layout.   # optional; never sent
universe: 'SP500'
rules:
  - 'AvgDailyTot(30) > 1000000'                        # at least one rule
ranking:
  formula: 'EarnYield'
  lower_is_better: false
max_holdings: 25
benchmark: 'SPY'
start_date: 2016-01-01
end_date: 2025-12-31
rebalance_weeks: 4                                     # 1 or 4
transaction_price: open                                # open only
slippage_percent: 0.25                                 # 0.25 means 0.25%
pit_method: complete                                   # complete only
precision: 4                                           # 4 only
```

## Keys

Every key but `purpose` and `data_vendor` is required. There's no default end date, and no default slippage of zero.

| Key | Required | Value | Sent to Portfolio123 |
|---|---|---|---|
| `kind` | Yes | `screen` | No |
| `schema_version` | Yes | `1.0.0` | No |
| `title` | Yes | Your title, which heads the report: 1 to 200 characters | No |
| `purpose` | No | Why you're running the backtest: 1 to 2,000 characters, not all whitespace. Without one, the report says no purpose was declared. | No |
| `universe` | Yes | A Portfolio123 universe, by name, [in quotes](#quoting-the-text-portfolio123-receives), such as `'SP500'` | Yes |
| `rules` | Yes | A list of at least one screening formula, each in quotes. Their order is kept. | Yes |
| `ranking` | Yes | One of the [three forms of ranking](#ranking) | Yes |
| `max_holdings` | Yes | The most stocks held: an integer, 1 or more | Yes |
| `benchmark` | Yes | A Portfolio123 benchmark symbol, in quotes, such as `'SPY'` | Yes |
| `start_date` | Yes | The backtest's first day, `YYYY-MM-DD` | Yes |
| `end_date` | Yes | `YYYY-MM-DD`, later than `start_date`. There's no default of today. | Yes |
| `rebalance_weeks` | Yes | The weeks between rebalances: `1` or `4` | Yes |
| `transaction_price` | Yes | The price trades use: `open` | Yes |
| `slippage_percent` | Yes | A decimal, 0 or more, in percent: `0.25` means 0.25%. There's no default of zero. | Yes |
| `pit_method` | Yes | Portfolio123's point-in-time method: `complete` | Yes |
| `precision` | Yes | The decimal places in results: `4` | Yes |
| `data_vendor` | No | `FactSet`, the [only value accepted](#data_vendor) | No |

Trial Folio also sends three fixed values with every request, which no key changes: a stock screen, long positions, and the currency USD.

## Quoting the text Portfolio123 receives

- **Text that Portfolio123 receives goes in single quotes:** the rules, the ranking's formula or name, the universe, and the benchmark.
  - Without quotes, it's rejected, because outside quotes YAML reads a space and `#` as the start of a comment, with no error. It would cut `FRank("EarnYield", #Industry) > 50` short, and read `name: Core Combo #2` as `Core Combo`, a different ranking system.
  - Single quotes also keep the double quotes inside a formula as they are. Inside single quotes, a single quote is written twice (`''`).
  - Double quotes and block scalars (`|` or `>`) work too.
- **Other values need no quotes:** numbers, dates, `true` and `false`, fixed words such as `screen`, `open`, and `complete`, and the title and purpose, which are never sent.
- **A title or purpose that holds a space followed by `#`** still needs quotes, or YAML cuts it short.

## Comments

- A comment runs from `#` to the end of the line, outside quotes.
- Comments aren't part of the plan, so adding or changing one doesn't change the plan hash.
- The run keeps them, in its byte-for-byte copy of the file, `configuration.yaml`.

## Ranking

`ranking` holds exactly one of three forms:

| Form | Keys | Example |
|---|---|---|
| One formula | `formula`, in quotes, and `lower_is_better`, `true` or `false`, which is required with it | `formula: 'EarnYield'` and `lower_is_better: false` |
| An existing ranking system in your account, by name | `name`, in quotes | `name: 'My ranking system'` |
| An existing ranking system in your account, by ID | `id`, a positive integer | `id: 12345` |

```yaml
ranking:
  name: 'My ranking system'
```

```yaml
ranking:
  id: 12345
```

- **Not snapshotted.** A ranking system, like the universe, can change in your account after the run, and Trial Folio doesn't save its definition. So the run records it as not snapshotted (`not_snapshotted` in [`settings.csv`](outputs.md#normalizedsettingscsv)), and its reproducibility as incomplete. A formula ranking is recorded completely. [Reproducibility](../explanation/reproducibility.md) explains why.
- **Not accepted.** A ranking method override, and a ranking definition given as nodes or XML, fail with `config.invalid`. The message names the supported forms.

## `data_vendor`

`data_vendor` may be left out, or given as `FactSet`. Either way, it's recorded as FactSet, an inferred default, and isn't sent. Any other value, including `Compustat`, fails with `config.invalid`.

## Only verified values are accepted

Trial Folio accepts only the values that a recorded live call has verified. Portfolio123 documents other values, which Trial Folio rejects until a live call verifies them:

- `max_holdings` 0, meaning no limit
- `rebalance_weeks` 2, 3, 6, 8, 13, 26, and 52
- `transaction_price` `high_low_average` and `close`
- `pit_method` `prelim`
- `precision` 2 and 3

Free-form values, such as universe names, benchmark symbols, and formulas, are verified by their form.

## How values are written

These rules hold for every configuration: a screen's, a [review's](review-configuration.md), and an [experiment's](experiment-configuration.md).

- **Dates** are `YYYY-MM-DD`, with no time part.
- **Booleans** are `true` or `false` only.
- **Integers** are plain decimal digits, with no leading zero, underscore, sign, or base prefix. So `010`, `1_000`, `+5`, and `0x10` are rejected.
- **Decimals** are written in plain notation: digits, then optionally a decimal point and more digits. There's no sign or exponent, so `-0.25`, `.25`, and `2.5e-1` are rejected. Trailing zeros don't count: `0.250` and `0.25` are the same setting. A decimal has at most 4 digits after the decimal point. [The screen configuration](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#screen-configuration) gives its other limits.
- **A number written as a string,** such as `'25'`, is rejected.
- **An optional key** is left out to omit it. Don't write it empty: a null value is rejected.
- **Unknown keys and duplicate keys** are rejected, so a misspelling fails instead of being ignored.
- **No credentials.** A key whose name looks like a credential, such as one containing `password`, `secret`, `token`, or `api_key`, is rejected, at any depth.
- **Paths** inside a configuration are read from the configuration file's folder.

## What's rejected

- A misspelled key, a missing required key, or an unsupported value fails with `config.invalid`, exit code 3. The message lists every problem, and nothing is sent or created. For example, `rebalance_weeks: 2` gives "`rebalance_weeks` input should be 1 or 4."
- A rule without quotes, such as `- AvgDailyTot(30) > 1000000`, fails the same way, with "`rules[0]` is text Portfolio123 receives, written without quotes." So does `universe: SP500`, naming `universe`.
- A `schema_version` other than `1.0.0` fails with `config.invalid`, and the message names the supported versions.
- A message names each key with a problem, and never its value.
