# Trial Folio contracts

**Status:** Draft. R01-T07 implemented 0.1.0's contracts as Pydantic models, generated schemas, and the screen configuration fixtures, R01-T08 the `ArtifactStore` and the output directory claim, R01-T09 the `ScreenBacktestClient` and its transport adapter, R01-T10 plans, canonical hashing, and approval, R01-T11 attempt recording, R01-T12 normalization and the normalized tables, and R01-T13 the report, its notices, and reading a saved run back for `trialfolio report`. Nothing else here is implemented yet.
**Date:** 2026-10-01

This document owns the meaning of Trial Folio's interfaces and artifacts: configuration files, saved artifacts, identifiers, metric values, errors, CLI behavior, reports, and logs. Pydantic models under `src/trialfolio/contracts/` define the executable structures, JSON Schemas generated from them under `schemas/` publish those structures, and tests with fixtures under `tests/fixtures/` provide conformance evidence. This prose stays authoritative for meaning. If a model accepts something this document says is invalid, the model has a defect.

Structures appear here as lists of concepts, not field-by-field schemas. Each release specification states which concepts it introduces and which schema versions it ships. Examples are illustrative until an implementation validates them.

## Public contract boundary

For semantic versioning, Trial Folio's public contract is:

- Documented CLI commands, options, exit codes, and stdout/stderr behavior.
- Configuration file formats.
- Machine-readable outputs: manifests, normalized CSV files, and `--json` summaries.
- The documented ability to read artifacts written by earlier versions.

