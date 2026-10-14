"""A ranking snapshot's own records (docs/contracts.md, ranking snapshot output): its plan, its
record, and its manifest, each schema version 1.0.0, a schema of its own.

`trialfolio run` of a ranking snapshot configuration reads the system it names with one
`rank_get`, under its own plan and approval, and writes nothing to the account. Its directory
holds the plan, `plan.json`; the configuration's copy; its attempt, whose start and attempt
records are version 1.2.0, with no case (`trialfolio.contracts.attempt`); the system's XML,
`definition.xml`; the snapshot record, `snapshot.json`; and the snapshot manifest,
`manifest.json`, written last.

- `RankingSnapshotPlan`: the plan, with the system's name, its one `rank_get`, and no case.
- `RankingSnapshotRecord`: `snapshot.json`, the system as `rank_get` returned it.
- `RankingSnapshotManifest`: the manifest, `artifact_type: ranking-snapshot`.

Whether a snapshot can be a ranking is checked each time a configuration names it, by the rules
of the Trial Folio that reads it, not here.
"""

import re
from collections import Counter
from datetime import date
from typing import Annotated, Final, Literal, Self, TypedDict

from pydantic import ConfigDict, Field, model_validator, with_config

from trialfolio.contracts.common import (
    UUID4_PATTERN,
    Approval,
    AttemptId,
    ContractModel,
    Count,
    ErrorDetail,
    IntegerOnly,
    LicenseId,
    NonEmptyText,
    RelativePath,
    SemanticVersion,
    Sha256Digest,
    TransportVersions,
    UtcDatetime,
    WrapperVersions,
    check_outcome,
    require_unique,
)
from trialfolio.contracts.manifest import (
    AttemptCounts,
    ParserVersion,
    SourceRecordV1_1,
    check_ranking_artifact,
)
from trialfolio.contracts.plan import Budget, DataCategory, DocumentedSource, RetryPolicy
from trialfolio.contracts.ranking_snapshot_configuration import RANKING_SNAPSHOT_SCHEMA_VERSIONS

RANK_GET_COST_SOURCE: Final = DocumentedSource(
    title="API functions: Rank",
    url="https://portfolio123.customerly.help/en/articles/43323-api-rank",
    checked=date(2026, 10, 12),
)
"""Where `rank_get`'s documented cost, 1 credit, is documented, and the date it was checked
(ranking snapshot output)."""

SNAPSHOT_BUDGET: Final = Budget(
    provider_requests=1,
    credits_per_request=1,
    credits_per_request_source=RANK_GET_COST_SOURCE,
    credits=1,
    authentication_calls=1,
)
"""A snapshot plan's budget: one `rank_get`, at its documented cost, 1 credit, and one
authentication call."""


class RankGetParams(ContractModel):
    """The params p123api's `rank_get` sends as the query of `GET /rank`: the system's name."""

    name: NonEmptyText


class RankGetRequest(ContractModel):
    """A snapshot's one request, the `rank_get` that reads the system it names."""

    operation: Literal["rank_get"]
    params: RankGetParams


class SnapshotDataSent(ContractModel):
    """A category of data a snapshot's request sends: the credentials, and the system's name, as
    `strategy_definition`. It sends no backtest settings."""

    category: DataCategory
    recipient: Literal["Portfolio123"]
    via: Literal["p123api"]
    settings: tuple[Literal["system"], ...]


_SNAPSHOT_DATA_SENT: Final = (("credentials", ()), ("strategy_definition", ("system",)))


class RankingSnapshotPlan(ContractModel):
    """A ranking snapshot's plan: the system its configuration names, its one `rank_get`, the
    budget, the retry policy, and the data sent. It has no title, purpose, or cases. Execution
    requires its `plan_hash` as approval (ranking snapshot output)."""

    schema_version: Literal["1.0.0"]
    trialfolio_version: SemanticVersion
    canonicalization_version: Annotated[Literal[1], IntegerOnly]
    provider_wrapper: WrapperVersions
    transport: TransportVersions
    system: NonEmptyText
    """The configuration's `system`, which is sent."""
    requests: tuple[RankGetRequest]
    budget: Budget
    """One provider request, at 1 credit, `rank_get`'s documented cost, and one authentication
    call."""
    retry_policy: RetryPolicy
    data_sent: tuple[SnapshotDataSent, SnapshotDataSent]
    """`credentials`, then `strategy_definition`, which carries `system`."""
    plan_hash: Sha256Digest

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.requests[0].params.name != self.system:
            raise ValueError("the rank_get's name is the plan's system")
        if self.budget != SNAPSHOT_BUDGET:
            raise ValueError(
                "a snapshot's budget is one rank_get, at its documented cost of 1 credit, from "
                "the Rank API page checked 2026-10-12, and one authentication call"
            )
        sent = tuple((entry.category, entry.settings) for entry in self.data_sent)
        if sent != _SNAPSHOT_DATA_SENT:
            raise ValueError(
                "a snapshot sends its credentials, then the system's name, as strategy_definition"
            )
        return self


