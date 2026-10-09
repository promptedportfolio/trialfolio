"""The JSON summary that `--json` writes to stdout (docs/contracts.md, JSON summary).

Trial Folio 0.3.0 writes version 1.2.0, `JsonSummaryV1_2`, for every command: 1.1.0 with an
experiment's `ids`, its `cases`, and its counts (D-33). Version 1.1.0, `JsonSummaryV1_1`, is
what 0.2.0 writes: 1.0.0 with `review` in `command`, `review_id` in `ids`, and the review's
counts. `JsonSummary` is version 1.0.0, which 0.1.0 writes. Each earlier version's model, and each
model it uses, keeps its name, because its committed schema names them, and its bytes never
change.
"""

from typing import Annotated, Literal, Self, TypedDict

from pydantic import ConfigDict, Field, model_validator, with_config

from trialfolio.contracts.common import (
    BASELINE_CASE_KEY,
    AttemptId,
    CaseId,
    CommandOutcome,
    ContractModel,
    Count,
    ErrorDetail,
    ExperimentKey,
    IntegerOnly,
    NonEmptyText,
    NotAssessed,
    Ordinal,
    RelativePath,
    ReviewId,
    SemanticVersion,
    Sha256Digest,
    check_outcome,
    optional_key,
    require_unique,
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


@with_config(ConfigDict(strict=True, extra="forbid"))
class SummaryIdsV1_2(SummaryIdsV1_1, total=False):
    """The identifiers the command created, in version 1.2.0: 1.1.0's, and an experiment's. A
    key is left out until its identifier exists. An experiment's `cases` give its cases' and
    attempts' IDs, so its `ids` hold no `case_id` or `attempt_id`."""

    experiment_id: ExperimentKey
    """Given once an experiment's configuration is valid."""
    session: Ordinal
    """The session's number, once its session record is written."""


class SummaryCase(ContractModel):
    """One case of the experiment's plan, as the experiment manifest counts it."""

    case_key: ExperimentKey
    case_id: CaseId
    outcome: Literal["succeeded", "failed", "unknown", "not_yet_run"]
    repeat_attempt_id: AttemptId | None
    """For a case awaiting a repeat, the `attempt_id` that `--repeat <case-key>:<attempt-id>`
    names to confirm it; null for any other case."""

    @model_validator(mode="after")
    def _repeatable(self) -> Self:
        if self.repeat_attempt_id is not None and self.outcome not in ("failed", "unknown"):
            raise ValueError("only a failed or unknown case awaits a repeat")
        return self


class ExperimentCounts(ContractModel):
    """An experiment's counts, as its manifest counts them, across every run of it; and the
    `unavailable` rows of the planned cases' tables, and the warnings this command logged."""

    cases_planned: Annotated[int, Field(ge=2)]
    cases_succeeded: Count
    cases_failed: Count
    cases_skipped: Count
    cases_unknown: Count
    cases_not_yet_run: Count
    cases_retired: Count
    attempts: Count
    repeats: Count
    provider_requests: Count
    """The sends that may have reached Portfolio123, a `running` attempt counted as one, never
    authentication."""
    authentication_calls: Count
    """Trial Folio's own authentication calls, whatever their result."""
    cost: Count | None
    """The credits Portfolio123 reported charging; null when it reported none."""
    metrics_unavailable: Count
    warnings: Count

    @model_validator(mode="after")
    def _add_up(self) -> Self:
        total = (
            self.cases_succeeded
            + self.cases_failed
            + self.cases_skipped
            + self.cases_unknown
            + self.cases_not_yet_run
        )
        if total != self.cases_planned:
            raise ValueError(
                "cases_planned must equal the cases succeeded, failed, skipped, unknown, and not "
                "yet run"
            )
        if self.repeats > self.attempts:
            raise ValueError("repeats counts attempts, so it's at most their number")
        return self


class JsonSummaryV1_2(ContractModel):
    """The one JSON object a command writes to stdout with `--json`, on success and on
    failure: version 1.2.0, which Trial Folio 0.3.0 writes for every command. A 1.1.0 summary
    with its version changed to 1.2.0 is a valid 1.2.0 summary."""

    schema_version: Literal["1.2.0"]
    command: Literal["init", "run", "report", "demo", "license", "review"]
    trialfolio_version: SemanticVersion
    outcome: CommandOutcome
    exit_code: Annotated[Literal[0, 1, 2, 3, 4, 5, 6, 130], IntegerOnly]
    ids: SummaryIdsV1_2
    output_dir: NonEmptyText | None
    """The output directory as given on the command line, `.` for `trialfolio init` without
    one; null if none was created. For an experiment, given once the command writes into it:
    from a new experiment's claim, or from a resume's session record."""
    outputs: SummaryOutputs
    cases: Annotated[
        tuple[SummaryCase, ...] | None,
        Field(exclude_if=lambda cases: cases is None, json_schema_extra=optional_key),
    ] = None
    """For an experiment only, once its plan is built: each case of the plan this run builds, in
    its order. Left out for every other command and configuration."""
    counts: RunCounts | ReviewCounts | ExperimentCounts | NoCounts
    """`{}` for `init`, `report`, and `license`, and for an experiment until its counts are
    known."""
    statistical_validation: NotAssessed
    trading_readiness: NotAssessed
    error: ErrorDetail | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _check_summary(self.outcome, self.exit_code, self.error, self.output_dir, self.outputs)
        if self.cases is None and "cases" in self.model_fields_set:
            raise ValueError("cases is left out when it isn't given, never null")
        if isinstance(self.counts, ReviewCounts) != (self.command == "review"):
            raise ValueError("a review's counts are given exactly for review")
        claimed = self.command == "review" and self.output_dir is not None
        if ("review_id" in self.ids) != claimed:
            raise ValueError("review_id is given exactly once a review has claimed its output")
        if "experiment_id" not in self.ids:
            if self.cases is not None or "session" in self.ids:
                raise ValueError("cases and a session are given only for an experiment")
            if isinstance(self.counts, ExperimentCounts):
                raise ValueError("an experiment's counts are given only for an experiment")
            if isinstance(self.counts, RunCounts) != (self.command in ("run", "demo")):
                raise ValueError("a run's counts are given exactly for run and demo")
            return self
        self._check_experiment()
        return self

    def _check_experiment(self) -> None:
        if self.command != "run":
            raise ValueError("an experiment is run with run")
        if "case_id" in self.ids or "attempt_id" in self.ids:
            raise ValueError("an experiment's cases give their IDs, so its ids hold none")
        if isinstance(self.counts, RunCounts):
            raise ValueError("an experiment's counts are its own, or {} until they're known")
        if ("plan_hash" in self.ids) != (self.cases is not None):
            raise ValueError("an experiment's plan_hash and cases are given once its plan is built")
        if "session" in self.ids and self.output_dir is None:
            raise ValueError("a session writes into the output directory")
        if set(self.outputs) - {"manifest", "report"}:
            raise ValueError("an experiment's outputs are its session's manifest and report")
        if self.cases is None:
            return
        if self.cases[0].case_key != BASELINE_CASE_KEY or len(self.cases) < 2:
            raise ValueError("an experiment's cases are the baseline first, and its variants")
        require_unique(tuple(case.case_key for case in self.cases), "case keys")
        require_unique(tuple(case.case_id for case in self.cases), "case IDs")
        counts = self.counts
        if isinstance(counts, ExperimentCounts):
            outcomes = [case.outcome for case in self.cases]
            if (
                counts.cases_planned,
                counts.cases_succeeded,
                counts.cases_failed,
                counts.cases_unknown,
                counts.cases_not_yet_run,
            ) != (
                len(outcomes),
                outcomes.count("succeeded"),
                outcomes.count("failed"),
                outcomes.count("unknown"),
                outcomes.count("not_yet_run"),
            ):
                raise ValueError("the case counts are the cases' outcomes, counted")
