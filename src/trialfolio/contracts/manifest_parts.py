"""The parts of a manifest that a run's, a review's, an experiment's, and a ranking snapshot's
share (docs/contracts.md, artifact storage): a source artifact's source record, the roles of the
source artifacts, the parser versions, the capabilities, the reproducibility, the attempts by
outcome, and the check of a file of a role a ranking definition adds, with the formats of the
`rank_update`'s files, which the manifests' writers give too (`trialfolio.manifests`).

From release 0.5.0, the parts a run manifest 1.2.0, an experiment manifest 1.2.0, and the report
manifest share: the capabilities, whose `return_series` may be `normalized`; the analytical
methods, `analysis-set` and `baseline-comparison`, each with its version; and the files of the
tables, by role (a run 0.5.0 writes, the experiment manifest, the report manifest).
"""

from collections.abc import Sequence
from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from trialfolio.contracts.common import (
    ContractModel,
    Count,
    NonEmptyText,
    NotAssessed,
    Provenance,
    SemanticVersion,
    SettingName,
    UtcDatetime,
    require_unique,
)

SOURCE_ROLES: Final[frozenset[str]] = frozenset(
    {"configuration", "provider_request", "provider_response", "provider_response_undecoded"}
)
"""The roles of source artifacts, which carry a source record (INV-04, source artifacts), in a
run's manifest and an experiment's, and, with a definition's copy, a snapshot's."""

SOURCE_ROLES_V1_1: Final[frozenset[str]] = frozenset(
    {
        *SOURCE_ROLES,
        "ranking_definition",
        "rank_update_request",
        "rank_update_response",
        "rank_update_response_undecoded",
    }
)
"""The roles of source artifacts in a manifest with a ranking definition, run manifest 1.1.0 and
experiment manifest 1.1.0: 1.0.0's, the copy of the definition, and the `rank_update`'s request
and response (artifact storage)."""


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


class CapabilitiesV1_2(ContractModel):
    """What a run or an experiment 0.5.0 writes does and doesn't contain: 1.0.0's capabilities,
    whose `return_series` may also be `normalized` (a run 0.5.0 writes)."""

    return_series: Literal["normalized", "source_only", "absent"]
    """`normalized`: `series.csv` holds the series the saved response has, whatever their
    availability, and `analysis.csv` the analysis set's values of them. `source_only` and
    `absent`, for a run or an experiment without tables, as before."""
    statistical_validation: NotAssessed
    trading_readiness: NotAssessed


ANALYSIS_SET: Final = "analysis-set"
"""The method of `analysis.csv`'s values, by the analysis set's version (analysis set 1.0.0)."""

BASELINE_COMPARISON: Final = "baseline-comparison"
"""The method of `comparison.csv`'s rows: comparing a case with the baseline."""


class AnalysisSetMethod(ContractModel):
    """The analysis set a manifest's `analysis.csv` holds the values of, by its version, a string,
    as `analysis.csv`'s `analysis_set` gives it."""

    name: Literal["analysis-set"]
    version: SemanticVersion


class BaselineComparisonMethod(ContractModel):
    """`baseline-comparison`, the rules of comparing a case with the baseline, by its version, an
    integer, as a review's method's is. A change to them that could change a row of
    `comparison.csv` makes a new version."""

    name: Literal["baseline-comparison"]
    version: Annotated[int, Field(ge=1)]


type AnalyticsMethod = AnalysisSetMethod | BaselineComparisonMethod
"""An analytical method a manifest records, with its version."""


def check_methods(
    methods: Sequence[AnalysisSetMethod | BaselineComparisonMethod],
    *,
    analyses: bool | None,
    comparison: bool,
) -> None:
    """Raises `ValueError` unless `methods` lists the analysis set exactly when `analyses`, or
    when the manifest's own files can't tell, with `analyses` None, as the report manifest's,
    which also shows its input's tables; by each version once, in increasing order; then
    `baseline-comparison`, once, exactly when `comparison`: so the same tables give the same
    list."""
    require_unique(tuple((method.name, method.version) for method in methods), "methods")
    sets = [method for method in methods if isinstance(method, AnalysisSetMethod)]
    comparisons = [method for method in methods if isinstance(method, BaselineComparisonMethod)]
    if analyses is not None and bool(sets) != analyses:
        raise ValueError("methods lists the analysis set exactly when an analysis.csv is listed")
    if len(comparisons) != int(comparison):
        raise ValueError("methods lists baseline-comparison once exactly when the comparison is")
    if list(methods) != [*sets, *comparisons]:
        raise ValueError("methods lists the analysis set's versions, then baseline-comparison")
    versions = [tuple(int(part) for part in method.version.split(".")) for method in sets]
    if versions != sorted(versions):
        raise ValueError("methods lists the analysis set's versions in increasing order")


TABLE_FILES: Final[dict[str, str]] = {
    "metrics": "metrics.csv",
    "settings": "settings.csv",
    "series": "series.csv",
    "analysis": "analysis.csv",
}
"""The file each role of a result's tables names, in the order they're written (where the return
analytics are written)."""


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


RANKING_FILES: Final[dict[str, str]] = {
    "ranking_definition": "definition.xml",
    "ranking_snapshot_record": "snapshot.json",
    "update_record": "updating.json",
    "rank_update_request": "rank-update-request.json",
    "rank_update_response": "rank-update-response.json",
    "rank_update_response_undecoded": "rank-update-response.raw",
}
"""The file each role a ranking definition adds names."""

RANK_UPDATE_FORMATS: Final[dict[str, str]] = {
    "rank_update_request": "p123api-rank-update-request",
    "rank_update_response": "p123api-rank-update",
    "rank_update_response_undecoded": "p123api-rank-update-response_undecoded",
}
"""The source format of each of the `rank_update`'s files, at version 1, which no parser reads."""


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
    elif shape != (RANK_UPDATE_FORMATS[role], "1", None) or (
        source.provenance,
        source.operation,
    ) != ("verified", "rank_update"):
        raise ValueError(
            f"a rank_update's file of the role {role} is the format {RANK_UPDATE_FORMATS[role]}, "
            "version 1, verified, from rank_update, with no parser"
        )
