"""The JSON summary that `--json` writes to stdout, schema version 1.0.0 (docs/contracts.md, JSON
summary).
"""

from typing import Annotated, Literal, Self, TypedDict

from pydantic import UUID4, ConfigDict, Field, model_validator, with_config

from trialfolio.contracts.common import (
    CaseId,
    ContractModel,
    ErrorDetail,
    IntegerOnly,
    NonEmptyText,
    NotAssessed,
    RelativePath,
    SemanticVersion,
    Sha256Digest,
)
from trialfolio.errors import EXIT_CODES

Count = Annotated[int, Field(ge=0)]


@with_config(ConfigDict(extra="forbid"))
class SummaryIds(TypedDict, total=False):
    """The identifiers the command created. A key is left out until its identifier exists."""

    plan_hash: Sha256Digest
    case_id: CaseId
    attempt_id: UUID4


@with_config(ConfigDict(extra="forbid"))
class SummaryOutputs(TypedDict, total=False):
    """The output files, relative to `output_dir`, by role. A key is left out for a file the
    command didn't write."""

    manifest: RelativePath
    report: RelativePath
    metrics: RelativePath
    settings: RelativePath
    differences: RelativePath


class RunCounts(ContractModel):
    """The counts of `run` and `demo`."""

    attempts: Count
    provider_requests: Count
    """The sends of the planned request that may have reached Portfolio123, never
    authentication."""
    metrics_unavailable: Count
    warnings: Count
    cost: Count | None
    """The credits Portfolio123 reported charging; null when it reported none."""


class NoCounts(ContractModel):
    """The counts of a command that has none: `report` and `license`."""


class JsonSummary(ContractModel):
    """The one JSON object a command writes to stdout with `--json`, on success and on
    failure."""

    schema_version: Literal["1.0.0"]
    command: Literal["run", "report", "demo", "license"]
    trialfolio_version: SemanticVersion
    outcome: Literal["completed", "partial", "failed"]
    exit_code: Annotated[Literal[0, 1, 2, 3, 4, 5, 6, 130], IntegerOnly]
    ids: SummaryIds
    output_dir: NonEmptyText | None
    """The output directory as given on the command line; null if none was created."""
    outputs: SummaryOutputs
    counts: RunCounts | NoCounts
    statistical_validation: NotAssessed
    trading_readiness: NotAssessed
    error: ErrorDetail | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.outcome == "completed":
            if self.error is not None or self.exit_code != 0:
                raise ValueError("a completed command has exit_code 0 and no error")
        elif self.error is None:
            raise ValueError("a command that didn't complete has an error")
        elif self.exit_code != EXIT_CODES[self.error.code]:
            raise ValueError("exit_code must be the exit code of the error's code")
        elif (self.outcome == "partial") != (self.error.code == "execution.partial"):
            raise ValueError("the outcome is partial exactly for execution.partial")
        if isinstance(self.counts, RunCounts) != (self.command in ("run", "demo")):
            raise ValueError("counts are given exactly for run and demo")
        if self.output_dir is None and self.outputs:
            raise ValueError("outputs must be empty when no output directory was created")
        return self