Python functions are internal during 0.x.y development. A core function becomes public only when this section names it, which will be required before any separately distributed interface calls it. Log event names and fields are documented below but are not public contract.

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
| Provider library versions | The versions of `p123api`, `requests`, and `urllib3` used for provider requests ([plan contents](#plan-contents)) |
| Method versions | Version of each analytical method applied (when methods are introduced) |
| `license_id`, `notice_version` | The applicable license identifier (`LicenseRef-NSPRL-1.0`) and financial-notice version (`1.0`), defined in [../LICENSE](../LICENSE) and [disclaimers.md](disclaimers.md) |

A schema's version does not need to match the release that introduces it. Compatibility is defined against documented readers and semantics, not merely against added fields.

## Identity

Identifiers are introduced with the release that can define their semantics.

| Identifier | Introduced | Meaning | Form |
|---|---|---|---|
| `artifact_id` | 0.1.0 | Content address of one stored file | `sha256:<64 hex>` of the file's bytes |
| `review_id` | 0.2.0 | One `trialfolio review` output | Random UUID, version 4 |
| `label` | 0.2.0 | User-declared name of one compared result, unique within a review | `[a-z0-9][a-z0-9_-]{0,63}` |
| `plan_hash` | 0.1.0 | Identity of a plan, which execution requires as approval | `sha256:` of the plan's canonical form ([plan hashing](#plan-hashing)) |
| `case_id` | 0.1.0 | Stable identity of one fully resolved configuration | `case-` plus the first 16 hex digits of the SHA-256 of the canonical resolved settings ([plan hashing](#plan-hashing)) |
| `case_key` | 0.3.0 | User-declared readable name for a planned case | Same pattern as `label` |
| `attempt_id` | 0.1.0 | One execution attempt of a case | Random UUID, version 4, written in canonical form: lowercase, with hyphens |
| `experiment_id` | 0.3.0 | One declared experiment | User-declared slug, same pattern as `label` |
| `study_id`, `candidate_id`, `assessment_id` | Later | Defined when their increment is specified | — |

The forms of the identifiers 0.1.0 introduces are requirements since 0.1.0's sign-off (2026-10-01). The others are proposed until their release is Ready.

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
- Configuration never contains credentials. A credential-like key is rejected, at any depth. A key is credential-like when its name, ignoring case and reading `-` as `_`, contains `password`, `passwd`, `secret`, `token`, `credential`, `authorization`, `bearer`, `api_key`, `apikey`, `api_id`, or `apiid`.
- File paths inside a configuration are resolved relative to the configuration file.
- Duplicate keys are rejected; a YAML loader must not silently keep the last one.
- Non-empty text, wherever a configuration requires it, has a character that isn't whitespace: one of Unicode's White_Space characters.
- A file is UTF-8 text, with or without a byte-order mark, and holds one YAML document: a mapping whose keys are text, with no value nested more than 16 levels deep. Null values, anchors, aliases, and explicit tags are rejected. To omit an optional key, leave it out; don't write it empty. An optional text value, when present, must not be empty or all whitespace.
- Error messages name each offending key, and never include its value, so they're safe to log.

### Screen configuration

Schema version 1.0.0, introduced in 0.1.0 (task R01-T03). A screen configuration describes one long-only stock screen backtest, run through `p123api`'s `screen_backtest`. It covers only the settings in [0.1.0's scope](releases/0.1.0-api-execution.md#included-scope), as documented on Portfolio123's [API: Screen](https://portfolio123.customerly.help/en/articles/43324-api-screen) page, checked 2026-10-01.

**Keys:**

| Key | Type | Required | Rules | Sent as |
|---|---|---|---|---|
| `kind` | string | Yes | `screen` | Not sent |
| `schema_version` | string | Yes | A supported version (`1.0.0`). Any other value fails with `config.invalid`, and the message names the supported versions. | Not sent |
| `title` | string | Yes | 1–200 characters. Used as the report heading. | Not sent |
| `purpose` | string | No | 1–2,000 characters, not all whitespace. If it's absent, the report says no purpose was declared. | Not sent |
| `universe` | string | Yes | A non-empty Portfolio123 universe name, for example `SP500` | `screen.universe` |
| `rules` | list of strings | Yes | At least one screening formula. Each one is a non-empty string, and their order is kept. The model accepts ordered lists or tuples, never sets. | `screen.rules`, each as `{"formula": "…"}`. It has no `type` field, because Portfolio123 rejects one (R01-T01). |
| `ranking` | mapping | Yes | Exactly one of the [ranking forms](#ranking-forms) | `screen.ranking` |
| `max_holdings` | integer | Yes | 1 or more | `screen.maxNumHoldings` |
| `benchmark` | string | Yes | A non-empty Portfolio123 benchmark symbol, for example `SPY` | `screen.benchmark` |
| `start_date` | date | Yes | `YYYY-MM-DD` | `startDt` |
| `end_date` | date | Yes | `YYYY-MM-DD`, later than `start_date`. There is no default of today. | `endDt` |
| `rebalance_weeks` | integer | Yes | 1 or 4 | `rebalFreq`: `Every Week` for 1, or `Every 4 Weeks` for 4 |
| `transaction_price` | string | Yes | `open`. Required, so the price convention is always explicit. | `transPrice`: 1 |
| `slippage_percent` | decimal | Yes | 0 or more, in percent: `0.25` means 0.25%. There is no default of zero. | `slippage` |
| `pit_method` | string | Yes | `complete`, Portfolio123's point-in-time method | `pitMethod`: `Complete` |
| `precision` | integer | Yes | 4: the decimal places in results | `precision` |
| `data_vendor` | string | No | `FactSet` only ([D-16](spec.md#decisions)). Any other value, including `Compustat`, fails with `config.invalid`. | Never sent, because the endpoint documents no vendor parameter |

**Verified values.** Following [D-20](spec.md#decisions), the configuration accepts only values a recorded live call has verified. Free-form values, such as universe names, benchmark symbols, formulas, holdings counts, and slippage, are verified by form: R01-T01 sent one of each, and Portfolio123 accepted them.

- **Verified by R01-T01:** a formula ranking, `rebalance_weeks` 4, `open`, `complete`, precision 4, and a slippage sent as a JSON float, the form every slippage takes ([decimals](#screen-configuration)).
- **Verified by R01-T05:** `rebalance_weeks` 1, ranking by name, sent as a string, and ranking by ID, sent as a JSON integer, each in its own call ([run record](../reference/p123api-screen-backtest-values/README.md)).
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
  - **Integers** are plain decimal digits, with no leading zero, underscore, sign, or base prefix. So `010`, `1_000`, `+5`, and `0x10` are rejected. An integer is at most 9007199254740991 (2^53 − 1), the largest a JSON number keeps exactly, so canonical hashing stays exact. A larger one fails with `config.invalid`. A whole number of more than 16 digits is rejected as it's read, since no key takes one.
  - **Booleans** are `true` or `false`, and are never accepted where a number is expected, or the reverse.
  - **Dates** have no time part. So `2016-01-01 09:30:00` is rejected. A date may be a YAML date or a string in exactly `YYYY-MM-DD` form.
- **Decimals.** A decimal is read from its YAML text, never through binary floating point.
  - **Form.** It's written in plain notation: digits, optionally followed by a decimal point and more digits. There's no sign, exponent, or leading zero before another digit, so `2.5e-1`, `-0.25`, `.25`, and `00.25` are rejected. A whole number such as `0` or `1` is accepted.
  - **Normalization.** Before it's recorded, hashed, or compared, trailing zeros after the decimal point are removed, and then the point if no digits follow it. So `0.250` and `0.25` are the same setting, and so are `1.0` and `1`.
  - **Limits.** After normalization, it has at most 15 significant digits, at most 4 digits after the decimal point, and is less than 10^16. Leading zeros, and a whole number's trailing zeros, aren't significant: `1000000000000000` has one significant digit. A value outside these limits fails with `config.invalid`.
  - **On the wire.** Every decimal is sent as a JSON float, the type R01-T01 verified with `0.25`, never as an integer. `requests` writes the request body with Python's `json` module; Trial Folio refuses to run where `requests` would use `simplejson` instead ([plan contents](#plan-contents)). `json` writes a float in its shortest round-trip form. So the JSON text of a decimal is its normalized form, with `.0` added to a whole number:
    - **A whole number,** such as `1` (1%), is sent as `1.0`.
    - **Any other value,** such as `0.25` (0.25%, or 25 basis points), is sent with exactly its digits. Most values, such as `0.1`, have no exact binary form. But a value of up to 15 significant digits survives the round trip through binary floating point: its shortest round-trip form has exactly its digits.
    - **No exponent.** `json` writes a float with an exponent below 0.0001 or from 10^16 up, for example `0.00001` as `1e-05`. R01-T01 verified only plain notation, and the limits keep every value in it.
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
- **Other columns.** `original_key` and `original_value` come from the configuration, and are empty for rows that no key supplies. For row 16 they're filled only when the configuration gives `data_vendor`. `inference_rule` cites the decision or documentation and the date the documentation was checked. Its text for rows 14, 16, and 18 is fixed in `src/trialfolio/contracts/screen_settings.py`. A plan holds it, so changing it changes the plan hash.
- **Coverage.** `start_date` and `end_date` also carry `coverage_mismatch` when the response's coverage differs from them ([coverage](#p123api-screen-backtest-version-1)).
- **Flags.** Each row carries the flags the table gives it, and only those, apart from `coverage_mismatch` on the date settings.

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

Once implemented, a test repeats the second check: `tests/contract/test_screen_configuration.py::test_documented_example_resolves_to_reference_request` ([0.1.0's test pairing](releases/0.1.0-api-execution.md#test-pairing)).

### Review configuration

Schema version 1.0.0, introduced in 0.2.0. It names saved runs written by `trialfolio run`.

**Top-level keys:**

| Key | Type | Required | Rules |
|---|---|---|---|
| `kind` | string | Yes | `review` |
| `schema_version` | string | Yes | A supported version (`1.0.0`). Any other value fails with `config.invalid`, and the message names the supported versions. |
| `title` | string | Yes | 1–200 characters. Used as the report heading. |
| `purpose` | string | No | 1–2,000 characters, not all whitespace. If it's absent, the report says no purpose was declared. |
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

Introduced in 0.1.0 (task R01-T02). Portfolio123 doesn't document the response fields, so everything below is a verified observation of the reference response in [`reference/p123api-screen-backtest/`](../reference/p123api-screen-backtest/README.md). The response itself stays git-ignored. The run record there holds the checks behind each "reproduced" statement. R01-T05's three responses, with weekly rebalancing and with rankings by name and by ID, have the same keys and structure ([run record](../reference/p123api-screen-backtest-values/README.md)). A definition marked "not reproduced" is Portfolio123's own, and Trial Folio reports the value as given.

**Identity.**

- The layout is the decoded JSON body that `p123api`'s `screen_backtest(params, to_pandas=False)` returns for `POST /screen/backtest`. It was observed with `p123api` 3.1.0.
- The response carries no version of its own. Trial Folio labels a response version 1 when it has the required structure below.
- Trial Folio's adapter for it, in `src/trialfolio/normalization.py`, is parser version 1 (R01-T12). The manifest records it with the layout's version.

**Required structure.** A response without it is saved, and the result is flagged `provider.response_invalid`:

- The top level is an object with `stats` and `results` objects.
- `stats` has `port` and `bench` objects.
- `results.columns` is an array of strings. `results.rows` is an array of arrays, each as long as `columns`.

Nothing else is required. Extra keys, or a missing `chart` or summary row, don't make a response invalid. Individual values fail as follows:

- **A metric key that is missing, or whose value is `null`,** makes that metric unavailable with `blank_in_source`. A value that isn't a JSON number is unavailable with `unparseable_in_source`. That includes `NaN` and `Infinity`, which `response.json` can hold ([writing the files](#execution-outcomes-and-attempts)).
- **Coverage dates.** If `results.rows` is empty, or `columns` lacks `Tran Dt` or `End Dt`, then `coverage_start` and `coverage_end` are unavailable with `blank_in_source`. A date that isn't `YYYY-MM-DD` is `unparseable_in_source`. `coverage_periods` is always the number of rows, including zero.
  - **Every row counts.** The earliest or latest date is known only when every row has one, so if any row's `Tran Dt` isn't a `YYYY-MM-DD` calendar date, `null` included, `coverage_start` is `unparseable_in_source`, and the same holds for `End Dt` and `coverage_end`.
  - **Dates that contradict each other.** If the earliest `Tran Dt` is after the latest `End Dt`, neither can be the coverage, and both are `unparseable_in_source`.

**Numbers and precision.**

- The wrapper decodes JSON numbers into binary floating point. Trial Folio saves each one in its shortest round-trip form. For values of up to 15 significant digits, that form keeps every digit the provider sent except trailing zeros.
- Trial Folio reads numbers from the saved text as decimals, never as binary floats. A value keeps exactly the digits it has there, and `source_decimals` is the number of digits after its decimal point.
- A value can therefore carry fewer decimal places than the request's `precision`. The reference response was requested at 4, and its `stats.port.standard_dev` has 3. Trial Folio doesn't pad it back to 4.
- **Exponents.** `json` writes a float below 0.0001, or from 10^16 up, with an exponent. Such a value is written in plain notation, with the digits that gives, so `1e-05` is `0.00001`, with 5 decimal places.
- **Counts.** `risk_samples` is a whole number, 0 or more, written with its digits alone, so `118.0` is written `118`. A fraction or a negative value is `unparseable_in_source`.
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
- `coverage_mismatch` flags a difference between coverage and the requested `startDt` or `endDt`. It appears on the date settings in `settings.csv`, which R01-T03 names. In the reference response, coverage equals the requested dates. Each date setting is compared with its own coverage date. When that coverage date is unavailable, nothing is compared: the setting isn't flagged, and the report says the coverage couldn't be established, rather than showing it as matching.

**Preserved but not interpreted in 0.1.0:**

- **`cost` and `quotaRemaining`** are integers: the credits charged and the credits left. The attempt record keeps them as provider metadata. `quotaRemaining` is account information, so it's kept out of `metrics.csv`, the report, and the JSON summary.
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

- **`results.average`, `results.upMarkets`, and `results.downMarkets`.** Each is one element shorter than `columns`: element *i* belongs to `columns[i+1]`. Element 0 is `null`. In `upMarkets` and `downMarkets`, element 1, under `Rank Dt`, holds the number of periods in the group. The other non-null elements are means of their column: over all periods, over the periods whose `Bench%` is zero or above, and over the rest. R01-T01's response has no period at zero. R01-T05's weekly response verifies the zero case ([run record](../reference/p123api-screen-backtest-values/README.md)). Its first period, from 2016-01-01, a market holiday, to 2016-01-04, has the same benchmark level in `chart` on both dates and a `Bench%` of `0`, and it's counted in `upMarkets`. The wrapper's `to_pandas=True` conversion appends these arrays as table rows without the offset, which moves each value one column to the left. Trial Folio doesn't use that conversion ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md), decision 4).
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
- **Schemas.** `schemas/metrics-row-1.0.0.schema.json` and `schemas/settings-row-1.0.0.schema.json` each describe one row, after a CSV adapter step has read its cells: an empty cell is `null`, `critical` is a boolean, `source_decimals` is an integer, the period dates are dates, and `flags` is an array of codes. A property's position is its column's.

**Writing and reading them.** `src/trialfolio/normalization.py` normalizes a saved response, and `src/trialfolio/tables.py` writes the tables and reads them back (R01-T12):

- **Which runs have them.** A run's tables are written only from a decoded response with the [required structure](#p123api-screen-backtest-version-1): `normalized/metrics.csv`, then `normalized/settings.csv`. A response saved undecoded, as `response.raw`, or without that structure, is `provider.response_invalid`, and neither table is written: the normalized result is unavailable. An attempt that didn't succeed has no response to normalize, and no tables.
- **The label.** A run's rows carry its case's `case_id` as their `label`: the identity of the resolved settings, which the attempt's directory names too. So two runs of the same configuration label their rows the same.
- **Reading.** A file that isn't a valid table, because of its encoding, a byte-order mark, its header, its quoting, or a row's cells, is `input.not_a_run`. The message names the line the row starts on, since a quoted cell can span lines, and the column, never a value.

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
| `original_value` | The value exactly as written in the source. Empty when absent. In the row model, absent is `null`, never an empty string; `original_key` and `original_value` are present or absent together. |
| `source_artifact` | `artifact_id` of the saved screen configuration |
| `flags` | Flag codes, separated by semicolons. Empty when none apply. |

For a screen run:

- **`original_key`** is the configuration's top-level key, which is the setting's name.
- **`original_value`** is the value's text in the configuration file: from its first character to its last one that isn't YAML white space or a line break. So it keeps quotes and block indicators, as in `0.250` and `'2016-01-01'`. A block list or mapping keeps its line breaks, its indentation, and any comment between its items, but not one after its last item.
- **`value`** writes a list or a ranking as JSON, with `", "` and `": "` between items and non-ASCII text as it is: `["AvgDailyTot(30) > 1000000"]`.

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

An attempt has two records in its directory, `cases/<case_id>/attempts/<attempt_id>/`. Each is written once and never replaced ([atomic writes](#artifact-storage)):

- **The start record, `started.json`,** is written durably just before the request is sent. It holds the `attempt_id`, the `case_id`, the `plan_hash` it runs under, the start time, the installed versions of `p123api`, `requests`, and `urllib3`, and the one [HTTP exchange](#http-exchanges) completed before it: Trial Folio's successful authentication call. An attempt whose authentication fails, or that ends before authenticating, has no start record.
- **The attempt record, `attempt.json`,** is written once, when the attempt ends. It holds everything in the start record, plus the end time, the outcome, any error code, all the exchanges and whether the attempt is `possibly_charged`, references to the redacted request and the saved response, provider metadata, and any charge or quota information the provider returned.

An attempt with a start record and no attempt record is `running` ([uncertain completion](#uncertain-completion)).

**Field shapes.** Both records name the installed versions as the plan does, in `provider_wrapper` and `transport` ([plan contents](#plan-contents)). In the attempt record:

- **`outcome`** is `succeeded`, `failed`, or `unknown`. `running` is how a start record without an attempt record reads; it's never written. The outcome follows the request's exchange, as [0.1.0's failure table](releases/0.1.0-api-execution.md#failure-and-incomplete-data-behavior) gives it: with no request exchange, `failed`, or `unknown` for a restart without a saved response; `not_connected`, `failed`; `interrupted` or a 5xx, `unknown`; a 200, `succeeded` when its response was saved and `unknown` otherwise; any other status, `failed`. The request is sent at most once, so it has at most one exchange, and a start record holds only the authentication exchange.
- **Authentication in 0.1.0.** A start record holds exactly one successful authentication exchange (`response`, status 200). An attempt record holds at most one authentication exchange, before any request exchange. Failed authentication is valid only in a failed attempt with no request exchange. An attempt may fail before authentication starts, with no exchanges. Sending a request, or recording its uncertain completion on restart, requires successful authentication.
- **`error`** is `{"code": …, "message": …}`, and `null` exactly when the outcome is `succeeded`.
- **`request` and `response`** reference files by `path`, relative to the output root, and `artifact_id`. A request exchange requires a reference to its saved `request.json`, including when the connection failed. `response.form` is `decoded` for `response.json`, or `undecoded` for `response.raw`. A response is referenced exactly when the attempt is `succeeded`, decoded or not: a 200 the wrapper couldn't decode is `succeeded` for capture.
- **`provider_metadata`** holds `cost` and `quota_remaining`, Portfolio123's `quotaRemaining`. Each is `null` when the response doesn't carry it.
- **`possibly_charged`** is true exactly when the attempt is `unknown`, or an exchange other than Trial Folio's `POST /auth` has a result other than `not_connected` ([possibly charged](#http-exchanges)). An attempt restarted without a saved response is `unknown` with only its start record's exchanges ([uncertain completion](#uncertain-completion)).

`schemas/start-record-1.0.0.schema.json` and `schemas/attempt-record-1.0.0.schema.json` give every field.

**Writing the files.** `src/trialfolio/attempts.py` writes an attempt's files (R01-T11). After Trial Folio's authentication call succeeds, it writes them in this order:

1. **`request.json`.** It's the request's `params`, which hold no credentials, as Python's `json.dumps` writes them, indented. `requests` writes the request body with the same function, unindented. So each number's text is the body's, and non-ASCII text is escaped, as it is in the body. It comes before the start record, so the start record is the last write before the send, and an attempt restarted with a saved response has a request to reference.
2. **`started.json`.** Then the request is sent.
3. **`response.json` or `response.raw`.** `response.json` is the decoded value as `json.dumps` writes it, on one line. Unindented, `json` writes with its C encoder, which nests as deep as the C decoder that read the value; the Python encoder that indenting uses could run out of recursion first. Non-ASCII text is escaped, so a lone surrogate the decoder accepted is written back as it came. So are `NaN` and `Infinity`.
4. **`attempt.json`,** whatever ended the attempt.

An attempt that ends after the claim and before it authenticates, such as after an interrupt, or a failure to write `configuration.yaml`, writes only its attempt record.

- **`provider_metadata`** takes `cost` and `quotaRemaining` from the top level of a decoded response. A value that's absent, or isn't a non-negative integer, is `null`.
- **An interrupt while the attempt record is written.** If the record was published whole, it's left as it is. Otherwise it's written once more, with `command.interrupted` as its error code, unless the attempt succeeded. An interrupt during that second write ends the command, and the start record, if there is one, reads as `running`.
- **An error that decides the code keeps the message of the one it overrides,** after "Before that:". So a record whose code is `command.interrupted` after a 400 still holds Portfolio123's message.
- **An unexpected exception** ends the attempt like any other ending: the exchanges give the outcome, and the code is `provider.outcome_unknown` when the outcome is `unknown`, and `internal.unexpected` otherwise. Its code wins over a provider error's, but not over an interrupt's or a storage failure's ([endings that decide the error code](#endings-that-decide-the-error-code)). Its message names only its type, never its own message, which could hold a value. The log gives its type and its frames (`attempt.unexpected`).

Trial Folio saves decoded provider payloads, which is what the wrapper exposes, and labels them as decoded payloads. It doesn't capture HTTP headers, and it keeps a raw body only in one case: a 200 the wrapper can't decode, which it saves as `response.raw`, labeled undecoded ([HTTP exchanges](#http-exchanges)). Trial Folio configures the wrapper for a single HTTP attempt per call, and its adapter allows one exchange per call, as below. So the request is sent at most once, and running the command again is a new attempt.

### HTTP exchanges

Trial Folio mounts its own transport adapter on the wrapper's HTTP session, for both `https://` and `http://`, so every request the wrapper makes passes through it ([ADR 0006](adrs/0006-observe-the-wrappers-http-exchanges.md)). The adapter records each exchange in memory, in order. The start record keeps the exchanges completed before it, and the attempt record keeps them all:

| Field | Contents |
|---|---|
| `request` | The method and path, for example `POST /auth` or `POST /screen/backtest`. The path leaves out any query, which could carry data. |
| `result` | `response`: a complete response arrived. `not_connected`: the connection provably never opened, so nothing was sent. `interrupted`: no complete response arrived, and the connection can't be shown never to have opened, so the request may have reached Portfolio123. |
| `status` | The HTTP status of a `response`. `null` otherwise. A status outside 100 to 599 isn't an HTTP status ([RFC 9110, section 15](https://www.rfc-editor.org/rfc/rfc9110#section-15)), so an exchange that gets one is `interrupted`: no complete response arrived. |
| `note` | `completed_from_saved_response` on the request's exchange of an attempt restarted with a saved response, recorded as a `response` with status 200 ([uncertain completion](#uncertain-completion)). `null` otherwise, and always in a start record. |

- **Not connected means provably not sent.** An exchange is `not_connected` only when the `requests` error wraps a `urllib3` `MaxRetryError` whose `reason`, after unwrapping a `urllib3` `ProxyError` to its `original_error`, is a `ConnectTimeoutError`. That class covers a failed name lookup (`NameResolutionError`), a refused or unreachable connection (`NewConnectionError`), and a connect timeout. 0.1.0 uses no proxy ([credentials](#credentials)); unwrapping a `ProxyError` keeps the rule right if a later release adds one. It's the test `urllib3`'s `Retry` applies, in `_is_connection_error`, to decide that a request is safe to retry because the server didn't receive it. Every other ending without a complete response is `interrupted`, including a reset, a read timeout, a TLS failure, and an interrupt during the name lookup. So an unclear case counts as possibly sent.
- **Recorded before sending.** The adapter adds each exchange to the list before it sends, and fills in the result afterwards. An exchange still without a result when the attempt record is written, for example after Ctrl-C, is `interrupted`. An exchange that already has a result keeps it.
- **The body is read inside the adapter.** A body that breaks off is therefore recorded as `interrupted`.
- **Nothing else is recorded,** with one exception. The adapter keeps no headers, tokens, or exception objects, and no bodies, except the body of a 200 on the request's exchange, which it holds in memory. If the wrapper can't decode that body, Trial Folio saves it as `response.raw`, labeled undecoded, so the evidence is kept ([INV-01](spec.md#enduring-invariants)). The wrapper couldn't decode it when the request's call raised anything after the 200, not only a `JSONDecodeError`: JSON nested too deeply for the decoder raises `RecursionError`, for example. An authentication body holds the token, so it's never kept. The adapter changes no request or response, and passes every error on unchanged.
- **One exchange per call.** Each call to the wrapper, whether Trial Folio's own authentication call or the request's call, makes exactly one exchange. The adapter refuses any further exchange during the same call before connecting, whatever its path, by raising an error of Trial Folio's own type. The wrapper catches only `requests.ConnectionError`, so that error ends the call. A refused exchange sent nothing, so it isn't recorded, and the adapter logs `provider.request.refused`. An exchange outside any call is refused the same way. The rule refuses, without depending on how either is triggered:
  - **The wrapper's resend.** After a 401 or 403, the wrapper re-authenticates and resends the request ([retry policy](#budget-and-retries)). Its `POST /auth` is a second exchange, so it's refused, and the request isn't resent.
  - **A redirect.** `requests` follows a 301, 302, 303, 307, or 308 that has a `Location` header by sending the next request through the same session, and so through the adapter. That's a second exchange, so it's refused. Any other 3xx is an ordinary response. Either way, the exchange records the 3xx as a `response`.
- **No retries inside an exchange.** The adapter keeps `requests`' default `urllib3` retry setting, `Retry(0, read=False)`, so `urllib3` never resends within one exchange.
- **Timeouts.** Trial Folio sets the request's timeout to 300 seconds with the wrapper's `set_timeout(300)`. That's the wrapper's own default, set explicitly so that a wrapper upgrade can't change it unnoticed. The wrapper fixes the authentication call's timeout at 30 seconds. `set_timeout` takes whole seconds, so the shortest timeout is 1 second. Tests set it through the CLI's entry function ([credentials](#credentials)), and the installed command always uses 300 seconds. A connect timeout ends the exchange as `not_connected`, and a read timeout as `interrupted`.
- **When Trial Folio authenticates.** It authenticates with a call of its own before the first request, and again before a later request only when an earlier one got a 401 or 403, because the wrapper then drops its token. So the first exchange of an attempt is either its own `POST /auth`, or the request itself, sent with the token already held. In 0.1.0, with one request, every attempt starts with Trial Folio's own `POST /auth`.
- **Possibly charged.** This is the one definition the budget, the counts, and the failure behavior use. A send of the request may have reached Portfolio123, and so counts as possibly charged, when its exchange has a result other than `not_connected`, whatever its status or outcome. An attempt is `possibly_charged` when its request's exchange is such a send, or when it's `running` ([uncertain completion](#uncertain-completion)). Authentication isn't counted ([budget](#budget-and-retries)).
- **Classification.** Trial Folio classifies an attempt from its exchanges, and from whether the call returned a decoded response. A 200 the wrapper decodes and one it can't decode give the same exchanges, and only the call's return tells them apart. Trial Folio never reads the wrapper's exception object beyond its type and message: it takes only a sanitized message ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md), decision 7). When the adapter refused a second exchange, the call ends with Trial Folio's own error, which carries no Portfolio123 text. The message then names the status of the call's exchange, and says why the next exchange was refused: a re-authentication after a 401 or 403, or a redirect. [0.1.0's failure behavior](releases/0.1.0-api-execution.md#failure-and-incomplete-data-behavior) maps each situation to an outcome and an error code.

### Uncertain completion

Trial Folio authenticates first, when it [needs to](#http-exchanges), then writes the start record durably, and only then sends the request.

- **Authentication fails.** There's no start record. The attempt record is written as `failed`, because the request wasn't sent. Authentication isn't counted in the budget's credits ([budget](#budget-and-retries)).
- **A start record without an attempt record** is `running`. Its request is sent at most once, so a reader counts it as one possible send: `possibly_charged`, and one provider request. On restart, as in 0.3.0's resume, Trial Folio writes its attempt record, and rewrites nothing:
  - **With a saved response.** A `response.json` or `response.raw` in the attempt's directory is complete, because it's published atomically ([atomic writes](#artifact-storage)), and either is saved only after a 200. So the attempt record is written as `succeeded`, with the request's exchange recorded as a `response` with status 200 and the note `completed_from_saved_response`. A `response.raw` is flagged `provider.response_invalid`, as it would have been.
  - **Without one.** The attempt record is written as `unknown`, possibly charged, with one provider request. Its exchanges are the start record's: the request's exchange was never recorded.
- **An `unknown` attempt** is never retried automatically, because the original request may have been charged or may have changed provider state. `unknown` always means that no response was durably recorded.

### Endings that decide the error code

Two kinds of ending decide the command's error code, whatever the exchanges show:

- **A user interrupt,** such as Ctrl-C: `command.interrupted`, exit 130 ([interrupts](#interrupts)).
- **A storage failure:** `storage.write_failed`, exit 4. For example, the request got a 200, and then writing `response.json` failed.

If both happen, the interrupt's code wins. Either way, the exchanges still decide the attempt's outcome and whether it's `possibly_charged`, as the [0.1.0 failure rows](releases/0.1.0-api-execution.md#failure-and-incomplete-data-behavior) give them, with an exchange still in flight counted as `interrupted`. A 200 whose response wasn't saved durably is `unknown`. Trial Folio writes the attempt record if it still can, with that outcome, and with the overriding code as its error code unless the outcome is `succeeded`. If it can't, the start record is left, and reads as `running`.

### Interrupts

A user interrupt, such as Ctrl-C, reaches Trial Folio as an exception it can catch, and [decides the error code](#endings-that-decide-the-error-code). What the command leaves depends on when the interrupt arrives:

- **Before the claim succeeds.** The command removes what the claim created, as a [failed claim](#cli-behavior) does, so nothing is left.
- **After the claim, before authenticating.** The attempt record is written as `failed`, not possibly charged, so the planned case is accounted for ([INV-07](spec.md#enduring-invariants)). Without a manifest, the output is visibly incomplete.
- **During authentication, or before the request's send starts.** The attempt record is written as `failed`, not possibly charged.
- **During the request's send, or after it.** The attempt record is written with the outcome the request's exchange gives: `unknown` and possibly charged while the send is in flight.
- **After the attempt record is written.** It isn't changed.

A process that's killed, for example with `SIGKILL` or by a power loss, can't record anything. A start record it leaves is `running`, as above. If it's killed before the start record is written, there's no record of the attempt.

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
| `provider_wrapper` | `p123api` and its installed version, which will send the requests. The retry policy describes that version's behavior. So Trial Folio plans only with a version a release has verified: 3.1.0 for 0.1.0 ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md#verification-notes)). Any other installed version fails with `environment.unsupported` before the plan is shown. The package pins the verified version exactly, so a clean install gets it, and a test checks that the pin is in the verified list ([ADR 0006](adrs/0006-observe-the-wrappers-http-exchanges.md)). This row and the next own the verified versions; other documents link here. |
| `transport` | `requests` and `urllib3` and their installed versions. Trial Folio's adapter relies on how they raise errors, send a redirect through the session, and retry within one exchange ([HTTP exchanges](#http-exchanges)), so the same rules apply as for `provider_wrapper`: Trial Folio plans only with verified versions, `requests` 2.34.2 and `urllib3` 2.8.0 for 0.1.0, and the package pins them exactly. Trial Folio also requires `requests` to write request bodies with the standard library's `json`. `requests` switches to `simplejson` whenever that's importable (`requests.compat`), and the [decimals rules](#screen-configuration) are verified only for `json`. So an environment where `simplejson` is importable fails with `environment.unsupported` too. **Reading the versions:** Trial Folio reads each installed version with `importlib.metadata.version`. The imported `requests` and `urllib3` modules also carry `__version__`, which must equal it, so a stale `.dist-info` can't hide other code. `p123api` carries none. |
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

**The 0.1.0 request.** Its `operation` is `screen_backtest`: `p123api`'s `screen_backtest`, which sends `POST /screen/backtest`. Its `params` is the JSON object passed to the wrapper, exactly as it will be sent. Its numbers are JSON numbers, in the form the [decimals rules](#screen-configuration) give, so a whole-number slippage is the float `1.0`, never the integer `1`, and the request body's text for each number equals its text in `params`. Each parameter's JSON type is fixed: `slippage` is always a float, and the other numbers are always integers. So the plan hash, which covers the values, also fixes the text sent, although RFC 8785 writes `1.0` as `1` ([canonical hashing](#canonical-hashing)). It holds no credentials; the wrapper sends those separately.

**Settings in the plan.**

- **Values keep their JSON types.** Integers are numbers, decimals are normalized decimal strings, dates are `YYYY-MM-DD` strings, lists are arrays, mappings are objects, and tokens such as `not_sent` are strings. `flags` is an array of codes, empty when none apply. Any other column that `settings.csv` leaves empty is `null`.
- **Expected provenance.** Nothing in a plan has been sent yet, so no value in it is `verified` ([provenance](#provenance)). Instead, each row records `expected_provenance`: the provenance the value will have once the request is sent. Values in the request expect `verified`. `settings.csv` records the actual provenance after the attempt.
- **Flags known before execution.** These are `inferred_default` and `not_snapshotted`. `coverage_mismatch` needs the response, so it appears only in `settings.csv`.
- **No trace of how the file was written.** The four columns left out depend on how the configuration file is written. So two files that resolve to the same settings give the same plan, for example an omitted `data_vendor` and an explicit `FactSet` ([D-16](spec.md#decisions)), or `0.250` and `0.25`.

**Consistency.** A case's request is what its settings send, by the screen configuration's "Sent as" mapping, and each setting's `expected_provenance` and `flags` are the ones the [screen settings](#screen-settings) give it. `slippage` is a JSON float, never an integer, and never `-0.0`. A plan that breaks any of these is invalid.

**Field shapes.** `provider_wrapper` is `{"p123api": "<version>"}`, and `transport` is `{"requests": "<version>", "urllib3": "<version>"}`. The budget records its documented cost's source in `credits_per_request_source`, with the page's `title`, its `url`, and the date it was `checked`. A 1.0.0 plan has one request, so its `provider_requests` and `authentication_calls` are 1. Its `credits_per_request` is whatever cost the documentation gave when the plan was made, so a plan stays valid if Portfolio123 changes it; `credits` must equal `provider_requests` times `credits_per_request`. Each `data_sent` entry has a `category`, the `recipient`, `Portfolio123`, `via`, `p123api`, and `settings`, the names of the settings it carries, in the [screen settings](#screen-settings)' order, which is empty for `credentials`. The entries are in the order [data sent](#data-sent) lists them. `schemas/plan-1.0.0.schema.json` gives every field.

### Budget and retries

**Budget.** The values for 0.1.0:

| Field | Value |
|---|---|
| `provider_requests` | 1: the most times Trial Folio sends a provider request. The request is sent at most once ([HTTP exchanges](#http-exchanges)), so this is also the worst case. |
| `credits_per_request` | 5: Portfolio123's documented cost of a screen backtest. The plan records the source, [API: Screen](https://portfolio123.customerly.help/en/articles/43324-api-screen), and the date it was checked, 2026-10-01. |
| `credits` | 5: `provider_requests` times `credits_per_request`, the most credits the request can use at the documented cost. Authentication isn't included. |
| `authentication_calls` | 1: the most authentication calls the plan makes ([when Trial Folio authenticates](#http-exchanges)). Portfolio123 doesn't document their cost, so `credits` leaves them out, and this field bounds them instead, including in a later release with several requests. |

- **What counts.** Every send that may have reached Portfolio123 counts, whatever its status or outcome, because whether failed requests are charged is unverified. A send that's `not_connected` didn't reach it, and doesn't count ([possibly charged](#http-exchanges)).
- **Within budget.** A run or experiment is within its budget when its `provider_requests` count, the sends that may have reached Portfolio123 ([JSON summary](#json-summary)), is at most the budget's `provider_requests`. Execution never starts a send that would exceed it, and never makes more authentication calls than `authentication_calls`.
- **Authentication's cost.** Trial Folio authenticates through the wrapper's `POST /auth` before the first request, and again only after a 401 or 403. Portfolio123's [API credits](https://portfolio123.customerly.help/en/articles/13766-api-credits) page doesn't say whether that costs credits (checked 2026-10-01). The two authentications that R01-T05's live checks could measure, the second and third, cost none ([run record](../reference/p123api-screen-backtest-values/README.md)). That's an observation, not a documented price, so `credits` leaves authentication out, and the budget states the most authentication calls instead. The plan display says that authentication's cost isn't documented, and that it cost no credits when last measured.
- **The documented cost, not the charge.** The budget uses the documented cost. The attempt records the `cost` Portfolio123 reports.

**Retry policy.**

| Field | Value |
|---|---|
| `automatic_retries` | 0. Trial Folio never resends a request on its own. Running the command again is a new attempt. |
| `wrapper_attempts_per_call` | 1. Trial Folio sets the wrapper to one HTTP attempt per call, with `set_max_request_retries(1)`, for authentication and for the backtest. |
| `exchanges_per_call` | 1. Trial Folio's adapter refuses any second exchange in a call before connecting ([HTTP exchanges](#http-exchanges)). That refuses the wrapper's re-authentication and resend after a 401 or 403, which the pinned `p123api` 3.1.0 always attempts and no setting disables ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md#verification-notes)), and any redirect `requests` would follow. |

### Data sent

`data_sent` lists each category of data that leaves the machine. All three categories below appear exactly once, each carrying exactly its documented settings, with no repeated setting names. Each entry names its recipient, Portfolio123, through `p123api`, and the settings it carries, if any:

| Category | Contents |
|---|---|
| `credentials` | The API ID and key, sent to authenticate. They're never recorded. |
| `strategy_definition` | The universe, the rules, and the ranking: its formula, or a ranking system's name or ID |
| `backtest_settings` | The holdings, benchmark, dates, rebalance frequency, transaction price, slippage, point-in-time method, and precision, plus the fixed type, method, and currency |

These are categories of data, not the setting categories of `settings.csv`. Nothing else is sent: not the title, the purpose, `data_vendor`, the configuration file, file paths, earlier results, or logs.

### Plan hashing

- **The plan hash** is `sha256:` plus the hex SHA-256 of the [canonical form](#canonical-hashing) of the plan without its `plan_hash` field.
- **The case ID** is `case-` plus the first 16 hex digits of the SHA-256 of the canonical form of the case's `settings`, with each row reduced to `setting`, `value`, and `unit`. Changing any resolved setting changes it. The title, the purpose, and how the file is written don't.
- **Nothing varies between invocations.** The plan holds no timestamps, output directory, file paths, attempt IDs, credentials, or account information. So the same configuration, Trial Folio version, and versions of `p123api`, `requests`, and `urllib3` give the same plan and hash on any machine, at any time, and for any output directory. That's what lets a user review a plan in one command and approve it in the next.
- **Any change needs a new approval.** That includes a changed setting, title, purpose, budget, Trial Folio version, or version of `p123api`, `requests`, or `urllib3`. So after upgrading any of them, the same configuration needs approving again.
- **Saved plans are checked.** A reader recomputes the hash of a saved `plan.json`. If it differs from `plan_hash`, the run is invalid (`input.not_a_run`).

### Approval

The core recomputes a plan's hash from its contents, and executes the plan only when it's given a hash equal to that. It never trusts a stored `plan_hash` field. Otherwise it fails with `plan.approval_required` and sends nothing. The CLI gets the hash in one of two ways:

- **`--approve <plan-hash>`, for non-interactive use.** The value must be the full hash exactly as shown: `sha256:` and 64 lowercase hex digits. An abbreviated, malformed, or different hash doesn't match. With `--approve`, the CLI never asks for approval. The license acknowledgment is separate, and comes first ([order of steps](#approval)).
- **Interactive confirmation.** Without `--approve`, when stdin and stderr are both terminals, the CLI shows the plan and asks the user to type `approve`. It then passes the hash of the plan it showed. The answer is the line typed, without its line ending, and must be exactly `approve`: lowercase, with nothing before or after it. Any other answer, an empty line, or the end of input is a refusal.

Without a match, the command fails with `plan.approval_required`, exit 2, and creates no output. The plan hash has been shown, with the full plan on a terminal, and the message gives the exact option that approves this plan. So running without `--approve` from a script gets the hash without sending anything, and with `--json`, the summary's `ids` carry the `plan_hash`.

**The plan display.** The CLI writes it to stderr directly, never through logging, because it contains configuration values and formulas ([logging](#logging-and-local-diagnostics)). For the same reason, it shows the full plan only when stderr is a terminal: when it asks for confirmation, and when approval fails. When stderr isn't a terminal, as in a script or a CI job whose output may be kept, it shows only the plan hash and the budget, and says that running the command in a terminal shows the full plan. With a matching `--approve`, the plan is already approved, so it also shows only the plan hash and the budget. The full plan shows:

- the title and purpose
- the request exactly as it will be sent
- every resolved setting with its expected provenance, marking inferred defaults, settings not snapshotted, commission not modeled, and parameters not sent
- the budget, that a request that reaches Portfolio123 may be charged even if it fails, and the most authentication calls, whose cost isn't documented, and which cost no credits when last measured
- the retry policy
- the data sent, its recipient, and what isn't sent
- the plan hash, and how to approve it

Text from the configuration is shown with its control and formatting characters, Unicode's categories Cc and Cf, and the line and paragraph separators, written as escapes such as `\u001b`, so a title or formula can't move the cursor, clear the terminal, or reorder what's shown.

**Order of steps in `trialfolio run`.** Trial Folio creates no output and sends no request before step 7. So a plan can be reviewed, and its hash obtained, without credentials.

1. Check the license acknowledgment (`license.not_acknowledged`).
2. Validate the configuration (`config.invalid`).
3. Check that the output directory is absent or empty (`output.not_empty`).
4. Check that the installed `p123api`, `requests`, and `urllib3` are verified versions, and that `requests` would write request bodies with `json` ([plan contents](#plan-contents); `environment.unsupported`). Build the plan and show it, as [the plan display](#approval) says.
5. Check the approval (`plan.approval_required`).
6. Check that credentials are present (`provider.auth_failed`).
7. [Claim the output directory](#cli-behavior) with `plan.json` (`output.not_empty`). Logging to `<out>/logs/` starts only after the claim succeeds ([logging](#logging-and-local-diagnostics)). Write `configuration.yaml`, from the bytes read in step 2. That's the first [atomic write](#artifact-storage), so a file system that can't take one fails here, with `storage.write_failed`, before any request.
8. Authenticate with Trial Folio's own call. If that fails, write the attempt record as `failed` and stop ([uncertain completion](#uncertain-completion)). An interrupt after the claim and before the request's send starts writes it as `failed` too ([interrupts](#interrupts)).
9. Write the start record durably, together with the directories that hold it ([syncing](#artifact-storage)), and send the request. Write the attempt record when the call ends.

**Records.**

- **The start record and the attempt record** name the `plan_hash` the attempt ran under.
- **The manifest** records the `plan_hash` and how it was approved: `interactive` or `option`.
- **Logs** record the plan hash and the case ID, never the plan's contents.

In 0.1.0, a hash that doesn't match is `plan.approval_required`. `plan.changed` is for a saved plan that the configuration no longer resolves to, which arrives with resuming experiments in 0.3.0.

## Artifact storage

**Requirement (REQ-05).** All artifact reads and writes go through the `ArtifactStore` interface. From 0.1.0 it has a local filesystem implementation.

- **Relative paths.** Paths in manifests are relative to the output root, never absolute, so a moved or served directory stays valid. The store takes only such paths: segments separated by `/`, none of them empty, `.`, or `..`, and no `\`, `:`, or NUL, which no file name holds, the same rule the models apply.
- **Immutability.** Source artifacts are never modified after they are written. Trial Folio never overwrites an existing artifact; corrections and migrations produce new artifacts.
- **Atomic writes.** Each file is written to a temporary name in the same directory, flushed and synced to disk, and then published under its final name without replacing anything. The one exception is the file that [claims an output directory](#cli-behavior), which is created directly under its final name.
  - **Never replace.** If the final name exists, even because another process created it at the same moment, publishing fails, and the temporary file is removed. So a record that changes state is written as a new file, never over an old one: an attempt's start record and its attempt record are two files ([execution outcomes](#execution-outcomes-and-attempts)).
  - **Linux and macOS.** `os.rename` and `os.replace` silently replace an existing file there, so they aren't used. Trial Folio hard-links the temporary file to the final name with `os.link`, which fails if the name exists. It then removes the temporary name and syncs the directory.
  - **Windows.** `os.rename` fails if the name exists, so it's used.
  - **No hard links.** On Linux and macOS, a file system without hard links, such as FAT or exFAT, can't take these writes. The first atomic write, which for `run` is `configuration.yaml`, fails with `storage.write_failed`, before any request is sent, and the message says why. `os.link` reports it with `ENOTSUP` on macOS, `EPERM` on Linux, as link(2) documents, or `ENOSYS`, which libfuse returns for a file system without a link operation. Only an error from `os.link` is read this way. On Windows, `os.rename` works on those file systems.

    R01-T08 tried the store on exFAT and FAT32 disk images on macOS 26.6.2, with Python 3.12.13: the claim succeeded, and writing `configuration.yaml` failed with `storage.write_failed` and the message "the output directory's file system doesn't support hard links (Operation not supported)". The claim's `plan.json` was left, without a manifest.
- **Syncing.** A sync is `os.fsync`.
  - **macOS.** `fsync` doesn't flush the drive's write cache there, so Trial Folio calls `fcntl.fcntl` with `fcntl.F_FULLFSYNC` instead. Where the file system doesn't support it, such as some network volumes, Trial Folio falls back to `fsync`, and logs a warning, once for each output directory, that the files are less durable (`artifact.sync.degraded`).

    **How macOS reports it.** The fallback follows `ENOTSUP` and `ENODEV`. Any other error from `F_FULLFSYNC` fails the write, because a later `fsync` could hide an I/O error. R01-T08 checked this on macOS 26.6.2: APFS, exFAT, and FAT32 support `F_FULLFSYNC` for files and directories; devfs, a file system without it, reports `ENODEV`. A network volume couldn't be tried without administrator rights. Go's `os` package falls back on `ENOTSUP`, which it reports SMB mounts give ([golang/go#64215](https://github.com/golang/go/issues/64215)).
  - **New directories, on Linux and macOS.** A directory's entry is durable only once the directory holding it is synced. So before a file in a directory Trial Folio created counts as durable, it syncs each directory it created on the way, and the parent of the first one. That includes the start record's `cases/<case_id>/attempts/<attempt_id>/`. Each successful directory creation is recorded before a pending SIGINT is delivered, so an interrupt can't leave one out or attribute a competitor's directory to this store. A write that fails leaves its new directories to be synced by the next write under them. The claim also syncs the output directory's parent, even when it didn't create the output directory, because a competing claim may have created it and failed before syncing it.
  - **A directory that can't be synced.** Some systems refuse to sync a directory, with `EINVAL` or `EBADF`. PostgreSQL ignores those two errors for a directory (`fsync_fname_ext`), and so does Trial Folio: it logs a warning, once for each output directory, that new entries may be lost after a power loss (`artifact.sync.degraded`), as on Windows. Any other error fails the write.
  - **Windows.** Python can't open a directory there to sync it, and `os.rename` doesn't ask for the rename to be written through to disk. So Trial Folio syncs files only. That's a limitation: after a power loss on Windows, the entry of any newly published file may be lost, in a new directory or an existing one, so a start record, an attempt record, or a saved response may be lost.

    R01-T08 confirmed both from CPython 3.12.13's source and Microsoft's documentation, not on Windows itself. `os.open` calls `_wopen`, which fails with `EACCES` when [the path is a directory](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/open-wopen), and `os.fsync` calls `_commit`, which takes a file descriptor. `os.rename` calls [`MoveFileExW`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw) with no flags: without `MOVEFILE_REPLACE_EXISTING` it fails if the name exists, and without `MOVEFILE_WRITE_THROUGH` it doesn't wait for the move to reach the disk. No test has run on Windows yet.
- **Completion.** A case is complete only after its required payload and its attempt record are durably written. The manifest is written last, and a missing or incomplete manifest means the output is incomplete.
- **Hashes.** Hashes detect changes. They do not prove that a provider's data is scientifically correct, and they do not make local files tamper-proof.

The layout of a 0.1.0 run, which [0.1.0's required outputs](releases/0.1.0-api-execution.md#required-outputs) fix:

```text
<out>/
  manifest.json
  plan.json
  configuration.yaml                                byte-for-byte copy of the screen configuration
  cases/<case_id>/attempts/<attempt_id>/
    started.json                                    start record, written before the request is sent
    attempt.json                                    attempt record, written once when the attempt ends
    request.json                                    redacted
    response.json                                   the decoded response
    response.raw                                    only for a 200 the wrapper couldn't decode: the body as received, labeled undecoded
  normalized/metrics.csv
  normalized/settings.csv
  report.html
  logs/                                             diagnostics; excluded from hashes and from the manifest's evidence
```

Release 0.2.0 defines the review layout. The proposal is `inputs/<label>/`, holding byte-for-byte copies of each compared run's manifest and normalized tables, plus `normalized/differences.csv`. Release 0.3.0 adds `experiment.json` and a lock file.

The manifest records:

- `schema_version`, `artifact_type` (`review`, `run`, or `experiment`), `trialfolio_version`, and the creation time in UTC.
- The command, `run` or `demo`, its non-secret options, and when it started, so that the manifest gives the run's duration.
- `synthetic`: true exactly for the run `trialfolio demo` writes.
- The `outcome`, `completed`, `partial`, or `failed`, and the `error`, as the [JSON summary](#json-summary) gives them.
- For a run or an experiment, the `plan_hash` and how the plan was approved: `interactive` or `option` ([approval](#approval)). The synthetic run `trialfolio demo` writes sends nothing, so its approval is `not_required`.
- Every input and output artifact with its path, `artifact_id`, size, role, and schema version when it has one. A source artifact also carries its [source record](#source-artifacts): when it was acquired, its format and version, the parser version, its provenance, and the provider operation. `logs/` isn't listed.
- Parser versions, one for each provider layout, together with the layout's version; `license_id`; and `notice_version`.
- A capability statement of what the artifact does and does not contain. `return_series` is `source_only` when a saved response holds per-period series, which 0.1.0 preserves but doesn't normalize, chart, or analyze, and `absent` otherwise. It states `statistical_validation: not_assessed` and `trading_readiness: not_assessed`.
- Reproducibility: each external reference, by setting, and whether it was snapshotted. The status is `incomplete` when any wasn't, and `complete` otherwise.
- Counts: results, cases, attempts by outcome, provider requests as the [JSON summary](#json-summary) counts them, retries, and the cost Portfolio123 reported. `quotaRemaining` is account information, and manifests may be shared ([D-14](spec.md#decisions)), so it stays in the attempt record.

`schemas/run-manifest-1.0.0.schema.json` gives every field.

Raw files and JSON metadata come first, and normalized tables are CSV. Parquet MAY be added for large tables when needed. SQLite MAY later index outputs, but it MUST NOT become a first-release prerequisite or the only copy of any evidence.

## Canonical hashing

These rules are `canonicalization_version` 1, a requirement since 0.1.0's sign-off (2026-10-01). Plan 1.0.0 and `case_id` use them (R01-T04), and any later change makes a new version.

- Canonical JSON follows [RFC 8785, JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html), applied to the model's serialized form.
- Decimal values are strings: a configuration decimal in its normalized form ([screen configuration](#screen-configuration)), and a metric value with exactly the digits its saved source carries. The exception is a provider request recorded as it's sent, such as a plan's `params`: its numbers stay JSON numbers ([ADR 0003](adrs/0003-versioned-research-artifacts.md), decision 6).
- RFC 8785 differs from Python's `json.dumps` in two ways that matter here:
  - **Numbers.** RFC 8785 writes a number as ECMAScript does, so a whole-number float such as the slippage `1.0` becomes `1`. The [decimals rules](#screen-configuration) keep every other value in plain notation, where the two agree.
  - **Text.** `json.dumps` escapes non-ASCII text by default, so `Café` becomes `Caf\u00e9`, while RFC 8785 keeps the UTF-8 text.

  So the canonical form needs an RFC 8785 implementation, never `json.dumps`. R01-T10 chose Trail of Bits' [`rfc8785`](https://github.com/trailofbits/rfc8785.py) package, pure Python with no dependencies, pinned exactly at 0.1.4, because a change in its output would change every identity. `src/trialfolio/canonical.py` applies it. Fixtures with a slippage of `1` and a non-ASCII title check it (R01-AC25), and so do RFC 8785's own samples.
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

- It uses inline CSS and inline SVG only. It contains no `<script>` elements, event-handler attributes, or references to external resources such as fonts, stylesheets, images, or links that load content. Its only links are `<a href>` navigation: an in-page fragment (`#…`), a relative path to one of the run's artifacts, or one of the two outside links below. No other link has a scheme or a host, or starts with `/`.
- It has exactly two outside links ([D-21](spec.md#decisions)), each an `https` URL that loads nothing:
  - **The license:** `https://github.com/promptedportfolio/trialfolio/blob/v<version>/LICENSE`, where `<version>` is the Trial Folio version that rendered the report, so the link names that version's [release tag](#versioning). It works once the repository is public and the version is tagged.
  - **Portfolio123's terms:** `https://www.portfolio123.com/legal`, the page [DSC-10](disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users) cites.
- The concise financial-result notice from [disclaimers.md](disclaimers.md) appears near the top, before any results, with an in-page link (`href="#…"`) to the full notice. The full notice appears at the end, in a `<details>` element, which needs no script, together with the license name, `license_id`, `notice_version`, and the license link ([DSC-03](disclaimers.md#dsc-03-where-notices-appear)).
- The Portfolio123 data statement from [DSC-06](disclaimers.md#dsc-06-portfolio123-notices), with its link to Portfolio123's terms, appears in the closing section, before the `<details>` element, so it shows without being expanded. It isn't part of the versioned notices, so it doesn't change `notice_version`.
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

**Rendering and re-rendering (R01-T13).** `src/trialfolio/report.py` renders a run's report, and `src/trialfolio/runs.py` reads a saved run back for `trialfolio report`. `src/trialfolio/notices.py` holds the license's name and identifier, the notice version, and the texts of the notices and the Portfolio123 data statement; a contract test checks them word for word against [disclaimers.md](disclaimers.md) and LICENSE.

- **When it's written.** `run` and `demo` write `report.html` into the run after normalizing and before the manifest, so the manifest lists it. The report is rendered from what the manifest will record, without its own entry. `trialfolio report` writes only `report.html`, as the file that [claims](#cli-behavior) its new output directory: no manifest, which belongs to `run` and `demo`. It reads and checks the run first, then checks that the output directory is absent or empty, so an input that isn't a complete run is `input.not_a_run` even when the output directory isn't empty.
- **Its structure.** In order: a header holding the concise notice, before any result, whose words "the full license and research limitations" link to the full notice; the run's outcome, statistical validation and trading readiness, both "Not assessed", and the nature of the results, backtested, or synthetic for the demo's run ([DSC-04](disclaimers.md#dsc-04-actual-simulated-and-hypothetical-results)), which no other part of the report contradicts: a synthetic run's report never calls the run a backtest, or its values Portfolio123's; then the ten sections above, in order, each a `<section>` with its own `id`; then the closing section, a `<footer id="closing">`, holding the Portfolio123 data statement and then the full notice in `<details id="full-notice">`, with the license's name, `license_id`, `notice_version`, and the LICENSE link. The status is shown neutrally: every color is a neutral gray, and no status has styling of its own.
- **A synthetic run's records.** Its section of results or cases says that its attempt, the attempt's exchanges, and its counts are invented, as a real run would record them, and that nothing was sent or charged (R01-T14).
- **Sections the evidence can't support.** A screen run declares no research objective, and has no baseline, robustness results, statistical method, or separate holdout or forward period, so those parts say they're unavailable, or not assessed, and why. A run without normalized tables, because its attempt didn't succeed, or its response couldn't be decoded or lacks the required structure, says which, and shows the plan's resolved settings with their expected provenance instead of `settings.csv`'s.
- **Values.** Each value appears exactly as the normalized tables hold it, with its unit, its token such as `not_sent`, or, when it's unavailable, its reason code and what it means. The report never shows `quotaRemaining`.
- **Text Trial Folio didn't write,** such as the title, the formulas, or Portfolio123's message in an error, is HTML-escaped. As in the [plan display](#approval), its control and formatting characters and its line and paragraph separators, apart from tabs and line breaks, are written as escapes such as `\u202e`, so the text can't add markup or reorder what's shown. So are lone surrogates, which UTF-8 can't hold.
- **Links to the run's artifacts.** A report links `manifest.json` and each file the manifest lists, apart from reports, by a path relative to the report's own directory, with each segment percent-encoded. In the run, that's the path in the manifest. A report `trialfolio report` writes elsewhere links through the run's directory, by its path relative to the new output directory, such as `../../runs/baseline/plan.json`, which the CLI works out. Each of its segments is percent-encoded from its bytes in the file system, so a directory whose name isn't UTF-8 is still linked. Where there's no relative path, as between two Windows drives, the files are named without links.
- **Deterministic.** The report holds no time of its own rendering. So rendering the same run with the same version gives the same bytes, and re-rendering a run into its own directory reproduces its report.

**A complete run.** `trialfolio report` reads only through the `ArtifactStore`, and only the files the manifest lists. A directory is a complete run when all of these hold; otherwise it's `input.not_a_run`, and the message names the problem, never a value:

- Its `manifest.json` is a run manifest, `artifact_type: run`, valid against its model.
- Each file the manifest lists exists, with the size and `artifact_id` the manifest records.
- It lists `plan.json` and `configuration.yaml`, once each. `plan.json` recomputes to its `plan_hash` ([plan hashing](#plan-hashing)), and the manifest names the same hash.
- Each start record and attempt record it lists is in an attempt's directory of the plan's case, is valid, names that attempt, its case, and its plan's hash, and agrees with the attempt's other record. Each file an attempt record references is listed, with the same `artifact_id` and the matching role.
- It lists both normalized tables, or neither. Each table reads back as a valid table, its rows are labeled with the plan's `case_id`, and they were drawn from the run's own `configuration.yaml` and saved response. `metrics.csv` holds one row for each of the layout's metrics, and `settings.csv` one for each of the plan's settings, in their documented order: a table missing a row, or with one repeated, isn't complete.

A schema version with no reader, in the manifest, `plan.json`, a start record, an attempt record, or the manifest's entry for one of them or for a table, is `artifact.unknown_schema_version`.

## CLI behavior

The command is `trialfolio`. Commands are introduced by release:

| Command | Release | Purpose |
|---|---|---|
| `trialfolio run <config> --out <dir> [--approve <plan-hash>]` | 0.1.0 | Plan and execute one supported screen backtest, once its [plan is approved](#approval) |
| `trialfolio report <run-dir> --out <dir>` | 0.1.0 | Re-render a saved run's report offline |
| `trialfolio demo --out <dir>` | 0.1.0 | Write a synthetic example run, labeled synthetic, and render its report offline |
| `trialfolio review <config> --out <dir>` | 0.2.0 | Compare saved runs offline |
| `trialfolio experiment <config> --out <dir>` | 0.3.0 | Plan, execute, and resume a finite experiment |
| `trialfolio --version` | 0.1.0 | Print the application version |
| `trialfolio license [--accept]` | 0.1.0 | Print the license, the full notice, and the acknowledgment status; `--accept` records the acknowledgment |

- **stdout** carries the command's result: a short human summary, or with `--json` the [JSON summary](#json-summary).
- **stderr** carries progress, warnings, and errors, which come from the same events as the log file. It also carries the [plan display](#approval) and the confirmation prompts, which are written directly and never logged, because they show configuration values.
- **Output directory.** `review` and `run` create the output directory. They refuse to write into a directory that exists and is not empty (`output.not_empty`). There is no overwrite option in 0.1.0. `experiment` reuses an existing directory only to resume the same plan, as release 0.3.0 specifies.
- **Claiming the directory.** A command that creates a new output checks the directory early, but another process can write to it before the command writes anything, for example while `run` waits for approval. So the command claims the directory with its first file. `experiment` resuming its own existing directory doesn't claim it; it takes the experiment lock instead, as release 0.3.0 specifies. The claim:
  1. It creates the directory if it's absent, and any missing parent directories, one at a time, remembering which ones it created. A directory that another process creates first is used as it is, and not remembered. Before it creates anything, it checks the path as the early check does: a path that exists and isn't a directory, a symbolic link to nothing included, is `output.not_empty`, and a path that can't be created, because a parent isn't a directory or none exists, is `storage.write_failed`. `..` segments are resolved in the path as written, so the claim never creates a directory that's only on the way to `..`.
  2. It creates its first file directly under its final name, with an exclusive create that fails if the name exists, then writes and syncs it. No temporary file is involved, so nothing else is written into a directory that isn't claimed.
  3. It lists the directory.

  **Ownership across interrupts.** While creating a directory, or exclusively opening the claim file and recording its identity from the returned descriptor, the store defers a callable SIGINT handler. It restores the caller's handler before delivering a pending signal, even if creation failed. The descriptor is closed on the interrupt path too. This applies in the main thread, where Python delivers signal handlers; worker-thread calls do not change handlers, and an ignored SIGINT stays ignored ([Python's signal rules](https://docs.python.org/3.12/library/signal.html#signals-and-threads)). Tests send real SIGINT at the creation boundaries so they exercise this deferral rather than bypassing it with a directly raised exception.

  Cleanup never treats an empty file as proof of ownership. The claim records only successful creations, and checks the file's device and inode against the recorded identity both before accepting the claim and before removing its file on failure. A missing or replaced claim file fails with `output.not_empty`; a replacement is left alone. If cleanup cannot read the identity, it leaves the file rather than removing an unverified file.

  If the first file existed already, or the directory holds anything else, the claim fails with `output.not_empty`. Each command lists the directory only after its own file exists. So when two commands claim the same directory at once, at most one succeeds. If the directory, or a parent the claim is creating it in, disappears during the claim, because a competing claim that created it failed and removed it, the claim also fails with `output.not_empty`.

  **The first file's AppleDouble file.** On macOS, a file system that can't hold extended attributes, such as FAT or exFAT, gets an AppleDouble file for each file that has them, named `._` and the file's name. macOS creates it together with the file, and removes it with the file. R01-T08 saw it created with each new file on exFAT and FAT32, holding `com.apple.provenance`. So on macOS, the claim counts `._` plus its own file's name, such as `._plan.json`, as part of that file. Any other name, `._` names included, is something else.

  A command whose claim fails removes only what it created: the file it created, if any, and then the directories it remembers creating, deepest first, each only if it's empty. It removes each with `os.rmdir`, which never removes a non-empty directory. If another process has written there, that directory and its parents are left as they are, and the result is still `output.not_empty`. A command writes nothing else, logs included, into a directory it hasn't claimed.

  A crash while the first file is written leaves it incomplete. A saved `plan.json` is checked against its hash, and there's no manifest, so the output is visibly incomplete.
- **Validation first.** All inputs are validated before the output directory is created, so an invalid or unsupported input creates no output. An interactive license acknowledgment, which comes first, still writes its own record.
- **Partial success.** A command that finishes with some cases failed, skipped, or uncertain writes complete accounting and exits with code 6.

**Running the commands (R01-T14).** `src/trialfolio/cli.py` is the command, and `src/trialfolio/execution.py` the steps of `run` and `demo` after approval:

- **What a run writes after its attempt.** Once the attempt record is written, `run` normalizes a saved response, then writes `report.html`, then `manifest.json`. It does that for a failed attempt too, so a provider error is accounted for, with the manifest's `outcome` `failed`, and so is a response that fails validation (`provider.response_invalid`), without tables. An interrupt, a storage failure, or an unexpected exception after the attempt leaves no manifest, so the output is visibly incomplete, and so does an attempt record that couldn't be written.
- **The manifest.** `command.options` records `out`, `approve`, and `json`, as given; the configuration's path isn't recorded, because a path can name the user. Every run lists the layout's parser. The configuration's source record is acquired when the command started; the request's when the attempt started; the response's when it ended. A response is `verified`, and the configuration `user_supplied`. `return_series` is `source_only` when the attempt saved a decoded response, whose `results.rows` and `chart` are the per-period series, and `absent` otherwise.
- **The demo.** `trialfolio demo` takes `run`'s steps, with `approval: not_required`, over a client that opens no connection. That client records the two exchanges a successful call records, `POST /auth` and `POST /screen/backtest`, each a 200, because the 1.0.0 attempt record holds an attempt that succeeded only with them. So the demo's run has every file and record of a real one, and its records read as a real run's do, possibly charged with one provider request. Its manifest is labeled synthetic, and its report says that its attempt, exchanges, and counts are invented and nothing was sent or charged. Its packaged configuration, the documented example retitled, and response, the `complete.json` fixture without `cost` and `quotaRemaining`, are in `src/trialfolio/demo_data/`, so the run reports no cost.
- **`trialfolio report`** gives `input.not_found` for a run directory that doesn't exist, and `input.not_a_run` for anything else that isn't a complete run.
- **stdout and stderr.** Without `--json`, stdout holds a short summary on success, and nothing on failure. stderr shows the error with its full message, progress at INFO, and warnings. An argument the parser rejects is a usage error, exit 2, reported by the parser on stderr, without a JSON summary: no error code covers it.
- **The JSON summary.** `counts.attempts` is 1 once an attempt record or a start record exists. `metrics_unavailable` is 0 when there's no `metrics.csv`. `warnings` counts the warnings logged during the command.
- **The entry function** is `trialfolio.cli.main(argv, *, endpoint, timeout, clock, store_factory)`. It returns the exit code, and reads `sys.stdin`, `sys.stdout`, and `sys.stderr` as they are when it's called. The installed command, and `python -m trialfolio`, call it with none of the keyword parameters.
- **Imports.** The modules that import `p123api`, `requests`, or `urllib3` load only after `installed_versions` has checked them, so a missing or broken one is `environment.unsupported`, never an `ImportError`.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | Command completed and outputs were written. This says nothing about any strategy. |
| 1 | Unexpected internal error |
| 2 | Usage error: invalid arguments, missing plan approval, or license not acknowledged |
| 3 | Invalid or unsupported configuration, input, artifact, or environment |
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
| `ids` | Identifiers the command created, for example `{"review_id": "…"}`. For `run`: `plan_hash` and `case_id` once the plan is built, even if it isn't approved, and `attempt_id` whenever an attempt record or a start record exists, including after a failed authentication. Empty when it created none. |
| `output_dir` | The output directory as given on the command line. `null` if none was created. |
| `outputs` | Output files relative to `output_dir`, keyed by role: `manifest`, `report`, `metrics`, `settings`, `differences` |
| `counts` | For `run`: `attempts`; `provider_requests`, the sends of the planned request that may have reached Portfolio123, never authentication ([HTTP exchanges](#http-exchanges)), which the [budget](#budget-and-retries) limits; `metrics_unavailable`; `warnings`; and the credit `cost` when the provider reports it. For `review` (0.2.0): `results`, `settings_flagged`, `metrics_unavailable`, `warnings`. |
| `statistical_validation`, `trading_readiness` | `not_assessed` in every 0.x release that doesn't assess them |
| `error` | `null`, or `{"code": …, "message": …}` using the codes in [errors](#errors) |

`ids` and `outputs` leave out a key that has no value, rather than writing `null`. `counts` is `{}` for `report` and `license`. When `outcome` is `completed`, `exit_code` is 0 and `error` is `null`. Otherwise `exit_code` is the error code's exit code, and `outcome` is `partial` exactly for `execution.partial`. `schemas/json-summary-1.0.0.schema.json` gives every field.

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
- **Details (R01-T14).** `src/trialfolio/acknowledgment.py` holds them:
  - The typed answer must be exactly `accept`, as the plan's must be exactly `approve`.
  - An empty `TRIALFOLIO_ACCEPT_LICENSE` counts as unset. Any other value but the exact one is rejected, even when a record exists, and the message gives the exact value.
  - A record that can't be read, or isn't valid, asks again, as a missing one does. A new acknowledgment replaces it whole.
  - `trialfolio license --accept` fails with `storage.write_failed`, exit 4, when it can't write the record: recording it is the command's whole result.
  - `trialfolio license` prints the LICENSE from the installed package's metadata, then the full notice, then the status.
- **Scope.** This is a notice, not an eligibility check. It asks nothing about assets, income, or family ([LIC-12](licensing-policy.md#lic-12-acceptance-and-acknowledgment)). The core never checks it ([REQ-03](spec.md#enduring-requirements)). Each interface presents it, as the CLI does here.

## Errors

The core raises typed errors with stable dotted codes and actionable messages. Only the CLI maps them to exit codes. Messages say what failed, why, and what to do next. They never include credentials, and they include the offending values only in the terminal, never in logs. Portfolio123's own message, which a provider error ends with when [0.1.0's failure table](releases/0.1.0-api-execution.md#failure-and-incomplete-data-behavior) calls for it, can repeat configuration values, so the error also carries its message without that text for logs ([credentials](#credentials)). Every error carries such a loggable message, the same as its message when there's no text to leave out. It's also the error's string form, so a logged traceback leaves the text out too.

| Code | Exit | Meaning |
|---|---|---|
| `config.invalid` | 3 | Configuration fails validation, including unknown keys and cross-field rules |
| `input.not_found` | 3 | A referenced file does not exist |
| `input.not_a_run` | 3 | An input directory is not a complete Trial Folio run: its manifest is missing, or its files don't match their hashes. The message names the problem. |
| `artifact.unknown_schema_version` | 3 | An artifact's schema version has no reader |
| `environment.unsupported` | 3 | The installed `p123api`, `requests`, or `urllib3` isn't a verified version, or `requests` would write request bodies with `simplejson` ([plan contents](#plan-contents)). It's found before the plan is shown, so nothing is sent and no output is created. The message names the verified versions and how to restore them. Exit 3, like an unsupported input, because the fix is local. |
| `license.not_acknowledged` | 2 | A data-processing command ran without an acknowledgment of the current license and notice versions |
| `plan.approval_required` | 2 | A charged or mutating operation was requested without the matching plan hash: no `--approve`, a different hash, or a refused confirmation |
| `plan.changed` | 3 | The configuration no longer resolves to a saved plan, for example when resuming an experiment (0.3.0). A hash given with `--approve` that doesn't match is `plan.approval_required`. |
| `output.not_empty` | 4 | The output directory exists and is not empty |
| `storage.write_failed` | 4 | An artifact could not be written durably. This is the code even when a request was already sent; the attempt record still gives the outcome ([endings that decide the error code](#endings-that-decide-the-error-code)). |
| `experiment.locked` | 4 | Another process holds the experiment lock |
| `provider.auth_failed` | 5 | Credentials were missing, Trial Folio's authentication call got a 400, 401, 402, 403, or 406, or Portfolio123 refused a request's authorization with a 401 or 403 |
| `provider.unavailable` | 5 | Portfolio123 couldn't be reached, or didn't complete Trial Folio's authentication call: that call got a 5xx or no complete response, or the request's connection was never established ([HTTP exchanges](#http-exchanges)). Either way, the request wasn't sent. |
| `provider.quota_exceeded` | 5 | The provider refused the request because of quota or credits |
| `provider.unsupported_capability` | 5 | Portfolio123 rejected the request with a 400: a setting or operation the verified provider path doesn't support. The request may have been charged. |
| `provider.request_rejected` | 5 | Portfolio123 answered Trial Folio's authentication call or the request with a status below 500 that no other code covers, such as a 204, 3xx, 404, or 429. The message gives the status, and Portfolio123's sanitized message when the wrapper's exception message carries one. After a refused second exchange, such as a redirect, there's none ([HTTP exchanges](#http-exchanges)). |
| `provider.response_invalid` | 5 | The response was saved but failed validation, or couldn't be decoded and was saved undecoded as `response.raw` |
| `provider.outcome_unknown` | 5 | A request may have been sent, but no response was durably recorded: for example after a read timeout or a 5xx. It is never retried automatically. |
| `execution.partial` | 6 | Some planned cases did not succeed; all are accounted for |
| `command.interrupted` | 130 | The user interrupted the command, for example with Ctrl-C. The message says whether a request may have been sent, as the attempt record does ([interrupts](#interrupts)). |
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

**Requirement (REQ-09, INV-11).** Credentials come from an injected source. For the CLI, they come from these environment variables:

| Variable | Contents |
|---|---|
| `TRIALFOLIO_P123_API_ID` | Portfolio123 API ID |
| `TRIALFOLIO_P123_API_KEY` | Portfolio123 API key |

The CLI reads the variables and passes a credential object to the provider client. Credential objects are never serialized, hashed, logged, or written to artifacts. **Where the credentials go.** The CLI sends them only to the wrapper's default endpoint, Portfolio123's API, directly. Nothing in the environment can redirect or expose them:

- **No Trial Folio setting.** No option, configuration key, or environment variable changes the endpoint.
- **No `requests` environment settings.** Trial Folio sets `trust_env` to `False` on the wrapper's session, where it mounts its adapter ([ADR 0006](adrs/0006-observe-the-wrappers-http-exchanges.md)). So `requests` ignores the proxy variables, such as `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY`; the certificate-bundle variables `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE`; and `.netrc` or `NETRC`, whose credentials would otherwise replace the bearer token. Certificates come from `requests`' own bundle. So 0.1.0 supports no proxy ([open questions](releases/0.1.0-api-execution.md#open-questions)).
- **No TLS key log.** `urllib3` writes TLS session keys to the file that `SSLKEYLOGFILE` names, which would let anyone with a capture of the traffic read the API key. So the CLI removes `SSLKEYLOGFILE` from its own process environment before any request, and warns on stderr that it was ignored. The user's shell is unaffected.
- **The README says so** ([R01-T17](releases/0.1.0-api-execution.md#implementation-tasks-only-after-ready)).
- **The CLI's entry function** takes parameters for tests only: the endpoint, the request timeout, the clock, and the factory that makes the output directory's `ArtifactStore` ([0.1.0's test doubles](releases/0.1.0-api-execution.md#test-pairing)). It's internal ([public contract boundary](#public-contract-boundary)), and the installed command never passes them.

The wrapper's error objects need the same care. The response attached to a `p123api` `ClientException` carries the `Authorization` header, and for authentication failures its request body contains the API key. The client's token accessor exposes the bearer token. Trial Folio never logs, serializes, or saves these objects. From an error it keeps only the status code and a sanitized message:

- **What it reads.** Only the exception's type and message. Portfolio123's own text is the message of a plain `ClientException`, after the wrapper's prefix, `API request failed: ` or `API authentication failed: `. `ClientItemNotFoundException`'s message is the wrapper's own, and so are the authentication messages for a 400, 401, 402, or 406.
- **Sanitizing.** Each occurrence of the API ID, the API key, or the token becomes `[redacted]`. Replacement matches the original text once, with longer secrets first, so a shorter value contained in another cannot expose its remainder. Control characters become spaces, runs of whitespace one space, and the text is cut to 300 characters, the last an ellipsis.
- **No reference.** The client raises its own error outside the handler of the wrapper's, so the error's `__cause__` and `__context__` are empty, and nothing reaches the wrapper's exception from it.
- **Logs.** A provider error's message ends with Portfolio123's sanitized text when there is some. That's for the terminal and the attempt record. Its loggable message leaves the text out ([errors](#errors)). Redaction tests seed canary values and check that they appear nowhere in the outputs or logs, including after an authentication failure.

Development credentials are handled as [AGENTS.md](../AGENTS.md#credentials-and-reference-data) describes.

## Logging and local diagnostics

**Requirements (REQ-06, INV-14).**

- **Local only.** No log handler, trace or metrics exporter, crash reporter, analytics call, or update check sends anything off the machine. The only outbound traffic is provider requests the user invokes or explicitly enables. Telemetry built into dependencies is disabled.
- **Content.** Logs never contain credentials, strategy definitions, formulas, configuration values, provider payloads, results, or input file contents, at any level. Artifacts are referenced by ID and hash instead. Validation errors are logged with `errors(include_input=False)`, or with `hide_input_in_errors` enabled, and logged tracebacks omit local variables.
- **Mechanism.** The standard `logging` module, with no added dependency. Core modules use `logging.getLogger(__name__)` and never configure handlers; the CLI configures them.
- **Format.** Log files hold one JSON object per line with these snake_case fields: `timestamp` (UTC ISO 8601), `level`, `event` (a stable dotted name), `message`, `trialfolio_version`, `component`, and the applicable `review_id`, `plan_hash`, `case_id`, `attempt_id`, `request_id`, and `parent_id`. The terminal shows human-readable messages on stderr from the same events.
- **Levels.** ERROR for a failed operation, WARNING for a degraded condition the command continues through, INFO for lifecycle milestones, and DEBUG for diagnostic detail. Log files record INFO and above. Setting `TRIALFOLIO_LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, or `ERROR` changes that, for diagnosis. Any other value is ignored, with a warning on stderr. The content rules apply at every level.
- **Tracing.** Start and end events carry duration and outcome for each command, case, attempt, and provider request, linked by IDs, and this serves as the trace. OpenTelemetry is adopted only through an ADR, with local file exporters only.
- **Metrics.** There is no metrics system. Per-run counts and durations go in the manifest.
- **Storage.** Logs go to `logs/` inside the output directory, or to the per-user log directory for commands without one, such as `trialfolio license`. A command with an output directory holds its events in memory until it has [claimed the directory](#cli-behavior). If it stops before then, including when the claim fails, it writes no log file, and its messages appear only on stderr. The exception is `internal.unexpected`: the command then writes the held events to the per-user log directory, and its message names that file. Log size is bounded by rotation. The README documents the locations and how to delete them.
- **The per-user log directory** follows the same pattern as the [acknowledgment record](#license-acknowledgment), in each platform's conventional place for logs:
  - `TRIALFOLIO_LOG_DIR`, if set
  - otherwise `$XDG_STATE_HOME/trialfolio/logs` or `~/.local/state/trialfolio/logs` on Linux
  - `~/Library/Logs/trialfolio` on macOS
  - `%LOCALAPPDATA%\trialfolio\logs` on Windows

Initial event names: `cli.command.started`, `cli.command.completed`, `review.input.loaded`, `artifact.write.completed`, `artifact.sync.degraded`, `report.render.completed`, `plan.created`, `plan.approved`, `attempt.started`, `attempt.completed`, `attempt.unexpected`, `provider.request.started`, `provider.request.completed`, `provider.request.failed`, `provider.request.refused`, `case.completed`, `experiment.resumed`.

**The CLI's logging (R01-T14).** `src/trialfolio/logs.py` configures it:

- **The file** is `trialfolio.log`, in `<out>/logs/` or the per-user log directory, rotated at 1 MB with 3 older files kept. An `$XDG_STATE_HOME` or `$XDG_CONFIG_HOME` counts only when it's an absolute path, as the XDG Base Directory Specification says, and so does a Trial Folio variable only when it isn't empty.
- **The terminal** shows the events at INFO, as progress, and warnings, prefixed `Warning:`. Errors are the command's to show, with the full message; their log events hold the loggable message.
- **New events:** `cli.output.claimed`, when a command has claimed its output directory; `cli.command.unexpected`, for an unexpected exception outside an attempt, with its type and frames; `cli.environment.ignored`, for an ignored `SSLKEYLOGFILE` or `TRIALFOLIO_LOG_LEVEL`; `cli.log.unavailable`, when no log file can be opened, and the command carries on without one; `license.acknowledged`, and `license.record.failed`, when an interactive acknowledgment can't be recorded. `case.completed` ends a run that reached its manifest.
- **An internal error before the claim** writes the held events to the per-user log directory, and the message names the file. After the claim, the message names `<out>/logs/trialfolio.log`.

## Fixtures

**Requirement (REQ-11).** Committed fixtures are synthetic by default. A fixture that mirrors a verified provider layout copies its structure — column names, order, and formats — and never its data. Each fixture directory records:

- Its origin, and the layout version it mirrors.
- Its redistribution status.
- The requirements or acceptance criteria it exercises.

Expected outputs change only with a stated reason. Reference responses procured with the owner's account ([D-09](spec.md#decisions)) stay local and git-ignored unless Portfolio123's terms are confirmed to permit redistribution. No fixture, sample configuration, or sample export is copied from DataMiner or FactorMiner repositories.

## Pydantic conventions

- Pydantic v2 models define application-owned configuration, manifests, plans, attempt records, and later study protocols and assessments.
- Configuration models forbid unknown fields, and validate in Pydantic's strict mode, so no value is coerced: a string is never read as a number, a boolean, or a date, and a float never as an integer. Forms a YAML 1.1 loader converts before validation, such as `1:30`, are rejected from the YAML text ([screen configuration](#screen-configuration)). Provider payloads are preserved whole as source artifacts, and normalized models cover only the supported subset.
- CSV and provider-specific units are parsed in named adapter steps before normalized models are validated. Validation bypasses such as `model_construct` are never used on untrusted input.
- Non-finite numbers are rejected. Unavailable values carry a reason, and ambiguous booleans, percentage strings, and date coercions are avoided.
- Cross-field rules are validators, for example date ordering, a baseline that names an existing result, and a benchmark-relative metric that requires a benchmark.
- Large tables stay in CSV (later, possibly Parquet), not in per-row models.
- Frozen models are used for plans and resolved configurations. Frozen models do not make nested mutable objects or saved files immutable; immutability on disk comes from the `ArtifactStore`.
- A `Literal` of integers, such as `rebalance_weeks`' `1` or `4`, also requires an integer. A literal compares by equality, so without that, `true` would pass as 1, and `4.0` as 4.
- Pydantic is constrained to major version 2, and the tested dependency resolution is recorded.

## Schema generation and drift

JSON Schemas are generated from the models, never maintained by hand, and committed under `schemas/`, one file for each contract and each schema version that has a reader. The generation mode, validation or serialization, is stated wherever the two differ. `scripts/schemas` writes them. `scripts/schemas --check` is the drift check: it generates every schema in memory, compares the result with `schemas/`, lists each file that differs, is missing, or is extra, and fails if there's any. `scripts/check` runs it. Schemas do not encode every semantic validator, so the runtime semantics are tested separately.

`scripts/schemas` writes these files. It never deletes anything: before writing, it refuses a directory that isn't one, or that holds a subdirectory or any file other than the current schemas. So an obsolete schema, after a version change for example, is deleted by hand once it's checked, and the drift check's message says so. Both generation and the drift check ignore hidden entries, such as macOS's `.DS_Store`. The script finds the repository from its own location, so it works from any directory. The default directory is the repository's `schemas/`; an explicit `--dir DIR` is relative to the directory where the command is run, unless absolute. The repository's Git attributes keep every text file at LF line endings, even with `core.autocrlf=true`, so a checkout passes the byte comparisons of schemas and fixtures.

`scripts/check` also fails when a schema file under `schemas/` isn't tracked by git, even an ignored one, because the drift check reads the working tree. Hidden files don't count, and any other untracked file already fails the drift check as extra. Each schema's `$comment` names its model and mode, and says whether the other mode differs. A configuration is input, so its schema is in validation mode. Every other contract is written by Trial Folio, so its schema is in serialization mode; for each of those, the two modes give the same schema.

| File | Contract |
|---|---|
| `screen-configuration-1.0.0.schema.json` | [Screen configuration](#screen-configuration) |
| `plan-1.0.0.schema.json` | [Plan](#plan-contents) |
| `start-record-1.0.0.schema.json`, `attempt-record-1.0.0.schema.json` | [Start and attempt records](#execution-outcomes-and-attempts) |
| `run-manifest-1.0.0.schema.json` | [Run manifest](#artifact-storage) |
| `metrics-row-1.0.0.schema.json`, `settings-row-1.0.0.schema.json` | One row of each [normalized table](#normalized-tables) |
| `json-summary-1.0.0.schema.json` | [JSON summary](#json-summary) |
| `license-acknowledgment.schema.json` | [License acknowledgment record](#license-acknowledgment), which has no schema version |

## Open questions

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| Are failed screen-backtest requests charged? | Budget accounting for failed and uncertain attempts | Until verified, count every send that may have reached Portfolio123 as possibly charged, whatever its outcome, and no other ([possibly charged](#http-exchanges)) | The owner compares the account's credit history, or asks Portfolio123. R01-T01's and R01-T05's calls didn't settle it. |
