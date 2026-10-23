"""The writing of the normalized tables: a run's, and an experiment's case's (docs/contracts.md,
normalized tables, and an experiment's normalized tables).

- `write_tables` normalizes the saved response of an attempt that succeeded, and writes the two
  tables. `write_case_tables` does so for an experiment's case, in `cases/<case_id>/normalized/`,
  with `original_key` and `original_value` from the experiment configuration of the plan its
  attempt ran under. A resume writes them from the bytes of the response its records check read,
  and `write_case_settings` completes a case's `settings.csv` beside a `metrics.csv` a stopped run
  wrote, with the coverage that table holds.
- `case_metrics_rows` gives the rows the installed parser writes, which the check compares with a
  `metrics.csv` no manifest lists (R03-T09).

The tables are written only from a decoded response with the required structure. For any other
response, the normalized result is unavailable: `write_tables` raises
`provider.response_invalid` and writes neither table.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from trialfolio.contracts.attempt import SavedResponse
from trialfolio.contracts.experiment_plan import ExperimentPlanCase, ExperimentPlanCaseV1_3
from trialfolio.contracts.plan import Plan, PlanCase, PlanCaseV1_2, PlanV1_2
from trialfolio.contracts.tables import MetricsRow
from trialfolio.normalization.layout import (
    Coverage,
    ScreenBacktestResult,
    Value,
    check_decoded,
    read_response,
)
from trialfolio.normalization.rows import (
    AnySettingsRows,
    RankingOriginals,
    metrics_rows,
    settings_rows,
    settings_rows_v1_1,
)
from trialfolio.storage import ArtifactStore, StoredFile
from trialfolio.tables import metrics_csv, settings_csv, settings_csv_v1_1

METRICS_PATH: Final = "normalized/metrics.csv"
SETTINGS_PATH: Final = "normalized/settings.csv"

type AnyPlanCase = PlanCase | ExperimentPlanCase | PlanCaseV1_2 | ExperimentPlanCaseV1_3


@dataclass(frozen=True)
class NormalizedTables:
    """The tables `write_tables` wrote, and their rows."""

    metrics: StoredFile
    settings: StoredFile
    metrics_rows: tuple[MetricsRow, ...]
    settings_rows: AnySettingsRows

    @property
    def metrics_unavailable(self) -> int:
        """The JSON summary's `counts.metrics_unavailable`."""
        return sum(row.availability == "unavailable" for row in self.metrics_rows)


def write_tables(
    store: ArtifactStore,
    plan: Plan | PlanV1_2,
    originals: Mapping[str, str],
    *,
    configuration: StoredFile,
    response: SavedResponse,
    ranking: RankingOriginals | None = None,
) -> NormalizedTables:
    """Normalizes an attempt's saved response, and writes `normalized/metrics.csv`, then
    `normalized/settings.csv`.

    `configuration` is the saved `configuration.yaml`, and `originals` its top-level values as
    `original_values` reads them. `response` is the attempt record's reference to the saved
    response, which this reads from the store. Each row's label is the case's `case_id`. A plan
    1.2.0's run writes `settings.csv` 1.1.0, whose weight rows take their originals from
    `ranking`, which it requires.

    Raises `TrialFolioError` with `provider.response_invalid`, writing nothing, when the response
    was saved undecoded or doesn't have the layout's required structure; and with
    `storage.write_failed` when a table can't be written.
    """
    (case,) = plan.cases
    return _write(
        store,
        case,
        _Originals(originals, None, ranking),
        lambda path: path,
        configuration=configuration,
        response=response,
    )


def case_tables_path(case_id: str, path: str) -> str:
    """`cases/<case_id>/<path>`, relative to the output root, for `METRICS_PATH` or
    `SETTINGS_PATH`."""
    return f"cases/{case_id}/{path}"


def write_case_tables(
    store: ArtifactStore,
    case: ExperimentPlanCase | ExperimentPlanCaseV1_3,
    originals: Mapping[str, tuple[str, str]],
    *,
    configuration: StoredFile,
    response: SavedResponse,
    content: bytes | None = None,
    ranking: RankingOriginals | None = None,
) -> NormalizedTables:
    """Normalizes the saved response of an experiment's case, and writes
    `cases/<case_id>/normalized/metrics.csv`, then `settings.csv`, as `write_tables` writes a
    run's: the same rows, labeled with the case's `case_id`, apart from `original_key`,
    `original_value`, and `source_artifact` (docs/contracts.md, an experiment's normalized tables).

    `configuration` is the saved `configuration.yaml` of the plan the attempt ran under, and
    `originals` each setting's key path and text in it, as `experiment_original_values` reads
    them. `content` is the response's bytes, when the caller read them already, as a resume's
    records check did: the response is then never read again. A case of a plan 1.3.0 writes
    `settings.csv` 1.1.0, with `ranking`, as `write_tables` does. Raises as `write_tables` does.
    """
    original_values, original_keys = _split(originals)
    return _write(
        store,
        case,
        _Originals(original_values, original_keys, ranking),
        lambda path: case_tables_path(case.case_id, path),
        configuration=configuration,
        response=response,
        content=content,
    )


def case_metrics_rows(
    content: bytes, case: ExperimentPlanCase | ExperimentPlanCaseV1_3, response: SavedResponse
) -> tuple[MetricsRow, ...]:
    """The rows of the `metrics.csv` the installed parser writes for an experiment's case from its
    saved response, whose bytes are `content`. Raises `TrialFolioError` with
    `provider.response_invalid` as `write_case_tables` does."""
    return _metrics(case, response, _result(response, lambda: content))


