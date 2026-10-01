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
| `parser_version` | Version of the importer that interpreted a source file, per supported layout |
| `canonicalization_version` | Version of the canonical-hashing rules used for identities |
| Provider wrapper version | `p123api` version used for provider requests (0.2.0 onward) |
| Method versions | Version of each analytical method applied (when methods are introduced) |
| `license_id`, `notice_version` | The applicable license identifier (`LicenseRef-NSPRL-1.0`) and financial-notice version (`1.0`), defined in [../LICENSE](../LICENSE) and [disclaimers.md](disclaimers.md) |

A schema's version does not need to match the release that introduces it. Compatibility is defined against documented readers and semantics, not merely against added fields.

## Identity

Identifiers are introduced with the release that can define their semantics.

| Identifier | Introduced | Meaning | Proposed form |
|---|---|---|---|
| `artifact_id` | 0.1.0 | Content address of one stored file | `sha256:<64 hex>` of the file's bytes |
| `review_id` | 0.1.0 | One `trialfolio review` output | Random UUID, version 4 |
| `label` | 0.1.0 | User-declared name of one compared result, unique within a review | `[a-z0-9][a-z0-9_-]{0,63}` |
| `plan_hash` | 0.2.0 | Identity of an approved plan | `sha256:` of the plan's canonical form |
| `case_id` | 0.2.0 | Stable identity of one fully resolved configuration | `case-` plus the first 16 hex digits of the SHA-256 of the canonical resolved configuration |
| `case_key` | 0.3.0 | User-declared readable name for a planned case | Same pattern as `label` |
| `attempt_id` | 0.2.0 | One execution attempt of a case | Random UUID, version 4 |
| `experiment_id` | 0.3.0 | One declared experiment | User-declared slug, same pattern as `label` |
| `study_id`, `candidate_id`, `assessment_id` | Later | Defined when their increment is specified | — |

Configuration identity and attempt identity MUST stay separate. Re-running the same resolved configuration creates a new attempt of the same case. Changing any resolved setting creates a different case.

## Provenance

**Requirement (INV-02).** Every setting, metadata value, and reported metric carries a provenance class:

| Class | Meaning |
|---|---|
| `verified` | Captured by Trial Folio from the provider during an attempt it executed, or independently confirmed and recorded as such |
| `user_supplied` | Read from a file the user provided, including imported exports and attached configurations |
| `inferred` | Derived by Trial Folio under a documented rule, for example a date range read from row dates; the rule is recorded |
| `unknown` | Not available from any source |

Everything in 0.1.0 is `user_supplied`, `inferred`, or `unknown`, because Trial Folio did not observe the original provider exchange. Each value also records its source artifact and location where applicable, for example the CSV column or YAML key.

## Configuration files

Configuration files are YAML documents owned by the user. The rules apply to every kind:

- Each file declares `kind` (`review`, `screen`, or `experiment`) and `schema_version`.
- Unknown keys are rejected, so misspellings fail instead of being ignored.
- YAML is loaded with a safe loader. Values are not coerced: a percentage is written as a number with a declared unit, not as `"5%"`; dates use `YYYY-MM-DD`; booleans are `true` or `false` only.
- Configuration never contains credentials. A credential-like key is rejected.
- File paths inside a configuration are resolved relative to the configuration file.
- Duplicate keys are rejected; a YAML loader must not silently keep the last one.

### Review configuration

Schema version 1.0.0, introduced in 0.1.0. Release 0.2.0 extends it to 1.1.0.

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
| `export` | path | Yes | A DataMiner export; must be a regular file |
| `configuration` | path | No | The DataMiner configuration that produced the export; must be a regular file |
| `description` | string | No | Up to 500 characters, shown in the report |
| `intended_changes` | list | No | Not allowed on the baseline entry |

**Each entry in `intended_changes`:**

| Key | Type | Required | Rules |
|---|---|---|---|
| `setting` | string | Yes | A normalized setting name from the verified layout's mapping ([supported import layouts](#supported-import-layouts); fixed by 0.1.0 task R01-T02). An unknown name fails with `config.invalid`, and the message lists the valid names. A result may list each setting at most once. |
| `reason` | string | Yes | 1–500 characters, shown in the report |

