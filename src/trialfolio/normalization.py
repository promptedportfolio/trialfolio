"""Normalization: a saved screen backtest response, and the plan's settings, into the rows of
`metrics.csv` and `settings.csv` (docs/contracts.md, normalized tables, and `p123api-screen-backtest`
version 1).

- `read_response` is the layout's adapter. It reads a saved `response.json`, checks the required
  structure, and reads each metric and the coverage from the saved text: numbers as decimals,
  never as binary floats, with exactly the digits the file holds.
- `metrics_rows` gives `metrics.csv`'s 20 rows, and `settings_rows` `settings.csv`'s 23, in
  their documented order.
- `write_tables` does both for an attempt that succeeded, and writes the two tables.
- `holds_series` says whether a decoded response holds the per-period series that 0.1.0 preserves
  without interpreting, for the manifest's `return_series`.

The tables are written only from a decoded response with the required structure. For any other
response, the normalized result is unavailable: `write_tables` raises
`provider.response_invalid` and writes neither table.

Nothing here logs: the rows hold configuration values, formulas, and results.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Final, Literal, cast

from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.common import DATE_PATTERN, FlagCode, UnavailableReason
from trialfolio.contracts.plan import Plan, PlanCase, SettingValue
from trialfolio.contracts.screen_configuration import FormulaRanking, IdRanking, NameRanking
from trialfolio.contracts.tables import MetricsRow, SettingsRow
from trialfolio.errors import TrialFolioError
from trialfolio.storage import ArtifactStore, StoredFile
from trialfolio.tables import metrics_csv, settings_csv

LAYOUT: Final = "p123api-screen-backtest"
LAYOUT_VERSION: Final = 1
PARSER_VERSION: Final = 1
"""The version of this adapter, which the manifest records with the layout's (versioning)."""

METRICS_PATH: Final = "normalized/metrics.csv"
SETTINGS_PATH: Final = "normalized/settings.csv"

type Subject = Literal["strategy", "benchmark"]
type Kind = Literal["decimal", "count", "date"]


@dataclass(frozen=True)
class Metric:
    """One row of the layout's metrics table."""

    metric_id: str
    subject: Subject
    unit: str
    path: tuple[str, ...] | None
    """The value's JSON path in the response; None for a value Trial Folio calculates."""
    benchmark_relative: bool = False
    """Whether the row compares the strategy with the benchmark, and so names it."""

    @property
    def kind(self) -> Kind:
        return "date" if self.unit == "date" else "count" if self.unit == "count" else "decimal"


_PER_SUBJECT: Final = (
    ("total_return", "total_return", "percent"),
    ("annualized_return", "annualized_return", "percent"),
    ("max_drawdown", "max_drawdown", "percent"),
    ("standard_deviation", "standard_dev", "percent"),
    ("sharpe_ratio", "sharpe_ratio", "ratio"),
    ("sortino_ratio", "sortino_ratio", "ratio"),
)
"""Rows 4-9, and 15-20 for the benchmark: each metric's identifier, key, and unit."""

METRICS: Final = (
    Metric("coverage_start", "strategy", "date", None),
    Metric("coverage_end", "strategy", "date", None),
    Metric("coverage_periods", "strategy", "count", None),
    *(Metric(name, "strategy", unit, ("stats", "port", key)) for name, key, unit in _PER_SUBJECT),
    Metric("correlation", "strategy", "ratio", ("stats", "correlation"), True),
    Metric("r_squared", "strategy", "ratio", ("stats", "r_squared"), True),
    Metric("beta", "strategy", "ratio", ("stats", "beta"), True),
    Metric("alpha", "strategy", "percent", ("stats", "alpha"), True),
    Metric("risk_samples", "strategy", "count", ("stats", "samples")),
    *(Metric(name, "benchmark", unit, ("stats", "bench", key)) for name, key, unit in _PER_SUBJECT),
)
"""`metrics.csv`'s 20 rows, in order."""

TRANSACTION_DATE: Final = "Tran Dt"
END_DATE: Final = "End Dt"


