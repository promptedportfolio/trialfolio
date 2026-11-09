"""methodology.md's hand-checkable example, written by hand from its tables, and the reading of a
response and its configuration into `series.csv`'s and `analysis.csv`'s rows (release 0.5.0, test
pairing).

`EXAMPLE_FULL` gives each of the `full` segment's 94 values of `responses/hand-checkable.json`, in
`analysis.csv`'s order, and `EXAMPLE_SPLIT` each of `split-0`'s and `split-1`'s 31 with the split
on 2024-01-05, as methodology.md's [hand-checkable example](../../docs/methodology.md) gives them,
never as the code calculates them: `tests/core/test_analysis_set.py` checks Trial Folio's rows
against them, and `tests/core/test_analysis_reference.py` the reference calculation's. Each is an
`Expected` row: its analysis, subject, window, value as `analysis.csv` writes it, unit, decimals,
observations, dates, reason, and flags.

`tables_of` reads a response, as the core does, into a result's `series.csv` and `metrics.csv`
rows, with the dates and splits its configuration gives, and `analysed` into its `analysis.csv`
rows, labeled `LABEL`, from the response's `artifact_id`, by the installed version.

R05-T06 wrote it, for R05-AC01, R05-AC03, and R05-AC08.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from importlib.metadata import version
from typing import Final

from tests.support.paths import RESPONSES, SCREEN_CONFIGS
from trialfolio.analysis_set import analysis_rows
from trialfolio.configuration import read_screen_configuration_v1_2
from trialfolio.contracts.screen_configuration import (
    ScreenConfiguration,
    ScreenConfigurationV1_1,
    ScreenConfigurationV1_2,
)
from trialfolio.contracts.tables import AnalysisRow, MetricsRow, SeriesRow
from trialfolio.normalization import metrics_rows, read_response, series_rows

LABEL: Final = "case-0123456789abcdef"
"""The case's `case_id` that labels the rows of a core test's result."""

WINDOWS: Final = (7, 30, 90, 180, 365)
LONG_WINDOWS: Final = WINDOWS[1:]
"""The windows of 30 days or more, which none of the example's fit."""


@dataclass(frozen=True)
class Expected:
    """One row of `analysis.csv`, as a test writes it by hand."""

    analysis: str
    subject: str | None
    window_days: int | None
    value: str | None
    unit: str
    decimals: int | None
    observations: int | None
    start: str | None = None
    end: str | None = None
    reason: str | None = None
    flags: tuple[str, ...] = ()


def _window(length: int) -> tuple[Expected, ...]:
    """A window length none of the example's windows fit: no window, so each count is 0, and each
    summary unavailable, with `too_few_observations` and 0 observations."""
    counts = tuple(
        Expected(name, None, length, "0", "count", 0, 0)
        for name in ("rolling_window_count", "rolling_non_overlapping_count")
    )
    summaries = tuple(
        Expected(
            name,
            subject,
            length,
            None,
            "percent",
            None,
            0,
            reason="too_few_observations",
            flags=("overlapping_windows",),
        )
        for name in ("rolling_mean", "rolling_median", "rolling_p10", "rolling_p90")
        + ("rolling_worst",)
        for subject in ("strategy", "benchmark")
    )
    beating = Expected(
        "rolling_share_beating",
        "excess",
        length,
        None,
        "percent",
        None,
        0,
        reason="too_few_observations",
        flags=("overlapping_windows",),
    )
    return (*counts, *summaries, beating)


_FULL = ("2024-01-01", "2024-01-12")
_FIRST = ("2024-01-01", "2024-01-08")
_SECOND = ("2024-01-08", "2024-01-12")
_SEVEN = ("overlapping_windows",)