**Rules that span keys:**

- **Intended change not observed.** If a declared change isn't there because the two values are equal, the result is still valid. The difference is classified `same` and flagged `intended_change_not_observed`.
- **Intended change that can't be confirmed.** If the setting is missing from either result, the difference is `unknown` and is flagged.
- **Same export named twice.** Two entries may name the same export file. Identical bytes are flagged `identical_source`, as a warning.

Example (the setting name is illustrative until R01-T02 fixes the names):

```yaml
kind: review
schema_version: 1.0.0
title: Holdings 25 versus 50
purpose: Check whether doubling holdings changes risk as expected.
baseline: hold25
results:
  - label: hold25
    export: exports/hold25.csv
    configuration: configs/hold25.yaml
  - label: hold50
    export: exports/hold50.csv
    configuration: configs/hold50.yaml
    intended_changes:
      - setting: max_num_holdings
        reason: Doubling holdings is the change under review.
```

## Source artifacts

**Requirement (INV-04).** Source files are preserved byte for byte before anything is derived from them. A source artifact record contains:

- `artifact_id`, size, and the path relative to the output root.
- The original file name, which is recorded but not trusted as a path.
- Role: export, configuration, provider request, or provider response.
- Import or acquisition time in UTC.
- Source format identifier and version, for example the DataMiner ScreenBacktest CSV layout identifier once verified.
- The parser and parser version that interpreted it, or a statement that it was attached without interpretation.
- Provenance class, and source identity where available, for example the provider operation and account-independent identifiers.

Attached configuration files are preserved even when Trial Folio cannot interpret some of their settings. Uninterpreted settings are listed as such.

## Supported import layouts

**Status: no layout has been verified yet.** Release 0.1.0 task R01-T02 adds `dataminer-screenbacktest-csv` version 1 here. It is built from the reference exports in [reference/dataminer-screenbacktest/](../reference/dataminer-screenbacktest/README.md). Until then, Trial Folio makes no claim to import any export layout.

For each layout, this section records:

- **Identity.** The layout identifier and version, and the tool build it was observed from.
- **Structure.** The section structure and header rows used to detect the layout.
- **Metrics.** Each one's `metric_id`, its source label and location, its unit, the precision the source reports, and its definition.
- **Settings.** The documented configuration keys, each with its normalized setting name, category, and documented default. Time-dependent defaults are marked as such.
- **Everything else.** What the layout contains that Trial Folio preserves but does not interpret.

## Metrics and missing values

**Requirements (INV-03, INV-08).** A metric value carries:

| Concept | Meaning |
|---|---|
| Value | A decimal string carrying the source's precision, for example `"12.30"`. Never a float in interchange JSON, and never NaN or infinity. |
| Unit | One of `percent` (12.30 means 12.30%), `ratio` (dimensionless, for example beta or Sharpe), `currency:<ISO 4217 code>`, `count`, `days`, or `date` |
| Definition | A metric identifier and a reference to its documented definition; for imported metrics, the source's own label and the layout's documented meaning |
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

Each compared result has original settings, stored as they appear in the source, and resolved settings: normalized names, values, and units under the verified layout mapping. Settings that refer to mutable objects in the provider account, such as a saved ranking system or universe by name, are recorded as external references. Each one is marked snapshotted, if its definition was captured, or not snapshotted, with reproducibility labeled incomplete.

When a source tool applied a default because a setting was absent, the effective value is `inferred`: the record cites the documented default and the version of the documentation it came from. A default that depends on when the tool ran, such as an end date of "today", is `unknown` unless the data itself establishes it, for example the last date in a returned series. Trial Folio never assumes the run date.

Each setting in each non-baseline result is classified against the baseline:

| Class | Meaning |
|---|---|
| `same` | Equal resolved value |
| `intended_change` | Differs, and the configuration declares it as an intended change |
| `unexplained_mismatch` | Differs, and no intended change declares it |
| `unknown` | Missing or uninterpretable in at least one of the two results |

