"""The report manifest, `manifest.json` with `artifact_type: report`, schema version 1.0.0
(docs/contracts.md, the report manifest), from release 0.5.0. `trialfolio report` writes it last,
into its own output directory, after the report and each table it calculated for a result that
lacks one, so an output without it is incomplete.

It records what the report rendered by the `artifact_id` of its manifest, never by a path, which
can name the user, and holds no time and no option of the command, so the same input, rendered
with the same version into an output directory at the same place relative to it, gives the same
bytes. It lists only the files it wrote: the input's manifest lists the input's.
"""

import re
from collections import Counter
from typing import Final, Literal, Self

from pydantic import model_validator

from trialfolio.contracts.common import (
    ContractModel,
    Count,
    ExperimentKey,
    LicenseId,
    NonEmptyText,
    NotAssessed,
    Ordinal,
    RelativePath,
    SemanticVersion,
    Sha256Digest,
    require_unique,
)
from trialfolio.contracts.manifest_parts import (
    AnalysisSetMethod,
    AnalyticsMethod,
    ParserVersion,
    check_methods,
)

ReportArtifactRole = Literal["report", "series", "analysis", "comparison"]
"""The report, and each table it calculated: a result's `series.csv` and `analysis.csv`, and an
experiment's `comparison.csv`."""

_RESULT = r"(cases/(?P<case>case-[0-9a-f]{16})/)?normalized/"

REPORT_PATHS: Final[dict[str, re.Pattern[str]]] = {
    "report": re.compile(r"report\.html"),
    "series": re.compile(rf"{_RESULT}series\.csv"),
    "analysis": re.compile(rf"{_RESULT}analysis\.csv"),
    "comparison": re.compile(r"normalized/comparison\.csv"),
}
"""Where the file of each role is in `trialfolio report`'s output: a run's tables in
`normalized/`, each planned case's of an experiment in `cases/<case_id>/normalized/`, and an
experiment's `comparison.csv` in `normalized/` (`trialfolio report`'s output)."""


class ReportArtifact(ContractModel):
    """One file `trialfolio report` wrote, by path, content address, and role."""

    path: RelativePath
    artifact_id: Sha256Digest
    size: Count
    role: ReportArtifactRole
    schema_version: SemanticVersion | None
    """A table's schema version; null for the report, which has none."""

    @model_validator(mode="after")
    def _placed(self) -> Self:
        if not REPORT_PATHS[self.role].fullmatch(self.path):
            raise ValueError(f"a file of the role {self.role} isn't at this path")
        if (self.schema_version is None) != (self.role == "report"):
            raise ValueError("a table gives its schema version, and the report none")
        return self


class ReportInput(ContractModel):
    """What the report renders: a saved run, or a saved experiment's latest session, named by the
    `artifact_id` of the run's or the session's `manifest.json`, and its plan's hash. No path."""

    artifact_type: Literal["run", "experiment"]
    manifest: Sha256Digest
    """The `artifact_id` of the run's `manifest.json`, or of the session's."""
    plan_hash: Sha256Digest
    """The run's plan's hash, or the session's current plan's."""
    experiment_id: ExperimentKey | None
    """The experiment's identity; null for a run."""
    session: Ordinal | None
    """The number of the session whose report it renders, the latest manifest's; null for a
    run."""

    @model_validator(mode="after")
    def _of_its_kind(self) -> Self:
        experiment = (self.experiment_id is not None, self.session is not None)
        if experiment != ((self.artifact_type == "experiment"),) * 2:
            raise ValueError("experiment_id and session are given exactly for an experiment")
        return self


class ReportCapabilities(ContractModel):
    """What the output does and doesn't contain. It holds no response, so a series it holds is
    one it normalized."""

    return_series: Literal["normalized", "absent"]
    """`normalized` exactly when the output holds a `series.csv`."""
    statistical_validation: NotAssessed
    trading_readiness: NotAssessed


class ReportManifest(ContractModel):
    """The manifest `trialfolio report` writes last: what it rendered, the tables it calculated,
    and the methods and parsers behind the values its report shows."""

    schema_version: Literal["1.0.0"]
    artifact_type: Literal["report"]
    trialfolio_version: SemanticVersion
    """The version that rendered the report."""
    synthetic: bool
    """As the input's manifest gives it."""
    input: ReportInput
    artifacts: tuple[ReportArtifact, ...]
    """`report.html`, then each table it wrote, in the order it wrote them. Not the input's
    files, which its manifest lists and the report links, and not `logs/`."""
    parsers: tuple[ParserVersion, ...]
    """The parser version that read each response for a `series.csv` it wrote, with its layout's
    version; empty when it wrote none."""
    methods: tuple[AnalyticsMethod, ...]
    """Each method whose values the report shows: `analysis-set`, with each version of the
    `analysis.csv` it shows, the input's or its own, and, for an experiment, then
    `baseline-comparison`, version 1."""
    license_id: LicenseId
    notice_version: NonEmptyText
    capabilities: ReportCapabilities

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        require_unique(tuple(artifact.path for artifact in self.artifacts), "artifact paths")
        roles = Counter(artifact.role for artifact in self.artifacts)
        if roles["report"] != 1 or self.artifacts[0].role != "report":
            raise ValueError("the manifest lists the report, first")
        _check_tables(self)
        series = roles["series"] > 0
        if (self.capabilities.return_series == "normalized") != series:
            raise ValueError("return_series is normalized exactly when it wrote a series.csv")
        if bool(self.parsers) != series:
            raise ValueError("parsers name the parser of each series.csv it wrote, and only then")
        require_unique(
            tuple((p.layout, p.layout_version, p.parser_version) for p in self.parsers), "parsers"
        )
        experiment = self.input.artifact_type == "experiment"
        check_methods(
            self.methods, analyses=True if roles["analysis"] else None, comparison=experiment
        )
        sets = [method for method in self.methods if isinstance(method, AnalysisSetMethod)]
        if not experiment and len(sets) > 1:
            raise ValueError("a run's report shows one analysis.csv, so one analysis set")
        return self


def _check_tables(manifest: ReportManifest) -> None:
    """Raises `ValueError` unless the tables are where the input's kind puts them: a run's in
    `normalized/`, with no `comparison.csv`; an experiment's under each case's directory, with at
    most one `comparison.csv`; and a result's `series.csv` and `analysis.csv` together."""
    experiment = manifest.input.artifact_type == "experiment"
    results: Counter[tuple[str | None, str]] = Counter()
    for artifact in manifest.artifacts:
        if artifact.role in ("series", "analysis"):
            found = REPORT_PATHS[artifact.role].fullmatch(artifact.path)
            case = found.group("case") if found is not None else None
            if (case is not None) != experiment:
                raise ValueError(
                    "a run's tables are in normalized/, and an experiment's cases' in "
                    "cases/<case_id>/normalized/"
                )
            results[(case, artifact.role)] += 1
        elif artifact.role == "comparison" and not experiment:
            raise ValueError("only an experiment's report has a comparison.csv")
    cases = {case for case, _ in results}
    if any(results[(case, role)] != 1 for case in cases for role in ("series", "analysis")):
        raise ValueError("a result's series.csv and analysis.csv are written together")
