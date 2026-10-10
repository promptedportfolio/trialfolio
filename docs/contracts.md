# Trial Folio contracts

**Status:** Draft. R01-T07 implemented 0.1.0's contracts as Pydantic models, generated schemas, and the screen configuration fixtures, R01-T08 the `ArtifactStore` and the output directory claim, R01-T09 the `ScreenBacktestClient` and its transport adapter, R01-T10 plans, canonical hashing, and approval, R01-T11 attempt recording, R01-T12 normalization and the normalized tables, and R01-T13 the report, its notices, and reading a saved run back for `trialfolio report`. For 0.2.0, R02-T04 implemented the review configuration and its reader, the review manifest, the rows of `differences.csv`, and the JSON summary's version 1.1.0, as models and generated schemas. For 0.3.0, R03-T06 implemented the experiment configuration and its reader, plan 1.1.0, `experiment.json`, the session and authentication records, start and attempt records 1.1.0, the experiment manifest, and the JSON summary's version 1.2.0, as models and generated schemas, and R03-T07 the plan compiler, which compiles an experiment configuration into plan 1.1.0, and the revision rules, with what `experiment.json` records of each revision. Nothing else here is implemented yet.
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
- **The package's version** is the next release's once that release's specification is complete ([D-26](spec.md#decisions)). So `trialfolio --version`, and every artifact written from `main`, give it before the release is tagged, and a release's tag may sit on a commit older than `main`'s head.

Every artifact records these versions separately:

