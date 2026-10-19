# Ranking snapshot configurations

Synthetic ranking snapshot configurations for Trial Folio's tests ([fixtures](../../../docs/contracts.md#fixtures)). Each names a ranking system by name, as the [ranking snapshot configuration](../../../docs/contracts.md#ranking-snapshot-configuration) does. [`invalid/`](invalid/README.md) holds one file for each rejection rule.

- **Origin:** written for Trial Folio's tests by R04-T05. The system names are invented, except `ApiRankingSystem`, the system Trial Folio writes, and so is the canary value. No name comes from the owner's account.
- **Schema version:** [ranking snapshot configuration](../../../docs/contracts.md#ranking-snapshot-configuration) 1.0.0.
- **Redistribution:** synthetic, so they may be committed and shared.

| File | Contents | Criteria |
|---|---|---|
| `example.yaml` | The [snapshot example](../../../docs/contracts.md#ranking-snapshot-configuration), byte for byte | R04-AC08; the source of [`snapshots/synthetic-snapshot-1.0.0/`](../snapshots/README.md), which the synthetic writer takes with the demo's client |
| `api-ranking-system.yaml` | The live check's snapshot: `system: 'ApiRankingSystem'`, the system Trial Folio writes | R04-AC07 and R04-AC08, in the live check, `tests/live/test_ranking.py` |
| `canaries.yaml` | A canary string as the system's name, which `responses/rank-get-canaries.json` answers | R04-AC11, in `tests/interface/test_logs.py` |