@dataclass(frozen=True)
class Value:
    """A value read from the response, or why it's unavailable."""

    text: str | None
    """A decimal in plain notation with exactly its source's digits, a count's digits, or a
    `YYYY-MM-DD` date. None when unavailable."""
    reason: UnavailableReason | None = None
    """Why it's unavailable; None when it's available."""

    @property
    def available(self) -> bool:
        return self.text is not None


@dataclass(frozen=True)
class Coverage:
    """The dates and number of periods the response covers (coverage)."""

    start: Value
    """The earliest `Tran Dt` in `results.rows`."""
    end: Value
    """The latest `End Dt` in `results.rows`."""
    periods: int
    """The number of rows, including zero."""


@dataclass(frozen=True)
class ScreenBacktestResult:
    """A response read as `p123api-screen-backtest` version 1."""

    coverage: Coverage
    values: Mapping[tuple[str, ...], Value]
    """Each reported metric's value, by JSON path."""


@dataclass(frozen=True)
class NormalizedTables:
    """The tables `write_tables` wrote, and their rows."""

    metrics: StoredFile
    settings: StoredFile
    metrics_rows: tuple[MetricsRow, ...]
    settings_rows: tuple[SettingsRow, ...]

    @property
    def metrics_unavailable(self) -> int:
        """The JSON summary's `counts.metrics_unavailable`."""
        return sum(row.availability == "unavailable" for row in self.metrics_rows)


class _Number(str):
    """A JSON number's text, exactly as the saved file writes it."""

    __slots__ = ()


class _NotFinite:
    """`NaN`, `Infinity`, or `-Infinity`, which `json` writes but which aren't JSON numbers."""


_NOT_FINITE: Final = _NotFinite()
_DATE: Final = re.compile(DATE_PATTERN)


def _invalid(path: str, problem: str) -> TrialFolioError:
    return TrialFolioError(
        "provider.response_invalid",
        f"Portfolio123's response was saved, as {path}, but Trial Folio can't read it as "
        f"{LAYOUT} version {LAYOUT_VERSION}: {problem} So the normalized result is unavailable. "
        "The saved response is kept as it came; report the problem if it persists.",
    )


