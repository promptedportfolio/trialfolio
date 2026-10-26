"""The run manifest, `manifest.json` with `artifact_type: run`, schema version 1.0.0
(docs/contracts.md, artifact storage). It's written last: without one, a run is incomplete.

Version 1.1.0, `RunManifestV1_1`, is a run's whose ranking is a definition: 1.0.0's fields, with
the roles of the files such a run adds, their source records, and a run the core writes with the
demo's client, which is synthetic, with no command (a run with a ranking definition).

The parts every kind's manifest shares, such as the source records, are in
`trialfolio.contracts.manifest_parts`.
"""

from typing import Literal, Self

from pydantic import model_validator

from trialfolio.contracts.common import (
    CommandOutcome,
    ContractModel,
    Count,
    ErrorDetail,
    LicenseId,
    NonEmptyText,
    RelativePath,
    SemanticVersion,
    Sha256Digest,
    UtcDatetime,
    check_outcome,
    require_unique,
)
from trialfolio.contracts.manifest_parts import (
    SOURCE_ROLES,
    SOURCE_ROLES_V1_1,
    AttemptCounts,
    Capabilities,
    ParserVersion,
    Reproducibility,
    SourceRecord,
    SourceRecordV1_1,
    check_ranking_artifact,
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


class CommandRecord(ContractModel):
    """The command that wrote the run, its non-secret options, and when it started."""

    name: Literal["run", "demo"]
    options: dict[NonEmptyText, str | bool | None]
    """The command-line options as given, by name, such as `out` and `approve`."""
    started_at: UtcDatetime


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
