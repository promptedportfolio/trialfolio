"""The run manifest, `manifest.json` with `artifact_type: run`, schema version 1.0.0
(docs/contracts.md, artifact storage). It's written last: without one, a run is incomplete.

Version 1.1.0, `RunManifestV1_1`, is a run's whose ranking is a definition: 1.0.0's fields, with
the roles of the files such a run adds, their source records, and a run the core writes with the
demo's client, which is synthetic, with no command (a run with a ranking definition).
"""

from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from trialfolio.contracts.common import (
    CommandOutcome,
    ContractModel,
    Count,
    ErrorDetail,
    LicenseId,
    NonEmptyText,
    NotAssessed,
    Provenance,
    RelativePath,
    SemanticVersion,
    SettingName,
    Sha256Digest,
    UtcDatetime,
    check_outcome,
    require_unique,
)

ArtifactRole = Literal[
    "plan",
    "configuration",
    "start_record",
    "attempt_record",
    "provider_request",
    "provider_response",
    "provider_response_undecoded",
    "metrics",
    "settings",
    "report",
]

SOURCE_ROLES: frozenset[ArtifactRole] = frozenset(
    {"configuration", "provider_request", "provider_response", "provider_response_undecoded"}
)
"""The roles of source artifacts, which carry a source record (INV-04, source artifacts)."""


class CommandRecord(ContractModel):
    """The command that wrote the run, its non-secret options, and when it started."""

    name: Literal["run", "demo"]
    options: dict[NonEmptyText, str | bool | None]
    """The command-line options as given, by name, such as `out` and `approve`."""
    started_at: UtcDatetime


class SourceRecord(ContractModel):
    """What makes a file a source artifact: when and how it was acquired, and how it's read."""

    acquired_at: UtcDatetime
    format: NonEmptyText
    """The source format, such as `screen-configuration` or `p123api-screen-backtest`."""
    format_version: NonEmptyText
    parser_version: Annotated[int, Field(ge=1)] | None
    """The version of the adapter that interpreted it; null when nothing interpreted it."""
    provenance: Provenance
    operation: Literal["screen_backtest"] | None
    """The provider operation that produced it; null for a file the user wrote."""


class ManifestArtifact(ContractModel):
    """One file of the run, by path, content address, and role."""

    path: RelativePath
    artifact_id: Sha256Digest
    size: Count
    role: ArtifactRole
    schema_version: SemanticVersion | None
    """The file's schema version, for files that have one, such as the normalized tables."""
    source: SourceRecord | None
    """Given exactly for source artifacts."""

    @model_validator(mode="after")
    def _source_roles(self) -> Self:
        if (self.source is None) == (self.role in SOURCE_ROLES):
            raise ValueError("source must be given exactly for source artifacts")
        if self.path.split("/", 1)[0] == "logs":
            raise ValueError("logs are diagnostics, not evidence, and aren't listed")
        return self


class ParserVersion(ContractModel):
    """The parser version applied to one provider response layout."""

    layout: NonEmptyText
    layout_version: Annotated[int, Field(ge=1)]
    parser_version: Annotated[int, Field(ge=1)]


class Capabilities(ContractModel):
    """What the run does and doesn't contain."""

    return_series: Literal["source_only", "absent"]
    """`source_only`: the saved response holds per-period series, which are preserved but not
    normalized, charted, or analyzed. `absent`: no saved response holds any."""
    statistical_validation: NotAssessed
    trading_readiness: NotAssessed


class ExternalReference(ContractModel):
    """A setting that names a mutable object in the provider account."""

    setting: SettingName
    snapshotted: bool


class Reproducibility(ContractModel):
    """Whether the run's settings fully record what was run. A reference to an account object
    that wasn't snapshotted makes it incomplete."""

    status: Literal["complete", "incomplete"]
    external_references: tuple[ExternalReference, ...]

    @model_validator(mode="after")
    def _status(self) -> Self:
        complete = all(reference.snapshotted for reference in self.external_references)
        if (self.status == "complete") != complete:
            raise ValueError("status must be incomplete exactly when a reference isn't snapshotted")
        return self


class AttemptCounts(ContractModel):
    """Attempts, by outcome."""

    succeeded: Count
    failed: Count
    unknown: Count
    running: Count


