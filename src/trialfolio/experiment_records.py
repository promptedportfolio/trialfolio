"""An experiment's records, read back and checked, as a resume reads them before it builds its
plan (docs/contracts.md, running an experiment: a resumed experiment, checking the records, and
the cases that are due; experiment output; experiment attempts; an experiment's normalized
tables; and the experiment manifest).

`open_experiment` takes the experiment lock on a store's output directory, which holds
`experiment.lock`, and `read_experiment` reads every record of the experiment through the store,
each file once, and checks them:

- **The plans.** Each `plans/<n>/` that holds an `experiment.json`: the file is valid; its last
  entry is its directory's plan, by its number, its hash, and the `artifact_id`s of its
  `plan.json` and `configuration.yaml`; its earlier entries are the previous plan's; its plan
  recomputes to its hash, and revises the previous plan; and it records the experiment and the
  planned cases as its plan declares them. A plan's directory without `experiment.json` is a
  revision whose approval was never recorded, and isn't a plan. Without `plans/1/experiment.json`,
  the experiment's first run stopped before anything was sent, and there's nothing to resume.
- **The latest manifest,** the highest-numbered session's that has one: it's valid, and each file
  it lists has the size and `artifact_id` it records, so a record missing from an incomplete copy
  fails the check, instead of leaving its case looking due. It's the experiment's, names one of
  its plans, and is `synthetic` exactly when the plans record the approval `not_required`.
- **The attempts,** in `cases/<case_id>/attempts/<attempt_id>/`: their records are valid, and
  agree with each other and with their directory; they name a plan of the experiment, a case of
  that plan, and a session; no two attempts of a session have one `sequence`; each file an
  attempt record references has the `artifact_id` it records; each request was sent with a token
  an attempt of its session obtained, which no 401 or 403 had dropped since; and an attempt that
  follows a possibly charged attempt of its case names the latest one in `repeat_of`, and no
  other attempt names one.
- **The tables,** in `cases/<case_id>/normalized/`: only a case with a succeeded attempt has
  them, and `settings.csv` never alone; each reads back as a valid table, labeled with the case's
  `case_id`, and drawn from that attempt's saved response and the configuration of the plan it
  ran under; and a `metrics.csv` the latest manifest doesn't list is exactly what the installed
  parser writes from that response.

An attempt with a start record and no attempt record is `running`, and one whose only record is
its authentication record stopped before its send. `SavedExperimentAttempt` reads each as the
resume's step 8 will record it: the first `succeeded` with a saved response and `unknown` without
one, possibly charged either way, and the second `failed`, not possibly charged, and
`completed_record` gives the attempt record step 8 writes. The case states, and the budget's
counts, read them the same way, by the rules in `case_state.py`, which the executor shares.

The check also prepares the tables a stopped run didn't write: for each case with a succeeded
attempt and no `settings.csv`, the rows its `metrics.csv` will hold, from the response's bytes the
check read, or that the response fails validation, and the original values from its plan's
configuration. So the resume writes them without reading anything again.

From 0.4.0, read with `ranking`, it also reads an experiment with a ranking definition (release
0.4.0's R04-T09): plans 1.3.0, `experiment.json` 1.1.0, experiment manifests 1.1.0, start and
attempt records 1.3.0 with their update records, `settings.csv` 1.1.0, and configurations
1.1.0, each the version its plan, or the experiment's plans so far, give. Each plan 1.3.0 holds
`definition.xml`, which, read as a definition's file is read, has the hash its `ranking_source`
gives; its configuration reads with it. Each attempt under a plan 1.3.0 writes its records 1.3.0,
its update record before `started.json`, whose exchanges are the update record's, then the
`rank_update`'s 200, and the `rank_update`'s files beside them; its attempt record holds its start
records' contents, and references the `rank_update`'s files with the `artifact_id`s they have; and
a 401 or 403 to a `rank_update` drops the token, as one to a backtest does. A case's weight rows
are its plan's, drawn from the plan's `definition.xml`, or, for a weight its ranking variant
changes, its configuration. An attempt whose latest record is its update record stopped during
its `rank_update`, or after it and before its backtest was sent: it reads as step 8 records it,
`failed` with the `rank_update`'s response saved, and `unknown` without it, possibly charged
either way, with one provider request (sending a definition). A snapshot's records are release
0.4.0's R04-T10's, so a plan whose ranking is a snapshot is refused until then. Without
`ranking`, as `trialfolio run` reads the records until release 0.4.0's R04-T12, it reads 0.3.0's
versions only.

Nothing here writes, sends, or logs. A refusal is `input.not_a_run`, or
`artifact.unknown_schema_version` for a record whose schema version has no reader, and its
message names the problem and the file, by its path in the output directory, which holds no
configuration value, never a value. The checks it shares with a run's reader, `runs.py`, are in
`record_checks.py`, and the paths of the output directory in `experiment_paths.py`.
"""

import json
import re
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Final, Literal, cast, overload

from pydantic import BaseModel

from trialfolio.attempts import (
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
    provider_requests,
    ranking_detail,
    request_detail,
)
from trialfolio.case_state import (
    CaseOutcome,
    CaseState,
    case_outcome,
    case_state,
    counted_authentications,
    counted_requests,
    experiment_counts,
    latest_charged,
    unavailable_metrics,
)
from trialfolio.configuration import (
    ExperimentConfigurationRead,
    experiment_original_values,
    experiment_original_values_v1_1,
    experiment_schema_version,
    read_experiment_configuration,
    read_experiment_configuration_v1_1,
)
from trialfolio.contracts.attempt import (
    ArtifactReference,
    AttemptRecordV1_1,
    AttemptRecordV1_3,
    AuthenticationRecord,
    Exchange,
    ProviderMetadata,
    RankingUpdate,
    RankUpdateResponse,
    SavedResponse,
    StartRecordV1_1,
    StartRecordV1_3,
)
from trialfolio.contracts.common import (
    AUTHENTICATION_REQUEST,
    RANK_UPDATE_REQUEST,
    SCREEN_BACKTEST_REQUEST,
    ErrorDetail,
)
from trialfolio.contracts.experiment_manifest import (
    ExperimentArtifact,
    ExperimentArtifactRoleV1_1,
    ExperimentArtifactV1_1,
    ExperimentManifest,
    ExperimentManifestCounts,
    ExperimentManifestV1_1,
)
from trialfolio.contracts.experiment_plan import (
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanV1_1,
    PlanV1_3,
    PlanVariantV1_3,
)
from trialfolio.contracts.experiment_record import (
    ExperimentRecord,
    ExperimentRecordV1_1,
    PlanEntryV1_1,
    RecordedCase,
    RecordedCaseV1_1,
    SessionRecord,
)
from trialfolio.contracts.tables import (
    TABLES_SCHEMA_VERSION,
    TABLES_SCHEMA_VERSION_V1_1,
    MetricsRow,
    SettingsRow,
    SettingsRowV1_1,
)
from trialfolio.errors import TrialFolioError, reason_of
from trialfolio.experiment_paths import (
    CONFIGURATION,
    EXPERIMENT_RECORD,
    MANIFEST,
    PLAN,
    REPORT,
    REQUEST,
    RESPONSE,
    RESPONSE_RAW,
    SESSION_RECORD,
    plan_path,
    session_path,
)
from trialfolio.normalization import (
    METRICS_PATH,
    PARSER_VERSION,
    SETTINGS_PATH,
    RankingOriginals,
    case_metrics_rows,
    case_tables_path,
)
from trialfolio.planning import retired_cases, retired_cases_v1_1
from trialfolio.record_checks import (
    RecordChecks,
    artifact_id,
    definition_hash,
    drawn_from,
    holds_each_metric,
    holds_each_setting,
    holds_each_weight,
    labeled,
    matches,
    named,
)
from trialfolio.storage import LOCK_PATH, ArtifactStore, StoredFile
from trialfolio.tables import (
    metrics_csv,
    read_metrics_csv,
    read_settings_csv,
    read_settings_csv_v1_1,
)

type AttemptOutcome = Literal["succeeded", "failed", "unknown"]

type AnyPlan = PlanV1_1 | PlanV1_3
"""An experiment's plan: 1.1.0, or 1.3.0 with a ranking definition."""

type AnyExperimentRecord = ExperimentRecord | ExperimentRecordV1_1
"""A plan's `experiment.json`: 1.0.0, or 1.1.0 once a plan of the experiment is 1.3.0."""

type AnyPlanCase = ExperimentPlanCase | ExperimentPlanCaseV1_3

type AnyStart = StartRecordV1_1 | StartRecordV1_3

type AnyAttemptRecord = AttemptRecordV1_1 | AttemptRecordV1_3

type AnyManifest = ExperimentManifest | ExperimentManifestV1_1

type AnyArtifact = ExperimentArtifact | ExperimentArtifactV1_1

DEFINITION: Final = "definition.xml"
"""A plan's copy of its ranking definition, in its `plans/<n>/` (ranking definitions)."""

_ATTEMPT_FILES: Final[dict[str, AttemptRole]] = {
    AUTHENTICATION_RECORD: "authentication_record",
    REQUEST: "provider_request",
    START_RECORD: "start_record",
    RESPONSE: "provider_response",
    RESPONSE_RAW: "provider_response_undecoded",
    ATTEMPT_RECORD: "attempt_record",
}
"""The files an attempt writes, in the order it writes them, with their roles."""

_RANKING_ATTEMPT_FILES: Final[dict[str, AttemptRole]] = {
    AUTHENTICATION_RECORD: "authentication_record",
    RANK_UPDATE_REQUEST_FILE: "rank_update_request",
    UPDATE_RECORD: "update_record",
    RANK_UPDATE_RESPONSE_FILE: "rank_update_response",
    RANK_UPDATE_RESPONSE_RAW: "rank_update_response_undecoded",
    REQUEST: "provider_request",
    START_RECORD: "start_record",
    RESPONSE: "provider_response",
    RESPONSE_RAW: "provider_response_undecoded",
    ATTEMPT_RECORD: "attempt_record",
}
"""The same, for an attempt that sends a definition, which writes the `rank_update`'s files, and
its update record, before its backtest's (sending a definition)."""

_RANK_UPDATE_FILES: Final = frozenset(
    {RANK_UPDATE_REQUEST_FILE, UPDATE_RECORD, RANK_UPDATE_RESPONSE_FILE, RANK_UPDATE_RESPONSE_RAW}
)
"""The files only an attempt that sends a definition writes: the `rank_update`'s, and its update
record."""

_PLAN_FILES: Final = frozenset({CONFIGURATION, PLAN, EXPERIMENT_RECORD})
"""The files of a plan's directory, `plans/<n>/`."""

_RANKING_PLAN_FILES: Final = _PLAN_FILES | {DEFINITION}
"""The same, with the copy of a ranking definition, which a plan 1.3.0's directory holds."""

