# Demo data

The synthetic configuration and response that `trialfolio demo` packages and runs offline ([CLI behavior](../../../docs/contracts.md#cli-behavior)). They ship in the wheel.

- **Origin:** written for Trial Folio. Every value is invented. No value comes from Portfolio123 or from the owner's account.
- **Redistribution:** synthetic, so they may be shared with the package.
- **`screen.yaml`:** the [documented example](../../../docs/contracts.md#example), retitled as a synthetic example, in [screen configuration](../../../docs/contracts.md#screen-configuration) 1.0.0.
- **`response.json`:** the test fixture `tests/fixtures/responses/complete.json` without `cost` and `quotaRemaining`, in the layout of [`p123api-screen-backtest` version 1](../../../docs/contracts.md#p123api-screen-backtest-version-1). Nothing was charged, so the demo's run reports no cost.
- **Criteria:** R01-AC16, and the run `runs/synthetic-run-1.0.0/` that R01-T16 commits from `demo`'s output.