class ManifestCounts(ContractModel):
    """The run's counts. `quotaRemaining` stays in the attempt record, out of the manifest."""

    results: Count
    cases: Count
    attempts: AttemptCounts
    provider_requests: Count
    """The sends of the planned request that may have reached Portfolio123 (JSON summary)."""
    retries: Count
    cost: Count | None
    """The credits Portfolio123 reported charging; null when it reported none."""


class RunManifest(ContractModel):
    """The manifest of a run written by `trialfolio run` or `trialfolio demo`."""

    schema_version: Literal["1.0.0"]
    artifact_type: Literal["run"]
    trialfolio_version: SemanticVersion
    created_at: UtcDatetime
    command: CommandRecord
    synthetic: bool
    """True for the synthetic run `trialfolio demo` writes."""
    plan_hash: Sha256Digest
    approval: Literal["interactive", "option", "not_required"]
    outcome: CommandOutcome
    error: ErrorDetail | None
    """Null exactly when the outcome is `completed`. `execution.partial` exactly when it's
    `partial`."""
    artifacts: tuple[ManifestArtifact, ...]
    parsers: tuple[ParserVersion, ...]
    license_id: LicenseId
    notice_version: NonEmptyText
    capabilities: Capabilities
    reproducibility: Reproducibility
    counts: ManifestCounts

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.synthetic != (self.command.name == "demo"):
            raise ValueError("synthetic must be true exactly for a run trialfolio demo wrote")
        if (self.approval == "not_required") != self.synthetic:
            raise ValueError("approval is not_required exactly for the synthetic run")
        check_outcome(self.outcome, self.error)
        require_unique(tuple(artifact.path for artifact in self.artifacts), "artifact paths")
        return self


# Version 1.1.0: a run whose ranking is a definition.

ArtifactRoleV1_1 = Literal[
    "plan",
    "configuration",
    "ranking_definition",
    "ranking_snapshot_record",
    "update_record",
    "start_record",
    "attempt_record",
    "rank_update_request",
    "rank_update_response",
    "rank_update_response_undecoded",
    "provider_request",
    "provider_response",
    "provider_response_undecoded",
    "metrics",
    "settings",
    "report",
]
"""1.0.0's roles, with a ranking definition's: the copy of the definition, `definition.xml`; a
snapshot's record, `snapshot.json`; and an attempt's update record and `rank_update` files."""

SOURCE_ROLES_V1_1: Final[frozenset[ArtifactRoleV1_1]] = frozenset(
    {
        *SOURCE_ROLES,
        "ranking_definition",
        "rank_update_request",
        "rank_update_response",
        "rank_update_response_undecoded",
    }
)
"""The roles of source artifacts in a manifest with a ranking definition: 1.0.0's, the copy of
the definition, and the `rank_update`'s request and response (artifact storage)."""

RANKING_FILES: Final[dict[str, str]] = {
    "ranking_definition": "definition.xml",
    "ranking_snapshot_record": "snapshot.json",
    "update_record": "updating.json",
    "rank_update_request": "rank-update-request.json",
    "rank_update_response": "rank-update-response.json",
    "rank_update_response_undecoded": "rank-update-response.raw",
}
"""The file each role a ranking definition adds names."""

_RANK_UPDATE_FORMATS: Final = {
    "rank_update_request": "p123api-rank-update-request",
    "rank_update_response": "p123api-rank-update",
    "rank_update_response_undecoded": "p123api-rank-update-response_undecoded",
}


class SourceRecordV1_1(ContractModel):
    """A source record in a manifest with a ranking definition: 1.0.0's, whose provider operation
    may also be the `rank_update` or a snapshot's `rank_get`."""

    acquired_at: UtcDatetime
    format: NonEmptyText
    """The source format, such as `ranking-definition` or `p123api-rank-update`."""
    format_version: NonEmptyText
    parser_version: Annotated[int, Field(ge=1)] | None
    """The version of the adapter that interpreted it; null when nothing interpreted it."""
    provenance: Provenance
    operation: Literal["screen_backtest", "rank_update", "rank_get"] | None
    """The provider operation that produced it; null for a file the user wrote."""


