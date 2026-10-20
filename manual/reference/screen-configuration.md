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

## Two versions

A screen configuration is version `1.0.0` or `1.1.0`, as its `schema_version` says, and `trialfolio run` reads both.

- **`1.0.0`,** the version of the example above, and of the `screen.yaml` that `trialfolio init` writes, has every key on this page. Its `ranking` takes the first three [forms](#ranking): a formula, or a ranking system in your account by name or by ID.
- **`1.1.0`,** from release 0.4.0, adds two forms of `ranking`: a ranking system's definition, in a file, and a ranking snapshot. It adds nothing else, so a `1.0.0` file reads the same with `schema_version: 1.1.0`.

A `1.0.0` file that gives `definition` or `snapshot` fails with `config.invalid`, and the message says they need `1.1.0`.

## Keys

The Key, Required, and Value columns of each table on this page are generated from version `1.1.0`'s schema, [`schemas/screen-configuration-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/screen-configuration-1.1.0.schema.json), and What it's for is written here. [Version `1.0.0`'s schema](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/screen-configuration-1.0.0.schema.json) has the same keys, with the first three forms of `ranking`.

<!-- generated: screen-configuration -->

| Key | Required | Value | What it's for |
|---|---|---|---|
| `kind` | Yes | `screen` | Marks the file as a screen configuration |
| `schema_version` | Yes | `1.1.0` | The version of the configuration's format: `1.1.0`, or `1.0.0`, which has every key but the ranking's `definition` and `snapshot` forms ([two versions](#two-versions)) |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | Your title, which heads the report |
| `purpose` | No | Text, 1 to 2,000 characters, not all whitespace | Why you're running the backtest. Without one, the report says no purpose was declared. |
| `universe` | Yes | Text, not all whitespace | A Portfolio123 universe, by name, [in quotes](#quoting-the-text-portfolio123-receives), such as `'SP500'` |
| `rules` | Yes | A list of at least one item, each text, not all whitespace | The screening formulas, each in quotes. Their order is kept. |
| `ranking` | Yes | One of these objects: [`ranking` with `formula`](#screen-configuration-ranking-formula), [`ranking` with `name`](#screen-configuration-ranking-name), [`ranking` with `id`](#screen-configuration-ranking-id), [`ranking` with `definition`](#screen-configuration-ranking-definition), or [`ranking` with `snapshot`](#screen-configuration-ranking-snapshot) | How the screen ranks stocks: one of the [five forms of ranking](#ranking) |
| `max_holdings` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The most stocks held |
| `benchmark` | Yes | Text, not all whitespace | A Portfolio123 benchmark symbol, in quotes, such as `'SPY'` |
| `start_date` | Yes | A date, `YYYY-MM-DD` | The backtest's first day |
| `end_date` | Yes | A date, `YYYY-MM-DD` | The backtest's last day, later than `start_date`. There's no default of today. |
| `rebalance_weeks` | Yes | `1` or `4` | The weeks between rebalances |
| `transaction_price` | Yes | `open` | The price trades use |
| `slippage_percent` | Yes | A number, 0 or more, and less than 10,000,000,000,000,000. Plain notation, with at most 4 digits after the decimal point and 15 significant digits. Never a string. | The slippage, a decimal in percent: `0.25` means 0.25%. There's no default of zero. |
| `pit_method` | Yes | `complete` | Portfolio123's point-in-time method |
| `precision` | Yes | `4` | The decimal places in results |
| `data_vendor` | No | `FactSet` | The data vendor: `FactSet`, the [only value accepted](#data_vendor) |

<!-- end generated: screen-configuration -->

**Sent to Portfolio123:** `universe`, `rules`, `ranking`, `max_holdings`, `benchmark`, `start_date`, `end_date`, `rebalance_weeks`, `transaction_price`, `slippage_percent`, `pit_method`, and `precision`. Trial Folio never sends `kind`, `schema_version`, `title`, `purpose`, or `data_vendor`.

Trial Folio also sends three fixed values with every request, which no key changes: a stock screen, long positions, and the currency USD.

## Quoting the text Portfolio123 receives

- **Text that Portfolio123 receives goes in single quotes:** the rules, the ranking's formula or name, the universe, and the benchmark.
  - Without quotes, it's rejected, because outside quotes YAML reads a space and `#` as the start of a comment, with no error. It would cut `FRank("EarnYield", #Industry) > 50` short, and read `name: Core Combo #2` as `Core Combo`, a different ranking system.
  - Single quotes also keep the double quotes inside a formula as they are. Inside single quotes, a single quote is written twice (`''`).
  - Double quotes and block scalars (`|` or `>`) work too.
- **Other values need no quotes:** numbers, dates, `true` and `false`, fixed words such as `screen`, `open`, and `complete`, the title and purpose, which are never sent, and the paths of a definition's file and a snapshot's directory. The examples write those paths in quotes anyway, which a path that holds a space followed by `#` needs.
- **A title or purpose that holds a space followed by `#`** still needs quotes, or YAML cuts it short.

## Comments

- A comment runs from `#` to the end of the line, outside quotes.
- Comments aren't part of the plan, so adding or changing one doesn't change the plan hash.
- The run keeps them, in its byte-for-byte copy of the file, `configuration.yaml`.

## Ranking

`ranking` holds exactly one of five forms: one formula; an existing ranking system in your account, by name or by ID; and, from `schema_version` `1.1.0`, a ranking system's definition, in a file, or a ranking snapshot. Each form has its own keys.

<!-- generated: screen-configuration-ranking-formula -->

### `ranking` with `formula` { #screen-configuration-ranking-formula }

A ranking by a single formula, the recommended form.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | The formula, in quotes, such as `'EarnYield'` |
| `lower_is_better` | Yes | `true` or `false` | Whether the formula's lower values rank higher, such as `false` |

<!-- end generated: screen-configuration-ranking-formula -->

<!-- generated: screen-configuration-ranking-name -->

### `ranking` with `name` { #screen-configuration-ranking-name }

An existing ranking system in the account, by name. It's recorded as not snapshotted.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `name` | Yes | Text, not all whitespace | The name of an existing ranking system in your account, in quotes, such as `'My ranking system'` |

<!-- end generated: screen-configuration-ranking-name -->

<!-- generated: screen-configuration-ranking-id -->

### `ranking` with `id` { #screen-configuration-ranking-id }

An existing ranking system in the account, by ID. It's recorded as not snapshotted.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `id` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The ID of an existing ranking system in your account, such as `12345` |

<!-- end generated: screen-configuration-ranking-id -->

<!-- generated: screen-configuration-ranking-definition -->

### `ranking` with `definition` { #screen-configuration-ranking-definition }

A ranking system's definition, from 1.1.0: the XML in a file beside the configuration. Each case writes it into `ApiRankingSystem` with `rank_update`, and its backtest ranks by that system's name.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `definition` | Yes | Text, not all whitespace. The path of the file that holds the definition, relative to the configuration file. | The definition's file, in quotes, such as `'ranking/value-momentum.xml'`: the XML that Portfolio123's website shows in the ranking system's Text Editor, as [ranking definitions](ranking-definitions.md) describes |
| `ranking_method` | Yes | `percentile_nas_negative` or `percentile_nas_neutral`. Required, so the method is always explicit: `percentile_nas_negative`, sent as 2, or `percentile_nas_neutral`, sent as 4. | How the system ranks a stock whose value is missing: Percentile NAs Negative or Percentile NAs Neutral, as the website names them |

<!-- end generated: screen-configuration-ranking-definition -->

<!-- generated: screen-configuration-ranking-snapshot -->

### `ranking` with `snapshot` { #screen-configuration-ranking-snapshot }

A ranking snapshot, from 1.1.0: a ranking system saved in the account, as an earlier `trialfolio run` of a snapshot configuration read it. The definition and the ranking method are the snapshot's.

| Key | Required | Value | What it's for |
|---|---|---|---|
| `snapshot` | Yes | Text, not all whitespace. The path of the snapshot's directory, relative to the configuration file. | The directory of a [ranking snapshot](../how-to/take-a-ranking-snapshot.md), in quotes, such as `'runs/snapshots/value-momentum/'`. The snapshot gives the definition and the ranking method. |

<!-- end generated: screen-configuration-ranking-snapshot -->

The forms by name and by ID look like this:

```yaml
ranking:
  name: 'My ranking system'
```

```yaml
ranking:
  id: 12345
```

The forms by a definition and by a snapshot, in a `schema_version: 1.1.0` file, look like this:

```yaml
ranking:
  definition: 'ranking/value-momentum.xml'
  ranking_method: percentile_nas_negative
```

```yaml
ranking:
  snapshot: 'runs/snapshots/value-momentum/'
```

- **Not snapshotted.** A ranking system named by name or ID, like the universe, can change in your account after the run, and Trial Folio doesn't save its definition. So the run records it as not snapshotted (`not_snapshotted` in [`settings.csv`](outputs.md#normalizedsettingscsv)), and its reproducibility as incomplete. A formula ranking is recorded completely. [Reproducibility](../explanation/reproducibility.md) explains why.
- **A definition, or a snapshot, is recorded completely.** The run keeps a copy of the definition, `definition.xml`, and `settings.csv` gives each node's weight in a row of its own. The run writes the definition into `ApiRankingSystem`, a ranking system in your account, then backtests ranked by it, so it sends two requests, at 6 credits, where a ranking in another form sends one, at 5. [Vary a ranking system's weights](../how-to/vary-a-ranking-systems-weights.md) gives the steps, and [`ApiRankingSystem` and the ranking lock](../explanation/apirankingsystem-and-the-ranking-lock.md) explains what that means for your account.
- **One form only.** `lower_is_better` goes only with `formula`, and `ranking_method` only with `definition`, which requires it. A snapshot records its system's ranking method, so `ranking_method` with `snapshot` fails.
- **Not accepted.** A ranking method override, and a ranking definition written as nodes or XML in the configuration itself, fail with `config.invalid`. The message names the supported forms.

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
- A `schema_version` other than `1.0.0` or `1.1.0` fails with `config.invalid`, and the message names the supported versions. A `1.0.0` file that gives `definition` or `snapshot` fails the same way, and the message says they need `1.1.0` ([ranking forms](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-forms)).
- A definition's file that isn't a ranking system's definition Trial Folio can send, such as one with a weight of 0, fails with `config.invalid`, before anything is sent ([ranking definitions](ranking-definitions.md#whats-rejected)). A file or a snapshot's directory that doesn't exist fails with `input.not_found`, and a snapshot that didn't finish with `input.not_a_run`, both with exit code 3.
- A message names each key with a problem, and never its value.