class SnapshotSystem(ContractModel):
    """The ranking system as `rank_get` returned it, exactly as Portfolio123 gave its fields,
    with `verified` provenance."""

    name: str
    """The response's `name`, recorded as it is, even when it isn't the one requested."""
    id: int
    ranking_method: int
    """The response's `rankingMethod`, as the integer Portfolio123 gave."""
    currency: str
    type: str


class RankingSnapshotRecord(ContractModel):
    """The snapshot record, `snapshot.json`: the system a snapshot read, when, under which
    attempt and plan, and its files. It doesn't say whether the definition can be a ranking:
    that's checked each time a configuration names the snapshot."""

    schema_version: Literal["1.0.0"]
    trialfolio_version: SemanticVersion
    requested: NonEmptyText
    """The configuration's `system`."""
    system: SnapshotSystem
    taken_at: UtcDatetime
    """When the response arrived: the attempt's `ended_at`."""
    attempt_id: AttemptId
    plan_hash: Sha256Digest
    """The plan the snapshot was read under."""
    definition: Sha256Digest
    """The `artifact_id` of `definition.xml`."""
    response: Sha256Digest
    """The `artifact_id` of the saved response."""


SnapshotArtifactRole = Literal[
    "plan",
    "configuration",
    "start_record",
    "attempt_record",
    "provider_request",
    "provider_response",
    "provider_response_undecoded",
    "ranking_definition",
    "ranking_snapshot_record",
]

_SNAPSHOT_SOURCE_ROLES: Final[frozenset[SnapshotArtifactRole]] = frozenset(
    {
        "configuration",
        "provider_request",
        "provider_response",
        "provider_response_undecoded",
        "ranking_definition",
    }
)

_ATTEMPT = rf"attempts/{UUID4_PATTERN}/"

SNAPSHOT_ROLE_PATHS: Final[dict[str, re.Pattern[str]]] = {
    "plan": re.compile(r"plan\.json"),
    "configuration": re.compile(r"configuration\.yaml"),
    "start_record": re.compile(rf"{_ATTEMPT}started\.json"),
    "attempt_record": re.compile(rf"{_ATTEMPT}attempt\.json"),
    "provider_request": re.compile(rf"{_ATTEMPT}request\.json"),
    "provider_response": re.compile(rf"{_ATTEMPT}response\.json"),
    "provider_response_undecoded": re.compile(rf"{_ATTEMPT}response\.raw"),
    "ranking_definition": re.compile(r"definition\.xml"),
    "ranking_snapshot_record": re.compile(r"snapshot\.json"),
}
"""Where the file of each role is in a snapshot's directory (ranking snapshot output)."""

_SNAPSHOT_SOURCES: Final[dict[str, tuple[str, tuple[str, ...], int | None, str | None]]] = {
    "configuration": (
        "ranking-snapshot-configuration",
        RANKING_SNAPSHOT_SCHEMA_VERSIONS,
        None,
        None,
    ),
    "provider_request": ("p123api-rank-get-request", ("1",), None, "rank_get"),
    "provider_response": ("p123api-rank-get", ("1",), 1, "rank_get"),
    "provider_response_undecoded": (
        "p123api-rank-get-response_undecoded",
        ("1",),
        None,
        "rank_get",
    ),
}
"""Each source artifact's format, its format versions, its parser version, and its provider
operation, but the definition's copy, which a run's manifest checks too. The configuration's
format version is its schema version, and each of the `rank_get`'s files is version 1."""

_SNAPSHOT_PARSERS: Final = (
    ParserVersion(layout="p123api-rank-get", layout_version=1, parser_version=1),
)
"""A snapshot's parsers: the one that reads its `rank_get`'s response, as its source record
names it (ranking snapshot output)."""