_NUMBER: Final = re.compile(r"[1-9][0-9]*")
_CASE_ID: Final = re.compile(r"case-[0-9a-f]{16}")
_ATTEMPT_ID: Final = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_TOKEN_DROPPED: Final = frozenset({401, 403})
"""The statuses after which the client drops its token, so a later request authenticates again."""

type _Record = AuthenticationRecord | AnyStart | AnyAttemptRecord
"""One of an attempt's records."""

_READABLE: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "experiment_record": ("experiment records", ("1.0.0",)),
    "plan": ("plans", ("1.1.0",)),
    "session_record": ("session records", ("1.0.0",)),
    "manifest": ("experiment manifests", ("1.0.0",)),
    "authentication_record": ("authentication records", ("1.0.0",)),
    "start_record": ("start records", ("1.1.0",)),
    "attempt_record": ("attempt records", ("1.1.0",)),
    "configuration": ("experiment configurations", ("1.0.0",)),
    "metrics": ("metrics.csv", (TABLES_SCHEMA_VERSION,)),
    "settings": ("settings.csv", (TABLES_SCHEMA_VERSION,)),
}
"""The schema versions this version reads, for each kind of record, with what they're called in
messages: 0.3.0's, as `trialfolio run` reads them until release 0.4.0's R04-T12."""

_RANKING_READABLE: Final[dict[str, tuple[str, tuple[str, ...]]]] = {
    "experiment_record": ("experiment records", ("1.0.0", "1.1.0")),
    "plan": ("plans", ("1.1.0", "1.3.0")),
    "session_record": ("session records", ("1.0.0",)),
    "manifest": ("experiment manifests", ("1.0.0", "1.1.0")),
    "authentication_record": ("authentication records", ("1.0.0",)),
    "update_record": ("update records", ("1.3.0",)),
    "start_record": ("start records", ("1.1.0", "1.3.0")),
    "attempt_record": ("attempt records", ("1.1.0", "1.3.0")),
    "configuration": ("experiment configurations", ("1.0.0", "1.1.0")),
    "metrics": ("metrics.csv", (TABLES_SCHEMA_VERSION,)),
    "settings": ("settings.csv", (TABLES_SCHEMA_VERSION, TABLES_SCHEMA_VERSION_V1_1)),
}
"""The same, with an experiment with a ranking definition's, as a read with `ranking` reads
them."""


# What a resume reads


@dataclass(frozen=True)
class SavedPlan:
    """A plan of the experiment: `plans/<number>/`, with its `experiment.json`."""

    number: int
    plan: AnyPlan
    record: AnyExperimentRecord
    configuration: StoredFile
    configuration_content: bytes
    files: tuple[tuple[ExperimentArtifactRoleV1_1, StoredFile], ...]
    """Its `configuration.yaml`, its `definition.xml` for a plan 1.3.0, its `plan.json`, and its
    `experiment.json`, in the order they're written."""
    configuration_version: str
    """The schema version of its `configuration.yaml`, which its manifest entry records."""
    definition: StoredFile | None = None
    """Its `definition.xml`, for a plan 1.3.0, whose ranking is a definition."""
    read: ExperimentConfigurationRead | None = None
    """For a plan 1.3.0, its configuration as release 0.4.0's reader read it, with its
    `definition.xml`, from which its cases' weight rows take their originals."""

    def case(self, case_id: str) -> AnyPlanCase:
        """The plan's case with this `case_id`. Raises `KeyError` when it has none."""
        for case in self.plan.cases:
            if case.case_id == case_id:
                return case
        raise KeyError(case_id)

    @property
    def ranked(self) -> bool:
        """Whether this plan, or an earlier plan of the experiment, is 1.3.0, as its
        `experiment.json` 1.1.0 shows."""
        return isinstance(self.record, ExperimentRecordV1_1)


@dataclass(frozen=True)
class SavedExperimentAttempt:
    """An attempt of the experiment, as its records read: an attempt record, or, without one, a
    start record, which reads as `running`, an update record alone, or only its authentication
    record. The outcome and the counts read an attempt without its attempt record as step 8 will
    record it."""

    case_id: str
    attempt_id: uuid.UUID
    plan: int
    """The number of the plan it ran under."""
    session: int
    sequence: int
    repeat_of: uuid.UUID | None
    authentication: AuthenticationRecord | None
    start: AnyStart | None
    record: AnyAttemptRecord | None
    files: tuple[AttemptFile, ...]
    """Each file of its directory, in the order the attempt writes them."""
    response: tuple[SavedResponse, bytes] | None
    """The saved response its attempt record references, or, without an attempt record, the one
    its directory holds, with its bytes."""
    decoded_response: bytes | None
    """The bytes of the `response.json` its directory holds, if it holds one: its saved
    response's, or one whose write failed after the store published it, which its attempt record
    doesn't reference, so it isn't `response` (docs/contracts.md, the executor). A manifest lists
    it either way, and `return_series` reads it."""
    update: StartRecordV1_3 | None = None
    """The update record, `updating.json`, of an attempt that sends a definition, when it wrote
    one."""
    rank_response: tuple[RankUpdateResponse, bytes] | None = None
    """The `rank_update`'s saved response its attempt record references, or, without an attempt
    record, the one its directory holds, with its bytes."""

    @property
    def directory(self) -> str:
        return attempt_directory(self.case_id, self.attempt_id)

    @property
    def version(self) -> str:
        """The schema version of its start and attempt records, when it has one: 1.3.0 for an
        attempt that sends a definition, and 1.1.0 otherwise."""
        records = (self.record, self.start, self.update)
        found = next((record for record in records if record is not None), None)
        return "1.1.0" if found is None else found.schema_version

    @property
    def opening(self) -> AnyStart | None:
        """Its first start record, the last write before its first send: its update record, for
        an attempt that sends a definition, or else its start record."""
        return self.update if self.update is not None else self.start

    @property
    def outcome(self) -> AttemptOutcome:
        """Its attempt record's, or the one step 8 will record: `succeeded` for a `running`
        attempt with a saved response, `unknown` for one without; for one whose latest record is
        its update record, `failed` with the `rank_update`'s response saved, and `unknown`
        without it; and `failed` for one with only its authentication record."""
        if self.record is not None:
            return self.record.outcome
        if self.start is not None:
            return "succeeded" if self.response is not None else "unknown"
        if self.update is not None:
            return "failed" if self.rank_response is not None else "unknown"
        return "failed"

    @property
    def possibly_charged(self) -> bool:
        """Whether its request may have reached Portfolio123: a `running` attempt's may have,
        and so may the `rank_update` of one whose latest record is its update record, and one
        with only its authentication record sent nothing."""
        if self.record is not None:
            return self.record.possibly_charged
        return self.opening is not None

    @property
    def error_code(self) -> str | None:
        """Its attempt record's error code, or the one step 8 will record."""
        if self.record is not None:
            return None if self.record.error is None else self.record.error.code
        if self.outcome == "succeeded":
            return None
        rank_response = self.rank_response
        if (
            self.start is None
            and rank_response is not None
            and rank_response[0].form == "undecoded"
        ):
            return "provider.response_invalid"
        return "command.interrupted"

    @property
    def provider_requests(self) -> int:
        """The sends the budget counts: a `running` attempt's request is one, and an attempt
        that sends a definition counts one for each start record it wrote (counting the
        requests)."""
        if self.record is not None:
            return provider_requests(self.record)
        return sum(record is not None for record in (self.update, self.start))

    @property
    def authentication_calls(self) -> int:
        """Trial Folio's own authentication calls the budget counts: the `POST /auth` exchanges
        of its attempt record, or of its first start record when it has no attempt record yet,
        or one when its authentication record is its only record (the budget across runs)."""
        if self.record is not None:
            return _authentications(self.record.exchanges)
        if self.opening is not None:
            return _authentications(self.opening.exchanges)
        return 1

    def completed_record(self, plan: AnyPlan, ended_at: datetime) -> AnyAttemptRecord:
        """The attempt record a resume writes for this attempt, which has none, keeping its
        records' contents, `session`, `sequence`, and `repeat_of` (docs/contracts.md, uncertain
        completion, and experiment attempts). `plan` is the plan it ran under, and `ended_at`
        when the record is written, or its start time when the clock reads earlier.

        - **A `running` attempt with a saved response** is `succeeded`: its request's exchange is
          recorded as a `response` with status 200 and the note `completed_from_saved_response`.
        - **A `running` attempt without one** is `unknown`, possibly charged, with its start
          record's exchanges, and `command.interrupted`, as an interrupt during the send gives.
        - **An attempt with only its authentication record** is `failed`, not possibly charged,
          with `command.interrupted`, and its one exchange, the authentication call's, recorded
          as `interrupted`. A `request.json` it wrote isn't referenced.

        Under a plan 1.3.0, the record is 1.3.0, with the `rank_update`'s files in its
        `ranking_update`, and a `running` attempt's exchanges are its start record's, the
        `rank_update`'s 200 among them. An attempt whose latest record is its update record is
        recorded as sending a definition says: with the `rank_update`'s saved response, its
        exchange is a `response` with status 200 and the note `completed_from_saved_response`,
        and the attempt is `failed`, with `command.interrupted`, or `provider.response_invalid`
        for a response saved undecoded; without it, the exchange is `interrupted`, and the
        attempt `unknown`, with `command.interrupted`. Either way, it's possibly charged, and a
        backtest's `request.json` it wrote isn't referenced.

        Raises `ValueError` when it has an attempt record.
        """
        if self.record is not None:
            raise ValueError("the attempt has its attempt record")
        ended_at = max(ended_at, self.started_at)
        if isinstance(plan, PlanV1_3):
            return self._completed_v1_3(plan, ended_at)
        start = self.start
        if start is None:
            return AttemptRecordV1_1.model_validate(
                {
                    **self._identity("1.1.0"),
                    "authenticated_by": None,
                    "repeat_of": self.repeat_of,
                    "started_at": self.started_at,
                    "provider_wrapper": plan.provider_wrapper,
                    "transport": plan.transport,
                    "ended_at": ended_at,
                    "outcome": "failed",
                    "error": _stopped_authenticating(ranking=False),
                    "exchanges": (_AUTHENTICATION_INTERRUPTED,),
                    "possibly_charged": False,
                    "request": None,
                    "response": None,
                    "provider_metadata": _NO_METADATA,
                }
            )
        common = {
            **self._identity("1.1.0"),
            "authenticated_by": start.authenticated_by,
            "repeat_of": start.repeat_of,
            "started_at": start.started_at,
            "provider_wrapper": start.provider_wrapper,
            "transport": start.transport,
            "ended_at": ended_at,
            "possibly_charged": True,
            "request": self._reference(REQUEST),
        }
        return AttemptRecordV1_1.model_validate({**common, **self._backtest_ending(start)})

    def _completed_v1_3(self, plan: PlanV1_3, ended_at: datetime) -> AttemptRecordV1_3:
        """The attempt record 1.3.0 a resume writes for an attempt under a plan 1.3.0, as
        `completed_record` says."""
        opening = self.opening
        if opening is None:
            return AttemptRecordV1_3.model_validate(
                {
                    **self._identity("1.3.0"),
                    "operation": "screen_backtest",
                    "authenticated_by": None,
                    "repeat_of": self.repeat_of,
                    "started_at": self.started_at,
                    "provider_wrapper": plan.provider_wrapper,
                    "transport": plan.transport,
                    "ended_at": ended_at,
                    "outcome": "failed",
                    "error": _stopped_authenticating(ranking=True),
                    "exchanges": (_AUTHENTICATION_INTERRUPTED,),
                    "possibly_charged": False,
                    "ranking_update": RankingUpdate(
                        request=None, response=None, provider_metadata=_NO_METADATA
                    ),
                    "request": None,
                    "response": None,
                    "provider_metadata": _NO_METADATA,
                }
            )
        common = {
            **self._identity("1.3.0"),
            "operation": "screen_backtest",
            "authenticated_by": opening.authenticated_by,
            "repeat_of": opening.repeat_of,
            "started_at": opening.started_at,
            "provider_wrapper": opening.provider_wrapper,
            "transport": opening.transport,
            "ended_at": ended_at,
            "possibly_charged": True,
            "ranking_update": self._ranking_update(),
        }
        if self.start is not None:
            return AttemptRecordV1_3.model_validate(
                {**common, "request": self._reference(REQUEST), **self._backtest_ending(self.start)}
            )
        return AttemptRecordV1_3.model_validate(
            {
                **common,
                **self._update_ending(cast("StartRecordV1_3", self.update)),
                "request": None,
                "response": None,
                "provider_metadata": _NO_METADATA,
            }
        )

    def _backtest_ending(self, start: AnyStart) -> dict[str, object]:
        """The ending of a `running` attempt: `succeeded` from its saved response, or `unknown`
        without one (uncertain completion)."""
        ranking = isinstance(start, StartRecordV1_3)
        if self.response is None:
            detail = (
                ranking_detail("unknown", possibly_charged=True, backtest_sent=True)
                if ranking
                else request_detail("unknown", possibly_charged=True)
            )
            return {
                "outcome": "unknown",
                "error": ErrorDetail(
                    code="command.interrupted",
                    message=(
                        "The run that started the attempt stopped after its start record was"
                        f" written, before a response was saved. {detail}"
                    ),
                ),
                "exchanges": start.exchanges,
                "response": None,
                "provider_metadata": _NO_METADATA,
            }
        saved, content = self.response
        return {
            "outcome": "succeeded",
            "error": None,
            "exchanges": (
                *start.exchanges,
                Exchange(
                    request=SCREEN_BACKTEST_REQUEST,
                    result="response",
                    status=200,
                    note="completed_from_saved_response",
                ),
            ),
            "response": saved,
            "provider_metadata": _metadata(saved, content),
        }

    def _update_ending(self, update: StartRecordV1_3) -> dict[str, object]:
        """The ending of an attempt whose latest record is its update record (an attempt stopped
        after its update record): `failed` with the `rank_update`'s saved response, and `unknown`
        without it."""
        if self.rank_response is None:
            detail = ranking_detail("unknown", possibly_charged=True, backtest_sent=False)
            return {
                "outcome": "unknown",
                "error": ErrorDetail(
                    code="command.interrupted",
                    message=(
                        "The run that started the attempt stopped after its update record was"
                        f" written, before the rank_update's response was saved. {detail}"
                    ),
                ),
                "exchanges": (
                    *update.exchanges,
                    Exchange(
                        request=RANK_UPDATE_REQUEST, result="interrupted", status=None, note=None
                    ),
                ),
            }
        saved, _ = self.rank_response
        detail = ranking_detail("failed", possibly_charged=True, backtest_sent=False)
        if saved.form == "undecoded":
            error = ErrorDetail(
                code="provider.response_invalid",
                message=(
                    "Portfolio123 answered the rank_update request with a 200 whose body couldn't"
                    f" be decoded as JSON, so it was saved as it came, as {RANK_UPDATE_RESPONSE_RAW}."
                    " Trial Folio sends the case's screen backtest only after one whose response"
                    f" it could read, and the run that started the attempt stopped. {detail}"
                ),
            )
        else:
            error = ErrorDetail(
                code="command.interrupted",
                message=(
                    "The run that started the attempt stopped after the rank_update's response"
                    f" was saved, before the screen backtest request was sent. {detail}"
                ),
            )
        return {
            "outcome": "failed",
            "error": error,
            "exchanges": (
                *update.exchanges,
                Exchange(
                    request=RANK_UPDATE_REQUEST,
                    result="response",
                    status=200,
                    note="completed_from_saved_response",
                ),
            ),
        }

    def _ranking_update(self) -> RankingUpdate:
        """The `rank_update`'s files, as the attempt record references them: its request, and its
        saved response, with what that response reports of its charge."""
        response = None
        metadata = _NO_METADATA
        if self.rank_response is not None:
            response, content = self.rank_response
            metadata = _metadata(response, content)
        return RankingUpdate(
            request=self._reference(RANK_UPDATE_REQUEST_FILE),
            response=response,
            provider_metadata=metadata,
        )

    def _reference(self, name: str) -> ArtifactReference:
        """A reference to the file `name` of its directory, which the records check found."""
        path = f"{self.directory}/{name}"
        stored = next(file.file for file in self.files if file.file.path == path)
        return ArtifactReference(path=stored.path, artifact_id=stored.artifact_id)

    @property
    def started_at(self) -> datetime:
        records = (self.record, self.start, self.update, self.authentication)
        return next(record.started_at for record in records if record is not None)

    def _identity(self, schema_version: str) -> dict[str, object]:
        records = (self.update, self.start, self.authentication)
        version = next(record.trialfolio_version for record in records if record is not None)
        plan_hash_ = next(record.plan_hash for record in records if record is not None)
        return {
            "schema_version": schema_version,
            "trialfolio_version": version,
            "attempt_id": self.attempt_id,
            "case_id": self.case_id,
            "plan_hash": plan_hash_,
            "session": self.session,
            "sequence": self.sequence,
        }