Settings in these categories are critical: dates, benchmark, currency, costs (commission and slippage), execution (price convention, rebalance timing, and similar), universe, and data source (data vendor and point-in-time method). An `unexplained_mismatch` or `unknown` in a critical category is flagged prominently in the report and the normalized output. An intended change to a critical setting is shown, but not as a defect.

Metric differences are computed only between comparable values: the same unit, the same definition, and compatible contexts. A difference is `candidate − baseline` in the metric's unit, and a difference between `percent` values is expressed in percentage points (`pp`). Relative differences are not reported unless a release specifies and labels them. When contexts differ, for example different benchmarks or periods, Trial Folio shows both values, does not report a difference, and explains why.

## Normalized tables

Schema version 1.0.0, introduced in 0.1.0. Release 0.2.0 writes the same tables from provider payloads. These tables are public contract. The manifest records each table's schema version, because a CSV file can't carry its own.

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
| `metric_id` | Stable identifier from the layout mapping, for example `annualized_return`. Coverage uses `coverage_start`, `coverage_end`, and `coverage_periods`. |
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
| `source_location` | Where the value was read: `<section>/<row label>/<column label>` in the verified layout. Empty for calculated values. |

### `settings.csv`

One row for each setting of each result. This includes documented settings that are absent and settings Trial Folio does not interpret.

