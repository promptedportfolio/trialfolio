# Revisions of the experiment example

Synthetic experiment configurations, each [`example.yaml`](../example.yaml) with one change, or, for `two-holdings-reordered.yaml`, `two-holdings.yaml` with one, for `default-only-budget-3.yaml`, [`default-only.yaml`](../default-only.yaml) with one, and for the `ranking-` files, [`ranking-example.yaml`](../ranking-example.yaml) or `example.yaml` with the changes given in its first line's comment ([fixtures](../../../../docs/contracts.md#fixtures)). Each tests a kind of change that [experiment plans and revisions](../../../../docs/contracts.md#experiment-plans-and-revisions) lists: a revision, with the cases it keeps, adds, and retires, and the parts it changes, or another experiment, which isn't a revision.

- **Origin:** written for Trial Folio's tests from `example.yaml`. The changed values are invented. No value comes from Portfolio123 or from the owner's account.
- **Schema version:** [experiment configuration](../../../../docs/contracts.md#experiment-configuration) 1.0.0, and 1.1.0 for the `ranking-` files, which name their definitions by their paths from this directory, such as `../ranking/value-momentum.xml`.
- **Redistribution:** synthetic, so they may be committed and shared.

R03-T07 wrote these files, for `tests/core/test_experiment_plan.py`, which plans `example.yaml`, or `two-holdings.yaml`, and then each file as its revision, for R03-AC07's core check, and for R03-AC02's with `key-renamed.yaml` and `two-holdings-reordered.yaml`. The last column gives the criteria that the later tasks' tests use each one for, R03-T13's and R03-T11's. R03-T11 wrote one more, `default-only-budget-3.yaml`, [`default-only.yaml`](../default-only.yaml) with one change, for R03-AC10. Release 0.4.0's R04-T07 wrote the `ranking-` files, for `tests/core/test_ranking_plan.py`, which plans `ranking-example.yaml`, or `example.yaml`, and then each file as its revision, as plans with a ranking definition revise them; the last column gives the criteria release 0.4.0's [test pairing](../../../../docs/releases/0.4.0-ranking-weights.md#test-pairing) names them for. The fixes of [D-45](../../../../docs/spec.md#decisions) wrote `ranking-key-renamed.yaml`, for `tests/core/test_stale_backtests.py`, which resumes a flagged case under it.

| File | The change | What it is to the plan before it | Later criteria |
|---|---|---|---|
| `holdings-40.yaml` | `holdings-50`'s value is 40, under its key | A revision that adds a case and retires one, both keyed `holdings-50` | R03-AC03, R03-AC07, R03-AC08, R03-AC11, R03-AC16 |
| `key-renamed.yaml` | `holdings-50` is keyed `max-holdings-50` | A revision of `case_keys`, which keeps every case's `case_id` | R03-AC02, R03-AC07 |
| `description-changed.yaml` | `liquidity-100m`'s description changed | A revision of `case_descriptions` | R03-AC07 |
| `purpose-changed.yaml` | The purpose changed | A revision of `purpose` | R03-AC03, R03-AC07 |
| `prior-research-changed.yaml` | The prior-research declaration is `complete`, with another description | A revision of `prior_research` | R03-AC07 |
| `budget-raised.yaml` | A budget of 8 | A revision of `budget` | R03-AC07, R03-AC11 |
| `budget-lowered.yaml` | A budget of 5 | A revision of `budget` | R03-AC08, R03-AC10 |
| `variant-removed.yaml` | `slippage-050` removed | A revision that retires its case | R03-AC03, R03-AC07, R03-AC08 |
| `default-explicit.yaml` | A `rebalance_weeks` list that gives the default variant's value, 1, under its key | A revision of `case_variants`: the case is kept, and its `default` is false | R03-AC07 |
| `other-experiment-id.yaml` | Another `experiment_id` | Another experiment, not a revision: `output.not_empty` | R03-AC07, R03-AC16 |
| `other-universe.yaml` | The universe `'Easy to Trade US'` | Another experiment, not a revision: `output.not_empty` | R03-AC07, R03-AC16 |
| `two-holdings.yaml` | Two `max_holdings` variants, `holdings-40` and then `holdings-50` | A revision that adds `holdings-40` | R03-AC07 |
| `two-holdings-reordered.yaml` | From `two-holdings.yaml`: its two variants in the other order | To `two-holdings.yaml`'s plan, a revision of `case_order` that keeps every case | R03-AC07 |
| `default-only-budget-3.yaml` | From `default-only.yaml`: a budget of 3 | To `default-only.yaml`'s plan, a revision of `budget` | R03-AC08, R03-AC10 |
| `ranking-definition-changed.yaml` | From `ranking-example.yaml`: the baseline's definition [`value-momentum-revised.xml`](../ranking/README.md), whose Value factors weigh 60 and 40, and a budget of 12: the 8 requests `ranking-example.yaml` sends, and two for each of the two new cases | A revision that retires `baseline` and `value-heavy`, whose definitions change, and adds them again, and keeps `tilt-earnings-yield` and `no-sales-yield`, whose definitions don't; and of `budget` | R04-AC10 |
| `ranking-method-changed.yaml` | From `ranking-example.yaml`: the ranking method `percentile_nas_neutral` | A revision that retires every case, and adds each again | R04-AC10 |
| `ranking-budget-raised.yaml` | From `ranking-example.yaml`: a budget of 10 | A revision of `budget`, which keeps every case | R04-AC10 |
| `ranking-key-renamed.yaml` | From `ranking-example.yaml`: `value-heavy` is keyed `heavy-value` | A revision of `case_keys`, which keeps every case's `case_id` | D-45 |
| `ranking-from-formula.yaml` | From `example.yaml`, as schema version 1.1.0: its baseline ranked by `value-momentum.xml`, with `percentile_nas_negative`, in place of its formula, and a budget of 15: the 5 requests `example.yaml` sends, and two for each of its five new cases | To `example.yaml`'s plan 1.1.0, a revision into a plan 1.3.0 that retires every case, and adds each again; and of `budget`. Its `experiment.json` is 1.1.0. | R04-AC10 |
