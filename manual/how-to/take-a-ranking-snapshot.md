# Take a ranking snapshot

Use this page to rank a screen or an experiment by a ranking system you saved in your Portfolio123 account, with its definition recorded completely. A ranking snapshot reads the system once, with Portfolio123's `rank_get`, and saves its definition, with a record of where it came from: the system's name, its ID, its ranking method, currency, and type, and when it was read. A configuration's `ranking` then names the snapshot, and its plan is built from it offline. It's new in release 0.4.0.

A snapshot only reads the system you name. It writes nothing to your account. A run ranked by the snapshot writes its definition into `ApiRankingSystem`, as a run ranked by a definition's file does ([`ApiRankingSystem` and the ranking lock](../explanation/apirankingsystem-and-the-ranking-lock.md)).

Ranking by the system's name, `ranking: {name: ...}`, ranks by whatever the system holds when the backtest runs, and records it as not snapshotted. A snapshot fixes the definition, and records it.

## Before you start

- **A Portfolio123 subscription with the appropriate access, your credentials, and the license acknowledged,** as for any run ([store your credentials](store-credentials.md)).
- **1 API credit:** the snapshot's one `rank_get`, at Portfolio123's documented cost.
- **The system's name,** exactly as Portfolio123's website shows it.

## Steps

1. Write a [ranking snapshot configuration](../reference/ranking-snapshot-configuration.md) in your workspace, such as `snapshot.yaml`, with your system's name in single quotes:

    ```yaml
    kind: ranking-snapshot
    schema_version: 1.0.0
    system: 'Value and momentum'
    ```

2. Run it into a new directory. Write it under `runs/`, which the workspace's `.gitignore` keeps out of Git, since it holds your system's definition and Portfolio123's response:

    ```sh
    trialfolio run snapshot.yaml --out runs/snapshots/value-momentum/
    ```

    In a terminal, the plan shows the system's name, that the run reads it with one `rank_get` and writes nothing to the account, the request exactly as it will be sent, and the budget: 1 provider request, 1 credit. Type `approve`, or give the plan's hash with `--approve sha256:<the plan hash>`.

3. Read stdout. It names the system read, and says whether its definition, ranking method, currency, and type can be a ranking. For the invented system of this page's example, read from Trial Folio's test server, it reads:

    ```text
    Ranking snapshot taken: runs/snapshots/value-momentum/
    Ranking system read: Value and momentum
    Its definition, ranking method, currency, and type can be a ranking: name the snapshot's directory as ranking.snapshot in a screen's or an experiment's configuration, schema version 1.1.0.
    ```

    When it can't, the message lists each rule it breaks, such as a currency other than USD, or a node of a kind Trial Folio doesn't send. The snapshot is still kept, as a record of what the system held.

4. Name the snapshot's directory in a screen's or an experiment's `ranking`, in a configuration with `schema_version: 1.1.0`, in place of `definition` and `ranking_method`:

    ```yaml
    ranking:
      snapshot: 'runs/snapshots/value-momentum/'
    ```

    The path is read from the configuration file's folder. The snapshot gives the definition and the ranking method, so `ranking_method` isn't allowed beside it.

5. Run that configuration, as in [vary a ranking system's weights](vary-a-ranking-systems-weights.md#step-3-review-the-plan). Its plan is built from the snapshot, offline, without credentials, and gives the definition's source as a ranking snapshot of the system, with when it was read. The run copies the snapshot's `definition.xml` and `snapshot.json` beside each plan's `configuration.yaml`.

## What a snapshot holds

`runs/snapshots/value-momentum/` holds:

- `plan.json`, the snapshot's plan, and `configuration.yaml`, your configuration byte for byte;
- `attempts/<attempt_id>/`, the `rank_get`'s request, Portfolio123's response, and the attempt's start and attempt records;
- `definition.xml`, the system's definition, byte for byte as Portfolio123 returned it;
- `snapshot.json`, the snapshot's record: the name asked for, and the system's name, ID, ranking method, currency, and type, as Portfolio123 returned them, when it was read, and the hashes of `definition.xml` and the response;
- `manifest.json`, written last, and `logs/`.

[Outputs](../reference/outputs.md#a-ranking-snapshots-directory) describes each file, and [output file fields](../reference/output-fields.md#a-ranking-snapshots-snapshotjson) the record's fields.

A snapshot is never resumed or added to. To read the system again, such as after you change it, take a new snapshot, into a directory of its own. A configuration that names the new snapshot plans the definition it holds: in an experiment, a changed definition is a [revision](revise-an-experiment.md).

## The same definition, the same case

A case is identified by its definition's bytes, not by where they came from. So a snapshot and a file that hold the same definition, byte for byte, give the same case, with the same `case_id`, and a review compares their runs as the same ranking. The plans differ only in the definition's source, which the plan hash covers.

Portfolio123 stores a definition as equivalent XML, in its own serialization, so a snapshot of a system that Trial Folio or another program wrote through the API, such as `ApiRankingSystem`, may hold the definition in other bytes than were sent, and give another case ([what Portfolio123 stores](../explanation/apirankingsystem-and-the-ranking-lock.md#what-portfolio123-stores)).

## Check

- The snapshot's run exits 0, and its stdout says whether the snapshot can be a ranking.
- `runs/snapshots/value-momentum/snapshot.json` names the system you asked for.
- In Portfolio123's website, the system you named is unchanged.
- A configuration that names the snapshot shows its plan without credentials, with the snapshot as the definition's source.

These fail, each before anything is sent:

- a snapshot's directory that doesn't exist: `input.not_found`, exit code 3;
- a snapshot that didn't finish, such as one whose `rank_get` failed: `input.not_a_run`, exit code 3, naming the problem;
- a snapshot that can't be a ranking: `config.invalid`, exit code 3, with each rule it breaks;
- a synthetic snapshot, such as the one in Trial Folio's tests, whose system was invented: `config.invalid`, exit code 3;
- running the snapshot's configuration again into the same directory: `output.not_empty`, exit code 4.
