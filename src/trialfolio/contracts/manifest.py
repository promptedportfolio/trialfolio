"""The run manifest, `manifest.json` with `artifact_type: run`, schema version 1.0.0
(docs/contracts.md, artifact storage). It's written last: without one, a run is incomplete.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from trialfolio.contracts.common import (
    ContractModel,
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
    require_unique,
)

Count = Annotated[int, Field(ge=0)]

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
    outcome: Literal["completed", "partial", "failed"]
    error: ErrorDetail | None
    """Null exactly when the outcome is `completed`."""
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
        if (self.error is None) != (self.outcome == "completed"):
            raise ValueError("error must be given exactly when the outcome isn't completed")
        require_unique(tuple(artifact.path for artifact in self.artifacts), "artifact paths")
        return self
