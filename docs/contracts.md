# Trial Folio contracts

**Status:** Draft. Nothing here is implemented; no models, schemas, or fixtures exist yet.
**Date:** 2026-10-01

This document owns the meaning of Trial Folio's interfaces and artifacts: configuration files, saved artifacts, identifiers, metric values, errors, CLI behavior, reports, and logs. When implemented, Pydantic models under `src/trialfolio/contracts/` will define the executable structures, JSON Schemas generated from them under `schemas/` will publish those structures, and tests with fixtures under `tests/fixtures/` will provide conformance evidence. This prose stays authoritative for meaning. If a model accepts something this document says is invalid, the model has a defect.

Structures appear here as lists of concepts, not field-by-field schemas. Each release specification states which concepts it introduces and which schema versions it ships. Examples are illustrative until an implementation validates them.

## Public contract boundary

For semantic versioning, Trial Folio's public contract is:

- Documented CLI commands, options, exit codes, and stdout/stderr behavior.
- Configuration file formats.
- Machine-readable outputs: manifests, normalized CSV files, and `--json` summaries.
- The documented ability to read artifacts written by earlier versions.

Python functions are internal during 0.x.y development (proposed default). A core function becomes public only when this section names it, which will be required before any separately distributed interface calls it. Log event names and fields are documented below but are not public contract.

## Versioning