def write_case_settings(
    store: ArtifactStore,
    case: ExperimentPlanCase | ExperimentPlanCaseV1_3,
    originals: Mapping[str, tuple[str, str]],
    *,
    configuration: StoredFile,
    metrics: Sequence[MetricsRow],
    ranking: RankingOriginals | None = None,
) -> tuple[StoredFile, AnySettingsRows]:
    """Writes `cases/<case_id>/normalized/settings.csv` for a case whose `metrics.csv`, with the
    rows `metrics`, a stopped run wrote without it, and returns it with its rows.

    The settings are drawn from the configuration of the plan the attempt ran under, which no
    parser reads. The one thing they take from the response, its coverage dates, for
    `coverage_mismatch`, comes from `metrics`' coverage rows, so the pair agrees whichever parser
    wrote `metrics.csv`. A case of a plan 1.3.0 writes `settings.csv` 1.1.0, whose weight rows
    take their originals from `ranking`, as `write_case_tables` writes it. Raises
    `TrialFolioError` with `storage.write_failed` when it can't be written.
    """
    original_values, original_keys = _split(originals)
    path = case_tables_path(case.case_id, SETTINGS_PATH)
    rows, table = _settings(
        case,
        _Originals(original_values, original_keys, ranking),
        configuration=configuration,
        coverage=lambda: _coverage_of(metrics),
    )
    return store.write(path, table), rows


def _split(
    originals: Mapping[str, tuple[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    """An experiment's original values, as `experiment_original_values` gives them, split into
    each setting's text and its key."""
    return (
        {setting: text for setting, (_, text) in originals.items()},
        {setting: key for setting, (key, _) in originals.items()},
    )


def _coverage_of(metrics: Sequence[MetricsRow]) -> Coverage:
    """The coverage `metrics.csv`'s first three rows hold."""
    rows = {row.metric_id: row for row in metrics}
    start, end, periods = (
        rows[name] for name in ("coverage_start", "coverage_end", "coverage_periods")
    )
    return Coverage(
        start=Value(start.value, start.unavailable_reason),
        end=Value(end.value, end.unavailable_reason),
        periods=int(periods.value or 0),
    )


def _result(response: SavedResponse, content: Callable[[], bytes]) -> ScreenBacktestResult:
    """The saved response, read as the layout from the bytes `content` gives, which are read
    only once the response is known to have been saved decoded."""
    check_decoded(response)
    return read_response(content(), response.path)


def _metrics(
    case: AnyPlanCase, response: SavedResponse, result: ScreenBacktestResult
) -> tuple[MetricsRow, ...]:
    """`metrics.csv`'s rows for the case, from its saved response, read as `result`."""
    return metrics_rows(
        result,
        label=case.case_id,
        benchmark=case.requests[-1].params.screen.benchmark,
        source_artifact=response.artifact_id,
    )


@dataclass(frozen=True)
class _Originals:
    """A run's or a case's original values: each setting's text, by its name, and its key, when
    it isn't the setting's name, and the weight rows', for a ranking given as a definition."""

    values: Mapping[str, str]
    keys: Mapping[str, str] | None
    ranking: RankingOriginals | None


def _settings(
    case: AnyPlanCase,
    originals: _Originals,
    *,
    configuration: StoredFile,
    coverage: Callable[[], Coverage],
) -> tuple[AnySettingsRows, bytes]:
    """`settings.csv`'s rows for the case, and the table's bytes: 1.1.0's, whose weight rows take
    their originals from `originals.ranking`, for a case whose ranking is a definition, and
    1.0.0's for any other. The coverage is the one `coverage` gives, which is read only once a
    case ranked by a definition is known to have been given its weights' originals."""
    if isinstance(case, PlanCaseV1_2 | ExperimentPlanCaseV1_3):
        if originals.ranking is None:
            raise ValueError("a case whose ranking is a definition needs its weights' originals")
        ranked = settings_rows_v1_1(
            case,
            originals.values,
            originals.ranking,
            label=case.case_id,
            source_artifact=configuration.artifact_id,
            coverage=coverage(),
            original_keys=originals.keys,
        )
        return ranked, settings_csv_v1_1(ranked)
    rows = settings_rows(
        case,
        originals.values,
        label=case.case_id,
        source_artifact=configuration.artifact_id,
        coverage=coverage(),
        original_keys=originals.keys,
    )
    return rows, settings_csv(rows)


def _write(
    store: ArtifactStore,
    case: AnyPlanCase,
    originals: _Originals,
    path_of: Callable[[str], str],
    *,
    configuration: StoredFile,
    response: SavedResponse,
    content: bytes | None = None,
) -> NormalizedTables:
    """The tables of the case, written at the paths `path_of` gives `METRICS_PATH` and
    `SETTINGS_PATH`: a run's, or an experiment's case's."""
    result = _result(response, lambda: store.read(response.path) if content is None else content)
    metrics = _metrics(case, response, result)
    settings, table = _settings(
        case, originals, configuration=configuration, coverage=lambda: result.coverage
    )
    return NormalizedTables(
        metrics=store.write(path_of(METRICS_PATH), metrics_csv(metrics)),
        settings=store.write(path_of(SETTINGS_PATH), table),
        metrics_rows=metrics,
        settings_rows=settings,
    )
