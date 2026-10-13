"""What each kind of report is rendered from: the evidence the core gives, and the context each
kind of report's sections read.

- **The evidence.** A run's report reads a `SavedRun`, from `trialfolio.runs`. A review's reads a
  `ReviewEvidence`, and an experiment session's an `ExperimentEvidence`, with a `CaseView` for
  each planned case and a `RetiredCaseView` for each retired one, which the core builds.
- **The contexts.** `RunContext`, `ReviewContext`, and `ExperimentContext` each hold the evidence
  of one report, the version rendering it, and the lookups its sections share, such as its
  settings by name, so each section is a function of its report's context.
- **The paths** of a report, and of an experiment session's report and manifest.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, Self
from uuid import UUID

from trialfolio.contracts.attempt import AttemptRecordV1_1
from trialfolio.contracts.common import Approval, ErrorDetail
from trialfolio.contracts.experiment_manifest import (
    ExperimentArtifact,
    ExperimentCommandRecord,
    ExperimentManifestCounts,
)
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, PlanV1_1
from trialfolio.contracts.experiment_record import ExperimentRecord, RetiredCase
from trialfolio.contracts.manifest import Capabilities, ParserVersion, Reproducibility
from trialfolio.contracts.plan import PlanCase
from trialfolio.contracts.review_configuration import ReviewConfiguration
from trialfolio.contracts.review_manifest import ReviewArtifact
from trialfolio.contracts.tables import DifferencesRow, MetricsRow, SettingsRow
from trialfolio.differences import Differences
from trialfolio.display import series
from trialfolio.report.fragments import Setting, resolved_settings
from trialfolio.report.page import code
from trialfolio.report.vocabulary import SYNTHETIC_NOT_SENT, TOKENS
from trialfolio.review_inputs import ReviewInput
from trialfolio.runs import MANIFEST_PATH, SavedRun

REPORT_PATH: Final = "report.html"


def experiment_report_path(session: int) -> str:
    """`sessions/<session>/report.html`, relative to the output root."""
    return f"sessions/{session}/{REPORT_PATH}"


def experiment_manifest_path(session: int) -> str:
    """`sessions/<session>/manifest.json`, relative to the output root."""
    return f"sessions/{session}/{MANIFEST_PATH}"


# The run report (R01-T13)


@dataclass(frozen=True)
class RunContext:
    """A run's report: the saved run, its resolved settings, and its metrics."""

    saved: SavedRun
    base: tuple[str, ...] | None
    """The run's directory as percent-encoded path segments from the report's, or None for no
    links."""
    version: str
    """The Trial Folio version rendering the report."""
    settings: tuple[Setting, ...]
    by_name: Mapping[str, Setting]
    metrics: Mapping[tuple[str, str], MetricsRow]
    """By subject and `metric_id`. Empty for a run without normalized tables."""

    @classmethod
    def of(cls, saved: SavedRun, base: tuple[str, ...] | None, version: str) -> Self:
        settings = resolved_settings(saved.settings, saved.plan.cases[0].settings)
        return cls(
            saved,
            base,
            version,
            settings,
            {setting.name: setting for setting in settings},
            {(row.subject, row.metric_id): row for row in saved.metrics or ()},
        )

    @property
    def case(self) -> PlanCase:
        return self.saved.plan.cases[0]

    @property
    def synthetic(self) -> bool:
        return self.saved.manifest.synthetic


# The review report (R02-T07)


@dataclass(frozen=True)
class ReviewEvidence:
    """What a review's report shows: its configuration, each result's run as the input check read
    it, the comparison, and what the review manifest will record.

    The report is written before the manifest, so `artifacts` holds each file the manifest will
    list apart from the report itself: `configuration.yaml`, the copies, and `differences.csv`.
    """

    configuration: ReviewConfiguration
    inputs: tuple[ReviewInput, ...]
    """One for each result, in the configuration's order."""
    differences: Differences
    review_id: UUID
    started_at: datetime
    """When the command started, as the manifest's `command.started_at`."""
    artifacts: tuple[ReviewArtifact, ...]

    def __post_init__(self) -> None:
        labels = tuple(result.label for result in self.configuration.results)
        if tuple(checked.result.label for checked in self.inputs) != labels:
            raise ValueError("each result has one input, in the configuration's order")
        if any(artifact.role == "report" for artifact in self.artifacts):
            raise ValueError("the artifacts are the ones the report links, so not the report")


