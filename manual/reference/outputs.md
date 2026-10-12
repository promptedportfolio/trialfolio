# Outputs

This page lists what each command writes into its output directory, the one `--out` names, and what each file holds.

A command writes only into a new or empty directory, and never overwrites a file. An experiment's directory is the exception: it grows with each run of its configuration into it, and each run adds new files.

## A run's directory

`trialfolio run` writes one from a screen configuration, and `trialfolio demo` writes one from invented values.

| Path | What it is |
|---|---|
| `report.html` | The report: one self-contained file, with no scripts, that opens offline |
| `normalized/metrics.csv` | 20 rows: the response's coverage, its first date, last date, and number of periods, then the strategy's and the benchmark's metrics, with units and source precision |
| `normalized/settings.csv` | The 23 settings, each with its value, provenance, and flags |
| `manifest.json` | What ran and how, its outcome and counts, its reproducibility, and every file's hash. It's written last, so a run without one is incomplete. |
| `plan.json` | The plan you approved, with the versions of the packages that sent it |
| `configuration.yaml` | Your configuration file, byte for byte |
| `cases/<case>/attempts/<attempt>/` | The attempt's records: `started.json`, `attempt.json`, the request without credentials, and Portfolio123's decoded response |
| `logs/trialfolio.log` | The run's log |

### An attempt's folder

`<case>` is the case's `case_id`, and `<attempt>` the attempt's `attempt_id`.

| File | What it is |
|---|---|
| `started.json` | The start record, written before the request is sent |
| `attempt.json` | The attempt record, written once, when the attempt ends. It gives the outcome, whether the request is `possibly_charged`, and the cost Portfolio123 reported. |
| `request.json` | The request, without credentials |
| `response.json` | Portfolio123's response, decoded |
| `response.raw` | Only for a response that couldn't be decoded: its body as received |

### `normalized/metrics.csv`

- **Rows:** 20. The coverage first, `coverage_start`, `coverage_end`, and `coverage_periods`; then the strategy's `total_return`, `annualized_return`, `max_drawdown`, `standard_deviation`, `sharpe_ratio`, `sortino_ratio`, `correlation`, `r_squared`, `beta`, `alpha`, and `risk_samples`; then the benchmark's `total_return`, `annualized_return`, `max_drawdown`, `standard_deviation`, `sharpe_ratio`, and `sortino_ratio`.
- **Columns:** `label`, `subject`, `metric_id`, `source_label`, `value`, `unit`, `source_decimals`, `availability`, `unavailable_reason`, `origin`, `provenance`, `period_start`, `period_end`, `benchmark`, `source_artifact`, and `source_location`.
- **`label`** is the run's `case_id`.
- **A value missing from the response** is `unavailable`, with an empty value and a reason code in `unavailable_reason`, never zero.
- **The report's values** match this table's.

