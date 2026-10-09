# Revisions of the experiment example

Synthetic experiment configurations, each [`example.yaml`](../example.yaml) with one change, or, for `two-holdings-reordered.yaml`, `two-holdings.yaml` with one, given in its first line's comment ([fixtures](../../../../docs/contracts.md#fixtures)). Each tests a kind of change that [experiment plans and revisions](../../../../docs/contracts.md#experiment-plans-and-revisions) lists: a revision, with the cases it keeps, adds, and retires, and the parts it changes, or another experiment, which isn't a revision.

- **Origin:** written for Trial Folio's tests from `example.yaml`. The changed values are invented. No value comes from Portfolio123 or from the owner's account.
- **Schema version:** [experiment configuration](../../../../docs/contracts.md#experiment-configuration) 1.0.0.
- **Redistribution:** synthetic, so they may be committed and shared.

R03-T07 wrote these files, for `tests/core/test_experiment_plan.py`, which plans `example.yaml`, or `two-holdings.yaml`, and then each file as its revision, for R03-AC07's core check, and for R03-AC02's with `key-renamed.yaml` and `two-holdings-reordered.yaml`. The last column gives the criteria that the tests later tasks write use each one for. Release 0.3.0's [test pairing](../../../../docs/releases/0.3.0-experiments.md#test-pairing) names one more, `default-only-budget-3.yaml`, which a later task writes with its test.

| File | The change | What it is to the plan before it | Later criteria |
|---|---|---|---|
| `holdings-40.yaml` | `holdings-50`'s value is 40, under its key | A revision that adds a case and retires one, both keyed `holdings-50` | R03-AC03, R03-AC07 |
| `key-renamed.yaml` | `holdings-50` is keyed `max-holdings-50` | A revision of `case_keys`, which keeps every case's `case_id` | R03-AC02, R03-AC07 |
| `description-changed.yaml` | `liquidity-100m`'s description changed | A revision of `case_descriptions` | R03-AC07 |
| `purpose-changed.yaml` | The purpose changed | A revision of `purpose` | R03-AC03, R03-AC07 |
| `prior-research-changed.yaml` | The prior-research declaration is `complete`, with another description | A revision of `prior_research` | R03-AC07 |
| `budget-raised.yaml` | A budget of 8 | A revision of `budget` | R03-AC07 |
| `budget-lowered.yaml` | A budget of 5 | A revision of `budget` | R03-AC10 |
| `variant-removed.yaml` | `slippage-050` removed | A revision that retires its case | R03-AC03, R03-AC07 |
| `default-explicit.yaml` | A `rebalance_weeks` list that gives the default variant's value, 1, under its key | A revision of `case_variants`: the case is kept, and its `default` is false | R03-AC07 |
| `other-experiment-id.yaml` | Another `experiment_id` | Another experiment, not a revision: `output.not_empty` | R03-AC07 |
| `other-universe.yaml` | The universe `'Easy to Trade US'` | Another experiment, not a revision: `output.not_empty` | R03-AC07 |
| `two-holdings.yaml` | Two `max_holdings` variants, `holdings-40` and then `holdings-50` | A revision that adds `holdings-40` | R03-AC07 |
| `two-holdings-reordered.yaml` | From `two-holdings.yaml`: its two variants in the other order | To `two-holdings.yaml`'s plan, a revision of `case_order` that keeps every case | R03-AC07 |
