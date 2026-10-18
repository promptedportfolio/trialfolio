"""What a screen run, an experiment, and a review share in writing their manifests, and in ending
without one (docs/contracts.md, source artifacts, artifact storage, endings that decide the error
code, and interrupts).

- **The manifest's parts.** The source records of a configuration, and of Portfolio123's request
  and response (INV-04), and the parsers, the capabilities, and the reproducibility, which a
  run's manifest and an experiment's record the same way. Each kind keeps its own model of an
  artifact's entry, whose schema definitions differ. From 0.4.0, a manifest with a ranking
  definition, run manifest 1.1.0 and experiment manifest 1.1.0, also gives the source records
  of the definition's copy and of the `rank_update`'s request and response (a run with a
  ranking definition), in the source record of version 1.1.0.
- **Writing the manifest.** `ManifestFile` writes it last, and discards it when its write fails,
  an interrupt included, if the store had published it already, so an output whose command
  failed never reads as complete. It says which of three states the manifest is in, in the
  words of each kind of output, for an ending's message.
- **Endings without a manifest.** After the claim, an interrupt or a storage failure ends the
  output without its manifest, and is the error the command reports, rather than an exception
  that propagates: `EndingWithoutManifest` catches either, and lets every other exception
  through. So does an attempt whose attempt record wasn't written, which no manifest can account
  for (`ends_without_manifest`). `running_detail` says what such an attempt's start record means
  for its request.
- **Writing a record.** `model_json` gives a record's bytes, as Trial Folio writes each of its
  JSON records, and `utc` checks the clock's time, which every record holds in UTC.

Nothing here logs, so a log event keeps the `component` of the module that logs it.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import TracebackType
from typing import Final, Literal, Self

from pydantic import BaseModel

from trialfolio.contracts.experiment_plan import ExperimentPlanCase, ExperimentPlanCaseV1_3
from trialfolio.contracts.manifest import (
    Capabilities,
    ExternalReference,
    ParserVersion,
    Reproducibility,
    SourceRecord,
    SourceRecordV1_1,
)
from trialfolio.contracts.plan import PlanCase, PlanCaseV1_2
from trialfolio.errors import ErrorCode, TrialFolioError, interrupted
from trialfolio.normalization import LAYOUT, LAYOUT_VERSION, PARSER_VERSION
from trialfolio.storage import ArtifactStore, StoredFile

type ProviderRole = Literal["provider_request", "provider_response", "provider_response_undecoded"]
"""The role of a file of Portfolio123's that an attempt saves: its request or its response."""

type RankUpdateRole = Literal[
    "rank_update_request", "rank_update_response", "rank_update_response_undecoded"
]
"""The role of a `rank_update`'s file that an attempt saves: its request or its response."""

RANK_UPDATE_ROLES: Final[tuple[RankUpdateRole, ...]] = (
    "rank_update_request",
    "rank_update_response",
    "rank_update_response_undecoded",
)

RANKING_DEFINITION_FORMAT: Final = "ranking-definition"
"""The source format of a definition's copy, `definition.xml`, at version 1 (artifact storage)."""

_RANK_UPDATE_FORMATS: Final[dict[RankUpdateRole, str]] = {
    "rank_update_request": "p123api-rank-update-request",
    "rank_update_response": "p123api-rank-update",
    "rank_update_response_undecoded": "p123api-rank-update-response_undecoded",
}

PROVIDER_ROLES: Final[tuple[ProviderRole, ...]] = (
    "provider_request",
    "provider_response",
    "provider_response_undecoded",
)

_WITHOUT_MANIFEST: Final[tuple[ErrorCode, ...]] = ("command.interrupted", "storage.write_failed")
"""The error codes of the endings that leave an output without its manifest, whatever else
happened: an interrupt's and a storage failure's (endings that decide the error code)."""


# The manifest's parts


def configuration_source(file_format: str, version: str, acquired_at: datetime) -> SourceRecord:
    """The source record of the configuration an output holds, which the user supplied, in
    `file_format` at its schema `version`. It's acquired at `acquired_at`: when the command
    started, or, for an experiment, when the plan it gives was recorded."""
    return SourceRecord(
        acquired_at=acquired_at,
        format=file_format,
        format_version=version,
        parser_version=None,
        provenance="user_supplied",
        operation=None,
    )


def provider_source(
    role: ProviderRole, *, started_at: datetime, ended_at: datetime
) -> SourceRecord:
    """The source record of a file of Portfolio123's that an attempt saved, which `started_at`
    and `ended_at`, the attempt's times, date: the request was written just before the attempt's
    start record, and the response was saved just before its attempt record."""
    decoded = role == "provider_response"
    return SourceRecord(
        acquired_at=started_at if role == "provider_request" else ended_at,
        format=LAYOUT if decoded else f"{LAYOUT}-{role.removeprefix('provider_')}",
        format_version=str(LAYOUT_VERSION),
        parser_version=PARSER_VERSION if decoded else None,
        provenance="verified",
        operation="screen_backtest",
    )


