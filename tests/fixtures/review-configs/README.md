# Review configurations

Synthetic review configurations for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). [`invalid/`](invalid/README.md) holds one file for each rejection rule.

- **Origin:** written for Trial Folio's tests. The labels, paths, and text are invented. No value comes from Portfolio123 or from the owner's account.
- **Schema version:** [review configuration](../../../docs/contracts.md#review-configuration) 1.0.0.
- **Redistribution:** synthetic, so they may be committed and shared.

Each configuration names its runs by paths relative to itself, and a test puts it beside the runs it builds ([0.2.0's test pairing](../../../docs/releases/0.2.0-review.md#test-pairing)).

| File | Contents | Criteria |
|---|---|---|
| `example.yaml` | The [documented example](../../../docs/contracts.md#review-configuration), byte for byte: `hold25`, the baseline, and `hold50`, which declares `max_holdings` | R02-AC01, R02-AC02, R02-AC05, R02-AC07, R02-AC08, R02-AC09, R02-AC18, R02-AC19 |
