# JSON summary

With `--json`, each command writes its result to stdout as one JSON object, for a script to read. This page lists its keys, what each command gives in them, and the summary's versions.

[The JSON summary](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#json-summary), in the specification, gives its rules. [Using Trial Folio from a script](../how-to/use-from-a-script.md) gives the steps.

## When it's written

- **Add `--json` to any command:** `init`, `run`, `report`, `demo`, `review`, or `license`.
- **stdout then holds exactly one JSON object,** followed by a newline, on success and on failure. Everything else goes to stderr.
- **A usage error** that the command line's parser rejects, exit code 2, writes no summary.

## Keys

| Key | What it holds |
|---|---|
| `schema_version` | The summary's version: `1.2.0` from Trial Folio 0.3.0, as [schema versions](#schema-versions) lists |
| `command` | `init`, `run`, `report`, `demo`, `review`, or `license` |
| `trialfolio_version` | Trial Folio's version |
| `outcome` | `completed`, `partial`, or `failed` |
| `exit_code` | The process's [exit code](errors.md#exit-codes) |
| `ids` | The IDs the command created, such as the plan hash, as [`ids`](#ids) lists. Empty when it created none. |
| `output_dir` | The output directory as given on the command line, or `.` for `trialfolio init` given none. `null` if none was created. |
| `outputs` | The output files, relative to `output_dir`, as [`outputs`](#outputs) lists |
| `cases` | For an experiment only: each case of its plan, as [`cases`](#cases) lists |
| `counts` | The counts, such as `provider_requests` and the credit `cost`, as [`counts`](#counts) lists |
| `statistical_validation`, `trading_readiness` | `not_assessed` |
| `error` | `null`, or the error, with its `code` and its `message` |

- **When `outcome` is `completed`,** `exit_code` is 0 and `error` is `null`.
- **Otherwise,** `exit_code` is the error code's exit code, and `outcome` is `partial` exactly for `execution.partial`.
- **`ids` and `outputs` leave out a key** that has no value, rather than writing `null`.

## `ids`

| Command | `ids` |
|---|---|
| `run` with a screen configuration, and `demo` | `plan_hash` and `case_id`, once the plan is built, even if it isn't approved; and `attempt_id`, once the attempt has a record |
| `run` with an experiment configuration | `experiment_id`; `plan_hash`, the hash of the plan the command built, even if it isn't approved; and `session`, the session's number; once each is known |
| `review` | `review_id`, once the review has claimed its output directory |
| `init`, `report`, and `license` | None |

## `outputs`

Each key is a file's role, and its value the file's path relative to `output_dir`:

| Key | File |
|---|---|
| `configuration` | The starter configuration `trialfolio init` writes, `screen.yaml` |
| `manifest` | The manifest. For an experiment, the session's. |
| `report` | The report. For an experiment, the session's. |
| `metrics` | `normalized/metrics.csv` |
| `settings` | `normalized/settings.csv` |
| `differences` | A review's `normalized/differences.csv` |

An experiment's summary gives only the session's `manifest` and `report`: each case has its own tables, which the manifest lists.

## `counts`

| Command | `counts` |
|---|---|
| `run` with a screen configuration, and `demo` | `attempts`; `provider_requests`, the sends of the request that may have reached Portfolio123, never the authentication call; `metrics_unavailable`; `warnings`; and `cost`, the credits Portfolio123 reported, or `null` when it reported none |
| `review` | `results`; `settings_flagged`, the flagged setting rows; `metrics_unavailable`, the unavailable metric rows; and `warnings` |
| `run` with an experiment configuration | The experiment's counts, across every run of it: the cases by outcome, `cases_planned`, `cases_succeeded`, `cases_failed`, `cases_skipped`, `cases_unknown`, and `cases_not_yet_run`; the retired cases, `cases_retired`; the attempts and the repeats, `attempts` and `repeats`; the provider requests and authentication calls, `provider_requests` and `authentication_calls`; the `cost`; the unavailable metric rows, `metrics_unavailable`; and this command's `warnings` |
| `init`, `report`, and `license` | `{}` |

An experiment's `counts` is `{}` until its counts are known, as after `experiment.locked`.

## `cases`

For an experiment only, once its plan is built, `cases` lists each case of the plan, in its order. It's left out for every other command and configuration.

| Key | What it holds |
|---|---|
| `case_key` | The case's key |
| `case_id` | The case's `case_id` |
| `outcome` | `succeeded`, `failed`, `unknown`, or `not_yet_run` |
| `repeat_attempt_id` | The attempt ID that `--repeat <case-key>:<attempt-id>` names to repeat a case awaiting a repeat, or `null` for any other case |

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
