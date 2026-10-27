"""The executor: executing an approved experiment plan, in the core (docs/contracts.md, running
an experiment, experiment output, the lock, the budget across runs, repeating a case, and
progress and cancellation).

`ExperimentExecution.run` executes a new experiment into an output directory that's absent or
empty:

1. It claims the directory with `experiment.lock`, and takes the experiment lock on it
   (`output.not_empty`, `experiment.locked`). The store holds the lock until its owner closes
   it, so no other process can run the experiment meanwhile.
2. It writes `sessions/1/session.json`, which reserves the session. That's the first atomic
   write, so a file system that can't take one fails here, before any request
   (`storage.write_failed`).
3. It writes `plans/1/configuration.yaml`, `plan.json`, and then `experiment.json`. Nothing is
   sent under a plan before its `experiment.json` is written.
4. It runs the cases in the plan's order, one attempt each, with one client, so the session
   authenticates once, and again only after a 401 or 403 drops its token. Before each attempt,
   it checks the cancellation, and that the budget covers one more request, and one more
   authentication call when the attempt authenticates. A case the budget can't cover isn't
   started, and neither is any case after it. So it is after Trial Folio's own authentication
   call fails, whatever its result, or after a request gets `provider.quota_exceeded`, since
   every later case would end the same way (D-32), and after a cancellation.
5. It writes each succeeded case's tables, `cases/<case_id>/normalized/metrics.csv` and
   `settings.csv`, right after its attempt record. A response that fails validation leaves the
   case `failed`, with `provider.response_invalid`, awaiting a repeat, and the session goes on.
6. It writes the session's report, `sessions/1/report.html`, and then its manifest,
   `sessions/1/manifest.json`, last.

Given the experiment's records, which `open_experiment` read and checked while taking the lock,
it resumes the experiment in the same directory instead (R03-T09):

1. It writes the new session's `sessions/<s>/session.json`, numbered after every session in the
   directory.
2. It writes the attempt record of each attempt a stopped run left without one: `succeeded` for
   a start record with a saved response, `unknown` for one without, and `failed` for an attempt
   with only its authentication record. Then it writes each complete case's tables that a stopped
   run didn't, from the response's bytes the check read. For a revision, it writes
   `plans/<n>/`, as for the first plan, with the reason in its `experiment.json`.
3. It runs the cases that are due, and each case a confirmed repeat names, in the plan's order,
   as a new experiment runs its cases, with the budget counting every attempt of the experiment.
   A complete case, and one awaiting a repeat that no repeat names, are skipped.
4. It writes the session's report and manifest, which list every file of the experiment's
   records and count every attempt.

A case that fails is recorded, and the session goes on to the next one. An interrupt or a storage
failure ends the session at once, without its manifest, so the experiment's output reads as
incomplete until a later run resumes it. So does an attempt whose attempt record wasn't written,
such as after an unexpected exception while writing it, as for a run: a manifest couldn't account
for it. Every attempt written so far stays, and is never replaced. `trialfolio.manifests` holds
what a session shares here with a run and a review: writing the manifest and discarding it, the
endings without one, and the parts of the manifest that a run and an experiment record alike.

From 0.4.0, a new experiment whose plan is 1.3.0, whose ranking is a definition, takes the same
steps, with these differences (sending a definition, running an experiment):

- Before step 1, it takes the ranking lock, on the file its caller gives, and holds it until the
  execution ends, after the session's manifest (`experiment.locked`, `storage.write_failed`).
- Step 3 also writes `plans/1/definition.xml`, right after `configuration.yaml`, from the
  definition's bytes the configuration was validated with, and `experiment.json` 1.1.0. For a
  baseline named by a snapshot, it's the snapshot's `definition.xml`, and the snapshot's
  record, `snapshot.json`, follows it, each from the bytes read and checked when the
  configuration was validated (reading a snapshot).
- Step 4's attempts (`RankingExperimentAttempt`) each send the case's `rank_update`, then, once
  at least 10 seconds have passed since its 200, its backtest, with start and attempt records
  1.3.0 (D-45). An attempt starts only when the budget covers both its requests.
- Step 5 flags a stale backtest: a case's response equal, apart from `cost` and `quotaRemaining`,
  to the session's previous backtest of the same request after a different definition, as
  `stale_backtests.py` gives the rule, unless the experiment is synthetic. Its response fails
  validation, so the case is `failed`, with `provider.response_invalid`, without tables, and
  awaits a repeat (D-45).
- Step 5 writes `settings.csv` 1.1.0, with a weight row for each node, and step 6 experiment
  manifest 1.1.0, with the roles and source records of the files a definition adds.

It resumes and revises such an experiment the same way (release 0.4.0's R04-T09), given its
records, which `open_experiment` read with `ranking`:

- It takes the ranking lock, on the file its caller gives, only when its session sends: when a
  case is due or confirmed to repeat, and the budget covers the first one's two requests. It
  takes it before its session record, and holds it until the execution ends. A resume that sends
  nothing doesn't take it.
- Step 2 writes the attempt record of each attempt whose latest record is its update record, as
  sending a definition says, and a case's `settings.csv` 1.1.0, from the configuration and the
  `definition.xml` of the plan its attempt ran under. A revision into a plan 1.3.0 writes its
  `plans/<n>/definition.xml`, right after its `configuration.yaml`, and, for a snapshot, its
  `snapshot.json` after it.
- The budget counts each attempt's requests, two for an attempt that sends a definition, under
  every plan, and an attempt starts only when both its requests fit; a repeat sends both again.
- Each session of an experiment any of whose plans is 1.3.0 writes experiment manifest 1.1.0,
  which lists each file of an earlier plan, or of an attempt under one, with the version it has,
  and a file the latest manifest lists as it lists it.

Execution with the demo's client, which sends nothing, writes a synthetic experiment: its plan
and manifest record the approval `not_required`, and its report says its values are invented.
It resumes and revises only a synthetic experiment, and nothing else does.

Nothing here prompts, prints, reads the environment, or reads secrets: the caller passes the
approved hash, the confirmed repeats, and the client, which holds any credentials. Progress goes
to the caller's callback, as events that name each case by its `case_id` and hold no text from
the configuration, and the caller may cancel from any thread. Logs name the plan by its hash and
each case by its `case_id`, never by its key.

The package's modules, each importing only those before it: `progress`, the progress events and the
cancellation; `context`, what the writer, the case runner, the manifest's builder, and the executor
read, and the fields of its logs; `ledger`, what the experiment's records hold so far, which the
budget, the counts, the report, the manifest, and the ending messages read; `completion`, the
attempt records step 8 writes; `records`, the writer of the session's records; `authorization`, the
checks of the approval and the repeats; `cases`, the case runner; `manifest`, the builder of the
session's manifest and of its report's evidence; `ending`, the messages that end a session; and
`execution`, `ExperimentExecution`, which takes the steps in their order. The modules that log,
`records`, `cases`, and `execution`, log as `trialfolio.experiment_execution`, so each event keeps
its `component`. A confirmed repeat, `Repeat`, and the core's check of the repeats are in
`trialfolio.experiment_repeats`, which the CLI's approval imports without the executor.
"""

from trialfolio.experiment_execution.cases import StopReason
from trialfolio.experiment_execution.execution import ExperimentExecution
from trialfolio.experiment_execution.manifest import RANKING_SCHEMA_VERSION
from trialfolio.experiment_execution.progress import (
    AttemptEnded,
    AttemptStarted,
    Cancellation,
    Progress,
    ProgressEvent,
    SessionEnded,
    SessionStarted,
)
from trialfolio.experiment_execution.records import DEFINITION_FILE, SCHEMA_VERSION, SNAPSHOT_FILE
from trialfolio.experiment_repeats import Repeat
from trialfolio.storage import LOCK_LINE, LOCK_PATH

__all__ = [
    "DEFINITION_FILE",
    "LOCK_LINE",
    "LOCK_PATH",
    "RANKING_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "SNAPSHOT_FILE",
    "AttemptEnded",
    "AttemptStarted",
    "Cancellation",
    "ExperimentExecution",
    "Progress",
    "ProgressEvent",
    "Repeat",
    "SessionEnded",
    "SessionStarted",
    "StopReason",
]