@dataclass(frozen=True)
class ReviewContext:
    """A review's report: the evidence, with each result's resolved settings and metrics, and the
    comparison's rows, each by what names it."""

    evidence: ReviewEvidence
    version: str
    """The Trial Folio version rendering the report."""
    baseline: str
    """The baseline's label."""
    others: tuple[ReviewInput, ...]
    """Each result but the baseline, in the configuration's order."""
    synthetic: tuple[str, ...]
    """The labels of the synthetic results, in the configuration's order."""
    settings: Mapping[str, Mapping[str, Setting]]
    """By label, and then by setting name."""
    metrics: Mapping[str, Mapping[tuple[str, str], MetricsRow]]
    """By label, and then by subject and `metric_id`."""
    rows: Mapping[tuple[str, str, str | None, str], DifferencesRow]
    """`differences.csv`'s rows, by label, kind, subject, and name."""

    @classmethod
    def of(cls, evidence: ReviewEvidence, version: str) -> Self:
        baseline = evidence.configuration.baseline
        return cls(
            evidence,
            version,
            baseline,
            tuple(checked for checked in evidence.inputs if checked.result.label != baseline),
            tuple(
                checked.result.label
                for checked in evidence.inputs
                if checked.run.manifest.synthetic
            ),
            {
                checked.result.label: {
                    setting.name: setting
                    for setting in resolved_settings(
                        checked.run.settings, checked.run.plan.cases[0].settings
                    )
                }
                for checked in evidence.inputs
            },
            {
                checked.result.label: {
                    (row.subject, row.metric_id): row for row in checked.run.metrics or ()
                }
                for checked in evidence.inputs
            },
            {
                (row.label, row.kind, row.subject, row.name): row
                for row in evidence.differences.rows
            },
        )

    @property
    def all_synthetic(self) -> bool:
        """Whether every result is synthetic. When some are, the report says which."""
        return len(self.synthetic) == len(self.evidence.inputs)

    def name(self, label: str) -> str:
        """A result's label, marked when it's synthetic, as it appears beside its values."""
        return code(label) + (" (synthetic)" if label in self.synthetic else "")

    def labels(self, labels: Sequence[str]) -> str:
        return series([code(label) for label in labels])

    def sharing(self, label: str) -> tuple[str, ...]:
        """The other results whose runs saved the response `label`'s run did."""
        for shared in self.evidence.differences.shared_responses:
            if label in shared.labels:
                return tuple(other for other in shared.labels if other != label)
        return ()


# The experiment report (R03-T10)


@dataclass(frozen=True)
class CaseView:
    """A case of the experiment, as its report shows it: a case of the current plan, with its
    outcome, attempts, and normalized tables."""

    case: ExperimentPlanCase
    outcome: Literal["succeeded", "failed", "unknown", "not_yet_run"]
    """As the manifest counts it."""
    attempts: tuple[AttemptRecordV1_1, ...]
    """Every attempt of the case, under any plan, by session and then sequence."""
    metrics: tuple[MetricsRow, ...] | None
    """Its `metrics.csv`'s rows, once its attempt succeeded and its response was normalized."""
    settings: tuple[SettingsRow, ...] | None
    """Its `settings.csv`'s rows, with `metrics`."""
    invalid: ErrorDetail | None
    """The `provider.response_invalid` its succeeded attempt's response got, which left it
    `failed` without tables."""

    def __post_init__(self) -> None:
        if (self.metrics is None) != (self.settings is None):
            raise ValueError("a case has both of its normalized tables, or neither")
        if self.metrics is not None and self.outcome != "succeeded":
            raise ValueError("only a case that succeeded has normalized tables")
        if [(a.session, a.sequence) for a in self.attempts] != sorted(
            (a.session, a.sequence) for a in self.attempts
        ):
            raise ValueError("a case's attempts are in the order they were made")

    @property
    def repeat_attempt(self) -> AttemptRecordV1_1 | None:
        """When the case awaits a repeat, its latest possibly charged attempt, whose
        `attempt_id` confirms the repeat; otherwise None (repeating a case)."""
        if any(attempt.outcome == "succeeded" for attempt in self.attempts):
            return None
        charged = [attempt for attempt in self.attempts if attempt.possibly_charged]
        return charged[-1] if charged else None


