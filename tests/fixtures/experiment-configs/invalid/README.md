# Invalid experiment configurations

Each file breaks exactly one rule of the [experiment configuration](../../../../docs/contracts.md#experiment-configuration), or of the rules for [every configuration file](../../../../docs/contracts.md#configuration-files), and is otherwise the [documented example](../../../../docs/contracts.md#experiment-example), which `../example.yaml` copies. Release 0.3.0's [test pairing](../../../../docs/releases/0.3.0-experiments.md#invalid-experiment-configuration-cases) lists them by group. `tests/contract/test_experiment_configuration.py` reads each one, expects `config.invalid`, and expects the message to name the key on the file's `# Key:` line, where `-` means the file as a whole. The message never holds the offending value, given on the file's `# Value:` line, or any variant's key, which is the user's text: it names a variant by its place, such as `variants.max_holdings[0]`. `-` on the `# Value:` line means there's no value to look for: the key is missing, the value is empty or blank, the problem is the file as a whole, or the value is a word the rule itself names, as `key-baseline.yaml`'s `baseline` is. A value longer than 80 characters is `-` there too: the test also checks that no value of 20 characters or more in the file appears in the message.

- **Origin:** written for Trial Folio's tests by R03-T06, each from the documented example. Synthetic: the keys, descriptions, and other text are invented, and no value comes from Portfolio123 or from the owner's account.
- **Schema version:** experiment configuration 1.0.0.
- **Redistribution:** synthetic, so they may be committed and shared.
- **Criteria:** the experiment configuration's rules, in release 0.3.0's [other checks in the default suite](../../../../docs/releases/0.3.0-experiments.md#test-pairing). The test pairing also runs `misspelled-key.yaml`, `variant-universe.yaml`, and `budget-below-cases.yaml` through the CLI, in `tests/interface/test_run_validation.py`, once `run` reads an experiment configuration.

A new rule needs a new file, and a row here. The test checks that these tables and the directory list the same files.

## Structure

| File | Rule it breaks | Key |
|---|---|---|
| `misspelled-key.yaml` | Unknown keys are rejected | `purpos` |
| `misspelled-prior-research-key.yaml` | Unknown keys in `prior_research` are rejected | `prior_research.descripton` |
| `misspelled-baseline-key.yaml` | Unknown keys in `baseline` are rejected | `baseline.max_holding` |
| `misspelled-variant-key.yaml` | Unknown keys in a variant are rejected | `variants.max_holdings[0].vaule` |
| `misspelled-budget-key.yaml` | Unknown keys in `budget` are rejected: the budget is in provider requests, not credits | `budget.credits` |
| `duplicate-key.yaml` | Duplicate keys are rejected | `baseline.benchmark` |
| `credential-key.yaml` | A credential-like key is rejected, at any depth | `baseline.api_key` |
| `wrong-kind.yaml` | `kind` is `experiment` | `kind` |
| `unsupported-schema-version.yaml` | `schema_version` is a supported version | `schema_version` |
| `missing-kind.yaml` | `kind` is required | `kind` |
| `missing-schema-version.yaml` | `schema_version` is required | `schema_version` |
| `missing-experiment-id.yaml` | `experiment_id` is required | `experiment_id` |
| `missing-title.yaml` | `title` is required | `title` |
| `missing-purpose.yaml` | `purpose` is required | `purpose` |
| `missing-prior-research.yaml` | `prior_research` is required | `prior_research` |
| `missing-status.yaml` | `prior_research.status` is required | `prior_research.status` |
| `missing-baseline.yaml` | `baseline` is required | `baseline` |
| `missing-budget.yaml` | `budget` is required | `budget` |
| `missing-provider-requests.yaml` | `budget.provider_requests` is required | `budget.provider_requests` |
| `missing-variant-key.yaml` | Each variant's `key` is required | `variants.max_holdings[0].key` |
| `null-value.yaml` | A key has a value; null is rejected | `variants.rules[0].description` |
| `anchor-alias.yaml` | Anchors and aliases are rejected | `experiment_id` |
| `explicit-tag.yaml` | Explicit YAML tags are rejected | `baseline.max_holdings` |
| `non-text-key.yaml` | Keys are text | `budget` |
| `two-documents.yaml` | A file holds one YAML document | - |
| `not-a-mapping.yaml` | A file is a mapping of keys to values | - |

## The baseline

| File | Rule it breaks | Key |
|---|---|---|
| `baseline-with-kind.yaml` | The baseline has no `kind`: it's the experiment's | `baseline.kind` |
| `baseline-with-title.yaml` | The baseline has no `title`: it's the experiment's | `baseline.title` |
| `baseline-missing-universe.yaml` | The baseline's `universe` is required, as a screen configuration's is | `baseline.universe` |
| `baseline-unquoted-rule.yaml` | The baseline's rules are quoted, as a screen configuration's are (R01-T18) | `baseline.rules[0]` |
| `baseline-two-ranking-forms.yaml` | The baseline's `ranking` holds exactly one form, as a screen configuration's does | `baseline.ranking` |
| `baseline-rebalance-weeks-2.yaml` | The baseline's `rebalance_weeks` is 1 or 4, the verified values | `baseline.rebalance_weeks` |
| `baseline-vendor-compustat.yaml` | The baseline's `data_vendor`, when given, is FactSet (D-16) | `baseline.data_vendor` |
| `baseline-end-before-start.yaml` | The baseline's `end_date` is later than its `start_date` | `baseline.end_date` |
| `baseline-slippage-five-decimals.yaml` | The baseline's slippage has at most 4 digits after the decimal point | `baseline.slippage_percent` |
| `baseline-max-holdings-string.yaml` | The baseline's `max_holdings` is an integer, never text | `baseline.max_holdings` |

## Research context

| File | Rule it breaks | Key |
|---|---|---|
| `experiment-id-uppercase.yaml` | `experiment_id` matches `[a-z0-9][a-z0-9_-]{0,63}`: lowercase only | `experiment_id` |
| `experiment-id-device-name.yaml` | `experiment_id` isn't a name Windows reserves for a device (`nul`) | `experiment_id` |
| `experiment-id-too-long.yaml` | `experiment_id` has at most 64 characters (this one has 65) | `experiment_id` |
| `experiment-id-number.yaml` | `experiment_id` is text, never a number read as one | `experiment_id` |
| `empty-title.yaml` | `title` has 1 to 200 characters | `title` |
| `title-too-long.yaml` | `title` has at most 200 characters (this one has 201) | `title` |
| `blank-purpose.yaml` | `purpose` isn't all whitespace | `purpose` |
| `purpose-too-long.yaml` | `purpose` has at most 2,000 characters (this one has 2,001) | `purpose` |
| `status-incomplete.yaml` | `prior_research.status` is `complete`, `partial`, or `unknown`; `incomplete` is the word METH-03.4 used before `partial` | `prior_research.status` |
| `complete-without-description.yaml` | `prior_research.description` is required with `complete` | `prior_research.description` |
| `partial-without-description.yaml` | `prior_research.description` is required with `partial` | `prior_research.description` |
| `blank-prior-research-description.yaml` | `prior_research.description` isn't all whitespace | `prior_research.description` |
| `prior-research-description-too-long.yaml` | `prior_research.description` has at most 5,000 characters (this one has 5,001) | `prior_research.description` |

## Which settings vary

| File | Rule it breaks | Key |
|---|---|---|
| `variant-universe.yaml` | A variant may change only `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, never `universe` | `variants.universe` |
| `variant-ranking.yaml` | A variant may change only `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, never `ranking` | `variants.ranking` |
| `variant-benchmark.yaml` | A variant may change only `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, never `benchmark` | `variants.benchmark` |
| `variant-start-date.yaml` | A variant may change only `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, never `start_date` | `variants.start_date` |
| `variants-empty.yaml` | `variants`, when it's given, holds at least one key | `variants` |
| `empty-max-holdings-list.yaml` | A variant list holds at least one entry | `variants.max_holdings` |
| `empty-rules-list.yaml` | A variant list holds at least one entry | `variants.rules` |
| `empty-slippage-list.yaml` | A variant list holds at least one entry | `variants.slippage_percent` |

## Keys and descriptions

| File | Rule it breaks | Key |
|---|---|---|
| `key-baseline.yaml` | A variant's key isn't `baseline`, the baseline's case key | `variants.max_holdings[0].key` |
| `key-duplicate.yaml` | A variant's key is unique among the experiment's cases | `variants.slippage_percent[0].key` |
| `key-default.yaml` | A variant's key isn't the default variant's, `rebalance-weeks-1`, beside the default it would name | `variants.slippage_percent[0].key` |
| `key-uppercase.yaml` | A variant's key matches `[a-z0-9][a-z0-9_-]{0,63}`: lowercase only | `variants.max_holdings[0].key` |
| `key-device-name.yaml` | A variant's key isn't a name Windows reserves for a device (`con`) | `variants.max_holdings[0].key` |
| `blank-description.yaml` | A variant's `description`, when given, isn't all whitespace | `variants.rules[0].description` |
| `description-too-long.yaml` | A variant's `description` has at most 500 characters (this one has 501) | `variants.rules[0].description` |

## A variant changes something

| File | Rule it breaks | Key |
|---|---|---|
| `value-equals-baseline.yaml` | A variant's `value` differs from the baseline's | `variants.max_holdings[0].value` |
| `slippage-equals-baseline.yaml` | A variant's `value` differs from the baseline's once normalized: `0.250` is the baseline's `0.25` | `variants.slippage_percent[0].value` |
| `rebalance-weeks-equals-baseline.yaml` | A variant's `value` differs from the baseline's | `variants.rebalance_weeks[0].value` |
| `two-variants-one-case.yaml` | No two cases resolve to the same settings: two `max_holdings` variants of 50 | `variants.max_holdings[1]` |
| `only-baseline.yaml` | An experiment has at least one variant: `rebalance_weeks: []` and no other variant leave only the baseline | `variants.rebalance_weeks` |

## Each variant's change

| File | Rule it breaks | Key |
|---|---|---|
| `missing-value.yaml` | A variant of `max_holdings` has a `value` | `variants.max_holdings[0].value` |
| `value-in-rules.yaml` | A variant of `rules` has no `value` | `variants.rules[0].value` |
| `add-in-max-holdings.yaml` | A variant of `max_holdings` has no `add` | `variants.max_holdings[0].add` |
| `add-and-replace.yaml` | A variant of `rules` holds `add`, or `replace` and `with`, never both | `variants.rules[0]` |
| `replace-without-with.yaml` | `with` is required with `replace` | `variants.rules[0].with` |
| `with-without-replace.yaml` | `replace` is required with `with` | `variants.rules[0].replace` |
| `replace-not-a-rule.yaml` | `replace` is the same text as one of the baseline's rules | `variants.rules[0].replace` |
| `add-existing-rule.yaml` | `add` isn't one of the baseline's rules | `variants.rules[0].add` |
| `with-existing-rule.yaml` | `with` isn't one of the baseline's rules | `variants.rules[0].with` |
| `unquoted-add.yaml` | `add` is written in quotes or as a block scalar, as rules are (R01-T18) | `variants.rules[0].add` |
| `unquoted-replace.yaml` | `replace` is written in quotes or as a block scalar, as rules are | `variants.rules[0].replace` |
| `unquoted-with.yaml` | `with` is written in quotes or as a block scalar, as rules are | `variants.rules[0].with` |

## Variant values

| File | Rule it breaks | Key |
|---|---|---|
| `rebalance-weeks-2.yaml` | A rebalance variant's `value` is 1 or 4, the verified values | `variants.rebalance_weeks[0].value` |
| `max-holdings-0.yaml` | A holdings variant's `value` is 1 or more: 0, meaning no limit, isn't verified | `variants.max_holdings[1].value` |
| `slippage-negative.yaml` | A slippage variant's `value` is 0 or more | `variants.slippage_percent[0].value` |
| `slippage-five-decimals.yaml` | A slippage variant's `value` has at most 4 digits after the decimal point | `variants.slippage_percent[0].value` |
| `value-string.yaml` | A variant's `value` is a number, never text | `variants.max_holdings[0].value` |
| `rebalance-weeks-float.yaml` | A rebalance variant's `value` is an integer, never `1.0` | `variants.rebalance_weeks[0].value` |

## The budget

| File | Rule it breaks | Key |
|---|---|---|
| `budget-below-cases.yaml` | `budget.provider_requests` is at least the number of cases (4, for five cases) | `budget.provider_requests` |
| `budget-zero.yaml` | `budget.provider_requests` is 1 or more | `budget.provider_requests` |
| `budget-string.yaml` | `budget.provider_requests` is an integer, never text | `budget.provider_requests` |
| `budget-float.yaml` | `budget.provider_requests` is an integer, never `6.0` | `budget.provider_requests` |