_NO_METADATA: Final = ProviderMetadata(cost=None, quota_remaining=None)
"""What a request without a decoded response reports of its charge: nothing."""

_AUTHENTICATION_INTERRUPTED: Final = Exchange(
    request=AUTHENTICATION_REQUEST, result="interrupted", status=None, note=None
)
"""The authentication call of an attempt whose only record is its authentication record: nothing
shows whether it was made, or how it ended."""


def _stopped_authenticating(*, ranking: bool) -> ErrorDetail:
    """The error of an attempt whose only record is its authentication record."""
    detail = (
        ranking_detail("failed", possibly_charged=False, backtest_sent=False)
        if ranking
        else request_detail("failed", possibly_charged=False)
    )
    return ErrorDetail(
        code="command.interrupted",
        message=(
            "The run that started the attempt stopped while it authenticated, before its request"
            f" was sent. {detail}"
        ),
    )


@dataclass(frozen=True)
class SavedTables:
    """A case's normalized tables, as the check read them."""

    metrics: StoredFile
    metrics_rows: tuple[MetricsRow, ...]
    settings: StoredFile | None
    """None when a stopped run wrote `metrics.csv` alone."""
    settings_rows: tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...] | None
    """`settings.csv`'s rows, with `settings`: version 1.1.0's for a case of a plan 1.3.0."""
    parser_version: int
    """The parser that wrote `metrics.csv`: the one the latest manifest names, when it lists the
    table, and otherwise the installed one, which the check found writes it."""

    @property
    def settings_version(self) -> str:
        """The schema version of `settings.csv`: 1.1.0 for a case whose ranking is a
        definition."""
        rows = self.settings_rows or ()
        return (
            TABLES_SCHEMA_VERSION_V1_1
            if rows and isinstance(rows[0], SettingsRowV1_1)
            else (TABLES_SCHEMA_VERSION)
        )


@dataclass(frozen=True)
class MissingTables:
    """What a resume writes for a case whose succeeded attempt has no `settings.csv`: both
    tables, or `settings.csv` beside a `metrics.csv` a stopped run wrote."""

    attempt: SavedExperimentAttempt
    case: AnyPlanCase
    """The case as the plan its attempt ran under holds it."""
    configuration: StoredFile
    """That plan's `configuration.yaml`."""
    originals: Mapping[str, tuple[str, str]]
    """Each setting's key path and text in that configuration."""
    ranking: RankingOriginals | None
    """For a case of a plan 1.3.0, where its weight rows take their originals: that plan's
    `definition.xml`, or its configuration, for a weight the case's ranking variant changes."""
    response: SavedResponse
    content: bytes
    """The response's bytes, as the check read them."""
    metrics_rows: tuple[MetricsRow, ...] | None
    """The rows the installed parser writes to `metrics.csv` from the response, when the case
    has none yet; None when it has, or when the response fails validation."""
    invalid: TrialFolioError | None
    """The `provider.response_invalid` the response gets, when the case has no `metrics.csv`."""


class _CaseRecords:
    """What the experiment's records say of a case of a plan (the cases that are due), for
    `SavedCase` and `SavedRankingCase`, which hold these fields."""

    attempts: tuple[SavedExperimentAttempt, ...]
    valid: bool

    @property
    def state(self) -> CaseState:
        """`complete`, `due`, or `awaiting_repeat`, by `case_state`."""
        return case_state(self.attempts)

    @property
    def latest_charged(self) -> SavedExperimentAttempt | None:
        """Its latest possibly charged attempt, whose `attempt_id` confirms a repeat."""
        return latest_charged(self.attempts)

    @property
    def outcome(self) -> CaseOutcome:
        """As the manifest counts it."""
        return case_outcome(self.attempts, valid=self.valid)


@dataclass(frozen=True)
class SavedCase(_CaseRecords):
    """A case of a plan 1.1.0, and what the experiment's records say of it."""

    case: ExperimentPlanCase
    attempts: tuple[SavedExperimentAttempt, ...]
    """Every attempt of the case, under any plan, by session and then sequence."""
    valid: bool
    """Whether its succeeded attempt's response passed validation, or will once a resume writes
    its tables, when it has one."""


@dataclass(frozen=True)
class SavedRankingCase(_CaseRecords):
    """A case of a plan 1.3.0, whose ranking is a definition, and what the experiment's records
    say of it, as `SavedCase` gives a case of a plan 1.1.0."""

    case: ExperimentPlanCaseV1_3
    attempts: tuple[SavedExperimentAttempt, ...]
    valid: bool


