"""Trial Folio's contracts as Pydantic models (docs/contracts.md; ADR 0002).

The models are the executable structure, and the JSON Schemas under `schemas/` are generated from
them by `scripts/schemas`. docs/contracts.md stays authoritative for meaning: a model that accepts
something it calls invalid has a defect.

- `screen_configuration`: the `kind: screen` configuration, which `trialfolio.configuration` reads
- `screen_settings`: the 23 screen settings, in order
- `plan`: `plan.json`
- `attempt`: `started.json` and `attempt.json`
- `manifest`: the run manifest
- `tables`: rows of `metrics.csv` and `settings.csv`
- `summary`: the `--json` summary
- `acknowledgment`: the license acknowledgment record
- `schema_files`: schema generation and the drift check
"""