EXAMPLE_FULL: Final = (
    # The period returns: 2 periods, from 2024-01-01 to 2024-01-12.
    Expected("period_count", None, None, "2", "count", 0, 2, *_FULL),
    Expected("mean_period_return", "strategy", None, "5.0000", "percent", 4, 2, *_FULL),
    Expected("mean_period_return", "benchmark", None, "0.5000", "percent", 4, 2, *_FULL),
    Expected("mean_period_return", "excess", None, "4.5000", "percent", 4, 2, *_FULL),
    Expected("median_period_return", "strategy", None, "5.0000", "percent", 4, 2, *_FULL),
    Expected("median_period_return", "benchmark", None, "0.5000", "percent", 4, 2, *_FULL),
    Expected("median_period_return", "excess", None, "4.5000", "percent", 4, 2, *_FULL),
    Expected("best_period_return", "strategy", None, "10.0000", "percent", 4, 2, *_SECOND),
    Expected("best_period_return", "benchmark", None, "1.0000", "percent", 4, 2, *_FIRST),
    Expected("best_period_return", "excess", None, "10.0000", "percent", 4, 2, *_SECOND),
    Expected("worst_period_return", "strategy", None, "0.0000", "percent", 4, 2, *_FIRST),
    Expected("worst_period_return", "benchmark", None, "0.0000", "percent", 4, 2, *_SECOND),
    Expected("worst_period_return", "excess", None, "-1.0000", "percent", 4, 2, *_FIRST),
    Expected("positive_excess_share", "excess", None, "50.0000", "percent", 4, 2, *_FULL),
    # √60.5, 4.5 / √60.5, and 4.5 / 5.5.
    Expected(
        "tracking_error", "excess", None, "7.7782", "percent", 4, 2, *_FULL, flags=("descriptive",)
    ),
    Expected(
        "information_ratio", "excess", None, "0.5785", "ratio", 4, 2, *_FULL, flags=("descriptive",)
    ),
    Expected(
        "excess_t_value", "excess", None, "0.8182", "ratio", 4, 2, *_FULL, flags=("descriptive",)
    ),
    # The daily levels: 10 levels, from 2024-01-01 to 2024-01-12, 11 days.
    Expected("total_return", "strategy", None, "10.0000", "percent", 4, 10, *_FULL),
    Expected("total_return", "benchmark", None, "1.0000", "percent", 4, 10, *_FULL),
    Expected("total_return_difference", "excess", None, "9.0000", "pp", 4, 10, *_FULL),
    Expected("annualized_return", "strategy", None, None, "percent", None, 10, reason="too_short"),
    Expected("annualized_return", "benchmark", None, None, "percent", None, 10, reason="too_short"),
    Expected(
        "annualized_return_difference",
        "excess",
        None,
        None,
        "pp",
        None,
        None,
        reason="input_unavailable",
    ),
    Expected(
        "max_drawdown", "strategy", None, "-4.8077", "percent", 4, 10, "2024-01-04", "2024-01-05"
    ),
    Expected(
        "max_drawdown", "benchmark", None, "-1.9608", "percent", 4, 10, "2024-01-04", "2024-01-05"
    ),
    Expected("max_drawdown_recovery", "strategy", None, "2024-01-10", "date", None, 10, *_FULL),
    Expected("max_drawdown_recovery", "benchmark", None, "2024-01-09", "date", None, 10, *_FULL),
    Expected(
        "longest_drawdown_days", "strategy", None, "6", "days", 0, 10, "2024-01-04", "2024-01-10"
    ),
    Expected(
        "longest_drawdown_days", "benchmark", None, "5", "days", 0, 10, "2024-01-04", "2024-01-09"
    ),
    # The 7-day windows: 5, from 2024-01-01 to 2024-01-08 through 2024-01-05 to 2024-01-12.
    Expected("rolling_window_count", None, 7, "5", "count", 0, 5, *_FULL),
    Expected("rolling_non_overlapping_count", None, 7, "1", "count", 0, 5, *_FULL),
    Expected("rolling_mean", "strategy", 7, "2.8258", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_mean", "benchmark", 7, "0.9941", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_median", "strategy", 7, "0.9804", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_median", "benchmark", 7, "1.0000", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_p10", "strategy", 7, "-1.1538", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_p10", "benchmark", 7, "0.3960", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_p90", "strategy", 7, "8.2508", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_p90", "benchmark", 7, "1.5881", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_worst", "strategy", 7, "-1.9231", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected("rolling_worst", "benchmark", 7, "0.0000", "percent", 4, 5, *_FULL, flags=_SEVEN),
    Expected(
        "rolling_share_beating", "excess", 7, "40.0000", "percent", 4, 5, *_FULL, flags=_SEVEN
    ),
    *(row for length in LONG_WINDOWS for row in _window(length)),
)
"""The `full` segment's 94 rows of `hand-checkable.json`."""


def _too_few(analysis: str, subject: str, observations: int, unit: str = "percent") -> Expected:
    flags = ("descriptive",) if analysis in _DESCRIPTIVE else ()
    return Expected(
        analysis,
        subject,
        None,
        None,
        unit,
        None,
        observations,
        reason="too_few_observations",
        flags=flags,
    )


_DESCRIPTIVE = ("tracking_error", "information_ratio", "excess_t_value")
_SUMMARIES = (
    "mean_period_return",
    "median_period_return",
    "best_period_return",
    "worst_period_return",
)

_SPLIT_0 = (
    # From 2024-01-01 to 2024-01-05: 4 days of 11, and no period, since the first spans the date.
    Expected(
        "coverage_share", None, None, "36.3636", "percent", 4, None, "2024-01-01", "2024-01-05"
    ),
    Expected("period_count", None, None, "0", "count", 0, 0),
    Expected("spanning_period_count", None, None, "1", "count", 0, 2, "2024-01-01", "2024-01-05"),
    *(
        _too_few(name, subject, 0)
        for name in _SUMMARIES
        for subject in ("strategy", "benchmark", "excess")
    ),
    _too_few("positive_excess_share", "excess", 0),
    _too_few("tracking_error", "excess", 0),
    _too_few("information_ratio", "excess", 0, "ratio"),
    _too_few("excess_t_value", "excess", 0, "ratio"),
    # Its levels, 2024-01-01 to 2024-01-05.
    Expected(
        "total_return", "strategy", None, "-1.0000", "percent", 4, 5, "2024-01-01", "2024-01-05"
    ),
    Expected(
        "total_return", "benchmark", None, "0.0000", "percent", 4, 5, "2024-01-01", "2024-01-05"
    ),
    Expected(
        "total_return_difference", "excess", None, "-1.0000", "pp", 4, 5, "2024-01-01", "2024-01-05"
    ),
    Expected("annualized_return", "strategy", None, None, "percent", None, 5, reason="too_short"),
    Expected("annualized_return", "benchmark", None, None, "percent", None, 5, reason="too_short"),
    Expected(
        "annualized_return_difference",
        "excess",
        None,
        None,
        "pp",
        None,
        None,
        reason="input_unavailable",
    ),
    Expected(
        "max_drawdown", "strategy", None, "-4.8077", "percent", 4, 5, "2024-01-04", "2024-01-05"
    ),
    Expected(
        "max_drawdown", "benchmark", None, "-1.9608", "percent", 4, 5, "2024-01-04", "2024-01-05"
    ),
    Expected(
        "max_drawdown_recovery", "strategy", None, None, "date", None, 5, reason="not_recovered"
    ),
    Expected(
        "max_drawdown_recovery", "benchmark", None, None, "date", None, 5, reason="not_recovered"
    ),
    Expected(
        "longest_drawdown_days", "strategy", None, "2", "days", 0, 5, "2024-01-02", "2024-01-04"
    ),
    Expected(
        "longest_drawdown_days",
        "benchmark",
        None,
        "1",
        "days",
        0,
        5,
        "2024-01-04",
        "2024-01-05",
        flags=("not_recovered",),
    ),
)

_ITS_PERIOD = ("2024-01-08", "2024-01-12")
_ITS_LEVELS = ("2024-01-05", "2024-01-12")
_SPLIT_1 = (
    # From 2024-01-05 to 2024-01-12: 7 days of 11, and the second period.
    Expected("coverage_share", None, None, "63.6364", "percent", 4, None, *_ITS_LEVELS),
    Expected("period_count", None, None, "1", "count", 0, 1, *_ITS_PERIOD),
    Expected("spanning_period_count", None, None, "1", "count", 0, 2, *_ITS_LEVELS),
    *(
        Expected(name, subject, None, value, "percent", 4, 1, *_ITS_PERIOD)
        for name in _SUMMARIES
        for subject, value in (
            ("strategy", "10.0000"),
            ("benchmark", "0.0000"),
            ("excess", "10.0000"),
        )
    ),
    Expected("positive_excess_share", "excess", None, "100.0000", "percent", 4, 1, *_ITS_PERIOD),
    _too_few("tracking_error", "excess", 1),
    _too_few("information_ratio", "excess", 1, "ratio"),
    _too_few("excess_t_value", "excess", 1, "ratio"),
    # Its levels, 2024-01-05 to 2024-01-12: 110 / 99 − 1.
    Expected("total_return", "strategy", None, "11.1111", "percent", 4, 6, *_ITS_LEVELS),
    Expected("total_return", "benchmark", None, "1.0000", "percent", 4, 6, *_ITS_LEVELS),
    Expected("total_return_difference", "excess", None, "10.1111", "pp", 4, 6, *_ITS_LEVELS),
    Expected("annualized_return", "strategy", None, None, "percent", None, 6, reason="too_short"),
    Expected("annualized_return", "benchmark", None, None, "percent", None, 6, reason="too_short"),
    Expected(
        "annualized_return_difference",
        "excess",
        None,
        None,
        "pp",
        None,
        None,
        reason="input_unavailable",
    ),
    Expected(
        "max_drawdown", "strategy", None, "-2.8571", "percent", 4, 6, "2024-01-10", "2024-01-11"
    ),
    Expected(
        "max_drawdown", "benchmark", None, "-1.9417", "percent", 4, 6, "2024-01-10", "2024-01-12"
    ),
    Expected(
        "max_drawdown_recovery", "strategy", None, "2024-01-12", "date", None, 6, *_ITS_LEVELS
    ),
    Expected(
        "max_drawdown_recovery", "benchmark", None, None, "date", None, 6, reason="not_recovered"
    ),
    Expected(
        "longest_drawdown_days", "strategy", None, "2", "days", 0, 6, "2024-01-10", "2024-01-12"
    ),
    Expected(
        "longest_drawdown_days",
        "benchmark",
        None,
        "2",
        "days",
        0,
        6,
        "2024-01-10",
        "2024-01-12",
        flags=("not_recovered",),
    ),
)

EXAMPLE_SPLIT: Final = {"split-0": _SPLIT_0, "split-1": _SPLIT_1}
"""`split-0`'s and `split-1`'s 31 rows each, with the split on 2024-01-05."""


def written(row: AnalysisRow) -> Expected:
    """A row of Trial Folio's, in the form a test writes one."""
    return Expected(
        row.analysis,
        row.subject,
        row.window_days,
        row.value,
        row.unit,
        row.decimals,
        row.observations,
        None if row.period_start is None else row.period_start.isoformat(),
        None if row.period_end is None else row.period_end.isoformat(),
        row.unavailable_reason,
        row.flags,
    )


@dataclass(frozen=True)
class Tables:
    """A result's `series.csv` and `metrics.csv` rows, and what its configuration gives the
    analysis set."""

    series: tuple[SeriesRow, ...]
    metrics: tuple[MetricsRow, ...]
    precision: int
    splits: tuple[date, ...]


def artifact_id(content: bytes) -> str:
    """A saved file's `artifact_id`, as the store gives it."""
    return "sha256:" + hashlib.sha256(content).hexdigest()


def splits_of(name: str) -> tuple[date, ...]:
    """The split dates a screen configuration declares, read with 0.5.0's reader; none for a
    version before 1.2.0, or a 1.2.0 without `analysis`."""
    read = _configuration(name)
    if not isinstance(read, ScreenConfigurationV1_2) or read.analysis is None:
        return ()
    return tuple(split.date for split in read.analysis.period_splits)


def _configuration(
    name: str,
) -> ScreenConfiguration | ScreenConfigurationV1_1 | ScreenConfigurationV1_2:
    path = SCREEN_CONFIGS / name
    return read_screen_configuration_v1_2(path.read_bytes(), str(path), path).configuration


def tables_of(
    response: bytes | str,
    config: str = "hand-checkable.yaml",
    splits: tuple[date, ...] | None = None,
) -> Tables:
    """`response`, a fixture's name under `responses/` or a response's bytes, read as the core
    reads it, with the dates, precision, and splits of `config`, a screen configuration, or with
    `splits` in place of its splits."""
    content = (RESPONSES / response).read_bytes() if isinstance(response, str) else response
    settings = _configuration(config)
    source = artifact_id(content)
    series = series_rows(
        content,
        "response.json",
        label=LABEL,
        source_artifact=source,
        start_date=settings.start_date,
        end_date=settings.end_date,
    )
    metrics = metrics_rows(
        read_response(content, "response.json"),
        label=LABEL,
        benchmark=settings.benchmark,
        source_artifact=source,
    )
    declared = splits_of(config) if splits is None else splits
    return Tables(series, metrics, settings.precision, declared)


def analysed(
    response: bytes | str,
    config: str = "hand-checkable.yaml",
    splits: tuple[date, ...] | None = None,
) -> tuple[AnalysisRow, ...]:
    """`response`'s `analysis.csv` rows, with `config`'s settings and splits, or `splits` in place
    of its splits, by the installed version."""
    tables = tables_of(response, config, splits)
    return analysis_rows(
        tables.series,
        tables.metrics,
        precision=tables.precision,
        splits=tables.splits,
        trialfolio_version=version("trialfolio"),
    )