@dataclass(frozen=True)
class SavedExperiment:
    """An experiment's records, read and checked.

    The store it was read from holds the experiment lock, when `open_experiment` read it, until
    its owner closes it, so the records don't change while a resume uses them.
    """

    plans: tuple[SavedPlan, ...]
    """Each plan with its `experiment.json`, by number. The last is the current plan."""
    sessions: tuple[SessionRecord, ...]
    """Each session with its session record, by number."""
    attempts: tuple[SavedExperimentAttempt, ...]
    """Every attempt, of every case, retired ones included, by session and then sequence."""
    tables: Mapping[str, SavedTables]
    """Each case's tables, by `case_id`."""
    missing: Mapping[str, MissingTables]
    """What a resume writes for each case whose succeeded attempt has no `settings.csv`, by
    `case_id`."""
    manifest: AnyManifest | None
    """The latest manifest; None when no session has one."""
    next_plan: int
    """The number a revision's `plans/<n>/` takes: one more than the largest in the directory,
    with or without its `experiment.json`."""
    next_session: int
    """The number the next session takes, as `next_plan`."""

    @property
    def current(self) -> SavedPlan:
        """The current plan: the highest-numbered one with an `experiment.json`."""
        return self.plans[-1]

    @property
    def plan(self) -> PlanV1_1:
        """The current plan of an experiment without a ranking definition, which `trialfolio run`
        resumes until release 0.4.0's R04-T12; `current` gives any experiment's. Raises
        `TypeError` for a plan 1.3.0, which only a read with `ranking` reads."""
        plan = self.current.plan
        if not isinstance(plan, PlanV1_1):
            raise TypeError("the current plan has a ranking definition: read it from `current`")
        return plan

    @property
    def record(self) -> ExperimentRecord:
        """The current plan's `experiment.json`, the experiment's research record, for an
        experiment without a ranking definition, as `plan` gives its plan. Raises `TypeError`
        for an `experiment.json` 1.1.0, which `current` gives."""
        record = self.current.record
        if not isinstance(record, ExperimentRecord):
            raise TypeError("a plan of the experiment has a ranking definition: use `current`")
        return record

    @property
    def synthetic(self) -> bool:
        """Whether the experiment was executed with the demo's client: its plans record the
        approval `not_required`."""
        return self.current.record.plans[0].approval == "not_required"

    @property
    def provider_requests(self) -> int:
        """The sends counted against the budget, across every attempt of the experiment."""
        return counted_requests(self.attempts)

    @property
    def authentication_calls(self) -> int:
        """Trial Folio's own authentication calls counted against the budget."""
        return counted_authentications(self.attempts)

    def saved_plan(self, number: int) -> SavedPlan:
        """The plan with this number. Raises `KeyError` when there's none."""
        for saved in self.plans:
            if saved.number == number:
                return saved
        raise KeyError(number)

    def attempts_of(self, case_id: str) -> tuple[SavedExperimentAttempt, ...]:
        """The case's attempts, by session and then sequence."""
        return tuple(attempt for attempt in self.attempts if attempt.case_id == case_id)

    @overload
    def cases(self, plan: PlanV1_1) -> tuple[SavedCase, ...]: ...
    @overload
    def cases(self, plan: PlanV1_3) -> tuple[SavedRankingCase, ...]: ...
    def cases(self, plan: AnyPlan) -> tuple[SavedCase, ...] | tuple[SavedRankingCase, ...]:
        """Each case of `plan`, the current plan or a revision of it, in its order, with what the
        records say of it."""
        if isinstance(plan, PlanV1_3):
            return tuple(
                SavedRankingCase(case, self.attempts_of(case.case_id), self.valid(case.case_id))
                for case in plan.cases
            )
        return tuple(
            SavedCase(case, self.attempts_of(case.case_id), self.valid(case.case_id))
            for case in plan.cases
        )

    def valid(self, case_id: str) -> bool:
        """Whether the case's succeeded attempt's response passed validation, or will pass it
        when a resume writes its tables: it has `metrics.csv`, or the installed parser reads its
        response. True for a case without a succeeded attempt."""
        missing = self.missing.get(case_id)
        return missing is None or missing.invalid is None

    def counts(self, plan: AnyPlan) -> ExperimentManifestCounts:
        """The experiment's counts over `plan`, the current plan or a revision of it, as the
        records give them: those the manifest of a session that sent nothing under `plan` would
        give. The executor counts its own session's attempts with the same rules."""
        invalid = {case_id for case_id in self.missing if not self.valid(case_id)}
        record = self.current.record
        if isinstance(record, ExperimentRecord) and isinstance(plan, PlanV1_1):
            retired = len(retired_cases(record, plan))
        else:
            retired = len(retired_cases_v1_1(record, plan))
        return experiment_counts(plan, self.attempts, invalid=invalid, retired=retired)

    def metrics_unavailable(self, plan: AnyPlan) -> int:
        """The `unavailable` rows of the `metrics.csv` files of `plan`'s cases."""
        return unavailable_metrics(
            plan, {case_id: tables.metrics_rows for case_id, tables in self.tables.items()}
        )

    def listed(self, path: str) -> AnyArtifact | None:
        """The latest manifest's entry for the file at `path`, when it lists it."""
        if self.manifest is None:
            return None
        for artifact in self.manifest.artifacts:
            if artifact.path == path:
                return artifact
        return None


def open_experiment(store: ArtifactStore, *, ranking: bool = False) -> SavedExperiment:
    """Takes the experiment lock on the output directory of `store`, and reads and checks its
    records, as `read_experiment` does (docs/contracts.md, a resumed experiment, steps 3 and 4),
    an experiment with a ranking definition's too with `ranking`.

    The store holds the lock until its owner closes it, whatever this raises, so the records
    can't change while the caller uses them.

    Raises `TrialFolioError` with `output.not_empty` when the directory holds no
    `experiment.lock`, so it isn't an experiment's; with `experiment.locked` when another process
    holds the lock; with `storage.write_failed` when the file system refuses it; and as
    `read_experiment` does.
    """
    try:
        store.lock(LOCK_PATH)
    except FileNotFoundError:
        raise TrialFolioError(
            "output.not_empty",
            "The output directory isn't empty, and it isn't an experiment's: it holds no"
            f" {LOCK_PATH}. Nothing was sent or written. Run the configuration into a new or"
            " empty output directory.",
        ) from None
    return read_experiment(store, ranking=ranking)


def read_experiment(store: ArtifactStore, *, ranking: bool = False) -> SavedExperiment:
    """Reads the records of the experiment in the output directory of `store`, each file once,
    and checks them, as the module says. Writes nothing. With `ranking`, it reads an experiment
    with a ranking definition too; without it, 0.3.0's versions only.

    Raises `TrialFolioError` with `input.not_a_run` when they aren't a complete, consistent
    experiment; with `artifact.unknown_schema_version` when a record, or the latest manifest's
    entry for one, has a schema version this version has no reader for; and with
    `output.not_empty` when the directory has no `plans/1/experiment.json`, because its first run
    stopped before anything was sent.
    """
    reader = _Reader(store, ranking=ranking)
    # The latest manifest's files first: one missing from an incomplete copy, the first plan's
    # included, is reported as missing.
    sessions, manifest_session, next_session = _sessions(reader)
    manifest = None if manifest_session is None else _latest_manifest(reader, manifest_session)
    plans, next_plan = _plans(reader)
    synthetic = plans[0].record.plans[0].approval == "not_required"
    if manifest is not None:
        _check_manifest(manifest, plans, synthetic=synthetic)
    attempts = _attempts(reader, plans, {record.session for record in sessions})
    _check_authentication(attempts)
    _check_repeats(attempts)
    listed: dict[str, AnyArtifact] = (
        {} if manifest is None else {a.path: a for a in manifest.artifacts}
    )
    plans = [_with_version(reader, saved, listed) for saved in plans]
    since = tuple(
        record.trialfolio_version
        for record in sessions
        if manifest is None or record.session > manifest.session
    )
    tables = _tables(reader, plans, attempts, listed, since)
    missing = _missing(plans, attempts, tables)
    return SavedExperiment(
        plans=tuple(plans),
        sessions=tuple(sessions),
        attempts=tuple(attempts),
        tables=MappingProxyType(tables),
        missing=MappingProxyType(missing),
        manifest=manifest,
        next_plan=next_plan,
        next_session=next_session,
    )


# Reading


class _Reader:
    """Reads the output directory's files through the store, each once, with the checks of the
    versions it reads: 0.3.0's, or, with `ranking`, an experiment with a ranking definition's
    too."""

    def __init__(self, store: ArtifactStore, *, ranking: bool) -> None:
        self._store = store
        self._contents: dict[str, bytes | None] = {}
        self.ranking = ranking
        self.checks = _RANKING_CHECKS if ranking else _CHECKS
        self.attempt_files = _RANKING_ATTEMPT_FILES if ranking else _ATTEMPT_FILES
        """The files an attempt writes, in the order it writes them, with their roles."""
        self.plan_files = _RANKING_PLAN_FILES if ranking else _PLAN_FILES
        """The files a plan's directory holds."""

    def get(self, path: str) -> bytes | None:
        """The file's bytes, or None when there's no such file."""
        if path not in self._contents:
            try:
                self._contents[path] = self._store.read(path)
            except FileNotFoundError:
                self._contents[path] = None
            except OSError as error:
                raise _refused(f"{named(path)} can't be read ({reason_of(error)}).") from None
        return self._contents[path]

    def require(self, path: str) -> bytes:
        content = self.get(path)
        if content is None:
            raise _refused(f"{named(path)} is missing.")
        return content

    def names(self, path: str) -> tuple[str, ...]:
        """The names in the directory, apart from hidden ones: a store's temporary files, which a
        stopped write can leave, and a file system's own. Empty when there's no such
        directory."""
        try:
            found = self._store.entries(path)
        except FileNotFoundError:
            return ()
        except NotADirectoryError:
            raise _refused(f"{named(path)} isn't a directory.") from None
        except OSError as error:
            raise _refused(f"{named(path)} can't be read ({reason_of(error)}).") from None
        return tuple(name for name in found if not name.startswith("."))

    def numbered(self, path: str) -> list[int]:
        """The numbers of the directories in `plans/` or `sessions/`, in order."""
        names = self.names(path)
        if any(not _NUMBER.fullmatch(name) for name in names):
            raise _refused(f"{named(path + '/')} holds an entry that isn't a numbered directory.")
        return sorted(int(name) for name in names)


def _plans(reader: _Reader) -> tuple[list[SavedPlan], int]:
    numbers = reader.numbered("plans")
    if 1 not in numbers or EXPERIMENT_RECORD not in reader.names("plans/1"):
        raise TrialFolioError(
            "output.not_empty",
            "The output directory holds an experiment whose first run stopped before its first"
            " plan was recorded, so nothing was sent, and it can't be resumed. Remove the"
            " directory, and run the command again.",
        )
    plans: list[SavedPlan] = []
    for number in numbers:
        names = reader.names(f"plans/{number}")
        if set(names) - reader.plan_files:
            raise _refused(f"{named(f'plans/{number}/')} holds a file no plan has.")
        if EXPERIMENT_RECORD in names:
            plans.append(_plan(reader, number, plans[-1] if plans else None))
    return plans, max(numbers) + 1


