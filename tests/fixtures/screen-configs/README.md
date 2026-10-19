# Screen configurations

Synthetic screen configurations for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). Each one is the [documented example](../../../docs/contracts.md#example), changed as its row says. [`invalid/`](invalid/README.md) holds one file for each rejection rule.

- **Origin:** written for Trial Folio's tests. The ranking system name and ID are invented, and so are the canary values. No value comes from Portfolio123 or from the owner's account.
- **Schema version:** [screen configuration](../../../docs/contracts.md#screen-configuration) 1.0.0, and 1.1.0 for `definition.yaml`, `value-heavy.yaml`, `positions.yaml`, and `positions-without-first-yield.yaml`.
- **Redistribution:** synthetic, so they may be committed and shared.

| File | Contents | Criteria |
|---|---|---|
| `formula.yaml` | The documented example, byte for byte: a single-formula ranking, with no `data_vendor` | R01-AC01, R01-AC10, R01-AC11, R01-AC24, R01-AC25, R01-AC30; the baseline's run, and the runs with its settings, in R02-AC01, R02-AC02, R02-AC03, R02-AC04, R02-AC05, R02-AC07, R02-AC08, R02-AC09, R02-AC10, R02-AC11, R02-AC13, R02-AC15, R02-AC17, R02-AC18, and R02-AC19; R03-AC18, as the screen run whose rows the baseline case's equal, in `tests/interface/test_experiment_tables.py` |
| `ranking-name.yaml` | The example, ranking by an invented ranking system name | R01-AC10, R01-AC30, R02-AC03, R02-AC07, R02-AC13, R02-AC18 |
| `ranking-id.yaml` | The example, ranking by an invented ranking system ID | R01-AC10, R01-AC30 |
| `vendor-factset.yaml` | The example with `data_vendor: FactSet` | R01-AC11, R01-AC25 |
| `written-differently.yaml` | The example's settings, written differently: keys in another order, `slippage_percent: 0.250`, dates as quoted strings, the universe and benchmark in double quotes, and `data_vendor: FactSet` | R01-AC25, R02-AC07, R02-AC17, R02-AC18 |
| `slippage-whole.yaml` | The example with `slippage_percent: 1` | R01-AC25, R02-AC03, R02-AC07, R02-AC13, R02-AC17, R02-AC18 |
| `title-non-ascii.yaml` | The example with a title that contains `Café` and other non-ASCII text | R01-AC25 |
| `canaries.yaml` | The example with a distinct canary string in the title, the purpose, the universe, each of two rules, the ranking formula, and the benchmark | R01-AC01, R01-AC17, R02-AC12 |
| `holdings-50.yaml` | The example with `max_holdings: 50` | R02-AC01, R02-AC02, R02-AC05, R02-AC07, R02-AC08, R02-AC09, R02-AC10, R02-AC13, R02-AC16, R02-AC17, R02-AC18, R02-AC19; R03-AC18, as the screen run whose rows `holdings-50`'s case's equal |
| `benchmark-other.yaml` | The example with another benchmark symbol, `'IWM'` | R02-AC03, R02-AC07, R02-AC08, R02-AC13, R02-AC18 |
| `definition.yaml` | The example's settings, as schema version 1.1.0, ranked by the [ranking example](../../../docs/contracts.md#ranking-example)'s definition, [`../experiment-configs/ranking/value-momentum.xml`](../experiment-configs/ranking/README.md), with `percentile_nas_negative`: the case of [`ranking-example.yaml`](../experiment-configs/README.md)'s baseline, as a screen run. Its title and purpose say so. | R04-AC02, in `tests/contract/test_ranking_definitions.py`, which reads each [invalid definition](../experiment-configs/ranking/invalid/README.md) through it; and, in the modules release 0.4.0's [test pairing](../../../docs/releases/0.4.0-ranking-weights.md#test-pairing) names, R04-AC01, R04-AC02, R04-AC03, R04-AC04, R04-AC05, R04-AC06, R04-AC08, R04-AC11, R04-AC12, and R04-AC13 |
| `value-heavy.yaml` | `definition.yaml`, ranked by [`../experiment-configs/ranking/value-heavy.xml`](../experiment-configs/ranking/README.md), the definition the ranking example's `value-heavy` variant gives: the case of that variant, as a screen run. Its title and purpose say so. | R04-AC04, as the result of [`../review-configs/ranking-weights.yaml`](../review-configs/README.md) and `ranking-undeclared.yaml`, in `tests/core/test_differences.py`, `tests/core/test_review_report.py`, and `tests/interface/test_review_weights.py` |
| `positions.yaml` | `definition.yaml`, ranked by [`../experiment-configs/ranking/positions.xml`](../experiment-configs/ranking/README.md): the baseline of [`ranking-positions.yaml`](../experiment-configs/README.md), as a screen run | R04-AC04, as the baseline of `../review-configs/ranking-removal.yaml`, the alignment's limit, in `tests/core/test_differences.py` |
| `positions-without-first-yield.yaml` | `definition.yaml`, ranked by `../experiment-configs/ranking/positions-without-first-yield.xml`: `positions.xml` without the first of its two factors named Yield, as `ranking-positions.yaml`'s `no-first-yield` case removes it | R04-AC04, as the result of `../review-configs/ranking-removal.yaml`, in `tests/core/test_differences.py` |

R02-T06 added `holdings-50.yaml` and `benchmark-other.yaml` ahead of R02-T09, for the comparison core's tests. R04-T06 added `definition.yaml`, and R04-T11 `value-heavy.yaml`, `positions.yaml`, and `positions-without-first-yield.yaml`, for the review's weight rows.
