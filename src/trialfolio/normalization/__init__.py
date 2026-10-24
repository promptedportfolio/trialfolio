"""Normalization: a saved screen backtest response, and the plan's settings, into the rows of
`metrics.csv` and `settings.csv` (docs/contracts.md, normalized tables, and `p123api-screen-backtest`
version 1).

The package's modules, each importing only those before it:

- `layout`, the layout's adapter. `read_response` reads a saved `response.json`, checks the
  required structure, and reads each metric and the coverage from the saved text: numbers as
  decimals, never as binary floats, with exactly the digits the file holds. `holds_series` says
  whether a decoded response holds the per-period series that 0.1.0 preserves without
  interpreting, for the manifest's `return_series`.
- `rows`, the row builders. `metrics_rows` gives `metrics.csv`'s 20 rows, and `settings_rows`
  `settings.csv`'s 23, in their documented order.
- `writer`, the writing of the tables. `write_tables` does both for an attempt that succeeded,
  and writes the two tables. `write_case_tables` does so for an experiment's case, in
  `cases/<case_id>/normalized/`, with `original_key` and `original_value` from the experiment
  configuration of the plan its attempt ran under (docs/contracts.md, an experiment's normalized
  tables). A resume writes them from the bytes of the response its records check read, and
  `write_case_settings` completes a case's `settings.csv` beside a `metrics.csv` a stopped run
  wrote, with the coverage that table holds. `case_metrics_rows` gives the rows the installed
  parser writes, which the check compares with a `metrics.csv` no manifest lists (R03-T09).

From 0.4.0, a run or a case whose ranking is a definition writes `settings.csv` 1.1.0 (weight
rows): 1.0.0's rows, with a row for each node's weight right after `ranking`, as its plan holds
them, and the column `node`. Each weight row's `original_key` and `original_value` come from the
definition, whose copy, `definition.xml`, is its `source_artifact`, or from the ranking variant's
`set` entry that changes it, whose source is the configuration, as the configuration's reader
gives them (`RankingOriginals`).

The tables are written only from a decoded response with the required structure. For any other
response, the normalized result is unavailable: `write_tables` raises
`provider.response_invalid` and writes neither table.

Nothing here logs: the rows hold configuration values, formulas, and results.

Every name the rest of Trial Folio uses is imported from `trialfolio.normalization`, as before it
was a package.
"""

from trialfolio.normalization.layout import (
    END_DATE,
    LAYOUT,
    LAYOUT_VERSION,
    METRICS,
    PARSER_VERSION,
    TRANSACTION_DATE,
    Coverage,
    Kind,
    Metric,
    ScreenBacktestResult,
    Subject,
    Value,
    holds_series,
    read_response,
)
from trialfolio.normalization.rows import (
    AnySettingsRows,
    RankingOriginals,
    metrics_rows,
    setting_text,
    settings_rows,
    settings_rows_v1_1,
)
from trialfolio.normalization.writer import (
    METRICS_PATH,
    SETTINGS_PATH,
    AnyPlanCase,
    NormalizedTables,
    case_metrics_rows,
    case_tables_path,
    write_case_settings,
    write_case_tables,
    write_tables,
)

__all__ = [
    "END_DATE",
    "LAYOUT",
    "LAYOUT_VERSION",
    "METRICS",
    "METRICS_PATH",
    "PARSER_VERSION",
    "SETTINGS_PATH",
    "TRANSACTION_DATE",
    "AnyPlanCase",
    "AnySettingsRows",
    "Coverage",
    "Kind",
    "Metric",
    "NormalizedTables",
    "RankingOriginals",
    "ScreenBacktestResult",
    "Subject",
    "Value",
    "case_metrics_rows",
    "case_tables_path",
    "holds_series",
    "metrics_rows",
    "read_response",
    "setting_text",
    "settings_rows",
    "settings_rows_v1_1",
    "write_case_settings",
    "write_case_tables",
    "write_tables",
]