def _plan(reader: _Reader, number: int, previous: SavedPlan | None) -> SavedPlan:
    """`plans/<number>/`, checked, given the plan with the number before it, if there's one."""
    record_path = plan_path(number, EXPERIMENT_RECORD)
    record_content = reader.require(record_path)
    record = _experiment_record(reader, record_content, record_path)
    path = plan_path(number, PLAN)
    content = reader.require(path)
    plan = _plan_record(reader, content, path)
    reader.checks.check_plan_hash(plan, named(path))
    configuration_path = plan_path(number, CONFIGURATION)
    configuration = reader.require(configuration_path)
    ranked = isinstance(plan, PlanV1_3) or (previous is not None and previous.ranked)
    if isinstance(record, ExperimentRecordV1_1) != ranked:
        raise _refused(
            f"{named(record_path)} isn't the version its plan's experiment.json is: 1.1.0 once"
            " its plan, or an earlier one, has a ranking definition, and 1.0.0 before."
        )
    _check_entry(record, number, plan, content, configuration)
    _check_history(record, number, plan, previous)
    _check_declared(record, number, plan, previous)
    definition = _definition(reader, number, plan)
    files: list[tuple[ExperimentArtifactRoleV1_1, StoredFile]] = [
        ("configuration", StoredFile.of(configuration_path, configuration))
    ]
    if definition is not None:
        files.append(("ranking_definition", definition))
    files.append(("plan", StoredFile.of(path, content)))
    files.append(("experiment_record", StoredFile.of(record_path, record_content)))
    return SavedPlan(
        number=number,
        plan=plan,
        record=record,
        configuration=StoredFile.of(configuration_path, configuration),
        configuration_content=configuration,
        files=tuple(files),
        configuration_version="",
        definition=definition,
    )


def _experiment_record(reader: _Reader, content: bytes, path: str) -> AnyExperimentRecord:
    """A plan's `experiment.json`, read by its schema version."""
    if _version(reader, content, path, "experiment_record") == "1.1.0":
        return reader.checks.record(ExperimentRecordV1_1, content, path, "experiment_record")
    return reader.checks.record(ExperimentRecord, content, path, "experiment_record")


def _plan_record(reader: _Reader, content: bytes, path: str) -> AnyPlan:
    """A plan's `plan.json`, read by its schema version."""
    if _version(reader, content, path, "plan") == "1.3.0":
        return reader.checks.record(PlanV1_3, content, path, "plan")
    return reader.checks.record(PlanV1_1, content, path, "plan")


def _version(reader: _Reader, content: bytes, path: str, kind: str) -> object:
    """The schema version of the record of `kind` in `content`, the file at `path`, checked: one
    this version reads."""
    version = reader.checks.json_object(content, path).get("schema_version")
    reader.checks.check_version(version, path, kind)
    return version


def _definition(reader: _Reader, number: int, plan: AnyPlan) -> StoredFile | None:
    """`plans/<number>/definition.xml`, for a plan 1.3.0, checked: there, and, read as a
    definition's file is read, with the hash its plan's `ranking_source` gives (a complete run,
    and checking the records). A plan 1.1.0 has none. A snapshot's records are release 0.4.0's
    R04-T10's."""
    path = plan_path(number, DEFINITION)
    if not isinstance(plan, PlanV1_3):
        if DEFINITION in reader.names(f"plans/{number}"):
            raise _refused(f"{named(path)} is there, though its plan has no ranking definition.")
        return None
    source = plan.ranking_source
    if source.form != "definition":
        raise _refused(
            f"{named(plan_path(number, PLAN))}'s ranking is a snapshot, whose records this version"
            " of Trial Folio doesn't read."
        )
    content = reader.get(path)
    if content is None:
        raise _refused(f"{named(path)} is missing, though its plan's ranking is a definition.")
    if definition_hash(content) != source.definition:
        raise _refused(
            f"{named(path)} isn't its plan's ranking definition: read as a definition's file is"
            " read, it doesn't have the hash its plan's ranking_source gives."
        )
    return StoredFile.of(path, content)


def _check_entry(
    record: AnyExperimentRecord, number: int, plan: AnyPlan, content: bytes, configuration: bytes
) -> None:
    """The last entry of `plans/<number>/experiment.json` is its directory's plan: by its number,
    its hash, and the `artifact_id`s of its `plan.json`, whose bytes are `content`, and of its
    `configuration.yaml`."""
    entry = record.plans[-1]
    last = f"{named(plan_path(number, EXPERIMENT_RECORD))}'s last entry isn't its directory's plan"
    if entry.plan != number:
        raise _refused(f"{last}: it gives another number.")
    if entry.plan_hash != plan.plan_hash:
        raise _refused(f"{last}: it gives another plan_hash than its plan.json.")
    if (entry.plan_artifact_id, entry.configuration_artifact_id) != (
        artifact_id(content),
        artifact_id(configuration),
    ):
        raise _refused(
            f"{last}: its plan.json or configuration.yaml has another artifact_id than it records."
        )


def _check_history(
    record: AnyExperimentRecord, number: int, plan: AnyPlan, previous: SavedPlan | None
) -> None:
    """The entries of `plans/<number>/experiment.json` before its last are the previous plan's,
    and its plan revises the previous plan. An `experiment.json` 1.1.0 holds the entries of a
    previous 1.0.0 one as version 1.1.0's entries."""
    earlier: tuple[object, ...] = () if previous is None else previous.record.plans
    if isinstance(record, ExperimentRecordV1_1):
        earlier = tuple(
            PlanEntryV1_1.model_validate_json(entry.model_dump_json())
            for entry in (() if previous is None else previous.record.plans)
        )
    if record.plans[:-1] != earlier:
        raise _refused(
            f"{named(plan_path(number, EXPERIMENT_RECORD))}'s earlier entries aren't those of the"
            " previous plan's experiment.json."
        )
    if plan.revises != (None if previous is None else previous.plan.plan_hash):
        raise _refused(f"{named(plan_path(number, PLAN))} doesn't revise the previous plan.")


def _check_declared(
    record: AnyExperimentRecord, number: int, plan: AnyPlan, previous: SavedPlan | None
) -> None:
    """`plans/<number>/experiment.json` records the experiment and its planned cases as its plan
    declares them, and the plan is the previous plan's experiment's."""
    planned = tuple(
        _recorded(case, ranked=isinstance(record, ExperimentRecordV1_1)) for case in plan.cases
    )
    declared = (record.experiment_id, record.title, record.purpose, record.prior_research)
    if planned != record.planned_cases or declared != (
        plan.experiment_id,
        plan.title,
        plan.purpose,
        plan.prior_research,
    ):
        raise _refused(
            f"{named(plan_path(number, EXPERIMENT_RECORD))} doesn't record the experiment and its"
            " planned cases as its plan declares them."
        )
    if previous is not None and plan.experiment_id != previous.plan.experiment_id:
        raise _refused(f"{named(plan_path(number, PLAN))} is another experiment's plan.")


def _recorded(case: AnyPlanCase, *, ranked: bool) -> RecordedCase | RecordedCaseV1_1:
    """A planned case, as its plan's `experiment.json` records it: in 1.1.0, with its variant's
    `set` and `remove`, null in a variant of another setting."""
    if not ranked and isinstance(case, ExperimentPlanCase):
        return RecordedCase(
            case_key=case.case_key,
            case_id=case.case_id,
            description=case.description,
            variant=case.variant,
        )
    variant = case.variant
    if variant is not None and not isinstance(variant, PlanVariantV1_3):
        variant = PlanVariantV1_3.model_validate(
            variant.model_dump(mode="json") | {"set": None, "remove": None}
        )
    return RecordedCaseV1_1(
        case_key=case.case_key,
        case_id=case.case_id,
        description=case.description,
        variant=variant,
    )


def _with_version(
    reader: _Reader, saved: SavedPlan, listed: Mapping[str, AnyArtifact]
) -> SavedPlan:
    """`saved` with its configuration's schema version: the latest manifest's, when it lists the
    file, and otherwise the version the configuration gives, read as a configuration is. A
    version this version has no reader for is `artifact.unknown_schema_version`, as the latest
    manifest's entry for the file would be. A plan 1.3.0's configuration is read by release
    0.4.0's reader, with the plan's `definition.xml`, and kept, for its cases' weight rows."""
    path = saved.configuration.path
    entry = listed.get(path)
    content = saved.configuration_content
    if saved.definition is not None:
        read = _ranked_configuration(reader, saved)
        version = read.configuration.schema_version
        if entry is not None and entry.schema_version is not None:
            version = entry.schema_version
        return replace(saved, configuration_version=version, read=read)
    if entry is not None and entry.schema_version is not None:
        return replace(saved, configuration_version=entry.schema_version)
    try:
        read = read_experiment_configuration(content, path)
    except TrialFolioError:
        pass
    else:
        return replace(saved, configuration_version=read.schema_version)
    _check_configuration_version(reader, content, path)
    raise _refused(f"{named(path)} isn't an experiment configuration this version reads.")


def _ranked_configuration(reader: _Reader, saved: SavedPlan) -> ExperimentConfigurationRead:
    """A plan 1.3.0's configuration, read with its `definition.xml` by release 0.4.0's reader,
    which reads no file but those bytes."""
    path = saved.configuration.path
    content = saved.configuration_content
    definition = cast("StoredFile", saved.definition)
    try:
        return read_experiment_configuration_v1_1(
            content, path, path, definition=reader.require(definition.path)
        )
    except (TrialFolioError, ValueError):
        pass
    _check_configuration_version(reader, content, path)
    raise _refused(
        f"{named(path)} isn't an experiment configuration this version reads, with its plan's"
        f" {DEFINITION}."
    )


def _check_configuration_version(reader: _Reader, content: bytes, path: str) -> None:
    """A configuration that can't be read with a schema version this version has no reader for
    is `artifact.unknown_schema_version`."""
    try:
        version = experiment_schema_version(content, path)
    except TrialFolioError:
        version = None
    if isinstance(version, str):
        reader.checks.check_version(version, path, "configuration")


def _sessions(reader: _Reader) -> tuple[list[SessionRecord], int | None, int]:
    numbers = reader.numbered("sessions")
    records: list[SessionRecord] = []
    manifest: int | None = None
    for number in numbers:
        names = reader.names(f"sessions/{number}")
        if set(names) - {SESSION_RECORD, REPORT, MANIFEST}:
            raise _refused(f"{named(f'sessions/{number}/')} holds a file no session has.")
        if SESSION_RECORD in names:
            path = session_path(number, SESSION_RECORD)
            record = reader.checks.record(
                SessionRecord, reader.require(path), path, "session_record"
            )
            if record.session != number:
                raise _refused(f"{named(path)} names another session than its directory's.")
            records.append(record)
        if MANIFEST in names:
            manifest = number
    return records, manifest, max(numbers, default=0) + 1


