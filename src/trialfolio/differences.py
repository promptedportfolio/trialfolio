"""The comparison core: each result's settings and metrics compared with the baseline's, as the
rows of `differences.csv` (release 0.2.0, R02-T06; docs/contracts.md, differences between screen
runs). Its rules are the review's method, `screen-run-differences` version 1.

`compare` compares each result except the baseline, in the configuration's order, and gives its
23 setting rows, then its 20 metric rows:

- **Settings.** A setting is `same` when its two values read the same, `intended_change` when
  they don't and the result declares it, `unexplained_mismatch` when they don't and it doesn't,
  and `unknown` when either run lacks it. A run without tables is compared from its plan. A row
  carries the flags either run's row has, and its comparison's own.
- **Metrics.** A metric is `unavailable` when either value is. Otherwise it's `not_comparable`,
  with the first reason that applies, when the units, the benchmark, or the period differ, as
  its row of the contract's table says, and `differenced` when none does. A difference is
  `value - baseline_value`, rounded half to even to the smaller of the two values' decimal
  counts, in percentage points for percent metrics, and in days for dates.
- **Identical responses.** Every metric row of a result whose saved response is byte-identical
  to another result's, the baseline's included, is flagged `identical_source`.

Nothing here logs: the rows hold configuration values, formulas, and results. A warning that
results share a response is the command's to log, by their positions.
"""

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import MAX_EMAX, MAX_PREC, MIN_EMIN, ROUND_HALF_EVEN, Context, Decimal
from typing import Final, Self, get_args

from trialfolio.contracts.common import CRITICAL_CATEGORIES, FlagCode
from trialfolio.contracts.review_manifest import MetricRowCounts, SettingRowCounts
from trialfolio.contracts.screen_settings import SCREEN_SETTINGS, ScreenSetting, check_value_text
from trialfolio.contracts.tables import (
    FLAGGING,
    DifferenceReason,
    DifferencesRow,
    MetricClassification,
    MetricsRow,
    SettingClassification,
)
from trialfolio.normalization import METRICS, Metric, setting_text
from trialfolio.review_inputs import ReviewInput

METHOD: Final = "screen-run-differences"
METHOD_VERSION: Final = 1
"""The review manifest's method: these rules. A change that could change a row makes a new
version."""

DIFFERENCES_PATH: Final = "normalized/differences.csv"

_FLAG_ORDER: Final[tuple[FlagCode, ...]] = get_args(FlagCode)
"""A row's flags are written in the order of the flag codes table."""

_COVERAGE: Final = frozenset({"coverage_start", "coverage_end", "coverage_periods"})
"""The coverage rows, which are the period, so they're differenced whatever the periods are."""

_EXACT: Final = Context(prec=MAX_PREC, rounding=ROUND_HALF_EVEN, Emax=MAX_EMAX, Emin=MIN_EMIN)
"""Subtracts two decimals exactly, whatever their digits, and rounds half to even."""


@dataclass(frozen=True)
class RunSetting:
    """One setting of a run: its value as `settings.csv` writes it, and the flags its row
    carries."""

    value: str
    flags: tuple[FlagCode, ...]


@dataclass(frozen=True)
class ComparedRun:
    """One result, as the comparison reads it."""

    label: str
    settings: Mapping[str, RunSetting]
    """By setting name: its `settings.csv` rows, or its plan's for a run without tables. A
    setting missing from the run is absent, which no complete 1.0.0 screen run gives."""
    metrics: Mapping[tuple[str, str], MetricsRow]
    """By subject and `metric_id`: its `metrics.csv` rows. Empty for a run without tables."""
    response: str | None
    """The `artifact_id` of its saved response; None when it has none."""
    intended_changes: Mapping[str, str]
    """Each setting the result declares as an intended change, with the reason it gives."""

    @classmethod
    def of(cls, checked: ReviewInput) -> Self:
        """A result's run, as the input check read it."""
        run = checked.run
        if run.settings is not None:
            settings = {row.setting: RunSetting(row.value, row.flags) for row in run.settings}
        else:
            (case,) = run.plan.cases
            settings = {
                row.setting: RunSetting(setting_text(row.value), row.flags) for row in case.settings
            }
        return cls(
            label=checked.result.label,
            settings=settings,
            metrics={(row.subject, row.metric_id): row for row in run.metrics or ()},
            response=checked.reviewed.response,
            intended_changes={
                change.setting: change.reason for change in checked.result.intended_changes or ()
            },
        )