def check_ranking_artifact(
    role: str, path: str, schema_version: str | None, source: SourceRecordV1_1 | None
) -> None:
    """Raises `ValueError` unless a file of a role a ranking definition adds is the file its role
    names, with its schema version or its source record as artifact storage gives them: the
    definition's copy is `ranking-definition` version 1, the user's for a file and `rank_get`'s
    for a snapshot, and the `rank_update`'s request and response are its operation's."""
    expected = RANKING_FILES.get(role)
    if expected is None:
        return
    if path.rsplit("/", 1)[-1] != expected:
        raise ValueError(f"a file of the role {role} is {expected}")
    if role in ("ranking_snapshot_record", "update_record") and schema_version is None:
        raise ValueError(f"a file of the role {role} gives its schema version")
    if source is None:
        return
    shape = (source.format, source.format_version, source.parser_version)
    if role == "ranking_definition":
        origin = (source.provenance, source.operation)
        if shape != ("ranking-definition", "1", None) or origin not in (
            ("user_supplied", None),
            ("verified", "rank_get"),
        ):
            raise ValueError(
                "a definition's copy is the format ranking-definition, version 1, with no "
                "parser: user_supplied from a file, or verified, by rank_get, from a snapshot"
            )
    elif shape != (_RANK_UPDATE_FORMATS[role], "1", None) or (
        source.provenance,
        source.operation,
    ) != ("verified", "rank_update"):
        raise ValueError(
            f"a rank_update's file of the role {role} is the format {_RANK_UPDATE_FORMATS[role]}, "
            "version 1, verified, from rank_update, with no parser"
        )


class ManifestArtifactV1_1(ContractModel):
    """One file of a run with a ranking definition, by path, content address, and role."""

    path: RelativePath
    artifact_id: Sha256Digest
    size: Count
    role: ArtifactRoleV1_1
    schema_version: SemanticVersion | None
    """The file's schema version, for files that have one, such as the records and tables."""
    source: SourceRecordV1_1 | None
    """Given exactly for source artifacts."""

    @model_validator(mode="after")
    def _source_roles(self) -> Self:
        if (self.source is None) == (self.role in SOURCE_ROLES_V1_1):
            raise ValueError("source must be given exactly for source artifacts")
        if self.path.split("/", 1)[0] == "logs":
            raise ValueError("logs are diagnostics, not evidence, and aren't listed")
        check_ranking_artifact(self.role, self.path, self.schema_version, self.source)
        return self


class RunManifestV1_1(ContractModel):
    """The manifest of a run whose ranking is a definition: 1.0.0's, with the files the
    definition adds. A run the core writes with the demo's client, which no command writes, is
    synthetic, with no command (a run with a ranking definition)."""

    schema_version: Literal["1.1.0"]
    artifact_type: Literal["run"]
    trialfolio_version: SemanticVersion
    created_at: UtcDatetime
    command: CommandRecord | None
    """Null for a run the core writes with the demo's client, which no command writes."""
    synthetic: bool
    """True exactly for a run `trialfolio demo` writes, or one the core writes with the demo's
    client. Its values, attempt, and counts are invented."""
    plan_hash: Sha256Digest
    approval: Literal["interactive", "option", "not_required"]
    """`not_required` exactly for a synthetic run, which sends nothing."""
    outcome: CommandOutcome
    error: ErrorDetail | None
    """Null exactly when the outcome is `completed`. `execution.partial` exactly when it's
    `partial`."""
    artifacts: tuple[ManifestArtifactV1_1, ...]
    parsers: tuple[ParserVersion, ...]
    license_id: LicenseId
    notice_version: NonEmptyText
    capabilities: Capabilities
    reproducibility: Reproducibility
    counts: ManifestCounts
    """`provider_requests` counts both kinds of request, and `cost` sums the costs Portfolio123
    reported for both."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        written_by_demo = self.command is None or self.command.name == "demo"
        if self.synthetic != written_by_demo:
            raise ValueError(
                "synthetic must be true exactly for a run trialfolio demo wrote, or one the core "
                "wrote with the demo's client, with no command"
            )
        if (self.approval == "not_required") != self.synthetic:
            raise ValueError("approval is not_required exactly for a synthetic run")
        check_outcome(self.outcome, self.error)
        require_unique(tuple(artifact.path for artifact in self.artifacts), "artifact paths")
        return self
