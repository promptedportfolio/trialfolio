# DataMiner ScreenBacktest reference exports

These are the reference configurations for release 0.1.0, task R01-T01 ([0.1.0 spec](../../docs/releases/0.1.0-review.md#implementation-tasks-and-dependencies)). They produce real DataMiner exports so the importer can be built against the actual file layout instead of a guessed one.

The configurations and this run record are committed. The exports contain Portfolio123 data, so they go in `exports/`, which is git-ignored and never committed ([REQ-11](../../docs/spec.md#enduring-requirements)).

## The three runs

| File | Differs from A | What it exercises in a review |
|---|---|---|
| [a-baseline.yaml](a-baseline.yaml) | — | The baseline |
| [b-max-holdings-50.yaml](b-max-holdings-50.yaml) | Max Num Holdings 25 → 50 | A declared intended change |
| [c-benchmark-vti.yaml](c-benchmark-vti.yaml) | Benchmark SPY → VTI | Different benchmarks: flagged, with benchmark-relative metrics not differenced |

Every setting that affects results is explicit, including `Vendor: FactSet`, which is Portfolio123's standard data. The configurations don't rely on DataMiner's defaults, such as End Date = today and Slippage = 0. Tests for absent settings use synthetic configurations, which cost no credits.

The choices below are proposed; change any of them before running:

- **Universe `SP500`.** It is a Portfolio123 universe named in DataMiner's documentation.
- **Rule.** One liquidity rule.
- **Ranking.** A single `EarnYield` formula. A single formula creates or overwrites nothing in your account. Ranking definitions given as nodes or XML would overwrite `APIRankingSystem`.
- **Dates.** 2016-01-01 to 2025-12-31.
- **Rebalancing.** Every 4 weeks.
- **Slippage** 0.25%.
- **Precision** 4 decimal places.

## How to run

1. **Install DataMiner.** Download the current build from Portfolio123's [DataMiner page](https://portfolio123.customerly.help/en/articles/13764-dataminer). The build may differ from DataMiner's GitHub source, so record the version it shows.
2. **Record credits.** Note your API credit balance, under Account Settings → "DataMiner & API". Portfolio123 documents a screen backtest as 5 credits, so the three runs should cost about 15.
3. **Enter credentials.** Enter your API ID and key when DataMiner asks. Leave **"save credentials" unticked**, unless you accept that DataMiner stores them in a plaintext `config.ini`.
4. **Run each file** unchanged. Use **"Save output"** to save the result as `exports/<same name>.csv`, for example `exports/a-baseline.csv`.
5. **Leave the CSVs as saved.** Don't open and re-save them in Excel or another editor, because that can change their bytes and formatting.
6. **Fill in the run record below.** If DataMiner rejects a setting or the run fails, record the exact error message and stop. Don't improvise a fix; the configuration gets corrected here first.

## Run record

| File | Run date and time | DataMiner version | Credits before → after | Result or error |
|---|---|---|---|---|
| a-baseline.yaml | | | | |
| b-max-holdings-50.yaml | | | | |
| c-benchmark-vti.yaml | | | | |

## Basis

The key names, the section names (`Main`, `Default Settings`), and the single-formula ranking syntax come from these sources, checked 2026-10-01:

- Portfolio123's documentation of the [ScreenBacktest operation](https://portfolio123.customerly.help/en/articles/14056-dataminer-operation-screen-backtest).
- Its documentation of [ranking definitions](https://portfolio123.customerly.help/en/articles/13793-dataminer-ranking-definition).
- DataMiner's source at commit `721f3deaa8bcb564846229506e6f84e3a41f9008`, which was read to confirm key names.

The configurations are original. No DataMiner sample configuration was copied ([ADR 0001](../../docs/adrs/0001-python-and-portfolio123-integration.md)). None of them has been run yet.
