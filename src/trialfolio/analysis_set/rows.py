"""`analysis.csv`'s rows: each calculated value written in its unit, with its decimals, flags,
inputs, and provenance (docs/contracts.md, analysis.csv).

`analysis_row` writes one value: a percent, percentage points, or a ratio rounded once to the
result's `precision`, a zero without a sign; a count or a number of days whole; and a date as a
date. Its flags are its analysis's, on every row of it, available or not, and `not_recovered` on
an available time below a peak that runs to its segment's end. Every row is `calculated` and
`inferred`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from trialfolio.analysis_set.arithmetic import Calculated, written
from trialfolio.analysis_set.reconciliation import Reconciliation
from trialfolio.contracts.tables import (
    ANALYSIS_SET_1_0_0,
    AnalysisFlag,
    AnalysisRow,
    AnalysisSubject,
)

ANALYSIS_SET_VERSION = "1.0.0"
"""The analysis set's version, recorded with every value it gives."""


@dataclass(frozen=True)
class RowSource:
    """What every row of one result shares."""

    label: str
    precision: int
    trialfolio_version: str
    source_artifact: str


@dataclass(frozen=True)
class Place:
    """Where a row is: its segment, analysis, subject, and window."""

    segment: str
    analysis: str
    subject: AnalysisSubject | None
    window_days: int | None = None


def analysis_row(
    source: RowSource,
    place: Place,
    calculated: Calculated,
    reconciliation: tuple[str | None, Reconciliation | None] = (None, None),
) -> AnalysisRow:
    """One row of `analysis.csv`. `reconciliation` gives a reconciled value's `reported_value`
    and `reconciliation`, and is empty on every other value."""
    definition = ANALYSIS_SET_1_0_0[place.analysis]
    available = calculated.value is not None
    flags: list[AnalysisFlag] = [] if definition.flag is None else [definition.flag]
    if calculated.not_recovered:
        flags.append("not_recovered")
    dates = calculated.dates if available else None
    reported, agreement = reconciliation
    return AnalysisRow(
        label=source.label,
        analysis_set=ANALYSIS_SET_VERSION,
        segment=place.segment,
        analysis=place.analysis,
        subject=place.subject,
        window_days=place.window_days,
        value=_text(calculated.value, source.precision),
        unit=definition.unit,
        decimals=_decimals(calculated.value, definition.unit, source.precision),
        availability="available" if available else "unavailable",
        unavailable_reason=calculated.reason,
        observations=calculated.observations,
        period_start=None if dates is None else dates[0],
        period_end=None if dates is None else dates[1],
        reported_value=reported,
        reconciliation=agreement,
        flags=tuple(flags),
        inputs=definition.inputs(place.analysis, place.subject),
        origin="calculated",
        provenance="inferred",
        trialfolio_version=source.trialfolio_version,
        source_artifact=source.source_artifact,
    )


def _text(value: Decimal | int | date | None, precision: int) -> str | None:
    match value:
        case None:
            return None
        case Decimal():
            return written(value, precision)
        case date():
            return value.isoformat()
        case int():
            return str(value)


def _decimals(value: Decimal | int | date | None, unit: str, precision: int) -> int | None:
    if value is None or unit == "date":
        return None
    return 0 if unit in ("count", "days") else precision
