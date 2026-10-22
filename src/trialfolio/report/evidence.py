"""What each kind of report is rendered from: the evidence the core gives, and the context each
kind of report's sections read.

- **The evidence.** A run's report reads a `SavedRun`, from `trialfolio.runs`. A review's reads a
  `ReviewEvidence`, and an experiment session's an `ExperimentEvidence`, with a `CaseView` for
  each planned case, a `RetiredCaseView` for each retired one, and, from release 0.4.0, a
  `PlanRanking` for each plan, where its ranking definition came from, which the core builds.
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

from trialfolio.contracts.attempt import AttemptRecordV1_1, AttemptRecordV1_3
from trialfolio.contracts.common import Approval, ErrorDetail
from trialfolio.contracts.experiment_manifest import (
    ExperimentArtifact,
    ExperimentArtifactV1_1,
    ExperimentCommandRecord,
    ExperimentManifestCounts,
)
from trialfolio.contracts.experiment_plan import (
    ExperimentPlanCase,
    ExperimentPlanCaseV1_3,
    PlanV1_1,
    PlanV1_3,
)
from trialfolio.contracts.experiment_record import (
    ExperimentRecord,
    ExperimentRecordV1_1,
    RetiredCase,
    RetiredCaseV1_1,
)
from trialfolio.contracts.manifest import Capabilities, ParserVersion, Reproducibility
from trialfolio.contracts.plan import PlanCase, PlanCaseV1_2, RankingSource
from trialfolio.contracts.ranking_snapshot import RankingSnapshotRecord
from trialfolio.contracts.review_configuration import ReviewConfiguration
from trialfolio.contracts.review_manifest import ReviewArtifact
from trialfolio.contracts.tables import (
    DifferencesRowV1_1,
    MetricsRow,
    SettingsRow,
    SettingsRowV1_1,
)
from trialfolio.differences import AnyDifferencesRow, Differences
from trialfolio.display import series
from trialfolio.report.fragments import Setting, resolved_settings
from trialfolio.report.page import code
from trialfolio.report.vocabulary import SYNTHETIC_NOT_SENT, TOKENS
from trialfolio.review_inputs import ReviewInput
from trialfolio.runs import MANIFEST_PATH, SavedRun

REPORT_PATH: Final = "report.html"


def node_of(row: AnyDifferencesRow) -> str | None:
    """A row's node: a weight row's canonical path, in `differences.csv` 1.1.0, and None on every
    other row."""
    return row.node if isinstance(row, DifferencesRowV1_1) else None


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
    def case(self) -> PlanCase | PlanCaseV1_2:
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
    resolved: Mapping[str, tuple[Setting, ...]]
    """By label: each result's resolved settings, in their order, its weight rows included."""
    settings: Mapping[str, Mapping[str, Setting]]
    """By label, and then by setting name, its weight rows apart: each weight row has the name
    `ranking_weight`, so only its node tells it apart."""
    metrics: Mapping[str, Mapping[tuple[str, str], MetricsRow]]
    """By label, and then by subject and `metric_id`."""
    rows: Mapping[tuple[str, str, str | None, str], AnyDifferencesRow]
    """`differences.csv`'s rows but its weight rows, by label, kind, subject, and name."""

    @classmethod
    def of(cls, evidence: ReviewEvidence, version: str) -> Self:
        baseline = evidence.configuration.baseline
        resolved = {
            checked.result.label: resolved_settings(
                checked.run.settings, checked.run.plan.cases[0].settings
            )
            for checked in evidence.inputs
        }
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
            resolved,
            {
                label: {setting.name: setting for setting in settings if setting.node is None}
                for label, settings in resolved.items()
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
                if node_of(row) is None
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

    case: ExperimentPlanCase | ExperimentPlanCaseV1_3
    outcome: Literal["succeeded", "failed", "unknown", "not_yet_run"]
    """As the manifest counts it."""
    attempts: tuple[AttemptRecordV1_1 | AttemptRecordV1_3, ...]
    """Every attempt of the case, under any plan, by session and then sequence."""
    metrics: tuple[MetricsRow, ...] | None
    """Its `metrics.csv`'s rows, once its attempt succeeded and its response was normalized."""
    settings: tuple[SettingsRow, ...] | tuple[SettingsRowV1_1, ...] | None
    """Its `settings.csv`'s rows, with `metrics`."""
    invalid: ErrorDetail | None
    """The `provider.response_invalid` its latest succeeded attempt's response got, which left
    it without tables, awaiting a repeat."""
    identical_to: str | None = None
    """With `invalid`, for a stale backtest, the `case_id` of the case before it in its session,
    whose response it repeats (D-45)."""

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
    def repeat_attempt(self) -> AttemptRecordV1_1 | AttemptRecordV1_3 | None:
        """When the case awaits a repeat, its latest possibly charged attempt, whose
        `attempt_id` confirms the repeat; otherwise None (repeating a case). A case whose
        succeeded attempt's response failed validation awaits one, and its succeeded attempt
        can be that attempt (D-45)."""
        if self.invalid is None and any(a.outcome == "succeeded" for a in self.attempts):
            return None
        charged = [attempt for attempt in self.attempts if attempt.possibly_charged]
        return charged[-1] if charged else None

    @property
    def invalid_success(self) -> bool:
        """Whether the case awaits a repeat because its latest possibly charged attempt
        succeeded, and its response failed validation, which `invalid` gives (D-45)."""
        attempt = self.repeat_attempt
        return attempt is not None and attempt.outcome == "succeeded"


@dataclass(frozen=True)
class RetiredCaseView:
    """A case a revision retired, as the experiment's record keeps it, with its attempts."""

    case: RetiredCase | RetiredCaseV1_1
    outcome: Literal["succeeded", "failed", "unknown", "not_yet_run"]
    """By its attempts, as the manifest counts a planned case's."""
    attempts: tuple[AttemptRecordV1_1 | AttemptRecordV1_3, ...]


@dataclass(frozen=True)
class PlanRanking:
    """Where a plan of the experiment took its ranking definition from, as the report shows it:
    its `ranking_source`, and, for a snapshot, the record its `snapshot.json` copies (release
    0.4.0, R04-T11)."""

    number: int
    source: RankingSource | None
    """None for a plan whose ranking isn't a definition."""
    snapshot: RankingSnapshotRecord | None

    def __post_init__(self) -> None:
        if (self.snapshot is None) != (self.source is None or self.source.form != "snapshot"):
            raise ValueError(
                "a plan has its snapshot's record exactly when a snapshot names its ranking"
            )


@dataclass(frozen=True)
class ExperimentEvidence:
    """What an experiment session's report shows: the current plan and its `experiment.json`,
    each case with its attempts and tables, and what the session's manifest will record.

    The report is written before the manifest, so `artifacts` holds each file the manifest will
    list apart from the report itself.
    """

    plan: PlanV1_1 | PlanV1_3
    plan_number: int
    record: ExperimentRecord | ExperimentRecordV1_1
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
    artifacts: tuple[ExperimentArtifact | ExperimentArtifactV1_1, ...]
    rankings: tuple[PlanRanking, ...] = ()
    """Each plan's, oldest first, once a plan of the experiment has a ranking definition, as its
    `experiment.json` 1.1.0 shows; empty before."""

    def __post_init__(self) -> None:
        if tuple(view.case for view in self.cases) != self.plan.cases:
            raise ValueError("each planned case has one view, in the plan's order")
        if tuple(view.case for view in self.retired) != self.record.retired_cases:
            raise ValueError("each retired case has one view, in the record's order")
        ranked = isinstance(self.record, ExperimentRecordV1_1)
        numbers = tuple(entry.plan for entry in self.record.plans) if ranked else ()
        if tuple(ranking.number for ranking in self.rankings) != numbers:
            raise ValueError("an experiment with a ranking definition gives each plan's source")
        if any(artifact.role == "report" for artifact in self.artifacts):
            raise ValueError("the artifacts are the ones the report links, so not the report")


@dataclass(frozen=True)
class ExperimentContext:
    """An experiment session's report: the evidence, with the baseline's resolved settings, the
    plans' numbers, and what each setting's token means."""

    evidence: ExperimentEvidence
    version: str
    """The Trial Folio version rendering the report."""
    baseline_settings: tuple[Setting, ...]
    """The baseline's resolved settings, in their order, each weight row of a ranking definition
    included. The baseline is the plan's first case."""
    baseline_by_name: Mapping[str, Setting]
    """The baseline's resolved settings but its weight rows, by name: each weight row has the
    name `ranking_weight`, so only its node tells it apart."""
    plan_numbers: Mapping[str, int]
    """Each plan's number, by its hash."""
    tokens: Mapping[str, str]
    """What each setting's token means. A synthetic experiment sent nothing, so no default of
    Portfolio123's applied to it (DSC-04)."""

    @classmethod
    def of(cls, evidence: ExperimentEvidence, version: str) -> Self:
        (baseline, *_) = evidence.cases
        settings = resolved_settings(baseline.settings, baseline.case.settings)
        return cls(
            evidence,
            version,
            settings,
            {setting.name: setting for setting in settings if setting.node is None},
            {entry.plan_hash: entry.plan for entry in evidence.record.plans},
            TOKENS | ({"not_sent": SYNTHETIC_NOT_SENT} if evidence.synthetic else {}),
        )

    @property
    def plan(self) -> PlanV1_1 | PlanV1_3:
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
        return self.baseline_by_name[name].value
