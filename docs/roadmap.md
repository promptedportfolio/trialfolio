# Trial Folio roadmap

**Status:** Draft
**Date:** 2026-10-01

This document owns the release sequence, dependencies, the value of each increment, and deferred scope. It does not track progress. Each release specification's **Status** line is authoritative, and the roadmap only links to it. The roadmap by itself is not an implementation assignment; an agent implements a release only when that release specification is assigned.

## Principles

- **Each release is useful on its own.** A release must stay useful if development pauses for months after it. A release includes its documentation, installation path, meaningful verification, and example.
- **Narrow before deferring correctness.** When time is short, the functionality is narrowed; basic correctness is never deferred to a later release.
- **Scope targets are not deadlines.** Releases 0.1.0, 0.2.0, and 0.3.0 are sized for about one, two, and three cumulative focused working days, which may be spread over two weeks. They are scope targets, not promises, and verification is never skipped to meet them.
- **Implemented is not Released ([D-08](spec.md#decisions)).** A release is Implemented when it works, is verified, and is used privately by the owner. It becomes Released, meaning publicly distributed, only after Nathan Slaughter adopts the license and chooses a distribution channel consistent with the no-publication restriction. The gates are listed in [licensing-policy.md](licensing-policy.md).
- **Reference data is procured when needed ([D-09](spec.md#decisions)).** No representative export or provider payload exists yet. The first task of each release that depends on a provider format is procuring a reference sample with the owner's credentials, and the owner does any Portfolio123 web-UI steps.

## Releases 0.1.0 to 0.3.0

| Release | User outcome | Adds | Depends on | Key external dependency |
|---|---|---|---|---|
| [0.1.0 Review](releases/0.1.0-review.md) | Compare existing DataMiner screen-backtest results with their configurations and see what differs | Offline import of one verified ScreenBacktest CSV layout, comparison against an explicit baseline, a self-contained report, normalized CSV, and a manifest | None | One reference ScreenBacktest export, procured under D-09 |
| [0.2.0 API execution](releases/0.2.0-api-execution.md) | Run one supported screen backtest and keep the link between its settings and results | `p123api` as an input adapter, plan and approval, a saved request and payload, and the same result contract and report as 0.1.0 | 0.1.0 | A working account, one reference payload, and a real integration check |
| [0.3.0 Experiments](releases/0.3.0-experiments.md) | Run and review a controlled, finite experiment | A baseline plus predefined variants, stable case and attempt identities, sequential execution, resume, and uncertain-completion handling | 0.2.0 | Verified backend support for each variant type offered |

The 0.1.0 import and report path stays supported in later releases, and 0.2.0 output uses the same result contract and report. Automatic search, sophisticated scheduling, and statistical acceptance decisions are outside all three.

## After 0.3.0

These are proposed increments. Names, order, and estimates are refined as their dependencies are understood. None of them is specified yet.

| Increment | Added investor value | Important dependency |
|---|---|---|
| Descriptive return analytics (proposed addition, see below) | A fixed, versioned analysis set for archived return series: full-period metrics, gross versus net, drawdowns, rolling returns over several holding periods, and period splits | Return series of adequate granularity in archived payloads; benchmark series |
| Simulation review | Inspect and compare saved simulations: settings, holdings, transactions, and available performance | Verified strategy endpoints and output granularity |
| Robustness and rank diagnostics | Test predefined perturbations and inspect rank behavior, including quantile buckets; rerun supported simulation variants | Isolated provider state, comparable outputs, cost semantics |
| Statistical evaluation | Chronological evaluation, uncertainty estimation, and multiple-testing procedures | Sufficient return data, research history, a frozen protocol, validated methods, and a methods ADR |
| Forward tracking | Compare timestamped signals and modeled execution with later observed results and imported fills | Identifier alignment, price conventions, execution records |
| Optional discovery | Use FactorMiner or bounded LLM proposals to generate candidates within development data | Reliable evaluation boundaries and complete selection history; the model backends of [REQ-10](spec.md#enduring-requirements) |

**Descriptive return analytics** is a proposed addition to the guide's sequence, made because of the driving use case ([D-10](spec.md#decisions)). Reproduction studies need the same descriptive analysis for every study before any statistical evaluation exists. It computes descriptive numbers only, with no significance claims. The wrapper source shows per-rebalance-period screen returns, benchmark returns, turnover, and position counts in the screen-backtest payload. DataMiner's export appears to carry the same series. Both observations are unverified until 0.1.0 and 0.2.0 inspect real samples ([ADR 0001](adrs/0001-python-and-portfolio123-integration.md#verification-notes)). If they hold, this increment can follow 0.3.0 directly, using screen-backtest payloads that 0.2.0 and 0.3.0 already archive.

The two to four working weeks estimated earlier applies to a broader validated tool. It is not a prerequisite for 0.1.0, and it is not a schedule for the full scientific roadmap.

### Ranks, screens, and simulations

Each serves a different purpose, and not every study needs all three:

- Rank snapshots, bucket behavior, factor-removal tests, and information coefficients diagnose signals.
- Screens give simple portfolio baselines and sensitivity experiments.
- Simulations represent holdings, trading rules, turnover, cash, and execution assumptions.

A strong factor diagnostic is not evidence that a portfolio implementation is tradable. The actual proposed portfolio rules are evaluated before any deployment assessment ([METH-06](methodology.md)).

## Driving use case coverage

This table maps what reproducing published factor research needs ([spec.md, Primary use](spec.md#primary-use); [METH-09](methodology.md)) to the increment that first delivers it. "Preserved" means the evidence is kept, even though it is not yet analyzed.

| Research need | First delivered | Notes |
|---|---|---|
| Every result and case kept, including failures | 0.1.0 (preserved); 0.3.0 (full case accounting) | INV-01, INV-07 |
| Settings compared, with intended changes separated from unexplained mismatches | 0.1.0 | The first step toward a deviation record against the paper |
| Deviation record against the paper's method | Statistical evaluation (study records) | Needs a study-protocol contract; the protocol is owned by [methodology.md](methodology.md) |
| Preregistered plan: purpose, planned cases, declared prior research | 0.3.0 (plan and purpose); Statistical evaluation (full protocol) | The approved plan hash is the record that cases were declared before execution |
| Full universe versus excluding microcaps | 0.3.0, if universe variants are verified backend capabilities | Otherwise, the next increment that verifies them |
| Stable-identifier universe slices | 0.3.0, if universe rules can express them | Slices share dates and are not independent confirmations (METH-09) |
| Paper's rebalance versus practitioner screen with a rank-drop sell rule | 0.3.0 for rebalance variants; Simulation review for sell rules | Sell-rule support in screen backtests is unverified |
| Gross and net of declared costs | 0.2.0 (recorded settings); Descriptive return analytics (both computed) | Repricing a trade list is not a rerun (METH-06) |
| Rolling returns over several holding periods | Descriptive return analytics | Needs return series; unavailable from summary-only exports |
| Quantile-bucket returns and top-minus-bottom spread | Robustness and rank diagnostics | DataMiner's RankPerformance runs one screen backtest per bucket; it is not assumed equivalent to a direct rank-performance call |
| Period splits around the paper's sample and publication | Descriptive return analytics | Descriptive only until Statistical evaluation |
| Model-drafted setups logged with first output unedited | Optional discovery | METH-08 |

## Deferred scope

Deferred until a later increment is specified:

- Any statistical acceptance decision, significance badge, or deployment judgment.
- Automatic search and adaptive experiment generation.
- Parallel or scheduled execution.
- Simulation, rank-performance, and rolling-screen operations.
- Tiingo integration.
- Runtime LLM features.
- A desktop, local web, or hosted interface; see [licensing-policy.md](licensing-policy.md) for the conditions that apply first.
- Parquet storage and a SQLite index.
- Import formats other than the one verified ScreenBacktest layout.
- Data vendors other than FactSet, including Compustat. This is out of scope, not merely deferred ([D-16](spec.md#decisions)); it needs a new owner decision and an account to test with.

## Open questions

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| Does Descriptive return analytics come before Simulation review? | Order of increments | Put it first if the 0.2.0 reference payload confirms the per-period series; otherwise, after Simulation review | End of 0.2.0 |
| Which variant types can 0.3.0 offer? | 0.3.0 scope | Only the types whose backend support is recorded with integration evidence in 0.2.0 or 0.3.0 | 0.3.0 specification Ready |