@dataclass(frozen=True)
class SharedResponse:
    """Results whose runs have one saved response, byte for byte, in the configuration's
    order."""

    response: str
    """Its `artifact_id`."""
    labels: tuple[str, ...]
    positions: tuple[int, ...]
    """Their positions in `results`, from 1, as logs name them."""


@dataclass(frozen=True)
class Differences:
    """The rows of `differences.csv`, and the results that share a response."""

    rows: tuple[DifferencesRow, ...]
    shared_responses: tuple[SharedResponse, ...]

    @property
    def setting_counts(self) -> SettingRowCounts:
        """The review manifest's `counts.settings`."""
        rows = [row for row in self.rows if row.kind == "setting"]
        counted = Counter(row.classification for row in rows)
        return SettingRowCounts(
            same=counted["same"],
            intended_change=counted["intended_change"],
            unexplained_mismatch=counted["unexplained_mismatch"],
            unknown=counted["unknown"],
            flagged=sum(row.flagged for row in rows),
        )

    @property
    def metric_counts(self) -> MetricRowCounts:
        """The review manifest's `counts.metrics`."""
        rows = [row for row in self.rows if row.kind == "metric"]
        counted = Counter(row.classification for row in rows)
        return MetricRowCounts(
            differenced=counted["differenced"],
            not_comparable=counted["not_comparable"],
            unavailable=counted["unavailable"],
            flagged=sum(row.flagged for row in rows),
        )


def compare(baseline: str, runs: Sequence[ComparedRun]) -> Differences:
    """Compares each of `runs` except the one labeled `baseline` with it, in order.

    Raises `ValueError` unless the labels are unique, and one of them is `baseline`.
    """
    labels = [run.label for run in runs]
    if len(set(labels)) != len(labels) or baseline not in labels:
        raise ValueError("each result has its own label, and one of them is the baseline")
    base = runs[labels.index(baseline)]
    shared = _shared_responses(runs)
    sharing = {position for group in shared for position in group.positions}
    rows: list[DifferencesRow] = []
    for position, run in enumerate(runs, start=1):
        if run is base:
            continue
        rows.extend(_setting_row(setting, base, run) for setting in SCREEN_SETTINGS)
        identical = position in sharing
        rows.extend(_metric_row(metric, base, run, identical) for metric in METRICS)
    return Differences(tuple(rows), shared)


def _shared_responses(runs: Sequence[ComparedRun]) -> tuple[SharedResponse, ...]:
    """Each response that more than one result's run saved, in the order it first appears. Two
    runs with no saved response share none."""
    groups: dict[str, list[int]] = {}
    for index, run in enumerate(runs):
        if run.response is not None:
            groups.setdefault(run.response, []).append(index)
    return tuple(
        SharedResponse(
            response,
            tuple(runs[index].label for index in indexes),
            tuple(index + 1 for index in indexes),
        )
        for response, indexes in groups.items()
        if len(indexes) > 1
    )


def _setting_row(setting: ScreenSetting, base: ComparedRun, run: ComparedRun) -> DifferencesRow:
    before, after = base.settings.get(setting.name), run.settings.get(setting.name)
    declared = run.intended_changes.get(setting.name)
    critical = setting.category in CRITICAL_CATEGORIES
    classification: SettingClassification
    if before is None or after is None:
        classification = "unknown"
    elif check_value_text(setting, before.value) == check_value_text(setting, after.value):
        # A list or a ranking reads as JSON, and anything else as its text.
        classification = "same"
    else:
        classification = "unexplained_mismatch" if declared is None else "intended_change"
    flags = set[FlagCode](setting.flags)
    for row in (before, after):
        if row is not None:
            flags.update(row.flags)
    if critical and classification == "unexplained_mismatch":
        flags.add("critical_unexplained_mismatch")
    if critical and classification == "unknown":
        flags.add("critical_unknown")
    if classification == "same" and declared is not None:
        flags.add("intended_change_not_observed")
    return DifferencesRow(
        label=run.label,
        baseline_label=base.label,
        kind="setting",
        name=setting.name,
        subject=None,
        category=setting.category,
        critical=critical,
        baseline_value=None if before is None else before.value,
        value=None if after is None else after.value,
        unit=setting.unit,
        classification=classification,
        difference=None,
        difference_unit=None,
        difference_decimals=None,
        reason=None,
        declared_reason=declared,
        flagged=_flagged(flags),
        flags=_ordered(flags),
    )


