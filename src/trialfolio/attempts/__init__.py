"""Attempt recording: the start record, the exchange record, and the attempt record
(docs/contracts.md, execution outcomes and attempts, uncertain completion, endings that decide the
error code, and interrupts).

An `Attempt` is one execution of a plan's case. The command creates it once it has claimed the
output directory, and it ends once. `Attempt.run` carries out steps 8 and 9 of `trialfolio run`
(docs/contracts.md, approval), writing each file into `cases/<case_id>/attempts/<attempt_id>/`:

1. It authenticates with Trial Folio's own call.
2. It writes the redacted request, `request.json`: the request's `params`, which hold no
   credentials. That comes before the start record, so the start record is the last write before
   the send, and an attempt restarted with a saved response has a request to reference.
3. It writes the start record, `started.json`, durably, with the directories that hold it. From
   here on, without an attempt record, the attempt reads as `running`.
4. It sends the request, at most once.
5. It saves the response: `response.json`, or `response.raw` for a 200 the wrapper couldn't decode.
6. It writes the attempt record, `attempt.json`, whatever ended the attempt.

`Attempt.end_before_authenticating` ends an attempt that stopped before step 1, for example after
an interrupt just after the claim, with an attempt record only. Neither method raises for an
ending it records: a provider failure, a storage failure, a user interrupt, or an unexpected
exception. Each returns an `AttemptResult`, whose `error` is the one the command reports. Only a
second interrupt, while the attempt record is written once more after a first, gets through.

An `ExperimentAttempt` is one attempt of an experiment's case, with start and attempt records
1.1.0 (docs/contracts.md, experiment attempts). The attempts of a session share one client, so
one that sends with the token an earlier attempt obtained skips step 1, and one that
authenticates first writes its authentication record, `authenticating.json`, durably before the
call. Its records name its session, its place in it, the attempt whose authentication gave its
token, and the attempt a repeat repeats. Both kinds of attempt write their files, and end, the
same way.

From 0.4.0, a case whose ranking is a definition sends two requests in each attempt (sending a
definition): `RankingAttempt`, a screen run's, with start and attempt records 1.2.0, and
`RankingExperimentAttempt`, an experiment's, with records 1.3.0. After authenticating, each writes
the `rank_update`'s request, `rank-update-request.json`, and its start record, the update record
`updating.json`, sends the `rank_update`, and saves its response, `rank-update-response.json`, or
`.raw` for a 200 the wrapper couldn't decode. Only after a 200 the wrapper decoded, and saved, does
it write the backtest's `request.json` and `started.json`, and send the backtest, as 0.3.0's
attempts do. Any other ending of the `rank_update` ends the attempt there, so no backtest ranks by
whatever `ApiRankingSystem` held before. The backtest's exchange gives the outcome; without one,
the `rank_update`'s does, and the attempt is possibly charged when either may have reached
Portfolio123.

A `SnapshotAttempt` is a ranking snapshot's one attempt (ranking snapshot output), in
`attempts/<attempt_id>/`, since a snapshot plans no case. It takes an `Attempt`'s steps with its
one request, the `rank_get` that reads the ranking system its configuration names, and writes
start and attempt records 1.2.0, with `operation` `rank_get`, no case, and no `ranking_update`.

No file is written twice, and none is replaced. The outcome follows the request's exchange and
whether the response was saved. An interrupt or a storage failure decides only the error code.
A file before the attempt record that the store published before its write failed, whatever the
failure, is among the attempt's files all the same, so a manifest written later lists every file
the attempt wrote. The attempt record references a request or a response only when its write
completed. An attempt record the store published before an interrupt or a storage failure counts
as written, so the attempt reads as the record says.

The package's modules, each importing only those before it:

- `files`: the names and roles of an attempt's files, its directory, and `AttemptFiles`, the file
  writer, which writes each file once and lists every file the attempt wrote.
- `reading`: how a saved attempt reads, `running` included, and what its records count: its
  provider requests, its authentication calls, and the cost Portfolio123 reported.
- `endings`: the ending policy, `AttemptEnding`, which classifies an attempt from its exchanges,
  decides the command's error, writes the attempt record whatever ended the attempt, and logs how
  it ended; and what an attempt's messages say of its requests.
- `kinds`: the attempt classes, each kind of attempt from `_AttemptBase`, which every kind
  shares, with their results.

The modules that log, `endings` and `kinds`, log as `trialfolio.attempts` (docs/refactoring.md,
decision 11). Every name the rest of Trial Folio uses is imported from `trialfolio.attempts`, as
before it was a package.
"""

from trialfolio.attempts.endings import (
    BACKTEST_REQUEST_NAME,
    RANK_GET_REQUEST_NAME,
    Outcome,
    prevailing,
    ranking_detail,
    record_detail,
    request_detail,
)
from trialfolio.attempts.files import (
    ATTEMPT_RECORD,
    AUTHENTICATION_RECORD,
    RANK_UPDATE_REQUEST_FILE,
    RANK_UPDATE_RESPONSE_FILE,
    RANK_UPDATE_RESPONSE_RAW,
    START_RECORD,
    UPDATE_RECORD,
    AttemptFile,
    AttemptRole,
    attempt_directory,
    provider_metadata,
    snapshot_attempt_directory,
)
from trialfolio.attempts.kinds import (
    AUTHENTICATION_SCHEMA_VERSION,
    EXPERIMENT_SCHEMA_VERSION,
    RANKING_EXPERIMENT_SCHEMA_VERSION,
    RANKING_SCHEMA_VERSION,
    SCHEMA_VERSION,
    Attempt,
    AttemptResult,
    Clock,
    ExperimentAttempt,
    ExperimentAttemptResult,
    RankingAttempt,
    RankingExperimentAttempt,
    RankingOperation,
    SnapshotAttempt,
    utc_now,
)
from trialfolio.attempts.reading import (
    AnyAttemptRecord,
    AttemptStatus,
    attempt_status,
    authentication_calls,
    check_records,
    provider_requests,
    read_attempt,
    reported_cost,
)

__all__ = [
    "ATTEMPT_RECORD",
    "AUTHENTICATION_RECORD",
    "AUTHENTICATION_SCHEMA_VERSION",
    "BACKTEST_REQUEST_NAME",
    "EXPERIMENT_SCHEMA_VERSION",
    "RANKING_EXPERIMENT_SCHEMA_VERSION",
    "RANKING_SCHEMA_VERSION",
    "RANK_GET_REQUEST_NAME",
    "RANK_UPDATE_REQUEST_FILE",
    "RANK_UPDATE_RESPONSE_FILE",
    "RANK_UPDATE_RESPONSE_RAW",
    "SCHEMA_VERSION",
    "START_RECORD",
    "UPDATE_RECORD",
    "AnyAttemptRecord",
    "Attempt",
    "AttemptFile",
    "AttemptResult",
    "AttemptRole",
    "AttemptStatus",
    "Clock",
    "ExperimentAttempt",
    "ExperimentAttemptResult",
    "Outcome",
    "RankingAttempt",
    "RankingExperimentAttempt",
    "RankingOperation",
    "SnapshotAttempt",
    "attempt_directory",
    "attempt_status",
    "authentication_calls",
    "check_records",
    "prevailing",
    "provider_metadata",
    "provider_requests",
    "ranking_detail",
    "read_attempt",
    "record_detail",
    "reported_cost",
    "request_detail",
    "snapshot_attempt_directory",
    "utc_now",
]
