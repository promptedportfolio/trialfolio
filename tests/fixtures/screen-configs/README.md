# Screen configurations

Synthetic screen configurations for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). Each one is the [documented example](../../../docs/contracts.md#example), changed as its row says. [`invalid/`](invalid/README.md) holds one file for each rejection rule.

- **Origin:** written for Trial Folio's tests. The ranking system name and ID are invented, and so are the canary values. No value comes from Portfolio123 or from the owner's account.
- **Schema version:** [screen configuration](../../../docs/contracts.md#screen-configuration) 1.0.0.
- **Redistribution:** synthetic, so they may be committed and shared.

| File | Contents | Criteria |
|---|---|---|
| `formula.yaml` | The documented example, byte for byte: a single-formula ranking, with no `data_vendor` | R01-AC01, R01-AC10, R01-AC11, R01-AC24, R01-AC25, R01-AC30 |
| `ranking-name.yaml` | The example, ranking by an invented ranking system name | R01-AC10, R01-AC30 |
| `ranking-id.yaml` | The example, ranking by an invented ranking system ID | R01-AC10, R01-AC30 |
| `vendor-factset.yaml` | The example with `data_vendor: FactSet` | R01-AC11, R01-AC25 |
| `written-differently.yaml` | The example's settings, written differently: keys in another order, `slippage_percent: 0.250`, dates as quoted strings, the universe and benchmark in double quotes, and `data_vendor: FactSet` | R01-AC25 |
| `slippage-whole.yaml` | The example with `slippage_percent: 1` | R01-AC25 |
| `title-non-ascii.yaml` | The example with a title that contains `Café` and other non-ASCII text | R01-AC25 |
| `canaries.yaml` | The example with a distinct canary string in the title, the purpose, the universe, each of two rules, the ranking formula, and the benchmark | R01-AC01, R01-AC17 |