class SnapshotArtifact(ContractModel):
    """One file of a snapshot, by path, content address, and role."""

    path: RelativePath
    artifact_id: Sha256Digest
    size: Count
    role: SnapshotArtifactRole
    schema_version: SemanticVersion | None
    """The file's schema version, for files that have one."""
    source: SourceRecordV1_1 | None
    """Given exactly for source artifacts."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.source is None) == (self.role in _SNAPSHOT_SOURCE_ROLES):
            raise ValueError("source must be given exactly for source artifacts")
        if not SNAPSHOT_ROLE_PATHS[self.role].fullmatch(self.path):
            raise ValueError(f"a file of the role {self.role} isn't at this path")
        if self.role == "ranking_definition" and (
            self.source is None or self.source.operation != "rank_get"
        ):
            raise ValueError("a snapshot's definition comes from its rank_get")
        check_ranking_artifact(self.role, self.path, self.schema_version, self.source)
        expected = _SNAPSHOT_SOURCES.get(self.role)
        if expected is not None and self.source is not None:
            format_, versions, parser, operation = expected
            provenance = "user_supplied" if self.role == "configuration" else "verified"
            found = (
                self.source.format,
                self.source.parser_version,
                self.source.operation,
                self.source.provenance,
            )
            if (
                found != (format_, parser, operation, provenance)
                or self.source.format_version not in versions
            ):
                raise ValueError(
                    f"a file of the role {self.role} is the format {format_}, version "
                    f"{' or '.join(versions)}, with {provenance} provenance"
                )
        return self


@with_config(ConfigDict(strict=True, extra="forbid"))
class SnapshotOptions(TypedDict):
    """The run's options. Neither the configuration's path nor `--out` is recorded, because a
    path can name the user."""

    approve: Sha256Digest | None
    """`--approve`, as given."""
    json: bool


class SnapshotCommandRecord(ContractModel):
    """The command that took the snapshot, its non-secret options, and when it started."""

    name: Literal["run"]
    options: SnapshotOptions
    started_at: UtcDatetime


class SnapshotCounts(ContractModel):
    """The snapshot's counts."""

    attempts: AttemptCounts
    provider_requests: Annotated[int, Field(ge=0, le=1)]
    """The `rank_get` sent, when it may have reached Portfolio123."""
    retries: Annotated[Literal[0], IntegerOnly]
    """Trial Folio never resends a request on its own."""
    cost: Count | None
    """The credits Portfolio123 reported charging; null when it reported none."""


class RankingSnapshotManifest(ContractModel):
    """The snapshot manifest, `manifest.json` with `artifact_type: ranking-snapshot`, written
    last: a run's manifest, without capabilities or reproducibility, since a snapshot holds no
    result or series and has no settings. A synthetic snapshot, which only the core takes, with
    the demo's client, has no command and the approval `not_required`, and no configuration can
    name it as its ranking."""

    schema_version: Literal["1.0.0"]
    artifact_type: Literal["ranking-snapshot"]
    trialfolio_version: SemanticVersion
    created_at: UtcDatetime
    command: SnapshotCommandRecord | None
    """Null for a synthetic snapshot, which no command takes."""
    synthetic: bool
    """True exactly for a snapshot taken with the demo's client, which sends nothing and answers
    `rank_get` with an invented system. Its system, definition, and attempt are invented."""
    plan_hash: Sha256Digest
    approval: Approval
    """`interactive` or `option`; `not_required` exactly for a synthetic snapshot."""
    outcome: Literal["completed", "failed"]
    """`completed` once `snapshot.json` is written, and `failed` otherwise."""
    error: ErrorDetail | None
    """Null exactly when the outcome is `completed`."""
    artifacts: tuple[SnapshotArtifact, ...]
    """Every file but the manifest itself and the logs."""
    parsers: Annotated[tuple[ParserVersion, ...], Field(min_length=1)]
    """`p123api-rank-get`, layout version 1, parser version 1."""
    license_id: LicenseId
    notice_version: NonEmptyText
    counts: SnapshotCounts

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.approval == "not_required") != self.synthetic:
            raise ValueError("approval is not_required exactly for a synthetic snapshot")
        if self.synthetic and self.command is not None:
            raise ValueError("no trialfolio command takes a synthetic snapshot: the core does")
        if not self.synthetic and self.command is None:
            raise ValueError("a snapshot that isn't synthetic names the command that took it")
        check_outcome(self.outcome, self.error)
        require_unique(tuple(artifact.path for artifact in self.artifacts), "artifact paths")
        if self.parsers != _SNAPSHOT_PARSERS:
            raise ValueError(
                "a snapshot's parsers are p123api-rank-get, layout version 1, parser version 1, "
                "and no other"
            )
        roles = Counter(artifact.role for artifact in self.artifacts)
        if roles["plan"] != 1 or roles["configuration"] != 1:
            raise ValueError("a snapshot lists its plan and its configuration")
        written = (roles["ranking_definition"], roles["ranking_snapshot_record"])
        if written not in ((0, 0), (1, 1)) or (written == (1, 1)) != (self.outcome == "completed"):
            raise ValueError(
                "a snapshot is completed exactly when it lists its definition.xml and its "
                "snapshot.json, and otherwise lists neither"
            )
        return self