[`metrics.csv`](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#metricscsv), in the specification, gives each column's meaning, and [metrics and missing values](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#metrics-and-missing-values) each unit and reason code.

### `normalized/settings.csv`

- **Rows:** 23, one for each setting, in this order: `universe`, `screen_type`, `rules`, `ranking`, `max_holdings`, `position_method`, `benchmark`, `currency`, `start_date`, `end_date`, `rebalance_weeks`, `transaction_price`, `slippage_percent`, `commission`, `pit_method`, `data_vendor`, `precision`, `risk_stats_period`, `max_pos_pct`, `rank_tolerance`, `carry_cost`, `long_weight`, and `short_weight`.
- **Columns:** `label`, `setting`, `category`, `critical`, `value`, `unit`, `interpretation`, `provenance`, `inference_rule`, `original_key`, `original_value`, `source_artifact`, and `flags`.
- **`commission`** is `not_modeled`: the API documents no commission setting, and slippage is the only cost sent.
- **`data_vendor` and `risk_stats_period`** are flagged `inferred_default`.
- **Five parameters Trial Folio doesn't send,** `max_pos_pct`, `rank_tolerance`, `carry_cost`, `long_weight`, and `short_weight`, are `not_sent`, with `unknown` provenance.
- **The universe, and a ranking by name or ID,** are flagged `not_snapshotted`, and the manifest's reproducibility is `incomplete`.
- **`start_date` and `end_date`** are flagged `coverage_mismatch` when the response covers different dates than you asked for.

[`settings.csv`](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#settingscsv) and the [screen settings](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#screen-settings), in the specification, give each column and row. [The flag codes](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#flag-codes) explain each flag.

### `manifest.json`

- **It's written last.** A run without it is incomplete, as after an interrupt, a storage failure, or an internal error. A run whose request failed at Portfolio123 still has it, and it records the failure.
- **It records** the command and its options, the outcome and the error, the plan hash and how the plan was approved, every file with its hash, the reproducibility, and the counts.
- **It records no path** of yours: neither the configuration's nor `--out`.
- **`synthetic`** is true exactly for the run `trialfolio demo` writes.

### The log

`logs/trialfolio.log` holds one JSON object per line. It holds no credentials, configuration values, formulas, or results. [Logs](errors.md#logs) says more.

### In the report

- The research notice is at the top, with a link to the full notice at the end.
- Its [ten sections](#every-reports-sections) say what a screen backtest can and can't support. A section the run can't support says so, and why.
- A value missing from the response shows as unavailable, with the reason, never as zero.
- Commission shows as not modeled: the API documents no commission setting, and slippage is the only cost sent.
- If the response covers different dates than you asked for, the report shows both, and `settings.csv` flags the date as `coverage_mismatch`.
- Statistical validation and trading readiness read "Not assessed".
- The closing section carries the Portfolio123 data statement and two outside links: the license and Portfolio123's terms. The license link names the tag of the version that rendered the report, such as `v0.1.0`, so it works only once that version is tagged.
- The demo's report is labeled synthetic: its title starts with "Synthetic example", and it says nothing was sent or charged.

[What a backtest can support](../explanation/what-a-backtest-can-support.md) explains these limits.

## A re-rendered report's directory

`trialfolio report <run-dir> --out <dir>` rebuilds a saved run's report offline, from its saved files.

| Path | What it is |
|---|---|
| `report.html` | The run's report, rendered again |
| `logs/trialfolio.log` | The command's log |

- **It writes nothing else,** and no manifest. The run's directory isn't changed.
- **The new report's values** match the original's.
- **It links the run's files** by their paths from the new directory.

## A review's directory

`trialfolio review` writes one from a [review configuration](review-configuration.md).

| Path | What it is |
|---|---|
| `report.html` | The review's report: one self-contained file, with no scripts, that opens offline |
| `normalized/differences.csv` | For each result but the baseline, its 23 settings and then its 20 metrics, each compared with the baseline's |
| `manifest.json` | Which run each label names, the comparison's method, its counts, and every file's hash. It's written last, so a review without one is incomplete. |
| `configuration.yaml` | Your review configuration, byte for byte |
| `inputs/<label>/` | Byte-for-byte copies of each run's `manifest.json`, `plan.json`, and normalized tables, when it has them, so the review stands on its own |
| `logs/trialfolio.log` | The review's log |

It doesn't copy a run's request, its response, or its report.

### `normalized/differences.csv`

- **Setting rows** are classified `same`, `intended_change`, `unexplained_mismatch`, or `unknown`. The `intended_change` rows are the changes you declared.
- **A declared change whose values are the same** is `same`, flagged `intended_change_not_observed`.
- **Metric rows** are classified `differenced`, `not_comparable`, or `unavailable`.
- **Two runs with byte-identical saved responses,** such as two demo runs: the review warns that they share one response, and the metric rows of each result but the baseline are flagged `identical_source`.

[`differences.csv`](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#differencescsv), in the specification, gives each column, and [differences between screen runs](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#differences-between-screen-runs) when a metric is differenced.

### In the review's report

- The research notice, the Portfolio123 data statement, and "Not assessed", as in a run's report.
- Each result's benchmark beside the baseline's.
- The intended changes, apart from the unexplained mismatches, and any other setting that's flagged, such as a date whose coverage differs.
- Each result's metrics beside the baseline's, with the difference only where the two are comparable. It's in percentage points (`pp`) for percent metrics, and never has more decimal places than the two values. A metric that depends on the benchmark isn't differenced when the benchmarks differ, and no metric but the coverage is when the periods differ. The report gives the reason.
- A missing value shows as unavailable, with the reason its run's `metrics.csv` gives, never as zero.
- A result whose run has no tables, because its request failed or its response was invalid, is still compared: its settings from its plan, and every metric as unavailable. The report says why it has no tables.
- A synthetic result, from `trialfolio demo`, is named before any result, and labeled synthetic wherever its values appear.
- It links only to the review's own files, never to the runs, and never shows a `run` path.
- It doesn't rank the runs, or say which strategy is better.

## An experiment's directory

`trialfolio run` writes one from an [experiment configuration](experiment-configuration.md), and adds to it each time it runs the same configuration into it.

| Path | What it is |
|---|---|
| `experiment.lock` | The lock, which claims the directory for the experiment, so that only one process runs it at a time. It isn't evidence. |
| `plans/<n>/` | One for each plan you approved, numbered from 1: `configuration.yaml`, your configuration byte for byte; `plan.json`; and `experiment.json`, the experiment's research record as of that plan, with every plan before it and the reason for each revision |
| `cases/<case_id>/attempts/<attempt_id>/` | Each attempt's records, as a run's are. The attempt that authenticated also has `authenticating.json`. |
| `cases/<case_id>/normalized/` | The case's `metrics.csv` and `settings.csv`, as a run's, once its attempt succeeds |
| `sessions/<s>/` | One for each run of the command that passed its checks and its approval, numbered from 1: `session.json`, `report.html`, and `manifest.json`, which is written last |
| `logs/trialfolio.log` | The log of every session |

- **A case's folder is named by its `case_id`,** never its key. The plan display and the report give each case's key beside its `case_id`.
- **The newest session's report and manifest supersede the earlier ones.** A session without a manifest, because its command was interrupted, reads as incomplete until the same command resumes the experiment.
- **It isn't a run.** `trialfolio report` and `trialfolio review` read runs only, and fail with `input.not_a_run` given an experiment. Each session writes its own report.

**What its files hold:**

- **A session's `manifest.json`** counts the planned cases: those that succeeded, failed, were skipped, are unknown, and haven't run yet add up to the planned cases. The report gives the same counts.
- **Each case that succeeded** has `metrics.csv` and `settings.csv` in its own `normalized/` folder, labeled with its `case_id`.
- **The log** names cases by their `case_id`, and holds no case key or description, formula, or result.

### In the experiment's report

`sessions/<s>/report.html` holds:

- The research notice, the Portfolio123 data statement, and "Not assessed", as in a run's report.
- The research context: the purpose, the prior research, and every plan, with its reason and what it changed.
- Each case's change from the baseline, and its coverage.
- The metrics side by side, with a column for each case that has results. The report computes no difference between cases, and orders, ranks, and marks no case by a value.
- The counts of cases and attempts; every case with its outcome and attempts; the cases awaiting a repeat, each with the option that repeats it; and the retired cases.
- In its limitations, that a prior-research declaration other than `complete` limits any claim drawn from the cases.

## Every report's sections

Every report, a run's, a review's, or an experiment's, starts with the research notice, and has these ten sections, then a closing section with the Portfolio123 data statement and the full notice:

1. Objective, purpose, and research status
2. Definitions, and changes from a baseline. A review's and an experiment's read "the baseline".
3. Data sources, coverage, provenance, and missing values
4. Returns, risks, costs, and assumptions
5. Cases and attempts. A review's is "Results compared, and their runs".
6. Robustness and concentration
7. Statistical methods and uncertainty
8. Development, selection, holdout, and forward evidence
9. Feasibility, capacity, and missing execution evidence
10. Conclusion, limitations, and artifacts

[Reports](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#reports), in the specification, gives what each holds.

## Outputs that hold Portfolio123 data

- **Runs, re-rendered reports, reviews, and experiments** hold Portfolio123 data. A review holds it in its copies of the runs' tables.
- **The `.gitignore` that `trialfolio init` writes** keeps the `runs/`, `reports/`, and `reviews/` folders at the workspace's top level out of Git, and credential files, `.env*` and `*.env`. So write runs and experiments under `runs/`, re-rendered reports under `reports/`, and reviews under `reviews/`.
- **A workspace that Trial Folio 0.1.0 set up** lacks the `reviews/` line: if you keep it in Git, add `/reviews/` to its `.gitignore`.