def _latest_manifest(reader: _Reader, session: int) -> AnyManifest:
    path = session_path(session, MANIFEST)
    content = reader.require(path)
    checks = reader.checks
    fields = checks.json_object(content, path)
    if fields.get("artifact_type") != "experiment":
        raise _refused(f"{named(path)} isn't an experiment's manifest.")
    version = fields.get("schema_version")
    checks.check_version(version, path, "manifest")
    manifest = (
        checks.validated(ExperimentManifestV1_1, content, path, "experiment manifest")
        if version == "1.1.0"
        else checks.validated(ExperimentManifest, content, path, "experiment manifest")
    )
    if manifest.session != session:
        raise _refused(f"{named(path)} names another session than its directory's.")
    for artifact in manifest.artifacts:
        checks.check_version(artifact.schema_version, artifact.path, artifact.role, listed=True)
        listed = reader.get(artifact.path)
        if listed is None:
            raise _refused(
                f"the latest manifest, {named(path)}, lists {named(artifact.path)}, which is"
                " missing."
            )
        if not matches(listed, artifact):
            raise _refused(
                f"{named(artifact.path)} doesn't match its artifact_id in the latest manifest,"
                " so it changed after the session wrote it."
            )
    return manifest


def _check_manifest(manifest: AnyManifest, plans: Sequence[SavedPlan], *, synthetic: bool) -> None:
    path = session_path(manifest.session, MANIFEST)
    if manifest.experiment_id != plans[0].plan.experiment_id:
        raise _refused(f"{named(path)} is another experiment's manifest.")
    found = [saved for saved in plans if saved.number == manifest.plan]
    if not found or found[0].plan.plan_hash != manifest.plan_hash:
        raise _refused(f"{named(path)} names a plan the experiment doesn't have.")
    if isinstance(manifest, ExperimentManifestV1_1) != found[0].ranked:
        raise _refused(
            f"{named(path)} isn't the version its session's manifest is: 1.1.0 once its plan, or"
            " an earlier one, has a ranking definition, and 1.0.0 before."
        )
    if manifest.synthetic and not synthetic:
        raise _refused(
            f"{named(path)} is synthetic, though the experiment's plans don't record the"
            " approval not_required."
        )
    if synthetic and not manifest.synthetic:
        raise _refused(
            f"{named(path)} isn't synthetic, though the experiment's plans record the approval"
            " not_required."
        )


def _attempts(
    reader: _Reader, plans: Sequence[SavedPlan], sessions: set[int]
) -> list[SavedExperimentAttempt]:
    by_hash = {saved.plan.plan_hash: saved for saved in plans}
    attempts: list[SavedExperimentAttempt] = []
    for case_id in reader.names("cases"):
        if not _CASE_ID.fullmatch(case_id):
            raise _refused(f"{named('cases/')} holds an entry that isn't a case's directory.")
        names = reader.names(f"cases/{case_id}")
        if set(names) - {"attempts", "normalized"}:
            raise _refused(f"{named(f'cases/{case_id}/')} holds an entry no case has.")
        for name in reader.names(f"cases/{case_id}/attempts"):
            if not _ATTEMPT_ID.fullmatch(name):
                raise _refused(
                    f"{named(f'cases/{case_id}/attempts/')} holds an entry that isn't an"
                    " attempt's directory."
                )
            attempt = _attempt(reader, case_id, uuid.UUID(name), by_hash, sessions)
            if attempt is not None:
                attempts.append(attempt)
    attempts.sort(key=lambda attempt: (attempt.session, attempt.sequence))
    for (session, sequence), count in Counter((a.session, a.sequence) for a in attempts).items():
        if count > 1:
            raise _refused(
                f"two attempts of session {session} have the same sequence, {sequence}, though a"
                " session starts its attempts one at a time."
            )
    return attempts


def _attempt(
    reader: _Reader,
    case_id: str,
    attempt_id: uuid.UUID,
    plans: Mapping[str, SavedPlan],
    sessions: set[int],
) -> SavedExperimentAttempt | None:
    """The attempt in this directory, or None when it has none of its records, as after a
    process killed before it wrote its first: there's no record of the attempt then."""
    directory = attempt_directory(case_id, attempt_id)
    names = reader.names(directory)
    if set(names) - set(reader.attempt_files):
        raise _refused(f"{named(directory + '/')} holds a file no attempt writes.")
    authentication, update, start, record = _records(reader, directory, names)
    present = [r for r in (authentication, update, start, record) if r is not None]
    if not present:
        return None
    _check_identity(present, case_id, attempt_id)
    _check_agreement(
        authentication,
        update,
        start,
        record,
        f"the records in {named(directory + '/')} don't agree",
    )
    first = present[0]
    saved = _placement(first, plans, sessions, directory)
    ranked = isinstance(saved.plan, PlanV1_3)
    _check_attempt_version(ranked, (update, start, record), names, directory)
    order = _RANKING_ATTEMPT_FILES if ranked else _ATTEMPT_FILES
    files = tuple(
        AttemptFile(
            role, StoredFile.of(f"{directory}/{name}", reader.require(f"{directory}/{name}"))
        )
        for name, role in order.items()
        if name in names
    )
    contents = {file.file.path: file.file for file in files}
    response = _response(reader, directory, names, start, record, contents)
    rank_response = (
        _rank_response(reader, directory, names, update, start, record) if ranked else None
    )
    decoded = reader.require(f"{directory}/{RESPONSE}") if RESPONSE in names else None
    return SavedExperimentAttempt(
        case_id=case_id,
        attempt_id=attempt_id,
        plan=saved.number,
        session=first.session,
        sequence=first.sequence,
        repeat_of=first.repeat_of,
        authentication=authentication,
        start=start,
        record=record,
        files=files,
        response=response,
        decoded_response=decoded,
        update=update,
        rank_response=rank_response,
    )


def _records(
    reader: _Reader, directory: str, names: Sequence[str]
) -> tuple[
    AuthenticationRecord | None,
    StartRecordV1_3 | None,
    AnyStart | None,
    AnyAttemptRecord | None,
]:
    """The attempt's authentication record, update record, start record, and attempt record, each
    checked against its schema version and its model, by that version, or None for each that its
    directory doesn't hold. `names` are its directory's."""

    def read[M: BaseModel](name: str, kind: str, models: Mapping[str, type[M]]) -> M | None:
        if name not in names:
            return None
        path = f"{directory}/{name}"
        content = reader.require(path)
        model = models.get(cast("str", _version(reader, content, path, kind)))
        if model is None:
            raise _refused(f"{named(path)} has no schema version a record of its kind has.")
        return reader.checks.record(model, content, path, kind)

    starts: dict[str, type[AnyStart]] = {"1.1.0": StartRecordV1_1, "1.3.0": StartRecordV1_3}
    records: dict[str, type[AnyAttemptRecord]] = {
        "1.1.0": AttemptRecordV1_1,
        "1.3.0": AttemptRecordV1_3,
    }
    return (
        read(AUTHENTICATION_RECORD, "authentication_record", {"1.0.0": AuthenticationRecord}),
        read(UPDATE_RECORD, "update_record", {"1.3.0": StartRecordV1_3}),
        read(START_RECORD, "start_record", starts),
        read(ATTEMPT_RECORD, "attempt_record", records),
    )


def _check_attempt_version(
    ranked: bool,
    records: tuple[StartRecordV1_3 | None, AnyStart | None, AnyAttemptRecord | None],
    names: Sequence[str],
    directory: str,
) -> None:
    """An attempt's records are the version an attempt under its plan writes: 1.3.0 under a plan
    with a ranking definition, and 1.1.0 under any other; and only the former writes the
    `rank_update`'s files and its update record."""
    expected = "1.3.0" if ranked else "1.1.0"
    if any(record is not None and record.schema_version != expected for record in records):
        raise _refused(
            f"the records in {named(directory + '/')} aren't the version an attempt under their"
            " plan writes: 1.3.0 under a plan with a ranking definition, and 1.1.0 under any"
            " other."
        )
    if not ranked and set(names) & _RANK_UPDATE_FILES:
        raise _refused(f"{named(directory + '/')} holds a file no attempt under its plan writes.")


def _check_identity(present: Sequence[_Record], case_id: str, attempt_id: uuid.UUID) -> None:
    """The attempt's records name the case and the attempt of its directory, and give it the
    same plan, place, and start."""
    records = f"the records in {named(attempt_directory(case_id, attempt_id) + '/')}"
    if any((r.case_id, r.attempt_id) != (case_id, attempt_id) for r in present):
        raise _refused(f"{records} name another attempt.")
    shared = ("trialfolio_version", "plan_hash", "session", "sequence", "repeat_of", "started_at")
    if len({tuple(getattr(r, field) for field in shared) for r in present}) > 1:
        raise _refused(f"{records} don't agree: they give it another plan, place, or start.")


def _placement(
    first: _Record, plans: Mapping[str, SavedPlan], sessions: set[int], directory: str
) -> SavedPlan:
    """The plan the attempt in `directory` ran under, as its first record names it: a plan of the
    experiment, which has the attempt's case, in a session of the experiment."""
    records = f"the records in {named(directory + '/')}"
    saved = plans.get(first.plan_hash)
    if saved is None:
        raise _refused(f"{records} name a plan the experiment doesn't have.")
    if first.case_id not in {case.case_id for case in saved.plan.cases}:
        raise _refused(f"{records} name a case their plan doesn't have.")
    if first.session not in sessions:
        raise _refused(f"{records} name a session the experiment doesn't have.")
    return saved


def _check_agreement(
    authentication: AuthenticationRecord | None,
    update: StartRecordV1_3 | None,
    start: AnyStart | None,
    record: AnyAttemptRecord | None,
    disagree: str,
) -> None:
    """The records agree with each other: the attempt record holds its start records' contents,
    and an attempt that authenticated wrote its authentication record first. An attempt that
    sends a definition wrote its update record before its `rank_update`, and before `started.json`,
    which holds the update record's values, and its exchanges, then the `rank_update`'s 200."""
    shared = set(StartRecordV1_3.model_fields) - {"operation", "exchanges"}
    if start is not None and record is not None:
        # Their exchanges then agree too: both name the same `authenticated_by`, and the models
        # hold an attempt that authenticated to one successful `POST /auth` exchange, first, and
        # one sent with another's token to none.
        fields = set(type(start).model_fields) - {"operation", "exchanges"}
        if record.model_dump(include=fields) != start.model_dump(include=fields):
            raise _refused(f"{disagree}: the attempt record doesn't hold its start record's.")
    if update is not None:
        _check_update(update, start, record, shared, disagree)
    elif isinstance(start, StartRecordV1_3) or (
        isinstance(record, AttemptRecordV1_3)
        and any(e.request == RANK_UPDATE_REQUEST for e in record.exchanges)
    ):
        raise _refused(
            f"{disagree}: the attempt sent its rank_update without the update record written"
            " before it."
        )
    opening = update if update is not None else start
    if opening is None and record is not None and record.authenticated_by is not None:
        raise _refused(f"{disagree}: the attempt record names a token, without a start record.")
    if opening is not None and (authentication is not None) != any(
        e.request == AUTHENTICATION_REQUEST for e in opening.exchanges
    ):
        raise _refused(
            f"{disagree}: an attempt authenticates exactly when it has its authentication record."
        )
    if (
        record is not None
        and authentication is None
        and any(e.request == AUTHENTICATION_REQUEST for e in record.exchanges)
    ):
        raise _refused(
            f"{disagree}: the attempt authenticated without writing its authentication record."
        )


