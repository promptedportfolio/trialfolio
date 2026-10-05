"""The review manifest, `manifest.json` with `artifact_type: review`, schema version 1.0.0
(docs/contracts.md, review output). It's written last, and only when the review completes:
without one, a review is incomplete.
"""

from collections import Counter
from typing import Annotated, Final, Literal, Self, TypedDict

from pydantic import ConfigDict, Field, model_validator, with_config

from trialfolio.contracts.common import (
    CaseId,
    ContractModel,
    Count,
    LicenseId,
    NonEmptyText,
    NotAssessed,
    RelativePath,
    ReviewId,
    ReviewLabel,
    SemanticVersion,
    Sha256Digest,
    UtcDatetime,
    require_unique,
)
from trialfolio.contracts.manifest import SourceRecord

ReviewArtifactRole = Literal[
    "configuration",
    "run_manifest",
    "plan",
    "metrics",
    "settings",
    "differences",
    "report",
]

COPY_ROLES: Final[frozenset[ReviewArtifactRole]] = frozenset(
    {"run_manifest", "plan", "metrics", "settings"}
)
"""The roles of the files a review copies from each run, under `inputs/<label>/`."""

REVIEW_CONFIGURATION_FORMAT: Final = "review-configuration"
"""The format the source record of a review's `configuration.yaml` gives."""


@with_config(ConfigDict(strict=True, extra="forbid"))
class ReviewOptions(TypedDict):
    """The review's options, as given. Neither the configuration's path nor `--out` is
    recorded, because a path can name the user."""

    json: bool


class ReviewCommandRecord(ContractModel):
    """The command that wrote the review, its options, and when it started."""

    name: Literal["review"]
    options: ReviewOptions
    started_at: UtcDatetime


class ReviewedResult(ContractModel):
    """Which run one label names. Each entry agrees with the result's copies."""

    label: ReviewLabel
    run_manifest: Sha256Digest
    """The `artifact_id` of the run's `manifest.json`, which identifies the run."""
    synthetic: bool
    """As the run's manifest gives it: true for the run `trialfolio demo` writes."""
    plan_hash: Sha256Digest
    case_id: CaseId
    normalized_tables: bool
    """Whether the run has normalized tables. Without them, its settings are compared from its
    plan, and its metrics are unavailable."""
    response: Sha256Digest | None
    """The `artifact_id` of the run's saved response, `response.json` or `response.raw`; null when
    it has none. Two results with the same one have byte-identical saved responses."""


class ReviewArtifact(ContractModel):
    """One file of the review, by path, content address, and role."""

    path: RelativePath
    artifact_id: Sha256Digest
    size: Count
    role: ReviewArtifactRole
    schema_version: SemanticVersion | None
    """The file's schema version. Every file but the report has one: a copy's is the one its
    run records."""
    source: SourceRecord | None
    """Given exactly for `configuration.yaml`, the review's one source artifact."""
    label: ReviewLabel | None
    """The label of the result a copy was copied from. Null for the review's own files."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if (self.source is None) != (self.role != "configuration"):
            raise ValueError("source must be given exactly for the configuration")
        if (self.schema_version is None) != (self.role == "report"):
            raise ValueError("schema_version must be given for every file but the report")
        if (self.label is None) != (self.role not in COPY_ROLES):
            raise ValueError("label must be given exactly for a copy of a run's file")
        top = self.path.split("/", 1)[0]
        if self.label is None:
            if top in ("inputs", "logs") or self.path == "manifest.json":
                raise ValueError(
                    "the review's own files aren't under inputs/ or logs/, and the manifest "
                    "doesn't list itself"
                )
        elif not self.path.startswith(f"inputs/{self.label}/"):
            raise ValueError("a copy's path is inputs/<label>/ followed by its path in the run")
        if self.source is not None and (
            self.source.format != REVIEW_CONFIGURATION_FORMAT
            or self.source.parser_version is not None
            or self.source.provenance != "user_supplied"
            or self.source.operation is not None
        ):
            raise ValueError(
                "the configuration's source record gives the review-configuration format, "
                "user_supplied provenance, and no parser version or provider operation"
            )
        return self


class Method(ContractModel):
    """An analytical method the review applied, with its version. A 1.0.0 review applies
    `screen-run-differences`, the rules of docs/contracts.md's differences between screen runs.
    A change to them that could change a row of `differences.csv` makes a new version."""

    name: Literal["screen-run-differences"]
    version: Annotated[int, Field(ge=1)]


class ReviewCapabilities(ContractModel):
    """What the review does and doesn't contain. Each copied run manifest says whether its run
    preserved per-period series."""

    return_series: Literal["absent"]
    statistical_validation: NotAssessed
    trading_readiness: NotAssessed


class SettingRowCounts(ContractModel):
    """`differences.csv`'s setting rows, by classification, and how many are flagged."""

    same: Count
    intended_change: Count
    unexplained_mismatch: Count
    unknown: Count
    flagged: Count