def source_v1_1(source: SourceRecord) -> SourceRecordV1_1:
    """A source record of 1.0.0's, as a manifest with a ranking definition holds it."""
    return SourceRecordV1_1.model_validate(source.model_dump())


def definition_source(acquired_at: datetime) -> SourceRecordV1_1:
    """The source record of a definition's copy, `definition.xml`, from a file the configuration
    names, which the user supplied: the format `ranking-definition`, version 1, which no parser
    reads, acquired with the configuration, at `acquired_at`."""
    return SourceRecordV1_1(
        acquired_at=acquired_at,
        format=RANKING_DEFINITION_FORMAT,
        format_version="1",
        parser_version=None,
        provenance="user_supplied",
        operation=None,
    )


def snapshot_definition_source(taken_at: datetime) -> SourceRecordV1_1:
    """The source record of the copy of a snapshot's definition, `definition.xml`: the format
    `ranking-definition`, version 1, which no parser reads, `verified`, from the `rank_get` that
    read it, acquired when the snapshot was taken, at `taken_at`, its record's `taken_at`
    (artifact storage, a run with a ranking definition; ranking snapshot output)."""
    return SourceRecordV1_1(
        acquired_at=taken_at,
        format=RANKING_DEFINITION_FORMAT,
        format_version="1",
        parser_version=None,
        provenance="verified",
        operation="rank_get",
    )


def rank_update_source(
    role: RankUpdateRole, *, started_at: datetime, ended_at: datetime
) -> SourceRecordV1_1:
    """The source record of a `rank_update`'s file that an attempt saved, dated as a backtest's
    is by the attempt's times: its request when the attempt started, and its response when it
    ended. No parser reads either (`p123api-rank-update` version 1)."""
    return SourceRecordV1_1(
        acquired_at=started_at if role == "rank_update_request" else ended_at,
        format=_RANK_UPDATE_FORMATS[role],
        format_version="1",
        parser_version=None,
        provenance="verified",
        operation="rank_update",
    )


def parsers(versions: Iterable[int] = ()) -> tuple[ParserVersion, ...]:
    """The parsers a manifest lists, for the response layout: each of `versions`, the parsers
    that wrote the output's tables, once, in order; or the installed parser, when none is
    given."""
    return tuple(
        ParserVersion(layout=LAYOUT, layout_version=LAYOUT_VERSION, parser_version=version)
        for version in sorted(set(versions)) or [PARSER_VERSION]
    )


def capabilities(*, series: bool) -> Capabilities:
    """What a run or an experiment can show. `series` is whether a saved response holds the
    per-period series, `results.rows` and `chart`, which Trial Folio preserves without
    normalizing them. Neither statistical validation nor trading readiness is assessed."""
    return Capabilities(
        return_series="source_only" if series else "absent",
        statistical_validation="not_assessed",
        trading_readiness="not_assessed",
    )


def reproducibility(
    cases: Iterable[PlanCase | ExperimentPlanCase | PlanCaseV1_2 | ExperimentPlanCaseV1_3],
) -> Reproducibility:
    """Whether the cases can be reproduced from what the output holds: each setting of theirs
    that refers to something in the account that no snapshot records, once, in the order the
    cases first give it, and `incomplete` when there's any."""
    references: dict[str, ExternalReference] = {}
    for case in cases:
        for row in case.settings:
            if "not_snapshotted" in row.flags:
                references.setdefault(
                    row.setting, ExternalReference(setting=row.setting, snapshotted=False)
                )
    return Reproducibility(
        status="incomplete" if references else "complete",
        external_references=tuple(references.values()),
    )


# Writing the manifest


@dataclass(frozen=True)
class ManifestDetails:
    """What an ending's message says of an output's manifest, in each kind of output's own
    words, for each state `ManifestFile.detail` gives."""

    written: str
    """The manifest was written, so the output is complete."""
    left: str
    """A write of the manifest failed after the store published it, and it couldn't be removed,
    so the output reads as complete although its command failed."""
    missing: str
    """There's no manifest, so the output is incomplete."""


