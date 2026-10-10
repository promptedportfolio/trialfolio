# Research methodology

Status: Draft design, prepared 2026-10-01. No method in this document is implemented or validated.

This document defines what Trial Folio's scientific assessments mean, the conditions under which they may be made, and the evidence each one requires. It is a research design, not a description of working software.

- [spec.md](spec.md) owns the product vocabulary (study, experiment, case, candidate, attempt, artifact, assessment, report) and the invariants INV-01 to INV-14.
- [contracts.md](contracts.md) owns the structures that record the artifacts named here. This document defines their meaning, not their fields.
- The [release specifications](releases/) own what each increment implements and how it is accepted.
- A methods ADR, written before the Statistical evaluation increment, owns the choice of inference method (see [Open questions](#open-questions)).

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
| METH-09.7 | Rolling returns | Descriptive return analytics | Dated return series | Needs dated return series; window counts checked by hand on a fixture | Unavailable in 0.1.0; Proposed later |

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

## Verification of statistical methods

These requirements apply before any METH-04 or METH-06 method moves from Implemented to Validated.

- **Independent reference calculations.** Check each estimator against a calculation that does not share the implementation's code path: a published worked example, an established library, or a hand calculation. A test that repeats the implementation's formula is not independent verification.
- **Hand-checkable examples.** Maintain small fixtures whose expected results can be verified by hand, including window counts, non-overlapping counts, and Holm-adjusted p-values.
- **Synthetic scenarios.** Generate data under known nulls and alternatives that exercise serial and cross-strategy dependence, missingness, and selection from a searched family. Check rejection rates under the null (size) and under alternatives (power).
- **Tolerances first.** Specify calibration tolerances and simulation counts before interpreting the results, and record the seeds.
- **Proportion.** Presentation changes do not need statistical tests.

Each check traces to a METH requirement and is recorded as actual evidence in the release specification that claims it. Intended checks are not evidence.

## Open questions

| Question | Impact | Proposed default | Resolve by |
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
| Rolling-window horizons in calendar or trading days | Window counts and comparability | 7, 30, 90, 180, and 365 calendar days, fixed in the analysis-set version | First analysis-set version |
| Taxes | Net results | Not modeled; stated as a limitation | Per study, as a declared scope choice |
