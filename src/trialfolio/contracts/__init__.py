"""Trial Folio's contracts as Pydantic models (docs/contracts.md; ADR 0002).

The models are the executable structure, and the JSON Schemas under `schemas/` are generated from
them by `scripts/schemas`. docs/contracts.md stays authoritative for meaning: a model that accepts
something it calls invalid has a defect.

- `screen_configuration`: the `kind: screen` configuration, versions 1.0.0 and 1.1.0, which
  `trialfolio.configuration` reads, and `ScreenFields`, a screen's settings
- `review_configuration`: the `kind: review` configuration, which `trialfolio.configuration` reads
- `experiment_configuration`: the `kind: experiment` configuration, versions 1.0.0 and 1.1.0,
  which `trialfolio.configuration` reads, and its variants in the order of its cases
- `ranking_snapshot_configuration`: the `kind: ranking-snapshot` configuration
- `screen_settings`: the 23 screen settings, in order, and the weight row
- `plan`: `plan.json`, versions 1.0.0 and 1.2.0, a screen's
- `experiment_plan`: `plan.json`, versions 1.1.0 and 1.3.0, an experiment's
- `experiment_record`: `experiment.json`, versions 1.0.0 and 1.1.0, and `session.json`
- `attempt`: `started.json` and `attempt.json`, versions 1.0.0 to 1.3.0, `updating.json`, and
  `authenticating.json`
- `manifest`: the run manifest, versions 1.0.0 and 1.1.0
- `review_manifest`: the review manifest
- `experiment_manifest`: the experiment manifest, versions 1.0.0 and 1.1.0
- `ranking_snapshot`: a ranking snapshot's plan, `snapshot.json`, and manifest
- `tables`: rows of `metrics.csv`, `settings.csv`, and `differences.csv`, and of `settings.csv`
  1.1.0 and `differences.csv` 1.1.0
- `summary`: the `--json` summary, versions 1.0.0, 1.1.0, and 1.2.0
- `acknowledgment`: the license acknowledgment record
- `schema_files`: schema generation and the drift check
"""