def _check_update(
    update: StartRecordV1_3,
    start: AnyStart | None,
    record: AnyAttemptRecord | None,
    shared: set[str],
    disagree: str,
) -> None:
    """The update record of an attempt that sends a definition agrees with its other records: each
    names the request it comes before, the update record the `rank_update`, and `started.json`
    the backtest; `started.json` holds its values, and its exchanges, then the `rank_update`'s
    200; the attempt record holds its values, and both's exchanges, first; and an attempt record
    that shows its backtest sent, or possibly sent, has `started.json`, the last write before that
    send (sending a definition)."""
    if update.operation != "rank_update" or (
        isinstance(start, StartRecordV1_3) and start.operation != "screen_backtest"
    ):
        raise _refused(
            f"{disagree}: a start record doesn't name the request it comes before: the"
            f" rank_update in {UPDATE_RECORD}, and the screen backtest in {START_RECORD}."
        )
    if start is None and isinstance(record, AttemptRecordV1_3) and _backtest_sent(record):
        raise _refused(
            f"{disagree}: the attempt record shows that its backtest was sent, or may have been,"
            " without the start record written before it."
        )
    if start is not None and (
        start.model_dump(include=shared) != update.model_dump(include=shared)
        or start.exchanges[:-1] != update.exchanges
    ):
        raise _refused(
            f"{disagree}: the start record doesn't hold the update record's values, and its"
            " exchanges, then the rank_update's."
        )
    latest = start if start is not None else update
    if record is not None and (
        record.model_dump(include=shared) != update.model_dump(include=shared)
        or record.exchanges[: len(latest.exchanges)] != latest.exchanges
    ):
        raise _refused(f"{disagree}: the attempt record doesn't hold its start records'.")


def _backtest_sent(record: AttemptRecordV1_3) -> bool:
    """Whether the attempt record shows its backtest sent, or possibly sent: by its exchange, or
    as a resume records an attempt from `started.json` without a saved response, `unknown`, with
    the backtest's request and no exchange of it, as counting the requests counts it (sending a
    definition)."""
    return any(e.request == SCREEN_BACKTEST_REQUEST for e in record.exchanges) or (
        record.outcome == "unknown" and record.request is not None
    )


def _response(
    reader: _Reader,
    directory: str,
    names: Sequence[str],
    start: AnyStart | None,
    record: AnyAttemptRecord | None,
    files: Mapping[str, StoredFile],
) -> tuple[SavedResponse, bytes] | None:
    """The saved response the attempt record references, with each file it references checked;
    or, for a `running` attempt, the one its directory holds, with its request checked."""
    if record is not None:
        _check_references(record, directory, files)
        if record.response is None:
            return None
        return record.response, reader.require(record.response.path)
    if start is None:
        return None
    if REQUEST not in names:
        raise _refused(
            f"{named(directory + '/')} has a start record, but not the request.json written"
            " before it."
        )
    saved = [name for name in (RESPONSE, RESPONSE_RAW) if name in names]
    if len(saved) > 1:
        raise _refused(f"{named(directory + '/')} holds two saved responses.")
    if not saved:
        return None
    path = f"{directory}/{saved[0]}"
    content = reader.require(path)
    response = SavedResponse(
        path=path,
        artifact_id=artifact_id(content),
        form="decoded" if saved[0] == RESPONSE else "undecoded",
    )
    return response, content


def _rank_response(
    reader: _Reader,
    directory: str,
    names: Sequence[str],
    update: StartRecordV1_3 | None,
    start: AnyStart | None,
    record: AnyAttemptRecord | None,
) -> tuple[RankUpdateResponse, bytes] | None:
    """The `rank_update`'s saved response of an attempt that sends a definition, which its
    attempt record references, already checked; or, without an attempt record, the one its
    directory holds, with the `rank_update`'s request, written before its update record, checked,
    and, for a `running` attempt, its decoded response, saved before `started.json`."""
    if isinstance(record, AttemptRecordV1_3):
        saved = record.ranking_update.response
        return None if saved is None else (saved, reader.require(saved.path))
    held = [name for name in (RANK_UPDATE_RESPONSE_FILE, RANK_UPDATE_RESPONSE_RAW) if name in names]
    if update is None:
        if held:
            raise _refused(
                f"{named(directory + '/')} holds the rank_update's response, but not the update"
                " record written before its send."
            )
        return None
    if RANK_UPDATE_REQUEST_FILE not in names:
        raise _refused(
            f"{named(directory + '/')} has an update record, but not the"
            f" {RANK_UPDATE_REQUEST_FILE} written before it."
        )
    if len(held) > 1:
        raise _refused(f"{named(directory + '/')} holds two saved rank_update responses.")
    if start is not None and held != [RANK_UPDATE_RESPONSE_FILE]:
        raise _refused(
            f"{named(directory + '/')} has a start record, but not the {RANK_UPDATE_RESPONSE_FILE}"
            " saved before it."
        )
    if not held:
        return None
    path = f"{directory}/{held[0]}"
    content = reader.require(path)
    response = RankUpdateResponse(
        path=path,
        artifact_id=artifact_id(content),
        form="decoded" if held[0] == RANK_UPDATE_RESPONSE_FILE else "undecoded",
    )
    return response, content


def _check_references(
    record: AnyAttemptRecord, directory: str, files: Mapping[str, StoredFile]
) -> None:
    """Each file the attempt record references is one of `files`, its directory's, with the
    `artifact_id` it records: the `rank_update`'s too, for an attempt that sends a
    definition."""
    references: list[ArtifactReference] = []
    if record.request is not None:
        references.append(record.request)
    if record.response is not None:
        references.append(record.response)
    if isinstance(record, AttemptRecordV1_3):
        update = record.ranking_update
        references += [ref for ref in (update.request, update.response) if ref is not None]
    for reference in references:
        stored = files.get(reference.path)
        if stored is None:
            raise _refused(
                f"the attempt record in {named(directory + '/')} references a file that isn't in"
                " its directory."
            )
        if stored.artifact_id != reference.artifact_id:
            raise _refused(
                f"{named(reference.path)} doesn't match the artifact_id its attempt record gives"
                " it."
            )


def _check_authentication(attempts: Sequence[SavedExperimentAttempt]) -> None:
    """Each request was sent with a token that an attempt of its session obtained, itself or an
    earlier one, and that no 401 or 403 to an earlier request sent with it had dropped: a
    `rank_update`'s included."""
    by_id = {attempt.attempt_id: attempt for attempt in attempts}
    for attempt in attempts:
        opening = attempt.opening
        if opening is None:
            continue
        origin = by_id.get(opening.authenticated_by)
        if (
            origin is None
            or origin.session != attempt.session
            or origin.sequence > attempt.sequence
            or not _authenticated(origin)
        ):
            raise _refused(
                f"the request of {named(attempt.directory + '/')} was sent with a token no"
                " attempt of its session obtained before it."
            )
        for earlier in attempts:
            used = earlier.opening
            if (
                earlier.session == attempt.session
                and earlier.sequence < attempt.sequence
                and used is not None
                and used.authenticated_by == origin.attempt_id
                and _token_dropped(earlier)
            ):
                raise _refused(
                    f"the request of {named(attempt.directory + '/')} was sent with a token that"
                    " a 401 or 403 to an earlier request had dropped."
                )


def _authenticated(attempt: SavedExperimentAttempt) -> bool:
    opening = attempt.opening
    exchanges = (
        attempt.record.exchanges
        if attempt.record is not None
        else opening.exchanges
        if opening is not None
        else ()
    )
    return any(e.request == AUTHENTICATION_REQUEST and e.status == 200 for e in exchanges)


def _token_dropped(attempt: SavedExperimentAttempt) -> bool:
    if attempt.record is None:
        return False
    return any(
        e.request != AUTHENTICATION_REQUEST and e.status in _TOKEN_DROPPED
        for e in attempt.record.exchanges
    )


def _check_repeats(attempts: Sequence[SavedExperimentAttempt]) -> None:
    """An attempt that follows a possibly charged attempt of its case, by session and then
    sequence, names the latest such attempt in `repeat_of`, and no other attempt names one. No
    attempt follows its case's succeeded attempt: a complete case is never sent again."""
    by_case: dict[str, list[SavedExperimentAttempt]] = {}
    for attempt in attempts:
        by_case.setdefault(attempt.case_id, []).append(attempt)
    for group in by_case.values():
        latest: SavedExperimentAttempt | None = None
        succeeded = False
        for attempt in group:
            directory = named(attempt.directory + "/")
            if succeeded:
                raise _refused(
                    f"{directory} follows its case's succeeded attempt, and a complete case is"
                    " never sent again."
                )
            expected = None if latest is None else latest.attempt_id
            if attempt.repeat_of != expected:
                if attempt.repeat_of is None:
                    raise _refused(
                        f"{directory} was started after an attempt of its case whose request may"
                        " have been charged, without a confirmed repeat of it."
                    )
                raise _refused(
                    f"{directory} names in repeat_of an attempt that isn't its case's latest"
                    " whose request may have been charged."
                )
            if attempt.possibly_charged:
                latest = attempt
            succeeded = attempt.outcome == "succeeded"


def _tables(
    reader: _Reader,
    plans: Sequence[SavedPlan],
    attempts: Sequence[SavedExperimentAttempt],
    listed: Mapping[str, AnyArtifact],
    since: Sequence[str],
) -> dict[str, SavedTables]:
    tables: dict[str, SavedTables] = {}
    numbered = {saved.number: saved for saved in plans}
    for case_id in reader.names("cases"):
        names = reader.names(f"cases/{case_id}/normalized")
        if set(names) - {"metrics.csv", "settings.csv"}:
            raise _refused(f"{named(f'cases/{case_id}/normalized/')} holds a file no case has.")
        if not names:
            continue
        if "metrics.csv" not in names:
            settings_path = case_tables_path(case_id, SETTINGS_PATH)
            raise _refused(f"{named(settings_path)} is there without its metrics.csv.")
        attempt = _succeeded(attempts, case_id)
        saved = numbered[attempt.plan]
        metrics, metrics_rows, parser = _metrics(
            reader, saved.case(case_id), attempt, listed, since
        )
        settings, settings_rows = (
            _settings(reader, saved, case_id, listed) if "settings.csv" in names else (None, None)
        )
        tables[case_id] = SavedTables(
            metrics=metrics,
            metrics_rows=metrics_rows,
            settings=settings,
            settings_rows=settings_rows,
            parser_version=parser,
        )
    return tables


def _succeeded(attempts: Sequence[SavedExperimentAttempt], case_id: str) -> SavedExperimentAttempt:
    """The succeeded attempt of a case that has normalized tables, as only such a case does."""
    succeeded = [
        a
        for a in attempts
        if a.case_id == case_id and a.record is not None and a.record.outcome == "succeeded"
    ]
    if not succeeded:
        raise _refused(
            f"{named(f'cases/{case_id}/')} has normalized tables, but no succeeded attempt."
        )
    (attempt,) = succeeded
    return attempt


