"""The JSON summary that `--json` writes to stdout, schema version 1.0.0 (docs/contracts.md, JSON
summary).
"""

from typing import Annotated, Literal, Self, TypedDict

from pydantic import ConfigDict, model_validator, with_config

from trialfolio.contracts.common import (
    AttemptId,
    CaseId,
    CommandOutcome,
    ContractModel,
    Count,
    ErrorDetail,
    IntegerOnly,
    NonEmptyText,
    NotAssessed,
    RelativePath,
    SemanticVersion,
    Sha256Digest,
    check_outcome,
)
from trialfolio.errors import EXIT_CODES


@with_config(ConfigDict(strict=True, extra="forbid"))
class SummaryIds(TypedDict, total=False):
    """The identifiers the command created. A key is left out until its identifier exists."""

    plan_hash: Sha256Digest
    case_id: CaseId
    attempt_id: AttemptId


@with_config(ConfigDict(strict=True, extra="forbid"))
class SummaryOutputs(TypedDict, total=False):
    """The output files, relative to `output_dir`, by role. A key is left out for a file the
    command didn't write."""

    configuration: RelativePath
    """`trialfolio init`'s starter screen configuration."""
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
    """The counts of a command that has none: `init`, `report`, and `license`."""


class JsonSummary(ContractModel):
    """The one JSON object a command writes to stdout with `--json`, on success and on
    failure."""

    schema_version: Literal["1.0.0"]
    command: Literal["init", "run", "report", "demo", "license"]
    trialfolio_version: SemanticVersion
    outcome: CommandOutcome
    exit_code: Annotated[Literal[0, 1, 2, 3, 4, 5, 6, 130], IntegerOnly]
    ids: SummaryIds
    output_dir: NonEmptyText | None
    """The output directory as given on the command line, `.` for `trialfolio init` without
    one; null if none was created."""
    outputs: SummaryOutputs
    counts: RunCounts | NoCounts
    statistical_validation: NotAssessed
    trading_readiness: NotAssessed
    error: ErrorDetail | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        check_outcome(self.outcome, self.error)
        expected_exit = 0 if self.error is None else EXIT_CODES[self.error.code]
        if self.exit_code != expected_exit:
            raise ValueError("exit_code must be 0 when completed, or the exit code of the error")
        if isinstance(self.counts, RunCounts) != (self.command in ("run", "demo")):
            raise ValueError("counts are given exactly for run and demo")
        if self.output_dir is None and self.outputs:
            raise ValueError("outputs must be empty when no output directory was created")
        return self