def _metric_row(
    metric: Metric, base: ComparedRun, run: ComparedRun, identical: bool
) -> DifferencesRow:
    key = (metric.subject, metric.metric_id)
    before, after = base.metrics.get(key), run.metrics.get(key)
    flags: set[FlagCode] = {"identical_source"} if identical else set()
    classification: MetricClassification
    reason: DifferenceReason | None
    difference: tuple[str, str, int] | None = None
    if before is None or after is None or before.value is None or after.value is None:
        classification, reason = "unavailable", "input_unavailable"
    else:
        reason = _not_comparable(metric, before, after, base, run)
        if reason is not None:
            classification = "not_comparable"
        else:
            classification = "differenced"
            difference = _difference(metric.unit, before.value, after.value)
    return DifferencesRow(
        label=run.label,
        baseline_label=base.label,
        kind="metric",
        name=metric.metric_id,
        subject=metric.subject,
        category=None,
        critical=None,
        baseline_value=None if before is None else before.value,
        value=None if after is None else after.value,
        unit=metric.unit,
        classification=classification,
        difference=None if difference is None else difference[0],
        difference_unit=None if difference is None else difference[1],
        difference_decimals=None if difference is None else difference[2],
        reason=reason,
        declared_reason=None,
        flagged=_flagged(flags),
        flags=_ordered(flags),
    )


def _not_comparable(
    metric: Metric, before: MetricsRow, after: MetricsRow, base: ComparedRun, run: ComparedRun
) -> DifferenceReason | None:
    """The first reason the two values can't be differenced, or None when they can."""
    if before.unit != after.unit:
        return "different_unit"
    if metric.benchmark_relative and before.benchmark != after.benchmark:
        return "different_benchmark"
    if metric.subject == "benchmark" and not _same_benchmark(base, run):
        return "different_benchmark"
    if metric.metric_id in _COVERAGE:
        return None
    periods = [(row.period_start, row.period_end) for row in (before, after)]
    if any(None in period for period in periods):
        return "unknown_period"
    if periods[0] != periods[1]:
        return "different_period"
    return None


def _same_benchmark(base: ComparedRun, run: ComparedRun) -> bool:
    """Whether the runs' `benchmark` settings are known and the same."""
    before, after = base.settings.get("benchmark"), run.settings.get("benchmark")
    return before is not None and after is not None and before.value == after.value


def _difference(unit: str, before: str, after: str) -> tuple[str, str, int]:
    """`after - before` as written, its unit, and its decimal places."""
    if unit == "date":
        return str((date.fromisoformat(after) - date.fromisoformat(before)).days), "days", 0
    if unit == "count":
        return str(int(after) - int(before)), "count", 0
    decimals = min(_decimals(before), _decimals(after))
    exact = _EXACT.subtract(Decimal(after), Decimal(before))
    rounded = _EXACT.quantize(exact, Decimal(1).scaleb(-decimals))
    if rounded.is_zero():
        # A difference of zero is written without a sign, never `-0.0`.
        rounded = rounded.copy_abs()
    return format(rounded, "f"), "pp" if unit == "percent" else unit, decimals


def _decimals(text: str) -> int:
    """The digits after the decimal point: the value's `source_decimals`."""
    return len(text.partition(".")[2])


def _flagged(flags: Collection[str]) -> bool:
    return not FLAGGING.isdisjoint(flags)


def _ordered(flags: Collection[str]) -> tuple[FlagCode, ...]:
    return tuple(code for code in _FLAG_ORDER if code in flags)