class ManifestFile:
    """The manifest of one output, at `path` in the output directory of `store`. It's written
    last, once. Its properties stay readable whatever happens, so a command whose write of it
    failed still knows whether the output reads as complete."""

    def __init__(self, store: ArtifactStore, path: str, details: ManifestDetails) -> None:
        """Writes nothing."""
        self._store = store
        self._path = path
        self._details = details
        self._written: StoredFile | None = None
        self._left = False
        """Whether a manifest whose write failed couldn't be discarded."""

    @property
    def written(self) -> StoredFile | None:
        """The manifest's file, once it's written: the output is then complete."""
        return self._written

    @property
    def detail(self) -> str:
        """What the manifest's state means for the output, for an ending's message."""
        if self._written is not None:
            return self._details.written
        if self._left:
            return self._details.left
        return self._details.missing

    def write(self, manifest: BaseModel) -> StoredFile:
        """Writes the manifest. A write that fails, an interrupt or an unexpected exception
        included, discards the file if the store published it before the failure, which the
        store does only while the file holds exactly the failed write's bytes, and raises again.
        A file it can't remove is left, and `detail` says so."""
        data = model_json(manifest)
        try:
            self._written = self._store.write(self._path, data)
        except BaseException:
            self._written = None
            try:
                self._store.discard(self._path, data)
            except TrialFolioError:
                self._left = True
            raise
        return self._written


# Endings without a manifest


class EndingWithoutManifest:
    """A context manager for the steps after the claim that end with the output's manifest. When
    an interrupt or a storage failure ends them, it keeps their `error`, the one the command
    reports: `command.interrupted`, whose message ends "after `after`" when given, such as "the
    attempt ended", or the storage failure, `storage.write_failed`. The caller then appends what
    the records say, for an ending without a manifest. Any other exception propagates."""

    def __init__(self, *, after: str | None = None) -> None:
        self._after = after
        self.error: TrialFolioError | None = None
        """The error of the ending without a manifest, once one ended the steps."""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        ending: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if isinstance(ending, KeyboardInterrupt):
            self.error = interrupted(after=self._after)
            return True
        if isinstance(ending, TrialFolioError) and ending.code == "storage.write_failed":
            self.error = ending
            return True
        return False


def ends_without_manifest(*, recorded: bool, error: TrialFolioError | None) -> bool:
    """Whether an attempt's ending leaves the output without its manifest: when its attempt
    record wasn't written, since a manifest can't account for an attempt whose start record
    reads as running, whatever stopped the write; and when an interrupt or a storage failure
    decided its error code."""
    return not recorded or (error is not None and error.code in _WITHOUT_MANIFEST)


def updating_detail(attempt: str | None = None) -> str:
    """What the update record of an attempt that sends a definition, without its backtest's start
    record or its attempt record, says of its two requests, for an ending's message: the
    `rank_update` may have been sent and charged, and the backtest wasn't. `attempt` is as for
    `running_detail`."""
    of, record = ("", "the attempt's") if attempt is None else (f" of {attempt}", "its")
    return (
        f"The rank_update request{of}, which writes the case's ranking definition into"
        f" ApiRankingSystem, may have been sent, and may have been charged: {record} update record"
        " was written, and its screen backtest request wasn't sent. Trial Folio never retries it"
        " automatically."
    )


def running_detail(
    attempt: str | None = None, *, ranking: bool = False, name: str = "screen backtest request"
) -> str:
    """What the start record of an attempt without its attempt record says of its request, for
    an ending's message: it may have been sent and charged. `attempt` names the attempt, such as
    "the attempt under way", where the output has several; without it, it's a run's one
    attempt, or a snapshot's, whose request `name` names, as "rank_get request". With `ranking`,
    for an attempt that sends a definition, it says what each of its two requests did: its
    backtest's start record follows only its `rank_update`'s 200, so the `rank_update` reached
    Portfolio123 (sending a definition)."""
    of, record = ("", "the attempt's") if attempt is None else (f" of {attempt}", "its")
    if not ranking:
        return (
            f"The {name}{of} may have been sent, and may have been charged: {record} start record"
            " reads as running. Trial Folio never retries it automatically."
        )
    return (
        f"The rank_update request{of}, which writes the case's ranking definition into"
        " ApiRankingSystem, reached Portfolio123, and may have been charged. Its screen backtest"
        f" request may have been sent, and may have been charged: {record} start record reads as"
        " running. Trial Folio never retries either automatically."
    )


# Writing a record


def model_json(model: BaseModel) -> bytes:
    """A record's bytes, as Trial Folio writes each of its JSON records: indented by two spaces,
    with a final newline, in UTF-8."""
    return (model.model_dump_json(indent=2) + "\n").encode("utf-8")


def utc(moment: datetime) -> datetime:
    """`moment`, a time the clock gave, once it's checked as UTC. Raises `ValueError` for any
    other offset, or none."""
    if moment.utcoffset() != timedelta(0):
        raise ValueError("the clock must give UTC times")
    return moment
