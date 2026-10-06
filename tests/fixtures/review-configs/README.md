# Review configurations

Synthetic review configurations for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). [`invalid/`](invalid/README.md) holds one file for each rejection rule.

- **Origin:** written for Trial Folio's tests. The labels, paths, and text are invented. No value comes from Portfolio123 or from the owner's account.
- **Schema version:** [review configuration](../../../docs/contracts.md#review-configuration) 1.0.0.
- **Redistribution:** synthetic, so they may be committed and shared.

Each configuration names its runs by paths relative to itself, and a test puts it beside the runs it builds ([0.2.0's test pairing](../../../docs/releases/0.2.0-review.md#test-pairing)). The [run builder](../../support/run_builder.py) writes each run with `trialfolio run`, over the fake server, from the screen configuration and the reply [below](#the-runs-each-configuration-names), and its `RUNS` gives the same runs. R02-T04 wrote `example.yaml`. R02-T06 wrote the others ahead of R02-T09, for the comparison core's tests, apart from `synthetic.yaml` and `synthetic-only.yaml`, which R02-T07 wrote for the review report's.

| File | Contents | Criteria |
|---|---|---|
| `example.yaml` | The [documented example](../../../docs/contracts.md#review-configuration), byte for byte: `hold25`, the baseline, and `hold50`, which declares `max_holdings` | R02-AC01, R02-AC02, R02-AC05, R02-AC07, R02-AC08, R02-AC09, R02-AC13, R02-AC18, R02-AC19 |
| `undeclared.yaml` | A baseline, and three results that declare nothing: one whose run has another slippage, with the baseline's metrics; one whose run has another benchmark; and one whose run ranks by a ranking system's name, with missing metrics | R02-AC03, R02-AC07, R02-AC13, R02-AC18 |
| `declared-benchmark.yaml` | A baseline, and a result whose run has another benchmark, declared | R02-AC03 |
| `not-observed.yaml` | A baseline, and a result that declares `max_holdings` and `precision`, whose run has the baseline's settings | R02-AC11, R02-AC18 |
| `coverage.yaml` | A baseline, and two results: one whose run's coverage differs from the baseline's, and one whose run's coverage couldn't be established | R02-AC08, R02-AC18 |
| `coverage-and-benchmark.yaml` | A baseline, and a result whose run has another benchmark and coverage that differs from the baseline's | R02-AC08 |
| `missing-metrics.yaml` | A baseline, and a result whose run has missing metrics | R02-AC04 |
| `without-tables.yaml` | A baseline, and three results whose runs have no normalized tables: Portfolio123 rejected one's request, one's response lacks the required structure, and one's isn't JSON | R02-AC13, R02-AC15, R02-AC18 |
| `shared-response.yaml` | A baseline; a result whose run, of the baseline's settings written differently, has the baseline's saved response; two results that name two runs of one configuration, which share another response; and a result whose run has the baseline's metrics, from a response no other result has. The three results with a changed setting declare it. | R02-AC07, R02-AC17, R02-AC18 |
| `synthetic.yaml` | The run `trialfolio demo` wrote as the baseline, `demo`, and a result whose run isn't synthetic, `hold50`, which declares `max_holdings` | R02-AC09, R02-AC16 |
| `synthetic-only.yaml` | Two results, `demo` and `demo-again`, that both name the run `trialfolio demo` wrote, so they share its saved response | R02-AC16 |

## The runs each configuration names

Each run is a screen configuration in [`screen-configs/`](../screen-configs/README.md), run with a reply from the fake server to its backtest request: a response in [`responses/`](../responses/README.md), sent with a 200, or a 400. The baseline is `formula.yaml` with `complete.json`, apart from `synthetic.yaml`'s and `synthetic-only.yaml`'s, which is a copy of the committed run [`runs/synthetic-run-1.0.0/`](../runs/README.md), as `trialfolio demo` wrote it.

| Configuration | `run` path | Screen configuration | Reply |
|---|---|---|---|
| `example.yaml` | `runs/hold25` | `formula.yaml` | `complete.json` |
| | `runs/hold50` | `holdings-50.yaml` | `changed-metrics.json` |
| `undeclared.yaml` | `runs/baseline` | `formula.yaml` | `complete.json` |
| | `runs/slippage` | `slippage-whole.yaml` | `same-metrics.json` |
| | `runs/benchmark` | `benchmark-other.yaml` | `changed-metrics.json` |
| | `runs/ranking-name` | `ranking-name.yaml` | `missing-metrics.json` |
| `declared-benchmark.yaml` | `runs/baseline` | `formula.yaml` | `complete.json` |
| | `runs/benchmark` | `benchmark-other.yaml` | `changed-metrics.json` |
| `not-observed.yaml` | `runs/baseline` | `formula.yaml` | `complete.json` |
| | `runs/declared` | `formula.yaml` | `changed-metrics.json` |
| `coverage.yaml` | `runs/baseline` | `formula.yaml` | `complete.json` |
| | `runs/coverage-mismatch` | `formula.yaml` | `coverage-mismatch.json` |
| | `runs/no-periods` | `formula.yaml` | `no-periods.json` |
| `coverage-and-benchmark.yaml` | `runs/baseline` | `formula.yaml` | `complete.json` |
| | `runs/benchmark` | `benchmark-other.yaml` | `coverage-mismatch.json` |
| `missing-metrics.yaml` | `runs/baseline` | `formula.yaml` | `complete.json` |
| | `runs/missing` | `formula.yaml` | `missing-metrics.json` |
| `without-tables.yaml` | `runs/baseline` | `formula.yaml` | `complete.json` |
| | `runs/rejected` | `formula.yaml` | A 400 |
| | `runs/invalid-structure` | `formula.yaml` | `invalid-structure.json` |
| | `runs/not-json` | `formula.yaml` | `not-json.txt` |
| `shared-response.yaml` | `runs/baseline` | `formula.yaml` | `complete.json` |
| | `runs/written-differently` | `written-differently.yaml` | `complete.json` |
| | `runs/hold50-first` | `holdings-50.yaml` | `changed-metrics.json` |
| | `runs/hold50-second` | `holdings-50.yaml` | `changed-metrics.json` |
| | `runs/slippage` | `slippage-whole.yaml` | `same-metrics.json` |
| `synthetic.yaml` | `runs/demo` | A copy of `runs/synthetic-run-1.0.0/` | |
| | `runs/hold50` | `holdings-50.yaml` | `changed-metrics.json` |
| `synthetic-only.yaml` | `runs/demo`, for both results | A copy of `runs/synthetic-run-1.0.0/` | |
