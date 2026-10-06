# Runs

Complete runs, kept as Trial Folio wrote them, for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). Each one is the [historical fixture](../../../docs/contracts.md#artifact-compatibility) for the schema versions its name gives, so it changes only with a stated reason, and never to make a test pass.

- **Origin:** written by `trialfolio demo`, from the packaged [demo data](../../../src/trialfolio/demo_data/README.md). Every value is invented, and nothing was sent to Portfolio123. No value comes from Portfolio123 or from the owner's account.
- **Schema versions:** given by each run's name, and by its manifest's entries.
- **Redistribution:** synthetic, so they may be committed and shared.

| Run | Contents | Criteria |
|---|---|---|
| `synthetic-run-1.0.0/` | The run `trialfolio demo --out tests/fixtures/runs/synthetic-run-1.0.0` wrote on 2026-10-04, with `TRIALFOLIO_ACCEPT_LICENSE` set, under Trial Folio 0.1.0, Python 3.12.13, and macOS 26.6.2: every file of a 0.1.0 run, in the 1.0.0 schemas of the plan, the start record, the attempt record, the run manifest, and the normalized tables, and `logs/`, which the manifest doesn't list. R01-T16 committed it unchanged. Its manifest labels it synthetic, with the approval `not_required`. | R01-AC08, R01-AC13, R01-AC23; R02-AC02, R02-AC06, and R02-AC14, through `tests/core/test_review_inputs.py`; R02-AC09 and R02-AC16, as the demo's run in `review-configs/synthetic.yaml` and `synthetic-only.yaml`, through `tests/core/test_review_report.py`, and R02-AC16 through `tests/interface/test_review.py` too; [artifact compatibility](../../../docs/contracts.md#artifact-compatibility), through `tests/contract/test_historical_artifacts.py` |
