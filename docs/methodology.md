# Research methodology

Status: Draft design, prepared 2026-10-01. No method in this document is implemented or validated.

This document defines what Trial Folio's scientific assessments mean, the conditions under which they may be made, and the evidence each one requires. It is a research design, not a description of working software.

- [spec.md](spec.md) owns the product vocabulary (study, experiment, case, candidate, attempt, artifact, assessment, report) and the invariants INV-01 to INV-14.
- [contracts.md](contracts.md) owns the structures that record the artifacts named here. This document defines their meaning, not their fields.
- The [release specifications](releases/) own what each increment implements and how it is accepted.
- A methods ADR, written before the Statistical evaluation increment, owns the choice of inference method (see [Open questions](#open-questions)). The [statistics prototype](statistics-prototype.md) gathers its evidence ([D-43](spec.md#decisions)).

## Status and labels

Each method has one status:

| Status | Meaning |
|---|---|
| Proposed | Designed here; not implemented |
| Implemented | Code exists and its conformance tests pass; not independently verified |
| Validated | Implemented and checked against independent reference calculations and synthetic scenarios ([Verification of statistical methods](#verification-of-statistical-methods)) |
| Unavailable | Cannot be provided with the current data, access, or tool, either by nature or pending a dependency |

Every method is currently Proposed or Unavailable. A status changes only with the evidence the traceability table names, recorded in the release specification that delivered it.

Statements use the labels defined in [spec.md](spec.md): Requirement, Proposed default, Verified observation, Open question, and Deferred. MUST is required behavior; SHOULD is a default whose exceptions need a documented reason; MAY is optional.

## What the first three releases preserve without evaluating

Releases 0.1.0, 0.2.0, and 0.3.0 make no statistical, robustness, or deployment judgment. Every report they produce MUST label statistical validation and trading readiness "not assessed" (METH-07.3). They MUST still preserve the evidence that later assessments depend on, because it cannot be reconstructed afterwards.

| From | Evidence preserved | Why later assessments need it |
|---|---|---|
| 0.1.0 | Redacted request, full returned response and its hash, provider metadata, verified resolved settings, snapshots of mutable references, the response's reported precision | Later analysis without fresh provider data, honest treatment of reruns, and honest limits on what summary statistics support (METH-05.7, METH-05.10, INV-05) |
| 0.2.0 | Intended changes distinguished from unexplained differences in dates, benchmark, currency, costs, execution, and data source | A comparison means something only when its differences are known (METH-01.4, METH-09.3) |
| 0.3.0 | Study purpose, every planned case, declared prior research, every attempt and outcome, plan revisions | Research history for multiple-testing treatment (METH-03) and for separating development from confirmation (METH-02) |

INV-09 requires this history to exist before any statistical correction is implemented. A count that starts at installation is not a research history (METH-03.4).

## Traceability

"Artifacts" names what must be recorded; [contracts.md](contracts.md) defines the structure. "Evidence" names what must exist before the status can move past Proposed.

| ID | Requirement | Release or increment | Artifacts | Acceptance evidence | Status |
|---|---|---|---|---|---|
| METH-01 | Define the question before measuring success | Statistical evaluation (protocol); 0.3.0 records declared purpose | Study protocol; declared purpose | Protocol validation rejects a missing primary objective, benchmark, or cost input | Proposed |
| METH-01.4 | No silent benchmark, cost, or date defaults | 0.1.0 (resolve), 0.2.0 (flag) | Resolved settings; comparison flags | R01 plan shows every resolved setting; R02 fixtures with differing benchmarks | Proposed |
| METH-02 | Separate development, selection, and confirmation | Statistical evaluation | Partition boundaries; prior-exposure record; frozen candidate family | Tests that selection cannot read confirmation data; protocol archived before exposure | Proposed |
| METH-02.6 | Prove the owner never inspected data elsewhere | None | Limitation statement | Not achievable by a local tool | Unavailable |
| METH-03 | Research history and multiple testing | History from 0.3.0; treatment in Statistical evaluation | All cases, candidates, attempts, plan revisions, declared prior research, search-history status | R03 accounting fixtures; later, family construction tests | Proposed |
| METH-04 | Inference before any statistical badge | Statistical evaluation | Significance policy; estimates; adjusted and unadjusted p-values; seeds | Methods ADR; independent reference calculations; calibration under synthetic nulls | Proposed |
| METH-05 | Data integrity appropriate to the claim | 0.1.0 onward (provenance, coverage); Simulation review and later (point-in-time, universes) | Source artifacts; coverage records; exclusions with originals | Fixtures for missingness, duplicates, alignment, label boundaries | Proposed |
| METH-05.10 | No reconstruction from summary statistics | 0.1.0 | Capability declaration of the saved run | R01 report omits return-series, interval, and drawdown-history sections, and never exceeds the response's precision | Proposed |
| METH-06 | Robustness and economic usefulness | 0.3.0 (predefined variants run); Robustness and rank diagnostics (assessment) | Predefined perturbation set; cost and turnover records | Perturbation set archived before results; cost sensitivity reconciles with a full rerun where they differ | Proposed |
| METH-07 | Multidimensional assessment and permitted conclusions | 0.1.0 onward ("not assessed"); Statistical evaluation (outcomes) | Assessment record per dimension; applicable notice version | Report tests: dimensions separate; no affirmative judgment before its method is Validated | Proposed |
| METH-08 | Optional LLM research agents | Optional discovery | Proposal log; prompts; model identifiers; outputs; decisions | Contract tests with recorded responses; boundary tests that protected outcomes are never sent | Proposed |
| METH-09 | Reproducing published research | Partly 0.3.0 (variants the backend supports); later analyses and the Reproduction and sensitivity workflow as mapped in [roadmap.md](roadmap.md#driving-use-case-coverage) | Preregistered protocol; deviation record; fixed analysis-set version | A reproduction fixture study produces every analysis in the fixed set, including failed and inconclusive cases | Proposed |
| METH-09.7 | Rolling returns | Descriptive return analytics (0.5.0, [analysis set 1.0.0](#analysis-set-100)) | Dated return series (`series.csv`); the analysis set's values (`analysis.csv`) | Needs dated return series; window counts checked by hand on a fixture ([the example](#a-hand-checkable-example)) | Unavailable in 0.1.0; Proposed for 0.5.0 |

## METH-01 Define the question before measuring success

**METH-01.1 Confirmatory protocol.** Requirement: each confirmatory study MUST record the following before any evaluation result is seen.

| Field | Meaning |
|---|---|
| Economic hypothesis | Why the strategy should earn what it claims: a risk premium, a behavioral mispricing, a structural constraint. Not "the backtest was good." |
| Primary objective | Benchmark-relative performance after costs, or standalone return and risk (METH-01.2) |
| Estimand and null hypothesis | The quantity being estimated and the value it takes if the hypothesis is false |
| Target population and universe | The securities, dates, and eligibility rules the claim is about |
| Benchmark | The comparison series, why it suits this universe, and its return convention |
| Expected implementation | Holdings, rebalance frequency, execution timing, and the sell rule the claim assumes |
| Return frequency | The observation frequency used for inference, and how returns are compounded or aggregated |
| Costs | Commission, spread and slippage, and any financing or borrow, as explicit inputs |
| Minimum economically relevant effect | The smallest effect that would matter after costs; below it, a significant result is not useful |
| Risk constraints | Any drawdown, volatility, concentration, or capacity limits the result must respect |
| Testing direction | One- or two-sided alternative |
| Error criterion | The error rate and the family it controls (METH-04.4) |
| Stopping and selection rules | How candidates are chosen, when searching stops, and what ends the study |
| Partition boundaries and prior exposure | METH-02 |

**METH-01.2 One primary claim.** Proposed default: one primary claim per confirmatory study; all other metrics are reported as secondary. Trial Folio eventually supports two objective types:

1. Performance above a suitable benchmark after specified costs.
2. Attractive standalone returns and risk.

A study MUST choose its primary objective and decision criteria before seeing evaluation results. Reporting both objectives does not permit selecting whichever passes.

**METH-01.3 Metrics answer different questions.** These are distinct and MUST NOT be substituted for each other:

| Metric | Question it answers |
|---|---|
| Arithmetic mean active return | Average per-period return above the benchmark |
| Compound growth (CAGR) difference | Whether wealth grew faster than the benchmark over the whole period |
| Risk-adjusted alpha | Return not explained by exposure to the benchmark or declared factors, under a stated model |
| Information ratio | Mean active return per unit of tracking error |
| Standalone Sharpe ratio | Excess return over a stated risk-free series per unit of volatility |

CAGR above a benchmark is not risk-adjusted alpha. A standalone Sharpe analysis MUST identify its risk-free series and return convention.

**METH-01.4 No silent defaults.** Benchmark, costs, dates, currency, and price convention MUST be explicit study inputs or visibly resolved settings. Trial Folio MUST NOT assume SPY, zero costs, or "today" as an end date. Where two runs differ on any of these, the comparison MUST show it (INV-08).

**METH-01.5 Unset owner parameters.** The owner has not set drawdown limits, capital, slippage, a minimum acceptable return, or a significance threshold. Each is a study input or a documented proposed default, never an invented product-wide decision.

## METH-02 Separate development, selection, and confirmation

**METH-02.1 Chronological boundaries.** Partitions MUST be chronological and suited to the strategy's data and return horizon. Development includes every choice informed by returns: factor direction and choice, weights, universe changes, preprocessing, and thresholds. Validation data used to choose a winner is selection data, not confirmation data.

**METH-02.2 Holdout integrity.** A final holdout is meaningful only if it was not previously inspected or used in development. The study MUST record known prior exposure, including manual work outside Trial Folio. When the history has already been inspected, the evaluation MUST be labeled retrospective, and genuinely unseen evidence comes only from new forward observations.

**METH-02.3 Justified splits.** The split MUST be justified by the available observations, the return horizon, prior exposure, and power. A 10-year development, 6-year validation, and 4-year holdout division of 20 years of data is an illustration, not a rule. Access to 20 years of provider history does not establish 20 years of usable or previously unseen evidence.

**METH-02.4 Walk-forward evaluation.** A walk-forward design MUST state what is refitted, when, and on exactly which past data. All outcome-driven selection MUST be nested inside each training period. Training labels whose outcome windows cross an evaluation boundary MUST be excluded. Any purge or gap MUST be derived from the label and holding horizons, not chosen as a fixed decorative number.

**METH-02.5 Freeze before exposure.** The protocol and candidate definitions MUST be archived before protected results are released. Changing a candidate after holdout inspection creates further research; the same period MUST NOT be reused as a fresh holdout.

**METH-02.6 Limits of a local tool.** Access controls and data scoping can reduce accidental leakage, but a local tool cannot prove the owner never inspected the data elsewhere. Assessments MUST state this limitation. Status: Unavailable by nature.

**METH-02.7 Discovery tools stay in development data.** FactorMiner and other discovery aids MAY propose candidates only within permitted development data. Verified observation (documentation and source, per the [spec-authoring guide](spec-authoring-guide.md#8-portfolio123-reuse-and-integration-findings)): FactorMiner selects factor direction automatically, filters extreme returns, may truncate after dates where a factor is completely missing, uses next-close prices, computes alpha and beta without a risk-free adjustment, and uses an ordinary one-sample t-test for information coefficients. A study using it MUST preserve its exclusions, reconcile its portfolio assumptions with the study's, and compute final inference with the study's own method (METH-04), never with FactorMiner's test.

## METH-03 Research history and multiple testing

Searching more strategies requires stronger evidence, and correlations among the tests matter. Harvey and Liu's "Backtesting" addresses multiple testing and data-mining adjustments; a universal fixed t-statistic threshold is not their procedure. [Harvey and Liu, Backtesting](https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF)

**METH-03.1 Record outcome-informed choices.** Every choice informed by outcomes that contributes to selection MUST be recorded: factors, signs, weights, rules, universes, dates, metrics, and rejected alternatives. Searching universes matters as much as searching factors.

**METH-03.2 Keep the counts separate.** These are different quantities and MUST be recorded separately:

| Quantity | Example | Is it a hypothesis? |
|---|---|---|
| Provider operations and retries | Three requests to complete one backtest | No |
| Distinct candidate specifications | Two ranking systems with different weights | Candidates, not automatically hypotheses |
| Statistical hypotheses and their declared family | "Candidate A beats the benchmark after costs" | Yes, within the declared family |
| Predefined diagnostic perturbations | Holdings of 20, 30, 50 run to check sensitivity | No, unless the outcome influences selection |
| Adaptive changes made after seeing outcomes | Dropping a factor because it hurt the backtest | Yes, it is part of the search |

A provider request count is not a multiple-testing family size (INV-09).

**METH-03.3 Selection is history.** A predefined diagnostic does not mechanically add one independent hypothesis per request. If its outcome influences which system is selected, that selection MUST be represented in the history. Keeping only finalists, or dropping correlated factors, does not erase the search.

**METH-03.4 Unknown earlier search.** Searches made before Trial Folio recorded them cannot be repaired by starting the count at installation. The study MUST record a search-history status (complete, partial, or unknown), the statuses an experiment's prior-research declaration uses from 0.3.0 ([experiment configuration](contracts.md#prior-research)). The owner chose `partial` on 2026-10-07. Where defensible, it SHOULD report sensitivity to plausible prior-search assumptions, and it MUST limit its claim accordingly.

**METH-03.5 History before correction.** Research history is recorded from 0.3.0. No multiple-testing correction is implemented until that history exists and its completeness is visible (INV-09).

## METH-04 Inference before any statistical badge

**METH-04.1 Proposed initial design.** Proposed default, conservative:

1. Freeze the candidate family before an evaluation period is exposed.
2. Use aligned portfolio-level return observations with a declared estimand and null hypothesis.
3. Predeclare a dependence-aware method for individual uncertainty or p-values, either a correctly specified HAC estimator or a time-block bootstrap. The choice requires a methods ADR.
4. For that fixed family, consider Holm adjustment of valid individual p-values as the initial family-wise procedure.
5. Apply the frozen decision procedure once to the final untouched holdout.

This is a proposal, not an implemented or validated algorithm. Counting adaptive searches and applying a correction does not repair all selection bias or repeated peeking. A sequential or adaptive protocol needs its own justification.

**METH-04.2 Specify before ready.** Before a statistical increment is marked Ready, its specification MUST define and test: the null; a one- or two-sided alternative; the observation frequency; the lag or block-length rule; the missingness and alignment policy; the number of resamples; the random seed; the family definition; minimum sample requirements; and the decision policy. Each method MUST be justified by primary sources and numerical verification.

**METH-04.3 Joint dependence.** When comparing strategies, resampling MUST preserve their cross-strategy dependence. Stocks, trades, overlapping rolling windows, stable-identifier universe slices, and repeated backtests are not independent replications of the same portfolio hypothesis.

**METH-04.4 Significance policy.** The significance policy is a study input, persisted with the study:

| Input | Meaning |
|---|---|
| Error rate | The family-wise (or other declared) error rate. Proposed default: family-wise 5%, not a product-wide truth |
| Method and version | The procedure used for individual p-values and for the adjustment, with its implementation version |
| Hypothesis family | The frozen set of hypotheses the error rate covers |
| Prior-search assumptions | The search-history status and any assumption about searches not recorded (METH-03.4) |

The assessment MUST persist the calculated adjusted p-values and, where the chosen procedure supports it, the applicable critical value. It MUST NOT expose an unexplained "required t" number, or equate a raw experiment count with an estimated number of independent tests.

**METH-04.5 Report estimates, not badges.** Reports MUST give effect estimates, uncertainty, sample size, sensitivity, and economic significance. Where adjustment applies, adjusted and unadjusted values are both shown and clearly labeled. A p-value is not the probability that a strategy will outperform in the future. An inconclusive result is a valid outcome.

**METH-04.6 Descriptive statistics are labeled.** A plain t-statistic of mean excess return on non-overlapping periods MAY be reported as a descriptive statistic. It MUST be labeled descriptive, and it MUST NOT be used as a confirmatory test; it ignores serial dependence and the search that produced the candidate.

**METH-04.7 Advanced procedures.** Deferred: Romano–Wolf stepdown, the deflated Sharpe ratio, and probability-of-backtest-overfitting diagnostics may be researched later. Each needs its assumptions checked for the study design before use. Trial Folio MUST NOT assemble impressive-looking scores without that check.

## METH-05 Data integrity appropriate to the claim

The integrity required rises with the claim. A comparison of saved summaries needs provenance and coverage; a confirmatory claim needs all of the following.

**METH-05.1 Point-in-time data.** Account for availability dates, reporting delays, and preliminary versus complete financial data.

**METH-05.2 Universe history.** Account for historical universe membership, survivorship, delistings, ticker changes, and stable identifiers.

**METH-05.3 Prices and corporate actions.** Account for dividends, splits, currencies, and adjusted versus unadjusted prices.

**METH-05.4 Coverage.** Record actual coverage, missingness, duplicate records, calendar alignment, and changing sample composition. Trial Folio MUST NOT silently shorten an evaluation window to obtain attractive coverage or performance, and MUST NOT replace unavailable values with zero or a favorable default (INV-03).

**METH-05.5 Outliers and exclusions.** Outlier handling and exclusions MUST be declared, and the original observations retained (INV-04).

**METH-05.6 Signal timing.** Record the time of signal formation and the first permissible execution time. Returns are credited only from the permissible execution time.

**METH-05.7 Revisions and reruns.** Upstream data and engines change, so a provider rerun MAY differ from an earlier run. A rerun is a new attempt, never a silent replacement. Offline reproducibility means reproducing a declared analysis from archived inputs with identified code and settings (INV-05, INV-06), not identical future provider responses.

**METH-05.8 Labels are not inputs.** Future-return columns are labels, never signal inputs. Every label's outcome window MUST end within the partition it is used in.

**METH-05.9 Cross-provider checks.** Tiingo MAY eventually support price checks, benchmark series, and forward tracking where its data is suitable. It does not reconstruct Portfolio123's historical fundamentals or universes. Identifier, calendar, dividend, and price-adjustment conventions MUST be reconciled before providers are compared.

**METH-05.10 No reconstruction from summaries.** Summary statistics alone do not justify reconstructing returns, confidence intervals, or drawdown histories. Values MUST NOT be displayed with more precision than their source provides. Sections that need data the source lacks are marked unavailable, not approximated.

## METH-06 Robustness and economic usefulness

**METH-06.1 Predefined perturbations.** Robustness perturbations MUST be predefined and bounded, and archived before their results are seen. Candidates include neighboring factor weights, removal of one factor, liquidity thresholds, holdings count, rebalance schedule, universe boundaries, signal delays, execution assumptions, and higher costs. The default variant set is [P-13](spec.md#proposed-defaults), and universes follow [D-19](spec.md#decisions). A variant used to choose a candidate is part of the search, not independent robustness evidence for that candidate (METH-03.3).

**METH-06.2 Universes and benchmarks.** A universe change alters the opportunity set and may require a different benchmark. A legitimate strategy need not work in every universe. The assessment asks whether sensitivity is consistent with the economic hypothesis and the intended trading domain.

**METH-06.3 Concentration.** Where data permits, inspect how contributions concentrate by time, sector, security, and extreme events.

**METH-06.4 Stable regions.** Prefer a stable region of reasonable choices over an isolated peak. "Stability" MUST NOT become an unregistered optimization score.

**METH-06.5 Costs and capacity.** Evaluate commission, spread and slippage, turnover, financing and borrow where applicable, participation in volume, position size, concentration, cash behavior, and plausible capital capacity. Taxes are a separately declared scope choice; when not modeled, they are stated as a limitation.

**METH-06.6 Repricing is not rerunning.** Repricing a fixed trade list under different costs is a useful sensitivity calculation, but costs can change cash, sizing, and later trades. Results MUST label which of the two was done.

**METH-06.7 Conditional feasibility.** Historical trading feasibility remains conditional on its assumptions. Forward signal timestamps, paper tracking, and eventually observed fills add evidence. Paper execution alone does not prove achievable fills.

**METH-06.8 Signals, screens, and simulations.** Rank snapshots, bucket behavior, factor-removal tests, and information coefficients diagnose signals. Screens provide simple portfolio baselines and sensitivity experiments. Simulations represent holdings, trading rules, turnover, cash, and execution. A strong factor diagnostic is not evidence that a portfolio is tradable; the actual proposed portfolio rules MUST be evaluated before any deployment assessment.

## METH-07 Multidimensional assessment and permitted conclusions

**METH-07.1 Separate dimensions.** Report these separately: data quality, historical economic performance, statistical evidence, robustness, and implementation feasibility.

**METH-07.2 Predeclared overall rule.** Any overall decision MUST be a transparent rule over those dimensions, declared before results.

**METH-07.3 Permitted outcomes.** Candidate outcomes are rejected, inconclusive, and meeting predefined criteria for additional forward research. A dimension whose method is not Validated is reported as "not assessed". Releases 0.1.0 to 0.3.0 MUST report statistical validation and trading readiness as "not assessed" (INV-10).

**METH-07.4 Process success is not strategy success.** A completed run, review, or experiment says nothing about whether the strategy is useful. Reports MUST keep execution status separate from any research outcome, and a green completion status MUST NOT resemble a "safe to trade" endorsement.

**METH-07.5 Claim limits.** A report MUST NOT present a result as a promise, prediction, or representation of gains a user could realize. Passing a backtest is not an assurance of future superiority. Any later terminology about deployment review requires legal review of the actual functionality and presentation, and MUST NOT become a recommendation that an individual invest. Notices are defined in [disclaimers.md](disclaimers.md).

**METH-07.6 Label what is actual.** When a report includes forward observations, it MUST label which portions are actual, simulated, or hypothetical.

**METH-07.7 Deterministic numbers.** Deterministic code produces every number in an assessment and every conclusion the policy allows. An optional LLM-written narrative MUST NOT create a metric or claim absent from the saved assessment.

## METH-08 Optional LLM research agents

Runtime LLM use is optional, disabled by default, and deferred to the Optional discovery increment. The backends and their data-disclosure rules are defined in [spec.md](spec.md); this section governs the research process.

**METH-08.1 Code before agents.** Conditional execution does not require an agent. Schema checks, coverage gates, fixed experiment expansion, retry rules, and configured stopping conditions are ordinary code. Routine supported perturbations are generated and run by configuration, without a human or a model editing each factor.

**METH-08.2 Bounded proposals.** A research agent MAY propose economic hypotheses, explain diagnostics, or suggest additional development experiments. It MUST work with structured output validated by a Pydantic model, a finite proposal and API budget, a declared data-access boundary, and a complete proposal and decision log.

**METH-08.3 Prohibited actions.** A research agent MUST NOT inspect protected outcomes, change acceptance criteria after results, silently discard failures, or authorize trading.

**METH-08.4 Complete record.** Record prompts, model and provider identifiers, relevant settings, tool actions, outputs, and each proposal's acceptance or rejection. Seeds do not make hosted model output repeatable, so the actual first output is preserved unedited. A correction is a new, dated record that names what changed and how it was checked; it never overwrites the original.

**METH-08.5 Proposals are search.** Every proposal a study evaluates is a candidate in its research history (METH-03). A rejected proposal remains in the history.

**METH-08.6 Human decisions.** A human decides unresolved economic intent, material protocol changes, uncertain external actions, and deployment.

## METH-09 Reproducing published research

The driving use case for Trial Folio is reproducing published factor research in Portfolio123: taking a paper's factors, building them as ranking systems and screens, and testing whether the paper's findings hold with an individual investor's tools. Exact reproduction is rarely possible without the original data and tools, so the method records how the reproduction differs rather than hiding it.

**METH-09.1 Preregistration.** A reproduction study MUST record the paper, the claim being tested, the reproduction criteria, the planned deviations, and the fixed analysis-set version (METH-09.10) before running any test. The protocol is committed before the first test; its timestamp is the evidence that the criteria came first. Later changes are dated amendments appended to it, never edits.

**METH-09.2 Every study is reported.** Every study and every case is kept and reported on the same terms whether or not it reproduces the paper (INV-01, INV-07). A study is never abandoned or hidden because of its result; if it stops, the reason is recorded.

**METH-09.3 Deviation record.** Each study MUST compare its settings with the paper's for universe, microcap treatment, breakpoints, long-only or long-short construction, weighting, rebalance frequency, data vendor, point-in-time handling, delisting returns, and sample period. An unknown paper setting is recorded as unknown, not assumed.

**METH-09.4 Variant set.** The protocol lists its variants before testing. Proposed default set:

| Variant | Purpose |
|---|---|
| The paper's construction at the paper's rebalance frequency, full universe | The closest available reproduction |
| The same, excluding microcaps, with the cutoff stated | Whether the result depends on the smallest, least tradable stocks |
| Practitioner variant: a weekly screen used as a buy list, selection within it by rank, and a rank-drop sell rule | How a practitioner would trade the idea; labeled separately, with both the screen's turnover and the portfolio's turnover |
| The paper's construction on each stable-identifier universe slice (METH-09.5) | Whether the result depends on a few stocks |

Each variant runs only where the backend's capability has been verified.

**METH-09.5 Universe slices.** The universe is split into four slices by a stable identifier, for example `Mod(StockID,4)` = 0 to 3, so each slice keeps the same stocks at every rebalance. The slices share dates: they show whether a result depends on a few stocks, not whether it depends on the period. They MUST NOT be counted as independent confirmations (METH-04.3). The protocol states how slice results enter the verdict. Whether `StockID` is stable across the test period must be verified before the slice rule is relied on.

**METH-09.6 Gross and net.** Results are reported before and after the protocol's declared trading-cost and slippage assumptions (METH-06.5).

**METH-09.7 Rolling returns.** For each variant and the benchmark, over the protocol's holding periods (proposed default: 7, 30, 90, 180, and 365 calendar days), report the median, mean, 10th and 90th percentile, and worst return; the share of windows in which the strategy beat the benchmark; the number of windows; and the number of non-overlapping windows. Overlapping windows are not independent observations, and every summary of them MUST say so. Rolling returns require dated return series and are Unavailable where a source has only summary statistics (METH-05.10). For a screen backtest, they are calculated from the run's daily values ([`chart`](contracts.md#p123api-screen-backtest-version-1)): the value at the end of a window divided by the value at its start, minus 1. So one run gives every window length. A rolling 4-week return of a weekly-rebalanced run is still the weekly portfolio's return. It is not a substitute for a run rebalanced every 4 weeks, whose holdings, turnover, and costs differ.

**METH-09.8 Quantiles.** Where a rank performance test was run, report return by bucket, the top-minus-bottom spread, and the rank correlation between bucket and return as a check that returns rise steadily across buckets. The bucket semantics of Portfolio123's rank-performance operation MUST be verified before any quantile claim.

**METH-09.9 Period splits.** Where the data covers them, report the full-period metrics for three periods: before the paper's sample ended, between the end of the sample and publication, and after publication. State the share of the test period that falls after the paper's sample and after its publication. The paper's sample period has already been used by its authors, so results there are retrospective by construction (METH-02.2). The post-publication period is out of sample for the paper but not necessarily unseen by the researcher; record any prior exposure.

**METH-09.10 Fixed analysis set.** The metrics, splits, and charts are chosen before results and applied identically to every study, because choosing them after seeing results is data snooping. The analysis set is versioned. Changing it creates a new version, and each study records which version it used and, if a version changed mid-study, why.

**METH-09.11 Descriptive statistics only, until METH-04.** The fixed analysis set MAY include a t-statistic of mean excess return on non-overlapping periods, labeled descriptive (METH-04.6). A reproduction verdict of the form "reproduced" or "did not reproduce" is a comparison with the paper's claim under the preregistered criteria; it is not a statistical acceptance decision until METH-04 is Validated.

**METH-09.12 Model-drafted setups.** When a model drafts ranking systems or screens from a paper, its first output is preserved unedited (METH-08.4), every formula or function that failed or was invented is recorded with its correction, and the syntax is verified against Portfolio123's documentation. A model never supplies a figure that appears in an assessment (METH-07.7).

## Analysis set 1.0.0

Proposed for release [0.5.0](releases/0.5.0-return-analytics.md) (R05-T02). Status: Proposed. This is the fixed analysis set METH-09.10 requires: the descriptive analyses Trial Folio calculates from each result's dated series, and, from R05-T03, the [charts](#charts) it draws of them, chosen before any result is seen, and applied identically to every case of every run and experiment, saved ones included. Its version is recorded with every value. A change to any calculation, window, minimum, or rule below makes a new version, and a Trial Folio version that changes none of them keeps 1.0.0. [contracts.md](contracts.md) owns its two tables: the series it reads, [`series.csv`](contracts.md#seriescsv), and the values it gives, [`analysis.csv`](contracts.md#analysiscsv). It makes no inference (METH-04): its tracking error, information ratio, and t-value are descriptive (METH-04.6, METH-09.11).

### Inputs

- **Daily levels.** For the strategy and for the benchmark, the levels L₀ to L_N of 100 invested, on the `chart` dates t₀ to t_N: every weekday from the requested start date to the end date, as `series.csv`'s daily rows hold them. L₀ is 100.
- **Period returns.** For each rebalance period i, from 1 to n, the strategy's `Ret%`, the benchmark's `Bench%`, and the excess, `Excess%`, in percent, each with its `Tran Dt` and `End Dt`, as `series.csv`'s period rows hold them. The periods don't overlap, since each one's `End Dt` is the next one's `Tran Dt`, and the first and last can be shorter than the rebalance frequency ([the verified layout](contracts.md#p123api-screen-backtest-version-1)). The excess is Portfolio123's `Excess%`, never `Ret%` minus `Bench%` calculated again ([D-47](spec.md#decisions)).
- **A level's date.** Portfolio123 doesn't document which close a level stands for, and at least two readings fit what R05-T01 found ([the verified layout](contracts.md#p123api-screen-backtest-version-1)). So each level keeps its `chart` date, and every value calculated from it is dated by `chart` dates: no date is moved.
- **Nothing else.** No risk-free series, price, or holding: a measure that needs one, such as a Sharpe ratio Trial Folio would calculate, isn't in the set (METH-01.3).

### Arithmetic and digits

- **Decimals.** Every calculation uses decimal arithmetic, never binary floating point: Python's `decimal`, with 50 significant digits and rounding half to even, as R05-T01's checks did. A square root and a power with a fractional exponent are `decimal`'s own, at that precision, far beyond the digits any value keeps. So the set adds no runtime dependency.
- **One rounding.** Each value is rounded once, at the end, half to even: a value in percent, in percentage points, or a ratio to the request's `precision`, the decimals its inputs have, which is 4 in every configuration Trial Folio accepts; a count or a number of days is whole; a date is a date. A value that rounds to zero is written without a sign, as a difference is: −0.00004, at 4 decimals, is `0.0000`, never `-0.0000`, though `decimal` keeps the sign. A `…_difference` is the difference of the two values as rounded, so it's exact at their digits. No value has more digits than its inputs (METH-05.10).
- **Rounded inputs.** Each value is calculated from the response's rounded levels or returns, not from Portfolio123's unrounded series, so it can differ in its last digit from one Portfolio123 calculated before rounding, as R05-T01 found of Portfolio123's own metrics. [Reconciliation](#reconciliation-with-portfolio123s-metrics) allows for that.

### Segments

Every analysis below is calculated over the `full` segment: all of a result's levels, and all its periods. The period-return and daily-level analyses are also calculated over each split segment, when the configuration declares [period splits](contracts.md#period-splits) (METH-09.9). The rolling returns aren't: a window needs the whole series.

- **The split segments.** Declared dates d₁ to d_k, in increasing order, divide the result's coverage, from C₀ to C₁, into k + 1 segments: `split-0`, from C₀ to d₁, or to C₁ when d₁ is after it; `split-n`, for n from 1 to k − 1, from dₙ to dₙ₊₁; and `split-k`, from d_k, or from C₀ when d_k is before it, to C₁. Those are each segment's first and last dates.
- **The coverage.** C₀ and C₁ are the result's `coverage_start` and `coverage_end`, from its period rows. When either is unavailable, as for a result without period rows, they're its first and last `chart` dates, t₀ and t_N, so such a result keeps its split segments' daily-level analyses, as it keeps its other analyses of its daily levels ([R05-AC02](releases/0.5.0-return-analytics.md#acceptance-criteria)). Its split segments' periods aren't known, though: the coverage is unavailable only when the result has no period, as [`series.csv`](contracts.md#seriescsv) gives it, when a period's `Tran Dt` or `End Dt` can't be read, or when the earliest `Tran Dt` is after the latest `End Dt` ([coverage dates](contracts.md#p123api-screen-backtest-version-1)). So each value an available split segment calculates from its periods, `period_count` and `spanning_period_count` included, is unavailable, with `input_unavailable`, rather than calculated without a period it may hold (METH-05.4). Its `coverage_share`, from dates alone, is calculated as below. When the daily series is unavailable too, every split segment is unavailable, with `input_unavailable`.
- **Outside the coverage.** A declared date before C₀, or after C₁, is outside the coverage, and the report flags it ([R05-AC08](releases/0.5.0-return-analytics.md#acceptance-criteria)). A segment the coverage doesn't reach is unavailable, with `outside_coverage`: `split-0` when d₁ is before C₀, and `split-k` when d_k is after C₁. A segment between two declared dates is unavailable unless the coverage reaches both, C₀ ≤ dₙ and dₙ₊₁ ≤ C₁, so it's never shortened to the part the coverage reaches (METH-05.4). `split-0` and `split-k` have one declared date each, and hold what the coverage holds on their side of it: "before the paper's sample ended" is every covered date before it.
- **A date on the coverage's edge,** d₁ on C₀, or d_k on C₁, is within the coverage, and isn't flagged. The segment on its outer side, `split-0` or `split-k`, is that one date, with one level and no period, so each of its values that needs two levels or a period is unavailable as in any segment too short for it, with `too_few_observations`, or, for a value from the periods when they aren't known, with `input_unavailable`, as above. Its `coverage_share` is 0, unless C₀ and C₁ are that same date, as below.
- **A segment's levels** are those from the latest `chart` date on or before its first date to the latest on or before its last date, both included. So the level that ends one segment begins the next, and the segments' total returns compound to the `full` one's. A segment whose dates the `chart` doesn't reach is unavailable with `outside_coverage`.
- **A segment's periods** are those wholly within it: `split-0`'s end on or before d₁; `split-n`'s start on or after dₙ and end on or before dₙ₊₁; and `split-k`'s start on or after d_k. A period that starts before a declared date and ends after it is in neither segment beside it, so no return is credited to a side it's only partly on, and each of those segments counts it in `spanning_period_count`.
- **`coverage_share`,** for each split segment: the calendar days from its first date to its last, divided by those from C₀ to C₁, in percent, the share of the test period METH-09.9 asks for. When C₀ and C₁ are the same date, as for a result without period rows whose `chart` has one date, there are no days to divide by, so each available split segment's `coverage_share` is unavailable, with `not_applicable`.
- **A summary's dates.** A value over a whole segment gives its inputs' first and last dates, never a declared date they don't have, so it keeps the dates of the levels or periods it's calculated from ([D-48](spec.md#decisions)): a value from the levels, the dates of the segment's first and last levels; one from the periods, the earliest `Tran Dt` and the latest `End Dt` of the segment's periods when they're known, and none when it has none or they aren't. For the `full` segment, those are the first and last `chart` dates, and C₀ and C₁. When the coverage is unavailable, though, its periods' first and last dates aren't known, and C₀ and C₁ are the `chart`'s, so the `full` segment's values from its periods give none, though some, such as `period_count`, can stay available. Only `coverage_share` and `spanning_period_count`, which describe the segment rather than a series, give the segment's own first and last dates.

### Period-return analyses

Over a segment's periods. A value of a subject needs every one of the segment's periods to have that subject's return: when one is unavailable, the value is unavailable, with `input_unavailable`, and no period is left out to calculate it (METH-05.4). Its `observations` is n, the number of the segment's periods. With fewer periods than a value needs, it's unavailable with `too_few_observations`.

| Analysis | Subjects | Unit | Definition | Needs |
|---|---|---|---|---|
| `coverage_share` | None | percent | Split segments only, as above | Its segment available, and C₁ after C₀, or it's unavailable with `not_applicable` |
| `period_count` | None | count | n, the segment's periods | The period series |
| `spanning_period_count` | None | count | Split segments only: the periods that span one of its declared dates | The period series |
| `mean_period_return` | strategy, benchmark, excess | percent | The arithmetic mean, (x₁ + … + xₙ) / n | 1 period |
| `median_period_return` | strategy, benchmark, excess | percent | The middle value of the sorted returns, or the mean of the two middle values when n is even | 1 period |
| `best_period_return` | strategy, benchmark, excess | percent | The largest return, with its period's `Tran Dt` and `End Dt` as the value's dates; the earliest period on a tie | 1 period |
| `worst_period_return` | strategy, benchmark, excess | percent | The smallest, in the same way | 1 period |
| `positive_excess_share` | excess | percent | The share of periods whose excess is above 0, times 100. An excess of 0 isn't positive. | 1 period |
| `tracking_error` | excess | percent | The sample standard deviation of the excess, √(Σ(eᵢ − ē)² / (n − 1)), per rebalance period, not annualized | 2 periods |
| `information_ratio` | excess | ratio | The mean excess per unit of tracking error, ē / s, per rebalance period (METH-01.3) | 2 periods, and a tracking error above 0, or it's unavailable with `not_applicable` |
| `excess_t_value` | excess | ratio | The t-value of the mean excess per period, ē / (s / √n), which is the information ratio times √n. Descriptive, given with n, and never a test (METH-04.6). The rebalance periods don't overlap. | As `information_ratio` |

### Daily-level analyses

Over a segment's levels, L_a to L_b, on the dates t_a to t_b. Its `observations` is the number of levels. When the daily series is unavailable, each value is unavailable with `input_unavailable`, and with fewer levels than a value needs, with `too_few_observations`.

| Analysis | Subjects | Unit | Definition | Needs |
|---|---|---|---|---|
| `total_return` | strategy, benchmark | percent | (L_b / L_a − 1) × 100. Over the `full` segment, L_a is 100, so it's L_b − 100, the layout's definition of Portfolio123's `total_return`. | 2 levels |
| `total_return_difference` | excess | pp | The strategy's `total_return` minus the benchmark's | Both available |
| `annualized_return` | strategy, benchmark | percent | ((L_b / L_a)^(365.25 / D) − 1) × 100, with D the calendar days from t_a to t_b: the compound annual growth rate, with years of 365.25 days, as the layout defines Portfolio123's | 2 levels, and D of at least 365, or it's unavailable with `too_short`: a return over less than a year isn't stated as an annual rate it never held |
| `annualized_return_difference` | excess | pp | The strategy's `annualized_return` minus the benchmark's. It isn't risk-adjusted alpha (METH-01.3). | Both available |
| `max_drawdown` | strategy, benchmark | percent | The largest decline from a running peak, as a negative number: the smallest of (L_j / M_j − 1) × 100, where M_j is the highest level from L_a to L_j; 0 when the level never falls below its running peak. Its dates are the peak, the first date the level reached the peak it fell from, and the trough, the first date of the largest decline; none when it's 0. | 2 levels |
| `max_drawdown_recovery` | strategy, benchmark | date | The first date after the trough whose level is at least the peak's | A `max_drawdown` below 0, or it's unavailable with `not_applicable`; a level that never returns to the peak within the segment is unavailable with `not_recovered` |
| `longest_drawdown_days` | strategy, benchmark | days | The longest time below a peak. A time below a peak is a run of dates whose levels are below their running peak, M. It starts on the date before the run, whose level is M, so it never counts an earlier time below the same peak, which ended when the level returned to it; and it ends on the first date after the run, whose level is at least M, or, when the run reaches the segment's last date, on that date, flagged `not_recovered`, since it lasted at least that long. Its value is the calendar days from its start to its end, and those are its dates; the earliest on a tie; 0, with no dates, when the level is never below its running peak. Levels of 100, 90, 100, 90, and 100 on five weekdays in a row have two times below a peak, of 2 days each. | 2 levels |

### Rolling returns

METH-09.7's, over the `full` segment's levels, for each window length w of 7, 30, 90, 180, and 365 calendar days:

- **Windows.** A window ends at each `chart` date t_j, and starts at the latest `chart` date tᵢ on or before t_j − w days. No window ends less than w days after t₀. So no window is shorter than its length, and in a `chart` of every weekday, none is more than 2 days longer: R05-T01 found at most 2 in every saved `chart` ([its run record](../reference/return-series/README.md#rolling-windows)). A `chart` with a gap isn't read ([`series.csv`](contracts.md#seriescsv)), so no window crosses one. A window's return is (L_j / Lᵢ − 1) × 100.
- **Their summaries,** for the strategy and the benchmark: `rolling_mean`, the arithmetic mean; `rolling_median`, as `median_period_return`; `rolling_worst`, the smallest; and `rolling_p10` and `rolling_p90`, the 10th and 90th percentiles, by linear interpolation between the sorted returns x₍₀₎ to x₍ₘ₋₁₎: with h = (m − 1)p, the percentile is x₍h₎ when h is a whole number, and otherwise x₍⌊h⌋₎ + (h − ⌊h⌋)(x₍⌊h⌋₊₁₎ − x₍⌊h⌋₎), so one window's percentiles are its return. That's Hyndman and Fan's definition 7, which `numpy.percentile`'s default and Python's `statistics.quantiles` with `method="inclusive"` also compute, though Python 3.12's `quantiles` raises an error for a single window, where 3.14's gives its return. Each summary needs 1 window, or it's unavailable with `too_few_observations`, and its `observations` is m, the number of windows.
- **`rolling_share_beating`,** of the excess: the share of windows in which the strategy's return is above the benchmark's over the same window, times 100, compared before rounding. A tie isn't beating.
- **The counts,** which every summary gives with it: `rolling_window_count`, m; and `rolling_non_overlapping_count`, the most windows no two of which overlap. It's counted from the earliest: the window that ends first, then each window, in the order of their ends, that starts on or after the end of the last one counted. A window that starts on the date another ends doesn't overlap it.
- **Not independent.** Overlapping windows aren't independent observations (METH-04.3), so each summary is flagged `overlapping_windows`, and given with both counts. A rolling 4-week return of a weekly run is still the weekly portfolio's (METH-09.7).

### Charts

METH-09.10's charts, which belong to the set as its values do, so a change to what they draw makes a new version (R05-T03). For each result with usable daily levels, over the `full` segment's levels; [contracts.md](contracts.md#reports) gives their structure:

- **The equity chart:** each level L_j of the strategy and of the benchmark, against its `chart` date t_j, on a logarithmic scale, so that equal returns rise equal heights at any level.
- **The drawdown chart:** at each date t_j, the decline below the running peak, (L_j / M_j − 1) × 100, with M_j the highest level from L₀ to L_j, as `max_drawdown` defines it, so its lowest point is the `full` segment's `max_drawdown`.
- **Every level, and nothing else.** Each line has a point for each `chart` date, joined by straight lines, with none smoothed, interpolated, or left out, so a chart shows what `series.csv` holds, and no more.
- **In an experiment,** each case's charts also draw the baseline's strategy, over the same dates, which an experiment's cases share; and every case's charts have the same axes, so a line's height means the same in each.
- **Split dates,** where declared and within the chart's dates, are marked on each chart, so its segments can be seen; the segments' values are in `analysis.csv`.
- **Unavailable** without usable daily levels: a result whose daily series is unavailable, with its reason, has no chart, and nothing is drawn from its period returns or its summary statistics instead (METH-05.10).

### Reconciliation with Portfolio123's metrics

Over the `full` segment, `total_return`, `annualized_return`, and `max_drawdown`, for the strategy and the benchmark, calculate again the metric `metrics.csv` gives with the same `metric_id` and `subject`. The report shows both, and neither replaces the other (INV-08). The recalculated value *agrees* when Portfolio123's value is within the range that the rounding of the recalculated value's inputs allows, widened by the rounding of the reported value, and otherwise *differs*, which the report flags ([D-48](spec.md#decisions)):

- **Rounding.** Each level is read as rounded to half a unit of its last digit: the request's `precision`, since saving drops only trailing zeros, or its own decimals, where it has more ([numbers and precision](contracts.md#p123api-screen-backtest-version-1)). So is the reported value, R. With h for a value's half unit, Portfolio123's value agrees when low − h_R ≤ R ≤ high + h_R.
- **`total_return`:** from low, L_N − h_N − 100, to high, L_N + h_N − 100. L₀ is 100, as the layout gives it.
- **`annualized_return`:** those two ends of L_N, each annualized, ((L_N ∓ h_N) / 100)^(365.25 / D) − 1, times 100.
- **`max_drawdown`:** a range that holds the exact one. Its low is the smallest of ((L_j − h_j) / max(Lᵢ + hᵢ, for i ≤ j) − 1) × 100, every trough as low as its rounding allows against every earlier level as high. Its high is the smaller of 0 and ((L_t + h_t) / (L_p − h_p) − 1) × 100, the recalculated drawdown's own trough, t, and peak, p, the other way.
- **Not compared.** When either value is unavailable, such as an `annualized_return` over less than a year, the pair is `not_compared`.

These are the ranges R05-T01's script computes. By them, every reconciled metric of the owner's 74 distinct saved responses agrees, though 26 maximum drawdowns and 1 annualized return of the strategy differ by more than half a unit of the reported value's last digit ([its run record](../reference/return-series/README.md#the-checks)).

### What the values may be read as

- **Descriptive, of one backtest.** Each value describes one result's returns over its coverage, as Portfolio123 calculated them. None is an inference, a prediction, or a ranking, and statistical validation and trading readiness stay "Not assessed" (METH-07.3). Each chart is descriptive too, and so is each difference from the baseline: a case's value minus the baseline's, never a test.
- **Per rebalance period.** The period-return values are per rebalance period, so a weekly result's and a 4-weekly result's don't compare: the comparison with the baseline doesn't difference them ([comparing a case with the baseline](contracts.md#comparing-a-case-with-the-baseline)).
- **A split's segment** over the paper's sample is retrospective by construction, and the one after publication isn't necessarily unseen by the researcher (METH-09.9).
- **Rounded inputs.** A recalculated value can differ from Portfolio123's in its last digit, within the rounding, as above.

### A hand-checkable example

A response requested from 2024-01-01 to 2024-01-12, rebalanced every week, at precision 4. Its `chart` has the 10 weekdays, and its two periods are 2024-01-01 to 2024-01-08, with a `Ret%` of 0, a `Bench%` of 1, and an `Excess%` of −1, and 2024-01-08 to 2024-01-12, with 10, 0, and 10:

| Date | 01-01 | 01-02 | 01-03 | 01-04 | 01-05 | 01-08 | 01-09 | 01-10 | 01-11 | 01-12 |
|---|---|---|---|---|---|---|---|---|---|---|
| Strategy | 100 | 102 | 101 | 104 | 99 | 100 | 103 | 105 | 102 | 110 |
| Benchmark | 100 | 101 | 101 | 102 | 100 | 101 | 102 | 103 | 102 | 101 |

The `full` segment gives:

| Analysis | Strategy | Benchmark | Excess |
|---|---|---|---|
| `period_count` | 2 | | |
| `mean_period_return`, `median_period_return` | 5.0000 | 0.5000 | 4.5000 |
| `best_period_return` | 10.0000, the second period | 1.0000, the first | 10.0000, the second |
| `worst_period_return` | 0.0000, the first | 0.0000, the second | −1.0000, the first |
| `positive_excess_share` | | | 50.0000 |
| `tracking_error` | | | 7.7782: √((5.5² + 5.5²) / 1) = √60.5 |
| `information_ratio` | | | 0.5785: 4.5 / √60.5 |
| `excess_t_value` | | | 0.8182: 4.5 / (√60.5 / √2) = 4.5 / 5.5, with 2 periods |
| `total_return` | 10.0000 | 1.0000 | 9.0000 |
| `annualized_return` | Unavailable, `too_short`: 11 days | Unavailable, `too_short` | Unavailable, `input_unavailable` |
| `max_drawdown` | −4.8077: 99 / 104 − 1, from 01-04 to 01-05 | −1.9608: 100 / 102 − 1, from 01-04 to 01-05 | |
| `max_drawdown_recovery` | 2024-01-10, the first level of 104 or more | 2024-01-09 | |
| `longest_drawdown_days` | 6: 01-04 to 01-10 | 5: 01-04 to 01-09 | |

The 7-day windows are 5, from 01-01 to 01-08 through 01-05 to 01-12, of which 1 doesn't overlap another: each later one starts before 01-08. The strategy's returns are 0, 0.980392…, 3.960396…, −1.923077…, and 11.111111…, so its `rolling_mean` is 2.8258, `rolling_median` 0.9804, `rolling_p10` −1.1538, with h = 0.4, `rolling_p90` 8.2508, with h = 3.6, and `rolling_worst` −1.9231. The benchmark's are 1, 0.990099…, 1.980198…, 0, and 1: 0.9941, 1.0000, 0.3960, 1.5881, and 0.0000. The strategy beats the benchmark in 2 of the 5, the third and the fifth, so `rolling_share_beating` is 40.0000. No window of 30 days or more fits, so each of their summaries is unavailable, with `too_few_observations` and 0 observations, and each count is 0.

**Reconciled.** Had Portfolio123 reported the strategy's maximum drawdown as −4.8078, it would agree: the range is about −4.807786 to −4.807598, widened by 0.00005. As −4.8079, it would differ. A reported `total_return` of 10.0001 agrees with the range from 9.99995 to 10.00005, and one of 10.0002 differs.

**Split.** With one declared date, 2024-01-05, `split-0` runs from 2024-01-01 to 2024-01-05, with a `coverage_share` of 36.3636, 4 days of 11, and `split-1` from 2024-01-05 to 2024-01-12, with 63.6364. The first period spans 2024-01-05, so each segment's `spanning_period_count` is 1. `split-0` has no period, so each of its period-return values is unavailable, with `too_few_observations`. `split-1` has the second period: a mean of 10.0000, 0.0000, and 10.0000, a `positive_excess_share` of 100.0000, and a `tracking_error` unavailable, with 1 observation. Those are dated by its period, 2024-01-08 to 2024-01-12, and its values from the levels by its levels, 2024-01-05 to 2024-01-12. From the levels:

| Analysis | `split-0`, strategy | `split-0`, benchmark | `split-1`, strategy | `split-1`, benchmark |
|---|---|---|---|---|
| `total_return` | −1.0000 | 0.0000 | 11.1111: 110 / 99 − 1 | 1.0000 |
| `max_drawdown` | −4.8077, 01-04 to 01-05 | −1.9608, 01-04 to 01-05 | −2.8571, 01-10 to 01-11 | −1.9417, 01-10 to 01-12 |
| `max_drawdown_recovery` | `not_recovered` | `not_recovered` | 2024-01-12 | `not_recovered` |
| `longest_drawdown_days` | 2: 01-02 to 01-04 | 1: 01-04 to 01-05, `not_recovered` | 2: 01-10 to 01-12 | 2: 01-10 to 01-12, `not_recovered` |

The strategy's segments compound to its `full` total: 0.99 × 1.111111… = 1.1.

Declared on Sunday, 2024-01-07, instead, the split gives the same values from the levels and the periods, with the same dates, since `split-0`'s levels still end on 2024-01-05, and the first period still spans the date. Only the segments' own dates change, and with them their `coverage_share`: `split-0` runs to 2024-01-07, with a `coverage_share` of 54.5455, 6 days of 11, and `split-1` from 2024-01-07, with 45.4545.

## Verification of statistical methods

These requirements apply before any METH-04 or METH-06 method moves from Implemented to Validated.

- **Independent reference calculations.** Check each estimator against a calculation that does not share the implementation's code path: a published worked example, an established library, or a hand calculation. A test that repeats the implementation's formula is not independent verification.
- **Hand-checkable examples.** Maintain small fixtures whose expected results can be verified by hand, including window counts, non-overlapping counts, and Holm-adjusted p-values.
- **Synthetic scenarios.** Generate data under known nulls and alternatives that exercise serial and cross-strategy dependence, missingness, and selection from a searched family. Check rejection rates under the null (size) and under alternatives (power).
- **Tolerances first.** Specify calibration tolerances and simulation counts before interpreting the results, and record the seeds.
- **Proportion.** Presentation changes do not need statistical tests.

Each check traces to a METH requirement and is recorded as actual evidence in the release specification that claims it. Intended checks are not evidence.

## Open questions

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| HAC estimator or time-block bootstrap for individual uncertainty | Every p-value and interval in Statistical evaluation | Time-block bootstrap with joint resampling across strategies, because it preserves the cross-strategy dependence a family-wise procedure needs; HAC as an independent reference calculation. Decided in a methods ADR | Before the Statistical evaluation increment is marked Ready |
| What forms the hypothesis family | The size and meaning of every adjustment | All candidates frozen for one confirmation period within one study; predefined diagnostics and universe slices are not separate hypotheses unless they influence selection | Methods ADR, then each study protocol |
| Historical split | Which data can support a confirmatory claim | Chronological, justified by observations, horizon, prior exposure, and power; for reproductions, the post-publication period labeled retrospective unless it was genuinely unseen | Before evaluation data is exposed, per study |
| Treatment of unknown prior search | How strongly claims must be limited | Record the search-history status; report sensitivity to plausible prior-search counts where defensible; otherwise restrict the claim to descriptive | Each study protocol |
| Benchmark and cost inputs | Every benchmark-relative and net result | Explicit per study; no default benchmark, zero costs, or inherited "today" | Before the relevant assessment |
| Significance level | Decision threshold | Proposed family-wise 5%, stated per study; not hard-coded | Methods ADR and study protocol |
| Should reports grade statistical confidence, and against what cut-offs? | Whether readers over-trust a single run, especially after the same idea was tried on other universes or settings | Two steps. First, show a descriptive t-value of mean excess return per non-overlapping rebalance period, labeled descriptive, with the number of periods (METH-04.6). Later, grade in three tiers whose cut-offs come from a named procedure, never a fixed number: below the unadjusted 5% critical value; above it but below the critical value adjusted for the recorded number of tries, for example by Holm; and above the adjusted value, shown with that number and the history's completeness. Runs on other universes count as tries only when they're declared or linked (0.3.0's prior-research declaration). | The descriptive t-value: Descriptive return analytics. The grade: Statistical evaluation, after its methods ADR ([P-07](spec.md#proposed-defaults)) |
| Minimum sample size and minimum economically relevant effect | Whether a study can be informative at all | Stated per study with a power estimate | Study protocol, before evaluation |
| Risk-free series and return convention for Sharpe | Standalone objective results | Stated per study | Before any standalone assessment |
| Microcap cutoff and universe-slice rule | Two of the default reproduction variants | Cutoff stated per study; `Mod(StockID,4)` after verifying `StockID` stability | Before those variants run |
| Rolling-window horizons in calendar or trading days | Window counts and comparability | 7, 30, 90, 180, and 365 calendar days, fixed in the analysis-set version | First analysis-set version. [Analysis set 1.0.0](#rolling-returns) gives them as calendar days (R05-T02, 2026-11-02), which the owner confirmed the same day. |
| Taxes | Net results | Not modeled; stated as a limitation | Per study, as a declared scope choice |
