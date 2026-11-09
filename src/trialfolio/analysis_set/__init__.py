"""Analysis set 1.0.0: the fixed, versioned descriptive analyses of each result's dated series
(docs/methodology.md, analysis set 1.0.0; docs/contracts.md, analysis.csv).

`analysis_rows` gives a result's `analysis.csv` rows, calculated from its `series.csv` alone, by
the methods methodology.md defines, with its `precision`, its `metrics.csv`'s coverage and
reported metrics, and the plan's period splits: the `full` segment's 94 rows, then each split
segment's 31, `split-0` first. Every row is written, an unavailable one included. Every value is
calculated in `decimal`, with 50 significant digits, and rounded once, half to even.

The package's modules, each importing only those before it:

- `arithmetic`, the context every calculation runs in, a value before it's written, and its
  rounding.
- `inputs`, a result's daily levels, periods, coverage, and reported metrics, read from its
  tables' rows.
- `segments`, the `full` segment and the split segments, with their dates, levels, periods, and
  availability.
- `period_returns`, the period-return analyses, over a segment's periods.
- `daily_levels`, the daily-level analyses, over a segment's levels, and the maximum drawdown's
  peak and trough.
- `rolling`, the rolling returns, over the `full` segment's levels, for each window length.
- `reconciliation`, each reconciled value against the metric Portfolio123 reports.
- `rows`, each value written as a row of `analysis.csv`.

Nothing here logs: the values come from a response's series.
"""

from collections.abc import Sequence
from datetime import date
from decimal import localcontext

from trialfolio.analysis_set.arithmetic import CONTEXT, Calculated
from trialfolio.analysis_set.daily_levels import level_values
from trialfolio.analysis_set.inputs import Result, read_result
from trialfolio.analysis_set.period_returns import period_values
from trialfolio.analysis_set.reconciliation import Reconciliation, reconciled
from trialfolio.analysis_set.rolling import rolling_values
from trialfolio.analysis_set.rows import ANALYSIS_SET_VERSION, Place, RowSource, analysis_row
from trialfolio.analysis_set.segments import Segment, segments
from trialfolio.contracts.tables import (
    ANALYSIS_SET_1_0_0,
    RECONCILED_1_0_0,
    ROLLING_WINDOWS_1_0_0,
    AnalysisRow,
    AnalysisSubject,
    MetricsRow,
    SeriesRow,
)


def analysis_rows(
    series: Sequence[SeriesRow],
    metrics: Sequence[MetricsRow],
    *,
    precision: int,
    splits: Sequence[date],
    trialfolio_version: str,
) -> tuple[AnalysisRow, ...]:
    """A result's `analysis.csv` rows, in order, from its `series.csv` and `metrics.csv` rows.

    `precision` is its `precision` setting, the decimals of every value in percent, percentage
    points, or a ratio; `splits` the plan's declared split dates, in increasing order; and
    `trialfolio_version` the version that calculates them. Each row's `label` and
    `source_artifact` are its series'.
    """
    with localcontext(CONTEXT):
        result = read_result(series, metrics)
        source = RowSource(
            label=result.label,
            precision=precision,
            trialfolio_version=trialfolio_version,
            source_artifact=result.source_artifact,
        )
        rows: list[AnalysisRow] = []
        for segment in segments(result, splits):
            rows.extend(_segment_rows(result, segment, source))
        return tuple(rows)


def _segment_rows(result: Result, segment: Segment, source: RowSource) -> list[AnalysisRow]:
    """A segment's rows: the period returns', then the daily levels', each analysis's subjects in
    order, and in the `full` segment, the rolling returns' for each window length."""
    values: dict[tuple[str, AnalysisSubject | None], Calculated] = {}
    if segment.reason is None:
        values.update(period_values(segment))
        values.update(level_values(segment, source.precision))
    rows: list[AnalysisRow] = []
    for name, definition in ANALYSIS_SET_1_0_0.items():
        if definition.windows or not _in(definition.segments, segment.name):
            continue
        for subject in definition.subjects:
            calculated = values.get((name, subject), Calculated(None, segment.reason))
            place = Place(segment.name, name, subject)
            reconciliation = _reconciliation(result, segment, place, calculated, source)
            rows.append(analysis_row(source, place, calculated, reconciliation))
    if segment.name == "full":
        rows.extend(_rolling_rows(segment, source))
    return rows


def _in(where: str, segment: str) -> bool:
    return where == "any" or (where == "full") == (segment == "full")


def _rolling_rows(segment: Segment, source: RowSource) -> list[AnalysisRow]:
    values = rolling_values(segment.levels, ROLLING_WINDOWS_1_0_0)
    rows: list[AnalysisRow] = []
    for window in ROLLING_WINDOWS_1_0_0:
        for name, definition in ANALYSIS_SET_1_0_0.items():
            if not definition.windows:
                continue
            for subject in definition.subjects:
                place = Place(segment.name, name, subject, window)
                rows.append(analysis_row(source, place, values[(name, subject, window)]))
    return rows


def _reconciliation(
    result: Result, segment: Segment, place: Place, calculated: Calculated, source: RowSource
) -> tuple[str | None, Reconciliation | None]:
    subject = place.subject
    if segment.name != "full" or place.analysis not in RECONCILED_1_0_0:
        return (None, None)
    # A reconciled analysis's subjects are the strategy and the benchmark, each a metric's.
    if subject != "strategy" and subject != "benchmark":
        return (None, None)
    reported = result.reported.get((place.analysis, subject))
    agreement = reconciled(
        place.analysis, subject, calculated, reported, segment.levels, source.precision
    )
    return (reported, agreement)


__all__ = ["ANALYSIS_SET_VERSION", "analysis_rows"]