| Column | Meaning |
|---|---|
| `label` | Result label |
| `setting` | Normalized setting name. For a setting Trial Folio doesn't interpret, the original key path. |
| `category` | `dates`, `benchmark`, `currency`, `costs`, `execution`, `universe`, `data_source`, or `other` |
| `critical` | `true` for the critical categories in [settings and differences](#settings-and-differences) |
| `value` | Normalized value. Lists, such as screen rules, are JSON arrays. Empty when unknown. |
| `unit` | Unit for numeric values. Empty otherwise. |
| `interpretation` | `interpreted` or `not_interpreted` |
| `provenance` | `user_supplied`, `inferred`, or `unknown` (`verified` from 0.2.0) |
| `inference_rule` | For `inferred` values, the rule and its source, for example DataMiner's documented default and the date the documentation was checked. Empty otherwise. |
| `original_key` | The key path in the source configuration, for example `Default Settings.Max Num Holdings`. Empty when absent. |
| `original_value` | The value exactly as written in the source. Empty when absent. |
| `source_artifact` | `artifact_id` of the configuration. Empty when no configuration was attached. |
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
| `inferred_default` | The value is a documented default the source tool applied |
| `time_dependent_default` | An absent setting whose default depends on when the tool ran, such as an End Date of "today". The value is `unknown` unless the data establishes it. |
| `unsupported_value` | The value is recorded, but it is unsupported and unverified, for example a data vendor other than FactSet ([D-16](spec.md#decisions)) |
| `coverage_mismatch` | Requested dates and actual coverage differ |
| `identical_source` | Two results have byte-identical exports |

## Execution outcomes and attempts

Introduced in 0.2.0.

| Outcome | Meaning |
|---|---|
| `planned` | In an approved plan; not started |
| `running` | A durable start record exists; the attempt has not finished |
| `succeeded` | The provider returned a response that was saved, and the attempt record is durably complete. This says nothing about the strategy. |
| `failed` | The attempt ended with a recorded error |
| `skipped` | Deliberately not run, with a reason |
| `unknown` | Completion is uncertain: a request may have been sent and a response was not durably recorded |

An attempt record contains the `attempt_id`, the `case_id`, start and end times, the outcome, any error code, references to the redacted request and the saved response, provider metadata, the wrapper version, and any charge or quota information the provider returned.

Trial Folio saves decoded provider payloads, which is what the wrapper exposes, and labels them as decoded payloads. It does not claim to capture HTTP bytes, status codes, or headers on success, because the verified wrapper does not expose them ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md#verification-notes)). Trial Folio configures the wrapper for a single HTTP attempt per call, so every retry is its own recorded attempt. The one exception is the wrapper's single re-authentication reissue after a 401 or 403, which Trial Folio cannot observe; attempt records state that limitation.

**Uncertain completion.** Trial Folio writes a `running` record durably before sending a request. On restart, a `running` attempt without a durable response becomes `unknown`. An `unknown` attempt is never retried automatically, because the original request may have been charged or may have changed provider state.

## Plans and approval

**Requirement (REQ-04).** Before any charged or mutating provider request, Trial Folio builds a plan from the configuration. A plan contains every fully resolved case, the requests each case needs, a request budget, the retry policy, and the categories of data that will leave the machine. Its `plan_hash` is the SHA-256 of its canonical form. Execution requires that exact hash as approval. If the plan changes, the approval no longer applies.

The CLI shows the plan and its hash. On an interactive terminal it MAY ask for confirmation. Non-interactive use requires the hash as an explicit option; release 0.2.0 fixes the option's name. The core never prompts.

## Artifact storage

**Requirement (REQ-05).** All artifact reads and writes go through the `ArtifactStore` interface. From 0.1.0 it has a local filesystem implementation.

- **Relative paths.** Paths in manifests are relative to the output root, never absolute, so a moved or served directory stays valid.
- **Immutability.** Source artifacts are never modified after they are written. Trial Folio never overwrites an existing artifact; corrections and migrations produce new artifacts.
- **Atomic writes.** Each file is written to a temporary name in the same directory, flushed and synced to disk, and then renamed into place.
- **Completion.** A case is complete only after its required payload and its attempt record are durably written. The manifest is written last, and a missing or incomplete manifest means the output is incomplete.
- **Hashes.** Hashes detect changes. They do not prove that a provider's data is scientifically correct, and they do not make local files tamper-proof.

Proposed layout for 0.1.0; the release specification owns the final layout:

```text
<out>/
  manifest.json
  sources/<label>/export.csv            byte-for-byte copy; original name recorded in manifest
  sources/<label>/configuration.yaml    byte-for-byte copy, when supplied
  normalized/metrics.csv
  normalized/settings.csv
  normalized/differences.csv
  report.html
  logs/                                 diagnostics; excluded from hashes and from the manifest's evidence
```

Releases 0.2.0 and 0.3.0 add `plan.json` and `cases/<case_id>/attempts/<attempt_id>/`, which holds `attempt.json`, `request.json` (redacted), and `response.json`. Release 0.3.0 adds `experiment.json` and a lock file.

The manifest records:

- `schema_version`, `artifact_type` (`review`, `run`, or `experiment`), `trialfolio_version`, and the creation time in UTC.
- The command and its non-secret options.
- Every input and output artifact with its `artifact_id`.
- Parser versions, `license_id`, and `notice_version`.
- A capability statement of what the artifact does and does not contain. For example, it says whether return series are present, and states `statistical_validation: not_assessed` and `trading_readiness: not_assessed`.
- Counts: results, cases, attempts by outcome, provider requests, retries, and returned cost or quota metadata.

Raw files and JSON metadata come first, and normalized tables are CSV. Parquet MAY be added for large tables when needed. SQLite MAY later index outputs, but it MUST NOT become a first-release prerequisite or the only copy of any evidence.

## Canonical hashing

Proposed default:

- Canonical JSON follows [RFC 8785, JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785), applied to the model's serialized form.
- Decimal values are strings carrying their declared precision.
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
| `trialfolio review <config> --out <dir>` | 0.1.0 | Compare imported results offline |
| `trialfolio demo --out <dir>` | 0.1.0 | Proposed: write the synthetic demo inputs and run a review offline |
| `trialfolio run <config> --out <dir>` | 0.2.0 | Plan and execute one supported screen backtest |
| `trialfolio experiment <config> --out <dir>` | 0.3.0 | Plan, execute, and resume a finite experiment |
| `trialfolio --version` | 0.1.0 | Print the application version |
| `trialfolio license [--accept]` | 0.1.0 | Print the license, the full notice, and the acknowledgment status; `--accept` records the acknowledgment |

- **stdout** carries the command's result: a short human summary, or with `--json` the [JSON summary](#json-summary).
- **stderr** carries progress, warnings, and errors, which come from the same events as the log file.
- **Output directory.** `review` and `run` create the output directory. They refuse to write into a directory that exists and is not empty (`output.not_empty`). There is no overwrite option in 0.1.0. `experiment` reuses an existing directory only to resume the same plan, as release 0.3.0 specifies.
- **Validation first.** All inputs are validated before the output directory is created, so an invalid or unsupported input writes nothing.
- **Partial success.** A command that finishes with some cases failed, skipped, or uncertain writes complete accounting and exits with code 6.

Exit codes (proposed default):

| Code | Meaning |
|---|---|
| 0 | Command completed and outputs were written. This says nothing about any strategy. |
| 1 | Unexpected internal error |
| 2 | Usage error: invalid arguments, missing plan approval, or license not acknowledged |
| 3 | Invalid or unsupported configuration, input, or artifact |
| 4 | Output problem: directory not empty, write failure, or experiment locked by another process |
| 5 | Provider error: authentication, quota, unsupported capability, or invalid response |
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
| `ids` | Identifiers the command created, for example `{"review_id": "…"}`. Empty when it created none. |
| `output_dir` | The output directory as given on the command line. `null` if none was created. |
| `outputs` | Output files relative to `output_dir`, keyed by role: `manifest`, `report`, `metrics`, `settings`, `differences` |
| `counts` | For `review`: `results`, `settings_flagged`, `metrics_unavailable`, `warnings` |
| `statistical_validation`, `trading_readiness` | `not_assessed` in every 0.x release that doesn't assess them |
| `error` | `null`, or `{"code": …, "message": …}` using the codes in [errors](#errors) |

### License acknowledgment

**Requirement ([D-17](spec.md#decisions), [LIC-12](licensing-policy.md#lic-12-acceptance-and-acknowledgment)).** Before a command processes any data, the user acknowledges the license and the research notice once. This applies to `review` and `demo`, and later to `run` and `experiment`. Each acknowledgment covers one license identifier and one notice version. Only a change to either one asks again.

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
| `import.unsupported_layout` | 3 | The export does not match a verified layout; the message names the supported layouts |
| `import.malformed` | 3 | The export matches a layout but a row or value is invalid |
| `artifact.unknown_schema_version` | 3 | An artifact's schema version has no reader |
| `license.not_acknowledged` | 2 | A data-processing command ran without an acknowledgment of the current license and notice versions |
| `plan.approval_required` | 2 | A charged or mutating operation was requested without the matching plan hash |
| `plan.changed` | 3 | The configuration no longer resolves to the approved or saved plan |
| `output.not_empty` | 4 | The output directory exists and is not empty |
| `storage.write_failed` | 4 | An artifact could not be written durably |
| `experiment.locked` | 4 | Another process holds the experiment lock |
| `provider.auth_failed` | 5 | Credentials were rejected or missing |
| `provider.quota_exceeded` | 5 | The provider refused the request because of quota or credits |
| `provider.unsupported_capability` | 5 | The requested setting or operation is not supported by the verified provider path |
| `provider.response_invalid` | 5 | The response was saved but failed validation |
| `provider.outcome_unknown` | 5 | A request may have been sent, but no response was durably recorded, for example after a read timeout; it is never retried automatically |
| `execution.partial` | 6 | Some planned cases did not succeed; all are accounted for |
| `internal.unexpected` | 1 | A defect; the message asks the user to report it with the log location |

## Interface-independent core

**Requirement (REQ-03).** The CLI is the first interface, not necessarily the only one.

- The CLI parses arguments, reads configuration files, injects credentials, calls core functions, formats output, and maps errors to exit codes.
- Core functions accept validated models and return result models. They do not print, prompt, parse arguments, exit the process, read environment variables, or read secrets.
- Importers accept file content together with a declared source name, not only a filesystem path.
- Planning returns a plan model, and execution requires the approved plan hash.
- Long-running execution reports progress through callbacks or events and supports cancellation between provider requests. It holds a lock that prevents two processes from executing the same experiment, and it serializes Portfolio123 shared-state operations per account across processes.

## Protocols

Protocols are introduced only when a release needs them. Each protocol's documentation states its preconditions, return type, exceptions, side effects, and capability limits. Data lives in models and behavior in protocols, and dependencies are passed explicitly, never through global clients.

| Protocol | Release | Responsibility |
|---|---|---|
| `ResultImporter` | 0.1.0 | Interpret one verified export layout from content plus a source name, and return a validated imported result or `import.unsupported_layout` / `import.malformed` |
| `ArtifactStore` | 0.1.0 | Persist and read artifacts by relative path, with atomic writes and immutability as above |
| `ReportRenderer` | 0.1.0 | Render a saved comparison or assessment to HTML without provider or network access |
| `ScreenBacktestClient` | 0.2.0 | Execute the one supported screen-backtest request and return the captured provider evidence |
| `ModelClient` | Later | Send a bounded structured request to the configured model backend and return validated output with usage metadata ([REQ-10](spec.md#enduring-requirements)) |

There is no universal provider interface, plugin registry, or service framework. Import and execution paths converge on the same result model without pretending to be the same operation. A runtime-checkable protocol does not verify signatures or behavior, so static type checking and contract tests carry those obligations.

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
- **Content.** Logs never contain credentials, strategy definitions, formulas, configuration values, provider payloads, results, or imported file contents, at any level. Artifacts are referenced by ID and hash instead. Validation errors are logged with `errors(include_input=False)`, or with `hide_input_in_errors` enabled, and logged tracebacks omit local variables.
- **Mechanism (proposed default).** The standard `logging` module, with no added dependency. Core modules use `logging.getLogger(__name__)` and never configure handlers; the CLI configures them.
- **Format.** Log files hold one JSON object per line with these snake_case fields: `timestamp` (UTC ISO 8601), `level`, `event` (a stable dotted name), `message`, `trialfolio_version`, `component`, and the applicable `review_id`, `case_id`, `attempt_id`, `request_id`, and `parent_id`. The terminal shows human-readable messages on stderr from the same events.
- **Levels.** ERROR for a failed operation, WARNING for a degraded condition the command continues through, INFO for lifecycle milestones, and DEBUG for diagnostic detail.
- **Tracing.** Start and end events carry duration and outcome for each command, case, attempt, and provider request, linked by IDs, and this serves as the trace. OpenTelemetry is adopted only through an ADR, with local file exporters only.
- **Metrics.** There is no metrics system. Per-run counts and durations go in the manifest.
- **Storage.** Logs go to `logs/` inside the output directory, or to a per-user local log directory for commands without one. Log size is bounded by rotation. The README documents the locations and how to delete them.

Initial event names: `cli.command.started`, `cli.command.completed`, `review.import.started`, `review.import.completed`, `artifact.write.completed`, `report.render.completed`, `plan.created`, `attempt.started`, `attempt.completed`, `provider.request.started`, `provider.request.completed`, `provider.request.failed`, `case.completed`, `experiment.resumed`.

## Fixtures

**Requirement (REQ-11).** Committed fixtures are synthetic by default. A fixture that mirrors a verified provider layout copies its structure — column names, order, and formats — and never its data. Each fixture directory records:

- Its origin, and the layout version it mirrors.
- Its redistribution status.
- The requirements or acceptance criteria it exercises.

Expected outputs change only with a stated reason. Reference exports and payloads procured with the owner's account ([D-09](spec.md#decisions)) stay local and git-ignored unless Portfolio123's terms are confirmed to permit redistribution. No fixture, sample configuration, or sample export is copied from DataMiner or FactorMiner repositories.

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
| Which setting names and metric identifiers does the verified ScreenBacktest layout provide? | The normalized setting names, the metric definitions, and the `comparison.yaml` intended-change keys | Derive them from the reference export procured in [0.1.0](releases/0.1.0-review.md), task R01-T01 | Before 0.1.0 is Ready |
| What is the non-interactive plan-approval option called? | CLI contract for 0.2.0 | `--approve <plan-hash>` | 0.2.0 specification |
| Are failed screen-backtest requests charged? | Budget accounting for failed and uncertain attempts | Count them against the budget as possibly charged until verified | 0.2.0 live integration check |
