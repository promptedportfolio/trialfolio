# Reviews

Complete reviews, kept as Trial Folio wrote them, for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). Each one is the [historical fixture](../../../docs/contracts.md#artifact-compatibility) for the schema versions its name gives, so it changes only with a stated reason, and never to make a test pass.

- **Origin:** written by `trialfolio review`, from a review configuration in [`review-configs/`](../review-configs/README.md) and copies of the committed run [`runs/synthetic-run-1.0.0/`](../runs/README.md), which `trialfolio demo` wrote. Every value is invented, and nothing was sent to Portfolio123. No value comes from Portfolio123 or from the owner's account.
- **Schema versions:** given by each review's name, and by its manifest's entries.
- **Redistribution:** synthetic, so they may be committed and shared.

| Review | Contents | Criteria |
|---|---|---|
| `synthetic-review-1.0.0/` | The review `trialfolio review synthetic-only.yaml --out tests/fixtures/reviews/synthetic-review-1.0.0` wrote on 2026-10-06, with `TRIALFOLIO_ACCEPT_LICENSE` set, from [`review-configs/synthetic-only.yaml`](../review-configs/synthetic-only.yaml), placed beside a copy of `runs/synthetic-run-1.0.0/` at its `run` path, `runs/demo`. R02-T10 committed it unchanged. Its two results, `demo`, the baseline, and `demo-again`, both name that run, so they share its saved response. It holds every file of a 0.2.0 review, in the 1.0.0 schemas of the review configuration, the review manifest, and `differences.csv`; the copies of the run's manifest, plan, and tables, in their 1.0.0 schemas; and `logs/`, which the manifest doesn't list. Its manifest is `synthetic`. It was written from the branch `test/r02-t10-review-tests`, by Trial Folio 0.2.0, the package's version since 0.2.0's specification was completed ([D-26](../../../docs/spec.md#decisions)), on Python 3.14.8 and macOS 26.6.2. | [Artifact compatibility](../../../docs/contracts.md#artifact-compatibility), through `tests/contract/test_historical_artifacts.py` |