class MetricRowCounts(ContractModel):
    """`differences.csv`'s metric rows, by classification, and how many are flagged."""

    differenced: Count
    not_comparable: Count
    unavailable: Count
    flagged: Count


class ReviewManifestCounts(ContractModel):
    """The review's counts."""

    results: Count
    """The results compared, the baseline included."""
    settings: SettingRowCounts
    metrics: MetricRowCounts

    @model_validator(mode="after")
    def _flagged_rows_are_rows(self) -> Self:
        settings, metrics = self.settings, self.metrics
        setting_rows = (
            settings.same
            + settings.intended_change
            + settings.unexplained_mismatch
            + settings.unknown
        )
        metric_rows = metrics.differenced + metrics.not_comparable + metrics.unavailable
        if settings.flagged > setting_rows or metrics.flagged > metric_rows:
            raise ValueError("flagged counts rows of differences.csv, so it's at most their number")
        return self


class ReviewManifest(ContractModel):
    """The manifest of a review written by `trialfolio review`. It has no plan hash, approval,
    parsers, or reproducibility: each copied run manifest records its own."""

    schema_version: Literal["1.0.0"]
    artifact_type: Literal["review"]
    trialfolio_version: SemanticVersion
    created_at: UtcDatetime
    review_id: ReviewId
    command: ReviewCommandRecord
    synthetic: bool
    """True when any result is synthetic."""
    outcome: Literal["completed"]
    """A review writes its manifest only when it completes."""
    error: None
    baseline: ReviewLabel
    results: Annotated[tuple[ReviewedResult, ...], Field(min_length=2)]
    """One entry for each result, in the configuration's order."""
    artifacts: tuple[ReviewArtifact, ...]
    """Each file of the review except its own `manifest.json` and the logs."""
    methods: Annotated[tuple[Method, ...], Field(min_length=1)]
    license_id: LicenseId
    notice_version: NonEmptyText
    capabilities: ReviewCapabilities
    counts: ReviewManifestCounts

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        labels = tuple(result.label for result in self.results)
        require_unique(labels, "result labels")
        if self.baseline not in labels:
            raise ValueError("baseline must be the label of one of the results")
        if self.synthetic != any(result.synthetic for result in self.results):
            raise ValueError("synthetic must be true exactly when a result is synthetic")
        require_unique(tuple(artifact.path for artifact in self.artifacts), "artifact paths")
        require_unique(tuple(method.name for method in self.methods), "method names")
        if self.counts.results != len(self.results):
            raise ValueError("counts.results must be the number of results")
        own = Counter(artifact.role for artifact in self.artifacts if artifact.label is None)
        if own != Counter({"configuration": 1, "differences": 1, "report": 1}):
            raise ValueError(
                "the review lists one configuration, one differences table, and one report"
            )
        for result in self.results:
            self._check_copies(result)
        if any(artifact.label not in (None, *labels) for artifact in self.artifacts):
            raise ValueError("each copy's label must be the label of one of the results")
        return self

    def _check_copies(self, result: ReviewedResult) -> None:
        copies = [artifact for artifact in self.artifacts if artifact.label == result.label]
        roles = Counter(artifact.role for artifact in copies)
        tables = {"metrics": 1, "settings": 1} if result.normalized_tables else {}
        if roles != Counter({"run_manifest": 1, "plan": 1, **tables}):
            raise ValueError(
                "each result has a copy of its run's manifest and plan, and of its normalized "
                "tables exactly when it has them"
            )
        (manifest,) = (artifact for artifact in copies if artifact.role == "run_manifest")
        if manifest.artifact_id != result.run_manifest:
            raise ValueError("a result's run_manifest must be its copied manifest's artifact_id")