def _metrics(
    reader: _Reader,
    case: AnyPlanCase,
    attempt: SavedExperimentAttempt,
    listed: Mapping[str, AnyArtifact],
    since: Sequence[str],
) -> tuple[StoredFile, tuple[MetricsRow, ...], int]:
    """The case's `metrics.csv`, its rows, and the parser that wrote it, checked: it reads back,
    labeled with the case's `case_id`, holds the layout's metrics, and was drawn from the
    response of `attempt`, the case's succeeded attempt; and, when the latest manifest doesn't
    list it, it's what the installed parser writes from that response."""
    path = case_tables_path(case.case_id, METRICS_PATH)
    response = cast("tuple[SavedResponse, bytes]", attempt.response)
    content = reader.require(path)
    rows = reader.checks.table_rows(read_metrics_csv, content, path)
    if not labeled(rows, case.case_id):
        raise _refused(f"{named(path)} labels its rows with another case.")
    if not holds_each_metric(rows):
        raise _refused(
            f"{named(path)} doesn't hold one row for each of the layout's metrics, in order, each"
            " in the metric's unit."
        )
    if not drawn_from(rows, response[0].artifact_id):
        raise _refused(
            f"{named(path)} was drawn from another response than its case's succeeded attempt's."
        )
    if path in listed:
        return StoredFile.of(path, content), rows, _parser_of(response[0].path, listed)
    _check_parser(content, case, response, path, since)
    # A table no manifest lists is what the installed parser writes, as just checked, whichever
    # parser the latest manifest names for its response.
    return StoredFile.of(path, content), rows, PARSER_VERSION


def _settings(
    reader: _Reader, saved: SavedPlan, case_id: str, listed: Mapping[str, AnyArtifact]
) -> tuple[StoredFile, tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...]]:
    """The case's `settings.csv` and its rows, checked: it reads back, labeled with the case's
    `case_id`, holds the settings of `saved`, the plan its succeeded attempt ran under, and was
    drawn from that plan's configuration. A case of a plan 1.3.0 has `settings.csv` 1.1.0, whose
    weight rows are its plan's, each drawn from the plan's `definition.xml`, or, for a weight its
    ranking variant changes, its configuration (weight rows)."""
    path = case_tables_path(case_id, SETTINGS_PATH)
    content = reader.require(path)
    case = saved.case(case_id)
    entry = listed.get(path)
    expected = TABLES_SCHEMA_VERSION_V1_1 if saved.definition is not None else TABLES_SCHEMA_VERSION
    if entry is not None and entry.schema_version not in (None, expected):
        raise _refused(
            f"the latest manifest gives {named(path)} another version than its case's plan's:"
            " 1.1.0 for a plan with a ranking definition, and 1.0.0 for any other."
        )
    rows: tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...] = (
        reader.checks.table_rows(read_settings_csv_v1_1, content, path)
        if saved.definition is not None
        else reader.checks.table_rows(read_settings_csv, content, path)
    )
    if not labeled(rows, case_id):
        raise _refused(f"{named(path)} labels its rows with another case.")
    if not holds_each_setting(rows, case.settings):
        raise _refused(
            f"{named(path)} doesn't hold one row for each of its plan's settings, in order."
        )
    configuration = saved.configuration.artifact_id
    weights = [row for row in rows if isinstance(row, SettingsRowV1_1) and row.node is not None]
    others = [row for row in rows if row not in weights]
    if not drawn_from(others, configuration):
        raise _refused(
            f"{named(path)} was drawn from another configuration than that of the plan its case's"
            " attempt ran under."
        )
    if saved.definition is not None and (
        not isinstance(case, ExperimentPlanCaseV1_3)
        or not holds_each_weight(weights, case.settings)
        or not _drawn_as_written(weights, saved, case.case_key)
    ):
        raise _refused(
            f"{named(path)}'s weight rows aren't its case's definition's: each gives the weight its"
            " plan gives its node, drawn from the plan's definition.xml, or, for a weight its"
            " ranking variant changes, its configuration."
        )
    return StoredFile.of(path, content), rows


def _drawn_as_written(weights: Sequence[SettingsRowV1_1], saved: SavedPlan, case_key: str) -> bool:
    """Whether each weight row of the case `case_key`, of the plan 1.3.0 `saved`, was drawn from
    the file its weight comes from: the plan's `definition.xml`, or its configuration, for a
    weight the case's ranking variant changes, as the session that wrote it draws it (weight
    rows)."""
    path = saved.configuration.path
    read = cast("ExperimentConfigurationRead", saved.read)
    definition = cast("StoredFile", saved.definition)
    try:
        _, originals = experiment_original_values_v1_1(
            saved.configuration_content, path, read, case_key
        )
    except (TrialFolioError, ValueError):
        raise _refused(
            f"{named(path)} isn't a configuration this version reads for its case, so its weight"
            " rows' sources can't be checked."
        ) from None
    for row in weights:
        original = originals.get(cast("str", row.node))
        given = original is not None and original.in_definition
        source = definition.artifact_id if given else saved.configuration.artifact_id
        if row.source_artifact != source:
            return False
    return True


def _parser_of(response: str, listed: Mapping[str, AnyArtifact]) -> int:
    """The parser the latest manifest names for a response whose table it lists. Never for one
    whose table it doesn't list: it may name the parser that found the response invalid."""
    entry = listed.get(response)
    if entry is None or entry.source is None or entry.source.parser_version is None:
        return PARSER_VERSION
    return entry.source.parser_version


def _check_parser(
    content: bytes,
    case: AnyPlanCase,
    response: tuple[SavedResponse, bytes],
    path: str,
    since: Sequence[str],
) -> None:
    """A `metrics.csv` no manifest lists was written by a session that stopped before its end,
    and no record names its parser, so it must be what the installed parser writes."""
    try:
        expected = metrics_csv(case_metrics_rows(response[1], case, response[0]))
    except TrialFolioError:
        expected = None
    if content != expected:
        versions = ", ".join(sorted(set(since))) or "unknown"
        raise _refused(
            f"{named(path)}, which no session's manifest lists, isn't what this version's parser"
            " writes from its response, as after an upgrade whose parser reads it differently."
            " Resume the experiment first with the version of Trial Folio that wrote it, one of"
            f" those the sessions since the latest manifest record ({versions}), so that a"
            " session's manifest names its parser."
        )


def _missing(
    plans: Sequence[SavedPlan],
    attempts: Sequence[SavedExperimentAttempt],
    tables: Mapping[str, SavedTables],
) -> dict[str, MissingTables]:
    """For each case whose succeeded attempt has no `settings.csv`, what a resume writes: the
    response's rows, read from the bytes the check read, and its plan's original values, and,
    for a case of a plan 1.3.0, its weight rows' originals."""
    numbered = {saved.number: saved for saved in plans}
    missing: dict[str, MissingTables] = {}
    for attempt in attempts:
        saved_tables = tables.get(attempt.case_id)
        if attempt.outcome != "succeeded" or (
            saved_tables is not None and saved_tables.settings is not None
        ):
            continue
        response, content = cast("tuple[SavedResponse, bytes]", attempt.response)
        saved = numbered[attempt.plan]
        case = saved.case(attempt.case_id)
        rows: tuple[MetricsRow, ...] | None = None
        invalid: TrialFolioError | None = None
        if saved_tables is None:
            try:
                rows = case_metrics_rows(content, case, response)
            except TrialFolioError as error:
                invalid = error
        originals: Mapping[str, tuple[str, str]] = {}
        ranking: RankingOriginals | None = None
        if invalid is None:
            originals, ranking = _originals(saved, case.case_key)
        missing[attempt.case_id] = MissingTables(
            attempt=attempt,
            case=case,
            configuration=saved.configuration,
            originals=MappingProxyType(originals),
            ranking=ranking,
            response=response,
            content=content,
            metrics_rows=rows,
            invalid=invalid,
        )
    return missing


def _originals(
    saved: SavedPlan, case_key: str
) -> tuple[Mapping[str, tuple[str, str]], RankingOriginals | None]:
    """The original values of the case `case_key` in the configuration of the plan `saved`, and,
    for a plan 1.3.0, its weight rows' originals, with the plan's `definition.xml`."""
    path = saved.configuration.path
    try:
        if saved.read is not None and saved.definition is not None:
            originals, weights = experiment_original_values_v1_1(
                saved.configuration_content, path, saved.read, case_key
            )
            return originals, RankingOriginals(weights, saved.definition)
        return experiment_original_values(saved.configuration_content, path, case_key), None
    except (TrialFolioError, ValueError):
        raise _refused(
            f"{named(path)} isn't a configuration this version reads for its case, so the tables a"
            " stopped run didn't write can't be written."
        ) from None


def _metadata(response: SavedResponse | RankUpdateResponse, content: bytes) -> ProviderMetadata:
    """`cost` and `quotaRemaining` from the top level of a saved decoded response, as the
    attempt that saved it would have recorded them."""
    if response.form == "undecoded":
        return ProviderMetadata(cost=None, quota_remaining=None)
    try:
        payload: object = json.loads(content)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return ProviderMetadata(cost=None, quota_remaining=None)
    if not isinstance(payload, dict):
        return ProviderMetadata(cost=None, quota_remaining=None)
    fields = cast("dict[str, object]", payload)
    return ProviderMetadata(
        cost=_count(fields.get("cost")), quota_remaining=_count(fields.get("quotaRemaining"))
    )


def _count(value: object) -> int | None:
    # A bool is an int in Python, and never a count.
    return value if type(value) is int and value >= 0 else None


def _authentications(exchanges: Sequence[Exchange]) -> int:
    return sum(exchange.request == AUTHENTICATION_REQUEST for exchange in exchanges)


# Refusing


def _refused(problem: str) -> TrialFolioError:
    return TrialFolioError(
        "input.not_a_run",
        f"The output directory doesn't hold a complete, consistent Trial Folio experiment:"
        f" {problem} Nothing was sent or written. Restore the experiment's records from a"
        " complete copy, or run the configuration into a new output directory.",
    )


def _unknown_version(path: str, problem: str) -> TrialFolioError:
    return TrialFolioError(
        "artifact.unknown_schema_version",
        f"Trial Folio can't read {named(path)} in the output directory: {problem} Resume the"
        " experiment with a version of Trial Folio that has one. Nothing was sent or written.",
    )


_CHECKS: Final = RecordChecks(
    refused=_refused,
    unknown_version=_unknown_version,
    readable=_READABLE,
    manifest="the latest manifest",
)
"""The checks `read_experiment` shares with a run's reader, which refuse as it does."""

_RANKING_CHECKS: Final = RecordChecks(
    refused=_refused,
    unknown_version=_unknown_version,
    readable=_RANKING_READABLE,
    manifest="the latest manifest",
)
"""The same, reading an experiment with a ranking definition too, as a read with `ranking`
does."""
