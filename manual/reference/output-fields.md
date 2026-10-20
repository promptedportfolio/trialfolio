# Output file fields

This page lists the fields of each JSON file Trial Folio writes, at the version it writes now, generated from the file's committed schema. Each section links to the section of the specification, [contracts.md](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md), that gives the file's rules.

[Outputs](outputs.md) says where each file is, and what the CSV files' columns hold. A file's `schema_version` names the version of its schema, except the license acknowledgment's record, which has none.

From release 0.4.0, a run or an experiment whose ranking is a ranking system's definition, given in a file or by a ranking snapshot, writes later versions of some of its files, which hold the definition, its two requests, and each node's weight. Each has a section of its own, after the files a run or an experiment ranked any other way writes. A ranking snapshot's own files come last but two.

## A run's `manifest.json`

A run's manifest, in its output directory, is written last. [Artifact storage](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#artifact-storage), in the specification, gives its rules.

<!-- generated: output-fields-run-manifest -->

Its schema: [`schemas/run-manifest-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/run-manifest-1.0.0.schema.json).

The manifest of a run written by `trialfolio run` or `trialfolio demo`.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `artifact_type` | Yes | `run` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `created_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `command` | Yes | An [object](#output-fields-run-manifest-command) | |
| `synthetic` | Yes | `true` or `false` | True for the synthetic run `trialfolio demo` writes. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `approval` | Yes | `interactive`, `option`, or `not_required` | |
| `outcome` | Yes | `completed`, `partial`, or `failed` | |
| `error` | Yes | An [object](#output-fields-run-manifest-error) or `null` | Null exactly when the outcome is `completed`. `execution.partial` exactly when it's `partial`. |
| `artifacts` | Yes | A list of [objects](#output-fields-run-manifest-artifacts) | |
| `parsers` | Yes | A list of [objects](#output-fields-run-manifest-parsers) | |
| `license_id` | Yes | `LicenseRef-`, then letters, digits, `.`, and `-` | |
| `notice_version` | Yes | Text, not all whitespace | |
| `capabilities` | Yes | An [object](#output-fields-run-manifest-capabilities) | |
| `reproducibility` | Yes | An [object](#output-fields-run-manifest-reproducibility) | |
| `counts` | Yes | An [object](#output-fields-run-manifest-counts) | |

### `command` { #output-fields-run-manifest-command }

The command that wrote the run, its non-secret options, and when it started.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | `run` or `demo` | |
| `options` | Yes | An object whose keys are text, not empty; each key that's not all whitespace has a value that's text; `true` or `false`; or `null` | The command-line options as given, by name, such as `out` and `approve`. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |

### `error` { #output-fields-run-manifest-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `artifacts` { #output-fields-run-manifest-artifacts }

One file of the run, by path, content address, and role.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `size` | Yes | An integer, 0 or more | |
| `role` | Yes | `plan`, `configuration`, `start_record`, `attempt_record`, `provider_request`, `provider_response`, `provider_response_undecoded`, `metrics`, `settings`, or `report` | |
| `schema_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0`; or `null` | The file's schema version, for files that have one, such as the normalized tables. |
| `source` | Yes | An [object](#output-fields-run-manifest-artifacts-source) or `null` | Given exactly for source artifacts. |

### `artifacts[].source` { #output-fields-run-manifest-artifacts-source }

What makes a file a source artifact: when and how it was acquired, and how it's read.

| Field | Required | Value | Description |
|---|---|---|---|
| `acquired_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `format` | Yes | Text, not all whitespace | The source format, such as `screen-configuration` or `p123api-screen-backtest`. |
| `format_version` | Yes | Text, not all whitespace | |
| `parser_version` | Yes | An integer, 1 or more; or `null` | The version of the adapter that interpreted it; null when nothing interpreted it. |
| `provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `operation` | Yes | `screen_backtest` or `null` | The provider operation that produced it; null for a file the user wrote. |

### Each of `parsers` { #output-fields-run-manifest-parsers }

The parser version applied to one provider response layout.

| Field | Required | Value | Description |
|---|---|---|---|
| `layout` | Yes | Text, not all whitespace | |
| `layout_version` | Yes | An integer, 1 or more | |
| `parser_version` | Yes | An integer, 1 or more | |

### `capabilities` { #output-fields-run-manifest-capabilities }

What the run does and doesn't contain.

| Field | Required | Value | Description |
|---|---|---|---|
| `return_series` | Yes | `source_only` or `absent` | `source_only`: the saved response holds per-period series, which are preserved but not normalized, charted, or analyzed. `absent`: no saved response holds any. |
| `statistical_validation` | Yes | `not_assessed` | |
| `trading_readiness` | Yes | `not_assessed` | |

### `reproducibility` { #output-fields-run-manifest-reproducibility }

Whether the run's settings fully record what was run. A reference to an account object that wasn't snapshotted makes it incomplete.

| Field | Required | Value | Description |
|---|---|---|---|
| `status` | Yes | `complete` or `incomplete` | |
| `external_references` | Yes | A list of [objects](#output-fields-run-manifest-reproducibility-external-references) | |

### Each of `reproducibility.external_references` { #output-fields-run-manifest-reproducibility-external-references }

A setting that names a mutable object in the provider account.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | Lowercase letters, digits, and `_`, starting with a letter | |
| `snapshotted` | Yes | `true` or `false` | |

### `counts` { #output-fields-run-manifest-counts }

The run's counts. `quotaRemaining` stays in the attempt record, out of the manifest.

| Field | Required | Value | Description |
|---|---|---|---|
| `results` | Yes | An integer, 0 or more | |
| `cases` | Yes | An integer, 0 or more | |
| `attempts` | Yes | An [object](#output-fields-run-manifest-counts-attempts) | |
| `provider_requests` | Yes | An integer, 0 or more | The sends of the planned request that may have reached Portfolio123 (JSON summary). |
| `retries` | Yes | An integer, 0 or more | |
| `cost` | Yes | An integer, 0 or more; or `null` | The credits Portfolio123 reported charging; null when it reported none. |

### `counts.attempts` { #output-fields-run-manifest-counts-attempts }

Attempts, by outcome.

| Field | Required | Value | Description |
|---|---|---|---|
| `succeeded` | Yes | An integer, 0 or more | |
| `failed` | Yes | An integer, 0 or more | |
| `unknown` | Yes | An integer, 0 or more | |
| `running` | Yes | An integer, 0 or more | |

<!-- end generated: output-fields-run-manifest -->

## A run's `plan.json`

A run's plan, in its output directory. [Plan contents](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plan-contents), in the specification, gives its rules.

<!-- generated: output-fields-run-plan -->

Its schema: [`schemas/plan-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/plan-1.0.0.schema.json).

A plan: every resolved case, its requests, the budget, the retry policy, and the data sent. Execution requires its `plan_hash` as approval (plans and approval).

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `canonicalization_version` | Yes | `1` | |
| `provider_wrapper` | Yes | An [object](#output-fields-run-plan-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-run-plan-transport) | |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | |
| `purpose` | Yes | Text, 1 to 2,000 characters, not all whitespace; or `null` | |
| `cases` | Yes | A list of exactly one [object](#output-fields-run-plan-cases) | |
| `budget` | Yes | An [object](#output-fields-run-plan-budget) | |
| `retry_policy` | Yes | An [object](#output-fields-run-plan-retry-policy) | |
| `data_sent` | Yes | A list of exactly 3 [objects](#output-fields-run-plan-data-sent) | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `provider_wrapper` { #output-fields-run-plan-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-run-plan-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### Each of `cases` { #output-fields-run-plan-cases }

One fully resolved case. A 1.0.0 plan has exactly one.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `requests` | Yes | A list of exactly one [object](#output-fields-run-plan-cases-requests) | |
| `settings` | Yes | A list of [objects](#output-fields-run-plan-cases-settings) | |

### Each of `cases[].requests` { #output-fields-run-plan-cases-requests }

One provider request a case needs.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `screen_backtest` | |
| `params` | Yes | An [object](#output-fields-run-plan-cases-requests-params) | |

### `cases[].requests[].params` { #output-fields-run-plan-cases-requests-params }

The JSON object passed to p123api's `screen_backtest`, exactly as it will be sent. `slippage` is always a JSON float, and every other number an integer (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `screen` | Yes | An [object](#output-fields-run-plan-cases-requests-params-screen) | |
| `startDt` | Yes | A date, `YYYY-MM-DD` | |
| `endDt` | Yes | A date, `YYYY-MM-DD` | |
| `pitMethod` | Yes | `Complete` | |
| `precision` | Yes | `4` | |
| `transPrice` | Yes | `1` | |
| `slippage` | Yes | A number | |
| `rebalFreq` | Yes | `Every Week` or `Every 4 Weeks` | |

### `cases[].requests[].params.screen` { #output-fields-run-plan-cases-requests-params-screen }

The `screen` object of a screen backtest request.

| Field | Required | Value | Description |
|---|---|---|---|
| `type` | Yes | `stock` | |
| `universe` | Yes | Text, not all whitespace | |
| `maxNumHoldings` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |
| `method` | Yes | `long` | |
| `currency` | Yes | `USD` | |
| `benchmark` | Yes | Text, not all whitespace | |
| `ranking` | Yes | An [object](#output-fields-run-plan-cases-requests-params-screen-ranking); text, not all whitespace; or an integer, from 1 to 9,007,199,254,740,991 | |
| `rules` | Yes | A list of at least one [object](#output-fields-run-plan-cases-requests-params-screen-rules) | |

### `cases[].requests[].params.screen.ranking` { #output-fields-run-plan-cases-requests-params-screen-ranking }

A single-formula ranking, as sent.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |
| `lowerIsBetter` | Yes | `true` or `false` | |

### Each of `cases[].requests[].params.screen.rules` { #output-fields-run-plan-cases-requests-params-screen-rules }

One screening rule, as sent. It has no `type` field: Portfolio123 rejects one.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |

### Each of `cases[].settings` { #output-fields-run-plan-cases-settings }

One resolved setting: a `settings.csv` row without `label`, `original_key`, `original_value`, and `source_artifact`, with `expected_provenance` for `provenance`.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | Lowercase letters, digits, and `_`, starting with a letter | |
| `category` | Yes | `dates`, `benchmark`, `currency`, `costs`, `execution`, `universe`, `data_source`, `strategy`, or `other` | |
| `critical` | Yes | `true` or `false` | |
| `value` | Yes | An integer, from 0 to 9,007,199,254,740,991; text, not all whitespace; a list of items, each text, not all whitespace; or one of these objects: [`cases[].settings[].value` with `formula`](#output-fields-run-plan-cases-settings-value-formula), [`cases[].settings[].value` with `name`](#output-fields-run-plan-cases-settings-value-name), or [`cases[].settings[].value` with `id`](#output-fields-run-plan-cases-settings-value-id) | |
| `unit` | Yes | `count`, `weeks`, or `percent`; or `null` | |
| `interpretation` | Yes | `interpreted` or `not_interpreted` | |
| `expected_provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `inference_rule` | Yes | Text, not all whitespace; or `null` | |
| `flags` | Yes | A list of items, each `inferred_default` or `not_snapshotted` | |

### `cases[].settings[].value` with `formula` { #output-fields-run-plan-cases-settings-value-formula }

A ranking by a single formula, the recommended form.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |
| `lower_is_better` | Yes | `true` or `false` | |

### `cases[].settings[].value` with `name` { #output-fields-run-plan-cases-settings-value-name }

An existing ranking system in the account, by name. It's recorded as not snapshotted.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | Text, not all whitespace | |

### `cases[].settings[].value` with `id` { #output-fields-run-plan-cases-settings-value-id }

An existing ranking system in the account, by ID. It's recorded as not snapshotted.

| Field | Required | Value | Description |
|---|---|---|---|
| `id` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |

### `budget` { #output-fields-run-plan-budget }

The request budget (budget and retries).

| Field | Required | Value | Description |
|---|---|---|---|
| `provider_requests` | Yes | `1` | A 1.0.0 plan has one request, sent at most once. |
| `credits_per_request` | Yes | An integer, 0 or more | Portfolio123's documented cost of one request when the plan was made. It isn't fixed, because Portfolio123 can change it. |
| `credits_per_request_source` | Yes | An [object](#output-fields-run-plan-budget-credits-per-request-source) | |
| `credits` | Yes | An integer, 0 or more | |
| `authentication_calls` | Yes | `1` | |

### `budget.credits_per_request_source` { #output-fields-run-plan-budget-credits-per-request-source }

Where a documented value comes from, and the date the documentation was checked.

| Field | Required | Value | Description |
|---|---|---|---|
| `title` | Yes | Text, not all whitespace | |
| `url` | Yes | An `https://` address, without spaces | |
| `checked` | Yes | A date, `YYYY-MM-DD` | |

### `retry_policy` { #output-fields-run-plan-retry-policy }

The retry policy: no automatic retries, and one exchange per wrapper call.

| Field | Required | Value | Description |
|---|---|---|---|
| `automatic_retries` | Yes | `0` | |
| `wrapper_attempts_per_call` | Yes | `1` | |
| `exchanges_per_call` | Yes | `1` | |

### Each of `data_sent` { #output-fields-run-plan-data-sent }

A category of data that leaves the machine, its recipient, and the settings it carries.

| Field | Required | Value | Description |
|---|---|---|---|
| `category` | Yes | `credentials`, `strategy_definition`, or `backtest_settings` | |
| `recipient` | Yes | `Portfolio123` | |
| `via` | Yes | `p123api` | |
| `settings` | Yes | A list of items, each lowercase letters, digits, and `_`, starting with a letter | |

<!-- end generated: output-fields-run-plan -->

## A run's `started.json`

The start record of a run's attempt, in `cases/<case_id>/attempts/<attempt_id>/`. [Execution outcomes and attempts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#execution-outcomes-and-attempts), in the specification, gives its rules.

<!-- generated: output-fields-run-start-record -->

Its schema: [`schemas/start-record-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/start-record-1.0.0.schema.json).

The start record, written durably just before the request is sent. Without an attempt record beside it, the attempt is `running` (uncertain completion).

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `provider_wrapper` | Yes | An [object](#output-fields-run-start-record-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-run-start-record-transport) | |
| `exchanges` | Yes | A list of exactly one [object](#output-fields-run-start-record-exchanges) | The successful authentication exchange completed before the request in 0.1.0. |

### `provider_wrapper` { #output-fields-run-start-record-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-run-start-record-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### Each of `exchanges` { #output-fields-run-start-record-exchanges }

One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An HTTP method in capitals, a space, and a path that starts with `/`, without spaces | The method and path, such as `POST /auth` or `POST /screen/backtest`. |
| `result` | Yes | `response`, `not_connected`, or `interrupted` | |
| `status` | Yes | An integer, from 100 to 599; or `null` | The HTTP status of a `response`; null otherwise. |
| `note` | Yes | `completed_from_saved_response` or `null` | Set only on a restarted attempt's request exchange, recorded as a 200 because its response was found saved (uncertain completion); null otherwise. |

<!-- end generated: output-fields-run-start-record -->

## A run's `attempt.json`

The attempt record of a run's attempt, beside its start record. [Execution outcomes and attempts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#execution-outcomes-and-attempts), in the specification, gives its rules.

<!-- generated: output-fields-run-attempt-record -->

Its schema: [`schemas/attempt-record-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/attempt-record-1.0.0.schema.json).

The attempt record, written once when the attempt ends: everything in the start record, plus how the attempt ended.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `provider_wrapper` | Yes | An [object](#output-fields-run-attempt-record-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-run-attempt-record-transport) | |
| `ended_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `outcome` | Yes | `succeeded`, `failed`, or `unknown` | |
| `error` | Yes | An [object](#output-fields-run-attempt-record-error) or `null` | Null exactly when the outcome is `succeeded`. |
| `exchanges` | Yes | A list of [objects](#output-fields-run-attempt-record-exchanges) | Every exchange, in order. |
| `possibly_charged` | Yes | `true` or `false` | True when a send of the request may have reached Portfolio123 (possibly charged). |
| `request` | Yes | An [object](#output-fields-run-attempt-record-request) or `null` | The redacted request, `request.json`. |
| `response` | Yes | An [object](#output-fields-run-attempt-record-response) or `null` | |
| `provider_metadata` | Yes | An [object](#output-fields-run-attempt-record-provider-metadata) | |

### `provider_wrapper` { #output-fields-run-attempt-record-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-run-attempt-record-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `error` { #output-fields-run-attempt-record-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `exchanges` { #output-fields-run-attempt-record-exchanges }

One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An HTTP method in capitals, a space, and a path that starts with `/`, without spaces | The method and path, such as `POST /auth` or `POST /screen/backtest`. |
| `result` | Yes | `response`, `not_connected`, or `interrupted` | |
| `status` | Yes | An integer, from 100 to 599; or `null` | The HTTP status of a `response`; null otherwise. |
| `note` | Yes | `completed_from_saved_response` or `null` | Set only on a restarted attempt's request exchange, recorded as a 200 because its response was found saved (uncertain completion); null otherwise. |

### `request` { #output-fields-run-attempt-record-request }

A file in the output directory, by path and content address.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `response` { #output-fields-run-attempt-record-response }

The saved response: `response.json`, the decoded payload, or `response.raw`, the body of a 200 the wrapper couldn't decode.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `form` | Yes | `decoded` or `undecoded` | |

### `provider_metadata` { #output-fields-run-attempt-record-provider-metadata }

What the provider reported about the charge: `cost` and `quotaRemaining`. Each is null when the response doesn't carry it.

| Field | Required | Value | Description |
|---|---|---|---|
| `cost` | Yes | An integer, 0 or more; or `null` | |
| `quota_remaining` | Yes | An integer, 0 or more; or `null` | `quotaRemaining`: account information, kept out of shareable outputs. |

<!-- end generated: output-fields-run-attempt-record -->

## A run's `manifest.json` 1.1.0, with a ranking definition

The manifest of a run whose ranking is a ranking system's definition. A run ranked any other way writes [version 1.0.0](#a-runs-manifestjson). [Artifact storage](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#artifact-storage), in the specification, gives its rules.

<!-- generated: output-fields-ranking-run-manifest -->

Its schema: [`schemas/run-manifest-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/run-manifest-1.1.0.schema.json).

The manifest of a run whose ranking is a definition: 1.0.0's, with the files the definition adds. A run the core writes with the demo's client, which no command writes, is synthetic, with no command (a run with a ranking definition).

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.1.0` | |
| `artifact_type` | Yes | `run` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `created_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `command` | Yes | An [object](#output-fields-ranking-run-manifest-command) or `null` | Null for a run the core writes with the demo's client, which no command writes. |
| `synthetic` | Yes | `true` or `false` | True exactly for a run `trialfolio demo` writes, or one the core writes with the demo's client. Its values, attempt, and counts are invented. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `approval` | Yes | `interactive`, `option`, or `not_required` | `not_required` exactly for a synthetic run, which sends nothing. |
| `outcome` | Yes | `completed`, `partial`, or `failed` | |
| `error` | Yes | An [object](#output-fields-ranking-run-manifest-error) or `null` | Null exactly when the outcome is `completed`. `execution.partial` exactly when it's `partial`. |
| `artifacts` | Yes | A list of [objects](#output-fields-ranking-run-manifest-artifacts) | |
| `parsers` | Yes | A list of [objects](#output-fields-ranking-run-manifest-parsers) | |
| `license_id` | Yes | `LicenseRef-`, then letters, digits, `.`, and `-` | |
| `notice_version` | Yes | Text, not all whitespace | |
| `capabilities` | Yes | An [object](#output-fields-ranking-run-manifest-capabilities) | |
| `reproducibility` | Yes | An [object](#output-fields-ranking-run-manifest-reproducibility) | |
| `counts` | Yes | An [object](#output-fields-ranking-run-manifest-counts) | `provider_requests` counts both kinds of request, and `cost` sums the costs Portfolio123 reported for both. |

### `command` { #output-fields-ranking-run-manifest-command }

The command that wrote the run, its non-secret options, and when it started.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | `run` or `demo` | |
| `options` | Yes | An object whose keys are text, not empty; each key that's not all whitespace has a value that's text; `true` or `false`; or `null` | The command-line options as given, by name, such as `out` and `approve`. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |

### `error` { #output-fields-ranking-run-manifest-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `artifacts` { #output-fields-ranking-run-manifest-artifacts }

One file of a run with a ranking definition, by path, content address, and role.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `size` | Yes | An integer, 0 or more | |
| `role` | Yes | `plan`, `configuration`, `ranking_definition`, `ranking_snapshot_record`, `update_record`, `start_record`, `attempt_record`, `rank_update_request`, `rank_update_response`, `rank_update_response_undecoded`, `provider_request`, `provider_response`, `provider_response_undecoded`, `metrics`, `settings`, or `report` | |
| `schema_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0`; or `null` | The file's schema version, for files that have one, such as the records and tables. |
| `source` | Yes | An [object](#output-fields-ranking-run-manifest-artifacts-source) or `null` | Given exactly for source artifacts. |

### `artifacts[].source` { #output-fields-ranking-run-manifest-artifacts-source }

A source record in a manifest with a ranking definition: 1.0.0's, whose provider operation may also be the `rank_update` or a snapshot's `rank_get`.

| Field | Required | Value | Description |
|---|---|---|---|
| `acquired_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `format` | Yes | Text, not all whitespace | The source format, such as `ranking-definition` or `p123api-rank-update`. |
| `format_version` | Yes | Text, not all whitespace | |
| `parser_version` | Yes | An integer, 1 or more; or `null` | The version of the adapter that interpreted it; null when nothing interpreted it. |
| `provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `operation` | Yes | `screen_backtest`, `rank_update`, or `rank_get`; or `null` | The provider operation that produced it; null for a file the user wrote. |

### Each of `parsers` { #output-fields-ranking-run-manifest-parsers }

The parser version applied to one provider response layout.

| Field | Required | Value | Description |
|---|---|---|---|
| `layout` | Yes | Text, not all whitespace | |
| `layout_version` | Yes | An integer, 1 or more | |
| `parser_version` | Yes | An integer, 1 or more | |

### `capabilities` { #output-fields-ranking-run-manifest-capabilities }

What the run does and doesn't contain.

| Field | Required | Value | Description |
|---|---|---|---|
| `return_series` | Yes | `source_only` or `absent` | `source_only`: the saved response holds per-period series, which are preserved but not normalized, charted, or analyzed. `absent`: no saved response holds any. |
| `statistical_validation` | Yes | `not_assessed` | |
| `trading_readiness` | Yes | `not_assessed` | |

### `reproducibility` { #output-fields-ranking-run-manifest-reproducibility }

Whether the run's settings fully record what was run. A reference to an account object that wasn't snapshotted makes it incomplete.

| Field | Required | Value | Description |
|---|---|---|---|
| `status` | Yes | `complete` or `incomplete` | |
| `external_references` | Yes | A list of [objects](#output-fields-ranking-run-manifest-reproducibility-external-references) | |

### Each of `reproducibility.external_references` { #output-fields-ranking-run-manifest-reproducibility-external-references }

A setting that names a mutable object in the provider account.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | Lowercase letters, digits, and `_`, starting with a letter | |
| `snapshotted` | Yes | `true` or `false` | |

### `counts` { #output-fields-ranking-run-manifest-counts }

The run's counts. `quotaRemaining` stays in the attempt record, out of the manifest.

| Field | Required | Value | Description |
|---|---|---|---|
| `results` | Yes | An integer, 0 or more | |
| `cases` | Yes | An integer, 0 or more | |
| `attempts` | Yes | An [object](#output-fields-ranking-run-manifest-counts-attempts) | |
| `provider_requests` | Yes | An integer, 0 or more | The sends of the planned request that may have reached Portfolio123 (JSON summary). |
| `retries` | Yes | An integer, 0 or more | |
| `cost` | Yes | An integer, 0 or more; or `null` | The credits Portfolio123 reported charging; null when it reported none. |

### `counts.attempts` { #output-fields-ranking-run-manifest-counts-attempts }

Attempts, by outcome.

| Field | Required | Value | Description |
|---|---|---|---|
| `succeeded` | Yes | An integer, 0 or more | |
| `failed` | Yes | An integer, 0 or more | |
| `unknown` | Yes | An integer, 0 or more | |
| `running` | Yes | An integer, 0 or more | |

<!-- end generated: output-fields-ranking-run-manifest -->

## A run's `plan.json` 1.2.0, with a ranking definition

The plan of a run whose ranking is a ranking system's definition: [version 1.0.0](#a-runs-planjson)'s fields, with the definition's source, the case's two requests, its `rank_update` and its backtest, and a weight row for each node. [Plans with a ranking definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plans-with-a-ranking-definition), in the specification, gives its rules.

<!-- generated: output-fields-ranking-run-plan -->

Its schema: [`schemas/plan-1.2.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/plan-1.2.0.schema.json).

A screen's plan whose ranking is a definition: its one case's `rank_update` and backtest, with the whole definition, the definition's source, the budget with each operation's cost, the retry policy, and the data sent. Execution requires its `plan_hash` as approval (plans with a ranking definition).

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.2.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `canonicalization_version` | Yes | `1` | |
| `provider_wrapper` | Yes | An [object](#output-fields-ranking-run-plan-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-ranking-run-plan-transport) | |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | |
| `purpose` | Yes | Text, 1 to 2,000 characters, not all whitespace; or `null` | |
| `ranking_source` | Yes | An [object](#output-fields-ranking-run-plan-ranking-source) | |
| `cases` | Yes | A list of exactly one [object](#output-fields-ranking-run-plan-cases) | |
| `budget` | Yes | An [object](#output-fields-ranking-run-plan-budget) | |
| `retry_policy` | Yes | An [object](#output-fields-ranking-run-plan-retry-policy) | |
| `data_sent` | Yes | A list of exactly 3 [objects](#output-fields-ranking-run-plan-data-sent) | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `provider_wrapper` { #output-fields-ranking-run-plan-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-ranking-run-plan-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `ranking_source` { #output-fields-ranking-run-plan-ranking-source }

Where the plan's ranking definition came from, which the plan hash covers and no `case_id` does: a file, by the definition's hash, or a snapshot, by its system's name and the `artifact_id`s of its `snapshot.json` and `definition.xml` (ranking definitions). Each field is always written, null where the form has none.

| Field | Required | Value | Description |
|---|---|---|---|
| `form` | Yes | `definition` or `snapshot` | |
| `definition` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The definition's hash, which the baseline's `ranking` setting holds too. |
| `system` | Yes | Text or `null` | A snapshot's system's name, as its record gives it in `system.name`; null for a file. |
| `snapshot_record` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The `artifact_id` of a snapshot's `snapshot.json`; null for a file. |
| `snapshot_definition` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The `artifact_id` of a snapshot's `definition.xml`; null for a file. |

### Each of `cases` { #output-fields-ranking-run-plan-cases }

The one case of a screen whose ranking is a definition: its `rank_update`, then its backtest, ranked by `ApiRankingSystem`, and its settings, with a weight row for each node.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `requests` | Yes | A list of exactly 2 items, in this order: an [object](#output-fields-ranking-run-plan-cases-requests-0), then an [object](#output-fields-ranking-run-plan-cases-requests-1) | The `rank_update` that writes the case's whole definition, then the backtest. |
| `settings` | Yes | A list of [objects](#output-fields-ranking-run-plan-cases-settings) | |

### `cases[].requests[0]` { #output-fields-ranking-run-plan-cases-requests-0 }

A case's first request: the `rank_update` that writes its definition into `ApiRankingSystem`.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `rank_update` | |
| `params` | Yes | An [object](#output-fields-ranking-run-plan-cases-requests-0-params) | |

### `cases[].requests[0].params` { #output-fields-ranking-run-plan-cases-requests-0-params }

The params passed to p123api's `rank_update`, exactly as they're sent, in this order: the fixed type, the case's whole definition, its ranking method's number, and the fixed currency. There's no `id`, so the call writes `ApiRankingSystem` (sending a definition).

| Field | Required | Value | Description |
|---|---|---|---|
| `type` | Yes | `stock` | |
| `nodes` | Yes | Text, not empty | The case's whole definition, as its file's text reads, each line end a line feed. |
| `rankingMethod` | Yes | `2` or `4` | 2 for `percentile_nas_negative`, and 4 for `percentile_nas_neutral`. |
| `currency` | Yes | `USD` | |

### `cases[].requests[1]` { #output-fields-ranking-run-plan-cases-requests-1 }

One provider request a case needs.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `screen_backtest` | |
| `params` | Yes | An [object](#output-fields-ranking-run-plan-cases-requests-1-params) | |

### `cases[].requests[1].params` { #output-fields-ranking-run-plan-cases-requests-1-params }

The JSON object passed to p123api's `screen_backtest`, exactly as it will be sent. `slippage` is always a JSON float, and every other number an integer (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `screen` | Yes | An [object](#output-fields-ranking-run-plan-cases-requests-1-params-screen) | |
| `startDt` | Yes | A date, `YYYY-MM-DD` | |
| `endDt` | Yes | A date, `YYYY-MM-DD` | |
| `pitMethod` | Yes | `Complete` | |
| `precision` | Yes | `4` | |
| `transPrice` | Yes | `1` | |
| `slippage` | Yes | A number | |
| `rebalFreq` | Yes | `Every Week` or `Every 4 Weeks` | |

### `cases[].requests[1].params.screen` { #output-fields-ranking-run-plan-cases-requests-1-params-screen }

The `screen` object of a screen backtest request.

| Field | Required | Value | Description |
|---|---|---|---|
| `type` | Yes | `stock` | |
| `universe` | Yes | Text, not all whitespace | |
| `maxNumHoldings` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |
| `method` | Yes | `long` | |
| `currency` | Yes | `USD` | |
| `benchmark` | Yes | Text, not all whitespace | |
| `ranking` | Yes | An [object](#output-fields-ranking-run-plan-cases-requests-1-params-screen-ranking); text, not all whitespace; or an integer, from 1 to 9,007,199,254,740,991 | |
| `rules` | Yes | A list of at least one [object](#output-fields-ranking-run-plan-cases-requests-1-params-screen-rules) | |

### `cases[].requests[1].params.screen.ranking` { #output-fields-ranking-run-plan-cases-requests-1-params-screen-ranking }

A single-formula ranking, as sent.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |
| `lowerIsBetter` | Yes | `true` or `false` | |

### Each of `cases[].requests[1].params.screen.rules` { #output-fields-ranking-run-plan-cases-requests-1-params-screen-rules }

One screening rule, as sent. It has no `type` field: Portfolio123 rejects one.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |

### Each of `cases[].settings` { #output-fields-ranking-run-plan-cases-settings }

One resolved setting of a plan with a ranking definition: 1.0.0's row, with `node` after `setting`: a weight row's canonical path, and null on every other row.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | Lowercase letters, digits, and `_`, starting with a letter | |
| `node` | Yes | Text, not empty; or `null` | A weight row's node, by its canonical path; null on every other row. |
| `category` | Yes | `dates`, `benchmark`, `currency`, `costs`, `execution`, `universe`, `data_source`, `strategy`, or `other` | |
| `critical` | Yes | `true` or `false` | |
| `value` | Yes | An integer, from 0 to 9,007,199,254,740,991; text, not all whitespace; a list of items, each text, not all whitespace; or an [object](#output-fields-ranking-run-plan-cases-settings-value) | |
| `unit` | Yes | `count`, `weeks`, or `percent`; or `null` | |
| `interpretation` | Yes | `interpreted` or `not_interpreted` | |
| `expected_provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `inference_rule` | Yes | Text, not all whitespace; or `null` | |
| `flags` | Yes | A list of items, each `inferred_default` or `not_snapshotted` | |

### `cases[].settings[].value` { #output-fields-ranking-run-plan-cases-settings-value }

A ranking given as a definition, in a file or by a snapshot, as a case's resolved `ranking` holds it: the definition's hash and its ranking method, in place of the configuration's keys. So the `case_id` covers the definition, byte for byte, and its ranking method, and nothing about where it came from (ranking definitions).

| Field | Required | Value | Description |
|---|---|---|---|
| `definition` | Yes | `sha256:` and 64 lowercase hexadecimal digits | `sha256:` and the hex SHA-256 of the definition's UTF-8 text. |
| `ranking_method` | Yes | `percentile_nas_negative` or `percentile_nas_neutral` | |

### `budget` { #output-fields-ranking-run-plan-budget }

The budget of a screen whose ranking is a definition: its two requests, the `rank_update` and the backtest, each operation's documented cost, and the most they can cost.

| Field | Required | Value | Description |
|---|---|---|---|
| `provider_requests` | Yes | `2` | The case's `rank_update` and its backtest, each sent at most once. |
| `costs` | Yes | A list of exactly 2 [objects](#output-fields-ranking-run-plan-budget-costs) | `rank_update`'s documented cost, then the backtest's, in place of 1.0.0's `credits_per_request` and its source. |
| `credits` | Yes | An integer, 0 or more | |
| `authentication_calls` | Yes | `1` | |

### Each of `budget.costs` { #output-fields-ranking-run-plan-budget-costs }

One operation's documented cost, in credits, when the plan was made, and its source.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `rank_update` or `screen_backtest` | |
| `credits_per_request` | Yes | An integer, 0 or more | |
| `source` | Yes | An [object](#output-fields-ranking-run-plan-budget-costs-source) | |

### `budget.costs[].source` { #output-fields-ranking-run-plan-budget-costs-source }

Where a documented value comes from, and the date the documentation was checked.

| Field | Required | Value | Description |
|---|---|---|---|
| `title` | Yes | Text, not all whitespace | |
| `url` | Yes | An `https://` address, without spaces | |
| `checked` | Yes | A date, `YYYY-MM-DD` | |

### `retry_policy` { #output-fields-ranking-run-plan-retry-policy }

The retry policy: no automatic retries, and one exchange per wrapper call.

| Field | Required | Value | Description |
|---|---|---|---|
| `automatic_retries` | Yes | `0` | |
| `wrapper_attempts_per_call` | Yes | `1` | |
| `exchanges_per_call` | Yes | `1` | |

### Each of `data_sent` { #output-fields-ranking-run-plan-data-sent }

A category of data that leaves the machine, in a plan with a ranking definition.

| Field | Required | Value | Description |
|---|---|---|---|
| `category` | Yes | `credentials`, `strategy_definition`, or `backtest_settings` | |
| `recipient` | Yes | `Portfolio123` | |
| `via` | Yes | `p123api` | |
| `settings` | Yes | A list of items, each lowercase letters, digits, and `_`, starting with a letter | |

<!-- end generated: output-fields-ranking-run-plan -->

## `started.json` and `updating.json` 1.2.0, of a run with a ranking definition or a snapshot

The start records of a run's attempt that sends a definition: `updating.json`, written just before its `rank_update`, and `started.json`, just before its backtest, in `cases/<case_id>/attempts/<attempt_id>/`. A ranking snapshot's attempt writes `started.json` 1.2.0 too, in `attempts/<attempt_id>/`, just before its `rank_get`. [Sending a definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#sending-a-definition), in the specification, gives their rules.

<!-- generated: output-fields-ranking-run-start-record -->

Its schema: [`schemas/start-record-1.2.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/start-record-1.2.0.schema.json).

A start record 1.2.0: a screen run's attempt that sends a definition, or a snapshot's. It's written durably just before its send: the update record, `updating.json`, before the `rank_update`, and `started.json` before the backtest, or before a snapshot's `rank_get`.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.2.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits; or `null` | The case; null for a snapshot's attempt, which plans no case. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `operation` | Yes | `rank_update`, `screen_backtest`, or `rank_get` | The request it comes before. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `provider_wrapper` | Yes | An [object](#output-fields-ranking-run-start-record-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-ranking-run-start-record-transport) | |
| `exchanges` | Yes | A list of [objects](#output-fields-ranking-run-start-record-exchanges) | Trial Folio's successful authentication, and in `started.json` before a backtest, the `rank_update`'s exchange, `POST /rank` with a 200. |

### `provider_wrapper` { #output-fields-ranking-run-start-record-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-ranking-run-start-record-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### Each of `exchanges` { #output-fields-ranking-run-start-record-exchanges }

One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An HTTP method in capitals, a space, and a path that starts with `/`, without spaces | The method and path, such as `POST /auth` or `POST /screen/backtest`. |
| `result` | Yes | `response`, `not_connected`, or `interrupted` | |
| `status` | Yes | An integer, from 100 to 599; or `null` | The HTTP status of a `response`; null otherwise. |
| `note` | Yes | `completed_from_saved_response` or `null` | Set only on a restarted attempt's request exchange, recorded as a 200 because its response was found saved (uncertain completion); null otherwise. |

<!-- end generated: output-fields-ranking-run-start-record -->

## `attempt.json` 1.2.0, of a run with a ranking definition or a snapshot

The attempt record of a run's attempt that sends a definition, and of a ranking snapshot's attempt, beside its start records. [Sending a definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#sending-a-definition), in the specification, gives its rules.

<!-- generated: output-fields-ranking-run-attempt-record -->

Its schema: [`schemas/attempt-record-1.2.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/attempt-record-1.2.0.schema.json).

An attempt record 1.2.0: a screen run's attempt that sends a definition, or a snapshot's, written once when the attempt ends: its start record's fields, how it ended, and, for a definition, its `rank_update`.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.2.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits; or `null` | The case; null for a snapshot's attempt. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `operation` | Yes | `screen_backtest` or `rank_get` | The attempt's last request: the backtest, or a snapshot's `rank_get`. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `provider_wrapper` | Yes | An [object](#output-fields-ranking-run-attempt-record-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-ranking-run-attempt-record-transport) | |
| `ended_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `outcome` | Yes | `succeeded`, `failed`, or `unknown` | |
| `error` | Yes | An [object](#output-fields-ranking-run-attempt-record-error) or `null` | Null exactly when the outcome is `succeeded`. |
| `exchanges` | Yes | A list of [objects](#output-fields-ranking-run-attempt-record-exchanges) | Every exchange, in order: the authentication's, then `POST /rank`, then `POST /screen/backtest`; or a snapshot's authentication and `GET /rank`. |
| `possibly_charged` | Yes | `true` or `false` | |
| `ranking_update` | Yes | An [object](#output-fields-ranking-run-attempt-record-ranking-update) or `null` | The `rank_update`'s request, response, and provider metadata; null for a snapshot's. |
| `request` | Yes | An [object](#output-fields-ranking-run-attempt-record-ranking-update-request) or `null` | The backtest's, or the `rank_get`'s, redacted request, `request.json`. |
| `response` | Yes | An [object](#output-fields-ranking-run-attempt-record-response) or `null` | |
| `provider_metadata` | Yes | An [object](#output-fields-ranking-run-attempt-record-ranking-update-provider-metadata) | The backtest's, or the `rank_get`'s. |

### `provider_wrapper` { #output-fields-ranking-run-attempt-record-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-ranking-run-attempt-record-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `error` { #output-fields-ranking-run-attempt-record-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `exchanges` { #output-fields-ranking-run-attempt-record-exchanges }

One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An HTTP method in capitals, a space, and a path that starts with `/`, without spaces | The method and path, such as `POST /auth` or `POST /screen/backtest`. |
| `result` | Yes | `response`, `not_connected`, or `interrupted` | |
| `status` | Yes | An integer, from 100 to 599; or `null` | The HTTP status of a `response`; null otherwise. |
| `note` | Yes | `completed_from_saved_response` or `null` | Set only on a restarted attempt's request exchange, recorded as a 200 because its response was found saved (uncertain completion); null otherwise. |

### `ranking_update` { #output-fields-ranking-run-attempt-record-ranking-update }

The `rank_update` an attempt sent before its backtest: its request, its saved response, and what Portfolio123 reported of its charge (sending a definition).

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An [object](#output-fields-ranking-run-attempt-record-ranking-update-request) or `null` | `rank-update-request.json`; null when the attempt ended before writing it. |
| `response` | Yes | An [object](#output-fields-ranking-run-attempt-record-ranking-update-response) or `null` | The saved response; null when none was saved. |
| `provider_metadata` | Yes | An [object](#output-fields-ranking-run-attempt-record-ranking-update-provider-metadata) | The `cost` and `quotaRemaining` of its decoded response, each null when it doesn't carry it. |

### `ranking_update.request` { #output-fields-ranking-run-attempt-record-ranking-update-request }

A file in the output directory, by path and content address.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `ranking_update.response` { #output-fields-ranking-run-attempt-record-ranking-update-response }

The `rank_update`'s saved response: `rank-update-response.json`, the decoded payload, or `rank-update-response.raw`, the body of a 200 the wrapper couldn't decode.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `form` | Yes | `decoded` or `undecoded` | |

### `ranking_update.provider_metadata` { #output-fields-ranking-run-attempt-record-ranking-update-provider-metadata }

What the provider reported about the charge: `cost` and `quotaRemaining`. Each is null when the response doesn't carry it.

| Field | Required | Value | Description |
|---|---|---|---|
| `cost` | Yes | An integer, 0 or more; or `null` | |
| `quota_remaining` | Yes | An integer, 0 or more; or `null` | `quotaRemaining`: account information, kept out of shareable outputs. |

### `response` { #output-fields-ranking-run-attempt-record-response }

The saved response: `response.json`, the decoded payload, or `response.raw`, the body of a 200 the wrapper couldn't decode.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `form` | Yes | `decoded` or `undecoded` | |

<!-- end generated: output-fields-ranking-run-attempt-record -->

## An experiment's `started.json`

The start record of an experiment's attempt, in `cases/<case_id>/attempts/<attempt_id>/`. [Experiment attempts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-attempts), in the specification, gives its rules.

<!-- generated: output-fields-experiment-start-record -->

Its schema: [`schemas/start-record-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/start-record-1.1.0.schema.json).

An experiment's start record, written durably just before the request is sent. Without an attempt record beside it, the attempt is `running` (uncertain completion).

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.1.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `session` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the session that started the attempt. |
| `sequence` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The attempt's place in its session: 1 for the first attempt it starts. It orders a session's attempts, which their start times can't, because the clock can move backward. |
| `authenticated_by` | Yes | A version 4 UUID | The attempt whose successful authentication gave the token the request is sent with: this one, or an earlier one of its session. |
| `repeat_of` | Yes | A version 4 UUID or `null` | The attempt that `--repeat`'s confirmation named, for an attempt it started; null for any other. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `provider_wrapper` | Yes | An [object](#output-fields-experiment-start-record-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-experiment-start-record-transport) | |
| `exchanges` | Yes | A list of at most one [object](#output-fields-experiment-start-record-exchanges) | The exchange completed before the send: Trial Folio's successful authentication call, or none when the session already held a token. |

### `provider_wrapper` { #output-fields-experiment-start-record-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-experiment-start-record-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### Each of `exchanges` { #output-fields-experiment-start-record-exchanges }

One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An HTTP method in capitals, a space, and a path that starts with `/`, without spaces | The method and path, such as `POST /auth` or `POST /screen/backtest`. |
| `result` | Yes | `response`, `not_connected`, or `interrupted` | |
| `status` | Yes | An integer, from 100 to 599; or `null` | The HTTP status of a `response`; null otherwise. |
| `note` | Yes | `completed_from_saved_response` or `null` | Set only on a restarted attempt's request exchange, recorded as a 200 because its response was found saved (uncertain completion); null otherwise. |

<!-- end generated: output-fields-experiment-start-record -->

## An experiment's `attempt.json`

The attempt record of an experiment's attempt, beside its start record. [Experiment attempts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-attempts), in the specification, gives its rules.

<!-- generated: output-fields-experiment-attempt-record -->

Its schema: [`schemas/attempt-record-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/attempt-record-1.1.0.schema.json).

An experiment's attempt record, written once when the attempt ends: everything in its start record, when it has one, plus how the attempt ended.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.1.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `session` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the session that started the attempt. |
| `sequence` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The attempt's place in its session: 1 for the first attempt it starts. It orders a session's attempts, which their start times can't, because the clock can move backward. |
| `authenticated_by` | Yes | A version 4 UUID or `null` | As in the start record, given exactly when the attempt has one. |
| `repeat_of` | Yes | A version 4 UUID or `null` | |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `provider_wrapper` | Yes | An [object](#output-fields-experiment-attempt-record-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-experiment-attempt-record-transport) | |
| `ended_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `outcome` | Yes | `succeeded`, `failed`, or `unknown` | |
| `error` | Yes | An [object](#output-fields-experiment-attempt-record-error) or `null` | Null exactly when the outcome is `succeeded`. |
| `exchanges` | Yes | A list of [objects](#output-fields-experiment-attempt-record-exchanges) | Every exchange of this attempt, in order. It has no authentication exchange when it sent with an earlier attempt's token. |
| `possibly_charged` | Yes | `true` or `false` | |
| `request` | Yes | An [object](#output-fields-experiment-attempt-record-request) or `null` | |
| `response` | Yes | An [object](#output-fields-experiment-attempt-record-response) or `null` | |
| `provider_metadata` | Yes | An [object](#output-fields-experiment-attempt-record-provider-metadata) | |

### `provider_wrapper` { #output-fields-experiment-attempt-record-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-experiment-attempt-record-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `error` { #output-fields-experiment-attempt-record-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `exchanges` { #output-fields-experiment-attempt-record-exchanges }

One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An HTTP method in capitals, a space, and a path that starts with `/`, without spaces | The method and path, such as `POST /auth` or `POST /screen/backtest`. |
| `result` | Yes | `response`, `not_connected`, or `interrupted` | |
| `status` | Yes | An integer, from 100 to 599; or `null` | The HTTP status of a `response`; null otherwise. |
| `note` | Yes | `completed_from_saved_response` or `null` | Set only on a restarted attempt's request exchange, recorded as a 200 because its response was found saved (uncertain completion); null otherwise. |

### `request` { #output-fields-experiment-attempt-record-request }

A file in the output directory, by path and content address.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `response` { #output-fields-experiment-attempt-record-response }

The saved response: `response.json`, the decoded payload, or `response.raw`, the body of a 200 the wrapper couldn't decode.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `form` | Yes | `decoded` or `undecoded` | |

### `provider_metadata` { #output-fields-experiment-attempt-record-provider-metadata }

What the provider reported about the charge: `cost` and `quotaRemaining`. Each is null when the response doesn't carry it.

| Field | Required | Value | Description |
|---|---|---|---|
| `cost` | Yes | An integer, 0 or more; or `null` | |
| `quota_remaining` | Yes | An integer, 0 or more; or `null` | `quotaRemaining`: account information, kept out of shareable outputs. |

<!-- end generated: output-fields-experiment-attempt-record -->

## `authenticating.json`

The authentication record, in the folder of an experiment's attempt that makes Trial Folio's own authentication call. [Experiment attempts](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-attempts), in the specification, gives its rules.

<!-- generated: output-fields-authentication-record -->

Its schema: [`schemas/authentication-record-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/authentication-record-1.0.0.schema.json).

The authentication record, `authenticating.json`, written durably before an experiment's attempt makes Trial Folio's own authentication call, so the budget counts the call even when the process is killed before its exchange is recorded (experiment attempts). An attempt that sends with a token its session already holds has none.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `session` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the session that started the attempt. |
| `sequence` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The attempt's place in its session: 1 for the first attempt it starts. |
| `repeat_of` | Yes | A version 4 UUID or `null` | The attempt that `--repeat`'s confirmation named, for an attempt it started; null for any other. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |

<!-- end generated: output-fields-authentication-record -->

## An experiment's `plans/<n>/plan.json`

The plan of each plan you approved for an experiment. [Experiment plans and revisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-plans-and-revisions), in the specification, gives its rules.

<!-- generated: output-fields-experiment-plan -->

Its schema: [`schemas/plan-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/plan-1.1.0.schema.json).

An experiment's plan: every case, the baseline first, its research context, the budget across runs, and the plan it revises. Execution requires its `plan_hash` as approval.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.1.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `canonicalization_version` | Yes | `1` | |
| `provider_wrapper` | Yes | An [object](#output-fields-experiment-plan-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-experiment-plan-transport) | |
| `experiment_id` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | |
| `purpose` | Yes | Text, 1 to 2,000 characters, not all whitespace | An experiment's purpose is required, so it's never null. |
| `prior_research` | Yes | An [object](#output-fields-experiment-plan-prior-research) | |
| `revises` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The `plan_hash` of the plan this one revises; null for the experiment's first plan. |
| `cases` | Yes | A list of at least 2 [objects](#output-fields-experiment-plan-cases) | Every case, in the order of cases: the baseline first, then the variants of `rules`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`. |
| `budget` | Yes | An [object](#output-fields-experiment-plan-budget) | |
| `retry_policy` | Yes | An [object](#output-fields-experiment-plan-retry-policy) | |
| `data_sent` | Yes | A list of exactly 3 [objects](#output-fields-experiment-plan-data-sent) | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `provider_wrapper` { #output-fields-experiment-plan-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-experiment-plan-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `prior_research` { #output-fields-experiment-plan-prior-research }

The prior-research declaration as the configuration gives it, with `user_supplied` provenance. Trial Folio can't verify it.

| Field | Required | Value | Description |
|---|---|---|---|
| `status` | Yes | `complete`, `partial`, or `unknown` | |
| `description` | Yes | Text, 1 to 5,000 characters, not all whitespace; or `null` | Given with `complete` or `partial`, and optionally with `unknown`; null when it isn't. |

### Each of `cases` { #output-fields-experiment-plan-cases }

One case of an experiment: a 1.0.0 case, with its key, description, and variant. Its `case_id` covers only its settings, so it doesn't change with its key, description, or plan.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `description` | Yes | Text, 1 to 500 characters, not all whitespace; or `null` | The variant's description, with `user_supplied` provenance; null when there's none, and for the baseline. |
| `variant` | Yes | An [object](#output-fields-experiment-plan-cases-variant) or `null` | Null for the baseline. |
| `requests` | Yes | A list of exactly one [object](#output-fields-experiment-plan-cases-requests) | |
| `settings` | Yes | A list of [objects](#output-fields-experiment-plan-cases-settings) | |

### `cases[].variant` { #output-fields-experiment-plan-cases-variant }

A case's variant: the setting it changes, and its change as the configuration gives it: a `value`, in the setting's JSON type, with a decimal as its normalized text; an `add`; or a `replace` and its `with`. Each key is always written, null where it doesn't apply.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | `rules`, `max_holdings`, `rebalance_weeks`, or `slippage_percent` | |
| `value` | Yes | An integer, from 1 to 9,007,199,254,740,991; text, not all whitespace; or `null` | |
| `add` | Yes | Text, not all whitespace; or `null` | |
| `replace` | Yes | Text, not all whitespace; or `null` | |
| `with` | Yes | Text, not all whitespace; or `null` | |
| `default` | Yes | `true` or `false` | True for P-13's default rebalance variant, and false otherwise. |

### Each of `cases[].requests` { #output-fields-experiment-plan-cases-requests }

One provider request a case needs.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `screen_backtest` | |
| `params` | Yes | An [object](#output-fields-experiment-plan-cases-requests-params) | |

### `cases[].requests[].params` { #output-fields-experiment-plan-cases-requests-params }

The JSON object passed to p123api's `screen_backtest`, exactly as it will be sent. `slippage` is always a JSON float, and every other number an integer (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `screen` | Yes | An [object](#output-fields-experiment-plan-cases-requests-params-screen) | |
| `startDt` | Yes | A date, `YYYY-MM-DD` | |
| `endDt` | Yes | A date, `YYYY-MM-DD` | |
| `pitMethod` | Yes | `Complete` | |
| `precision` | Yes | `4` | |
| `transPrice` | Yes | `1` | |
| `slippage` | Yes | A number | |
| `rebalFreq` | Yes | `Every Week` or `Every 4 Weeks` | |

### `cases[].requests[].params.screen` { #output-fields-experiment-plan-cases-requests-params-screen }

The `screen` object of a screen backtest request.

| Field | Required | Value | Description |
|---|---|---|---|
| `type` | Yes | `stock` | |
| `universe` | Yes | Text, not all whitespace | |
| `maxNumHoldings` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |
| `method` | Yes | `long` | |
| `currency` | Yes | `USD` | |
| `benchmark` | Yes | Text, not all whitespace | |
| `ranking` | Yes | An [object](#output-fields-experiment-plan-cases-requests-params-screen-ranking); text, not all whitespace; or an integer, from 1 to 9,007,199,254,740,991 | |
| `rules` | Yes | A list of at least one [object](#output-fields-experiment-plan-cases-requests-params-screen-rules) | |

### `cases[].requests[].params.screen.ranking` { #output-fields-experiment-plan-cases-requests-params-screen-ranking }

A single-formula ranking, as sent.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |
| `lowerIsBetter` | Yes | `true` or `false` | |

### Each of `cases[].requests[].params.screen.rules` { #output-fields-experiment-plan-cases-requests-params-screen-rules }

One screening rule, as sent. It has no `type` field: Portfolio123 rejects one.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |

### Each of `cases[].settings` { #output-fields-experiment-plan-cases-settings }

One resolved setting: a `settings.csv` row without `label`, `original_key`, `original_value`, and `source_artifact`, with `expected_provenance` for `provenance`.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | Lowercase letters, digits, and `_`, starting with a letter | |
| `category` | Yes | `dates`, `benchmark`, `currency`, `costs`, `execution`, `universe`, `data_source`, `strategy`, or `other` | |
| `critical` | Yes | `true` or `false` | |
| `value` | Yes | An integer, from 0 to 9,007,199,254,740,991; text, not all whitespace; a list of items, each text, not all whitespace; or one of these objects: [`cases[].settings[].value` with `formula`](#output-fields-experiment-plan-cases-settings-value-formula), [`cases[].settings[].value` with `name`](#output-fields-experiment-plan-cases-settings-value-name), or [`cases[].settings[].value` with `id`](#output-fields-experiment-plan-cases-settings-value-id) | |
| `unit` | Yes | `count`, `weeks`, or `percent`; or `null` | |
| `interpretation` | Yes | `interpreted` or `not_interpreted` | |
| `expected_provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `inference_rule` | Yes | Text, not all whitespace; or `null` | |
| `flags` | Yes | A list of items, each `inferred_default` or `not_snapshotted` | |

### `cases[].settings[].value` with `formula` { #output-fields-experiment-plan-cases-settings-value-formula }

A ranking by a single formula, the recommended form.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |
| `lower_is_better` | Yes | `true` or `false` | |

### `cases[].settings[].value` with `name` { #output-fields-experiment-plan-cases-settings-value-name }

An existing ranking system in the account, by name. It's recorded as not snapshotted.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | Text, not all whitespace | |

### `cases[].settings[].value` with `id` { #output-fields-experiment-plan-cases-settings-value-id }

An existing ranking system in the account, by ID. It's recorded as not snapshotted.

| Field | Required | Value | Description |
|---|---|---|---|
| `id` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |

### `budget` { #output-fields-experiment-plan-budget }

The experiment's request budget (docs/contracts.md, the budget across runs). It bounds the whole experiment: every attempt of every case, under every plan, in every run.

| Field | Required | Value | Description |
|---|---|---|---|
| `provider_requests` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The configuration's `budget.provider_requests`: at least the number of cases. |
| `credits_per_request` | Yes | An integer, 0 or more | Portfolio123's documented cost of one request when the plan was made. |
| `credits_per_request_source` | Yes | An [object](#output-fields-experiment-plan-budget-credits-per-request-source) | |
| `credits` | Yes | An integer, 0 or more | |
| `authentication_calls` | Yes | An integer, from 1 to 9,007,199,254,740,991 | Equal to `provider_requests`. |

### `budget.credits_per_request_source` { #output-fields-experiment-plan-budget-credits-per-request-source }

Where a documented value comes from, and the date the documentation was checked.

| Field | Required | Value | Description |
|---|---|---|---|
| `title` | Yes | Text, not all whitespace | |
| `url` | Yes | An `https://` address, without spaces | |
| `checked` | Yes | A date, `YYYY-MM-DD` | |

### `retry_policy` { #output-fields-experiment-plan-retry-policy }

The retry policy: no automatic retries, and one exchange per wrapper call.

| Field | Required | Value | Description |
|---|---|---|---|
| `automatic_retries` | Yes | `0` | |
| `wrapper_attempts_per_call` | Yes | `1` | |
| `exchanges_per_call` | Yes | `1` | |

### Each of `data_sent` { #output-fields-experiment-plan-data-sent }

A category of data that leaves the machine, its recipient, and the settings it carries.

| Field | Required | Value | Description |
|---|---|---|---|
| `category` | Yes | `credentials`, `strategy_definition`, or `backtest_settings` | |
| `recipient` | Yes | `Portfolio123` | |
| `via` | Yes | `p123api` | |
| `settings` | Yes | A list of items, each lowercase letters, digits, and `_`, starting with a letter | |

<!-- end generated: output-fields-experiment-plan -->

## `plans/<n>/experiment.json`

The experiment's research record as of each plan. [`experiment.json`](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experimentjson), in the specification, gives its rules.

<!-- generated: output-fields-experiment-record -->

Its schema: [`schemas/experiment-record-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/experiment-record-1.0.0.schema.json).

`experiment.json`: the experiment as its plan declares it, and every plan so far, oldest first, ending with its own. It records no outcome: attempts end after it's written.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `created_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `experiment_id` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | |
| `purpose` | Yes | Text, 1 to 2,000 characters, not all whitespace | |
| `prior_research` | Yes | An [object](#output-fields-experiment-record-prior-research) | As the user declared it. Trial Folio can't verify it. |
| `planned_cases` | Yes | A list of at least 2 [objects](#output-fields-experiment-record-planned-cases) | The plan's cases, in its order, the baseline first. |
| `retired_cases` | Yes | A list of [objects](#output-fields-experiment-record-retired-cases) | |
| `plans` | Yes | A list of at least one [object](#output-fields-experiment-record-plans) | |

### `prior_research` { #output-fields-experiment-record-prior-research }

The prior-research declaration as the configuration gives it, with `user_supplied` provenance. Trial Folio can't verify it.

| Field | Required | Value | Description |
|---|---|---|---|
| `status` | Yes | `complete`, `partial`, or `unknown` | |
| `description` | Yes | Text, 1 to 5,000 characters, not all whitespace; or `null` | Given with `complete` or `partial`, and optionally with `unknown`; null when it isn't. |

### Each of `planned_cases` { #output-fields-experiment-record-planned-cases }

A case as a plan holds it, without its settings and requests, which its `plan.json` holds.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `description` | Yes | Text, 1 to 500 characters, not all whitespace; or `null` | |
| `variant` | Yes | An [object](#output-fields-experiment-record-planned-cases-variant) or `null` | Null for the baseline. |

### `planned_cases[].variant` { #output-fields-experiment-record-planned-cases-variant }

A case's variant: the setting it changes, and its change as the configuration gives it: a `value`, in the setting's JSON type, with a decimal as its normalized text; an `add`; or a `replace` and its `with`. Each key is always written, null where it doesn't apply.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | `rules`, `max_holdings`, `rebalance_weeks`, or `slippage_percent` | |
| `value` | Yes | An integer, from 1 to 9,007,199,254,740,991; text, not all whitespace; or `null` | |
| `add` | Yes | Text, not all whitespace; or `null` | |
| `replace` | Yes | Text, not all whitespace; or `null` | |
| `with` | Yes | Text, not all whitespace; or `null` | |
| `default` | Yes | `true` or `false` | True for P-13's default rebalance variant, and false otherwise. |

### Each of `retired_cases` { #output-fields-experiment-record-retired-cases }

A case an earlier plan included and this one doesn't, as the last plan that included it held it. It and its attempts stay in the record.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `description` | Yes | Text, 1 to 500 characters, not all whitespace; or `null` | |
| `variant` | Yes | An [object](#output-fields-experiment-record-planned-cases-variant) or `null` | Null for the baseline. |
| `plan` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the last plan that included it. |

### Each of `plans` { #output-fields-experiment-record-plans }

One plan of the experiment, in the history of its plans.

| Field | Required | Value | Description |
|---|---|---|---|
| `plan` | Yes | An integer, from 1 to 9,007,199,254,740,991 | Its number: its directory's, `plans/<n>/`. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `revises` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The hash of the plan before it; null for the first plan. |
| `plan_artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The `artifact_id` of its `plan.json`. |
| `configuration_artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The `artifact_id` of its `configuration.yaml`. |
| `approval` | Yes | `interactive`, `option`, or `not_required` | `not_required` for each plan of a synthetic experiment, and for no other plan. |
| `reason` | Yes | Text, 1 to 2,000 characters, not all whitespace; or `null` | The revision's reason, as `--revision-reason` gave it, with `user_supplied` provenance; null for the first plan. |
| `changes` | Yes | An [object](#output-fields-experiment-record-plans-changes) or `null` | What the revision changed from the plan before it; null for the first plan. |

### `plans[].changes` { #output-fields-experiment-record-plans-changes }

What a revision changed from the plan before it. One whose only change is of versions records nothing else: it's a change of versions, not of the configuration.

| Field | Required | Value | Description |
|---|---|---|---|
| `versions` | Yes | A list of [objects](#output-fields-experiment-record-plans-changes-versions) | Each version that changed, with both values, in the order Trial Folio, `p123api`, `requests`, `urllib3`. |
| `cases_added` | Yes | A list of [objects](#output-fields-experiment-record-plans-changes-cases-added) | |
| `cases_retired` | Yes | A list of [objects](#output-fields-experiment-record-plans-changes-cases-added) | |
| `parts` | Yes | A list of items, each `title`, `purpose`, `prior_research`, `budget`, `case_keys`, `case_descriptions`, `case_variants`, or `case_order` | In the documented order: `title`, `purpose`, `prior_research`, `budget`, `case_keys`, `case_descriptions`, `case_variants`, `case_order`. |

### Each of `plans[].changes.versions` { #output-fields-experiment-record-plans-changes-versions }

A version a revision changed: of Trial Folio, or of a package that sends its requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `package` | Yes | `trialfolio`, `p123api`, `requests`, or `urllib3` | |
| `previous` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `current` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### Each of `plans[].changes.cases_added` { #output-fields-experiment-record-plans-changes-cases-added }

A case a revision added or retired, by its `case_id`, and its key: in the revision for an added case, and in the plan before it for a retired one.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |

<!-- end generated: output-fields-experiment-record -->

## `sessions/<s>/session.json`

The record of each run of an experiment's configuration that passed its checks and its approval. [Experiment output](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experiment-output), in the specification, gives its rules.

<!-- generated: output-fields-session-record -->

Its schema: [`schemas/session-record-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/session-record-1.0.0.schema.json).

A session's record: one `run` of the experiment that passed its checks and its approval. Writing it reserves the session's number, which each attempt the session starts records.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `session` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | When it was written. |

<!-- end generated: output-fields-session-record -->

## `sessions/<s>/manifest.json`

The experiment manifest, which a session writes last. [The experiment manifest](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-experiment-manifest), in the specification, gives its rules.

<!-- generated: output-fields-session-manifest -->

Its schema: [`schemas/experiment-manifest-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/experiment-manifest-1.0.0.schema.json).

The manifest a session of an experiment writes last, when it reaches its end.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `artifact_type` | Yes | `experiment` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `created_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `experiment_id` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `session` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the session that wrote it, in whose directory it is. |
| `command` | Yes | An [object](#output-fields-session-manifest-command) or `null` | Null when no `trialfolio` command ran the session, as when the core runs it for another interface, or writes a synthetic experiment. |
| `synthetic` | Yes | `true` or `false` | True exactly for an experiment executed with the demo's client, which sends nothing. Its values, attempts, and counts are invented. |
| `plan` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The current plan's number. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `approval` | Yes | `interactive`, `option`, or `not_required` | How this run approved the current plan: `not_required` exactly for a synthetic experiment. |
| `outcome` | Yes | `completed` or `partial` | `completed` when every planned case succeeded, and `partial` otherwise. |
| `error` | Yes | An [object](#output-fields-session-manifest-error) or `null` | Null when completed, and `execution.partial` when partial. |
| `artifacts` | Yes | A list of [objects](#output-fields-session-manifest-artifacts) | Every file of the experiment's records: each plan's three files, each attempt's files, each case's tables, and this session's record and report. Not `experiment.lock`, `logs/`, other sessions' files, or a plan's directory without `experiment.json`. |
| `parsers` | Yes | A list of at least one [object](#output-fields-session-manifest-parsers) | Each parser version that normalized a case's response, or the installed one's when none did. |
| `license_id` | Yes | `LicenseRef-`, then letters, digits, `.`, and `-` | |
| `notice_version` | Yes | Text, not all whitespace | |
| `capabilities` | Yes | An [object](#output-fields-session-manifest-capabilities) | |
| `reproducibility` | Yes | An [object](#output-fields-session-manifest-reproducibility) | Over the current plan's cases. |
| `counts` | Yes | An [object](#output-fields-session-manifest-counts) | |

### `command` { #output-fields-session-manifest-command }

The command that ran the session, its non-secret options, and when it started.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | `run` | |
| `options` | Yes | An [object](#output-fields-session-manifest-command-options) | |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |

### `command.options` { #output-fields-session-manifest-command-options }

The run's options. Neither the configuration's path nor `--out` is recorded, because a path can name the user. The reason's text is in `experiment.json`, and the repeats are in the attempts' `repeat_of`.

| Field | Required | Value | Description |
|---|---|---|---|
| `approve` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | |
| `json` | Yes | `true` or `false` | |
| `revision_reason` | Yes | `true` or `false` | |
| `repeat` | Yes | `true` or `false` | |

### `error` { #output-fields-session-manifest-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `artifacts` { #output-fields-session-manifest-artifacts }

One file of the experiment's records, by path, content address, and role.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `size` | Yes | An integer, 0 or more | |
| `role` | Yes | `configuration`, `plan`, `experiment_record`, `authentication_record`, `start_record`, `attempt_record`, `provider_request`, `provider_response`, `provider_response_undecoded`, `metrics`, `settings`, `session_record`, or `report` | |
| `schema_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0`; or `null` | The file's schema version, for files that have one. |
| `source` | Yes | An [object](#output-fields-session-manifest-artifacts-source) or `null` | Given exactly for source artifacts. |

### `artifacts[].source` { #output-fields-session-manifest-artifacts-source }

What makes a file a source artifact: when and how it was acquired, and how it's read.

| Field | Required | Value | Description |
|---|---|---|---|
| `acquired_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `format` | Yes | Text, not all whitespace | The source format, such as `screen-configuration` or `p123api-screen-backtest`. |
| `format_version` | Yes | Text, not all whitespace | |
| `parser_version` | Yes | An integer, 1 or more; or `null` | The version of the adapter that interpreted it; null when nothing interpreted it. |
| `provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `operation` | Yes | `screen_backtest` or `null` | The provider operation that produced it; null for a file the user wrote. |

### Each of `parsers` { #output-fields-session-manifest-parsers }

The parser version applied to one provider response layout.

| Field | Required | Value | Description |
|---|---|---|---|
| `layout` | Yes | Text, not all whitespace | |
| `layout_version` | Yes | An integer, 1 or more | |
| `parser_version` | Yes | An integer, 1 or more | |

### `capabilities` { #output-fields-session-manifest-capabilities }

What the run does and doesn't contain.

| Field | Required | Value | Description |
|---|---|---|---|
| `return_series` | Yes | `source_only` or `absent` | `source_only`: the saved response holds per-period series, which are preserved but not normalized, charted, or analyzed. `absent`: no saved response holds any. |
| `statistical_validation` | Yes | `not_assessed` | |
| `trading_readiness` | Yes | `not_assessed` | |

### `reproducibility` { #output-fields-session-manifest-reproducibility }

Whether the run's settings fully record what was run. A reference to an account object that wasn't snapshotted makes it incomplete.

| Field | Required | Value | Description |
|---|---|---|---|
| `status` | Yes | `complete` or `incomplete` | |
| `external_references` | Yes | A list of [objects](#output-fields-session-manifest-reproducibility-external-references) | |

### Each of `reproducibility.external_references` { #output-fields-session-manifest-reproducibility-external-references }

A setting that names a mutable object in the provider account.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | Lowercase letters, digits, and `_`, starting with a letter | |
| `snapshotted` | Yes | `true` or `false` | |

### `counts` { #output-fields-session-manifest-counts }

The experiment's counts, across every run of it.

| Field | Required | Value | Description |
|---|---|---|---|
| `cases` | Yes | An [object](#output-fields-session-manifest-counts-cases) | |
| `retired_cases` | Yes | An integer, 0 or more | How many cases revisions retired. Their attempts are counted with the others. |
| `attempts` | Yes | An [object](#output-fields-session-manifest-counts-attempts) | |
| `retries` | Yes | `0` | Trial Folio never resends a request on its own. |
| `provider_requests` | Yes | An integer, 0 or more | The sends that may have reached Portfolio123, a `running` attempt counted as one, as the budget counts them. A revision may set a budget below them. |
| `authentication_calls` | Yes | An integer, 0 or more | Trial Folio's own authentication calls, whatever their result, as the budget counts them. |
| `budget` | Yes | An [object](#output-fields-session-manifest-counts-budget) | |
| `cost` | Yes | An integer, 0 or more; or `null` | The credits Portfolio123 reported charging; null when it reported none. |

### `counts.cases` { #output-fields-session-manifest-counts-cases }

The current plan's cases, by outcome. They add up to `planned` (R03-AC08).

| Field | Required | Value | Description |
|---|---|---|---|
| `planned` | Yes | An integer, 2 or more | |
| `succeeded` | Yes | An integer, 0 or more | |
| `failed` | Yes | An integer, 0 or more | |
| `skipped` | Yes | An integer, 0 or more | 0.3.0 skips no planned case deliberately, so it's 0. |
| `unknown` | Yes | An integer, 0 or more | |
| `not_yet_run` | Yes | An integer, 0 or more | |

### `counts.attempts` { #output-fields-session-manifest-counts-attempts }

Every attempt of the experiment, retired cases' included, by outcome, and how many of them repeat a case.

| Field | Required | Value | Description |
|---|---|---|---|
| `succeeded` | Yes | An integer, 0 or more | |
| `failed` | Yes | An integer, 0 or more | |
| `unknown` | Yes | An integer, 0 or more | |
| `running` | Yes | An integer, 0 or more | |
| `repeats` | Yes | An integer, 0 or more | The attempts that `--repeat` started: those with a `repeat_of`. |

### `counts.budget` { #output-fields-session-manifest-counts-budget }

The current plan's budget, which bounds the whole experiment.

| Field | Required | Value | Description |
|---|---|---|---|
| `provider_requests` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |
| `authentication_calls` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |

<!-- end generated: output-fields-session-manifest -->

## An experiment's `started.json` and `updating.json` 1.3.0, with a ranking definition

The start records of an experiment's attempt that sends a definition: `updating.json`, written just before its `rank_update`, and `started.json`, just before its backtest, in `cases/<case_id>/attempts/<attempt_id>/`. [Sending a definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#sending-a-definition), in the specification, gives their rules.

<!-- generated: output-fields-ranking-experiment-start-record -->

Its schema: [`schemas/start-record-1.3.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/start-record-1.3.0.schema.json).

A start record 1.3.0: an experiment's attempt that sends a definition. The update record, `updating.json`, comes before its `rank_update`, and `started.json` before its backtest. The two hold the same values in every field but `operation` and `exchanges`.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.3.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `session` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the session that started the attempt. |
| `sequence` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The attempt's place in its session: 1 for the first attempt it starts. |
| `operation` | Yes | `rank_update` or `screen_backtest` | The request it comes before. |
| `authenticated_by` | Yes | A version 4 UUID | The attempt whose successful authentication gave the token the requests are sent with: this one, or an earlier one of its session. |
| `repeat_of` | Yes | A version 4 UUID or `null` | The attempt that `--repeat`'s confirmation named, for an attempt it started; null for any other. |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `provider_wrapper` | Yes | An [object](#output-fields-ranking-experiment-start-record-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-ranking-experiment-start-record-transport) | |
| `exchanges` | Yes | A list of [objects](#output-fields-ranking-experiment-start-record-exchanges) | Trial Folio's successful authentication, or none when the session already held a token; and in `started.json`, the `rank_update`'s exchange, `POST /rank` with a 200. |

### `provider_wrapper` { #output-fields-ranking-experiment-start-record-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-ranking-experiment-start-record-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### Each of `exchanges` { #output-fields-ranking-experiment-start-record-exchanges }

One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An HTTP method in capitals, a space, and a path that starts with `/`, without spaces | The method and path, such as `POST /auth` or `POST /screen/backtest`. |
| `result` | Yes | `response`, `not_connected`, or `interrupted` | |
| `status` | Yes | An integer, from 100 to 599; or `null` | The HTTP status of a `response`; null otherwise. |
| `note` | Yes | `completed_from_saved_response` or `null` | Set only on a restarted attempt's request exchange, recorded as a 200 because its response was found saved (uncertain completion); null otherwise. |

<!-- end generated: output-fields-ranking-experiment-start-record -->

## An experiment's `attempt.json` 1.3.0, with a ranking definition

The attempt record of an experiment's attempt under a plan with a ranking definition, beside its start records. [Sending a definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#sending-a-definition), in the specification, gives its rules.

<!-- generated: output-fields-ranking-experiment-attempt-record -->

Its schema: [`schemas/attempt-record-1.3.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/attempt-record-1.3.0.schema.json).

An attempt record 1.3.0: an experiment's attempt that sends a definition, written once when it ends: 1.1.0's fields, with its `operation` and its `rank_update`.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.3.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `attempt_id` | Yes | A version 4 UUID | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the attempt runs under. |
| `session` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the session that started the attempt. |
| `sequence` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The attempt's place in its session. |
| `operation` | Yes | `screen_backtest` | The attempt's last request, its backtest. |
| `authenticated_by` | Yes | A version 4 UUID or `null` | As in its start records, given exactly when it has one. |
| `repeat_of` | Yes | A version 4 UUID or `null` | |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `provider_wrapper` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-transport) | |
| `ended_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `outcome` | Yes | `succeeded`, `failed`, or `unknown` | |
| `error` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-error) or `null` | Null exactly when the outcome is `succeeded`. |
| `exchanges` | Yes | A list of [objects](#output-fields-ranking-experiment-attempt-record-exchanges) | Every exchange of this attempt, in order. It has no authentication exchange when it sent with an earlier attempt's token. |
| `possibly_charged` | Yes | `true` or `false` | |
| `ranking_update` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-ranking-update) | The `rank_update`'s request, response, and provider metadata. |
| `request` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-ranking-update-request) or `null` | The backtest's redacted request, `request.json`. |
| `response` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-response) or `null` | |
| `provider_metadata` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-ranking-update-provider-metadata) | The backtest's. |

### `provider_wrapper` { #output-fields-ranking-experiment-attempt-record-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-ranking-experiment-attempt-record-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `error` { #output-fields-ranking-experiment-attempt-record-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `exchanges` { #output-fields-ranking-experiment-attempt-record-exchanges }

One HTTP exchange the wrapper made through Trial Folio's transport adapter (HTTP exchanges). Nothing else about it is kept: no headers, tokens, bodies, or exceptions.

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An HTTP method in capitals, a space, and a path that starts with `/`, without spaces | The method and path, such as `POST /auth` or `POST /screen/backtest`. |
| `result` | Yes | `response`, `not_connected`, or `interrupted` | |
| `status` | Yes | An integer, from 100 to 599; or `null` | The HTTP status of a `response`; null otherwise. |
| `note` | Yes | `completed_from_saved_response` or `null` | Set only on a restarted attempt's request exchange, recorded as a 200 because its response was found saved (uncertain completion); null otherwise. |

### `ranking_update` { #output-fields-ranking-experiment-attempt-record-ranking-update }

The `rank_update` an attempt sent before its backtest: its request, its saved response, and what Portfolio123 reported of its charge (sending a definition).

| Field | Required | Value | Description |
|---|---|---|---|
| `request` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-ranking-update-request) or `null` | `rank-update-request.json`; null when the attempt ended before writing it. |
| `response` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-ranking-update-response) or `null` | The saved response; null when none was saved. |
| `provider_metadata` | Yes | An [object](#output-fields-ranking-experiment-attempt-record-ranking-update-provider-metadata) | The `cost` and `quotaRemaining` of its decoded response, each null when it doesn't carry it. |

### `ranking_update.request` { #output-fields-ranking-experiment-attempt-record-ranking-update-request }

A file in the output directory, by path and content address.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `ranking_update.response` { #output-fields-ranking-experiment-attempt-record-ranking-update-response }

The `rank_update`'s saved response: `rank-update-response.json`, the decoded payload, or `rank-update-response.raw`, the body of a 200 the wrapper couldn't decode.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `form` | Yes | `decoded` or `undecoded` | |

### `ranking_update.provider_metadata` { #output-fields-ranking-experiment-attempt-record-ranking-update-provider-metadata }

What the provider reported about the charge: `cost` and `quotaRemaining`. Each is null when the response doesn't carry it.

| Field | Required | Value | Description |
|---|---|---|---|
| `cost` | Yes | An integer, 0 or more; or `null` | |
| `quota_remaining` | Yes | An integer, 0 or more; or `null` | `quotaRemaining`: account information, kept out of shareable outputs. |

### `response` { #output-fields-ranking-experiment-attempt-record-response }

The saved response: `response.json`, the decoded payload, or `response.raw`, the body of a 200 the wrapper couldn't decode.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `form` | Yes | `decoded` or `undecoded` | |

<!-- end generated: output-fields-ranking-experiment-attempt-record -->

## An experiment's `plans/<n>/plan.json` 1.3.0, with a ranking definition

An experiment's plan whose baseline's ranking is a ranking system's definition: [version 1.1.0](#an-experiments-plansnplanjson)'s fields, with the definition's source, each case's two requests, its `rank_update` and its backtest, a weight row for each node, and each ranking variant's change. [Plans with a ranking definition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#plans-with-a-ranking-definition), in the specification, gives its rules.

<!-- generated: output-fields-ranking-experiment-plan -->

Its schema: [`schemas/plan-1.3.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/plan-1.3.0.schema.json).

An experiment's plan whose ranking is a definition: plan 1.1.0's, with each case's `rank_update` and its whole definition, the weight rows, the definition's source, and each operation's cost. Execution requires its `plan_hash` as approval (plans with a ranking definition).

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.3.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `canonicalization_version` | Yes | `1` | |
| `provider_wrapper` | Yes | An [object](#output-fields-ranking-experiment-plan-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-ranking-experiment-plan-transport) | |
| `experiment_id` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | |
| `purpose` | Yes | Text, 1 to 2,000 characters, not all whitespace | An experiment's purpose is required, so it's never null. |
| `prior_research` | Yes | An [object](#output-fields-ranking-experiment-plan-prior-research) | |
| `ranking_source` | Yes | An [object](#output-fields-ranking-experiment-plan-ranking-source) | The baseline's definition's source: every case's definition is the baseline's, or a ranking variant's change of it. |
| `revises` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The `plan_hash` of the plan this one revises; null for the experiment's first plan. |
| `cases` | Yes | A list of at least 2 [objects](#output-fields-ranking-experiment-plan-cases) | Every case, in the order of cases: the baseline first, then the variants of `rules`, `ranking`, `max_holdings`, `rebalance_weeks`, and `slippage_percent`. |
| `budget` | Yes | An [object](#output-fields-ranking-experiment-plan-budget) | |
| `retry_policy` | Yes | An [object](#output-fields-ranking-experiment-plan-retry-policy) | |
| `data_sent` | Yes | A list of exactly 3 [objects](#output-fields-ranking-experiment-plan-data-sent) | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `provider_wrapper` { #output-fields-ranking-experiment-plan-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-ranking-experiment-plan-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `prior_research` { #output-fields-ranking-experiment-plan-prior-research }

The prior-research declaration as the configuration gives it, with `user_supplied` provenance. Trial Folio can't verify it.

| Field | Required | Value | Description |
|---|---|---|---|
| `status` | Yes | `complete`, `partial`, or `unknown` | |
| `description` | Yes | Text, 1 to 5,000 characters, not all whitespace; or `null` | Given with `complete` or `partial`, and optionally with `unknown`; null when it isn't. |

### `ranking_source` { #output-fields-ranking-experiment-plan-ranking-source }

Where the plan's ranking definition came from, which the plan hash covers and no `case_id` does: a file, by the definition's hash, or a snapshot, by its system's name and the `artifact_id`s of its `snapshot.json` and `definition.xml` (ranking definitions). Each field is always written, null where the form has none.

| Field | Required | Value | Description |
|---|---|---|---|
| `form` | Yes | `definition` or `snapshot` | |
| `definition` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The definition's hash, which the baseline's `ranking` setting holds too. |
| `system` | Yes | Text or `null` | A snapshot's system's name, as its record gives it in `system.name`; null for a file. |
| `snapshot_record` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The `artifact_id` of a snapshot's `snapshot.json`; null for a file. |
| `snapshot_definition` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The `artifact_id` of a snapshot's `definition.xml`; null for a file. |

### Each of `cases` { #output-fields-ranking-experiment-plan-cases }

One case of an experiment whose ranking is a definition: a 1.1.0 case, with plan 1.2.0's two requests, and its settings with a weight row for each node.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `description` | Yes | Text, 1 to 500 characters, not all whitespace; or `null` | The variant's description, with `user_supplied` provenance; null when there's none, and for the baseline. |
| `variant` | Yes | An [object](#output-fields-ranking-experiment-plan-cases-variant) or `null` | Null for the baseline. |
| `requests` | Yes | A list of exactly 2 items, in this order: an [object](#output-fields-ranking-experiment-plan-cases-requests-0), then an [object](#output-fields-ranking-experiment-plan-cases-requests-1) | The `rank_update` that writes the case's whole definition, then its backtest. |
| `settings` | Yes | A list of [objects](#output-fields-ranking-experiment-plan-cases-settings) | |

### `cases[].variant` { #output-fields-ranking-experiment-plan-cases-variant }

A case's variant in plan 1.3.0: 1.1.0's, with a ranking variant's change, `set` and `remove`. Each key is always written, null where it doesn't apply.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | `rules`, `ranking`, `max_holdings`, `rebalance_weeks`, or `slippage_percent` | |
| `value` | Yes | An integer, from 1 to 9,007,199,254,740,991; text, not all whitespace; or `null` | |
| `add` | Yes | Text, not all whitespace; or `null` | |
| `replace` | Yes | Text, not all whitespace; or `null` | |
| `with` | Yes | Text, not all whitespace; or `null` | |
| `set` | Yes | A list of at least one [object](#output-fields-ranking-experiment-plan-cases-variant-set) or `null` | A ranking variant's weights, for each entry of the configuration's `set`, each node by its canonical path, in the baseline definition's order; null in a variant of another setting. |
| `remove` | Yes | Text, not empty; or `null` | The canonical path of the factor a ranking variant removes; null when it removes none, and in a variant of another setting. |
| `default` | Yes | `true` or `false` | True for P-13's default rebalance variant, and false otherwise. |

### Each of `cases[].variant.set` { #output-fields-ranking-experiment-plan-cases-variant-set }

One entry of a ranking variant's `set`: a node, by its canonical path in the baseline's definition, and the weight the variant gives it.

| Field | Required | Value | Description |
|---|---|---|---|
| `node` | Yes | Text, not empty | |
| `weight` | Yes | A decimal written as text, in plain notation, without trailing zeros, such as `12.5` | |

### `cases[].requests[0]` { #output-fields-ranking-experiment-plan-cases-requests-0 }

A case's first request: the `rank_update` that writes its definition into `ApiRankingSystem`.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `rank_update` | |
| `params` | Yes | An [object](#output-fields-ranking-experiment-plan-cases-requests-0-params) | |

### `cases[].requests[0].params` { #output-fields-ranking-experiment-plan-cases-requests-0-params }

The params passed to p123api's `rank_update`, exactly as they're sent, in this order: the fixed type, the case's whole definition, its ranking method's number, and the fixed currency. There's no `id`, so the call writes `ApiRankingSystem` (sending a definition).

| Field | Required | Value | Description |
|---|---|---|---|
| `type` | Yes | `stock` | |
| `nodes` | Yes | Text, not empty | The case's whole definition, as its file's text reads, each line end a line feed. |
| `rankingMethod` | Yes | `2` or `4` | 2 for `percentile_nas_negative`, and 4 for `percentile_nas_neutral`. |
| `currency` | Yes | `USD` | |

### `cases[].requests[1]` { #output-fields-ranking-experiment-plan-cases-requests-1 }

One provider request a case needs.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `screen_backtest` | |
| `params` | Yes | An [object](#output-fields-ranking-experiment-plan-cases-requests-1-params) | |

### `cases[].requests[1].params` { #output-fields-ranking-experiment-plan-cases-requests-1-params }

The JSON object passed to p123api's `screen_backtest`, exactly as it will be sent. `slippage` is always a JSON float, and every other number an integer (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `screen` | Yes | An [object](#output-fields-ranking-experiment-plan-cases-requests-1-params-screen) | |
| `startDt` | Yes | A date, `YYYY-MM-DD` | |
| `endDt` | Yes | A date, `YYYY-MM-DD` | |
| `pitMethod` | Yes | `Complete` | |
| `precision` | Yes | `4` | |
| `transPrice` | Yes | `1` | |
| `slippage` | Yes | A number | |
| `rebalFreq` | Yes | `Every Week` or `Every 4 Weeks` | |

### `cases[].requests[1].params.screen` { #output-fields-ranking-experiment-plan-cases-requests-1-params-screen }

The `screen` object of a screen backtest request.

| Field | Required | Value | Description |
|---|---|---|---|
| `type` | Yes | `stock` | |
| `universe` | Yes | Text, not all whitespace | |
| `maxNumHoldings` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |
| `method` | Yes | `long` | |
| `currency` | Yes | `USD` | |
| `benchmark` | Yes | Text, not all whitespace | |
| `ranking` | Yes | An [object](#output-fields-ranking-experiment-plan-cases-requests-1-params-screen-ranking); text, not all whitespace; or an integer, from 1 to 9,007,199,254,740,991 | |
| `rules` | Yes | A list of at least one [object](#output-fields-ranking-experiment-plan-cases-requests-1-params-screen-rules) | |

### `cases[].requests[1].params.screen.ranking` { #output-fields-ranking-experiment-plan-cases-requests-1-params-screen-ranking }

A single-formula ranking, as sent.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |
| `lowerIsBetter` | Yes | `true` or `false` | |

### Each of `cases[].requests[1].params.screen.rules` { #output-fields-ranking-experiment-plan-cases-requests-1-params-screen-rules }

One screening rule, as sent. It has no `type` field: Portfolio123 rejects one.

| Field | Required | Value | Description |
|---|---|---|---|
| `formula` | Yes | Text, not all whitespace | |

### Each of `cases[].settings` { #output-fields-ranking-experiment-plan-cases-settings }

One resolved setting of a plan with a ranking definition: 1.0.0's row, with `node` after `setting`: a weight row's canonical path, and null on every other row.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | Lowercase letters, digits, and `_`, starting with a letter | |
| `node` | Yes | Text, not empty; or `null` | A weight row's node, by its canonical path; null on every other row. |
| `category` | Yes | `dates`, `benchmark`, `currency`, `costs`, `execution`, `universe`, `data_source`, `strategy`, or `other` | |
| `critical` | Yes | `true` or `false` | |
| `value` | Yes | An integer, from 0 to 9,007,199,254,740,991; text, not all whitespace; a list of items, each text, not all whitespace; or an [object](#output-fields-ranking-experiment-plan-cases-settings-value) | |
| `unit` | Yes | `count`, `weeks`, or `percent`; or `null` | |
| `interpretation` | Yes | `interpreted` or `not_interpreted` | |
| `expected_provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `inference_rule` | Yes | Text, not all whitespace; or `null` | |
| `flags` | Yes | A list of items, each `inferred_default` or `not_snapshotted` | |

### `cases[].settings[].value` { #output-fields-ranking-experiment-plan-cases-settings-value }

A ranking given as a definition, in a file or by a snapshot, as a case's resolved `ranking` holds it: the definition's hash and its ranking method, in place of the configuration's keys. So the `case_id` covers the definition, byte for byte, and its ranking method, and nothing about where it came from (ranking definitions).

| Field | Required | Value | Description |
|---|---|---|---|
| `definition` | Yes | `sha256:` and 64 lowercase hexadecimal digits | `sha256:` and the hex SHA-256 of the definition's UTF-8 text. |
| `ranking_method` | Yes | `percentile_nas_negative` or `percentile_nas_neutral` | |

### `budget` { #output-fields-ranking-experiment-plan-budget }

The budget across runs of an experiment whose ranking is a definition: 1.1.0's, with each operation's documented cost in place of the one cost a request had.

| Field | Required | Value | Description |
|---|---|---|---|
| `provider_requests` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The configuration's `budget.provider_requests`. |
| `costs` | Yes | A list of exactly 2 [objects](#output-fields-ranking-experiment-plan-budget-costs) | `rank_update`'s documented cost, then the backtest's. |
| `credits` | Yes | An integer, 0 or more | |
| `authentication_calls` | Yes | An integer, from 1 to 9,007,199,254,740,991 | Equal to `provider_requests`. |

### Each of `budget.costs` { #output-fields-ranking-experiment-plan-budget-costs }

One operation's documented cost, in credits, when the plan was made, and its source.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `rank_update` or `screen_backtest` | |
| `credits_per_request` | Yes | An integer, 0 or more | |
| `source` | Yes | An [object](#output-fields-ranking-experiment-plan-budget-costs-source) | |

### `budget.costs[].source` { #output-fields-ranking-experiment-plan-budget-costs-source }

Where a documented value comes from, and the date the documentation was checked.

| Field | Required | Value | Description |
|---|---|---|---|
| `title` | Yes | Text, not all whitespace | |
| `url` | Yes | An `https://` address, without spaces | |
| `checked` | Yes | A date, `YYYY-MM-DD` | |

### `retry_policy` { #output-fields-ranking-experiment-plan-retry-policy }

The retry policy: no automatic retries, and one exchange per wrapper call.

| Field | Required | Value | Description |
|---|---|---|---|
| `automatic_retries` | Yes | `0` | |
| `wrapper_attempts_per_call` | Yes | `1` | |
| `exchanges_per_call` | Yes | `1` | |

### Each of `data_sent` { #output-fields-ranking-experiment-plan-data-sent }

A category of data that leaves the machine, in a plan with a ranking definition.

| Field | Required | Value | Description |
|---|---|---|---|
| `category` | Yes | `credentials`, `strategy_definition`, or `backtest_settings` | |
| `recipient` | Yes | `Portfolio123` | |
| `via` | Yes | `p123api` | |
| `settings` | Yes | A list of items, each lowercase letters, digits, and `_`, starting with a letter | |

<!-- end generated: output-fields-ranking-experiment-plan -->

## `plans/<n>/experiment.json` 1.1.0, with a ranking definition

The experiment's research record as of each plan, once a plan of the experiment, this one or an earlier one, has a ranking definition. [`experiment.json`](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#experimentjson), in the specification, gives its rules.

<!-- generated: output-fields-ranking-experiment-record -->

Its schema: [`schemas/experiment-record-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/experiment-record-1.1.0.schema.json).

`experiment.json` 1.1.0: the experiment as its plan declares it, and every plan so far, oldest first, ending with its own, once a plan of the experiment is plan 1.3.0. It records no outcome: attempts end after it's written.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.1.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `created_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `experiment_id` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `title` | Yes | Text, 1 to 200 characters, not all whitespace | |
| `purpose` | Yes | Text, 1 to 2,000 characters, not all whitespace | |
| `prior_research` | Yes | An [object](#output-fields-ranking-experiment-record-prior-research) | As the user declared it. Trial Folio can't verify it. |
| `planned_cases` | Yes | A list of at least 2 [objects](#output-fields-ranking-experiment-record-planned-cases) | The plan's cases, in its order, the baseline first. |
| `retired_cases` | Yes | A list of [objects](#output-fields-ranking-experiment-record-retired-cases) | |
| `plans` | Yes | A list of at least one [object](#output-fields-ranking-experiment-record-plans) | |

### `prior_research` { #output-fields-ranking-experiment-record-prior-research }

The prior-research declaration as the configuration gives it, with `user_supplied` provenance. Trial Folio can't verify it.

| Field | Required | Value | Description |
|---|---|---|---|
| `status` | Yes | `complete`, `partial`, or `unknown` | |
| `description` | Yes | Text, 1 to 5,000 characters, not all whitespace; or `null` | Given with `complete` or `partial`, and optionally with `unknown`; null when it isn't. |

### Each of `planned_cases` { #output-fields-ranking-experiment-record-planned-cases }

A case as a plan holds it, in `experiment.json` 1.1.0: its `variant` holds a ranking variant's `set` and `remove`, null in a variant of another setting, and in an entry taken from a 1.0.0 `experiment.json`.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `description` | Yes | Text, 1 to 500 characters, not all whitespace; or `null` | |
| `variant` | Yes | An [object](#output-fields-ranking-experiment-record-planned-cases-variant) or `null` | Null for the baseline. |

### `planned_cases[].variant` { #output-fields-ranking-experiment-record-planned-cases-variant }

A case's variant in plan 1.3.0: 1.1.0's, with a ranking variant's change, `set` and `remove`. Each key is always written, null where it doesn't apply.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | `rules`, `ranking`, `max_holdings`, `rebalance_weeks`, or `slippage_percent` | |
| `value` | Yes | An integer, from 1 to 9,007,199,254,740,991; text, not all whitespace; or `null` | |
| `add` | Yes | Text, not all whitespace; or `null` | |
| `replace` | Yes | Text, not all whitespace; or `null` | |
| `with` | Yes | Text, not all whitespace; or `null` | |
| `set` | Yes | A list of at least one [object](#output-fields-ranking-experiment-record-planned-cases-variant-set) or `null` | A ranking variant's weights, for each entry of the configuration's `set`, each node by its canonical path, in the baseline definition's order; null in a variant of another setting. |
| `remove` | Yes | Text, not empty; or `null` | The canonical path of the factor a ranking variant removes; null when it removes none, and in a variant of another setting. |
| `default` | Yes | `true` or `false` | True for P-13's default rebalance variant, and false otherwise. |

### Each of `planned_cases[].variant.set` { #output-fields-ranking-experiment-record-planned-cases-variant-set }

One entry of a ranking variant's `set`: a node, by its canonical path in the baseline's definition, and the weight the variant gives it.

| Field | Required | Value | Description |
|---|---|---|---|
| `node` | Yes | Text, not empty | |
| `weight` | Yes | A decimal written as text, in plain notation, without trailing zeros, such as `12.5` | |

### Each of `retired_cases` { #output-fields-ranking-experiment-record-retired-cases }

A case an earlier plan included and this one doesn't, as the last plan that included it held it. It and its attempts stay in the record.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `description` | Yes | Text, 1 to 500 characters, not all whitespace; or `null` | |
| `variant` | Yes | An [object](#output-fields-ranking-experiment-record-planned-cases-variant) or `null` | Null for the baseline. |
| `plan` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the last plan that included it. |

### Each of `plans` { #output-fields-ranking-experiment-record-plans }

One plan of the experiment, in the history of its plans, in `experiment.json` 1.1.0.

| Field | Required | Value | Description |
|---|---|---|---|
| `plan` | Yes | An integer, from 1 to 9,007,199,254,740,991 | Its number: its directory's, `plans/<n>/`. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `revises` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The hash of the plan before it; null for the first plan. |
| `plan_artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The `artifact_id` of its `plan.json`. |
| `configuration_artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The `artifact_id` of its `configuration.yaml`. |
| `approval` | Yes | `interactive`, `option`, or `not_required` | `not_required` for each plan of a synthetic experiment, and for no other plan. |
| `reason` | Yes | Text, 1 to 2,000 characters, not all whitespace; or `null` | The revision's reason, as `--revision-reason` gave it, with `user_supplied` provenance; null for the first plan. |
| `changes` | Yes | An [object](#output-fields-ranking-experiment-record-plans-changes) or `null` | What the revision changed from the plan before it; null for the first plan. |

### `plans[].changes` { #output-fields-ranking-experiment-record-plans-changes }

What a revision changed from the plan before it, in `experiment.json` 1.1.0: 1.0.0's, and a change of the definition's source alone.

| Field | Required | Value | Description |
|---|---|---|---|
| `versions` | Yes | A list of [objects](#output-fields-ranking-experiment-record-plans-changes-versions) | Each version that changed, with both values, in the order Trial Folio, `p123api`, `requests`, `urllib3`. |
| `cases_added` | Yes | A list of [objects](#output-fields-ranking-experiment-record-plans-changes-cases-added) | |
| `cases_retired` | Yes | A list of [objects](#output-fields-ranking-experiment-record-plans-changes-cases-added) | |
| `parts` | Yes | A list of items, each `title`, `purpose`, `prior_research`, `budget`, `ranking_source`, `case_keys`, `case_descriptions`, `case_variants`, or `case_order` | In the documented order: `title`, `purpose`, `prior_research`, `budget`, `ranking_source`, `case_keys`, `case_descriptions`, `case_variants`, `case_order`. |

### Each of `plans[].changes.versions` { #output-fields-ranking-experiment-record-plans-changes-versions }

A version a revision changed: of Trial Folio, or of a package that sends its requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `package` | Yes | `trialfolio`, `p123api`, `requests`, or `urllib3` | |
| `previous` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `current` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### Each of `plans[].changes.cases_added` { #output-fields-ranking-experiment-record-plans-changes-cases-added }

A case a revision added or retired, by its `case_id`, and its key: in the revision for an added case, and in the plan before it for a retired one.

| Field | Required | Value | Description |
|---|---|---|---|
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |

<!-- end generated: output-fields-ranking-experiment-record -->

## `sessions/<s>/manifest.json` 1.1.0, with a ranking definition

The experiment manifest of each session, once a plan of the experiment, this one or an earlier one, has a ranking definition. [The experiment manifest](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-experiment-manifest), in the specification, gives its rules.

<!-- generated: output-fields-ranking-session-manifest -->

Its schema: [`schemas/experiment-manifest-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/experiment-manifest-1.1.0.schema.json).

The manifest a session of an experiment with a ranking definition writes last: 1.0.0's, with the files the definition adds. Its counts' `provider_requests` count both kinds of request, and `cost` sums the costs reported for both.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.1.0` | |
| `artifact_type` | Yes | `experiment` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `created_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `experiment_id` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `session` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The number of the session that wrote it, in whose directory it is. |
| `command` | Yes | An [object](#output-fields-ranking-session-manifest-command) or `null` | Null when no `trialfolio` command ran the session, as when the core runs it for another interface, or writes a synthetic experiment. |
| `synthetic` | Yes | `true` or `false` | True exactly for an experiment executed with the demo's client, which sends nothing. Its values, attempts, and counts are invented. |
| `plan` | Yes | An integer, from 1 to 9,007,199,254,740,991 | The current plan's number. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `approval` | Yes | `interactive`, `option`, or `not_required` | How this run approved the current plan: `not_required` exactly for a synthetic experiment. |
| `outcome` | Yes | `completed` or `partial` | `completed` when every planned case succeeded, and `partial` otherwise. |
| `error` | Yes | An [object](#output-fields-ranking-session-manifest-error) or `null` | Null when completed, and `execution.partial` when partial. |
| `artifacts` | Yes | A list of [objects](#output-fields-ranking-session-manifest-artifacts) | Every file of the experiment's records: each plan's files, a definition's copy and a snapshot's record included, each attempt's files, each case's tables, and this session's record and report. |
| `parsers` | Yes | A list of at least one [object](#output-fields-ranking-session-manifest-parsers) | Each parser version that normalized a case's response, or the installed one's when none did. |
| `license_id` | Yes | `LicenseRef-`, then letters, digits, `.`, and `-` | |
| `notice_version` | Yes | Text, not all whitespace | |
| `capabilities` | Yes | An [object](#output-fields-ranking-session-manifest-capabilities) | |
| `reproducibility` | Yes | An [object](#output-fields-ranking-session-manifest-reproducibility) | Over the current plan's cases. |
| `counts` | Yes | An [object](#output-fields-ranking-session-manifest-counts) | |

### `command` { #output-fields-ranking-session-manifest-command }

The command that ran the session, its non-secret options, and when it started.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | `run` | |
| `options` | Yes | An [object](#output-fields-ranking-session-manifest-command-options) | |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |

### `command.options` { #output-fields-ranking-session-manifest-command-options }

The run's options. Neither the configuration's path nor `--out` is recorded, because a path can name the user. The reason's text is in `experiment.json`, and the repeats are in the attempts' `repeat_of`.

| Field | Required | Value | Description |
|---|---|---|---|
| `approve` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | |
| `json` | Yes | `true` or `false` | |
| `revision_reason` | Yes | `true` or `false` | |
| `repeat` | Yes | `true` or `false` | |

### `error` { #output-fields-ranking-session-manifest-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `artifacts` { #output-fields-ranking-session-manifest-artifacts }

One file of the records of an experiment with a ranking definition, by path, content address, and role.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `size` | Yes | An integer, 0 or more | |
| `role` | Yes | `configuration`, `plan`, `experiment_record`, `ranking_definition`, `ranking_snapshot_record`, `authentication_record`, `update_record`, `start_record`, `attempt_record`, `rank_update_request`, `rank_update_response`, `rank_update_response_undecoded`, `provider_request`, `provider_response`, `provider_response_undecoded`, `metrics`, `settings`, `session_record`, or `report` | |
| `schema_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0`; or `null` | The file's schema version, for files that have one. |
| `source` | Yes | An [object](#output-fields-ranking-session-manifest-artifacts-source) or `null` | Given exactly for source artifacts. |

### `artifacts[].source` { #output-fields-ranking-session-manifest-artifacts-source }

A source record in a manifest with a ranking definition: 1.0.0's, whose provider operation may also be the `rank_update` or a snapshot's `rank_get`.

| Field | Required | Value | Description |
|---|---|---|---|
| `acquired_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `format` | Yes | Text, not all whitespace | The source format, such as `ranking-definition` or `p123api-rank-update`. |
| `format_version` | Yes | Text, not all whitespace | |
| `parser_version` | Yes | An integer, 1 or more; or `null` | The version of the adapter that interpreted it; null when nothing interpreted it. |
| `provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `operation` | Yes | `screen_backtest`, `rank_update`, or `rank_get`; or `null` | The provider operation that produced it; null for a file the user wrote. |

### Each of `parsers` { #output-fields-ranking-session-manifest-parsers }

The parser version applied to one provider response layout.

| Field | Required | Value | Description |
|---|---|---|---|
| `layout` | Yes | Text, not all whitespace | |
| `layout_version` | Yes | An integer, 1 or more | |
| `parser_version` | Yes | An integer, 1 or more | |

### `capabilities` { #output-fields-ranking-session-manifest-capabilities }

What the run does and doesn't contain.

| Field | Required | Value | Description |
|---|---|---|---|
| `return_series` | Yes | `source_only` or `absent` | `source_only`: the saved response holds per-period series, which are preserved but not normalized, charted, or analyzed. `absent`: no saved response holds any. |
| `statistical_validation` | Yes | `not_assessed` | |
| `trading_readiness` | Yes | `not_assessed` | |

### `reproducibility` { #output-fields-ranking-session-manifest-reproducibility }

Whether the run's settings fully record what was run. A reference to an account object that wasn't snapshotted makes it incomplete.

| Field | Required | Value | Description |
|---|---|---|---|
| `status` | Yes | `complete` or `incomplete` | |
| `external_references` | Yes | A list of [objects](#output-fields-ranking-session-manifest-reproducibility-external-references) | |

### Each of `reproducibility.external_references` { #output-fields-ranking-session-manifest-reproducibility-external-references }

A setting that names a mutable object in the provider account.

| Field | Required | Value | Description |
|---|---|---|---|
| `setting` | Yes | Lowercase letters, digits, and `_`, starting with a letter | |
| `snapshotted` | Yes | `true` or `false` | |

### `counts` { #output-fields-ranking-session-manifest-counts }

The experiment's counts, across every run of it.

| Field | Required | Value | Description |
|---|---|---|---|
| `cases` | Yes | An [object](#output-fields-ranking-session-manifest-counts-cases) | |
| `retired_cases` | Yes | An integer, 0 or more | How many cases revisions retired. Their attempts are counted with the others. |
| `attempts` | Yes | An [object](#output-fields-ranking-session-manifest-counts-attempts) | |
| `retries` | Yes | `0` | Trial Folio never resends a request on its own. |
| `provider_requests` | Yes | An integer, 0 or more | The sends that may have reached Portfolio123, a `running` attempt counted as one, as the budget counts them. A revision may set a budget below them. |
| `authentication_calls` | Yes | An integer, 0 or more | Trial Folio's own authentication calls, whatever their result, as the budget counts them. |
| `budget` | Yes | An [object](#output-fields-ranking-session-manifest-counts-budget) | |
| `cost` | Yes | An integer, 0 or more; or `null` | The credits Portfolio123 reported charging; null when it reported none. |

### `counts.cases` { #output-fields-ranking-session-manifest-counts-cases }

The current plan's cases, by outcome. They add up to `planned` (R03-AC08).

| Field | Required | Value | Description |
|---|---|---|---|
| `planned` | Yes | An integer, 2 or more | |
| `succeeded` | Yes | An integer, 0 or more | |
| `failed` | Yes | An integer, 0 or more | |
| `skipped` | Yes | An integer, 0 or more | 0.3.0 skips no planned case deliberately, so it's 0. |
| `unknown` | Yes | An integer, 0 or more | |
| `not_yet_run` | Yes | An integer, 0 or more | |

### `counts.attempts` { #output-fields-ranking-session-manifest-counts-attempts }

Every attempt of the experiment, retired cases' included, by outcome, and how many of them repeat a case.

| Field | Required | Value | Description |
|---|---|---|---|
| `succeeded` | Yes | An integer, 0 or more | |
| `failed` | Yes | An integer, 0 or more | |
| `unknown` | Yes | An integer, 0 or more | |
| `running` | Yes | An integer, 0 or more | |
| `repeats` | Yes | An integer, 0 or more | The attempts that `--repeat` started: those with a `repeat_of`. |

### `counts.budget` { #output-fields-ranking-session-manifest-counts-budget }

The current plan's budget, which bounds the whole experiment.

| Field | Required | Value | Description |
|---|---|---|---|
| `provider_requests` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |
| `authentication_calls` | Yes | An integer, from 1 to 9,007,199,254,740,991 | |

<!-- end generated: output-fields-ranking-session-manifest -->

## A ranking snapshot's `plan.json`

A ranking snapshot's plan, in its output directory: its one `rank_get`, and its budget. [Ranking snapshot output](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-snapshot-output), in the specification, gives its rules.

<!-- generated: output-fields-snapshot-plan -->

Its schema: [`schemas/ranking-snapshot-plan-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/ranking-snapshot-plan-1.0.0.schema.json).

A ranking snapshot's plan: the system its configuration names, its one `rank_get`, the budget, the retry policy, and the data sent. It has no title, purpose, or cases. Execution requires its `plan_hash` as approval (ranking snapshot output).

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `canonicalization_version` | Yes | `1` | |
| `provider_wrapper` | Yes | An [object](#output-fields-snapshot-plan-provider-wrapper) | |
| `transport` | Yes | An [object](#output-fields-snapshot-plan-transport) | |
| `system` | Yes | Text, not all whitespace | The configuration's `system`, which is sent. |
| `requests` | Yes | A list of exactly one [object](#output-fields-snapshot-plan-requests) | |
| `budget` | Yes | An [object](#output-fields-snapshot-plan-budget) | One provider request, at 1 credit, `rank_get`'s documented cost, and one authentication call. |
| `retry_policy` | Yes | An [object](#output-fields-snapshot-plan-retry-policy) | |
| `data_sent` | Yes | A list of exactly 2 [objects](#output-fields-snapshot-plan-data-sent) | `credentials`, then `strategy_definition`, which carries `system`. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |

### `provider_wrapper` { #output-fields-snapshot-plan-provider-wrapper }

The installed `p123api`, which sends the requests (plan contents).

| Field | Required | Value | Description |
|---|---|---|---|
| `p123api` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### `transport` { #output-fields-snapshot-plan-transport }

The installed `requests` and `urllib3`, which carry the wrapper's requests.

| Field | Required | Value | Description |
|---|---|---|---|
| `requests` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |
| `urllib3` | Yes | A version: a digit, then letters, digits, `.`, `+`, `!`, `_`, and `-` | |

### Each of `requests` { #output-fields-snapshot-plan-requests }

A snapshot's one request, the `rank_get` that reads the system it names.

| Field | Required | Value | Description |
|---|---|---|---|
| `operation` | Yes | `rank_get` | |
| `params` | Yes | An [object](#output-fields-snapshot-plan-requests-params) | |

### `requests[].params` { #output-fields-snapshot-plan-requests-params }

The params p123api's `rank_get` sends as the query of `GET /rank`: the system's name.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | Text, not all whitespace | |

### `budget` { #output-fields-snapshot-plan-budget }

The request budget (budget and retries).

| Field | Required | Value | Description |
|---|---|---|---|
| `provider_requests` | Yes | `1` | A 1.0.0 plan has one request, sent at most once. |
| `credits_per_request` | Yes | An integer, 0 or more | Portfolio123's documented cost of one request when the plan was made. It isn't fixed, because Portfolio123 can change it. |
| `credits_per_request_source` | Yes | An [object](#output-fields-snapshot-plan-budget-credits-per-request-source) | |
| `credits` | Yes | An integer, 0 or more | |
| `authentication_calls` | Yes | `1` | |

### `budget.credits_per_request_source` { #output-fields-snapshot-plan-budget-credits-per-request-source }

Where a documented value comes from, and the date the documentation was checked.

| Field | Required | Value | Description |
|---|---|---|---|
| `title` | Yes | Text, not all whitespace | |
| `url` | Yes | An `https://` address, without spaces | |
| `checked` | Yes | A date, `YYYY-MM-DD` | |

### `retry_policy` { #output-fields-snapshot-plan-retry-policy }

The retry policy: no automatic retries, and one exchange per wrapper call.

| Field | Required | Value | Description |
|---|---|---|---|
| `automatic_retries` | Yes | `0` | |
| `wrapper_attempts_per_call` | Yes | `1` | |
| `exchanges_per_call` | Yes | `1` | |

### Each of `data_sent` { #output-fields-snapshot-plan-data-sent }

A category of data a snapshot's request sends: the credentials, and the system's name, as `strategy_definition`. It sends no backtest settings.

| Field | Required | Value | Description |
|---|---|---|---|
| `category` | Yes | `credentials`, `strategy_definition`, or `backtest_settings` | |
| `recipient` | Yes | `Portfolio123` | |
| `via` | Yes | `p123api` | |
| `settings` | Yes | A list of items, each `system` | |

<!-- end generated: output-fields-snapshot-plan -->

## A ranking snapshot's `snapshot.json`

The snapshot record, which says where the snapshot's `definition.xml` came from: the system `rank_get` returned, and when. A plan that a snapshot ranks keeps a copy of it beside its `configuration.yaml`. [Ranking snapshot output](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-snapshot-output), in the specification, gives its rules.

<!-- generated: output-fields-snapshot-record -->

Its schema: [`schemas/ranking-snapshot-record-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/ranking-snapshot-record-1.0.0.schema.json).

The snapshot record, `snapshot.json`: the system a snapshot read, when, under which attempt and plan, and its files. It doesn't say whether the definition can be a ranking: that's checked each time a configuration names the snapshot.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `requested` | Yes | Text, not all whitespace | The configuration's `system`. |
| `system` | Yes | An [object](#output-fields-snapshot-record-system) | |
| `taken_at` | Yes | A date and time, with its time zone (RFC 3339) | When the response arrived: the attempt's `ended_at`. |
| `attempt_id` | Yes | A version 4 UUID | |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The plan the snapshot was read under. |
| `definition` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The `artifact_id` of `definition.xml`. |
| `response` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The `artifact_id` of the saved response. |

### `system` { #output-fields-snapshot-record-system }

The ranking system as `rank_get` returned it, exactly as Portfolio123 gave its fields, with `verified` provenance.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | Text | The response's `name`, recorded as it is, even when it isn't the one requested. |
| `id` | Yes | An integer | |
| `ranking_method` | Yes | An integer | The response's `rankingMethod`, as the integer Portfolio123 gave. |
| `currency` | Yes | Text | |
| `type` | Yes | Text | |

<!-- end generated: output-fields-snapshot-record -->

## A ranking snapshot's `manifest.json`

A ranking snapshot's manifest, written last. [Ranking snapshot output](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-snapshot-output), in the specification, gives its rules.

<!-- generated: output-fields-snapshot-manifest -->

Its schema: [`schemas/ranking-snapshot-manifest-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/ranking-snapshot-manifest-1.0.0.schema.json).

The snapshot manifest, `manifest.json` with `artifact_type: ranking-snapshot`, written last: a run's manifest, without capabilities or reproducibility, since a snapshot holds no result or series and has no settings. A synthetic snapshot, which only the core takes, with the demo's client, has no command and the approval `not_required`, and no configuration can name it as its ranking.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `artifact_type` | Yes | `ranking-snapshot` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `created_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `command` | Yes | An [object](#output-fields-snapshot-manifest-command) or `null` | Null for a synthetic snapshot, which no command takes. |
| `synthetic` | Yes | `true` or `false` | True exactly for a snapshot taken with the demo's client, which sends nothing and answers `rank_get` with an invented system. Its system, definition, and attempt are invented. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `approval` | Yes | `interactive`, `option`, or `not_required` | `interactive` or `option`; `not_required` exactly for a synthetic snapshot. |
| `outcome` | Yes | `completed` or `failed` | `completed` once `snapshot.json` is written, and `failed` otherwise. |
| `error` | Yes | An [object](#output-fields-snapshot-manifest-error) or `null` | Null exactly when the outcome is `completed`. |
| `artifacts` | Yes | A list of [objects](#output-fields-snapshot-manifest-artifacts) | Every file but the manifest itself and the logs. |
| `parsers` | Yes | A list of at least one [object](#output-fields-snapshot-manifest-parsers) | `p123api-rank-get`, layout version 1, parser version 1. |
| `license_id` | Yes | `LicenseRef-`, then letters, digits, `.`, and `-` | |
| `notice_version` | Yes | Text, not all whitespace | |
| `counts` | Yes | An [object](#output-fields-snapshot-manifest-counts) | |

### `command` { #output-fields-snapshot-manifest-command }

The command that took the snapshot, its non-secret options, and when it started.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | `run` | |
| `options` | Yes | An [object](#output-fields-snapshot-manifest-command-options) | |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |

### `command.options` { #output-fields-snapshot-manifest-command-options }

The run's options. Neither the configuration's path nor `--out` is recorded, because a path can name the user.

| Field | Required | Value | Description |
|---|---|---|---|
| `approve` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | |
| `json` | Yes | `true` or `false` | |

### `error` { #output-fields-snapshot-manifest-error }

An error, as a stable code and an actionable message (errors).

| Field | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

### Each of `artifacts` { #output-fields-snapshot-manifest-artifacts }

One file of a snapshot, by path, content address, and role.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `size` | Yes | An integer, 0 or more | |
| `role` | Yes | `plan`, `configuration`, `start_record`, `attempt_record`, `provider_request`, `provider_response`, `provider_response_undecoded`, `ranking_definition`, or `ranking_snapshot_record` | |
| `schema_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0`; or `null` | The file's schema version, for files that have one. |
| `source` | Yes | An [object](#output-fields-snapshot-manifest-artifacts-source) or `null` | Given exactly for source artifacts. |

### `artifacts[].source` { #output-fields-snapshot-manifest-artifacts-source }

A source record in a manifest with a ranking definition: 1.0.0's, whose provider operation may also be the `rank_update` or a snapshot's `rank_get`.

| Field | Required | Value | Description |
|---|---|---|---|
| `acquired_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `format` | Yes | Text, not all whitespace | The source format, such as `ranking-definition` or `p123api-rank-update`. |
| `format_version` | Yes | Text, not all whitespace | |
| `parser_version` | Yes | An integer, 1 or more; or `null` | The version of the adapter that interpreted it; null when nothing interpreted it. |
| `provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `operation` | Yes | `screen_backtest`, `rank_update`, or `rank_get`; or `null` | The provider operation that produced it; null for a file the user wrote. |

### Each of `parsers` { #output-fields-snapshot-manifest-parsers }

The parser version applied to one provider response layout.

| Field | Required | Value | Description |
|---|---|---|---|
| `layout` | Yes | Text, not all whitespace | |
| `layout_version` | Yes | An integer, 1 or more | |
| `parser_version` | Yes | An integer, 1 or more | |

### `counts` { #output-fields-snapshot-manifest-counts }

The snapshot's counts.

| Field | Required | Value | Description |
|---|---|---|---|
| `attempts` | Yes | An [object](#output-fields-snapshot-manifest-counts-attempts) | |
| `provider_requests` | Yes | An integer, from 0 to 1 | The `rank_get` sent, when it may have reached Portfolio123. |
| `retries` | Yes | `0` | Trial Folio never resends a request on its own. |
| `cost` | Yes | An integer, 0 or more; or `null` | The credits Portfolio123 reported charging; null when it reported none. |

### `counts.attempts` { #output-fields-snapshot-manifest-counts-attempts }

Attempts, by outcome.

| Field | Required | Value | Description |
|---|---|---|---|
| `succeeded` | Yes | An integer, 0 or more | |
| `failed` | Yes | An integer, 0 or more | |
| `unknown` | Yes | An integer, 0 or more | |
| `running` | Yes | An integer, 0 or more | |

<!-- end generated: output-fields-snapshot-manifest -->

## A review's `manifest.json`

A review's manifest, in its output directory, is written last. [Review output](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#review-output), in the specification, gives its rules.

<!-- generated: output-fields-review-manifest -->

Its schema: [`schemas/review-manifest-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/review-manifest-1.0.0.schema.json).

The manifest of a review written by `trialfolio review`. It has no plan hash, approval, parsers, or reproducibility: each copied run manifest records its own.

| Field | Required | Value | Description |
|---|---|---|---|
| `schema_version` | Yes | `1.0.0` | |
| `artifact_type` | Yes | `review` | |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | |
| `created_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `review_id` | Yes | A version 4 UUID | |
| `command` | Yes | An [object](#output-fields-review-manifest-command) | |
| `synthetic` | Yes | `true` or `false` | True when any result is synthetic. |
| `outcome` | Yes | `completed` | A review writes its manifest only when it completes. |
| `error` | Yes | `null` | |
| `baseline` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `results` | Yes | A list of at least 2 [objects](#output-fields-review-manifest-results) | One entry for each result, in the configuration's order. |
| `artifacts` | Yes | A list of [objects](#output-fields-review-manifest-artifacts) | Each file of the review except its own `manifest.json` and the logs. |
| `methods` | Yes | A list of at least one [object](#output-fields-review-manifest-methods) | |
| `license_id` | Yes | `LicenseRef-`, then letters, digits, `.`, and `-` | |
| `notice_version` | Yes | Text, not all whitespace | |
| `capabilities` | Yes | An [object](#output-fields-review-manifest-capabilities) | |
| `counts` | Yes | An [object](#output-fields-review-manifest-counts) | |

### `command` { #output-fields-review-manifest-command }

The command that wrote the review, its options, and when it started.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | `review` | |
| `options` | Yes | An [object](#output-fields-review-manifest-command-options) | |
| `started_at` | Yes | A date and time, with its time zone (RFC 3339) | |

### `command.options` { #output-fields-review-manifest-command-options }

The review's options, as given. Neither the configuration's path nor `--out` is recorded, because a path can name the user.

| Field | Required | Value | Description |
|---|---|---|---|
| `json` | Yes | `true` or `false` | |

### Each of `results` { #output-fields-review-manifest-results }

Which run one label names. Each entry agrees with the result's copies.

| Field | Required | Value | Description |
|---|---|---|---|
| `label` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `run_manifest` | Yes | `sha256:` and 64 lowercase hexadecimal digits | The `artifact_id` of the run's `manifest.json`, which identifies the run. |
| `synthetic` | Yes | `true` or `false` | As the run's manifest gives it: true for the run `trialfolio demo` writes. |
| `plan_hash` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `normalized_tables` | Yes | `true` or `false` | Whether the run has normalized tables. Without them, its settings are compared from its plan, and its metrics are unavailable. |
| `response` | Yes | `sha256:` and 64 lowercase hexadecimal digits; or `null` | The `artifact_id` of the run's saved response, `response.json` or `response.raw`; null when it has none. Two results with the same one have byte-identical saved responses. |

### Each of `artifacts` { #output-fields-review-manifest-artifacts }

One file of the review, by path, content address, and role.

| Field | Required | Value | Description |
|---|---|---|---|
| `path` | Yes | A relative path: names separated by `/`, without `\` or `:` | |
| `artifact_id` | Yes | `sha256:` and 64 lowercase hexadecimal digits | |
| `size` | Yes | An integer, 0 or more | |
| `role` | Yes | `configuration`, `run_manifest`, `plan`, `metrics`, `settings`, `differences`, or `report` | |
| `schema_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0`; or `null` | The file's schema version. Every file but the report has one: a copy's is the one its run records. |
| `source` | Yes | An [object](#output-fields-review-manifest-artifacts-source) or `null` | Given exactly for `configuration.yaml`, the review's one source artifact. |
| `label` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9`; or `null` | The label of the result a copy was copied from. Null for the review's own files. |

### `artifacts[].source` { #output-fields-review-manifest-artifacts-source }

What makes a file a source artifact: when and how it was acquired, and how it's read.

| Field | Required | Value | Description |
|---|---|---|---|
| `acquired_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `format` | Yes | Text, not all whitespace | The source format, such as `screen-configuration` or `p123api-screen-backtest`. |
| `format_version` | Yes | Text, not all whitespace | |
| `parser_version` | Yes | An integer, 1 or more; or `null` | The version of the adapter that interpreted it; null when nothing interpreted it. |
| `provenance` | Yes | `verified`, `user_supplied`, `inferred`, or `unknown` | |
| `operation` | Yes | `screen_backtest` or `null` | The provider operation that produced it; null for a file the user wrote. |

### Each of `methods` { #output-fields-review-manifest-methods }

An analytical method the review applied, with its version. A 1.0.0 review applies `screen-run-differences`, the rules of docs/contracts.md's differences between screen runs. A change to them that could change a row of `differences.csv` makes a new version.

| Field | Required | Value | Description |
|---|---|---|---|
| `name` | Yes | `screen-run-differences` | |
| `version` | Yes | An integer, 1 or more | |

### `capabilities` { #output-fields-review-manifest-capabilities }

What the review does and doesn't contain. Each copied run manifest says whether its run preserved per-period series.

| Field | Required | Value | Description |
|---|---|---|---|
| `return_series` | Yes | `absent` | |
| `statistical_validation` | Yes | `not_assessed` | |
| `trading_readiness` | Yes | `not_assessed` | |

### `counts` { #output-fields-review-manifest-counts }

The review's counts.

| Field | Required | Value | Description |
|---|---|---|---|
| `results` | Yes | An integer, 0 or more | The results compared, the baseline included. |
| `settings` | Yes | An [object](#output-fields-review-manifest-counts-settings) | |
| `metrics` | Yes | An [object](#output-fields-review-manifest-counts-metrics) | |

### `counts.settings` { #output-fields-review-manifest-counts-settings }

`differences.csv`'s setting rows, by classification, and how many are flagged.

| Field | Required | Value | Description |
|---|---|---|---|
| `same` | Yes | An integer, 0 or more | |
| `intended_change` | Yes | An integer, 0 or more | |
| `unexplained_mismatch` | Yes | An integer, 0 or more | |
| `unknown` | Yes | An integer, 0 or more | |
| `flagged` | Yes | An integer, 0 or more | |

### `counts.metrics` { #output-fields-review-manifest-counts-metrics }

`differences.csv`'s metric rows, by classification, and how many are flagged.

| Field | Required | Value | Description |
|---|---|---|---|
| `differenced` | Yes | An integer, 0 or more | |
| `not_comparable` | Yes | An integer, 0 or more | |
| `unavailable` | Yes | An integer, 0 or more | |
| `flagged` | Yes | An integer, 0 or more | |

<!-- end generated: output-fields-review-manifest -->

## The license acknowledgment's record

`acknowledgment.json`, in the per-user configuration directory, as [the record](cli.md#the-record) says. [License acknowledgment](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#license-acknowledgment), in the specification, gives its rules.

<!-- generated: output-fields-acknowledgment -->

Its schema: [`schemas/license-acknowledgment.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/license-acknowledgment.schema.json).

A user's acknowledgment of one license identifier and one notice version. It holds no identity, account, financial, or family information, and it's never transmitted.

| Field | Required | Value | Description |
|---|---|---|---|
| `license_id` | Yes | `LicenseRef-`, then letters, digits, `.`, and `-` | |
| `notice_version` | Yes | Text, not all whitespace | |
| `acknowledged_at` | Yes | A date and time, with its time zone (RFC 3339) | |
| `method` | Yes | `interactive` or `command` | |

<!-- end generated: output-fields-acknowledgment -->