| Version | Meaning |
|---|---|
| `trialfolio_version` | Application version that wrote the artifact |
| `schema_version` | Artifact schema version, `<major>.<minor>.<patch>`, independent of the application version |
| `parser_version` | Version of the adapter that interpreted a provider response, per supported layout |
| `canonicalization_version` | Version of the canonical-hashing rules used for identities |
| Provider library versions | The versions of `p123api`, `requests`, and `urllib3` used for provider requests ([plan contents](#plan-contents)) |
| Method versions | Version of each analytical method applied (when methods are introduced) |
| `license_id`, `notice_version` | The applicable license identifier (`LicenseRef-NSPRL-1.1` from 0.2.1; artifacts that 0.1.0 and 0.2.0 wrote record `LicenseRef-NSPRL-1.0`) and financial-notice version (`1.0`), defined in [../LICENSE](../LICENSE) and [disclaimers.md](disclaimers.md) |

A schema's version does not need to match the release that introduces it. Compatibility is defined against documented readers and semantics, not merely against added fields.

## Identity

Identifiers are introduced with the release that can define their semantics.

| Identifier | Introduced | Meaning | Form |
|---|---|---|---|
| `artifact_id` | 0.1.0 | Content address of one stored file | `sha256:<64 hex>` of the file's bytes |
| `review_id` | 0.2.0 | One `trialfolio review` output | Random UUID, version 4 |
| `label` | 0.2.0 | User-declared name of one compared result, unique within a review | `[a-z0-9][a-z0-9_-]{0,63}`, other than a device name Windows reserves ([review configuration](#review-configuration)) |
| `plan_hash` | 0.1.0 | Identity of a plan, which execution requires as approval | `sha256:` of the plan's canonical form ([plan hashing](#plan-hashing)) |
| `case_id` | 0.1.0 | Stable identity of one fully resolved configuration | `case-` plus the first 16 hex digits of the SHA-256 of the canonical resolved settings ([plan hashing](#plan-hashing)) |
| `case_key` | 0.3.0 | Readable name for a planned case, unique within an experiment: `baseline` for the baseline, user-declared for a variant, and given by Trial Folio for a default variant ([experiment configuration](#experiment-configuration)) | Same pattern as `label`, with the same reserved names |
| `attempt_id` | 0.1.0 | One execution attempt of a case | Random UUID, version 4, written in canonical form: lowercase, with hyphens |
| `experiment_id` | 0.3.0 | One declared experiment | User-declared slug, same pattern as `label`, with the same reserved names ([experiment configuration](#experiment-configuration)) |
| `study_id`, `candidate_id`, `assessment_id` | Later | Defined when their increment is specified | — |

The forms of the identifiers 0.1.0 introduces are requirements since 0.1.0's sign-off (2026-10-01), those 0.2.0 introduces since 0.2.0's (2026-10-05), and those 0.3.0 introduces since 0.3.0's (2026-10-08). The others are proposed until their release is Ready.

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
| `universe` | string | Yes | A non-empty Portfolio123 universe name, written in quotes or as a block scalar ([text sent](#screen-configuration)), for example `'SP500'` | `screen.universe` |
| `rules` | list of strings | Yes | At least one screening formula. Each one is a non-empty string, written in quotes or as a block scalar ([formulas](#screen-configuration)), and their order is kept. The model accepts ordered lists or tuples, never sets. | `screen.rules`, each as `{"formula": "…"}`. It has no `type` field, because Portfolio123 rejects one (R01-T01). |
| `ranking` | mapping | Yes | Exactly one of the [ranking forms](#ranking-forms) | `screen.ranking` |
| `max_holdings` | integer | Yes | 1 or more | `screen.maxNumHoldings` |
| `benchmark` | string | Yes | A non-empty Portfolio123 benchmark symbol, written in quotes or as a block scalar, for example `'SPY'` | `screen.benchmark` |
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
- **Verified as variants by R03-T01 (2026-10-07):** a variant changes one of these settings from its baseline, and the change was accepted and changed the strategy's metrics, each in its own call ([run record](../reference/variant-capabilities/README.md)): `slippage_percent` 0.5 against 0.25; a liquidity rule's threshold, `AvgDailyTot(30) > 100000000` against `> 1000000`; and a second rule added to the first, both a market-cap cutoff, `MktCap > 300`, and `Mod(StockID,4) = 0`, which isn't offered as a universe slice until `StockID`'s stability is verified ([open questions](releases/0.3.0-experiments.md#open-questions)). The run on `Easy to Trade US` was the rule variants' baseline, not a variant ([D-19](spec.md#decisions)), and universe names stay verified by form. The [0.2.0 live exercise](../reference/review-live-exercise/README.md)'s `max_holdings` 50 against 25 counts for holdings.
- **Documented but not accepted until a release verifies them:**
  - `max_holdings` 0, meaning no limit
  - `rebalance_weeks` 2, 3, 6, 8, 13, 26, and 52
  - `transaction_price` `high_low_average` and `close` (`transPrice` 3 and 4)
  - `pit_method` `prelim`
  - precision 2 and 3

#### Ranking forms

| Form | Keys in `ranking` | Sent as |
|---|---|---|
| A single formula (recommended) | `formula`, a non-empty string, written in quotes or as a block scalar; `lower_is_better`, a boolean, required | `{"formula": "…", "lowerIsBetter": …}` |
| An existing ranking system, by name | `name`, a non-empty string, written in quotes or as a block scalar | The name, as a string |
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
  - **Text Portfolio123 receives is quoted (R01-T18).** Each rule, the ranking's `formula` or `name`, the universe, and the benchmark is written in single or double quotes, or as a block scalar (`|` or `>`). A plain scalar, without quotes, fails with `config.invalid`, and the message names its key and says to write it in single quotes. Outside quotes, YAML reads a space followed by `#` as the start of a comment, with no error. Portfolio123 formulas can hold `#`, as in `FRank("EarnYield", #Industry) > 50`, which YAML would read without quotes as `FRank("EarnYield",`. A name can hold one too: `name: Core Combo #2` would send `Core Combo`, which could name another ranking system, so Portfolio123 would run the wrong backtest. Quoting all such text, whatever it holds, makes one rule with no exceptions. Fixed words, such as `screen`, `open`, `complete`, and `FactSet`, and the title and purpose, which are never sent, may be written without quotes; a title or purpose that holds a space followed by `#` still needs them.
- **Descriptions.** `title` and `purpose` describe the run. They are recorded in the plan and the run manifest with `user_supplied` provenance ([plan contents](#plan-contents)). They're never sent, and they aren't part of the resolved settings that identify a case.

**Sent on every request.** Trial Folio adds three fixed values, which 0.1.0's scope doesn't let the configuration change. R01-T01 verified each one.

- `screen.type`: `stock`
- `screen.method`: `long`
- `screen.currency`: `USD`

Trial Folio sends nothing else. The documented parameters it leaves out are `riskStatsPeriod`, `maxPosPct`, `rankTolerance`, `carryCost`, `longWeight`, and `shortWeight`. The settings below record each one.

#### Screen settings

`settings.csv` has these rows for a screen run, in this order. Every category here except `other` is critical. A review configuration's `intended_changes` accepts only the 12 settings marked declarable: the ones whose value comes from a screen configuration key and is sent in the request. The other settings are fixed, inferred, or not sent, so no configuration changes them. Three declarable settings, `transaction_price`, `pit_method`, and `precision`, take only one value in screen configuration 1.0.0, so a change declared to one of them can't be observed yet: it's `same`, flagged `intended_change_not_observed`. They stay declarable so that a release that verifies more of their values doesn't have to change the review configuration.

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
```

This example is validated in two ways:

- **Against Portfolio123.** It resolves to exactly the request in [`reference/p123api-screen-backtest/request.json`](../reference/p123api-screen-backtest/request.json), which Portfolio123 accepted in R01-T01.
- **Against this mapping.** The example was parsed with a YAML safe loader and mapped by the rules above, and the result equals that request.

A test repeats the second check: `tests/contract/test_screen_configuration.py::test_documented_example_resolves_to_reference_request` ([0.1.0's test pairing](releases/0.1.0-api-execution.md#test-pairing)).

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
| `label` | string | Yes | Matches `[a-z0-9][a-z0-9_-]{0,63}`, and is unique within the file. It isn't `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`: a label names its result's directory in the review ([review output](#review-output)), and Windows reserves those names for devices, whatever their letter case, for directories as well as files ([Naming Files, Paths, and Namespaces](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file), checked 2026-10-05). |
| `run` | path | Yes | A complete run directory written by `trialfolio run` |
| `description` | string | No | Up to 500 characters, shown in the report |
| `intended_changes` | list | No | Not allowed on the baseline entry |

**Each entry in `intended_changes`:**

| Key | Type | Required | Rules |
|---|---|---|---|
| `setting` | string | Yes | One of the 12 settings marked declarable in the [screen settings](#screen-settings). Any other name, including a setting that isn't declarable, fails with `config.invalid`, and the message lists the valid names. A result may list each setting at most once. |
| `reason` | string | Yes | 1–500 characters, shown in the report |

**Rules that span keys:**

- **Intended change not observed.** If a declared change isn't there because the two values are equal, the result is still valid. The difference is classified `same` and flagged `intended_change_not_observed`.
- **Intended change that can't be confirmed.** If the setting is missing from either run, the difference is `unknown`, and it keeps its `declared_reason`. In a critical category it's flagged `critical_unknown`, as any `unknown` there is. `precision`, the one declarable setting outside the critical categories, isn't flagged.
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

### Experiment configuration

Schema version 1.0.0, introduced in 0.3.0 (task R03-T02). An experiment configuration describes a finite experiment: one baseline screen, and a small set of variants, each changing one setting of the baseline. `trialfolio run` compiles it into cases before any request ([D-24](spec.md#decisions)): the baseline's case, then one case for each variant. Each case is a fully resolved screen, sent just as a screen configuration with its settings would be.

**Top-level keys:**

| Key | Type | Required | Rules |
|---|---|---|---|
| `kind` | string | Yes | `experiment` |
| `schema_version` | string | Yes | A supported version (`1.0.0`). Any other value fails with `config.invalid`, and the message names the supported versions. |
| `experiment_id` | string | Yes | The experiment's [identity](#identity): the same pattern as a review's `label`, with the same reserved names |
| `title` | string | Yes | 1–200 characters. Used as the report heading. |
| `purpose` | string | Yes | 1–2,000 characters, not all whitespace: the question the experiment addresses. Unlike a screen's, it's required, because it's part of the research history ([METH-03](methodology.md#meth-03-research-history-and-multiple-testing)). |
| `prior_research` | mapping | Yes | The [prior-research declaration](#prior-research) |
| `baseline` | mapping | Yes | The [baseline](#the-baseline) screen's settings |
| `variants` | mapping | No | The [variants](#variants), by the setting each one changes. If it's absent, the only variant is the [default](#default-variants). |
| `budget` | mapping | Yes | The [request budget](#the-experiments-budget) |

**Not sent.** `experiment_id`, `title`, `purpose`, `prior_research`, and each variant's `key` and `description` describe the experiment. They're never sent, and they aren't part of any case's settings, so they don't change a `case_id`. They're recorded with `user_supplied` provenance, in [plan 1.1.0](#experiment-plans-and-revisions) and [`experiment.json`](#experimentjson). A change to any of them but `experiment_id` is a plan revision, and keeps every case's `case_id`; another `experiment_id` is another experiment.

#### Prior research

Prior research is earlier work on the same idea whose outcomes the user saw, such as backtests of the same screen or of close variations of it, in Trial Folio or anywhere else ([METH-03.1 and METH-03.4](methodology.md#meth-03-research-history-and-multiple-testing)). Trial Folio can't verify it. It records the declaration as the user wrote it, and its report says the declaration is unverified.

| Key | Type | Required | Rules |
|---|---|---|---|
| `status` | string | Yes | `complete`, `partial`, or `unknown`, below |
| `description` | string | With `complete` or `partial` | 1–5,000 characters, not all whitespace. It may also be given with `unknown`. |

- **`complete`:** the description accounts for all the earlier outcome-informed work on this idea, or says there was none.
- **`partial`:** it accounts for some of it, and there was more that it doesn't describe.
- **`unknown`:** the user can't say what earlier work there was.

#### The baseline

`baseline` holds a screen's settings: the keys of a [screen configuration](#screen-configuration) from `universe` to `data_vendor`, with the same types, rules, and [verified values](#screen-configuration). The text Portfolio123 receives is written in quotes or as a block scalar, as in a screen configuration (R01-T18). It has no `kind`, `schema_version`, `title`, or `purpose`, which are the experiment's. Its case's key is `baseline`. The universe is the baseline's, and every case uses it ([D-19](spec.md#decisions)). Another universe is another experiment, not a plan revision ([experiment plans and revisions](#experiment-plans-and-revisions)).

#### Variants

`variants` maps a setting to a list of variants of it. Each variant changes that one setting of the baseline, and nothing else. A variant may change only these settings, the types [R03-T01 verified](releases/0.3.0-experiments.md#what-r03-t01-verified):

| Key in `variants` | Variant type | Each entry's change |
|---|---|---|
| `rules` | A changed rule, such as a liquidity rule's threshold; or an added rule, such as a microcap cutoff | `replace` and `with`, or `add` |
| `max_holdings` | Maximum holdings | `value`: an integer, 1 or more |
| `rebalance_weeks` | Rebalance frequency | `value`: 1 or 4 |
| `slippage_percent` | Slippage | `value`: a decimal, 0 or more, in percent |

Any other key in `variants`, such as `universe`, `ranking`, `benchmark`, or a date, fails with `config.invalid`, and the message names the settings a variant may change.

**Each entry:**

| Key | Type | Required | Rules |
|---|---|---|---|
| `key` | string | Yes | The case's `case_key`. The same pattern as a review's `label`, with the same reserved names; unique among the experiment's cases, including a default variant's; and not `baseline`. |
| `description` | string | No | 1–500 characters, shown in the report |
| `value` | integer or decimal | In `max_holdings`, `rebalance_weeks`, and `slippage_percent`, and only there | The setting's value in this case. It follows the rules of the screen configuration's key of the same name: a decimal is read and normalized by the [decimals rules](#screen-configuration). |
| `add` | string | In `rules`, unless `replace` is given | A screening formula, added after the baseline's rules |
| `replace` | string | In `rules`, unless `add` is given | One of the baseline's rules. The case puts `with` in its place, so the rules keep their order. |
| `with` | string | With `replace`, and only with it | The formula that replaces it |

**Rules that span keys:**

- **One change per variant.** An entry in `rules` holds `add`, or `replace` and `with`, never both. A variant that changes two settings isn't offered: each case differs from the baseline in one setting, as each of [R03-T01's checks](releases/0.3.0-experiments.md#what-r03-t01-verified) did.
- **Rule text.** `add`, `replace`, and `with` are written in quotes or as block scalars, as rules are. `replace` must be the same text as exactly one of the baseline's rules, character for character, once YAML has read both. Trial Folio doesn't read formulas, so it can't check that a replacement changes only a threshold: any replacement is a changed rule, and a formula is verified by its form, as every formula is.
- **A variant changes something.** A `value` must differ from the baseline's, after normalization: `0.250` is the baseline's `0.25`. `add` and `with` must not be the same text as any of the baseline's rules. More generally, every case resolves to settings of its own, so no two cases share a `case_id`. A variant that breaks this fails with `config.invalid`, and the message names it by its place in the file, such as `variants.max_holdings[0]`, never by its key, which is the user's text.
- **Lists.** Each list holds at least one entry, except `rebalance_weeks`'s, where an empty list turns the [default](#default-variants) off. `variants`, when it's given, holds at least one key.
- **At least one variant.** An experiment has at least two cases: the baseline, and at least one variant, its own or the default. An experiment whose only case is its baseline fails with `config.invalid`; a screen configuration runs one screen.
- **Not offered:** a variant that removes one of the baseline's rules. R03-T01 verified changed and added rules only. A baseline without the rule, and a variant that adds it, make the same comparison.

#### Default variants

[P-13](spec.md#proposed-defaults) sets one default for screens: rebalancing every 1 week and every 4 weeks. Where `variants` has no `rebalance_weeks` key, Trial Folio adds a rebalance variant for each of those two values that isn't the baseline's. 1 and 4 are the only values [verified](#screen-configuration), so it always adds exactly one, keyed `rebalance-weeks-1` or `rebalance-weeks-4`, with no description.

- **A list replaces it.** A `rebalance_weeks` list replaces the default, and an empty list turns it off. A paper reproduction follows [METH-09.4](methodology.md#meth-09-reproducing-published-research)'s variant set instead of P-13's, so its configuration turns the default off.
- **It's a case like any other.** The plan shows it, the budget must cover it, and the research history records it. It adds one request, and so 5 credits at the documented cost.

#### Cases and their order

- **How a case resolves.** A case's settings are the baseline's with its one change. Its request follows the screen configuration's "Sent as" mapping, and its `case_id` is computed as a screen run's is ([plan hashing](#plan-hashing)). So a case has the same `case_id` as a screen run with the same settings, whatever its key.
- **Order.** The baseline comes first. Then come the variants of `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`, in that order, the [screen settings](#screen-settings)' order, and within each setting in its list's order. The default comes in `rebalance_weeks`'s place. The order of the keys in `variants` doesn't matter, so it leaves no trace in the plan.

#### The experiment's budget

| Key | Type | Required | Rules |
|---|---|---|---|
| `provider_requests` | integer | Yes | At least the number of cases, and at most 1801439850948198. The most provider requests the experiment may send, counted as [budget and retries](#budget-and-retries) counts them, across every attempt of every case, including the attempts of each later `run` that resumes it. |

- **At least one per case.** So every case can be sent once. A smaller budget fails with `config.invalid`, and the message gives the number of cases. A larger one leaves room to [repeat a case](#repeating-a-case) whose request may have been charged.
- **Requests, not credits.** Trial Folio counts sends exactly, while credits depend on Portfolio123's price. The plan's budget gives the credits too, as `provider_requests` times the documented cost of a request ([budget and retries](#budget-and-retries)), and the plan display shows them.
- **Few enough that the plan's credits can be hashed.** The plan records its credits, `provider_requests` times the documented cost of a request, and [canonical hashing](#canonical-hashing) refuses an integer above 9007199254740991 (2^53 − 1), the limit on every integer a configuration gives ([screen configuration](#screen-configuration)). At 5 credits a request, the largest budget is 1801439850948198 requests, whose credits are 9007199254740990. A larger one fails with `config.invalid` as the file is read, and the schema gives the bound as the key's `maximum`. The bound follows the documented cost, so a version with another cost has another bound. The review of R03-T07's pull request added it ([changes after sign-off](releases/0.3.0-experiments.md#changes-after-sign-off)).

Plan 1.1.0 records the budget, with a bound on authentication calls equal to `provider_requests`, and the current plan's budget bounds the experiment across every run and revision ([the budget across runs](#experiment-plans-and-revisions)).

#### Experiment example

```yaml
kind: experiment
schema_version: 1.0.0
experiment_id: earnyield-sensitivity
title: Earnings yield sensitivity
purpose: How do holdings, slippage, and a stricter liquidity rule change the earnings-yield screen's results?
prior_research:
  status: partial
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
      description: A stricter liquidity floor, 100 million dollars a day.
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

It compiles to five cases, in this order: `baseline`, `liquidity-100m`, `holdings-50`, the default `rebalance-weeks-1`, and `slippage-050`. Its budget allows one request more than the cases need.

An added rule is written like this. On a baseline whose universe is `'Easy to Trade US'`, with the settings above, this variant excludes microcaps, and the empty `rebalance_weeks` list turns the default off, so the experiment has two cases:

```yaml
variants:
  rules:
    - key: no-microcaps
      description: Excludes stocks with a market cap of 300 million dollars or less.
      add: 'MktCap > 300'
  rebalance_weeks: []
```

These examples are validated in two ways:

- **Against Portfolio123.** Each case resolves to a request Portfolio123 accepted:
  - `baseline` to R01-T01's [`request.json`](../reference/p123api-screen-backtest/request.json), as the [screen example](#example) does
  - `liquidity-100m` and `slippage-050` to those of R03-T01's [`liquidity-100m.yaml`](../reference/variant-capabilities/liquidity-100m.yaml) and [`slippage-050.yaml`](../reference/variant-capabilities/slippage-050.yaml)
  - `holdings-50` to that of the 0.2.0 live exercise's [`holdings-50.yaml`](../reference/review-live-exercise/holdings-50.yaml)
  - `rebalance-weeks-1` to R01-T05's [`request-weekly.json`](../reference/p123api-screen-backtest-values/request-weekly.json)
  - the second example's two cases to those of R03-T01's [`easy-to-trade.yaml`](../reference/variant-capabilities/easy-to-trade.yaml) and [`no-microcaps.yaml`](../reference/variant-capabilities/no-microcaps.yaml)
- **Against this format.** On 2026-10-07, R03-T02 read each example, the second as a whole file with those settings, with Trial Folio 0.2.1's YAML reader, which found every text Portfolio123 receives quoted. It then checked each rule above, compiled the cases, and validated each case as a screen configuration with 0.2.1's model. Each case's `case_id` and request equal those of its screen configuration, read by 0.2.1, or its committed request. The same check, run on altered copies, failed on each of these: a wrong reference, an unquoted rule, a `value` equal to the baseline's, a budget smaller than the number of cases, a key that's the default's, a `replace` that isn't one of the baseline's rules, and an empty `max_holdings` list.

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
- **Schemas.** `schemas/metrics-row-1.0.0.schema.json`, `schemas/settings-row-1.0.0.schema.json`, and `schemas/differences-row-1.0.0.schema.json` each describe one row, after a CSV adapter step has read its cells: an empty cell is `null`, `critical` and `flagged` are booleans, `source_decimals` and `difference_decimals` are integers, the period dates are dates, and `flags` is an array of codes. A property's position is its column's.

**Writing and reading them.** `src/trialfolio/normalization.py` normalizes a saved response, and `src/trialfolio/tables.py` writes the tables and reads them back (R01-T12):

- **Which runs have them.** A run's tables are written only from a decoded response with the [required structure](#p123api-screen-backtest-version-1): `normalized/metrics.csv`, then `normalized/settings.csv`. A response saved undecoded, as `response.raw`, or without that structure, is `provider.response_invalid`, and neither table is written: the normalized result is unavailable. An attempt that didn't succeed has no response to normalize, and no tables.
- **The label.** A run's rows carry its case's `case_id` as their `label`: the identity of the resolved settings, which the attempt's directory names too. So two runs of the same configuration label their rows the same. An experiment's case has tables of its own, labeled the same way ([an experiment's normalized tables](#an-experiments-normalized-tables)).
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

An experiment's case takes `original_key` and `original_value` from the experiment configuration, as [an experiment's normalized tables](#an-experiments-normalized-tables) says.

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
| `baseline_value`, `value` | The two values being compared, as the runs' tables write them. Empty for a metric value that's unavailable, or a setting missing from a run, which is `unknown`. |
| `unit` | Unit of the two values. Empty for a setting without one, as in `settings.csv`. |
| `classification` | For settings: `same`, `intended_change`, `unexplained_mismatch`, or `unknown`. For metrics: `differenced`, `not_comparable`, or `unavailable`. |
| `difference` | For `differenced` metrics: `value − baseline_value`. Empty otherwise. |
| `difference_unit` | `pp` for percent metrics, `days` for dates, otherwise the metric's unit. Empty when there's no difference. |
| `difference_decimals` | The smaller of the two source decimal counts, and 0 for dates and counts. Empty when there's no difference. |
| `reason` | For `not_comparable` or `unavailable`: `different_benchmark`, `different_period`, `unknown_period`, `different_unit`, or `input_unavailable`. Empty otherwise. |
| `declared_reason` | For a setting the configuration declares as an intended change, the reason it gives, whatever the classification, so a change that wasn't observed still shows what was intended. Empty otherwise. |
| `flagged` | `true` when the row needs the reader's attention: a critical `unexplained_mismatch` or `unknown`, or any row with a warning flag |
| `flags` | Flag codes, separated by semicolons. Empty when none apply. |

#### Differences between screen runs

R02-T01 took these names from 0.1.0's [screen settings](#screen-settings) and [metrics](#p123api-screen-backtest-version-1). Like the rest of 0.2.0's contracts, they're requirements since [0.2.0](releases/0.2.0-review.md)'s sign-off (2026-10-05), which confirmed the choices in its [open questions](releases/0.2.0-review.md#open-questions). R02-T06 wrote them as the comparison core, `compare` in `src/trialfolio/differences.py`, which compares the runs the [input check](#review-output) read. `src/trialfolio/tables.py` writes the table, and reads it back as the other tables.

For each result except the baseline, in the order the review configuration lists them, `differences.csv` has:

- **Its labels.** `label` and `baseline_label` are the review configuration's labels. The copied `metrics.csv` and `settings.csv` keep their own `label`, the run's `case_id`, because they're copied byte for byte. The review manifest's `results` record which run each label names ([review output](#review-output)). Two results may name runs of the same case, such as two runs of one configuration, and their labels tell them apart.
- **23 setting rows,** one for each screen setting, in that table's order. `name` is the setting, and `category`, `critical`, and `unit` are its row's in `settings.csv`. `baseline_value` and `value` are the two runs' `value` cells.
  - **A run without tables.** A review can include a run whose attempt didn't succeed, or whose response was invalid, as an [open question](releases/0.2.0-review.md#open-questions) settled. That run's [plan](#plan-contents) stands in for its `settings.csv`. Each setting's `category`, `critical`, `unit`, and `flags` are its plan row's, and its value is written as `settings.csv` writes it. So its date rows never carry `coverage_mismatch`, which needs a response.
  - **Same values.** Two values are the same when they read as the same value: a list or a ranking as JSON, and anything else as its text. A decimal is normalized before it's written, so `0.250` and `0.25` are both written `0.25`. A list keeps its order, as a case's identity does, so the same rules in another order differ. Two runs that both leave a parameter unsent have the same token, `not_sent`, and are `same`.
  - **Not differenced.** A setting row's `difference`, `difference_unit`, and `difference_decimals` are empty.
- **20 metric rows,** one for each of the layout's metrics, in that table's order. A metric is named by `subject` and `metric_id` together, because rows 15–20 reuse the identifiers of rows 4–9 for the benchmark.

A metric row is `unavailable`, with `input_unavailable`, when either value is unavailable. That run's copied `metrics.csv` holds the value's own reason, which the report gives. Otherwise the row is `differenced` when the table below allows it, and `not_comparable` when it doesn't:

| Rows | Metrics | Differenced only when | Difference unit |
|---|---|---|---|
| 1–2 | `coverage_start` and `coverage_end` | Always. Coverage is the period, so the period rule doesn't apply to it. | `days`: the calendar days from the baseline's date to the result's |
| 3 | `coverage_periods` | Always, as rows 1–2 | `count` |
| 4–9, 14 | The strategy's `total_return`, `annualized_return`, `max_drawdown`, `standard_deviation`, `sharpe_ratio`, `sortino_ratio`, and `risk_samples` | The two periods are the same | `pp`; `ratio` for `sharpe_ratio` and `sortino_ratio`; `count` for `risk_samples` |
| 10–13 | `correlation`, `r_squared`, `beta`, and `alpha`, the benchmark-relative metrics, which name the benchmark in their `benchmark` cell | The periods are the same, and so are the `benchmark` cells | `ratio`; `pp` for `alpha` |
| 15–20 | Rows 4–9 for the benchmark, which describe the benchmark itself | The periods are the same, and so are the runs' `benchmark` settings | As rows 4–9 |

- **Periods.** A metric's period is its `period_start` and `period_end`, which are its run's coverage. A period is known when both its dates are, and two periods are the same when both are known and equal. A different period gives `different_period`. A period that's unknown in either run gives `unknown_period`, so coverage that couldn't be established is never shown as matching.
- **Benchmarks.** A different benchmark gives `different_benchmark`. The strategy's other metrics don't depend on the benchmark, so they're differenced whatever it is.
- **Units.** Layout version 1 fixes each metric's unit, so two runs read with it never differ in unit. `different_unit` is for a later layout that changes one.
- **One reason.** When several reasons apply, `reason` gives the first of `different_unit`, `different_benchmark`, and `different_period` or `unknown_period`. The setting rows show every difference behind it.
- **Decimals.** `difference_decimals` is the smaller of the two values' `source_decimals`, and 0 for dates and counts. A difference with more decimal places is rounded to it, half to even. `source_decimals` counts the digits the saved value has ([numbers and precision](#p123api-screen-backtest-version-1)). Saving drops trailing zeros, but a whole number saved as a float keeps its `.0`. So `12.5` has one decimal place even when it was requested at 4, and so does `12.0`: `12.46` against a baseline of `12.0` gives `0.5`, never `0`.
- **Writing a difference.** `difference` has exactly `difference_decimals` digits after the decimal point, as a value in `metrics.csv` has its `source_decimals`, so `12.35` against `12.25` gives `0.10`. A difference of zero is written without a sign: `151.68` against `151.7` rounds to `-0.0`, which is written `0.0`, and so is `-0.0` against `0.0`.
- **Flags.** A row's flags are written in the order of the [flag codes](#flag-codes) table, so the same runs always give the same cell.

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
- **Authentication in 0.1.0.** A start record holds exactly one successful authentication exchange (`response`, status 200). An attempt record holds at most one authentication exchange, before any request exchange. Failed authentication is valid only in a failed attempt with no request exchange. An attempt may fail before authentication starts, with no exchanges. Sending a request, or recording its uncertain completion on restart, requires successful authentication. An experiment's records are version 1.1.0, in which an attempt may send with a token an earlier attempt of the same run obtained ([experiment attempts](#experiment-attempts)).
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
- **An `unknown` attempt** is never retried automatically, because the original request may have been charged or may have changed provider state. `unknown` always means that no response was durably recorded. From 0.3.0, the user can repeat an experiment's case on purpose, confirming the possible repeat charge ([repeating a case](#repeating-a-case)).

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

Schema version 1.0.0, introduced in 0.1.0 (task R01-T04). A 1.0.0 plan has exactly one case; release 0.3.0's plan 1.1.0 adds several cases and revisions ([experiment plans and revisions](#experiment-plans-and-revisions)). `plan.json` holds:

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
- **Nothing varies between invocations.** The plan holds no timestamps, output directory, file paths, attempt IDs, credentials, or account information. So the same configuration, Trial Folio version, and versions of `p123api`, `requests`, and `urllib3` give the same plan and hash on any machine, at any time, and for any output directory. That's what lets a user review a plan in one command and approve it in the next. A 1.1.0 plan also depends on the plan it revises ([experiment plans and revisions](#experiment-plans-and-revisions)).
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

Text from the configuration, and a revision's reason ([approving a revision](#experiment-plans-and-revisions)), is shown with its control and formatting characters, Unicode's categories Cc and Cf, and the line and paragraph separators, written as escapes such as `\u001b`, so a title, formula, or reason can't move the cursor, clear the terminal, or reorder what's shown.

**Order of steps in `trialfolio run`.** Trial Folio creates no output and sends no request before step 7. So a plan can be reviewed, and its hash obtained, without credentials.

1. Check the license acknowledgment (`license.not_acknowledged`).
2. Validate the configuration (`config.invalid`).
3. Check that the output directory is absent or empty (`output.not_empty`). An experiment's configuration may also name a directory that holds that experiment, to resume or revise it ([running an experiment](#running-an-experiment)).
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

In 0.1.0, a hash that doesn't match is `plan.approval_required`. `plan.changed` is for a saved plan that the configuration no longer resolves to, which arrives with resuming experiments in 0.3.0 ([experiment plans and revisions](#experiment-plans-and-revisions)).

### Experiment plans and revisions

Plan schema version 1.1.0, introduced in 0.3.0 (R03-T03). `trialfolio run` builds one from an [experiment configuration](#experiment-configuration). A screen configuration still gives a 1.0.0 plan, unchanged, so a screen run's artifacts, and the readers of them, stay as they are.

**Contents.** A 1.1.0 plan has every field of 1.0.0, with the same meaning and rules, except as follows:

| Field | Contents |
|---|---|
| `schema_version` | `1.1.0` |
| `experiment_id`, `title`, `purpose`, `prior_research` | The configuration's, with `user_supplied` provenance. `purpose` is never `null`, since an experiment's is required. `prior_research` holds its `status`, and its `description` or `null`. None of them is sent. |
| `revises` | The `plan_hash` of the plan this one revises, or `null` for the experiment's first plan (revisions, below) |
| `cases` | Every case, in the [order of cases](#cases-and-their-order), the baseline first. Each holds a 1.0.0 case's `case_id`, `requests`, and `settings`, with the same rules, and the three fields below. |
| `budget` | `provider_requests` is the configuration's `budget.provider_requests`, and `authentication_calls` is the same number (the budget across runs, below). `credits_per_request`, its source, and `credits` are as in 1.0.0. |

Each case also holds:

- **`case_key`:** `baseline`, the variant's `key`, or the [default variant](#default-variants)'s.
- **`description`:** the variant's `description`, with `user_supplied` provenance, or `null`. The baseline has none.
- **`variant`:** `null` for the baseline. For a variant, the `setting` it changes, and its change as the configuration gives it: a `value`, in the setting's JSON type, with a decimal as its normalized string; an `add`; or a `replace` and its `with`. Its `default` is true for P-13's default variant, and false otherwise.

**Consistency.** Besides 1.0.0's rules for each case: the first case is the baseline; the case keys are unique, and so are the `case_id`s; each variant's settings are the baseline's with exactly the change its `variant` gives; and the budget's `provider_requests` is at least the number of cases. A plan that breaks any of these is invalid.

**Field shapes (R03-T06).** A case holds `case_key`, `case_id`, `description`, and `variant`, then a 1.0.0 case's `requests` and `settings`. `variant` always holds `setting`, `value`, `add`, `replace`, `with`, and `default`, with `null` for each that doesn't apply: a variant of `max_holdings`, `rebalance_weeks`, or `slippage_percent` gives a `value`, and a variant of `rules` an `add`, or a `replace` and its `with`. The default variant is the plan's only variant of `rebalance_weeks`, keyed as [default variants](#default-variants) says, with no description. `schemas/plan-1.1.0.schema.json` gives every field.

**Hashing.** `plan_hash` and `case_id` are computed as for 1.0.0 ([plan hashing](#plan-hashing)). So the plan hash covers the research context, the case keys and descriptions, and `revises`, while a `case_id` covers only the case's settings: a case keeps its `case_id` whatever its key, its description, or the plan it's in. `revises` is the one field that depends on more than the configuration and the versions: it depends on the experiment's history. The same configuration, versions, and revised plan still give the same plan and hash, so a revision, too, can be reviewed in one command and approved in the next.

**Revisions.** Running an experiment's configuration again into its own output directory builds its plan again, from the configuration and the installed versions, with the `revises` of the experiment's current plan, the latest one approved ([running an experiment](#running-an-experiment)). It compares that plan with the current plan:

- **The same plan resumes.** If it equals the current plan, the run resumes the experiment. That's so even when the file's bytes differ in a way no plan records, such as a comment, the order of keys, or `0.250` for `0.25` ([settings in the plan](#plan-contents)).
- **Anything else is a revision.** The revision is that plan with its `revises` set to the current plan's hash, and that's the plan shown, hashed, and approved. Anything a plan holds changes it, so each of these is a revision:
  - a changed setting of the baseline other than its universe, a changed setting of a variant, an added or removed variant, or a changed `rebalance_weeks` list, which changes the cases;
  - a changed `title`, `purpose`, or `prior_research`;
  - a changed case key, description, or `variant`, or a new order of one setting's variants. A `variant` can change while the case's settings don't, as when a `rebalance_weeks` list gives the [default variant](#default-variants)'s value, which makes its `default` false;
  - a changed budget;
  - a new version of Trial Folio, `p123api`, `requests`, or `urllib3`, even with the same configuration ([open question](releases/0.3.0-experiments.md#open-questions)). Its revision records both versions of each, and is a change of versions, not of the configuration.
- **Another `experiment_id` or universe isn't a revision.** Either makes another experiment, so its configuration can't run in this directory: `output.not_empty`, and the message says that it's another experiment, to run into a new output directory. The message names neither experiment's `experiment_id` nor either universe, which are the user's text, so it can be logged as it is ([logging](#logging-and-local-diagnostics)) (R03-T07).
  - **Another `experiment_id`** names another experiment. The alternative was a revision that renames the experiment, which would give one experiment's history two identities.
  - **Another universe** is a separate experiment ([D-19](spec.md#decisions)), which no release through 0.3.0 varies within an experiment. As a revision, it would retire every case and keep it in the record, so one experiment would hold cases on two universes.

**What a revision keeps.** A case is its `case_id`: the identity of its settings.

- **A case whose settings didn't change** keeps its `case_id`, and so its attempts. A succeeded attempt still completes it, whatever plan it ran under and whatever key the case has now. That's so after a change of versions too: the case's request is what its settings send.
- **A case whose settings changed** is a new case, with a new `case_id`, even when its key is the same. The old case is retired: no plan from then on includes it, and it and its attempts stay in the record, which counts and reports them ([experiment output](#experiment-output)).
- **A removed variant's case** is retired the same way. A later plan that includes the same settings again, under any key, includes that same case again, with its attempts.

**Approving a revision.** A revision needs a reason and the approval of its plan:

- **The reason** is the user's account of why the plan changed, given with `--revision-reason <text>`: 1–2,000 characters, not all whitespace, like a purpose. The revision's `experiment.json` records it with `user_supplied` provenance. It's never sent and never logged, and the report shows it. Every revision needs one, including a change of versions, so the record says why each plan replaced the one before it ([open question](releases/0.3.0-experiments.md#open-questions)).
  - **An invalid reason** is a usage error, which the parser reports before any other check: exit 2, without a JSON summary, as for a blank `--out` ([CLI behavior](#cli-behavior)). That's a reason that's empty, all whitespace, longer than 2,000 characters, or not valid UTF-8 text, which `experiment.json` couldn't hold.
  - **On a terminal,** the plan display shows the reason with its control and formatting characters written as escapes, as it shows text from the configuration ([the plan display](#approval)).
- **The approval** is the revised plan's hash, by `--approve` or by interactive confirmation, as for any plan ([approval](#approval)). The full display shows the plan, what changed from the current plan, the reason, and the experiment's progress so far, and the confirmation asks to approve the revision.
- **Without both, `plan.changed`.** The command then fails with `plan.changed`, exit 3, and sends and writes nothing. That includes an `--approve` with any other hash, the current plan's included, a refused confirmation, and a revision without a reason. The message says that the configuration or the versions changed since the current plan, gives the revision's hash, and gives the options that approve it.
- **A reason with no revision** fails with `plan.approval_required`, exit 2, and sends nothing. That's `--revision-reason` with a new experiment, with a screen, or with a configuration that still gives the current plan. A reason for a change that isn't there suggests that the configuration given isn't the one the user changed. The message says that the configuration gives the current plan, and to run without `--revision-reason` to resume it.
- **The same reason resumes.** The exception is a reason that's exactly the one the current plan's `experiment.json` records, character for character, with a configuration that gives the current plan: that's the command that approved the revision, run again, such as after an interruption. It resumes the current plan, as the same command without the reason would, and records nothing more about the reason. So the same command resumes an experiment after a revision too.

**Resuming needs approval too.** A run that resumes the same plan needs its approval, by the same hash, as every `run` that sends does: the core executes a plan only when it's given the plan's hash, and the CLI obtains it in each command ([approval](#approval), [REQ-04](spec.md#enduring-requirements)). So the same command resumes the experiment: the same `--approve` approves the same plan, and on a terminal the user sees the progress and confirms. One approval covers the whole plan, every case and the whole budget; it's never asked for case by case ([open question](releases/0.3.0-experiments.md#open-questions)).

**The budget across runs.** The current plan's budget bounds the whole experiment ([the experiment's budget](#the-experiments-budget)). Trial Folio counts against it every attempt of the experiment: those of every case, retired cases included, under every plan, in every `run`.

- **Provider requests** are counted as [budget and retries](#budget-and-retries) counts them: each send that may have reached Portfolio123, with a `running` attempt counted as one. Before each send, Trial Folio checks that one more stays within `provider_requests`.
- **Authentication calls** are Trial Folio's own authentication calls, whatever their result. Each attempt makes at most one, and writes its [authentication record](#experiment-attempts) durably before it, so a call is counted even when the process is killed before the call's exchange is recorded. Each attempt counts the `POST /auth` exchanges of its attempt record, or of its start record when it has no attempt record yet, or one when its authentication record is its only record. Trial Folio authenticates only to send: before a run's first request, and again only before a request that follows a 401 or 403 ([HTTP exchanges](#http-exchanges)). Before each call, it checks that one more stays within `authentication_calls`, which equals `provider_requests`. So a run that sends authenticates once, and again only after a 401 or 403. Only a call that no send follows, such as a failed authentication, or one followed by an interrupt, can bring the count above the requests sent. Either ends the run, a failed authentication by stopping it (below), so a run makes at most one such call.
- **When the budget is spent,** the case that would exceed it isn't started, and neither are the cases after it, as the [release's failure behavior](releases/0.3.0-experiments.md#failure-and-incomplete-data-behavior) says. Each keeps its outcome: one without an attempt stays not yet run. A revision that raises `budget.provider_requests` lets them run. A revision may set a budget below what's already counted; then nothing more is sent.
- **A failure that every later case would get** stops the run too ([D-32](spec.md#decisions)): Trial Folio's own authentication call fails, whatever its result, or a request gets `provider.quota_exceeded`. The run records that case's attempt, and starts no later case, as when the budget is spent, so wrong credentials or a spent quota can't fail every remaining case, each after an authentication call. The cases not started keep their outcomes. The run ends with its report and manifest, and with `execution.partial`, exit 6, as when the budget is spent; the message names the error, and says that a resume runs the cases not started once the cause is fixed. A request that got `provider.quota_exceeded` may have been charged, so a resume doesn't send it again automatically ([the cases that are due](#running-an-experiment)).
- **The display** gives the budget, the requests and authentication calls counted so far, and what remains, and names the cases the remaining budget can't cover.

## Artifact storage

**Requirement (REQ-05).** All artifact reads and writes go through the `ArtifactStore` interface. From 0.1.0 it has a local filesystem implementation.

- **Relative paths.** Paths in manifests are relative to the output root, never absolute, so a moved or served directory stays valid. The store takes only such paths: segments separated by `/`, none of them empty, `.`, or `..`, and no `\`, `:`, or NUL, which no file name holds, the same rule the models apply.
- **Immutability.** Source artifacts are never modified after they are written. Trial Folio never overwrites an existing artifact; corrections and migrations produce new artifacts.
- **Atomic writes.** Each file is written to a temporary name in the same directory, flushed and synced to disk, and then published under its final name without replacing anything. The one exception is the file that [claims an output directory](#cli-behavior), which is created directly under its final name.
  - **Never replace.** If the final name exists, even because another process created it at the same moment, publishing fails, and the temporary file is removed. So a record that changes state is written as a new file, never over an old one: an attempt's start record and its attempt record are two files ([execution outcomes](#execution-outcomes-and-attempts)).
  - **Linux and macOS.** `os.rename` and `os.replace` silently replace an existing file there, so they aren't used. Trial Folio hard-links the temporary file to the final name with `os.link`, which fails if the name exists. It then removes the temporary name and syncs the directory.
  - **Windows.** `os.rename` fails if the name exists, so it's used.
  - **No hard links.** On Linux and macOS, a file system without hard links, such as FAT or exFAT, can't take these writes. The first atomic write, which for `run` is `configuration.yaml`, fails with `storage.write_failed`, before any request is sent, and the message says why. `os.link` reports it with `ENOTSUP` on macOS, `EPERM` on Linux, as link(2) documents, or `ENOSYS`, which libfuse returns for a file system without a link operation. Only an error from `os.link` is read this way. On Windows, `os.rename` works on those file systems.

    R01-T08 tried the store on exFAT and FAT32 disk images on macOS 26.6.2, with Python 3.12.13: the claim succeeded, and writing `configuration.yaml` failed with `storage.write_failed` and the message "the output directory's file system doesn't support hard links (Operation not supported)". The claim's `plan.json` was left, without a manifest. On 2026-10-04, the claim failed there instead, with `output.not_empty`, until it read its file's identity once written ([claiming the directory](#cli-behavior)). `trialfolio demo` onto the same kinds of disk images then gave R01-T08's result again.
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

A review's layout is in [review output](#review-output), and an experiment's, with `experiment.json` and its lock file, in [experiment output](#experiment-output).

A run's manifest records the following. A review's records what [review output](#review-output) lists.

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

### Review output

Introduced in 0.2.0 (R02-T02). Like the rest of 0.2.0's contracts, it's a requirement since [0.2.0](releases/0.2.0-review.md)'s sign-off (2026-10-05), which confirmed the choices in its [open questions](releases/0.2.0-review.md#open-questions). `trialfolio review` writes:

```text
<out>/
  manifest.json                                     the review manifest, written last
  configuration.yaml                                byte-for-byte copy of the review configuration; claims the directory
  inputs/<label>/                                   one for each result, in the configuration's order
    manifest.json                                   byte-for-byte copies of the run's files, at their paths in the run
    plan.json
    normalized/metrics.csv                          only when the run has normalized tables
    normalized/settings.csv                         only when the run has normalized tables
  normalized/differences.csv
  report.html
  logs/                                             diagnostics; excluded from hashes and from the manifest's evidence
```

**What it copies from each run.**

- **Its manifest, its plan, and its normalized tables, byte for byte.**
  - **The manifest** identifies the run, and lists each of its files with its hash, the ones the review doesn't copy included.
  - **The plan** holds the run's title and purpose, which the report shows; its resolved settings, from which a run without tables is compared ([differences between screen runs](#differences-between-screen-runs)); and the versions of `p123api`, `requests`, and `urllib3` it was planned with, which the run's manifest doesn't record.
  - **The tables** are what `differences.csv` compares. A run without them, because its attempt didn't succeed or its response was invalid, has none to copy.
- **Each copy keeps its path in the run,** under `inputs/<label>/`. So the copied manifest names each copied file by its path relative to `inputs/<label>/`, with its `artifact_id`, and the copies can be checked against it without the run.
- **Copies come from the bytes checked.** The review reads each run once, through the `ArtifactStore`, and checks that it's a [complete run](#reports), as `trialfolio report` does: each file its manifest lists, the response included, has the size and `artifact_id` the manifest records. It writes each copy from the bytes it read and checked, never by reading the run's file again, so a file changed after the check can't be copied.
- **Nothing else.** It doesn't copy the run's `configuration.yaml`, whose settings the plan and `settings.csv` hold; its start and attempt records, whose outcome the run's manifest gives; its request; its response; or its report. A response holds Portfolio123's data, including per-period series a review doesn't compare, and a review may be shared ([D-14](spec.md#decisions)). The copied manifest records the hash of each file left out, so anyone holding the run can check that it's the run reviewed.

**Its own files.**

- **`configuration.yaml`** is the review configuration, byte for byte: the source of the baseline, the labels, and each declared change and its reason. It holds each `run` path as the user wrote it. The manifest and the report never repeat those paths.
- **`normalized/differences.csv`** is the [`differences.csv`](#differencescsv) table, schema version 1.0.0.
- **`report.html`** follows [reports](#reports). It links `manifest.json` and each file that manifest lists, apart from itself, by its path in the review, and never links the runs. So a review that's moved or shared on its own keeps its links.

**Writing it.** After the [license acknowledgment](#license-acknowledgment), `trialfolio review`:

1. Validates the configuration (`config.invalid`).
2. Reads and checks each run, in the configuration's order (`input.not_found` for a directory that doesn't exist, `input.not_a_run`, or `artifact.unknown_schema_version`). Nothing is written until every run passes. The first result that fails is reported. R02-T05 wrote this check, `check_review_inputs` in `src/trialfolio/review_inputs.py`:
   - **Finding the run.** A `run` path is read from the configuration's directory, unless it's absolute, as [every configuration's file paths](#configuration-files) are. When nothing exists there, it's `input.not_found`, as for `trialfolio report`. The run is found and read at the one path the file system resolves, so a `..` after a symbolic link, such as a linked configuration directory, leads to the parent of the link's target, as opening the path does.
   - **Checking it.** Each run is read and checked as `trialfolio report` checks one, with each file read once, and the check keeps the bytes of the files the review copies. Two results that name the same run each read it.
   - **What a review also needs.** A run is also `input.not_a_run` when its manifest lists `plan.json` or a table without a schema version, which the review records for each copy, or when its attempts saved more than one response, because `results` gives one, and a screen run sends its request at most once. A run Trial Folio wrote has neither problem.
   - **Messages.** The message names the result by its label, and its `run` path as the configuration gives it: "Result `hold50`'s run directory (`runs/hold50`) isn't a complete Trial Folio run: it has no manifest.json. …". The logged message names the result by its position instead, "Result 2's run directory", as [labels in logs](#review-output) below says. Each run that passes is logged as `review.input.loaded`, by its result's position, with the `artifact_id` of its manifest, its `plan_hash`, and its `case_id`.
3. Checks that the output directory is absent or empty (`output.not_empty`). As for `trialfolio report`, a run that fails its check is reported even when the output directory isn't empty.
4. [Claims the output directory](#cli-behavior) with `configuration.yaml`, from the bytes read in step 1. Logging to `<out>/logs/` starts once the claim succeeds.
5. Writes each result's copies, in the configuration's order: `manifest.json`, `plan.json`, and then the tables. The first is the first [atomic write](#artifact-storage). So on Linux and macOS, a file system without hard links, such as FAT or exFAT, fails there, with `storage.write_failed`. On Windows, which publishes with `os.rename`, those file systems work.
6. Compares each result with the baseline. For each saved response that more than one result's run has, it logs a warning, `review.response.shared`, that names those results by their positions. Then it writes `normalized/differences.csv`, then `report.html`, then `manifest.json`. As for a run, the report is rendered from what the manifest will record, without its own entry.

A failure or an interrupt after the claim leaves no manifest, so the output is visibly incomplete, as for a run ([running the commands](#cli-behavior)). That includes a failure while `manifest.json` itself is written, even after the store published it, as when the sync of its directory fails: the review then discards it, through the `ArtifactStore`'s `discard`, which removes a file only while it holds exactly the failed write's bytes. The message says that the review is incomplete or, if the manifest can't be removed, that the review reads as complete although the command failed, and either way, to remove the output directory and run the review again. A review sends nothing, so, unlike a run's, it has no request to account for.

**The review manifest.** `manifest.json`, with `artifact_type: review` and schema version 1.0.0, records:

- `schema_version`, `artifact_type`, `trialfolio_version`, and `created_at`, as a run's manifest does.
- `review_id`: a new random UUID, version 4, for each review written. The [JSON summary](#json-summary) and the logs carry it too.
- `command`: `review`, its options, and when it started. As for a run, the options are `json`, as given, and neither the configuration's path nor `--out` is recorded ([running the commands](#cli-behavior)).
- `synthetic`: true when any result is synthetic.
- `outcome` and `error`: always `completed` and `null`, because a review writes its manifest only when it completes.
- `baseline`: the baseline's label.
- `results`: which run each label names, one entry for each result, in the configuration's order. Each entry agrees with the result's copies:
  - `label`
  - `run_manifest`: the `artifact_id` of the run's `manifest.json`, which identifies the run. Two results that name the same run have the same one.
  - `synthetic`: as the run's manifest gives it, true for the run `trialfolio demo` writes.
  - `plan_hash` and `case_id`: the run's. Two runs of one configuration have the same `case_id`, and their labels tell them apart.
  - `normalized_tables`: whether the run has normalized tables. When it hasn't, its settings are compared from its plan, and its metrics are unavailable.
  - `response`: the `artifact_id` of the run's saved response, `response.json` or `response.raw`, or `null` when it has none. Two results with the same one have byte-identical saved responses (`identical_source`). Two with `null` don't: neither has a response to share.
- `artifacts`: each file of the review except its own `manifest.json` and the logs, with its path, `artifact_id`, size, role, and schema version when it has one, as in a run's manifest. Every file but the report has one. The roles are `configuration`, `run_manifest`, `plan`, `metrics`, `settings`, `differences`, and `report`.
  - **`configuration.yaml`** is the review's one source artifact. Its [source record](#source-artifacts) gives the format `review-configuration`, version 1.0.0, `user_supplied` provenance, no parser version, and no provider operation. It's acquired when the command starts.
  - **Each copy** also gives the `label` of the result it was copied from. Its path is `inputs/<label>/` followed by its path in the run. Its `artifact_id` and size are the run's for that file ([R02-AC02](releases/0.2.0-review.md#acceptance-criteria)), and its schema version is the one the run records: the copied manifest's own `schema_version`, and for each other copy, the run manifest's entry's.
- `methods`: each analytical method applied, with its version. A 1.0.0 review applies one, `screen-run-differences`, version 1: the rules of [differences between screen runs](#differences-between-screen-runs). A change to those rules that could change a row of `differences.csv` makes a new version ([versioning](#versioning)).
- `license_id` and `notice_version`.
- `capabilities`: `return_series` is `absent`, since a review holds no per-period series, and `statistical_validation` and `trading_readiness` are `not_assessed`. Each copied run manifest says whether its run preserved per-period series.
- `counts`: `results`, the baseline included; the setting rows of `differences.csv` by classification, `same`, `intended_change`, `unexplained_mismatch`, and `unknown`, and how many are `flagged`; and its metric rows by classification, `differenced`, `not_comparable`, and `unavailable`, and how many are `flagged`.

A review's manifest has no `plan_hash`, `approval`, `parsers`, or `reproducibility`. A review sends nothing and parses no provider response: it reads a run's saved response only to check its size and `artifact_id`, and no parser interprets it. Each copied run manifest records its own run's parsers and reproducibility, which the report shows. `schemas/review-manifest-1.0.0.schema.json` gives every field.

**The JSON summary's `review_id` and counts.** As an [open question](releases/0.2.0-review.md#open-questions) settled, `ids` holds the `review_id` once the review has claimed its output directory: on success, and on a failure after the claim. A failure before the claim writes nothing, so its `ids` has none. For `review`, `results` is the manifest's, `settings_flagged` is its flagged setting rows, and `metrics_unavailable` its `unavailable` metric rows. `warnings` counts the warnings logged, as for any command. When the review fails, `results` is the number of results a valid configuration names, or 0. `settings_flagged` and `metrics_unavailable` are 0 when no `differences.csv` was written. Once it's written, they're its counts, even when the review then fails, as a run's `metrics_unavailable` is once its tables are written.

**Labels in logs.** As an [open question](releases/0.2.0-review.md#open-questions) settled, a label is the user's own text, a configuration value, which [logs](#logging-and-local-diagnostics) never hold. A logged event, and so a warning on stderr, names a result by its position in `results`, such as "result 2", and the report and the manifest give its label. An error's full message names the label, and its logged message gives the position instead ([errors](#errors)).

A copy's path holds its label too. The `ArtifactStore` logs each file it writes by its path, in `artifact.write.completed`, and its errors, such as `storage.write_failed`, name the path in their logged message. So the review gives the store, with each copy, a name for logs with the result's position in place of `inputs/<label>/`, such as "`manifest.json` of result 2". The store's events, and its errors' logged messages, use that name, and the errors' full messages keep the path. A run's paths hold no configuration value, so the store logs a run's files as before. R02-T08 made this change to the store: `ArtifactStore.write` takes the name for logs as `logged_as`, and logs a file by its path without one.

### Experiment output

Introduced in 0.3.0 (R03-T03). An experiment's output directory holds all of its plans, attempts, and records, and grows with each `run` of its configuration into it. No file in it is ever replaced ([atomic writes](#artifact-storage)), so each plan, and each run's report and manifest, is a new file:

```text
<out>/
  experiment.lock                                   the lock; claims the directory; not evidence
  plans/<n>/                                        one for each plan approved, numbered from 1
    configuration.yaml                              byte-for-byte copy of the configuration the plan was built from
    plan.json                                       plan 1.1.0
    experiment.json                                 the experiment's record as of this plan, written last
  cases/<case_id>/attempts/<attempt_id>/            every attempt, as for a run, with start and attempt records 1.1.0
    authenticating.json                             the authentication record, only when the attempt authenticates
  cases/<case_id>/normalized/metrics.csv            the case's normalized tables, once its attempt succeeds
  cases/<case_id>/normalized/settings.csv
  sessions/<s>/                                     one for each run that passed its checks, numbered from 1
    session.json                                    the session record, written before any other record of the run
    report.html
    manifest.json                                   the experiment manifest, written last
  logs/                                             diagnostics; excluded from hashes and from the manifest's evidence
```

Each case's normalized tables are in its own directory, as [an experiment's normalized tables](#an-experiments-normalized-tables) says (R03-T05).

- **Numbers.** `<n>` and `<s>` are decimal, without leading zeros. Each new one is one more than the largest in the directory, so a number is never reused.
- **No configuration values in paths.** A case's directory is named by its `case_id`, never its key, and plans and sessions by number. So, unlike a review's, an experiment's paths can be logged as they are ([labels in logs](#review-output)).
- **The current plan** is the one in the highest-numbered `plans/<n>/` that holds `experiment.json`. A plan's directory without one is a revision whose approval was never fully recorded, because the run stopped while writing it. Nothing was sent under it, since nothing is sent before `experiment.json` is written. It's left as it is, and no record counts it as a plan.
- **A session** is one `run` of the experiment that passes its checks and its approval, from then to its end.
  - **It starts with its session record.** Before it writes any other record of the experiment, or sends anything, it writes `sessions/<s>/session.json` durably, schema version 1.0.0: `schema_version`, `trialfolio_version`, `session`, its number, and `started_at`, when it was written. That reserves the number, which each attempt the session starts records ([experiment attempts](#experiment-attempts)). `schemas/session-record-1.0.0.schema.json` gives every field.
  - **It ends with its manifest.** One that reaches its end, whatever its cases' outcomes, writes its report, then its manifest, in its directory. One that stops on an interrupt, a storage failure, or an unexpected exception, or whose process is killed, writes no manifest, as a run doesn't ([running the commands](#cli-behavior)).
  - **The newest manifest supersedes the ones before it.** Since each run that changes the records reserves a session first, a run that stopped before its end always leaves a session numbered higher than any manifest written before it. So when the highest-numbered session has no manifest, the experiment's output is visibly incomplete, until a later run ends.

#### Experiment attempts

Each case's attempts are a run's, in `cases/<case_id>/attempts/<attempt_id>/` ([execution outcomes and attempts](#execution-outcomes-and-attempts)), with two differences: their start and attempt records, and an authentication record.

**Start and attempt records 1.1.0.** A run authenticates once, before its first request, and again only after a 401 or 403 ([release 0.3.0's required behavior](releases/0.3.0-experiments.md#required-behavior), 3). So an attempt that's sent with the token an earlier attempt of the same run obtained has no authentication exchange of its own. A 1.0.0 start record requires exactly one, so an experiment's start and attempt records are version 1.1.0:

- **The start record** holds the exchanges completed before the send: Trial Folio's successful authentication call, or none when the run already held a token.
- **The attempt record** holds every exchange of its attempt, as in 1.0.0. A request exchange, or an `unknown` outcome, requires successful authentication in the same run, which is its session: the attempt's own, or an earlier attempt's, whose token no 401 or 403 has since dropped.
- **Three fields place the attempt in its run, and name the authentication it used.** Both records hold them:
  - **`session`:** the number of the [session](#experiment-output) that started the attempt.
  - **`sequence`:** the attempt's place in its session: 1 for the first attempt the session starts, and one more for each attempt it starts after that. A session starts its attempts one at a time, so `sequence` orders them, and an earlier attempt of a session is one with a lower `sequence`. Their start times don't order them, because the clock can move backward between two attempts.
  - **`authenticated_by`:** the `attempt_id` of the attempt whose successful authentication gave the token its request was sent with: its own, or an earlier attempt's of the same session. A start record always has one, and an attempt record has one exactly when it has a start record, and the same one.

  An attempt record that a later run writes, for a `running` attempt or for one whose only record is its authentication record, keeps that record's `session` and `sequence`.
- **`repeat_of` records a repeat.** It's the `attempt_id` that the confirmation of a [repeat](#repeating-a-case) named, for an attempt that `--repeat` started, and `null` for any other. The start record, the attempt record, and the [authentication record](#experiment-attempts) all hold it, so an attempt record that a later run writes keeps it too.
- **Nothing else changes.** A screen run's records stay 1.0.0, where every attempt authenticates.

Release 0.3.0 had listed the attempt record as unchanged, and this follows its settled required behavior instead ([open question](releases/0.3.0-experiments.md#open-questions)). The owner confirmed it on 2026-10-08.

**The authentication record.** An attempt that makes Trial Folio's own authentication call first writes `authenticating.json` durably, in its directory, which it creates: schema version 1.0.0, with the `attempt_id`, `case_id`, `plan_hash`, `session`, `sequence`, `repeat_of`, and `started_at` that its start record will hold. An attempt that sends with a token the run already holds has none. Then it authenticates, and writes its files in a run's order ([writing the files](#execution-outcomes-and-attempts)). So each authentication call is recorded before it's made, and the budget counts it even when the process is killed before its exchange is recorded ([the budget across runs](#experiment-plans-and-revisions)). The record also holds `trialfolio_version`, as every artifact does ([versioning](#versioning)) (R03-T06).

`schemas/authentication-record-1.0.0.schema.json`, `schemas/start-record-1.1.0.schema.json`, and `schemas/attempt-record-1.1.0.schema.json` give every field.

An attempt that has its authentication record, and neither a start record nor an attempt record, stopped after writing it and before its send, perhaps during its authentication call. A resume writes its attempt record, as it does a `running` attempt's: `failed`, not possibly charged, because nothing was sent, with the error code `command.interrupted`, as an interrupt during authentication gives ([interrupts](#interrupts)). Its one exchange is the authentication call's, recorded as `interrupted`, because nothing shows whether the call was made, or how it ended. A `request.json` it wrote is left as it is, and the attempt record references none.

#### An experiment's normalized tables

Introduced in 0.3.0 (R03-T05). Each case whose attempt succeeds has a run's two tables, `metrics.csv` and `settings.csv`, schema version 1.0.0, in `cases/<case_id>/normalized/`. They have a screen run's columns and rows ([normalized tables](#normalized-tables)). So the experiment's tables cover every case that has a result, and a case's rows are those of a screen run with the same settings and response, apart from the three columns below.

- **When they're written.** Right after the attempt record of the case's succeeded attempt, `metrics.csv` and then `settings.csv`, before the next case starts, as a run writes its tables after its attempt record ([running the commands](#cli-behavior)). They're written from the attempt's saved response, by the rules of [writing and reading them](#normalized-tables): a response saved undecoded, or without the required structure, is `provider.response_invalid`, and the case has no tables. A case has at most one succeeded attempt, because a complete case is never sent again ([the cases that are due](#running-an-experiment)), so its tables are written once and never replaced.
- **The label** is the case's `case_id`, as a run's is. So a case and a screen run with the same settings label their rows the same, whatever the case's key.
- **`original_key` and `original_value`** come from the configuration of the plan the attempt ran under, `plans/<n>/configuration.yaml`. `original_key` is the key path in that file, with each list position in brackets, counted from 0, as the configuration's messages name a variant:
  - **A setting the case takes from the baseline:** `baseline.` and the setting's key, such as `baseline.max_holdings`.
  - **The setting the case's variant changes:** the variant's change, `variants.<setting>[<i>].value`, such as `variants.max_holdings[0].value`. For a rule, it's `variants.rules[<i>].add` or `variants.rules[<i>].with`: the formula the case adds, or puts in place of `replace`. The case's other rules are the baseline's, whose text is in `baseline.rules`.
  - **The default variant's `rebalance_weeks`,** which no key of the file writes, and the rows that no key supplies in a screen run either: empty.

  `original_value` is the value's text at that key, by the rule a screen run's follows ([`settings.csv`](#settingscsv)).
- **`source_artifact`** is, in `settings.csv`, the `artifact_id` of that `plans/<n>/configuration.yaml`, and in `metrics.csv`, the saved response's, as in a run.
- **Tables a run didn't write.** A run that stops after a case's attempt record, on an interrupt, a storage failure, or a killed process, may leave the case without its tables. The next resume writes them in its step 8 ([running an experiment](#running-an-experiment)): for each complete case without them, and for each `running` attempt it records as `succeeded` from its saved response. A case with `metrics.csv` and no `settings.csv` gets its `settings.csv`. The resume writes them from the bytes of the response its check read, never by reading the file again, and from the configuration of the plan the attempt ran under.
- **Which parser wrote them.** A case's `metrics.csv` is its response, read by the parser of the Trial Folio that wrote the table, and each session's manifest names that parser in the response's source record ([the experiment manifest](#the-experiment-manifest)). For a table the latest manifest lists, that manifest names its parser. A table it doesn't list was written by a session that stopped before its end, and no record names its parser. So the resume's check reads the response again with the installed parser, and the table must be exactly what that parser writes; the new manifest then names the installed parser. A table that isn't, as after an upgrade whose parser reads the response differently, fails the check with `input.not_a_run`, and the message says to resume first with the Trial Folio version that wrote it, one of those the sessions since the latest manifest record in their `session.json`, so that a manifest names its parser. `settings.csv` is drawn from the configuration, which no parser reads ([source artifacts](#source-artifacts)), so the installed Trial Folio completes a pair whichever version wrote its `metrics.csv`.

#### `experiment.json`

Schema version 1.0.0. Each `plans/<n>/` holds one, written once, after the plan's `configuration.yaml` and `plan.json` and before any request is sent under the plan. It records the experiment as that plan declares it, and the history of its plans. So the current plan's `experiment.json` is the experiment's research record: its purpose, its planned and retired cases, its declared prior research, and every revision with its reason ([METH-03](methodology.md#meth-03-research-history-and-multiple-testing); R03-AC03). It holds:

- `schema_version`, `trialfolio_version`, and `created_at`, when it was written.
- `experiment_id`.
- **The declaration,** as the plan holds it, with `user_supplied` provenance: `title`, `purpose`, and `prior_research`, its `status` and its `description` or `null`. Trial Folio can't verify any of it, and the report says so.
- **The planned cases,** as the plan holds them, in its order: each case's `case_key`, `case_id`, `description`, and `variant`.
- **The retired cases:** each case an earlier plan included and this one doesn't, by its `case_id`, with the `case_key`, `description`, and `variant` it had in the last plan that included it, and that plan's number.
- **The plans:** one entry for each plan of the experiment, oldest first, ending with this one. Each entry holds:
  - the plan's number, its `plan_hash`, and its `revises`;
  - the `artifact_id`s of its `plan.json` and `configuration.yaml`;
  - how it was approved, `interactive` or `option`, or `not_required` for each plan of a [synthetic experiment](#the-experiment-manifest), and for no other plan;
  - its `reason`: `null` for the first plan, and the `--revision-reason` text for a revision;
  - for a revision, what changed from the plan before it: each version that changed, with both values; the cases it added and retired, by `case_id` and key; and which other parts changed, of `title`, `purpose`, `prior_research`, `budget`, the case keys, the case descriptions, the case variants, and the order of cases. A case's `variant` can change while its settings don't, so the case is kept: a `rebalance_weeks` list that gives the default variant's value, for one, makes that case's `default` false, and nothing else changes. A revision whose only change is of versions is recorded as such, not as a changed configuration.

  The entries before the last are the earlier plan's `experiment.json`'s, unchanged, so the history can be checked one plan at a time.

It records no outcome. Attempts end after it's written, and their records hold their outcomes, which each manifest counts.

**Field shapes (R03-T06).** The planned cases are `planned_cases`, and the retired ones `retired_cases`, each with `plan`, the number of the last plan that included it. Each entry of `plans` holds `plan`, the plan's number; `plan_hash`; `revises`; `plan_artifact_id` and `configuration_artifact_id`; `approval`; `reason`; and `changes`, `null` for the first plan. A revision's `changes` holds:

- `versions`: each version that changed, with its `package`, `trialfolio`, `p123api`, `requests`, or `urllib3`, in that order, and its `previous` and `current` version;
- `cases_added` and `cases_retired`: each case by its `case_id` and `case_key`;
- `parts`: the names of the other parts that changed, of `title`, `purpose`, `prior_research`, `budget`, `case_keys`, `case_descriptions`, `case_variants`, and `case_order`, in that order.

A revision changes something a plan holds, so its `changes` record at least one change. The plans' numbers start at 1 and increase, but may skip a number: a plan's directory without `experiment.json` isn't part of the history ([experiment output](#experiment-output)). `schemas/experiment-record-1.0.0.schema.json` gives every field.

**What a revision records (R03-T07).** A case is its `case_id`, so the revision's changes compare the cases by it:

- **The case parts are changes to kept cases.** `case_keys`, `case_descriptions`, and `case_variants` say that a case both plans include has another key, description, or `variant` in the revision, and `case_order` that the cases both include come in another order. An added or retired case is recorded only in `cases_added` or `cases_retired`, even when it has a retired case's key: `holdings-50` with another value is a case added and a case retired, and no changed key. The alternative was to compare the keys, descriptions, variants, and order of every case, which would record each added or retired case a second time, as a changed key and a new order.
- **A case planned again** is in `cases_added`, under the key it has now, and leaves `retired_cases`, since it's a case this plan includes ([what a revision keeps](#experiment-plans-and-revisions)).
- **The order of the lists.** `cases_added` follows the revision's order of cases, and `cases_retired` the current plan's. `retired_cases` keeps the current plan's `experiment.json`'s entries, in their order, without the cases planned again, and then gives the cases the revision retires, in the current plan's order. So the retired cases come in the order of the last plan that included each, and those of one plan in its order.
- **`budget`** is any change to the plan's budget, not only to `provider_requests`: a new Trial Folio version may also bring another documented cost, and so other credits, which the user approves. That revision is then a change of versions and of the budget. The alternative was to compare only `provider_requests`, so that a revision whose configuration didn't change would always be a change of versions alone, though the credits shown changed.

#### The lock

Only one process runs an experiment at a time ([release 0.3.0's included scope](releases/0.3.0-experiments.md#included-scope)):

- **The file** is `experiment.lock`, in the output directory. The experiment's first run [claims the directory](#cli-behavior) with it, and nothing removes or rewrites it afterwards. It holds one fixed line, which says it's Trial Folio's experiment lock, so it's never empty, as a claim requires. It isn't evidence: no manifest lists it, and, like `logs/`, it's excluded from hashes.
- **The lock** is an exclusive advisory lock on the open file, taken without waiting: `fcntl.flock` with `LOCK_EX | LOCK_NB` on Linux and macOS, and `msvcrt.locking` with `LK_NBLCK` on the file's first byte on Windows. It's `flock`, and not `fcntl`'s record locks, because a process loses a record lock when it closes any descriptor of the file.
- **Held by another process,** it fails the command with `experiment.locked`, exit 4. The command sends nothing, and leaves nothing written: a new experiment's claim removes what it created.
- **When it's taken.** A new experiment takes it during the claim, on the descriptor that created the file, before writing the file's line. A resumed experiment takes it before reading any of the experiment's records. Either way, the command holds it until it ends: through the approval, every case, the report, and the manifest. So no other run can read the records while they change, or approve a plan against a history that's about to change.
- **Releasing it.** The operating system releases the lock when the process closes the file or ends, however it ends. So a killed process leaves no stale lock, and there's nothing to clean up. On Windows, Microsoft's [`LockFileEx`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-lockfileex) documentation says the release after a process ends may take time, depending on the system's resources (checked 2026-10-07). Until it happens, the next run fails with `experiment.locked`, and can be run again.
  - **Closing the store on Windows (R03-T08's review).** The store unlocks the file's first byte, from the start of the file, before it closes the descriptor, so that closing the store releases the lock at once, and the same process can take it again. Microsoft's [`_locking`](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/locking) documentation says a locked region should be unlocked before the file is closed, and that unlocking begins at the file's current position, which writing the lock file's line moved. The `LockFileEx` documentation says the system releases a lock left on a closed file, as after a process ends, in a time that depends on its resources, and recommends unlocking explicitly (both checked 2026-10-10). This comes from that documentation, not from a check on Windows. The alternative was to leave the release to the close.
- **File systems.** The lock excludes only the processes that the file system's locks reach. Two machines sharing a network volume exclude each other only when that file system enforces locks between them. A file system that refuses the lock, with any error but the one that says another process holds it, fails the command with `storage.write_failed`, exit 4, before any request, and the message says why. Network file systems are untested.
  - **Which error says another process holds it (R03-T08).** `EWOULDBLOCK` from `flock`, which is `EAGAIN` on Linux and macOS, and `EACCES` from `msvcrt.locking`, which Microsoft's C runtime documents as a locking violation. The Windows error comes from that documentation, not from a check on Windows.
  - **R03-T08's trials.** On 2026-10-09, on macOS 26.6.2 with Python 3.14.6, R03-T08 tried the lock on APFS, exFAT, and FAT32 disk images, as R01-T08 tried the store. On each, the lock was taken on the new, empty file's descriptor, and refused, with `EAGAIN` ("Resource temporarily unavailable"), to a second descriptor of the same process and to another process. Closing the descriptor released it, and so did killing its process with `SIGKILL`. A synthetic experiment run into each, through the core, completed on APFS. On exFAT and FAT32, its claim took the lock, and `sessions/1/session.json` then failed with `storage.write_failed`, because the file system has no hard links, before anything was sent; the lock stayed held until the store was closed.
- **One directory, one experiment.** The lock belongs to the output directory. An experiment's configuration run into two directories makes two experiments, each with its own records and lock, just as a screen run into two directories makes two runs.
- **No lock per account.** [ADR 0001](adrs/0001-python-and-portfolio123-integration.md) locks per account, across processes, each operation that updates a shared account object, such as an API ranking system. 0.3.0 sends only screen backtests, ranked in one of the three [ranking forms](#ranking-forms):
  - **A ranking system named by name or ID** is read, not updated.
  - **A single formula** is sent inline. [0.1.0's specification](releases/0.1.0-api-execution.md#implementation-tasks-only-after-ready) states that it changes nothing in the account. That rests on documentation, not on a check: ADR 0001's [verification notes](adrs/0001-python-and-portfolio123-integration.md#verification-notes) record that ranking definitions given as nodes or XML, which Trial Folio doesn't accept, create or overwrite `APIRankingSystem`, and no check has yet looked at the account's ranking systems after a formula-ranked backtest.

  On that basis, 0.3.0 has nothing to serialize per account, and no such lock: two experiments in different directories, or an experiment and a screen run, may run at the same time with one account. If a formula ranking were found to update a shared object, two runs with different formulas could each be backtested with the other's ranking, and 0.3.0 would need the lock. The first release that updates a shared object adds it. The owner confirmed this on 2026-10-08 ([open question](releases/0.3.0-experiments.md#open-questions)), and [R03-T11](releases/0.3.0-experiments.md#implementation-tasks-only-after-ready)'s live check verifies it: the owner compares the account's ranking systems before and after its formula-ranked run. If one changed, 0.3.0 needs the lock.
- **The core** takes the lock through the `ArtifactStore`, which owns the output directory, and holds it while it executes ([interface-independent core](#interface-independent-core)).
- **The store's side (R03-T08).** `ArtifactStore.claim` takes the lock when it's given `lock`, on the descriptor that created the file, before it writes the line; a resumed experiment takes it with `ArtifactStore.lock`, on the existing file, which lets the store write without claiming the directory. The store holds the lock until its owner calls `close`; the core never closes a store it was given, so the caller, the CLI or another interface, holds the lock until it's done with the experiment. A claim that fails after taking the lock releases it before removing what it created, since Windows can't remove a file a descriptor holds open. `src/trialfolio/storage.py` implements both, and the lock file's line is `Trial Folio experiment lock: it claims this directory for one experiment.`

#### Running an experiment

**A new experiment,** into an output directory that's absent or empty, takes the steps of [`trialfolio run` for a screen](#approval), with these differences:

- **Step 5** fails with `plan.approval_required` when `--revision-reason` or `--repeat` is given too: a new experiment has no revision, and no attempt to repeat.
- **Step 7** claims the directory with `experiment.lock`, and takes the lock. Logging to `<out>/logs/` starts then. The run writes `sessions/1/session.json`, the first [atomic write](#artifact-storage), then `plans/1/configuration.yaml`, `plans/1/plan.json`, and `plans/1/experiment.json`.
- **Then** it runs the cases in the plan's order, writing each succeeded case's [tables](#an-experiments-normalized-tables) after its attempt record, and ends with `sessions/1/`'s report and manifest.

**A resumed experiment,** into a directory that holds `experiment.lock`:

1. Check the license acknowledgment (`license.not_acknowledged`).
2. Validate the configuration (`config.invalid`).
3. Take the lock (`experiment.locked`). A directory that holds anything else, and no `experiment.lock`, is `output.not_empty`, as for a screen.
4. Read and check the experiment's records, below (`input.not_a_run` or `artifact.unknown_schema_version`). A configuration with another `experiment_id`, or whose baseline has another universe than the current plan's, is `output.not_empty`. So is a directory without `plans/1/experiment.json`: its first run stopped before anything was sent, and the message says so, and to remove the directory and run again. Once the records pass, an experiment whose plans record the approval `not_required` is [synthetic](#the-experiment-manifest), and `run` fails with `output.not_empty` too: the message says that the directory holds a synthetic experiment, whose values are invented, and to run the configuration into another directory.
5. Check the installed versions (`environment.unsupported`). Build the plan, which either is the current plan or revises it, and show it with the experiment's progress: each case's outcome so far, the cases that can be [repeated](#repeating-a-case), each with the option that repeats it, the retired cases, and the budget counted so far. Check each `--repeat` against the plan and the records (`plan.approval_required`).
6. Check the approval: for the current plan, as for a new one (`plan.approval_required`); for a revision, with its reason (`plan.changed`). Then confirm the repeats that `--repeat` names without an attempt ID (`plan.approval_required`).
7. Check that credentials are present when a case is due or to be repeated (`provider.auth_failed`).
8. Logging to `<out>/logs/` starts. Write the new session's `sessions/<s>/session.json`. Then write the attempt record of each `running` attempt, as [uncertain completion](#uncertain-completion) says, and of each attempt whose only record is its authentication record, as [experiment attempts](#experiment-attempts) says. Write the [tables](#an-experiments-normalized-tables) a run didn't write. For a revision, write `plans/<n>/`, as for the first plan.
9. Run the cases that are due, and the cases to repeat, in the plan's order, writing each succeeded case's tables after its attempt record, and end with the session's report and manifest.

**The cases that are due.** Each case of the plan is in one of three states, by whether its attempts succeeded or are [possibly charged](#http-exchanges). A `running` attempt, and one whose only record is its authentication record, count as step 8 will record them: the first `succeeded` with a saved response, and `unknown` without one, possibly charged either way; the second `failed`, not possibly charged.

- **Complete:** one of its attempts succeeded. It's skipped.
- **Due:** none of its attempts is possibly charged. It has no attempt, or each failed before its request could reach Portfolio123, such as after a failed authentication or a connection that never opened. A resume sends it.
- **Awaiting a repeat:** one of its attempts is possibly charged, and none succeeded, so it's `unknown`, or `failed` after a request that may have reached Portfolio123, such as one Portfolio123 rejected. A resume never sends its request again automatically, since it may already have been charged. Only a confirmed [repeat](#repeating-a-case) sends it ([open question](releases/0.3.0-experiments.md#open-questions)).

**Checking the records.** A resume reads the experiment's records through the `ArtifactStore` and checks them as `trialfolio report` checks a run ([a complete run](#reports)), before it builds the plan:

- **Each plan** with an `experiment.json`: that file is valid; its last entry is its directory's plan, so the entry's number is the directory's, its `plan.json` recomputes to the entry's hash, and its `plan.json` and `configuration.yaml` have the `artifact_id`s the entry records; its entries before the last equal the previous plan's `experiment.json`'s; and its `revises` is the previous plan's hash. Every plan records the approval `not_required`, or none does, and the latest manifest is `synthetic` exactly when they do.
- **Each attempt:** its records are valid, and agree with each other; they name a plan of the experiment, a case of that plan, and a session of the experiment; no other attempt of its session has its `sequence`; and each file the attempt record references has the `artifact_id` it records.
- **Each attempt's authentication,** when it has a start record: its `authenticated_by` names an attempt of its session whose records hold a successful authentication: itself, or one with a lower `sequence`. No attempt that names the same one, with a lower `sequence` than this one, got a 401 or 403 to its request, which would have dropped that token. `sequence` orders a session's attempts, not their start times ([experiment attempts](#experiment-attempts)).
- **Each attempt's repeat:** an attempt that follows a possibly charged attempt of its case, by `session`, then by `sequence`, has a `repeat_of` that names the latest such attempt before it. Every other attempt's `repeat_of` is `null`. So the records show that no request that may have been charged was sent again without a confirmation ([repeating a case](#repeating-a-case)).
- **Each case's tables:** only a case with a succeeded attempt has them, in its own directory. Each reads back as a valid table, as a complete run's does ([a complete run](#reports)): its rows are labeled with the case's `case_id`, and were drawn from that attempt's saved response and the configuration of the plan it ran under ([an experiment's normalized tables](#an-experiments-normalized-tables)). A case may have `metrics.csv` without `settings.csv`, which step 8 completes, but never `settings.csv` alone. A `metrics.csv` the latest manifest doesn't list is exactly what the installed parser writes from that response ([which parser wrote them](#an-experiments-normalized-tables)).
- **The latest manifest,** the highest-numbered session's that has one: it's valid, and each file it lists has the size and `artifact_id` it records, as `trialfolio report` checks a run's files. No record is ever removed or replaced, so it lists every plan's, attempt's, and case table's file written before it. A file missing or changed since, as after an incomplete copy, fails the check, instead of leaving a case that had an attempt looking due, to be sent again and left out of the budget. The files it doesn't list were written after it, and are checked as above. Earlier manifests aren't read, because the latest lists every file they list but their sessions' own. Records written after it, by a run that stopped before its end, have no manifest to be checked against.

**Progress and cancellation, in the core (R03-T05).** Execution reports its progress to a callback its caller gives, and the caller may cancel it ([interface-independent core](#interface-independent-core)):

- **Progress events.** In order: the session's start, with its number and the cases it will send or repeat; each attempt's start, with its `attempt_id`; each attempt's end, with its outcome and whether it's possibly charged; and the session's end, with the counts its manifest records. Each event names a case by its `case_id`, and holds no text from the configuration: the caller has the plan, which gives each case's key and description.
- **Cancellation.** The caller may ask execution to stop, at any time, from another thread. Execution checks before each attempt starts, and so before its authentication call and its send, never during either: a send in flight finishes, and its attempt is recorded. Once asked, execution starts no further attempt, and ends the session as when the budget is spent: the cases not started keep their outcomes, and it writes the session's report and manifest. The manifest's outcome is `partial`, with `execution.partial`, whose message says the run was cancelled, unless every planned case is complete. A resume, approved by the same hash, runs the rest.
- **The CLI doesn't cancel.** A Ctrl-C is an [interrupt](#interrupts), whenever it arrives, so a session the CLI runs ends without its manifest when it's interrupted, as [experiment output](#experiment-output) says.

**The executor (R03-T08).** `ExperimentExecution`, in `src/trialfolio/experiment_execution.py`, executes a new experiment, from the claim through the session's manifest; R03-T09 adds the resume. It takes the approved plan and hash, how the plan was approved, the store, the session's client, the command record or none, and optionally the clock, a progress callback, and a `Cancellation`, and its `run` takes the configuration's bytes. It builds the plan again from them, with the plan's versions, and refuses, with `ValueError`, before writing anything, a configuration that doesn't give the plan. It settles these details:

- **One client for the session.** The session's attempts share the client its caller gives, which the caller closes. An attempt authenticates when the client holds no token: the session's first attempt, and the first after a 401 or 403 dropped it. Each other attempt sends with the token, and its records name the attempt that obtained it in `authenticated_by`.
- **`sequence`** counts the attempts the session starts, one at a time, from 1, whatever case each is for.
- **The budget's checks.** Before each attempt, execution checks that the requests counted, plus one, stay within `provider_requests`, and, for an attempt that will authenticate, that the authentication calls counted, plus one, stay within `authentication_calls`. If either doesn't, the case isn't started, and no later case is. In a new experiment, the budget, at least the number of cases, always covers each case's one attempt, which makes at most one request and one authentication call; the checks stop a run only once an earlier session's attempts are counted, which R03-T09's resume brings.
- **D-32's stop** applies when a later case remains: after the last case, there's nothing to stop. Either way, the case's attempt is recorded, and `execution.partial`'s message names the error.
- **When the progress events come.** The session's start, once its session record and its plan are recorded, and before its first attempt; each attempt's start, before it authenticates or sends anything; each attempt's end, once its attempt record, and its case's tables, if it succeeded, are written; and the session's end, once its manifest is written. A session that ends without its manifest sends no end event. The callback runs in the thread that runs the execution, and an exception it raises ends the session as an unexpected exception would. An exception raised at the session's end, which comes once its manifest is written, still propagates, but the session has ended, and its manifest stays, since no record is removed (R03-T08's review). The alternative, discarding the manifest, would turn a complete, consistent session into one that reads as incomplete, because of an error in the interface that shows its progress.
- **`execution.partial`'s message** lists each planned case that didn't succeed, with its outcome and error code: by its key in the message, which the manifest and the terminal show, and by its `case_id` in the logged message. It says why no later case started, when one didn't, and that a case whose request may have reached Portfolio123 is sent again only by a confirmed repeat. R03-T13 adds the exact `--repeat` option to the CLI's messages.
- **An ending without a manifest.** An interrupt, or a storage failure, before the first plan's `experiment.json` is published sends nothing, and its message says to remove the directory and run the command again, since a resume can't use it ([running an experiment](#running-an-experiment), step 4). One after that, including one during or after an attempt, says what the latest attempt's records say about its request, that the attempts recorded so far are kept, and that running the same command again resumes the experiment. An interrupt that arrives once the store has published `experiment.json` counts as after it.
- **A response that fails validation** leaves its case without tables, `failed` with `provider.response_invalid` in the manifest's counts and in `execution.partial`'s message, and the session goes on to the next case. It's logged as `experiment.case.invalid`.
- **A file published before an unexpected failure.** When the write of an attempt's authentication record, `request.json`, or response fails after the store published the file, as when an unexpected exception follows, the file is listed with the attempt's files all the same, so the session's manifest lists every file the attempt wrote. The attempt record references a request or a response only when its write completed, so a 200 whose `response.json` was published that way is `unknown`, as when its save fails ([endings that decide the error code](#endings-that-decide-the-error-code)), and the session goes on to the next case, as after any case that fails. An interrupt or a storage failure still ends the session without its manifest (R03-T08's review). The alternative was to end the session there without its manifest, as a storage failure does, which would leave the file for a later session's manifest to list, but would stop the cases after it.

#### Repeating a case

Introduced in 0.3.0 (R03-T04). A resume never sends a case's request again once it may have reached Portfolio123 ([the cases that are due](#running-an-experiment)). `--repeat` sends it again, as a new attempt of the same case, when the user names the case and confirms the possible repeat charge ([release 0.3.0's required behavior](releases/0.3.0-experiments.md#required-behavior), 4).

**Which cases can be repeated.** A case of the plan the run approves that's awaiting a repeat: one of its attempts is possibly charged, and none succeeded. So it's `unknown`, or `failed` after a request that may have reached Portfolio123, such as one that got a 400, 402, or 429. A failed case needs the same confirmation as an `unknown` one, because whether Portfolio123 charges a failed request is unverified ([budget and retries](#budget-and-retries)). Without `--repeat`, it could never be sent again: a revision keeps a case whose settings didn't change, with its attempts ([what a revision keeps](#experiment-plans-and-revisions)). These can't be repeated:

- **A complete case,** one with a succeeded attempt. Its response is saved, and sending its request again would be a reproduction, which 0.3.0 doesn't offer.
- **A due case,** none of whose attempts is possibly charged. A resume sends it anyway.
- **A retired case.** No plan from then on includes it, unless a later plan includes its settings again.

**The option.** `--repeat <case-key>`, or `--repeat <case-key>:<attempt-id>`, once for each case to repeat. The key names the case in the plan this run approves: the current plan, or the revision when the run revises it. A case that a revision kept keeps its attempts, so it's repeated under its key in the revision.

- **With the attempt ID,** the option is the confirmation, and the CLI doesn't ask. The ID is the `attempt_id` of the case's latest possibly charged attempt, whose possible charge the user acknowledges, as `--approve` approves a plan by its hash. The full plan display gives this option, exactly, for each case awaiting a repeat, and so do the messages of a run that ends with one, and of a repeat that fails, below.
- **Without it,** the CLI asks, when stdin and stderr are both terminals and there's no `--approve`, once the plan is approved. It lists each case to repeat with its latest possibly charged attempt: the `attempt_id`, the outcome and error code, and that its request may already have been charged. It says that a repeat sends the request again, may be charged again, and counts against the budget, and gives the budget that would remain. Then it asks the user to type `repeat`, one answer for all the cases it lists, under the rules for typing `approve` ([approval](#approval)): exactly `repeat`, and any other answer is a refusal. It passes on the attempt IDs it showed, as interactive approval passes on the hash it showed. With `--approve`, or without a terminal, the CLI never asks, as for approval, so a repeat needs its attempt ID.
- **Usage errors.** A value that doesn't match a case key's pattern, `[a-z0-9][a-z0-9_-]{0,63}`, alone or followed by a colon and an `attempt_id`'s form, is a usage error that the parser reports before any other check, and so is a case key given twice: exit 2, without a JSON summary, as for an invalid `--revision-reason` ([CLI behavior](#cli-behavior)).

**One confirmation, one repeat.** A confirmation names an attempt, and allows one send of its case's request after that attempt. It's used once a later attempt of the case is possibly charged. So running the same command again, as after an interruption, never repeats the case a second time on the same confirmation:

- **Until the repeat may have reached Portfolio123,** the confirmation is unused, and the command repeats the case, as it would have the first time. That includes a repeat that sent nothing, such as one whose authentication failed: the same command tries it again.
- **After that,** the confirmation is used. The command doesn't repeat the case, says that it was repeated already, and resumes the rest of the experiment. A repeat that ended `unknown`, or `failed` and possibly charged, needs a new confirmation, which names the repeat's own attempt.

Each attempt that `--repeat` starts records the confirmation's attempt in `repeat_of` ([experiment attempts](#experiment-attempts)). A resume checks that each attempt sent after a possibly charged attempt of its case names the latest one ([checking the records](#running-an-experiment)).

**What fails.** Each of these fails with `plan.approval_required`, exit 2, once the plan is shown, and sends and writes nothing. The message says why, and gives the exact option for each case awaiting a repeat:

- `--repeat` with a screen, or with a new experiment, which has no attempts;
- a key that names no case of the plan this run approves;
- a key alone, for a due case;
- an attempt ID that names no attempt of the case, or an attempt that isn't possibly charged, or one that succeeded;
- a key alone, for a case awaiting a repeat, with `--approve` or without a terminal;
- a refused confirmation.

Two don't fail. The case isn't repeated, the command says so, and it resumes the rest of the experiment:

- an attempt ID whose confirmation is used;
- a key alone, for a complete case, so that a command that confirmed a repeat on a terminal resumes when it's run again after the repeat succeeded.

**The budget.** A repeat is a send like any other. It counts against the experiment's budget ([the budget across runs](#experiment-plans-and-revisions)), and runs in the plan's order, among the cases that are due. When the remaining budget can't cover it, it isn't started, and neither are the cases after it, and its confirmation stays unused. A revision that raises `budget.provider_requests` then lets the same confirmation repeat it.

**Counting.** A repeat is a provider operation, not a new case: it's an attempt of the same case, with the same `case_id`, and [METH-03.2](methodology.md#meth-03-research-history-and-multiple-testing) keeps provider operations apart from candidates and hypotheses. The [experiment manifest](#the-experiment-manifest) counts the repeats apart from the other attempts, and counts a case by the latest of its attempts that may have reached Portfolio123, so a repeat that sent nothing can't hide an `unknown` request. The report shows each repeat, and the attempt it repeated, and marks each case awaiting one; R03-T10 settles how.

**In the core.** Execution takes the confirmed repeats with the plan's hash: each case to repeat, by its `case_id`, and the attempt whose possible charge the user acknowledged. It checks them as above, and never asks ([interface-independent core](#interface-independent-core)). The CLI obtains them from `--repeat`, or from the confirmation it asks for.

**Logs** name a repeat's case by its `case_id`, and the attempt it repeats by its `attempt_id`, never by the case key.

#### The experiment manifest

`sessions/<s>/manifest.json`, with `artifact_type: experiment` and schema version 1.0.0. Each run that reaches its end writes one, last: one with cases that failed or are uncertain, one the budget stopped, and one that sends nothing because no case is due or to be repeated. It records the experiment as the run left it, and holds what a [run's manifest](#artifact-storage) holds, with these differences:

- **The experiment:** its `experiment_id`, and the session's number.
- **The plan:** the current plan's number and `plan_hash`, and how this run approved it, `interactive` or `option`, or `not_required` for a synthetic experiment (below).
- **The command:** `command.options` records `approve` and `json`, as for a run, and whether `--revision-reason` and `--repeat` were given. The reason's text is in `experiment.json`, and the repeats are in the attempts' `repeat_of`.
- **`artifacts`:** every file of the experiment's records: each plan's three files, each attempt's files, each case's [tables](#an-experiments-normalized-tables), and this session's `session.json` and report. It leaves out `experiment.lock`, `logs/`, other sessions' files, and a plan's directory without `experiment.json`. Each `plans/<n>/configuration.yaml` is a source artifact, with the format `experiment-configuration` version 1.0.0, `user_supplied` provenance, no parser version, and no provider operation. It's acquired when its plan is recorded, so its source record's `acquired_at` is its plan's `experiment.json`'s `created_at`, and every session's manifest gives it the same time (R03-T08). The alternative, the time the command that built the plan started, as a run's configuration has, isn't in any record a later session can read when that session ended without its manifest. A request's and a response's source records are a run's.
- **`parsers`:** each parser version that normalized a case's response, with its layout's version, since a revision for a new Trial Folio version keeps the cases an earlier version normalized. Each response's source record names the one that read it: the one the latest manifest names, or the installed one for a response read since ([which parser wrote them](#an-experiments-normalized-tables)). With no case normalized, it lists the installed version's, as a run without a response does.
- **`synthetic`:** true exactly for an experiment executed with the demo's client, which sends nothing ([running the commands](#cli-behavior)). Its approval is `not_required`, as the demo's run's is, and each of its plans records that approval in `experiment.json` too, before anything is sent under it, so a resume knows the experiment is synthetic even when no session has a manifest. Its report says that every value, attempt, and count in it is invented ([DSC-04](disclaimers.md#dsc-04-actual-simulated-and-hypothetical-results)). No 0.3.0 command writes one: the core does, given the demo's client, and the tests' historical experiment is one ([open question](releases/0.3.0-experiments.md#open-questions)). A synthetic experiment stays one, so invented and real attempts never share an experiment: the core resumes and revises it only with the demo's client, and `trialfolio run` doesn't resume it (step 4 of [a resumed experiment](#running-an-experiment)). The core also fails with `output.not_empty` when it's given the demo's client for an experiment that isn't synthetic.
- **Reproducibility:** over the current plan's cases.
- **`counts`:**
  - **Cases:** `planned`, the current plan's cases, and how many of them are `succeeded`, `failed`, `skipped`, `unknown`, and `not_yet_run`, which add up to `planned` ([R03-AC08](releases/0.3.0-experiments.md#acceptance-criteria)). 0.3.0 skips no planned case deliberately, so `skipped` is 0.
  - **Retired cases:** how many cases revisions retired. Their attempts are counted with the others.
  - **Attempts:** every attempt of the experiment, by outcome, and `repeats`, how many of them [repeat a case](#repeating-a-case), those with a `repeat_of`. `retries` is 0, as in a run, because Trial Folio never resends a request on its own ([budget and retries](#budget-and-retries)).
  - **The budget:** the experiment's `provider_requests` and `authentication_calls`, counted as [the budget across runs](#experiment-plans-and-revisions) counts them, beside the current plan's budget.
  - **Cost:** the sum of the costs Portfolio123 reported, when any did.
- **A case's outcome** for these counts:
  - `succeeded`, when one of its attempts succeeded and that attempt's response passed validation;
  - `failed`, when its succeeded attempt's response failed validation, with `provider.response_invalid`, as a run with that response fails;
  - otherwise, when one of its attempts is possibly charged, the outcome of the latest such attempt, by `session`, then by `sequence`, not by start time: `failed`, or `unknown`, with a `running` attempt counted as `unknown`. A later attempt that wasn't possibly charged, such as a [repeat](#repeating-a-case) whose authentication failed, sent nothing, so it changes nothing known about the case's request. Counting by the latest attempt, possibly charged or not, would count such a case as `failed`, although its request's outcome is still unknown;
  - `failed`, when it has attempts and none is possibly charged: it's due, and a resume sends it;
  - `not_yet_run`, when it has no attempt.
- **`outcome`:** `completed` when every planned case succeeded, and `partial` otherwise, with `execution.partial`, exit 6 ([CLI behavior](#cli-behavior)).

**Field shapes (R03-T06).**

- **`command`** is `null` when no `trialfolio` command ran the session: when the core runs it for another interface, and for a synthetic experiment, which only the core writes. Otherwise its `name` is `run`, and its `options` are `approve`, the hash as given or `null`; `json`; and `revision_reason` and `repeat`, each true when the option was given.
- **`plan`** is the current plan's number, beside its `plan_hash` and the `approval`.
- **`artifacts`.** Each file's role names it, and it's at its role's place in the layout: `configuration`, `plan`, and `experiment_record` in `plans/<n>/`; `authentication_record`, `start_record`, `attempt_record`, `provider_request`, `provider_response`, and `provider_response_undecoded` in an attempt's directory; `metrics` and `settings` in a case's `normalized/`; and `session_record` and `report` in the manifest's own session. Each plan it lists has its three files, and so do the first plan and the current one, which it always lists. A case whose tables it lists has both.
- **`counts`** holds `cases`, with `planned` and each outcome; `retired_cases`; `attempts`, by outcome as in a run, and `repeats`; `retries`, 0; `provider_requests` and `authentication_calls`, as counted; `budget`, the current plan's `provider_requests` and `authentication_calls`; and `cost`.

`schemas/experiment-manifest-1.0.0.schema.json` gives every field.

**The report,** `sessions/<s>/report.html`, comes before the manifest, and is rendered from the records and what the manifest will record, as a run's is. The release's [required behavior](releases/0.3.0-experiments.md#required-behavior), 6 and 7, and [reports](#reports) set what it holds: every case and its outcome, the retired cases, every revision and its reason, every repeat, and the declared prior research, which Trial Folio can't verify. R03-T10 settles its details, as R02-T07 did a review's. R03-T08 wrote a first version, `ReportRenderer.render_experiment`, so a session ends with its report as specified: the header, with the concise notice, the outcome, "Not assessed" twice, and the results' nature, synthetic or backtested; the ten sections, with the purpose and the prior-research declaration, which it says Trial Folio can't verify, the baseline's settings, each planned case in the plan's order with its key, `case_id`, change, description, outcome, and attempts, and the counts; and the closing section, with the Portfolio123 data statement and the full notice. It points to each case's tables rather than showing their values, and links each file the manifest lists, by its path relative to the report. R03-T10 replaces it with the full report.

**Logs** name the experiment's plans by number and hash, and its cases by `case_id`. They never hold the `experiment_id`, a case key, a description, or a revision's reason, which are the user's text ([logging](#logging-and-local-diagnostics)).

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

**The review report (R02-T07).** `src/trialfolio/report.py` renders a review's report too, with `ReportRenderer`'s `render_review`, from the review's configuration, each result's run as the [input check](#review-output) read it, the comparison, and what the review manifest will record, without the report's own entry. A run report's rules above hold for it, apart from where it links, and these add to them:

- **Its structure.** A run report's: the header, then the ten sections, with the same `id`s, and the closing section. The header's kind line reads "Trial Folio review report".
- **Changes from the baseline,** in section 2, the [differences between screen runs](#differences-between-screen-runs) rules, and then every flagged setting row of `differences.csv`, in tables of their own:
  - **Intended changes:** each declared change, observed or not, with its reason.
  - **Unexplained mismatches,** apart from the intended changes.
  - **Unknown settings,** that no result declares.
  - **The settings that are the same,** counted for each result. Those that are the same but flagged, such as a date with `coverage_mismatch`, are listed with their flags.

  The baseline's own settings follow.
- **Metrics,** in section 4: each result's beside the baseline's, with the difference, its unit, and its decimal places when they're differenced, or the reason when they're not. A benchmark-relative value names its benchmark, and the benchmark's own value the run's `benchmark` setting, so values across two benchmarks show both. An unavailable value gives the reason the copied `metrics.csv` gives it, such as `blank_in_source`, and its comparison is `unavailable`, with `input_unavailable`.
- **The coverage,** in section 3: each result's dates and periods, with any `coverage_mismatch`, and how far each moved from the baseline's: dates in days, and periods as a count.
- **Each result,** in section 5: its role, description, run title, run purpose, outcome, and whether it has normalized tables. A run without them says why, with its copied manifest's `error`: its code, and its message as recorded. Each result also names its run's manifest, plan hash, case, and saved response, and the results that share each response.
- **Synthetic results.** When any result is synthetic, a banner before any result names each one, and every table cell or heading that names one marks it, as in "`demo` (synthetic)". A column of the baseline's values names the baseline in its heading, so a synthetic baseline's values are marked there too. A synthetic result's values are never called Portfolio123's or a backtest's ([DSC-04](disclaimers.md#dsc-04-actual-simulated-and-hypothetical-results)).
- **Its links.** The report is in the review's output directory, so it links `manifest.json` and each file the manifest lists, apart from itself, by its path in the review. It never links a run, and no `run` path appears in it.
- **Its conclusion** says what differs, and never which result is better: a review ranks no result.

**A complete run.** `trialfolio report` reads only through the `ArtifactStore`, and only the files the manifest lists. A directory is a complete run when all of these hold; otherwise it's `input.not_a_run`, and the message names the problem, never a value:

- Its `manifest.json` is a run manifest, `artifact_type: run`, valid against its model.
- Each file the manifest lists exists, with the size and `artifact_id` the manifest records.
- It lists `plan.json` and `configuration.yaml`, once each. `plan.json` recomputes to its `plan_hash` ([plan hashing](#plan-hashing)), and the manifest names the same hash.
- Each start record and attempt record it lists is in an attempt's directory of the plan's case, is valid, names that attempt, its case, and its plan's hash, and agrees with the attempt's other record. Each file an attempt record references is listed, with the same `artifact_id` and the matching role.
- It lists both normalized tables, or neither. Each table reads back as a valid table, its rows are labeled with the plan's `case_id`, and they were drawn from the run's own `configuration.yaml` and saved response. `metrics.csv` holds one row for each of the layout's metrics, each in the unit the layout gives it, and `settings.csv` one for each of the plan's settings, in their documented order: a table missing a row, with one repeated, or with a metric in another unit, isn't complete.

A schema version with no reader, in the manifest, `plan.json`, a start record, an attempt record, or the manifest's entry for one of them or for a table, is `artifact.unknown_schema_version`.

The message names the run: `trialfolio report` calls it "the run directory", and a review names it by its result ([review output](#review-output)). A table that can't be read is one of the problems above, so its message names the run too.

## CLI behavior

The command is `trialfolio`. Commands are introduced by release:

| Command | Release | Purpose |
|---|---|---|
| `trialfolio init [<dir>]` | 0.1.0 | Set up a workspace: a new or empty folder, the current one by default, with a starter screen configuration, a README, and a `.gitignore` |
| `trialfolio run <config> --out <dir> [--approve <plan-hash>]` | 0.1.0 | Plan and execute one supported screen backtest, once its [plan is approved](#approval) |
| `trialfolio report <run-dir> --out <dir>` | 0.1.0 | Re-render a saved run's report offline |
| `trialfolio demo --out <dir>` | 0.1.0 | Write a synthetic example run, labeled synthetic, and render its report offline |
| `trialfolio review <config> --out <dir>` | 0.2.0 | Compare saved runs offline |
| `trialfolio run <config> --out <dir> [--approve <plan-hash>] [--revision-reason <text>] [--repeat <case-key>[:<attempt-id>]]...`, for a `kind: experiment` configuration | 0.3.0 | Plan, execute, resume, and revise a finite experiment, and repeat a case on purpose ([D-24](spec.md#decisions), [running an experiment](#running-an-experiment), [repeating a case](#repeating-a-case)) |
| `trialfolio --version` | 0.1.0 | Print the application version |
| `trialfolio license [--accept]` | 0.1.0 | Print the license, the full notice, and the acknowledgment status; `--accept` records the acknowledgment |

- **stdout** carries the command's result: a short human summary, or with `--json` the [JSON summary](#json-summary).
- **stderr** carries progress, warnings, and errors, which come from the same events as the log file. It also carries the [plan display](#approval) and the confirmation prompts, which are written directly and never logged, because they show configuration values.
- **Output directory.** `review` and `run` create the output directory. They refuse to write into a directory that exists and is not empty (`output.not_empty`). There is no overwrite option in 0.1.0. `init` treats its workspace the same way. `run` reuses an existing directory only to resume or revise the experiment it holds, as [running an experiment](#running-an-experiment) says; never for a screen.
- **Claiming the directory.** A command that creates a new output checks the directory early, but another process can write to it before the command writes anything, for example while `run` waits for approval. So the command claims the directory with its first file. A new experiment claims its directory with `experiment.lock`, and takes [the lock](#the-lock) on the file it creates, before writing it; if it can't, the claim fails, and removes what it created. `run` resuming an experiment in its own existing directory doesn't claim it; it takes the experiment lock instead. The claim:
  1. It creates the directory if it's absent, and any missing parent directories, one at a time, remembering which ones it created. A directory that another process creates first is used as it is, and not remembered. Before it creates anything, it checks the path as the early check does: a path that exists and isn't a directory, a symbolic link to nothing included, is `output.not_empty`, and a path that can't be created, because a parent isn't a directory or none exists, is `storage.write_failed`. `..` segments are resolved in the path as written, so the claim never creates a directory that's only on the way to `..`.
  2. It creates its first file directly under its final name, with an exclusive create that fails if the name exists, then writes and syncs it. No temporary file is involved, so nothing else is written into a directory that isn't claimed. The file is never empty: see the identity rule below.
  3. It lists the directory.

  **Ownership across interrupts.** While creating a directory, exclusively opening the claim file and recording its identity from the returned descriptor, or reading that identity again once the file is written, or once writing or syncing it failed or was interrupted, the store defers a callable SIGINT handler. It restores the caller's handler before delivering a pending signal, even if creation failed. The descriptor is closed on the interrupt path too. This applies in the main thread, where Python delivers signal handlers; worker-thread calls do not change handlers, and an ignored SIGINT stays ignored ([Python's signal rules](https://docs.python.org/3.12/library/signal.html#signals-and-threads)). Tests send real SIGINT at the creation boundaries so they exercise this deferral rather than bypassing it with a directly raised exception.

  Cleanup never treats an empty file as proof of ownership. The claim records only successful creations, and checks the file's device and inode against the recorded identity both before accepting the claim and before removing its file on failure. A missing or replaced claim file fails with `output.not_empty`; a replacement is left alone. If cleanup cannot read the identity, it leaves the file rather than removing an unverified file.

  **The identity once written.** On FAT and exFAT, macOS gives each new, empty file a temporary inode of its own, counted down from `2**64` for each mount, until its first write gives it a lasting one. So the claim reads its file's identity again from the descriptor once the file is written, and that's the identity it checks. It also reads it again if writing or syncing the file fails or is interrupted, before closing it, so that cleanup checks the identity the file has then: a write that failed with `ENOSPC`, and wrote nothing, gave the empty file another temporary inode. Its file is never empty, because an empty file there has only a temporary identity, which can change while the file stays empty, as it did after that failed write, and after the volume was mounted again. A walk-through of the user guide found on 2026-10-04 that a claim reading the identity only at creation failed on every such file system with `output.not_empty`, and left its file. exFAT and FAT32 disk images on macOS 26.6.2 showed these inodes the same day.

  If the first file existed already, or the directory holds anything else, the claim fails with `output.not_empty`. Each command lists the directory only after its own file exists. So when two commands claim the same directory at once, at most one succeeds. If the directory, or a parent the claim is creating it in, disappears during the claim, because a competing claim that created it failed and removed it, the claim also fails with `output.not_empty`.

  **The first file's AppleDouble file.** On macOS, a file system that can't hold extended attributes, such as FAT or exFAT, gets an AppleDouble file for each file that has them, named `._` and the file's name. macOS creates it together with the file, and removes it with the file. R01-T08 saw it created with each new file on exFAT and FAT32, holding `com.apple.provenance`. So on macOS, the claim counts `._` plus its own file's name, such as `._plan.json`, as part of that file. Any other name, `._` names included, is something else.

  A command whose claim fails removes only what it created: the file it created, if any, and then the directories it remembers creating, deepest first, each only if it's empty. It removes each with `os.rmdir`, which never removes a non-empty directory. If another process has written there, that directory and its parents are left as they are, and the result is still `output.not_empty`. A command writes nothing else, logs included, into a directory it hasn't claimed.

  A crash while the first file is written leaves it incomplete. A saved `plan.json` is checked against its hash, and there's no manifest, so the output is visibly incomplete.
- **Validation first.** All inputs are validated before the output directory is created, so an invalid or unsupported input creates no output. An interactive license acknowledgment, which comes first, still writes its own record.
- **Partial success.** A command that finishes with some cases failed, skipped, or uncertain writes complete accounting and exits with code 6.

**Running the commands (R01-T14).** `src/trialfolio/cli.py` is the command, and `src/trialfolio/execution.py` the steps of `run` and `demo` after approval:

- **What a run writes after its attempt.** Once the attempt record is written, `run` normalizes a saved response, then writes `report.html`, then `manifest.json`. It does that for a failed attempt too, so a provider error is accounted for, with the manifest's `outcome` `failed`, and so is a response that fails validation (`provider.response_invalid`), without tables. An interrupt, a storage failure, or an unexpected exception after the attempt leaves no manifest, so the output is visibly incomplete, and so does an attempt record that couldn't be written, or an attempt that ended before `configuration.yaml` was saved, which every manifest lists, as after an unexpected exception writing it. That includes a failure while `manifest.json` itself is written, even after the store published it, as when the sync of its directory fails: the run then discards it, through the `ArtifactStore`'s `discard`, which removes a file only while it holds exactly the failed write's bytes. If it can't be removed, the message says the run reads as complete although the command failed. The message of any such ending, an unexpected exception's `internal.unexpected` included, says what the attempt's records say about the request, whether it was sent and may have been charged, and whether the run has its manifest.
- **The manifest.** `command.options` records `approve` and `json`, as given. Neither the configuration's path nor `--out` is recorded, because a path can name the user, and manifests may be shared ([D-14](spec.md#decisions)): `configuration.yaml` holds the configuration's bytes, and the manifest is in the output directory. Every run lists the layout's parser. `command.started_at` is when the command started: once the license is acknowledged, before it reads the configuration, so the run's duration includes planning and any wait for approval. The configuration's source record is acquired then; the request's when the attempt started; the response's when it ended. A response is `verified`, and the configuration `user_supplied`. `return_series` is `source_only` when the attempt saved a decoded response that holds per-period series: a `results.rows` array with a row, or a `chart` object holding an array with an entry. It's `absent` otherwise, as for a response such as `{}`, and the report then says nothing was preserved of turnover, positions, or per-period returns.
- **The demo.** `trialfolio demo` takes `run`'s steps, with `approval: not_required`, over a client that opens no connection. That client records the two exchanges a successful call records, `POST /auth` and `POST /screen/backtest`, each a 200, because the 1.0.0 attempt record holds an attempt that succeeded only with them. So the demo's run has every file and record of a real one, and its records read as a real run's do, possibly charged with one provider request. Its manifest is labeled synthetic, and its report says that its attempt, exchanges, and counts are invented and nothing was sent or charged. Its packaged configuration, the documented example retitled, and response, the `complete.json` fixture without `cost` and `quotaRemaining`, are in `src/trialfolio/demo_data/`, so the run reports no cost. The core can also execute an experiment with that client, which no 0.3.0 command does (R03-T05). It answers each case's request with the same response, and records Trial Folio's `POST /auth` only for an attempt that authenticates, as start and attempt records 1.1.0 allow ([experiment attempts](#experiment-attempts)). Such an experiment is synthetic ([the experiment manifest](#the-experiment-manifest)).
- **`trialfolio report`** gives `input.not_found` for a run directory that doesn't exist, and `input.not_a_run` for anything else that isn't a complete run.
- **`trialfolio review` (R02-T08).** It takes the steps [review output](#review-output) lists. `src/trialfolio/review.py` writes the review once the input check has passed and the output directory is checked, from the claim through the manifest.
  - **`command.started_at`** is when the command started, as for a run: once the license is acknowledged, before it reads the configuration. The configuration's source record is acquired then.
  - **stdout** holds a short summary on success: where the review and its report are, the flagged setting rows and the unavailable metric rows, as the JSON summary counts them, the `review_id`, and that statistical validation and trading readiness aren't assessed. When any result is synthetic, it says so, and that their values are invented.
  - **The command's events** carry the `review_id` from the claim on, `cli.command.unexpected` included. The input check's events come before the claim, when the review has no ID yet, and the store's events carry no ID, as for a run.
- **`trialfolio init` (R01-T19).** It writes the starter files in `src/trialfolio/init_data/` into the workspace, `.` when no directory is given: `screen.yaml`, which claims the workspace, then `README.md` and `.gitignore`. `src/trialfolio/starter.py` gives them.
  - **`screen.yaml`** is the [documented example](#example) without its purpose, with a comment on each key and on quoting the text Portfolio123 receives. Its settings resolve to the request Portfolio123 accepted in R01-T01.
  - **`README.md`** says what the workspace holds, and the next steps, with a link to the user guide at the version's release tag, which works once the version is tagged.
  - **`.gitignore`** keeps credential files (`.env*` and `*.env`) and the `runs/`, `reports/`, and `reviews/` folders at the workspace's top level out of Git, because runs, reports, and reviews hold Portfolio123 data. `reviews/` was added in 0.2.0, by the owner's decision of 2026-10-07 ([changes after sign-off](releases/0.2.0-review.md#changes-after-sign-off)).
  - **No acknowledgment.** It processes no data, so it needs no [license acknowledgment](#license-acknowledgment). It sends nothing.
  - **Its log** goes to the per-user log directory, as `trialfolio license`'s does, so the workspace holds only the starter files. When that directory is the workspace or in it, because `TRIALFOLIO_LOG_DIR` names one there or the workspace holds the home directory's default, `init` writes no log file, with a warning on stderr. So it never changes a directory it refuses. It compares the two paths as the file system would: their parts that exist by the file system's own identity, so a symbolic link, or another case or Unicode normalization that the file system ignores, can't hide the workspace, and their names that don't exist yet ignoring case and normalization. So a log directory that differs from a new workspace only that way gets no log file on any file system.
  - **A failure after the claim.** A write that fails, or an interrupt, after `screen.yaml` claimed the workspace leaves the files written so far. It removes nothing. The message gives the usual code, `storage.write_failed` or `command.interrupted`, says nothing was sent, and says the workspace holds some of the starter files, to remove before running `trialfolio init` there again.
  - **Nothing depends on a workspace.** No other command looks for one, and the starter files hold nothing Trial Folio reads back.
- **stdout and stderr.** Without `--json`, stdout holds a short summary on success, and nothing on failure. stderr shows the error with its full message, progress at INFO, and warnings. An argument the parser rejects is a usage error, exit 2, reported by the parser on stderr, without a JSON summary: no error code covers it. That includes a blank `--out`, empty or only whitespace, which names no directory of its own, and an `--out` that isn't valid UTF-8 text, such as a name in another encoding, which Python reads with lone surrogates: the summary's `output_dir` couldn't hold either. So is an invalid `--revision-reason` ([approving a revision](#experiment-plans-and-revisions)), or `--repeat` ([repeating a case](#repeating-a-case)). An error message that names a path from the command line or the environment, such as the configuration's, the run directory's, or the log's, writes its lone surrogates and its control and formatting characters as escapes, as the [plan display](#approval) does, so the summary can hold the message, and the path can't act on a terminal.
- **The JSON summary.** `counts.attempts` is 1 once an attempt record or a start record exists. `metrics_unavailable` is 0 when there's no `metrics.csv`. `warnings` counts the warnings logged during the command.
- **The entry function** is `trialfolio.cli.main(argv, *, endpoint, timeout, clock, store_factory)`. It returns the exit code, and reads `sys.stdin`, `sys.stdout`, and `sys.stderr` as they are when it's called. The installed command, and `python -m trialfolio`, call it with none of the keyword parameters.
- **Imports.** `run` and `demo` load the modules that import `p123api`, `requests`, or `urllib3` only after `installed_versions` has checked them, and it imports all three, `p123api` last, so a missing or broken one is `environment.unsupported` before the plan is shown, never an `ImportError`. `trialfolio report` and `trialfolio review` send nothing, so they check no versions, but they read runs with modules that import them: an `ImportError` loading those is `environment.unsupported` too. `review` loads them once its configuration is valid.

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

**The review's summary.** The committed 1.0.0 schema allows no key it doesn't list, and its `command` has no `review`, its `ids` no `review_id`, and its `counts` none of the review's counts. So, as an [open question](releases/0.2.0-review.md#open-questions) settled, 0.2.0 writes version 1.1.0 for every command: 1.0.0 with those keys added, each 1.0.0 key keeping its meaning. `schemas/json-summary-1.0.0.schema.json` stays committed, beside `json-summary-1.1.0.schema.json`, because it says what 0.1.0 prints, and its bytes don't change. Its `$comment` and its titles name the models that generate it, so the model that generates it now, `trialfolio.contracts.summary.JsonSummary`, keeps its module and name, and so does each model it uses. The 1.1.0 model takes a new name, `JsonSummaryV1_1`, and so does its `ids`, `SummaryIdsV1_1`.

**An experiment's summary (R03-T05).** Version 1.1.0's `ids` and `counts` hold one case's, and allow no other key. So, as an [open question](releases/0.3.0-experiments.md#open-questions) settled ([D-33](spec.md#decisions)), 0.3.0 writes version 1.2.0 for every command: 1.1.0 with an experiment's keys, below, each 1.1.0 key keeping its meaning, so a 1.1.0 summary with its version changed to 1.2.0 is a valid 1.2.0 summary. `schemas/json-summary-1.1.0.schema.json` stays committed, with its bytes unchanged, beside 1.0.0's and 1.2.0's, and the 1.1.0 model keeps its name. For `run` with an experiment configuration:

- **`ids`:** `experiment_id`, once the configuration is valid; `plan_hash`, the hash of the plan this run builds, the current plan or its revision, once it's built, even if it isn't approved, so `run --json` without approval gives the hash to approve, as for a screen; and `session`, the session's number, once its session record is written. An experiment has several cases and attempts, so `ids` holds no `case_id` or `attempt_id`: `cases` gives them.
- **`cases`:** a new key, given exactly for an experiment, once its plan is built: each case of that plan, in its order, with its `case_key`, its `case_id`, its `outcome` as the [experiment manifest](#the-experiment-manifest) counts it, `succeeded`, `failed`, `unknown`, or `not_yet_run`, and `repeat_attempt_id`. That's the `attempt_id` that `--repeat <case-key>:<attempt-id>` names to confirm a repeat of a case awaiting one, and `null` for any other case ([repeating a case](#repeating-a-case)). So a script can run the command without approval, read the plan's hash and the cases awaiting a repeat, and run it again with `--approve` and each `--repeat` it chooses.
- **`counts`:** the experiment's, as its manifest counts them, across every run of the experiment: `cases_planned`, `cases_succeeded`, `cases_failed`, `cases_skipped`, `cases_unknown`, `cases_not_yet_run`, `cases_retired`, `attempts`, `repeats`, `provider_requests`, `authentication_calls`, and `cost`, the credits Portfolio123 reported, or `null` when it reported none; `metrics_unavailable`, the `unavailable` rows of the planned cases' `metrics.csv`; and `warnings`, those this command logged. They're known once a new experiment's configuration is valid, or once a resumed experiment's records are read and checked. Before then, as after `experiment.locked`, `counts` is `{}`, because 0s would misstate an experiment that has attempts. So a summary gives `cases` with `{}` only when its error is `experiment.locked`, which a new experiment can get at its claim, after its plan is built; every other summary that gives `cases` gives the experiment's counts, as the owner decided on 2026-10-09 ([changes after sign-off](releases/0.3.0-experiments.md#changes-after-sign-off)). A configuration that isn't valid can't be known as an experiment's, so it gives a screen run's counts, each 0, as in 1.1.0.
- **Which plan.** `cases` and the case counts are over the plan this run builds, once it's built, and the current plan before then. Once approved, the plan this run builds is the current plan. Until a revision is approved, its `cases` and case counts give what the experiment would hold under it: its kept cases with their outcomes, its new cases `not_yet_run`, and the cases it would retire counted as retired. The outcomes are as the command leaves the records: as the session's manifest gives them, once it's written.
- **`output_dir`:** the directory as given on the command line, once this command writes into it: for a new experiment, from the claim, as for a screen; for a resume, from its session record, when its logging starts there. Before then it's `null`, with no `outputs`, as when a command creates no directory, so a resume that fails before its session, such as with `experiment.locked`, `input.not_a_run`, `plan.approval_required`, or `plan.changed`, gives `null`: it wrote nothing.
- **`outputs`:** `manifest` and `report`, the session's, once written. A case's tables have no key, since an experiment has a pair for each case: the manifest lists them.
- **The models (R03-T06).** The 1.2.0 model is `JsonSummaryV1_2`, and its `ids` `SummaryIdsV1_2`, so the 1.0.0 and 1.1.0 models keep their names. `cases` is left out when it isn't given, never `null`, so an experiment's summary gives `ids.plan_hash` exactly when it gives `cases`. A run ends `completed` or `partial` only once it has run its plan, with the outcome its session's [manifest](#the-experiment-manifest) gives, so the model requires `cases` then, and `completed` exactly when every case succeeded.

| Key | Meaning |
|---|---|
| `schema_version` | Summary schema version |
| `command` | For example `review` |
| `trialfolio_version` | Application version |
| `outcome` | `completed`, `partial`, or `failed` |
| `exit_code` | The process exit code |
| `ids` | Identifiers the command created, for example `{"review_id": "…"}`. For `run`: `plan_hash` and `case_id` once the plan is built, even if it isn't approved, and `attempt_id` whenever an attempt record or a start record exists, including after a failed authentication. For an experiment (1.2.0): `experiment_id`, `plan_hash`, and `session`, as above. Empty when it created none. |
| `output_dir` | The output directory as given on the command line, and `.` for `trialfolio init` given none. `null` if none was created. For an experiment (1.2.0), from the claim or a resume's session record, as above. |
| `outputs` | Output files relative to `output_dir`, keyed by role: `configuration` (the starter configuration `trialfolio init` writes), `manifest`, `report`, `metrics`, `settings`, `differences` |
| `cases` | For an experiment (1.2.0) only: each case of its plan, above. Left out for every other command and configuration. |
| `counts` | For `run`: `attempts`; `provider_requests`, the sends of the planned request that may have reached Portfolio123, never authentication ([HTTP exchanges](#http-exchanges)), which the [budget](#budget-and-retries) limits; `metrics_unavailable`; `warnings`; and the credit `cost` when the provider reports it. For `review` (0.2.0): `results`, `settings_flagged`, `metrics_unavailable`, `warnings` ([review output](#review-output)). For an experiment (1.2.0): the experiment's counts, above. |
| `statistical_validation`, `trading_readiness` | `not_assessed` in every 0.x release that doesn't assess them |
| `error` | `null`, or `{"code": …, "message": …}` using the codes in [errors](#errors) |

`ids` and `outputs` leave out a key that has no value, rather than writing `null`, and the summary leaves out `cases` when it isn't given. `counts` is `{}` for `init`, `report`, and `license`, and for an experiment until its counts are known. When `outcome` is `completed`, `exit_code` is 0 and `error` is `null`. Otherwise `exit_code` is the error code's exit code, and `outcome` is `partial` exactly for `execution.partial`. `schemas/json-summary-1.2.0.schema.json` gives every field of version 1.2.0, `schemas/json-summary-1.1.0.schema.json` every field of 1.1.0, and `schemas/json-summary-1.0.0.schema.json` every field of 1.0.0.

### License acknowledgment

**Requirement ([D-17](spec.md#decisions), [LIC-12](licensing-policy.md#lic-12-acceptance-and-acknowledgment)).** Before a command processes any data, the user acknowledges the license and the research notice once. This applies to `run`, `report`, and `demo`, and from 0.2.0 to `review`. From 0.3.0, `run` covers experiments too. Each acknowledgment covers one license identifier and one notice version. Only a change to either one asks again.

- **Interactive.** When stdin and stderr are both terminals and there's no valid acknowledgment, the CLI prints three things to stderr:
  - the concise notice
  - the license identifier and notice version
  - how to read the full text with `trialfolio license`

  It then asks the user to type `accept`. Any other answer exits with `license.not_acknowledged` and writes nothing.
- **Non-interactive.** There are two ways to acknowledge:
  - `trialfolio license --accept` records the acknowledgment.
  - Setting `TRIALFOLIO_ACCEPT_LICENSE` to `<license_id>/<notice_version>`, for example `LicenseRef-NSPRL-1.1/1.0`, acknowledges for that process only and records nothing, which suits CI.

  Without either, the command exits with `license.not_acknowledged`. The message gives both options and the exact value to use.
- **Exempt commands.** `trialfolio --version`, `--help`, `trialfolio init`, which processes no data, and `trialfolio license` work without an acknowledgment. `trialfolio license` prints the license, the full notice, and the acknowledgment status.
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
| `plan.approval_required` | 2 | A charged or mutating operation was requested without the matching plan hash: no `--approve`, a different hash, or a refused confirmation. Also `--revision-reason` when there's no revision to give a reason for, unless it's the reason the current plan recorded, which resumes it ([experiment plans and revisions](#experiment-plans-and-revisions)). Also a `--repeat` that names no case awaiting a repeat, or a repeat that isn't confirmed ([repeating a case](#repeating-a-case)). |
| `plan.changed` | 3 | The configuration or the installed versions no longer give an experiment's current plan, and the revision wasn't approved with a reason: no `--revision-reason`, no `--approve` with the revision's hash, or a refused confirmation ([experiment plans and revisions](#experiment-plans-and-revisions)). Otherwise, a hash given with `--approve` that doesn't match is `plan.approval_required`. |
| `output.not_empty` | 4 | The output directory exists and is not empty. For an experiment, it holds no `experiment.lock`, or it holds another experiment, by its `experiment_id` or its universe, one whose first plan was never recorded, or a synthetic experiment, which `run` doesn't resume ([running an experiment](#running-an-experiment)). In the core, the demo's client given an experiment that isn't synthetic fails with it too ([the experiment manifest](#the-experiment-manifest)). |
| `storage.write_failed` | 4 | An artifact could not be written durably. This is the code even when a request was already sent; the attempt record still gives the outcome ([endings that decide the error code](#endings-that-decide-the-error-code)). |
| `experiment.locked` | 4 | Another process holds the experiment lock ([the lock](#the-lock)) |
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
- Planning returns a plan model, and execution requires the approved plan hash. An experiment's execution also takes the confirmed repeats, each naming the attempt whose possible charge the user acknowledged ([repeating a case](#repeating-a-case)).
- Long-running execution reports progress through callbacks or events and supports cancellation between provider requests ([progress and cancellation](#running-an-experiment)). It holds a lock that prevents two processes from executing the same experiment ([the lock](#the-lock)), and it serializes Portfolio123 shared-state operations per account across processes, of which 0.3.0 has none, on the basis [the lock](#the-lock) gives.

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
- **Mechanism.** The standard `logging` module, with no added dependency. Core modules use `logging.getLogger(__name__)` and never configure handlers; the CLI configures them. The package gives its `trialfolio` logger a `NullHandler`, as the standard library recommends for a library, so a caller that configures no logging, such as another interface running the core, gets nothing on stderr from Python's last-resort handler (R03-T08, R03-AC13).
- **Format.** Log files hold one JSON object per line with these snake_case fields: `timestamp` (UTC ISO 8601), `level`, `event` (a stable dotted name), `message`, `trialfolio_version`, `component`, and the applicable `review_id`, `plan_hash`, `case_id`, `attempt_id`, `request_id`, and `parent_id`. The terminal shows human-readable messages on stderr from the same events.
- **Levels.** ERROR for a failed operation, WARNING for a degraded condition the command continues through, INFO for lifecycle milestones, and DEBUG for diagnostic detail. Log files record INFO and above. Setting `TRIALFOLIO_LOG_LEVEL` to `DEBUG`, `INFO`, `WARNING`, or `ERROR` changes that, for diagnosis. Any other value is ignored, with a warning on stderr. The content rules apply at every level.
- **Tracing.** Start and end events carry duration and outcome for each command, case, attempt, and provider request, linked by IDs, and this serves as the trace. OpenTelemetry is adopted only through an ADR, with local file exporters only.
- **Metrics.** There is no metrics system. Per-run counts and durations go in the manifest.
- **Storage.** Logs go to `logs/` inside the output directory, or to the per-user log directory for commands without one, such as `trialfolio license`, and for `trialfolio init`, so a workspace holds only its starter files. A command with an output directory holds its events in memory until it has [claimed the directory](#cli-behavior). If it stops before then, including when the claim fails, it writes no log file, and its messages appear only on stderr. The exception is `internal.unexpected`: the command then writes the held events to the per-user log directory, and its message names that file. Log size is bounded by rotation. The README documents the locations and how to delete them.
- **The per-user log directory** follows the same pattern as the [acknowledgment record](#license-acknowledgment), in each platform's conventional place for logs:
  - `TRIALFOLIO_LOG_DIR`, if set
  - otherwise `$XDG_STATE_HOME/trialfolio/logs` or `~/.local/state/trialfolio/logs` on Linux
  - `~/Library/Logs/trialfolio` on macOS
  - `%LOCALAPPDATA%\trialfolio\logs` on Windows

Initial event names: `cli.command.started`, `cli.command.completed`, `review.input.loaded`, `artifact.write.completed`, `artifact.sync.degraded`, `report.render.completed`, `plan.created`, `plan.approved`, `attempt.started`, `attempt.completed`, `attempt.unexpected`, `provider.request.started`, `provider.request.completed`, `provider.request.failed`, `provider.request.refused`, `case.completed`, `experiment.resumed`.

**The CLI's logging (R01-T14).** `src/trialfolio/logs.py` configures it:

- **The file** is `trialfolio.log`, in `<out>/logs/` or the per-user log directory, rotated at 1 MB with 3 older files kept. An `$XDG_STATE_HOME` or `$XDG_CONFIG_HOME` counts only when it's an absolute path, as the XDG Base Directory Specification says, and so does a Trial Folio variable only when it isn't empty.
- **The terminal** shows the events at INFO, as progress, and warnings, prefixed `Warning:`. Errors are the command's to show, with the full message; their log events hold the loggable message.
- **New events:** `cli.output.claimed`, when a command has claimed its output directory; `cli.command.unexpected`, for an unexpected exception outside an attempt, with its type and frames; `cli.environment.ignored`, for an ignored `SSLKEYLOGFILE` or `TRIALFOLIO_LOG_LEVEL`; `cli.log.unavailable`, when no log file can be opened, and the command carries on without one; `license.acknowledged`, and `license.record.failed`, when an interactive acknowledgment can't be recorded. `case.completed` ends a run that reached its manifest. From 0.2.0 (R02-T08), `review.response.shared` warns that results share a saved response ([review output](#review-output)). From 0.3.0 (R03-T08), an experiment's session logs `experiment.session.started`, `experiment.plan.recorded`, `experiment.stopped`, a warning that no later case starts and why, `experiment.case.invalid`, for a response that failed validation, and `experiment.session.ended`, with each plan by its number and hash and each case by its `case_id`.
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
| `review-configuration-1.0.0.schema.json` | [Review configuration](#review-configuration) |
| `plan-1.0.0.schema.json` | [Plan](#plan-contents) |
| `start-record-1.0.0.schema.json`, `attempt-record-1.0.0.schema.json` | [Start and attempt records](#execution-outcomes-and-attempts) |
| `run-manifest-1.0.0.schema.json` | [Run manifest](#artifact-storage) |
| `review-manifest-1.0.0.schema.json` | [Review manifest](#review-output) |
| `metrics-row-1.0.0.schema.json`, `settings-row-1.0.0.schema.json`, `differences-row-1.0.0.schema.json` | One row of each [normalized table](#normalized-tables) |
| `experiment-configuration-1.0.0.schema.json` | [Experiment configuration](#experiment-configuration) |
| `plan-1.1.0.schema.json` | [Experiment plan](#experiment-plans-and-revisions) |
| `experiment-record-1.0.0.schema.json`, `session-record-1.0.0.schema.json` | [`experiment.json`](#experimentjson), and the [session record](#experiment-output) |
| `authentication-record-1.0.0.schema.json`, `start-record-1.1.0.schema.json`, `attempt-record-1.1.0.schema.json` | [Experiment attempts](#experiment-attempts) |
| `experiment-manifest-1.0.0.schema.json` | [Experiment manifest](#the-experiment-manifest) |
| `json-summary-1.0.0.schema.json`, `json-summary-1.1.0.schema.json`, `json-summary-1.2.0.schema.json` | [JSON summary](#json-summary): 1.0.0, which 0.1.0 writes, and 1.1.0, which 0.2.0 writes, each with its bytes unchanged, and 1.2.0, which 0.3.0 writes |
| `license-acknowledgment.schema.json` | [License acknowledgment record](#license-acknowledgment), which has no schema version |

## Open questions

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| Are failed screen-backtest requests charged? | Budget accounting for failed and uncertain attempts | Until verified, count every send that may have reached Portfolio123 as possibly charged, whatever its outcome, and no other ([possibly charged](#http-exchanges)) | The owner compares the account's credit history, or asks Portfolio123. R01-T01's and R01-T05's calls didn't settle it. |
