# Invalid screen configurations

Each file breaks exactly one rule of the [screen configuration](../../../../docs/contracts.md#screen-configuration), and is otherwise the [documented example](../../../../docs/contracts.md#example), which `../formula.yaml` copies. `tests/contract/test_screen_configuration.py` reads each one, expects `config.invalid`, and expects the message to name the key on the file's `# Key:` line, where `-` means the file as a whole.

- **Origin:** written for Trial Folio's tests. Synthetic: no value comes from Portfolio123.
- **Schema version:** screen configuration 1.0.0.
- **Redistribution:** synthetic, so it may be committed and shared.
- **Criteria:** R01-AC02, R01-AC09, and R01-AC11 ([0.1.0's test pairing](../../../../docs/releases/0.1.0-api-execution.md#test-pairing)).

A new rule needs a new file, and a row here. The test checks that this table and the directory list the same files.

## Structure

| File | Rule it breaks | Key |
|---|---|---|
| `misspelled-key.yaml` | Unknown keys are rejected | `max_holding` |
| `duplicate-key.yaml` | Duplicate keys are rejected | `max_holdings` |
| `credential-key.yaml` | A credential-like key is rejected | `api_key` |
| `wrong-kind.yaml` | `kind` is `screen` | `kind` |
| `unsupported-schema-version.yaml` | `schema_version` is a supported version | `schema_version` |
| `missing-kind.yaml` | `kind` is required | `kind` |
| `missing-schema-version.yaml` | `schema_version` is required | `schema_version` |
| `missing-title.yaml` | `title` is required | `title` |
| `missing-universe.yaml` | `universe` is required | `universe` |
| `missing-rules.yaml` | `rules` is required | `rules` |
| `missing-ranking.yaml` | `ranking` is required | `ranking` |
| `missing-max-holdings.yaml` | `max_holdings` is required | `max_holdings` |
| `missing-benchmark.yaml` | `benchmark` is required | `benchmark` |
| `missing-start-date.yaml` | `start_date` is required | `start_date` |
| `missing-end-date.yaml` | `end_date` is required | `end_date` |
| `missing-rebalance-weeks.yaml` | `rebalance_weeks` is required | `rebalance_weeks` |
| `missing-transaction-price.yaml` | `transaction_price` is required | `transaction_price` |
| `missing-slippage-percent.yaml` | `slippage_percent` is required | `slippage_percent` |
| `missing-pit-method.yaml` | `pit_method` is required | `pit_method` |
| `missing-precision.yaml` | `precision` is required | `precision` |
| `null-value.yaml` | A key has a value; null is rejected | `purpose` |
| `anchor-alias.yaml` | Anchors and aliases are rejected | `benchmark` |
| `explicit-tag.yaml` | Explicit YAML tags are rejected | `max_holdings` |
| `non-text-key.yaml` | Keys are text | - |
| `two-documents.yaml` | A file holds one YAML document | - |
| `not-a-mapping.yaml` | A file is a mapping of keys to values | - |

## Text

| File | Rule it breaks | Key |
|---|---|---|
| `empty-title.yaml` | `title` has 1–200 characters | `title` |
| `title-too-long.yaml` | `title` has 1–200 characters | `title` |
| `purpose-too-long.yaml` | `purpose` has up to 2,000 characters | `purpose` |
| `empty-universe.yaml` | `universe` is non-empty | `universe` |
| `blank-universe.yaml` | Non-empty text has a character that isn't whitespace | `universe` |
| `empty-benchmark.yaml` | `benchmark` is non-empty | `benchmark` |
| `empty-rules.yaml` | `rules` has at least one formula | `rules` |
| `empty-rule.yaml` | Each rule is a non-empty string | `rules[0]` |
| `empty-formula.yaml` | A ranking formula is a non-empty string | `ranking.formula` |
| `empty-ranking-name.yaml` | A ranking name is a non-empty string | `ranking.name` |

## Ranking

| File | Rule it breaks | Key |
|---|---|---|
| `ranking-empty.yaml` | `ranking` holds exactly one form | `ranking` |
| `two-ranking-forms.yaml` | `ranking` holds exactly one form | `ranking` |
| `ranking-method-override.yaml` | A ranking method override isn't supported | `ranking` |
| `ranking-nodes.yaml` | A ranking given as nodes or XML isn't supported | `ranking` |
| `formula-without-lower-is-better.yaml` | `lower_is_better` is required with `formula` | `ranking.lower_is_better` |
| `lower-is-better-without-formula.yaml` | `lower_is_better` is allowed only with `formula` | `ranking` |
| `lower-is-better-yes.yaml` | Booleans are `true` or `false` only | `ranking.lower_is_better` |
| `lower-is-better-number.yaml` | A number is never a boolean | `ranking.lower_is_better` |
| `ranking-id-zero.yaml` | A ranking ID is a positive integer | `ranking.id` |
| `ranking-id-too-large.yaml` | An integer is at most 2^53 − 1 | `ranking.id` |

## Unverified values

| File | Rule it breaks | Key |
|---|---|---|
| `rebalance-weeks-2.yaml` | `rebalance_weeks` is 1 or 4 | `rebalance_weeks` |
| `transaction-price-close.yaml` | `transaction_price` is `open` | `transaction_price` |
| `pit-method-prelim.yaml` | `pit_method` is `complete` | `pit_method` |
| `precision-2.yaml` | `precision` is 4 | `precision` |
| `max-holdings-0.yaml` | `max_holdings` is 1 or more | `max_holdings` |
| `vendor-compustat.yaml` | `data_vendor` is `FactSet` only (D-16) | `data_vendor` |

## Dates

| File | Rule it breaks | Key |
|---|---|---|
| `end-before-start.yaml` | `end_date` is later than `start_date` | `end_date` |
| `end-equals-start.yaml` | `end_date` is later than `start_date` | `end_date` |
| `date-with-time.yaml` | Dates have no time part | `start_date` |
| `date-not-iso.yaml` | A date as a string is exactly `YYYY-MM-DD` | `start_date` |

## Decimals

| File | Rule it breaks | Key |
|---|---|---|
| `slippage-five-decimals.yaml` | At most 4 digits after the decimal point | `slippage_percent` |
| `slippage-sixteen-digits.yaml` | At most 15 significant digits | `slippage_percent` |
| `slippage-too-large.yaml` | Less than 10^16; written with `.0` to reach the decimal limit rather than the YAML integer-length guard | `slippage_percent` |
| `slippage-exponent.yaml` | Plain notation: no exponent | `slippage_percent` |
| `slippage-negative.yaml` | Plain notation: no sign | `slippage_percent` |
| `slippage-leading-point.yaml` | Plain notation: digits before the decimal point | `slippage_percent` |
| `slippage-leading-zero.yaml` | Plain notation: no leading zero before another digit | `slippage_percent` |
| `slippage-string.yaml` | A number written as a string is rejected | `slippage_percent` |

## Coerced values

| File | Rule it breaks | Key |
|---|---|---|
| `max-holdings-string.yaml` | A string is never a number | `max_holdings` |
| `max-holdings-float.yaml` | A decimal is never an integer | `max_holdings` |
| `max-holdings-sexagesimal.yaml` | Integers are plain decimal digits; a YAML 1.1 loader reads `1:30` as 90 | `max_holdings` |
| `rebalance-weeks-string.yaml` | A string is never a number | `rebalance_weeks` |
| `precision-float.yaml` | A decimal is never an integer | `precision` |
| `ranking-id-string.yaml` | A string is never a number | `ranking.id` |
| `lower-is-better-string.yaml` | A string is never a boolean | `ranking.lower_is_better` |
| `date-as-integer.yaml` | A number is never a date | `start_date` |
| `universe-number.yaml` | A number is never text | `universe` |

## Integers

| File | Rule it breaks | Key |
|---|---|---|
| `integer-leading-zero.yaml` | Integers have no leading zero | `max_holdings` |
| `integer-underscore.yaml` | Integers have no underscore | `max_holdings` |
| `integer-sign.yaml` | Integers have no sign | `max_holdings` |
| `integer-hex.yaml` | Integers have no base prefix | `max_holdings` |
| `boolean-holdings.yaml` | A boolean is never a number | `max_holdings` |
