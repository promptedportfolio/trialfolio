# JSON summary

With `--json`, each command writes its result to stdout as one JSON object, for a script to read. This page lists its keys, what each command gives in them, and the summary's versions.

[The JSON summary](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#json-summary), in the specification, gives its rules. [Using Trial Folio from a script](../how-to/use-from-a-script.md) gives the steps.

## When it's written

- **Add `--json` to any command:** `init`, `run`, `report`, `demo`, `review`, or `license`.
- **stdout then holds exactly one JSON object,** followed by a newline, on success and on failure. Everything else goes to stderr.
- **A usage error** that the command line's parser rejects, exit code 2, writes no summary.

## Keys

The keys of the summary and of the objects in it are generated from its schema, [`schemas/json-summary-1.2.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/json-summary-1.2.0.schema.json), with the schema's descriptions.

<!-- generated: json-summary -->

| Key | Required | Value | Description | What it holds |
|---|---|---|---|---|
| `schema_version` | Yes | `1.2.0` | | The summary's version: `1.2.0` from Trial Folio 0.3.0, as [schema versions](#schema-versions) lists |
| `command` | Yes | `init`, `run`, `report`, `demo`, `license`, or `review` | | The command that wrote it |
| `trialfolio_version` | Yes | A version: three whole numbers, separated by `.`, such as `1.0.0` | | Trial Folio's version |
| `outcome` | Yes | `completed`, `partial`, or `failed` | | How the command ended |
| `exit_code` | Yes | `0`, `1`, `2`, `3`, `4`, `5`, `6`, or `130` | | The process's [exit code](errors.md#exit-codes) |
| `ids` | Yes | An [object](#json-summary-ids) | | The IDs the command created, such as the plan hash, as [`ids`](#json-summary-ids) lists. Empty when it created none. |
| `output_dir` | Yes | Text, not all whitespace; or `null` | The output directory as given on the command line, `.` for `trialfolio init` without one; null if none was created. For an experiment, given once the command writes into it: from a new experiment's claim, or from a resume's session record. | The output directory |
| `outputs` | Yes | An [object](#json-summary-outputs) | | The output files, relative to `output_dir`, as [`outputs`](#json-summary-outputs) lists |
| `cases` | No | A list of at least 2 [objects](#json-summary-cases) | For an experiment only, once its plan is built: each case of the plan this run builds, in its order, the baseline and at least one variant. Left out for every other command and configuration. | For an experiment only: each case of its plan, as [`cases`](#json-summary-cases) lists |
| `counts` | Yes | One of these objects: [`counts` with `attempts`](#json-summary-counts-attempts), [`counts` with `results`](#json-summary-counts-results), or [`counts` with `cases_planned`](#json-summary-counts-cases-planned); or an empty object, `{}` | `{}` for `init`, `report`, and `license`, and for an experiment until its counts are known. | The counts, such as `provider_requests` and the credit `cost`, as [`counts`](#counts) lists |
| `statistical_validation` | Yes | `not_assessed` | | Whether the results' statistical validity was assessed: `not_assessed` |
| `trading_readiness` | Yes | `not_assessed` | | Whether the strategy's readiness to trade was assessed: `not_assessed` |
| `error` | Yes | An [object](#json-summary-error) or `null` | | The error, with its `code` and its `message`, or `null` |

<!-- end generated: json-summary -->

- **When `outcome` is `completed`,** `exit_code` is 0 and `error` is `null`.
- **Otherwise,** `exit_code` is the error code's exit code, and `outcome` is `partial` exactly for `execution.partial`.
- **`ids` and `outputs` leave out a key** that has no value, rather than writing `null`.

<!-- generated: json-summary-ids -->

## `ids` { #json-summary-ids }

The identifiers the command created, in version 1.2.0: 1.1.0's, and an experiment's. A key is left out until its identifier exists. An experiment's `cases` give its cases' and attempts' IDs, so its `ids` hold no `case_id` or `attempt_id`.

| Key | Required | Value | Description |
|---|---|---|---|
| `plan_hash` | No | `sha256:` and 64 lowercase hexadecimal digits | |
| `case_id` | No | `case-` and 16 lowercase hexadecimal digits | |
| `attempt_id` | No | A version 4 UUID | |
| `review_id` | No | A version 4 UUID | |
| `experiment_id` | No | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `session` | No | An integer, from 1 to 9,007,199,254,740,991 | |

<!-- end generated: json-summary-ids -->

**Which command gives which:**

| Command | `ids` |
|---|---|
| `run` with a screen configuration, and `demo` | `plan_hash` and `case_id`, once the plan is built, even if it isn't approved; and `attempt_id`, once the attempt has a record |
| `run` with an experiment configuration | `experiment_id`; `plan_hash`, the hash of the plan the command built, even if it isn't approved; and `session`, the session's number; once each is known |
| `review` | `review_id`, once the review has claimed its output directory |
| `init`, `report`, and `license` | None |

<!-- generated: json-summary-outputs -->

## `outputs` { #json-summary-outputs }

The output files, relative to `output_dir`, by role. A key is left out for a file the command didn't write.

| Key | Required | Value | Description |
|---|---|---|---|
| `configuration` | No | A relative path: names separated by `/`, without `\` or `:` | |
| `manifest` | No | A relative path: names separated by `/`, without `\` or `:` | |
| `report` | No | A relative path: names separated by `/`, without `\` or `:` | |
| `metrics` | No | A relative path: names separated by `/`, without `\` or `:` | |
| `settings` | No | A relative path: names separated by `/`, without `\` or `:` | |
| `differences` | No | A relative path: names separated by `/`, without `\` or `:` | |

<!-- end generated: json-summary-outputs -->

**The files:** `configuration` is the starter configuration `trialfolio init` writes, `screen.yaml`. `manifest` and `report` are the manifest and the report, an experiment's session's for an experiment. `metrics` and `settings` are `normalized/metrics.csv` and `normalized/settings.csv`, and `differences` is a review's `normalized/differences.csv`.

An experiment's summary gives only the session's `manifest` and `report`: each case has its own tables, which the manifest lists.

## `counts`

`counts` takes one of three forms, or is `{}`:

| Command | `counts` |
|---|---|
| `run` with a screen configuration, and `demo` | `attempts`; `provider_requests`, the sends of the request that may have reached Portfolio123, never the authentication call; `metrics_unavailable`; `warnings`; and `cost`, the credits Portfolio123 reported, or `null` when it reported none |
| `review` | `results`; `settings_flagged`, the flagged setting rows; `metrics_unavailable`, the unavailable metric rows; and `warnings` |
| `run` with an experiment configuration | The experiment's counts, across every run of it: the cases by outcome, `cases_planned`, `cases_succeeded`, `cases_failed`, `cases_skipped`, `cases_unknown`, and `cases_not_yet_run`; the retired cases, `cases_retired`; the attempts and the repeats, `attempts` and `repeats`; the provider requests and authentication calls, `provider_requests` and `authentication_calls`; the `cost`; the unavailable metric rows, `metrics_unavailable`; and this command's `warnings` |
| `init`, `report`, and `license` | `{}` |

An experiment's `counts` is `{}` until its counts are known, as after `experiment.locked`.

<!-- generated: json-summary-counts-attempts -->

## `counts` with `attempts` { #json-summary-counts-attempts }

The counts of `run` and `demo`.

| Key | Required | Value | Description |
|---|---|---|---|
| `attempts` | Yes | An integer, 0 or more | |
| `provider_requests` | Yes | An integer, 0 or more | The sends of the planned request that may have reached Portfolio123, never authentication. |
| `metrics_unavailable` | Yes | An integer, 0 or more | |
| `warnings` | Yes | An integer, 0 or more | |
| `cost` | Yes | An integer, 0 or more; or `null` | The credits Portfolio123 reported charging; null when it reported none. |

<!-- end generated: json-summary-counts-attempts -->

<!-- generated: json-summary-counts-results -->

## `counts` with `results` { #json-summary-counts-results }

The counts of `review`. They're 0, or the number of results a valid configuration names, until `differences.csv` is written.

| Key | Required | Value | Description |
|---|---|---|---|
| `results` | Yes | An integer, 0 or more | The results compared, the baseline included. |
| `settings_flagged` | Yes | An integer, 0 or more | `differences.csv`'s flagged setting rows. |
| `metrics_unavailable` | Yes | An integer, 0 or more | `differences.csv`'s `unavailable` metric rows. |
| `warnings` | Yes | An integer, 0 or more | |

<!-- end generated: json-summary-counts-results -->

<!-- generated: json-summary-counts-cases-planned -->

## `counts` with `cases_planned` { #json-summary-counts-cases-planned }

An experiment's counts, as its manifest counts them, across every run of it; and the `unavailable` rows of the planned cases' tables, and the warnings this command logged.

| Key | Required | Value | Description |
|---|---|---|---|
| `cases_planned` | Yes | An integer, 2 or more | |
| `cases_succeeded` | Yes | An integer, 0 or more | |
| `cases_failed` | Yes | An integer, 0 or more | |
| `cases_skipped` | Yes | An integer, 0 or more | |
| `cases_unknown` | Yes | An integer, 0 or more | |
| `cases_not_yet_run` | Yes | An integer, 0 or more | |
| `cases_retired` | Yes | An integer, 0 or more | |
| `attempts` | Yes | An integer, 0 or more | |
| `repeats` | Yes | An integer, 0 or more | |
| `provider_requests` | Yes | An integer, 0 or more | The sends that may have reached Portfolio123, a `running` attempt counted as one, never authentication. |
| `authentication_calls` | Yes | An integer, 0 or more | Trial Folio's own authentication calls, whatever their result. |
| `cost` | Yes | An integer, 0 or more; or `null` | The credits Portfolio123 reported charging; null when it reported none. |
| `metrics_unavailable` | Yes | An integer, 0 or more | |
| `warnings` | Yes | An integer, 0 or more | |

<!-- end generated: json-summary-counts-cases-planned -->

<!-- generated: json-summary-cases -->

## Each of `cases` { #json-summary-cases }

One case of the experiment's plan, as the experiment manifest counts it.

| Key | Required | Value | Description |
|---|---|---|---|
| `case_key` | Yes | Lowercase letters, digits, `-`, and `_`, starting with a letter or a digit, at most 64 characters, not a name Windows reserves: `con`, `prn`, `aux`, `nul`, `com1` to `com9`, or `lpt1` to `lpt9` | |
| `case_id` | Yes | `case-` and 16 lowercase hexadecimal digits | |
| `outcome` | Yes | `succeeded`, `failed`, `unknown`, or `not_yet_run` | |
| `repeat_attempt_id` | Yes | A version 4 UUID or `null` | For a case awaiting a repeat, the `attempt_id` that `--repeat <case-key>:<attempt-id>` names to confirm it; null for any other case. |

<!-- end generated: json-summary-cases -->

<!-- generated: json-summary-error -->

## `error` { #json-summary-error }

An error, as a stable code and an actionable message (errors).

| Key | Required | Value | Description |
|---|---|---|---|
| `code` | Yes | `config.invalid`, `input.not_found`, `input.not_a_run`, `artifact.unknown_schema_version`, `environment.unsupported`, `license.not_acknowledged`, `plan.approval_required`, `plan.changed`, `output.not_empty`, `storage.write_failed`, `experiment.locked`, `provider.auth_failed`, `provider.unavailable`, `provider.quota_exceeded`, `provider.unsupported_capability`, `provider.request_rejected`, `provider.response_invalid`, `provider.outcome_unknown`, `execution.partial`, `command.interrupted`, or `internal.unexpected` | |
| `message` | Yes | Text, not all whitespace | |

<!-- end generated: json-summary-error -->

## What a script can read

- **A plan run without approval,** with `--json`, prints one object with `"exit_code": 2`, the plan hash in `ids`, and the error.
- **An experiment's plan run without approval** also lists every case in `cases`. In a new experiment, each is `not_yet_run`.
- **After a run of an experiment that leaves a case awaiting a repeat,** `--json` gives that case's `repeat_attempt_id`, the one in the message's `--repeat` option.

!!! warning "Approve only a plan you've reviewed"
    A script can read the hash from a run that wasn't approved, in `ids.plan_hash`, and approve it, but that skips the review the plan exists for. The same goes for a repeat: a script can read each case's `repeat_attempt_id` and repeat it, but each repeat may be charged again.

## Example

`trialfolio demo --out demo/ --json` prints this object, with `"outcome": "completed"`. Its values are invented, and nothing was sent.

Synthetic example output from `trialfolio demo`, shown over several lines; the command prints it on one:

```json
{
  "schema_version": "1.2.0",
  "command": "demo",
  "trialfolio_version": "0.3.0",
  "outcome": "completed",
  "exit_code": 0,
  "ids": {
    "plan_hash": "sha256:c10831d21f098224d7ddcc68c25cc818585839cde0dfe8ac4890cbfd6d41ec93",
    "case_id": "case-e29404ddebf86363",
    "attempt_id": "e31caaee-0ceb-48c1-8975-31794c74cfcc"
  },
  "output_dir": "demo/",
  "outputs": {
    "manifest": "manifest.json",
    "report": "report.html",
    "metrics": "normalized/metrics.csv",
    "settings": "normalized/settings.csv"
  },
  "counts": {
    "attempts": 1,
    "provider_requests": 1,
    "metrics_unavailable": 0,
    "warnings": 0,
    "cost": null
  },
  "statistical_validation": "not_assessed",
  "trading_readiness": "not_assessed",
  "error": null
}
```

## Schema versions

Each version only adds to the one before, and each key keeps its meaning.

| Version | Written by | Schema |
|---|---|---|
| 1.2.0 | Trial Folio 0.3.0, for every command | [`schemas/json-summary-1.2.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/json-summary-1.2.0.schema.json) |
| 1.1.0 | Trial Folio 0.2.0 and 0.2.1 | [`schemas/json-summary-1.1.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/json-summary-1.1.0.schema.json) |
| 1.0.0 | Trial Folio 0.1.0 | [`schemas/json-summary-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/json-summary-1.0.0.schema.json) |