def read_response(content: bytes, path: str) -> ScreenBacktestResult:
    """Reads a saved `response.json`, named by its `path` in messages, as `p123api-screen-backtest`
    version 1.

    Raises `TrialFolioError` with `provider.response_invalid` when the file doesn't have the
    layout's required structure. A metric or coverage date that's missing or can't be read is
    unavailable, with its reason, and doesn't make the response invalid.
    """
    try:
        loaded: object = json.loads(
            content.decode("utf-8"),
            parse_float=_Number,
            parse_int=_Number,
            parse_constant=lambda _: _NOT_FINITE,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _invalid(path, "it isn't JSON.") from None
    top = _object(loaded, "The top level", path)
    stats = _object(top.get("stats"), "`stats`", path)
    results = _object(top.get("results"), "`results`", path)
    for subject in ("port", "bench"):
        _object(stats.get(subject), f"`stats.{subject}`", path)
    columns = results.get("columns")
    # A number's text is a `str` too, so the type is checked exactly.
    if not isinstance(columns, list) or not all(
        type(column) is str for column in cast("list[object]", columns)
    ):
        raise _invalid(path, "`results.columns` isn't an array of strings.")
    rows = results.get("rows")
    if not isinstance(rows, list):
        raise _invalid(path, "`results.rows` isn't an array.")
    width = len(cast("list[str]", columns))
    for row in cast("list[object]", rows):
        if not isinstance(row, list) or len(cast("list[object]", row)) != width:
            raise _invalid(path, "a row of `results.rows` isn't an array as long as `columns`.")
    values = {metric.path: _reported(top, metric) for metric in METRICS if metric.path is not None}
    coverage = _coverage(cast("list[str]", columns), cast("list[list[object]]", rows))
    return ScreenBacktestResult(coverage=coverage, values=values)


def holds_series(payload: object) -> bool:
    """Whether a decoded response holds per-period series, which 0.1.0 preserves without
    interpreting (the manifest's `return_series`): a `results.rows` array with a row, or a
    `chart` object holding an array with an entry. A response without either, such as `{}`,
    holds none, whether or not it has the required structure."""
    if not isinstance(payload, dict):
        return False
    top = cast("dict[str, object]", payload)
    results = top.get("results")
    if isinstance(results, dict):
        rows = cast("dict[str, object]", results).get("rows")
        if _non_empty_array(rows):
            return True
    chart = top.get("chart")
    if not isinstance(chart, dict):
        return False
    return any(_non_empty_array(series) for series in cast("dict[str, object]", chart).values())


def _non_empty_array(value: object) -> bool:
    return isinstance(value, list) and len(cast("list[object]", value)) > 0


def _object(value: object, name: str, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _invalid(path, f"{name} isn't an object.")
    return cast("dict[str, object]", value)


def _reported(top: Mapping[str, object], metric: Metric) -> Value:
    value: object = top
    for key in cast("tuple[str, ...]", metric.path):
        value = cast("dict[str, object]", value).get(key)
        if value is None:
            # Missing, or null: the response has the field but no value.
            return Value(None, "blank_in_source")
    if type(value) is not _Number:
        return Value(None, "unparseable_in_source")
    number = Decimal(value)
    if metric.kind == "count":
        return _count(number)
    return Value(format(number, "f"))


def _count(number: Decimal) -> Value:
    """A count is a whole number, 0 or more. One written with a decimal point, such as `118.0`, is
    written with its digits alone."""
    if number < 0 or number != number.to_integral_value():
        return Value(None, "unparseable_in_source")
    return Value(format(number.copy_abs().to_integral_value(), "f"))


def _coverage(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> Coverage:
    periods = len(rows)
    if not rows or TRANSACTION_DATE not in columns or END_DATE not in columns:
        blank = Value(None, "blank_in_source")
        return Coverage(blank, blank, periods)
    starts = _dates(rows, columns.index(TRANSACTION_DATE))
    ends = _dates(rows, columns.index(END_DATE))
    start = Value(min(starts).isoformat()) if starts else Value(None, "unparseable_in_source")
    end = Value(max(ends).isoformat()) if ends else Value(None, "unparseable_in_source")
    if starts and ends and min(starts) > max(ends):
        # The dates contradict each other, so neither can be the coverage.
        contradicted = Value(None, "unparseable_in_source")
        return Coverage(contradicted, contradicted, periods)
    return Coverage(start, end, periods)


def _dates(rows: Sequence[Sequence[object]], column: int) -> list[date]:
    """Every row's date in the column; empty when any of them isn't a `YYYY-MM-DD` date, so the
    earliest or latest can't be known."""
    dates: list[date] = []
    for row in rows:
        value = row[column]
        if type(value) is not str or not _DATE.fullmatch(value):
            return []
        try:
            dates.append(date.fromisoformat(value))
        except ValueError:
            return []
    return dates


def metrics_rows(
    result: ScreenBacktestResult, *, label: str, benchmark: str, source_artifact: str
) -> tuple[MetricsRow, ...]:
    """`metrics.csv`'s rows for one result, in order: the coverage, then each reported metric.

    `benchmark` is the request's `screen.benchmark`, which the benchmark-relative rows name, and
    `source_artifact` the saved response's `artifact_id`.
    """
    coverage = result.coverage
    calculated = {
        "coverage_start": coverage.start,
        "coverage_end": coverage.end,
        "coverage_periods": Value(str(coverage.periods)),
    }
    period_start = date.fromisoformat(coverage.start.text) if coverage.start.text else None
    period_end = date.fromisoformat(coverage.end.text) if coverage.end.text else None
    rows: list[MetricsRow] = []
    for metric in METRICS:
        value = calculated[metric.metric_id] if metric.path is None else result.values[metric.path]
        rows.append(
            MetricsRow(
                label=label,
                subject=metric.subject,
                metric_id=metric.metric_id,
                source_label=metric.path[-1] if metric.path else None,
                value=value.text,
                unit=metric.unit,
                source_decimals=_decimals(metric, value),
                availability="available" if value.available else "unavailable",
                unavailable_reason=value.reason,
                origin="reported" if metric.path else "calculated",
                provenance="verified" if metric.path else "inferred",
                period_start=period_start,
                period_end=period_end,
                benchmark=benchmark if metric.benchmark_relative else None,
                source_artifact=source_artifact,
                source_location=".".join(metric.path) if metric.path else None,
            )
        )
    return tuple(rows)


def _decimals(metric: Metric, value: Value) -> int | None:
    if value.text is None or metric.kind != "decimal":
        return None
    return len(value.text.partition(".")[2])


def settings_rows(
    case: PlanCase,
    originals: Mapping[str, str],
    *,
    label: str,
    source_artifact: str,
    coverage: Coverage,
) -> tuple[SettingsRow, ...]:
    """`settings.csv`'s rows for one result, in order, from the plan's resolved settings.

    The request was sent, so each value has the provenance the plan expected. `originals` holds
    each top-level value as the configuration file writes it (`original_values`), and
    `source_artifact` is the saved configuration's `artifact_id`. A date setting is flagged
    `coverage_mismatch` when its coverage date is available and differs from it.
    """
    compared = {"start_date": coverage.start.text, "end_date": coverage.end.text}
    rows: list[SettingsRow] = []
    for setting in case.settings:
        flags: tuple[FlagCode, ...] = setting.flags
        covered = compared.get(setting.setting)
        if covered is not None and covered != setting.value:
            flags = (*flags, "coverage_mismatch")
        original = originals.get(setting.setting)
        rows.append(
            SettingsRow(
                label=label,
                setting=setting.setting,
                category=setting.category,
                critical=setting.critical,
                value=setting_text(setting.value),
                unit=setting.unit,
                interpretation=setting.interpretation,
                provenance=setting.expected_provenance,
                inference_rule=setting.inference_rule,
                original_key=None if original is None else setting.setting,
                original_value=original,
                source_artifact=source_artifact,
                flags=flags,
            )
        )
    return tuple(rows)


def setting_text(value: SettingValue) -> str:
    """A resolved value as `settings.csv` writes it: an integer in decimal digits, a list or a
    ranking as JSON with the configuration's keys, and text as it is."""
    match value:
        case int():
            return str(value)
        case str():
            return value
        case FormulaRanking() | NameRanking() | IdRanking():
            return json.dumps(value.model_dump(mode="json"), ensure_ascii=False)
        case _:
            return json.dumps(list(value), ensure_ascii=False)


def write_tables(
    store: ArtifactStore,
    plan: Plan,
    originals: Mapping[str, str],
    *,
    configuration: StoredFile,
    response: SavedResponse,
) -> NormalizedTables:
    """Normalizes an attempt's saved response, and writes `normalized/metrics.csv`, then
    `normalized/settings.csv`.

    `configuration` is the saved `configuration.yaml`, and `originals` its top-level values as
    `original_values` reads them. `response` is the attempt record's reference to the saved
    response, which this reads from the store. Each row's label is the case's `case_id`.

    Raises `TrialFolioError` with `provider.response_invalid`, writing nothing, when the response
    was saved undecoded or doesn't have the layout's required structure; and with
    `storage.write_failed` when a table can't be written.
    """
    if response.form == "undecoded":
        raise TrialFolioError(
            "provider.response_invalid",
            f"Portfolio123's response couldn't be decoded as JSON, so it was saved as it came, as "
            f"{response.path}, and the normalized result is unavailable. Report the problem if "
            "it persists.",
        )
    result = read_response(store.read(response.path), response.path)
    (case,) = plan.cases
    label = case.case_id
    metrics = metrics_rows(
        result,
        label=label,
        benchmark=case.requests[0].params.screen.benchmark,
        source_artifact=response.artifact_id,
    )
    settings = settings_rows(
        case,
        originals,
        label=label,
        source_artifact=configuration.artifact_id,
        coverage=result.coverage,
    )
    return NormalizedTables(
        metrics=store.write(METRICS_PATH, metrics_csv(metrics)),
        settings=store.write(SETTINGS_PATH, settings_csv(settings)),
        metrics_rows=metrics,
        settings_rows=settings,
    )