**Requirement (REQ-07).** Application releases use `<major>.<minor>.<patch>` per [Semantic Versioning 2.0.0](https://semver.org/): three non-negative integers without leading zeroes.

- During 0.x.y, a new feature or a breaking change increments minor. Patch releases stay backward compatible.
- From 1.0.0, incompatible public-contract changes increment major, backward-compatible features and deprecations increment minor, and backward-compatible fixes increment patch.
- Published releases are immutable; corrections ship as a new version.
- Breaking changes and migration instructions are documented, including during 0.x.y.
- 1.0.0 is adopted when the public contract above is intentionally declared stable.
- **Writing versions.** A version is written bare, with no prefix, everywhere it appears: package metadata, `trialfolio --version`, artifacts, release specifications, file names, and prose (`0.2.0`). The only exception is git release tags. They are named `v` plus the version, as in `v0.2.0`, following the [Semantic Versioning FAQ](https://semver.org/#is-v123-a-semantic-version): the tag name is `v0.2.0`, and the version is `0.2.0`. Artifact schema versions are never prefixed.

Every artifact records these versions separately:

| Version | Meaning |
|---|---|
| `trialfolio_version` | Application version that wrote the artifact |
| `schema_version` | Artifact schema version, `<major>.<minor>.<patch>`, independent of the application version |
| `parser_version` | Version of the adapter that interpreted a provider response, per supported layout |
| `canonicalization_version` | Version of the canonical-hashing rules used for identities |
| Provider wrapper version | `p123api` version used for provider requests |
| Method versions | Version of each analytical method applied (when methods are introduced) |
| `license_id`, `notice_version` | The applicable license identifier (`LicenseRef-NSPRL-1.0`) and financial-notice version (`1.0`), defined in [../LICENSE](../LICENSE) and [disclaimers.md](disclaimers.md) |

A schema's version does not need to match the release that introduces it. Compatibility is defined against documented readers and semantics, not merely against added fields.

## Identity

Identifiers are introduced with the release that can define their semantics.

| Identifier | Introduced | Meaning | Proposed form |
|---|---|---|---|
| `artifact_id` | 0.1.0 | Content address of one stored file | `sha256:<64 hex>` of the file's bytes |
| `review_id` | 0.2.0 | One `trialfolio review` output | Random UUID, version 4 |
| `label` | 0.2.0 | User-declared name of one compared result, unique within a review | `[a-z0-9][a-z0-9_-]{0,63}` |
| `plan_hash` | 0.1.0 | Identity of a plan, which execution requires as approval | `sha256:` of the plan's canonical form ([plan hashing](#plan-hashing)) |
| `case_id` | 0.1.0 | Stable identity of one fully resolved configuration | `case-` plus the first 16 hex digits of the SHA-256 of the canonical resolved settings ([plan hashing](#plan-hashing)) |
| `case_key` | 0.3.0 | User-declared readable name for a planned case | Same pattern as `label` |
| `attempt_id` | 0.1.0 | One execution attempt of a case | Random UUID, version 4 |
| `experiment_id` | 0.3.0 | One declared experiment | User-declared slug, same pattern as `label` |
| `study_id`, `candidate_id`, `assessment_id` | Later | Defined when their increment is specified | — |

Configuration identity and attempt identity MUST stay separate. Re-running the same resolved configuration creates a new attempt of the same case. Changing any resolved setting creates a different case.

## Provenance

**Requirement (INV-02).** Every setting, metadata value, and reported metric carries a provenance class:

| Class | Meaning |
|---|---|
| `verified` | Captured by Trial Folio from the provider during an attempt it executed, or independently confirmed and recorded as such |
| `user_supplied` | Provided by the user as description rather than as a request setting, for example a declared purpose or an intended-change reason |
| `inferred` | Derived by Trial Folio under a documented rule, for example a date range read from row dates; the rule is recorded |
| `unknown` | Not available from any source |

Every Portfolio123 result Trial Folio holds comes from a request it planned, sent, and recorded ([ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md)). So the settings sent and the values captured are `verified`, and a provider default applied to an omitted setting is `inferred`. Each value also records its source artifact and location where applicable, for example the configuration key or the response's JSON path.

## Configuration files

Configuration files are YAML documents owned by the user. The rules apply to every kind:

- Each file declares `kind` (`screen` from 0.1.0, `review` from 0.2.0, `experiment` from 0.3.0) and `schema_version`.
- Unknown keys are rejected, so misspellings fail instead of being ignored.
- YAML is loaded with a safe loader. Values are not coerced: a percentage is written as a number with a declared unit, not as `"5%"`; dates use `YYYY-MM-DD`; booleans are `true` or `false` only.
- Configuration never contains credentials. A credential-like key is rejected.
- File paths inside a configuration are resolved relative to the configuration file.
- Duplicate keys are rejected; a YAML loader must not silently keep the last one.

### Screen configuration

Schema version 1.0.0, introduced in 0.1.0 (task R01-T03). A screen configuration describes one long-only stock screen backtest, run through `p123api`'s `screen_backtest`. It covers only the settings in [0.1.0's scope](releases/0.1.0-api-execution.md#included-scope), as documented on Portfolio123's [API: Screen](https://portfolio123.customerly.help/en/articles/43324-api-screen) page, checked 2026-10-01.

**Keys:**

| Key | Type | Required | Rules | Sent as |
|---|---|---|---|---|
| `kind` | string | Yes | `screen` | Not sent |
| `schema_version` | string | Yes | A supported version (`1.0.0`). Any other value fails with `config.invalid`, and the message names the supported versions. | Not sent |
| `title` | string | Yes | 1–200 characters. Used as the report heading. | Not sent |
| `purpose` | string | No | Up to 2,000 characters. If it's absent, the report says no purpose was declared. | Not sent |
| `universe` | string | Yes | A Portfolio123 universe name, for example `SP500` | `screen.universe` |
| `rules` | list of strings | Yes | At least one screening formula. Each one is a non-empty string, and their order is kept. | `screen.rules`, each as `{"formula": "…"}`. It has no `type` field, because Portfolio123 rejects one (R01-T01). |
| `ranking` | mapping | Yes | Exactly one of the [ranking forms](#ranking-forms) | `screen.ranking` |
| `max_holdings` | integer | Yes | 1 or more | `screen.maxNumHoldings` |
| `benchmark` | string | Yes | A Portfolio123 benchmark symbol, for example `SPY` | `screen.benchmark` |
| `start_date` | date | Yes | `YYYY-MM-DD` | `startDt` |
| `end_date` | date | Yes | `YYYY-MM-DD`, later than `start_date`. There is no default of today. | `endDt` |
| `rebalance_weeks` | integer | Yes | 1 or 4 | `rebalFreq`: `Every Week` for 1, or `Every 4 Weeks` for 4 |
| `transaction_price` | string | Yes | `open`. Required, so the price convention is always explicit. | `transPrice`: 1 |
| `slippage_percent` | decimal | Yes | 0 or more, in percent: `0.25` means 0.25%. There is no default of zero. | `slippage` |
| `pit_method` | string | Yes | `complete`, Portfolio123's point-in-time method | `pitMethod`: `Complete` |
| `precision` | integer | Yes | 4: the decimal places in results | `precision` |
| `data_vendor` | string | No | `FactSet` only ([D-16](spec.md#decisions)). Any other value, including `Compustat`, fails with `config.invalid`. | Never sent, because the endpoint documents no vendor parameter |

**Verified values.** Following [D-20](spec.md#decisions), the configuration accepts only values a recorded live call has verified. Free-form values, such as universe names, benchmark symbols, formulas, holdings counts, and slippage, are verified by form: R01-T01 sent one of each, and Portfolio123 accepted them.

- **Verified by R01-T01:** a formula ranking, `rebalance_weeks` 4, `open`, `complete`, and precision 4.
- **Verified by R01-T05 before 0.1.0 is Ready:** `rebalance_weeks` 1, ranking by name, and ranking by ID, each in its own call. A value that fails its check is removed from these tables.
- **Documented but not accepted until a release verifies them:**
  - `max_holdings` 0, meaning no limit
  - `rebalance_weeks` 2, 3, 6, 8, 13, 26, and 52
  - `transaction_price` `high_low_average` and `close` (`transPrice` 3 and 4)
  - `pit_method` `prelim`
  - precision 2 and 3

#### Ranking forms

| Form | Keys in `ranking` | Sent as |
|---|---|---|
| A single formula (recommended) | `formula`, a non-empty string; `lower_is_better`, a boolean, required | `{"formula": "…", "lowerIsBetter": …}` |
| An existing ranking system, by name | `name`, a non-empty string | The name, as a string |
| An existing ranking system, by ID | `id`, a positive integer | The ID, as an integer |

- **One form only.** `ranking` holds exactly one of `formula`, `name`, and `id`. `lower_is_better` is allowed only with `formula`.
- **Account objects.** A ranking system named by name or ID is a mutable object in the provider account. Release 0.1.0 doesn't retrieve its definition, so it is recorded as an external reference that is not snapshotted, and reproducibility is labeled incomplete.
- **Not supported:**
  - a ranking method override, which Portfolio123 writes as `{"method": …, "id": …}` or `{"method": …, "name": …}`
  - ranking definitions given as nodes or XML

Either one fails with `config.invalid`, and the message names the supported forms.

**Rules that span keys and values:**

- **YAML types.** Trial Folio accepts only unambiguous YAML values, and rejects forms that a YAML 1.1 safe loader would quietly convert:
  - **Integers** are plain decimal digits, with no leading zero, underscore, sign, or base prefix. So `010`, `1_000`, `+5`, and `0x10` are rejected. An integer is at most 9007199254740991 (2^53 − 1), the largest a JSON number keeps exactly, so canonical hashing stays exact. A larger one fails with `config.invalid`.
  - **Booleans** are `true` or `false`, and are never accepted where a number is expected, or the reverse.
  - **Dates** have no time part. So `2016-01-01 09:30:00` is rejected. A date may be a YAML date or a string in exactly `YYYY-MM-DD` form.
- **Decimals.** A decimal is read from its YAML text, never through binary floating point.
  - **Form.** It's written in plain notation: digits, optionally followed by a decimal point and more digits. There's no sign, exponent, or leading zero before another digit, so `2.5e-1`, `-0.25`, `.25`, and `00.25` are rejected. A whole number such as `0` or `1` is accepted.
  - **Normalization.** Before it's recorded, hashed, or compared, trailing zeros after the decimal point are removed, and then the point if no digits follow it. So `0.250` and `0.25` are the same setting, and so are `1.0` and `1`.
  - **Limits.** After normalization, it has at most 15 significant digits and at most 15 digits after the decimal point. Such a value survives a round trip through binary floating point: most values, such as `0.1`, have no exact binary form, but the shortest form that converts back to the nearest binary number has exactly the same digits. So it's sent as a JSON number that reads back as the same decimal. The JSON may write a very small value with an exponent, such as `1e-15`. A value outside these limits fails with `config.invalid`.
  - **Not a string.** A number written as a string is rejected.
- **Dates.** `end_date` is later than `start_date`.
- **Formulas.** Formulas are the user's strategy definition. They're sent and saved, but never logged. Write them in single quotes. Portfolio123 formulas often contain double quotes, which single quotes keep as they are. YAML processes no escapes inside single quotes, and a single quote inside one is written twice (`''`).
- **Descriptions.** `title` and `purpose` describe the run. They are recorded in the plan and the run manifest with `user_supplied` provenance ([plan contents](#plan-contents)). They're never sent, and they aren't part of the resolved settings that identify a case.

**Sent on every request.** Trial Folio adds three fixed values, which 0.1.0's scope doesn't let the configuration change. R01-T01 verified each one.

- `screen.type`: `stock`
- `screen.method`: `long`
- `screen.currency`: `USD`

Trial Folio sends nothing else. The documented parameters it leaves out are `riskStatsPeriod`, `maxPosPct`, `rankTolerance`, `carryCost`, `longWeight`, and `shortWeight`. The settings below record each one.

#### Screen settings

`settings.csv` has these rows for a screen run, in this order. Every category here except `other` is critical. A review configuration's `intended_changes` accepts only the settings marked declarable: the ones a screen configuration can set to different values.

| # | `setting` | `category` | Declarable | Unit | Value and provenance |
|---|---|---|---|---|---|
| 1 | `universe` | `universe` | Yes | | From `universe`; `verified`. Flagged `not_snapshotted`. |
| 2 | `screen_type` | `universe` | No | | `stock`; `verified` |
| 3 | `rules` | `strategy` | Yes | | From `rules`, as a JSON array of strings; `verified` |
| 4 | `ranking` | `strategy` | Yes | | From `ranking`, as a JSON object with the configuration's keys, for example `{"formula": "EarnYield", "lower_is_better": false}`; `verified`. A ranking by name or ID is flagged `not_snapshotted`. |
| 5 | `max_holdings` | `strategy` | Yes | `count` | From `max_holdings`; `verified` |
| 6 | `position_method` | `strategy` | No | | `long`; `verified` |
| 7 | `benchmark` | `benchmark` | Yes | | From `benchmark`; `verified` |
| 8 | `currency` | `currency` | No | | `USD`; `verified` |
| 9 | `start_date` | `dates` | Yes | | From `start_date`; `verified` |
| 10 | `end_date` | `dates` | Yes | | From `end_date`; `verified` |
| 11 | `rebalance_weeks` | `execution` | Yes | `weeks` | From `rebalance_weeks`; `verified` |
| 12 | `transaction_price` | `execution` | Yes | | From `transaction_price`; `verified` |
| 13 | `slippage_percent` | `costs` | Yes | `percent` | From `slippage_percent`, normalized; `verified` |
| 14 | `commission` | `costs` | No | | `not_modeled`; `inferred`. The API documents no commission parameter, and slippage is its only trading-cost input. Never zero. |
| 15 | `pit_method` | `data_source` | Yes | | From `pit_method`; `verified` |
| 16 | `data_vendor` | `data_source` | No | | `FactSet`; `inferred` from [D-16](spec.md#decisions), whether the key is omitted or given, because it is never sent and the response doesn't report it. Flagged `inferred_default`. |
| 17 | `precision` | `other` | Yes | | From `precision`; `verified` |
| 18 | `risk_stats_period` | `other` | No | | `monthly`; `inferred` from the [documented default](#p123api-screen-backtest-version-1). Flagged `inferred_default`. |
| 19 | `max_pos_pct` | `strategy` | No | | `not_sent`; `unknown`. `maxPosPct` isn't sent, and its default isn't documented. |
| 20 | `rank_tolerance` | `strategy` | No | | `not_sent`; `unknown`, as row 19, for `rankTolerance` |
| 21 | `carry_cost` | `costs` | No | | `not_sent`; `unknown`, as row 19, for `carryCost` |
| 22 | `long_weight` | `strategy` | No | | `not_sent`; `unknown`, as row 19, for `longWeight` |
| 23 | `short_weight` | `strategy` | No | | `not_sent`; `unknown`, as row 19, for `shortWeight` |

- **No empty values.** A setting with no value from the request uses a token instead, `not_modeled` or `not_sent`. So no screen-run row has an empty `value`. Two runs that both leave a parameter unsent compare as `same`, and the report still lists its default as unknown.
- **Interpretation.** Rows 19–23 are `not_interpreted`, and every other row is `interpreted`.
- **Other columns.** `original_key` and `original_value` come from the configuration, and are empty for rows that no key supplies. For row 16 they're filled only when the configuration gives `data_vendor`. `inference_rule` cites the decision or documentation and the date the documentation was checked.
- **Coverage.** `start_date` and `end_date` also carry `coverage_mismatch` when the response's coverage differs from them ([coverage](#p123api-screen-backtest-version-1)).

#### Example

```yaml
kind: screen
schema_version: 1.0.0
title: Earnings yield with a liquidity floor
purpose: Reference backtest for the 0.1.0 response layout.
universe: SP500
rules:
  - 'AvgDailyTot(30) > 1000000'
ranking:
  formula: 'EarnYield'
  lower_is_better: false
max_holdings: 25
benchmark: SPY
start_date: 2016-01-01
end_date: 2025-12-31
rebalance_weeks: 4
transaction_price: open
slippage_percent: 0.25
pit_method: complete
precision: 4
```

This example is validated in two ways:

- **Against Portfolio123.** It resolves to exactly the request in [`reference/p123api-screen-backtest/request.json`](../reference/p123api-screen-backtest/request.json), which Portfolio123 accepted in R01-T01.
- **Against this mapping.** The example was parsed with a YAML safe loader and mapped by the rules above, and the result equals that request.

Once implemented, a fixture test repeats the second check (R01-T05 names it).

### Review configuration

Schema version 1.0.0, introduced in 0.2.0. It names saved runs written by `trialfolio run`.

**Top-level keys:**

| Key | Type | Required | Rules |
|---|---|---|---|
| `kind` | string | Yes | `review` |
| `schema_version` | string | Yes | A supported version (`1.0.0`). Any other value fails with `config.invalid`, and the message names the supported versions. |
| `title` | string | Yes | 1–200 characters. Used as the report heading. |
| `purpose` | string | No | Up to 2,000 characters. If it's absent, the report says no purpose was declared. |
| `baseline` | string | Yes | Must equal the `label` of one entry in `results` |
| `results` | list | Yes | At least two entries |

**Each entry in `results`:**

| Key | Type | Required | Rules |
|---|---|---|---|
| `label` | string | Yes | Matches `[a-z0-9][a-z0-9_-]{0,63}`, and is unique within the file |
| `run` | path | Yes | A complete run directory written by `trialfolio run` |
| `description` | string | No | Up to 500 characters, shown in the report |
| `intended_changes` | list | No | Not allowed on the baseline entry |

**Each entry in `intended_changes`:**

| Key | Type | Required | Rules |
|---|---|---|---|
| `setting` | string | Yes | A setting marked declarable in the [screen settings](#screen-settings). An unknown name fails with `config.invalid`, and the message lists the valid names. A result may list each setting at most once. |
| `reason` | string | Yes | 1–500 characters, shown in the report |

**Rules that span keys:**

- **Intended change not observed.** If a declared change isn't there because the two values are equal, the result is still valid. The difference is classified `same` and flagged `intended_change_not_observed`.
- **Intended change that can't be confirmed.** If the setting is missing from either run, the difference is `unknown` and is flagged.
- **Identical responses.** Two entries may name runs whose saved responses are byte-identical. That is flagged `identical_source`, as a warning.

Example:

```yaml
kind: review
schema_version: 1.0.0
title: Holdings 25 versus 50
purpose: Check whether doubling holdings changes risk as expected.
baseline: hold25
results:
  - label: hold25
    run: runs/hold25
  - label: hold50
    run: runs/hold50
    intended_changes:
      - setting: max_holdings
        reason: Doubling holdings is the change under review.
```

## Source artifacts

**Requirement (INV-04).** Source files are preserved byte for byte before anything is derived from them. A source artifact record contains:

- `artifact_id`, size, and the path relative to the output root.
- Role: screen configuration, provider request, or provider response.
- Acquisition time in UTC.
- Source format identifier and version, for example [`p123api-screen-backtest` version 1](#p123api-screen-backtest-version-1).
- The adapter and parser version that interpreted it.
- Provenance class, and source identity where available, for example the provider operation and account-independent identifiers.

## Supported provider payloads

Trial Folio supports only the response layouts recorded here. For each layout, this section records:

- **Identity.** The layout identifier and version, and the `p123api` version it was observed with.
- **Structure.** The top-level keys, and the structure used to validate a response.
- **Metrics.** Each one's `metric_id`, its JSON path, its unit, the precision the response carries, and its definition.
- **Everything else.** What the response contains that Trial Folio preserves but does not interpret, such as the per-period series in 0.1.0.

### `p123api-screen-backtest` version 1

Introduced in 0.1.0 (task R01-T02). Portfolio123 doesn't document the response fields, so everything below is a verified observation of the reference response in [`reference/p123api-screen-backtest/`](../reference/p123api-screen-backtest/README.md). The response itself stays git-ignored. The run record there holds the checks behind each "reproduced" statement. A definition marked "not reproduced" is Portfolio123's own, and Trial Folio reports the value as given.

**Identity.**

- The layout is the decoded JSON body that `p123api`'s `screen_backtest(params, to_pandas=False)` returns for `POST /screen/backtest`. It was observed with `p123api` 3.1.0.
- The response carries no version of its own. Trial Folio labels a response version 1 when it has the required structure below.

**Required structure.** A response without it is saved, and the result is flagged `provider.response_invalid`:

- The top level is an object with `stats` and `results` objects.
- `stats` has `port` and `bench` objects.
- `results.columns` is an array of strings. `results.rows` is an array of arrays, each as long as `columns`.

Nothing else is required. Extra keys, or a missing `chart` or summary row, don't make a response invalid. Individual values fail as follows:

- **A metric key that is missing, or whose value is `null`,** makes that metric unavailable with `blank_in_source`. A value that isn't a JSON number is unavailable with `unparseable_in_source`.
- **Coverage dates.** If `results.rows` is empty, or `columns` lacks `Tran Dt` or `End Dt`, then `coverage_start` and `coverage_end` are unavailable with `blank_in_source`. A date that isn't `YYYY-MM-DD` is `unparseable_in_source`. `coverage_periods` is always the number of rows, including zero.

**Numbers and precision.**

- The wrapper decodes JSON numbers into binary floating point. Trial Folio saves each one in its shortest round-trip form. For values of up to 15 significant digits, that form keeps every digit the provider sent except trailing zeros.
- Trial Folio reads numbers from the saved text as decimals, never as binary floats. A value keeps exactly the digits it has there, and `source_decimals` is the number of digits after its decimal point.
- A value can therefore carry fewer decimal places than the request's `precision`. The reference response was requested at 4, and its `stats.port.standard_dev` has 3. Trial Folio doesn't pad it back to 4.
- No value in the reference response carries more decimal places than the requested precision.

**Metrics.** `metrics.csv` has these rows, in this order:

| # | `metric_id` | `subject` | Source | Unit | Definition |
|---|---|---|---|---|---|
| 1 | `coverage_start` | `strategy` | Calculated: the earliest `Tran Dt` in `results.rows` | `date` | The first transaction date |
| 2 | `coverage_end` | `strategy` | Calculated: the latest `End Dt` in `results.rows` | `date` | The end of the last period |
| 3 | `coverage_periods` | `strategy` | Calculated: the number of `results.rows` | `count` | The number of rebalance periods |
| 4 | `total_return` | `strategy` | `stats.port.total_return` | `percent` | Cumulative return over the backtest. Reproduced: the last `chart` level minus 100. |
| 5 | `annualized_return` | `strategy` | `stats.port.annualized_return` | `percent` | Compound annual growth rate over the calendar days from the first to the last `chart` date, with 365.25-day years. Reproduced. |
| 6 | `max_drawdown` | `strategy` | `stats.port.max_drawdown` | `percent` | The largest peak-to-trough decline in the daily `chart` levels, as a negative number. Reproduced. |
| 7 | `standard_deviation` | `strategy` | `stats.port.standard_dev` | `percent` | Annualized standard deviation of monthly returns: the sample standard deviation of the month-end-to-month-end changes in the `chart` levels, times √12. Reproduced. |
| 8 | `sharpe_ratio` | `strategy` | `stats.port.sharpe_ratio` | `ratio` | Portfolio123's Sharpe ratio. Its risk-free rate isn't documented. Not reproduced. |
| 9 | `sortino_ratio` | `strategy` | `stats.port.sortino_ratio` | `ratio` | Portfolio123's Sortino ratio. Its risk-free rate and target aren't documented. Not reproduced. |
| 10 | `correlation` | `strategy` | `stats.correlation` | `ratio` | Correlation with the benchmark. Close to, but not equal to, the correlation of the monthly returns. Not reproduced. |
| 11 | `r_squared` | `strategy` | `stats.r_squared` | `ratio` | The square of `correlation`. Consistent: the reported `correlation`, squared and rounded, gives the reported value. |
| 12 | `beta` | `strategy` | `stats.beta` | `ratio` | Beta against the benchmark. Close to, but not equal to, the regression beta of the monthly returns. Not reproduced. |
| 13 | `alpha` | `strategy` | `stats.alpha` | `percent` | Portfolio123's alpha against the benchmark. The unit is inferred from the value's magnitude, and the method isn't documented. Not reproduced. |
| 14 | `risk_samples` | `strategy` | `stats.samples` | `count` | The number of returns behind the risk statistics. Reproduced: it equals the number of monthly returns in the `standard_deviation` reproduction, which runs from the end of the first month to the end of the next-to-last month. |
| 15–20 | Rows 4–9 again | `benchmark` | The same keys under `stats.bench` | As rows 4–9 | As rows 4–9, for the benchmark. The same checks reproduce rows 4–7. |

The other columns are filled the same way on every row:

- **`source_label`** is the last key of the JSON path, for example `standard_dev`. **`source_location`** is the full path, for example `stats.port.standard_dev`. Both are empty for the coverage rows.
- **`origin` and `provenance`.** Rows 1–3 are `calculated` and `inferred`, under the rules in the table. Every other row is `reported` and `verified`.
- **`period_start` and `period_end`** are `coverage_start` and `coverage_end` on every row. They're empty when those are unavailable.
- **`benchmark`** holds the request's `screen.benchmark` on rows 10–13, which compare the strategy with the benchmark. It's empty on every other row.

**Risk statistics.** Release 0.1.0 doesn't send `riskStatsPeriod`, so Portfolio123's default applies, which is documented as Monthly:

- The [API: Screen](https://portfolio123.customerly.help/en/articles/43324-api-screen) page lists the values as `['Monthly'] | 'Weekly' | 'Daily'`.
- The [wrapper documentation](https://portfolio123.customerly.help/en/articles/13765-the-api-wrapper-p123api) says that for an optional parameter, "the default value when not specified is the first value in the list (if any)".

The reference response agrees: the standard deviations (rows 7 and 18) reproduce from monthly returns, and `risk_samples` counts them. The other risk statistics, rows 8–13, 19, and 20, presumably use the same period, but that isn't verified. R01-T03 records the effective value as an inferred setting that cites this documentation.

**Coverage.**

- Rows appear newest first in the reference response. Trial Folio uses the earliest and latest dates, not row positions.
- Each period's `End Dt` is the next period's `Tran Dt`. The first and last periods can be shorter than the rebalance frequency.
- The first period's `As Of Dt` and `Rank Dt` fall before the start date, because the first positions are chosen from earlier data. They are signal dates, not coverage.
- `coverage_mismatch` flags a difference between coverage and the requested `startDt` or `endDt`. It appears on the date settings in `settings.csv`, which R01-T03 names. In the reference response, coverage equals the requested dates.

**Preserved but not interpreted in 0.1.0:**

- **`cost` and `quotaRemaining`** are integers: the credits charged and the credits left. The attempt record keeps them as provider metadata. `quotaRemaining` is account information, so it's kept out of `metrics.csv`, the report, and the JSON summary (proposed default).
- **`results.rows`,** apart from the two coverage dates. It has one row per rebalance period, with these columns:

  | Column | Type | Observed meaning |
  |---|---|---|
  | `#` | integer | The period number, 1 for the earliest |
  | `As Of Dt`, `Rank Dt`, `Tran Dt`, `End Dt` | `YYYY-MM-DD` string | The period's as-of, ranking, transaction, and end dates |
  | `#Pos`, `New Pos`, `Sold Pos` | integer | Positions held, bought, and sold |
  | `Turn` | number | Turnover in percent. It equals `Sold Pos` divided by `#Pos`, times 100, in every reference period. |
  | `Ret%`, `Bench%`, `Excess%` | number | The period's return in percent for the strategy and the benchmark, and their difference. `Ret%` and `Bench%` reproduce from the `chart` levels. |
  | `100 USD Investment`, `100 USD in SPY:USA` | number | The value of 100 invested, at the period's end. Reproduced. Their names contain the currency and the benchmark, so they change with those settings. |
  | `Costs`, `Cash`, `Min % no slip`, `Max % no slip`, `StdDev` | number | Not verified |

- **`results.average`, `results.upMarkets`, and `results.downMarkets`.** Each is one element shorter than `columns`: element *i* belongs to `columns[i+1]`. Element 0 is `null`. In `upMarkets` and `downMarkets`, element 1, under `Rank Dt`, holds the number of periods in the group. The other non-null elements are means of their column: over all periods, over periods whose `Bench%` is above zero, and over the rest. No period had a `Bench%` of exactly zero, so which group it joins is unverified. The wrapper's `to_pandas=True` conversion appends these arrays as table rows without the offset, which moves each value one column to the left. Trial Folio doesn't use that conversion ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md), decision 4).
- **`chart`,** five parallel arrays with one entry per weekday from the start date to the end date, including market holidays: `dates`, `screenReturns`, `benchReturns`, `turnoverPct`, and `positionCnt`. Despite their names, `screenReturns` and `benchReturns` are levels of 100 invested, starting at 100, not returns. `turnoverPct` and `positionCnt` hold whole numbers written as decimals, such as `25.0`.

## Metrics and missing values

**Requirements (INV-03, INV-08).** A metric value carries:

| Concept | Meaning |
|---|---|
| Value | A decimal string carrying the source's precision, for example `"12.30"`. Never a float in interchange JSON, and never NaN or infinity. |
| Unit | One of `percent` (12.30 means 12.30%), `ratio` (dimensionless, for example beta or Sharpe), `currency:<ISO 4217 code>`, `count`, `days`, or `date` |
| Definition | A metric identifier and a reference to its documented definition; for provider metrics, the response's own key and the layout's documented meaning |
| Context | Period covered, return frequency where known, and benchmark where the metric is benchmark-relative |
| Origin | `reported` (read from a source) or `calculated` (computed by Trial Folio, with method and version) |
| Availability | `available`, or `unavailable` with a reason code |
| Source precision | Number of decimal places as reported |

Unavailability reason codes:

| Code | Meaning |
|---|---|
| `absent_from_layout` | The source layout has no such metric |
| `blank_in_source` | The source has the field but no value |
| `unparseable_in_source` | The value could not be interpreted; the original text remains in the preserved source |
| `not_applicable` | The metric has no meaning in this context, for example a benchmark-relative metric with no benchmark |
| `not_supported` | The parser does not interpret this field yet |
| `input_unavailable` | A calculated value whose input was unavailable |

An unavailable metric is never written as zero, blank, or a placeholder number. CSV output writes an empty value together with a reason column. Trial Folio never reports more precision than its inputs: a difference between two values has the smaller of their two decimal counts.

## Settings and differences

Each run has original settings, as written in its screen configuration, and resolved settings: the normalized names, values, and units that were actually sent. Settings that refer to mutable objects in the provider account, such as a saved ranking system or universe by name, are recorded as external references. Each one is marked snapshotted, if its definition was captured, or not snapshotted, with reproducibility labeled incomplete.

When a setting was omitted and the provider applied its default, the effective value is `inferred`: the record cites the documented default and the version of the documentation it came from. A default that depends on when the tool ran, such as an end date of "today", is `unknown` unless the data itself establishes it, for example the last date in a returned series. Trial Folio never assumes the run date.

Each setting in each non-baseline result is classified against the baseline:

| Class | Meaning |
|---|---|
| `same` | Equal resolved value |
| `intended_change` | Differs, and the configuration declares it as an intended change |
| `unexplained_mismatch` | Differs, and no intended change declares it |
| `unknown` | Missing or uninterpretable in at least one of the two results |

Settings in these categories are critical: dates, benchmark, currency, costs (commission and slippage), execution (price convention, rebalance timing, and similar), universe, data source (data vendor and point-in-time method), and strategy (the screen's rules, ranking, and holdings). An `unexplained_mismatch` or `unknown` in a critical category is flagged prominently in the report and the normalized output. An intended change to a critical setting is shown, but not as a defect.

Metric differences are computed only between comparable values: the same unit, the same definition, and compatible contexts. A difference is `candidate − baseline` in the metric's unit, and a difference between `percent` values is expressed in percentage points (`pp`). Relative differences are not reported unless a release specifies and labels them. When contexts differ, for example different benchmarks or periods, Trial Folio shows both values, does not report a difference, and explains why.

## Normalized tables

Schema version 1.0.0. `metrics.csv` and `settings.csv` are introduced in 0.1.0, and `differences.csv` in 0.2.0. These tables are public contract. The manifest records each table's schema version, because a CSV file can't carry its own.

**Format rules for every table:**

- **Encoding.** UTF-8 without a byte-order mark, comma-delimited, quoted per RFC 4180, with `\n` line endings.
- **Columns.** One header row, then columns in exactly the order listed below.
- **Values:**
  - Decimals are written as normalized: a `.` decimal point, no thousands separators, no exponent, and never more digits than the source.
  - Dates are `YYYY-MM-DD`, and booleans are `true` or `false`.
  - A list is written as a JSON array in one cell.
- **Empty cells.** A cell is empty only where a column allows it. An empty value always comes with a reason in the row's reason column.
- **Row order.** Results appear in the order the configuration lists them. Within a result, rows follow the layout mapping's order, so the output is deterministic.
- **Compatibility.** New columns are appended only, and adding one is a schema change under [artifact compatibility](#artifact-compatibility).

### `metrics.csv`

One row for each metric of each result. That includes coverage values, which use the `date` and `count` units.

| Column | Meaning |
|---|---|
| `label` | Result label |
| `subject` | `strategy` or `benchmark` |
| `metric_id` | Stable identifier from the layout mapping, for example `annualized_return` in [`p123api-screen-backtest` version 1](#p123api-screen-backtest-version-1). Coverage uses `coverage_start`, `coverage_end`, and `coverage_periods`. |
| `source_label` | The metric's label as it appears in the source. Empty for coverage values. |
| `value` | Decimal or date string. Empty when unavailable. |
| `unit` | One of the units in [metrics and missing values](#metrics-and-missing-values) |
| `source_decimals` | Decimal places as reported. Empty for dates, counts, and unavailable values. |
| `availability` | `available` or `unavailable` |
| `unavailable_reason` | Reason code. Empty when available. |
| `origin` | `reported` or `calculated`. Coverage values are `calculated`. |
| `provenance` | `verified`, `user_supplied`, `inferred`, or `unknown` |
| `period_start`, `period_end` | The period the metric covers. Empty when unknown. |
| `benchmark` | The benchmark, for benchmark-relative metrics. Empty otherwise. |
| `source_artifact` | `artifact_id` of the source file |
| `source_location` | Where the value was read: its JSON path in the response, for example `stats.port.annualized_return`, as fixed by the verified layout. Empty for calculated values. |

### `settings.csv`

One row for each setting of each result. This includes documented settings that are absent and settings Trial Folio does not interpret.

| Column | Meaning |
|---|---|
| `label` | Result label |
| `setting` | Normalized setting name, in snake_case. A provider parameter that Trial Folio doesn't send gets its snake_case name, for example `rank_tolerance`. |
| `category` | `dates`, `benchmark`, `currency`, `costs`, `execution`, `universe`, `data_source`, `strategy` (the screen's own definition, such as its rules, ranking, and holdings), or `other` |
| `critical` | `true` for the critical categories in [settings and differences](#settings-and-differences) |
| `value` | Normalized value. Lists, such as screen rules, are JSON arrays, and mappings, such as a ranking, are JSON objects. A setting with no value from the request uses a token instead: `not_sent` for a provider parameter that isn't sent, or `not_modeled` for a cost the provider path doesn't model. Never empty. |
| `unit` | Unit for numeric values. Empty otherwise. |
| `interpretation` | `interpreted` or `not_interpreted` |
| `provenance` | `verified` for a value sent in the request, `inferred` for a documented default or rule, or `unknown` |
| `inference_rule` | For `inferred` values, the rule and its source, for example Portfolio123's documented default and the date the documentation was checked. Empty otherwise. |
| `original_key` | The key path in the screen configuration. Empty when the setting was omitted. |
| `original_value` | The value exactly as written in the source. Empty when absent. |
| `source_artifact` | `artifact_id` of the saved screen configuration |
| `flags` | Flag codes, separated by semicolons. Empty when none apply. |

### `differences.csv`

One row for each setting and each metric of each non-baseline result, compared with the baseline.

| Column | Meaning |
|---|---|
| `label` | The compared result |
| `baseline_label` | The baseline result |
| `kind` | `setting` or `metric` |
| `name` | Setting name or `metric_id` |
| `subject` | For metrics, `strategy` or `benchmark`. Empty for settings. |
| `category`, `critical` | For settings, as in `settings.csv`. Empty for metrics. |
| `baseline_value`, `value` | The two values being compared |
| `unit` | Unit of the two values |
| `classification` | For settings: `same`, `intended_change`, `unexplained_mismatch`, or `unknown`. For metrics: `differenced`, `not_comparable`, or `unavailable`. |
| `difference` | For `differenced` metrics: `value − baseline_value`. Empty otherwise. |
| `difference_unit` | `pp` for percent metrics, otherwise the metric's unit. Empty when there's no difference. |
| `difference_decimals` | The smaller of the two source decimal counts |
| `reason` | For `not_comparable` or `unavailable`: `different_benchmark`, `different_period`, `different_unit`, or `input_unavailable`. Empty otherwise. |
| `declared_reason` | For `intended_change`, the reason the configuration gives |
| `flagged` | `true` when the row needs the reader's attention: a critical `unexplained_mismatch` or `unknown`, or any row with a warning flag |
| `flags` | Flag codes, separated by semicolons |

### Flag codes

| Code | Meaning |
|---|---|
| `critical_unexplained_mismatch` | A critical setting differs, and the configuration doesn't declare the change |
| `critical_unknown` | A critical setting is missing or can't be interpreted in at least one of the two results |
| `intended_change_not_observed` | A declared change isn't present; the values are equal |
| `inferred_default` | The value is a default the provider applies to an omitted setting. It's inferred from the provider's documentation or an owner decision, such as [D-16](spec.md#decisions), and not reported by the provider. |
| `time_dependent_default` | An absent setting whose default depends on when the tool ran, such as an End Date of "today". The value is `unknown` unless the data establishes it. |
| `unsupported_value` | The value is recorded, but it is unsupported and unverified, for example a data vendor other than FactSet ([D-16](spec.md#decisions)) |
| `not_snapshotted` | The setting names a mutable object in the provider account, such as a ranking system or universe, whose definition wasn't captured. Reproducibility is incomplete. |
| `coverage_mismatch` | Requested dates and actual coverage differ |
| `identical_source` | Two results have byte-identical saved responses |

## Execution outcomes and attempts

Introduced in 0.1.0.

| Outcome | Meaning |
|---|---|
| `planned` | In an approved plan; not started |
| `running` | A durable start record exists; the attempt has not finished |
| `succeeded` | The provider returned a response that was saved, and the attempt record is durably complete. This says nothing about the strategy. |
| `failed` | The attempt ended with a recorded error |
| `skipped` | Deliberately not run, with a reason |
| `unknown` | Completion is uncertain: a request may have been sent and a response was not durably recorded |

An attempt record contains the `attempt_id`, the `case_id`, the `plan_hash` it ran under, start and end times, the outcome, any error code, its [HTTP exchanges](#http-exchanges) and whether it's `possibly_charged`, references to the redacted request and the saved response, provider metadata, the installed versions of `p123api`, `requests`, and `urllib3`, and any charge or quota information the provider returned.

Trial Folio saves decoded provider payloads, which is what the wrapper exposes, and labels them as decoded payloads. It does not claim to capture HTTP bytes or headers, because the verified wrapper does not expose them ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md#verification-notes)). Trial Folio configures the wrapper for a single HTTP attempt per call, turns off redirects, and refuses the wrapper's re-authentication after a 401 or 403, as below. So the request is sent at most once, and running the command again is a new attempt.

### HTTP exchanges

Trial Folio mounts its own transport adapter on the wrapper's HTTP session, for both `https://` and `http://`, so every request the wrapper makes passes through it ([ADR 0006](adrs/0006-observe-the-wrappers-http-exchanges.md)). The adapter records each exchange in memory, in order, and the attempt record keeps the list:

| Field | Contents |
|---|---|
| `request` | The method and path, for example `POST /auth` or `POST /screen/backtest` |
| `result` | `response`: a complete response arrived. `not_connected`: the connection was never established, so nothing was sent. `interrupted`: the connection was established, but no complete response arrived, so the request may have reached Portfolio123. |
| `status` | The HTTP status of a `response`. `null` otherwise. |

- **Not connected means provably not sent.** An exchange is `not_connected` only when the `requests` error wraps a `urllib3` `MaxRetryError` whose `reason` is a `ConnectTimeoutError`. That class covers a failed name lookup (`NameResolutionError`), a refused or unreachable connection (`NewConnectionError`), and a connect timeout. `urllib3` uses the same test to decide that a request is safe to retry, because the server didn't receive it. Every other error is `interrupted`, including a reset, a read timeout, and a TLS failure. So an unclear case counts as possibly sent.
- **Recorded before sending.** The adapter adds each exchange to the list before it sends, and fills in the result afterwards. An exchange still without a result when the attempt record is written, for example after Ctrl-C, counts as `interrupted`.
- **The body is read inside the adapter.** A body that breaks off is therefore recorded as `interrupted`.
- **Nothing else is recorded.** The adapter keeps no headers, bodies, tokens, or exception objects. It changes no request or response, and passes every error on unchanged.
- **No redirects.** Trial Folio sets the session's `max_redirects` to 0. On a redirect, `requests` then raises `TooManyRedirects` before it sends anything more, and the exchange records the 3xx as a `response`.
- **Authentication first, and only once.** Trial Folio authenticates with its own call before the call that sends the request, so the first exchange is its own `POST /auth`. After a 401 or 403, the wrapper would re-authenticate and resend the request. Once Trial Folio's own authentication has succeeded, the adapter refuses any further `POST /auth`: it raises an error of Trial Folio's own type without connecting. The wrapper catches only `requests.ConnectionError`, so that error ends the call, and the request isn't resent. A refused `POST /auth` sent nothing, so it isn't recorded.
- **Possibly charged.** An attempt is `possibly_charged` when its request's exchange has a result other than `not_connected`. Authentication isn't counted ([budget](#budget-and-retries)).
- **Classification reads the exchanges.** Trial Folio classifies a failure from the exchanges, never from the wrapper's exception. From the exception it takes only a sanitized message ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md), decision 7). [0.1.0's failure behavior](releases/0.1.0-api-execution.md#failure-and-incomplete-data-behavior) gives the classification.

### Uncertain completion

Trial Folio authenticates first, then writes a `running` record durably, and only then sends the request. If authentication fails, the attempt is recorded as `failed`, with no `running` record before it, because the request wasn't sent. If the process stops during authentication, the output has no attempt record, for the same reason. Authentication isn't counted in the budget, and whether it costs credits is an [open question](releases/0.1.0-api-execution.md#open-questions). On restart, a `running` attempt without a durable response becomes `unknown`. An `unknown` attempt is never retried automatically, because the original request may have been charged or may have changed provider state.

## Plans and approval

**Requirement (REQ-04).** Before any charged or mutating provider request, Trial Folio builds a plan from the configuration. A plan contains every fully resolved case, the requests each case needs, a request budget, the retry policy, and the categories of data that will leave the machine. Its `plan_hash` is the SHA-256 of its canonical form. Execution requires that exact hash as approval. If the plan changes, the approval no longer applies.

The core builds plans and checks approvals, and never prompts. The CLI shows the plan and obtains the approval.

### Plan contents

Schema version 1.0.0, introduced in 0.1.0 (task R01-T04). A 1.0.0 plan has exactly one case; release 0.3.0's plan 1.1.0 adds several cases and revisions. `plan.json` holds:

| Field | Contents |
|---|---|
| `schema_version` | `1.0.0` |
| `trialfolio_version` | The version that built the plan |
| `canonicalization_version` | `1`: the [canonical hashing](#canonical-hashing) rules behind `plan_hash` and `case_id` |
| `provider_wrapper` | `p123api` and its installed version, which will send the requests. The retry policy describes that version's behavior. So Trial Folio plans only with a version a release has verified: 3.1.0 for 0.1.0 ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md#verification-notes)). Any other installed version fails with `provider.unsupported_capability`, exit 5, before the plan is shown. The package pins the verified version exactly, `p123api==3.1.0`, so a clean install gets it, and a test checks that the pin is in the verified list ([ADR 0006](adrs/0006-observe-the-wrappers-http-exchanges.md)). |
| `title`, `purpose` | From the configuration, with `user_supplied` provenance. `purpose` is `null` when the configuration has none. Neither is sent. |
| `cases` | The cases, in order. Exactly one in 1.0.0. |
| `budget` | The request budget, [below](#budget-and-retries) |
| `retry_policy` | The retry policy, [below](#budget-and-retries) |
| `data_sent` | The categories of data that leave the machine, [below](#data-sent) |
| `plan_hash` | `sha256:` and 64 lowercase hex digits, as [hashing](#plan-hashing) defines |

Each case holds:

| Field | Contents |
|---|---|
| `case_id` | The case's identity, [below](#plan-hashing) |
| `requests` | The provider requests the case needs, in order, each with an `operation` and its `params`. Exactly one in 0.1.0. |
| `settings` | Every row of the [screen settings](#screen-settings), in that order, with the `settings.csv` columns except `label`, `original_key`, `original_value`, and `source_artifact`. `provenance` is replaced by `expected_provenance`. |

**The 0.1.0 request.** Its `operation` is `screen_backtest`: `p123api`'s `screen_backtest`, which sends `POST /screen/backtest`. Its `params` is the JSON object passed to the wrapper, exactly as it will be sent, so its numbers are JSON numbers. It holds no credentials; the wrapper sends those separately.

**Settings in the plan.**

- **Values keep their JSON types.** Integers are numbers, decimals are normalized decimal strings, dates are `YYYY-MM-DD` strings, lists are arrays, mappings are objects, and tokens such as `not_sent` are strings. `flags` is an array of codes, empty when none apply. Any other column that `settings.csv` leaves empty is `null`.
- **Expected provenance.** Nothing in a plan has been sent yet, so no value in it is `verified` ([provenance](#provenance)). Instead, each row records `expected_provenance`: the provenance the value will have once the request is sent. Values in the request expect `verified`. `settings.csv` records the actual provenance after the attempt.
- **Flags known before execution.** These are `inferred_default` and `not_snapshotted`. `coverage_mismatch` needs the response, so it appears only in `settings.csv`.
- **No trace of how the file was written.** The four columns left out depend on how the configuration file is written. So two files that resolve to the same settings give the same plan, for example an omitted `data_vendor` and an explicit `FactSet` ([D-16](spec.md#decisions)), or `0.250` and `0.25`.

### Budget and retries

**Budget.** The values for 0.1.0:

| Field | Value |
|---|---|
| `provider_requests` | 1: the most times Trial Folio sends a provider request. The request is sent at most once ([HTTP exchanges](#http-exchanges)), so this is also the worst case. |
| `credits_per_request` | 5: Portfolio123's documented cost of a screen backtest. The plan records the source, [API: Screen](https://portfolio123.customerly.help/en/articles/43324-api-screen), and the date it was checked, 2026-10-01. |
| `credits` | 5: `provider_requests` times `credits_per_request`, the most credits the plan can use at the documented cost |

- **Every request counts,** whatever its outcome, because whether failed requests are charged is unverified.
- **Within budget.** A run or experiment is within its budget when its `provider_requests` count, the sends that may have reached Portfolio123 ([JSON summary](#json-summary)), is at most the budget's `provider_requests`. Execution never starts a send that would exceed it.
- **Authentication isn't counted.** Trial Folio authenticates once, through the wrapper's `POST /auth`, before the request. Portfolio123's [API credits](https://portfolio123.customerly.help/en/articles/13766-api-credits) page doesn't say whether that costs credits (checked 2026-10-01). See the [0.1.0 open questions](releases/0.1.0-api-execution.md#open-questions).
- **The documented cost, not the charge.** The budget uses the documented cost. The attempt records the `cost` Portfolio123 reports.

**Retry policy.**

| Field | Value |
|---|---|
| `automatic_retries` | 0. Trial Folio never resends a request on its own. Running the command again is a new attempt. |
| `wrapper_attempts_per_call` | 1. Trial Folio sets the wrapper to one HTTP attempt per call, with `set_max_request_retries(1)`, for authentication and for the backtest. |
| `redirects` | `not_followed`. A 3xx response ends the call ([HTTP exchanges](#http-exchanges)). |
| `reauthentication` | `refused`. After a 401 or 403, the pinned `p123api` 3.1.0 re-authenticates and resends the request once, and no setting disables that ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md#verification-notes)). Trial Folio refuses that re-authentication before it's sent, so the request isn't resent ([HTTP exchanges](#http-exchanges)). |

### Data sent

`data_sent` lists each category of data that leaves the machine. Each entry names its recipient, Portfolio123, through `p123api`, and the settings it carries, if any:

| Category | Contents |
|---|---|
| `credentials` | The API ID and key, sent to authenticate. They're never recorded. |
| `strategy_definition` | The universe, the rules, and the ranking: its formula, or a ranking system's name or ID |
| `backtest_settings` | The holdings, benchmark, dates, rebalance frequency, transaction price, slippage, point-in-time method, and precision, plus the fixed type, method, and currency |

These are categories of data, not the setting categories of `settings.csv`. Nothing else is sent: not the title, the purpose, `data_vendor`, the configuration file, file paths, earlier results, or logs.

### Plan hashing

- **The plan hash** is `sha256:` plus the hex SHA-256 of the [canonical form](#canonical-hashing) of the plan without its `plan_hash` field.
- **The case ID** is `case-` plus the first 16 hex digits of the SHA-256 of the canonical form of the case's `settings`, with each row reduced to `setting`, `value`, and `unit`. Changing any resolved setting changes it. The title, the purpose, and how the file is written don't.
- **Nothing varies between invocations.** The plan holds no timestamps, output directory, file paths, attempt IDs, credentials, or account information. So the same configuration, Trial Folio version, and wrapper version give the same plan and hash on any machine, at any time, and for any output directory. That's what lets a user review a plan in one command and approve it in the next.
- **Any change needs a new approval.** That includes a changed setting, title, purpose, budget, Trial Folio version, or wrapper version. So after upgrading Trial Folio or `p123api`, the same configuration needs approving again.
- **Saved plans are checked.** A reader recomputes the hash of a saved `plan.json`. If it differs from `plan_hash`, the run is invalid (`input.not_a_run`).

### Approval

The core recomputes a plan's hash from its contents, and executes the plan only when it's given a hash equal to that. It never trusts a stored `plan_hash` field. Otherwise it fails with `plan.approval_required` and sends nothing. The CLI gets the hash in one of two ways:

- **`--approve <plan-hash>`, for non-interactive use.** The value must be the full hash exactly as shown: `sha256:` and 64 lowercase hex digits. An abbreviated, malformed, or different hash doesn't match. With `--approve`, the CLI never asks for approval. The license acknowledgment is separate, and comes first ([order of steps](#approval)).
- **Interactive confirmation.** Without `--approve`, when stdin and stderr are both terminals, the CLI shows the plan and asks the user to type `approve`. It then passes the hash of the plan it showed. Any other answer, an empty line, or the end of input is a refusal.

Without a match, the command fails with `plan.approval_required`, exit 2, and creates no output. The plan hash has been shown, with the full plan on a terminal, and the message gives the exact option that approves this plan. So running without `--approve` from a script gets the hash without sending anything, and with `--json`, the summary's `ids` carry the `plan_hash`.

**The plan display.** The CLI writes it to stderr directly, never through logging, because it contains configuration values and formulas ([logging](#logging-and-local-diagnostics)). For the same reason, it shows the full plan only when stderr is a terminal: when it asks for confirmation, and when approval fails. When stderr isn't a terminal, as in a script or a CI job whose output may be kept, it shows only the plan hash and the budget, and says that running the command in a terminal shows the full plan. With a matching `--approve`, the plan is already approved, so it also shows only the plan hash and the budget. The full plan shows:

- the title and purpose
- the request exactly as it will be sent
- every resolved setting with its expected provenance, marking inferred defaults, settings not snapshotted, commission not modeled, and parameters not sent
- the budget, and that failed or uncertain attempts may be charged
- the retry policy
- the data sent, its recipient, and what isn't sent
- the plan hash, and how to approve it

**Order of steps in `trialfolio run`.** Trial Folio creates no output and sends no request before step 7. So a plan can be reviewed, and its hash obtained, without credentials.

1. Check the license acknowledgment (`license.not_acknowledged`).
2. Validate the configuration (`config.invalid`).
3. Check that the output directory is absent or empty (`output.not_empty`).
4. Check that the installed `p123api` is a verified version (`provider.unsupported_capability`). Build the plan and show it, as [the plan display](#approval) says.
5. Check the approval (`plan.approval_required`).
6. Check that credentials are present (`provider.auth_failed`).
7. [Claim the output directory](#cli-behavior) with `plan.json` (`output.not_empty`, or `storage.write_failed` on a file system that can't take [atomic writes](#artifact-storage)). Logging to `<out>/logs/` starts only after the claim succeeds ([logging](#logging-and-local-diagnostics)). Write `configuration.yaml`, from the bytes read in step 2.
8. Authenticate with Trial Folio's own call. If that fails, write the attempt record as `failed` and stop ([uncertain completion](#uncertain-completion)).
9. Write the `running` attempt record, and send the request.

**Records.**

- **The attempt record** names the `plan_hash` it ran under.
- **The manifest** records the `plan_hash` and how it was approved: `interactive` or `option`.
- **Logs** record the plan hash and the case ID, never the plan's contents.

In 0.1.0, a hash that doesn't match is `plan.approval_required`. `plan.changed` is for a saved plan that the configuration no longer resolves to, which arrives with resuming experiments in 0.3.0.

## Artifact storage

**Requirement (REQ-05).** All artifact reads and writes go through the `ArtifactStore` interface. From 0.1.0 it has a local filesystem implementation.

- **Relative paths.** Paths in manifests are relative to the output root, never absolute, so a moved or served directory stays valid.
- **Immutability.** Source artifacts are never modified after they are written. Trial Folio never overwrites an existing artifact; corrections and migrations produce new artifacts.
- **Atomic writes.** Each file is written to a temporary name in the same directory, flushed and synced to disk, and then published under its final name without replacing anything:
  - **Never replace.** If the final name exists, even because another process created it at the same moment, publishing fails, and the temporary file is removed.
  - **Linux and macOS.** `os.rename` and `os.replace` silently replace an existing file there, so they aren't used. Trial Folio hard-links the temporary file to the final name with `os.link`, which fails if the name exists. It then removes the temporary name and syncs the directory.
  - **Windows.** `os.rename` fails if the name exists, so it's used.
  - **Syncing.** A sync is `os.fsync`. On macOS, `fsync` doesn't flush the drive's write cache, so Trial Folio also calls `fcntl.fcntl` with `fcntl.F_FULLFSYNC`.
  - **No hard links.** On Linux and macOS, a file system without hard links, such as FAT or exFAT, can't take these writes. The first write, which for `run` is `plan.json`, fails with `storage.write_failed`, before any request is sent, and the message says why. On Windows, `os.rename` works on those file systems.
- **Completion.** A case is complete only after its required payload and its attempt record are durably written. The manifest is written last, and a missing or incomplete manifest means the output is incomplete.
- **Hashes.** Hashes detect changes. They do not prove that a provider's data is scientifically correct, and they do not make local files tamper-proof.

Proposed layout for a 0.1.0 run; the release specification owns the final layout:

```text
<out>/
  manifest.json
  plan.json
  configuration.yaml                                byte-for-byte copy of the screen configuration
  cases/<case_id>/attempts/<attempt_id>/
    attempt.json
    request.json                                    redacted
    response.json                                   the decoded response
  normalized/metrics.csv
  normalized/settings.csv
  report.html
  logs/                                             diagnostics; excluded from hashes and from the manifest's evidence
```

Release 0.2.0 defines the review layout. The proposal is `inputs/<label>/`, holding byte-for-byte copies of each compared run's manifest and normalized tables, plus `normalized/differences.csv`. Release 0.3.0 adds `experiment.json` and a lock file.

The manifest records:

- `schema_version`, `artifact_type` (`review`, `run`, or `experiment`), `trialfolio_version`, and the creation time in UTC.
- The command and its non-secret options.
- For a run or an experiment, the `plan_hash` and how the plan was approved: `interactive` or `option` ([approval](#approval)). The synthetic run `trialfolio demo` writes sends nothing, so its approval is `not_required`.
- Every input and output artifact with its `artifact_id`.
- Parser versions, `license_id`, and `notice_version`.
- A capability statement of what the artifact does and does not contain. For example, it says whether return series are present, and states `statistical_validation: not_assessed` and `trading_readiness: not_assessed`.
- Counts: results, cases, attempts by outcome, provider requests as the [JSON summary](#json-summary) counts them, retries, and returned cost or quota metadata.

Raw files and JSON metadata come first, and normalized tables are CSV. Parquet MAY be added for large tables when needed. SQLite MAY later index outputs, but it MUST NOT become a first-release prerequisite or the only copy of any evidence.

## Canonical hashing

Proposed default until 0.1.0 is Ready. These rules then become `canonicalization_version` 1, which plan 1.0.0 and `case_id` use (R01-T04), and any later change makes a new version.

- Canonical JSON follows [RFC 8785, JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html), applied to the model's serialized form.
- Decimal values are strings: a configuration decimal in its normalized form ([screen configuration](#screen-configuration)), and a metric value with exactly the digits its saved source carries. The exception is a provider request recorded as it's sent, such as a plan's `params`: its numbers stay JSON numbers ([ADR 0003](adrs/0003-versioned-research-artifacts.md), decision 6).
- RFC 8785 writes a number as ECMAScript does, which differs from Python's `json.dumps`: `0.00001` rather than `1e-05`, and `1e-7` rather than `1e-07`. So the canonical form needs an RFC 8785 implementation, never `json.dumps`. R01-T10 chooses one, and a fixture with a slippage of `0.00001` checks it (R01-AC25).
- Dates use `YYYY-MM-DD`. Datetimes are UTC ISO 8601 with a `Z` suffix.
- Secrets are excluded by construction. Models that hold credentials are never serialized or hashed.
- Hashes are SHA-256.
- The rules carry a `canonicalization_version`; changing them increments it, and old identities remain valid under their recorded version.

Exact bytes are part of the contract only for canonical hashing. Everywhere else, tests assert meaning, not byte-for-byte output.

## Artifact compatibility

Defined before 0.1.0 ships:

- Artifact schema versions are independent of application versions.
- Each documented historical schema version has a reader and a committed fixture.
- A new optional field is not assumed compatible with strict readers; each schema change states its compatibility.
- An unknown schema version fails clearly with `artifact.unknown_schema_version`. A later release MAY add an explicitly labeled restricted inspection mode.
- Migrations preserve the original and write a new artifact.
- Configurations are strict. Preserved provider payloads keep every field the provider returned, including fields Trial Folio does not normalize. Artifact extensions follow a documented policy, not ad hoc keys.

## Reports

**Requirements (REQ-08, REQ-13, D-07).** A human-facing report is one self-contained HTML file:

- It uses inline CSS and inline SVG only. It contains no `<script>` elements, event-handler attributes, or references to external resources such as fonts, stylesheets, images, or links that load content.
- The concise financial-result notice from [disclaimers.md](disclaimers.md) appears near the top. The full notice and the license identifier appear at the end, in a `<details>` element, which needs no script.
- It includes the sections below. A section the evidence cannot support is shown as unavailable, with the reason, and is never filled with invented content.
  1. Objective, declared purpose, benchmark, and research status.
  2. Definitions, and what changed from the baseline, with intended changes separated from unexplained mismatches.
  3. Data sources, actual coverage, provenance, missing values, and exclusions.
  4. Returns, risks, costs, exposures, and implementation assumptions, as available.
  5. All results or cases, and their outcomes, including failed or rejected ones.
  6. Robustness results and concentration of contributions.
  7. Statistical methods, assumptions, uncertainty, multiplicity handling, and power limitations.
  8. Development, selection, holdout, and forward evidence, clearly separated.
  9. Conditional findings on feasibility and capacity, and the execution evidence still missing.
  10. The permitted conclusion, limitations, and relative links to the underlying artifacts.
- Metrics show units and source precision.
- Charts appear only when the data supports them. Summary statistics alone never justify a return, drawdown, or confidence-interval chart.
- Process status is shown neutrally. No green "pass" styling appears near strategy results. Statistical validation and trading readiness read "Not assessed" until a release that assesses them.
- An LLM-written narrative, if a later release adds one, may not introduce a metric or claim that is absent from the saved assessment.

Reports count as output under [D-07](spec.md#decisions). Users may share them with the concise notice intact, subject to data-provider terms.

## CLI behavior

The command is `trialfolio`. Commands are introduced by release:

| Command | Release | Purpose |
|---|---|---|
| `trialfolio run <config> --out <dir> [--approve <plan-hash>]` | 0.1.0 | Plan and execute one supported screen backtest, once its [plan is approved](#approval) |
| `trialfolio report <run-dir> --out <dir>` | 0.1.0 | Re-render a saved run's report offline |
| `trialfolio demo --out <dir>` | 0.1.0 | Proposed: write a synthetic example run, labeled synthetic, and render its report offline |
| `trialfolio review <config> --out <dir>` | 0.2.0 | Compare saved runs offline |
| `trialfolio experiment <config> --out <dir>` | 0.3.0 | Plan, execute, and resume a finite experiment |
| `trialfolio --version` | 0.1.0 | Print the application version |
| `trialfolio license [--accept]` | 0.1.0 | Print the license, the full notice, and the acknowledgment status; `--accept` records the acknowledgment |

- **stdout** carries the command's result: a short human summary, or with `--json` the [JSON summary](#json-summary).
- **stderr** carries progress, warnings, and errors, which come from the same events as the log file. It also carries the [plan display](#approval) and the confirmation prompts, which are written directly and never logged, because they show configuration values.
- **Output directory.** `review` and `run` create the output directory. They refuse to write into a directory that exists and is not empty (`output.not_empty`). There is no overwrite option in 0.1.0. `experiment` reuses an existing directory only to resume the same plan, as release 0.3.0 specifies.
- **Claiming the directory.** A command checks the directory early, but another process can write to it before the command writes anything, for example while `run` waits for approval. So a command claims the directory with its first file:
  1. It creates the directory if it's absent.
  2. It writes its first file without replacing any file ([atomic writes](#artifact-storage)).
  3. It lists the directory.

  If the first file existed already, or the directory holds anything else, the claim fails with `output.not_empty`. Each command lists the directory only after its own file exists. So when two commands claim the same directory at once, at most one succeeds.

  A command whose claim fails, with `output.not_empty` or `storage.write_failed`, removes what it created: the file it wrote, if any, and the directory, if it created it. The directory then holds only what was there before, or what another process wrote. A command writes nothing else, logs included, into a directory it hasn't claimed.
- **Validation first.** All inputs are validated before the output directory is created, so an invalid or unsupported input creates no output. An interactive license acknowledgment, which comes first, still writes its own record.
- **Partial success.** A command that finishes with some cases failed, skipped, or uncertain writes complete accounting and exits with code 6.

Exit codes (proposed default):

| Code | Meaning |
|---|---|
| 0 | Command completed and outputs were written. This says nothing about any strategy. |
| 1 | Unexpected internal error |
| 2 | Usage error: invalid arguments, missing plan approval, or license not acknowledged |
| 3 | Invalid or unsupported configuration, input, or artifact |
| 4 | Output problem: directory not empty, write failure, or experiment locked by another process |
| 5 | Provider error: authentication, provider unavailable, quota, unsupported capability, rejected request, uncertain outcome, or invalid response |
| 6 | Partial completion: at least one planned case failed, was skipped, or is uncertain |
| 130 | Interrupted by the user |

### JSON summary

With `--json`, every command writes exactly one JSON object to stdout, followed by a newline. It does so whether the command succeeds or fails. The summary has its own `schema_version`, starting at 1.0.0. New keys may be added in minor versions; existing keys don't change meaning.

| Key | Meaning |
|---|---|
| `schema_version` | Summary schema version |
| `command` | For example `review` |
| `trialfolio_version` | Application version |
| `outcome` | `completed`, `partial`, or `failed` |
| `exit_code` | The process exit code |
| `ids` | Identifiers the command created, for example `{"review_id": "…"}`. For `run`: `plan_hash` and `case_id` once the plan is built, even if it isn't approved, and `attempt_id` once an attempt starts. Empty when it created none. |
| `output_dir` | The output directory as given on the command line. `null` if none was created. |
| `outputs` | Output files relative to `output_dir`, keyed by role: `manifest`, `report`, `metrics`, `settings`, `differences` |
| `counts` | For `run`: `attempts`; `provider_requests`, the sends of the planned request that may have reached Portfolio123, never authentication ([HTTP exchanges](#http-exchanges)), which the [budget](#budget-and-retries) limits; `metrics_unavailable`; `warnings`; and the credit `cost` when the provider reports it. For `review` (0.2.0): `results`, `settings_flagged`, `metrics_unavailable`, `warnings`. |
| `statistical_validation`, `trading_readiness` | `not_assessed` in every 0.x release that doesn't assess them |
| `error` | `null`, or `{"code": …, "message": …}` using the codes in [errors](#errors) |

### License acknowledgment

**Requirement ([D-17](spec.md#decisions), [LIC-12](licensing-policy.md#lic-12-acceptance-and-acknowledgment)).** Before a command processes any data, the user acknowledges the license and the research notice once. This applies to `run`, `report`, and `demo`, and later to `review` and `experiment`. Each acknowledgment covers one license identifier and one notice version. Only a change to either one asks again.

- **Interactive.** When stdin and stderr are both terminals and there's no valid acknowledgment, the CLI prints three things to stderr:
  - the concise notice
  - the license identifier and notice version
  - how to read the full text with `trialfolio license`

  It then asks the user to type `accept`. Any other answer exits with `license.not_acknowledged` and writes nothing.
- **Non-interactive.** There are two ways to acknowledge:
  - `trialfolio license --accept` records the acknowledgment.
  - Setting `TRIALFOLIO_ACCEPT_LICENSE` to `<license_id>/<notice_version>`, for example `LicenseRef-NSPRL-1.0/1.0`, acknowledges for that process only and records nothing, which suits CI.

  Without either, the command exits with `license.not_acknowledged`. The message gives both options and the exact value to use.
- **Exempt commands.** `trialfolio --version`, `--help`, and `trialfolio license` work without an acknowledgment. `trialfolio license` prints the license, the full notice, and the acknowledgment status.
- **The record.** It's a file, `acknowledgment.json`, in the per-user configuration directory:
  - `TRIALFOLIO_CONFIG_DIR`, if set
  - otherwise `$XDG_CONFIG_HOME/trialfolio` or `~/.config/trialfolio` on Linux
  - `~/Library/Application Support/trialfolio` on macOS
  - `%APPDATA%\trialfolio` on Windows

  It holds only `license_id`, `notice_version`, `acknowledged_at` (UTC), and `method` (`interactive` or `command`). It contains no identity, account, financial, or family information, and it is never transmitted. If the file can't be written, the command continues for that run with a warning.
- **Scope.** This is a notice, not an eligibility check. It asks nothing about assets, income, or family ([LIC-12](licensing-policy.md#lic-12-acceptance-and-acknowledgment)). The core never checks it ([REQ-03](spec.md#enduring-requirements)). Each interface presents it, as the CLI does here.

## Errors

The core raises typed errors with stable dotted codes and actionable messages. Only the CLI maps them to exit codes. Messages say what failed, why, and what to do next. They never include credentials, and they include the offending values only in the terminal, never in logs.

| Code | Exit | Meaning |
|---|---|---|
| `config.invalid` | 3 | Configuration fails validation, including unknown keys and cross-field rules |
| `input.not_found` | 3 | A referenced file does not exist |
| `input.not_a_run` | 3 | An input directory is not a complete Trial Folio run: its manifest is missing, or its files don't match their hashes. The message names the problem. |
| `artifact.unknown_schema_version` | 3 | An artifact's schema version has no reader |
| `license.not_acknowledged` | 2 | A data-processing command ran without an acknowledgment of the current license and notice versions |
| `plan.approval_required` | 2 | A charged or mutating operation was requested without the matching plan hash: no `--approve`, a different hash, or a refused confirmation |
| `plan.changed` | 3 | The configuration no longer resolves to a saved plan, for example when resuming an experiment (0.3.0). A hash given with `--approve` that doesn't match is `plan.approval_required`. |
| `output.not_empty` | 4 | The output directory exists and is not empty |
| `storage.write_failed` | 4 | An artifact could not be written durably |
| `experiment.locked` | 4 | Another process holds the experiment lock |
| `provider.auth_failed` | 5 | Credentials were missing, Trial Folio's authentication call got a status other than 200 below 500, or Portfolio123 refused a request's authorization with a 401 or 403 |
| `provider.unavailable` | 5 | Portfolio123 couldn't be reached, so the request wasn't sent: Trial Folio's authentication call got a 5xx or no complete response, or the request's connection was never established ([HTTP exchanges](#http-exchanges)) |
| `provider.quota_exceeded` | 5 | The provider refused the request because of quota or credits |
| `provider.unsupported_capability` | 5 | The requested setting or operation is not supported by the verified provider path |
| `provider.request_rejected` | 5 | Portfolio123 answered the request with a status below 500 that no other code covers, such as a 3xx, 404, or 429. The message gives the status and Portfolio123's sanitized message. |
| `provider.response_invalid` | 5 | The response was saved but failed validation |
| `provider.outcome_unknown` | 5 | A request may have been sent, but no response was durably recorded: for example after a read timeout, a 5xx, or a response that couldn't be decoded. It is never retried automatically. |
| `execution.partial` | 6 | Some planned cases did not succeed; all are accounted for |
| `internal.unexpected` | 1 | A defect; the message asks the user to report it with the log location |

## Interface-independent core

**Requirement (REQ-03).** The CLI is the first interface, not necessarily the only one.

- The CLI parses arguments, reads configuration files, injects credentials, calls core functions, formats output, and maps errors to exit codes.
- Core functions accept validated models and return result models. They do not print, prompt, parse arguments, exit the process, read environment variables, or read secrets.
- Readers of configurations and saved runs accept content together with a declared source name, not only a filesystem path, so an uploaded file follows the same path as a local one.
- Planning returns a plan model, and execution requires the approved plan hash.
- Long-running execution reports progress through callbacks or events and supports cancellation between provider requests. It holds a lock that prevents two processes from executing the same experiment, and it serializes Portfolio123 shared-state operations per account across processes.

## Protocols

Protocols are introduced only when a release needs them. Each protocol's documentation states its preconditions, return type, exceptions, side effects, and capability limits. Data lives in models and behavior in protocols, and dependencies are passed explicitly, never through global clients.

| Protocol | Release | Responsibility |
|---|---|---|
| `ArtifactStore` | 0.1.0 | Persist and read artifacts by relative path, with atomic writes and immutability as above |
| `ReportRenderer` | 0.1.0 | Render a saved comparison or assessment to HTML without provider or network access |
| `ScreenBacktestClient` | 0.1.0 | Execute the one supported screen-backtest request and return the captured provider evidence |
| `ModelClient` | Later | Send a bounded structured request to the configured model backend and return validated output with usage metadata ([REQ-10](spec.md#enduring-requirements)) |

There is no universal provider interface, plugin registry, or service framework. Later operations, such as experiments, converge on the same result model without pretending to be the same operation. A runtime-checkable protocol does not verify signatures or behavior, so static type checking and contract tests carry those obligations.

## Credentials

**Requirement (REQ-09, INV-11).** Credentials come from an injected source. For the CLI, the proposed default is these environment variables:

| Variable | Contents |
|---|---|
| `TRIALFOLIO_P123_API_ID` | Portfolio123 API ID |
| `TRIALFOLIO_P123_API_KEY` | Portfolio123 API key |

The CLI reads the variables and passes a credential object to the provider client. Credential objects are never serialized, hashed, logged, or written to artifacts.

The wrapper's error objects need the same care. The response attached to a `p123api` `ClientException` carries the `Authorization` header, and for authentication failures its request body contains the API key. The client's token accessor exposes the bearer token. Trial Folio never logs, serializes, or saves these objects. From an error it keeps only the status code and a sanitized message. Redaction tests seed canary values and check that they appear nowhere in the outputs or logs, including after an authentication failure.

Development credentials are handled as [AGENTS.md](../AGENTS.md#credentials-and-reference-data) describes.

## Logging and local diagnostics

**Requirements (REQ-06, INV-14).**

- **Local only.** No log handler, trace or metrics exporter, crash reporter, analytics call, or update check sends anything off the machine. The only outbound traffic is provider requests the user invokes or explicitly enables. Telemetry built into dependencies is disabled.
- **Content.** Logs never contain credentials, strategy definitions, formulas, configuration values, provider payloads, results, or input file contents, at any level. Artifacts are referenced by ID and hash instead. Validation errors are logged with `errors(include_input=False)`, or with `hide_input_in_errors` enabled, and logged tracebacks omit local variables.
- **Mechanism (proposed default).** The standard `logging` module, with no added dependency. Core modules use `logging.getLogger(__name__)` and never configure handlers; the CLI configures them.
- **Format.** Log files hold one JSON object per line with these snake_case fields: `timestamp` (UTC ISO 8601), `level`, `event` (a stable dotted name), `message`, `trialfolio_version`, `component`, and the applicable `review_id`, `plan_hash`, `case_id`, `attempt_id`, `request_id`, and `parent_id`. The terminal shows human-readable messages on stderr from the same events.
- **Levels.** ERROR for a failed operation, WARNING for a degraded condition the command continues through, INFO for lifecycle milestones, and DEBUG for diagnostic detail.
- **Tracing.** Start and end events carry duration and outcome for each command, case, attempt, and provider request, linked by IDs, and this serves as the trace. OpenTelemetry is adopted only through an ADR, with local file exporters only.
- **Metrics.** There is no metrics system. Per-run counts and durations go in the manifest.
- **Storage.** Logs go to `logs/` inside the output directory, or to a per-user local log directory for commands without one, such as `trialfolio license`. A command with an output directory holds its events in memory until it has [claimed the directory](#cli-behavior). If it stops before then, including when the claim fails, it writes no log file, and its messages appear only on stderr. The exception is `internal.unexpected`: the command then writes the held events to the per-user log directory, and its message names that file. Log size is bounded by rotation. The README documents the locations and how to delete them.

Initial event names: `cli.command.started`, `cli.command.completed`, `review.input.loaded`, `artifact.write.completed`, `report.render.completed`, `plan.created`, `plan.approved`, `attempt.started`, `attempt.completed`, `provider.request.started`, `provider.request.completed`, `provider.request.failed`, `case.completed`, `experiment.resumed`.

## Fixtures

**Requirement (REQ-11).** Committed fixtures are synthetic by default. A fixture that mirrors a verified provider layout copies its structure — column names, order, and formats — and never its data. Each fixture directory records:

- Its origin, and the layout version it mirrors.
- Its redistribution status.
- The requirements or acceptance criteria it exercises.

Expected outputs change only with a stated reason. Reference responses procured with the owner's account ([D-09](spec.md#decisions)) stay local and git-ignored unless Portfolio123's terms are confirmed to permit redistribution. No fixture, sample configuration, or sample export is copied from DataMiner or FactorMiner repositories.

## Pydantic conventions

- Pydantic v2 models define application-owned configuration, manifests, plans, attempt records, and later study protocols and assessments.
- Configuration models forbid unknown fields. Provider payloads are preserved whole as source artifacts, and normalized models cover only the supported subset.
- CSV and provider-specific units are parsed in named adapter steps before normalized models are validated. Validation bypasses such as `model_construct` are never used on untrusted input.
- Non-finite numbers are rejected. Unavailable values carry a reason, and ambiguous booleans, percentage strings, and date coercions are avoided.
- Cross-field rules are validators, for example date ordering, a baseline that names an existing result, and a benchmark-relative metric that requires a benchmark.
- Large tables stay in CSV (later, possibly Parquet), not in per-row models.
- Frozen models are used for plans and resolved configurations. Frozen models do not make nested mutable objects or saved files immutable; immutability on disk comes from the `ArtifactStore`.
- Pydantic is constrained to major version 2, and the tested dependency resolution is recorded.

## Schema generation and drift

JSON Schemas are generated from the models, never maintained by hand, and committed under `schemas/`. The generation mode, validation or serialization, is stated wherever the two differ. A check fails when committed schemas differ from freshly generated ones. Schemas do not encode every semantic validator, so the runtime semantics are tested separately.

## Open questions

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| Are failed screen-backtest requests charged? | Budget accounting for failed and uncertain attempts | Count them against the budget as possibly charged until verified | 0.1.0 reference call or live check |
