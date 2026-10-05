"""The JSON summary that `--json` writes to stdout (docs/contracts.md, JSON summary).

Trial Folio 0.2.0 writes version 1.1.0, `JsonSummaryV1_1`, for every command: 1.0.0 with
`review` in `command`, `review_id` in `ids`, and the review's counts. `JsonSummary` is version
1.0.0, which 0.1.0 writes. It and each model it uses keep their names, because the committed
`schemas/json-summary-1.0.0.schema.json` names them, and its bytes never change.
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
    ReviewId,
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


# Version 1.0.0, which Trial Folio 0.1.0 writes. Its docstrings are its schema's descriptions,
# so they stay as they are, like its name and its fields.
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
        _check_summary(self.outcome, self.exit_code, self.error, self.output_dir, self.outputs)
        if isinstance(self.counts, RunCounts) != (self.command in ("run", "demo")):
            raise ValueError("counts are given exactly for run and demo")
        return self


def _check_summary(
    outcome: CommandOutcome,
    exit_code: int,
    error: ErrorDetail | None,
    output_dir: str | None,
    outputs: SummaryOutputs,
) -> None:
    """The rules every version of the summary keeps: the outcome, the exit code, and the error
    agree, and there are no outputs without an output directory."""
    check_outcome(outcome, error)
    expected_exit = 0 if error is None else EXIT_CODES[error.code]
    if exit_code != expected_exit:
        raise ValueError("exit_code must be 0 when completed, or the exit code of the error")
    if output_dir is None and outputs:
        raise ValueError("outputs must be empty when no output directory was created")


@with_config(ConfigDict(strict=True, extra="forbid"))
class SummaryIdsV1_1(SummaryIds, total=False):
    """The identifiers the command created, in version 1.1.0: 1.0.0's, and a review's
    `review_id`. A key is left out until its identifier exists."""

    review_id: ReviewId
    """Given once the review has claimed its output directory."""


class ReviewCounts(ContractModel):
    """The counts of `review`. They're 0, or the number of results a valid configuration names,
    until `differences.csv` is written."""

    results: Count
    """The results compared, the baseline included."""
    settings_flagged: Count
    """`differences.csv`'s flagged setting rows."""
    metrics_unavailable: Count
    """`differences.csv`'s `unavailable` metric rows."""
    warnings: Count


class JsonSummaryV1_1(ContractModel):
    """The one JSON object a command writes to stdout with `--json`, on success and on
    failure: version 1.1.0, which Trial Folio 0.2.0 writes for every command. A 1.0.0 summary
    with its version changed to 1.1.0 is a valid 1.1.0 summary."""

    schema_version: Literal["1.1.0"]
    command: Literal["init", "run", "report", "demo", "license", "review"]
    trialfolio_version: SemanticVersion
    outcome: CommandOutcome
    exit_code: Annotated[Literal[0, 1, 2, 3, 4, 5, 6, 130], IntegerOnly]
    ids: SummaryIdsV1_1
    output_dir: NonEmptyText | None
    """The output directory as given on the command line, `.` for `trialfolio init` without
    one; null if none was created."""
    outputs: SummaryOutputs
    counts: RunCounts | ReviewCounts | NoCounts
    statistical_validation: NotAssessed
    trading_readiness: NotAssessed
    error: ErrorDetail | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_summary(self.outcome, self.exit_code, self.error, self.output_dir, self.outputs)
        if isinstance(self.counts, RunCounts) != (self.command in ("run", "demo")):
            raise ValueError("counts are given exactly for run and demo")
        if isinstance(self.counts, ReviewCounts) != (self.command == "review"):
            raise ValueError("a review's counts are given exactly for review")
        claimed = self.command == "review" and self.output_dir is not None
        if ("review_id" in self.ids) != claimed:
            raise ValueError("review_id is given exactly once a review has claimed its output")
        return self