@dataclass(frozen=True)
class RetiredCaseView:
    """A case a revision retired, as the experiment's record keeps it, with its attempts."""

    case: RetiredCase
    outcome: Literal["succeeded", "failed", "unknown", "not_yet_run"]
    """By its attempts, as the manifest counts a planned case's."""
    attempts: tuple[AttemptRecordV1_1, ...]


@dataclass(frozen=True)
class ExperimentEvidence:
    """What an experiment session's report shows: the current plan and its `experiment.json`,
    each case with its attempts and tables, and what the session's manifest will record.

    The report is written before the manifest, so `artifacts` holds each file the manifest will
    list apart from the report itself.
    """

    plan: PlanV1_1
    plan_number: int
    record: ExperimentRecord
    """The current plan's `experiment.json`."""
    session: int
    synthetic: bool
    approval: Approval
    """How this session approved the current plan."""
    command: ExperimentCommandRecord | None
    outcome: Literal["completed", "partial"]
    error: ErrorDetail | None
    cases: tuple[CaseView, ...]
    """One for each planned case, in the plan's order."""
    retired: tuple[RetiredCaseView, ...]
    """One for each retired case, in the order `experiment.json` gives them."""
    counts: ExperimentManifestCounts
    parsers: tuple[ParserVersion, ...]
    capabilities: Capabilities
    reproducibility: Reproducibility
    artifacts: tuple[ExperimentArtifact, ...]

    def __post_init__(self) -> None:
        if tuple(view.case for view in self.cases) != self.plan.cases:
            raise ValueError("each planned case has one view, in the plan's order")
        if tuple(view.case for view in self.retired) != self.record.retired_cases:
            raise ValueError("each retired case has one view, in the record's order")
        if any(artifact.role == "report" for artifact in self.artifacts):
            raise ValueError("the artifacts are the ones the report links, so not the report")


@dataclass(frozen=True)
class ExperimentContext:
    """An experiment session's report: the evidence, with the baseline's resolved settings, the
    plans' numbers, and what each setting's token means."""

    evidence: ExperimentEvidence
    version: str
    """The Trial Folio version rendering the report."""
    baseline_settings: Mapping[str, Setting]
    """The baseline's resolved settings, by name. The baseline is the plan's first case."""
    plan_numbers: Mapping[str, int]
    """Each plan's number, by its hash."""
    tokens: Mapping[str, str]
    """What each setting's token means. A synthetic experiment sent nothing, so no default of
    Portfolio123's applied to it (DSC-04)."""

    @classmethod
    def of(cls, evidence: ExperimentEvidence, version: str) -> Self:
        (baseline, *_) = evidence.cases
        return cls(
            evidence,
            version,
            {
                setting.name: setting
                for setting in resolved_settings(baseline.settings, baseline.case.settings)
            },
            {entry.plan_hash: entry.plan for entry in evidence.record.plans},
            TOKENS | ({"not_sent": SYNTHETIC_NOT_SENT} if evidence.synthetic else {}),
        )

    @property
    def plan(self) -> PlanV1_1:
        return self.evidence.plan

    @property
    def synthetic(self) -> bool:
        return self.evidence.synthetic

    @property
    def cases(self) -> tuple[CaseView, ...]:
        return self.evidence.cases

    @property
    def baseline(self) -> CaseView:
        return self.evidence.cases[0]

    def baseline_value(self, name: str) -> str:
        return self.baseline_settings[name].value
