# Ranking snapshot configuration

A ranking snapshot configuration is a YAML file that names a ranking system saved in your Portfolio123 account, for `trialfolio run` to read into a ranking snapshot: a copy of the system's definition, with a record of where it came from. A screen's or an experiment's `ranking` can then name the snapshot. This page lists its keys, and what `trialfolio run` does with it. It's new in release 0.4.0.

[The ranking snapshot configuration](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#ranking-snapshot-configuration), in the specification, gives its rules. [Take a ranking snapshot](../how-to/take-a-ranking-snapshot.md) gives the steps, and [outputs](outputs.md#a-ranking-snapshots-directory) what a snapshot's directory holds.

## Example

```yaml
kind: ranking-snapshot
schema_version: 1.0.0
system: 'Value and momentum'      # the system's name, as the website shows it
```

The name is invented. Name one of your own ranking systems.

## Keys

The Key, Required, and Value columns are generated from the configuration's schema, [`schemas/ranking-snapshot-configuration-1.0.0.schema.json`](https://github.com/promptedportfolio/trialfolio/blob/main/schemas/ranking-snapshot-configuration-1.0.0.schema.json), and What it's for is written here.

<!-- generated: ranking-snapshot-configuration -->

| Key | Required | Value | What it's for |
|---|---|---|---|
| `kind` | Yes | `ranking-snapshot` | Marks the file as a ranking snapshot configuration |
| `schema_version` | Yes | `1.0.0` | The version of the configuration's format |
| `system` | Yes | Text, not all whitespace. The name of a ranking system saved in the account, as the website shows it, sent as `rank_get`'s `name`. An ID isn't offered. | The ranking system's name, [in quotes](#quoting), exactly as the website shows it, such as `'Value and momentum'` |

<!-- end generated: ranking-snapshot-configuration -->

**Sent to Portfolio123:** `system`, as the `name` of `rank_get`, which reads the system. Trial Folio never sends `kind` or `schema_version`.

- **By name only.** `rank_get` also takes an ID, but the website shows the name, so the configuration names the system by it.
- **Nothing else.** The file has no title or purpose: the snapshot records what Portfolio123 returns, and the configuration that names the snapshot declares the research.
- **How values are written.** The rules every configuration follows hold for it, as [how values are written](screen-configuration.md#how-values-are-written) gives them.

## Quoting

`system` is text Portfolio123 receives, so it goes in single quotes, as a screen configuration's [rules and names](screen-configuration.md#quoting-the-text-portfolio123-receives) do. Without quotes, YAML would read `system: Core Combo #2` as `Core Combo`, the name of another system, or none. A name without quotes fails with `config.invalid`, and the message says to write it in single quotes.

## What `trialfolio run` does with it

`trialfolio run snapshot.yaml --out <dir>` plans, shows the plan, and waits for your approval, as for a screen ([plans and approval](../explanation/plans-and-approval.md)):

- **The plan** holds one request, `rank_get`, with the system's name: 1 provider request, 1 credit at Portfolio123's documented cost, and one authentication call. It says that the run reads the system saved in your account, and writes nothing to it.
- **Once you approve it,** Trial Folio reads the system, and writes the snapshot into `--out`, a new or empty directory: its plan, a copy of this file, the attempt, `definition.xml`, the system's definition as Portfolio123 returned it, and `snapshot.json`, its record, then `manifest.json`. On success, stdout names the system read, and says whether its definition, ranking method, currency, and type can be a ranking.
- **It writes nothing to your account,** and takes no [ranking lock](../explanation/apirankingsystem-and-the-ranking-lock.md#the-ranking-lock).
- **A snapshot is never resumed or added to.** A later snapshot of the same system goes into a directory of its own, and running the command again into the same directory fails with `output.not_empty`.

## What's rejected

- A misspelled key, a missing `system`, a `system` without quotes, or a `schema_version` other than `1.0.0` fails with `config.invalid`, exit code 3, before anything is sent. The message names each key, and never its value.
- `--revision-reason` or `--repeat` fails with `plan.approval_required`, exit code 2: a snapshot has no plan to revise, and no case to repeat.
- A failed `rank_get` follows a screen run's failures, with the same error codes, and the snapshot has no `definition.xml` or `snapshot.json` ([errors](errors.md)).
