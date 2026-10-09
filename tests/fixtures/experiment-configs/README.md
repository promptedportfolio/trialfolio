# Experiment configurations

Synthetic experiment configurations for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). [`invalid/`](invalid/README.md) holds one file for each rejection rule, and [`revisions/`](revisions/README.md) `example.yaml` with one change each.

- **Origin:** written for Trial Folio's tests from the [documented examples](../../../docs/contracts.md#experiment-example). The keys, descriptions, and other text are invented. No value comes from Portfolio123 or from the owner's account.
- **Schema version:** [experiment configuration](../../../docs/contracts.md#experiment-configuration) 1.0.0.
- **Redistribution:** synthetic, so they may be committed and shared.

R03-T06 wrote `example.yaml`, `no-microcaps.yaml`, and `invalid/`, and R03-T07 `written-differently.yaml`, `default-only.yaml`, and `revisions/`. Release 0.3.0's [test pairing](../../../docs/releases/0.3.0-experiments.md#test-pairing) lists the others the later tasks write, with what each holds.

| File | Contents | Criteria |
|---|---|---|
| `example.yaml` | The [experiment example](../../../docs/contracts.md#experiment-example), byte for byte: five cases, `baseline`, `liquidity-100m`, `holdings-50`, the default `rebalance-weeks-1`, and `slippage-050`, and a budget of 6 | The documented examples' check, in [other checks in the default suite](../../../docs/releases/0.3.0-experiments.md#test-pairing); and, in the tests later tasks write, R03-AC01 to R03-AC11, R03-AC13, R03-AC14, R03-AC16, R03-AC18, and R03-AC19 |
| `no-microcaps.yaml` | The second example as a whole file: `example.yaml` with the universe `'Easy to Trade US'`, and the second example's `variants`, the `no-microcaps` rule and `rebalance_weeks: []`, so two cases | The documented examples' check; and, in the tests later tasks write, R03-AC01 and R03-AC18 |
| `written-differently.yaml` | `example.yaml`'s experiment, written differently: keys, and the settings in `variants`, in another order; comments; a baseline slippage of `0.250` and a variant's of `0.50`; dates as quoted strings; and the universe and benchmark in double quotes. It gives `example.yaml`'s plan. | R03-AC02, in `tests/core/test_experiment_plan.py`; and, in the tests later tasks write, R03-AC18 |
| `default-only.yaml` | `example.yaml`'s research context and baseline, with no `variants`, so its cases are `baseline` and the default `rebalance-weeks-1`, and a budget of 2 | The default variant, in `tests/core/test_experiment_plan.py`; and, in the tests later tasks write, R03-AC06, R03-AC10, R03-AC12, R03-AC14, and R03-AC19 |
