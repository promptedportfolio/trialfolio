# Guide for LLM agents authoring the research CLI specifications

This guide instructs an LLM coding agent to produce the initial specifications for a source-available Python CLI for Portfolio123 research under a custom personal-research license. It contains the project context, release sequence, scientific requirements, documentation responsibilities, and technical conventions needed to work without the original conversation.

The immediate assignment is to author the documentation that will guide implementation. Preserve the distinction between planned capabilities and working software. Do not implement the application, execute paid experiments, publish a repository, or place trades merely because this guide describes those activities.

Recommended repository location for this guide: docs/spec-authoring-guide.md.

Prepared on October 1, 2026. Provider observations are documentation and source-code findings, not evidence of successful integration with the owner's account. Recheck the relevant behavior during implementation.

**Owner decisions recorded on 2026-10-01.** These supersede conflicting text below. The current record is the decision table in [spec.md](spec.md#owner-decisions-and-defaults).

- The product is **Trial Folio**. The repository and the CLI command are `trialfolio`.
- Trial Folio builds on the Portfolio123 API only and does not integrate with DataMiner. Release 0.1.0 is API execution, 0.2.0 reviews saved runs, and 0.3.0 runs experiments ([ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md)). This supersedes sections 5 and 8 where they conflict.
- No representative provider response exists yet. The owner keeps Portfolio123 API credentials in a secret manager. Reference data is procured with them when a release needs it, and the owner performs any Portfolio123 web-UI steps on request.
- The project is the engine for reproducing published factor research. Project materials do not name any publication or brand, except where [D-10](spec.md#decisions) allows.
- Nathan Slaughter adopts the license himself. Counsel review is not a condition of adopting the license or of release.
- Generated reports contain no scripts, count as output rather than covered code, and may be shared with the concise notice intact. Users remain responsible for data-provider terms.
- Liquid assets exclude retirement accounts, with no further specification. "Primary source of income" means more than half of total income. "Family members" is used without a defined list.
- A release is Implemented when it works and is used privately. It is Released only after the license is adopted and a distribution channel consistent with section 17.3 is chosen.

## 1. Project intent and constraints

Build a configuration-driven CLI that helps investors collect, compare, reproduce, and eventually evaluate investment-strategy evidence with scientific discipline. Reuse Portfolio123's research engines and official Python wrapper. The project's contribution is controlled experimentation, durable evidence, transparent comparisons, and defensible evaluation.

The author and licensing contact is Nathan Slaughter, git@nathanslaughter.com. Texas is the starting jurisdiction for legal review. Apply the custom licensing and publication policy in section 17; it supersedes the former MIT recommendation. Do not describe the project's own restricted license as open source.

The owner wants independently useful public releases after approximately one, two, and three cumulative focused working days. Those days may be spread across two weeks. Further development may pause for months. Each release must remain useful without the next release. These are scope targets, not promises that a calendar deadline overrides verification.

The eventual environment includes Portfolio123 API access with approximately 20 years of history, Tiingo APIs, LLM APIs, and a human when judgment or missing information requires one. Actual data coverage, entitlements, quotas, and export permissions must be checked. Access to 20 years does not establish 20 years of usable or previously unseen evidence.

The owner wants to evaluate either:

1. Performance above a suitable benchmark after specified costs.
2. Attractive standalone returns and risk.

Support both objectives eventually. Each confirmatory study must choose its primary objective and decision criteria before seeing its evaluation results. Reporting both does not permit selecting whichever happens to pass.

Use Python as the implementation language. Use Pydantic v2 for appropriate data-validation and serialization boundaries, and typing.Protocol for appropriate behavioral interfaces. Do not introduce Go or require an LLM API for the first releases.

There are two distinct roles for LLMs:

- Development agents use these documents to build the software.
- Optional future research agents propose hypotheses within a bounded research process.

Using LLMs for development does not authorize or require autonomous strategy discovery in the product.

## 2. Interpret requirements and uncertainty consistently

Use the following labels in the generated documents:

| Label | Meaning |
|---|---|
| Requirement | A user constraint or an adopted product invariant |
| Proposed default | A recommendation that may be changed before the relevant implementation or study |
| Verified observation | Behavior supported by a cited source or recorded integration evidence |
| Open question | An unresolved matter with a stated impact and resolution point |
| Deferred | A capability outside the current release |

Use MUST for required behavior, SHOULD for a default with a documented reason for exceptions, and MAY for optional behavior. Do not turn every implementation preference into a mandatory architectural rule.

Proceed on reversible documentation choices using the proposed defaults below. If a material ambiguity prevents specifying correct behavior, ask a concise question, explain its consequence, and recommend a sensible default. Continue independent work. Do not repeatedly seek approval for decisions the owner has already made.

Avoid invented facts: no fabricated export layouts, provider endpoints, package versions, benchmarks, test results, live integrations, completed releases, or performance claims. Mark examples as illustrative until validated.

After the initial document set is adopted, this guide remains bootstrap context. Maintain current requirements in the documents that own them. Do not treat an old example in this guide as an override of a later explicit, accepted requirement.

## 3. Required document structure and ownership

Create the following initial documentation structure in the eventual repository:

~~~text
AGENTS.md
README.md
LICENSE
CONTACT.md
THIRD_PARTY_NOTICES.md
docs/
  README.md
  spec-authoring-guide.md
  spec.md
  roadmap.md
  contracts.md
  methodology.md
  licensing-policy.md
  disclaimers.md
  releases/
    0.1.0-review.md
    0.2.0-api-execution.md
    0.3.0-experiments.md
  adrs/
    0001-python-and-portfolio123-integration.md
    0002-pydantic-contracts-and-protocols.md
    0003-versioned-research-artifacts.md
    0004-custom-personal-research-license.md
~~~

Add docs/methodology.md because the full scientific plan needs a stable home without overwhelming the product summary or early release specifications. The initial methodology is a design, with implementation status explicitly identified.

| Document | Responsibility |
|---|---|
| AGENTS.md | Agent entry point, reading order, scope rules, development commands, verification expectations |
| README.md | Investor-facing purpose, actual supported capabilities, installation, example, limitations, and the Portfolio123 subscription and non-affiliation notices from section 17.9 |
| LICENSE | Complete custom license text for the project's own material; draft until reviewed and adopted |
| CONTACT.md | Nathan Slaughter's licensing contact and written-permission request instructions |
| THIRD_PARTY_NOTICES.md | Applicable dependency and third-party rights, licenses, and notices |
| docs/README.md | Reading map and links to the relevant release and contracts |
| docs/spec.md | Stable product purpose, vocabulary, user outcomes, enduring requirements |
| docs/roadmap.md | Release sequence, dependencies, value, and deferred scope |
| docs/contracts.md | Interface semantics, artifact meanings, errors, versioning, compatibility |
| docs/methodology.md | Research design, statistical assumptions, evidence requirements, interpretation |
| docs/licensing-policy.md | Eligibility, reserved uses, permission procedure, publication policy, and outstanding legal decisions |
| docs/disclaimers.md | Research limitations, financial-result notices, warranty and liability language consistent with LICENSE |
| docs/releases/*.md | Exact increment, acceptance criteria, implementation tasks, verification |
| docs/adrs/*.md | Significant decisions, alternatives, consequences, and decision status |

Keep release lifecycle status authoritative in each release specification; the roadmap should link to it instead of maintaining an independent detailed progress ledger.

Executable contract files will be introduced with implementation:

~~~text
src/<package>/contracts/
schemas/
tests/fixtures/
~~~

During a documentation-only assignment, specify their contents and verification requirements. Do not claim generated schemas or passing fixtures exist. If executable contracts are separately within the assigned scope, produce only the necessary models, schemas, examples, and checks.

### Document consistency

The documents have complementary responsibilities:

- The product spec defines enduring obligations.
- Methodology defines the meaning and conditions of scientific assessments.
- Release specs define the increment being implemented.
- Contract prose defines interface semantics.
- Pydantic models, once implemented, define executable structures.
- Generated JSON Schemas publish those structures.
- Tests provide conformance evidence.
- ADRs explain decisions and their history.
- LICENSE, once adopted, controls the legal grant; documentation summaries must match it and must not expand permissions.

A contradiction is a defect to resolve, not a reason to select the easiest interpretation. The roadmap alone is not an implementation assignment. Historical ADRs do not require readers to reconstruct current contracts from scratch.

Reference shared requirements rather than copying them across documents. Use stable identifiers for requirements and acceptance criteria that benefit from traceability. Do not annotate every paragraph or code line.

## 4. Product vocabulary and invariants

Define these terms in docs/spec.md:

- **Study:** a research question, objective, data boundaries, search history, and evaluation protocol.
- **Experiment:** a declared collection of cases addressing a particular question.
- **Case:** one resolved configuration or candidate strategy within an experiment.
- **Candidate:** a strategy specification considered during research; it can appear in multiple cases.
- **Attempt:** one execution or acquisition attempt for a case.
- **Artifact:** saved input, output, metadata, or derived evidence.
- **Assessment:** a versioned interpretation of artifacts using specified methods.
- **Report:** a presentation of the assessment and its evidence.

Preserve these distinctions even if the earliest implementation uses fewer objects. A retry is an attempt; it is not automatically a new strategy hypothesis. A provider request count is not a multiple-testing family size.

Give identifiers to at least these enduring invariants:

1. Preserve all collected and evaluated evidence within retention rights, including failed, rejected, and abandoned research cases where known.
2. Preserve source provenance and distinguish verified metadata, user-supplied metadata, inferred values, and unknowns.
3. Never silently replace unavailable information with zero or a favorable default.
4. Separate source responses from normalized data and calculated results.
5. Regenerate analysis and reports from archived artifacts without acquiring fresh provider data.
6. Record the inputs, implementation version, and method settings behind every calculated result.
7. Account for every planned case, including skipped, failed, incomplete, and uncertain attempts.
8. Make comparisons' settings, actual coverage, costs, and limitations visible.
9. Record research history before implementing statistical corrections.
10. Make scientific and trading-readiness claims only when their stated evidence requirements have been met.
11. Keep credentials out of artifacts, logs, fixtures, and reports.
12. Preserve readable historical artifacts as the application evolves.
13. Preserve the author's licensing restrictions, attribution, financial-result notices, and applicable third-party rights.
14. Keep logs, traces, and diagnostics on the machine or container that produced them, and never transmit user inputs or outputs except in provider requests the user invokes or explicitly enables.

“All data” means all material retrieved and evaluated, plus known acquisition failures and unavailable fields. It does not imply access to proprietary provider databases or missing outputs that the API cannot return. Imported CSVs cannot recover earlier raw API responses.

## 5. Releases after one, two, and three days

These are complete increments. A releasable increment includes its documentation, installation path, meaningful verification, and example. Narrow functionality when necessary; do not defer basic correctness to a later release.

### Release 0.1.0 after one cumulative day

**Outcome:** compare existing DataMiner results with their supplied configurations and understand the differences.

Specify an offline CLI that accepts two or more runs with an explicit baseline. Initially support one verified ScreenBacktest CSV export layout and the corresponding supported configuration subset. Confirm the actual layout before promising compatibility. Attach original configuration files even where some settings cannot yet be interpreted.

Required behavior:

- Preserve imported files and record hashes, import time, format version, parser version, and source identity where available.
- Label attached historical configuration as user-supplied unless independently verified.
- Compare available reported metrics and show differences from the baseline with explicit units.
- Show changed settings and flag unexplained date, benchmark, currency, cost, or execution differences.
- Distinguish intended experimental changes from unexplained mismatches.
- Represent missing metrics and missing metadata explicitly.
- Produce a self-contained HTML report, normalized comparison data, and an inspectable manifest.
- Run entirely offline, including the supplied synthetic demo.
- Identify statistical validation and trading readiness as not assessed.

Do not require return series, holdings, or charts when the export lacks the necessary data. Summary statistics alone do not justify reconstructing returns, confidence intervals, or drawdown histories. Do not infer precision beyond that of the export.

Example command to refine in the release contract:

~~~text
trialfolio review comparison.yaml --out review/
~~~

Acceptance criteria must include different benchmarks, a missing metric, an unsupported layout, preserved originals, offline report generation, and a clean-install example. Ship a supported-format statement, an explicit capability table, and the adopted license and notices described in section 17.

If no representative current export is available, document the missing verification and obtain one before claiming importer compatibility. A synthetic fixture demonstrates behavior but does not establish provider compatibility.

### Release 0.2.0 after two cumulative days

**Outcome:** execute one supported screen backtest and preserve the relationship between its settings and results.

Add the official p123api wrapper as an input adapter. Keep the 0.1.0 import and reporting path useful.

Required behavior:

- Validate a narrow configuration, resolve supported settings, and show the planned request before execution.
- Support one documented long-only stock screen-backtest path.
- Save the redacted request, full returned payload, timing, provider metadata, and execution outcome before deriving tables.
- Distinguish raw HTTP bytes, decoded provider payloads, and normalized data; do not claim wire-level capture if the wrapper exposes only decoded JSON.
- Generate the same result contract and report used by imported data.
- Provide actionable authentication, quota, unsupported-capability, and response-validation errors.
- Record mutable provider references and snapshot their definitions where available; otherwise label incomplete reproducibility.

Example:

~~~text
trialfolio run screen.yaml --out runs/baseline/
~~~

Acceptance requires a recorded real integration check with working account access, archived output, and offline regeneration. CI normally uses synthetic or permitted sanitized fixtures. Paid live checks are separate and respect the assigned budget.

Do not promise every DataMiner option or an exact clone of its GUI. A documented subset and migration example are sufficient.

### Release 0.3.0 after three cumulative days

**Outcome:** execute and review a controlled finite experiment.

Add an explicit baseline and a small list of predefined variants, such as holdings, rebalance frequency, liquidity rules, or slippage, limited to verified backend capabilities.

Required behavior:

- Compile all cases into fully resolved configurations before execution.
- Assign stable case identities and distinct attempt identities.
- Record study purpose, the planned cases, and any declared prior research.
- Run sequentially and save progress after each case.
- Resume verified completed work without repeating its provider calls.
- Record uncertain completion separately; do not automatically repeat a potentially charged or mutating request.
- Treat a changed configuration as a new case or plan revision, not as the old completed case.
- Produce an experiment report showing every case and its outcome.
- Keep execution success separate from strategy usefulness.

Example, with `run`, which executes a `kind: experiment` configuration as it does a screen ([D-24](spec.md#decisions)):

~~~text
trialfolio run study.yaml --out runs/study/
~~~

Acceptance includes interruption and restart, configuration changes, a failed case, uncertain completion, and complete accounting. Automatic search, sophisticated scheduling, and statistical acceptance decisions are deferred.

The product is named Trial Folio, and its CLI command is `trialfolio` (owner decision, 2026-10-01).

## 6. Roadmap beyond the first three releases

Preserve the following sequence as proposed increments. Refine later release names and estimates when the dependencies are understood.

| Increment | Added investor value | Important dependency |
|---|---|---|
| Simulation review | Inspect and compare saved simulations, settings, holdings, transactions, and available performance | Verified strategy endpoints and output granularity |
| Robustness and rank diagnostics | Test predefined perturbations and inspect rank behavior; rerun supported simulation variants | Isolated provider state, comparable outputs, cost semantics |
| Statistical evaluation | Apply chronological evaluation, uncertainty estimation, and multiple-testing procedures | Sufficient return data, research history, frozen protocol, validated methods |
| Forward tracking | Compare timestamped signals and modeled execution with later observed results and imported fills | Identifier alignment, price conventions, execution records |
| Optional discovery | Use FactorMiner or bounded LLM proposals to generate candidates within development data | Reliable evaluation boundaries and complete selection history |

Ranks, screens, and simulations serve different purposes:

- Rank snapshots, bucket behavior, factor-removal tests, and information coefficients diagnose signals.
- Screens provide relatively simple portfolio baselines and sensitivity experiments.
- Simulations represent holdings, trading rules, turnover, cash, and execution assumptions.

Not every study needs every diagnostic. A strong factor diagnostic is not sufficient evidence that a portfolio implementation is tradable. Evaluate the actual proposed portfolio rules before a deployment assessment.

The earlier estimate of approximately two to four working weeks applied to a broader validated tool. Do not reinterpret it as a prerequisite to publishing 0.1.0 or as a guaranteed schedule for the full scientific roadmap.

## 7. Scientific methodology to preserve in the specifications

Write docs/methodology.md as an explicit research design. Identify methods that are proposed, implemented, validated, or unavailable. Include a table mapping each scientific requirement to its intended release, required artifacts, acceptance evidence, and current status.

### 7.1 Define the question before measuring success

Each confirmatory protocol must specify the economic hypothesis, primary objective, target population/universe, benchmark, expected implementation, return frequency, costs, minimum economically relevant effect, risk constraints, testing direction, error criterion, and stopping/selection rules.

Distinguish arithmetic mean active return, compound wealth growth, risk-adjusted alpha, information ratio, and standalone Sharpe ratio. They answer different questions. CAGR above a benchmark is not automatically risk-adjusted alpha.

Proposed default: use one primary claim per confirmatory study, with other metrics reported as secondary. Require study-specific benchmark and cost choices rather than silently assuming SPY or zero costs. Standalone Sharpe analysis must identify its risk-free series and return convention.

The owner has not specified universal drawdown limits, capital, slippage, a minimum acceptable return, or a significance threshold. Make these explicit study inputs or documented proposed defaults, not invented user decisions.

### 7.2 Separate development, selection, and confirmation

Use chronological boundaries suited to the strategy's data and return horizon. Development includes factor direction, factor choice, weights, universe changes, preprocessing, thresholds, and other choices informed by returns. Validation used to choose a winner is selection data.

A final holdout is meaningful only if it was not previously inspected or used in development. Record known prior exposure, including manual work outside the CLI. With previously inspected history, label retrospective evaluation honestly and rely on new forward evidence for genuinely unseen observations.

An illustrative 10-year development, 6-year validation, and 4-year holdout division is only an example for a 20-year dataset. The specification must justify the actual split, available observations, and power; it must not make those numbers a universal rule.

For walk-forward evaluation, specify what is refitted, when, and using exactly which past data. Nest all outcome-driven selection inside each training period. Prevent training labels whose outcome windows cross evaluation boundaries. Specify purging or a gap based on the label and holding horizons rather than a decorative fixed gap.

Archive protocol and candidate definitions before releasing protected results. After holdout inspection, changing a candidate creates further research; do not reuse the same period as a fresh holdout.

Access controls and data scoping can reduce accidental leakage, but a local tool cannot prove the owner never inspected the data elsewhere. Record this limitation.

### 7.3 Understand the Harvey and Liu concern

The owner recalled Harvey and Liu when asking whether perturbations raise the required t-statistic. Their paper “Backtesting” addresses multiple testing and data-mining adjustments. Searching more strategies can require stronger evidence, and correlations among tests matter. A universal fixed t threshold is not the procedure. [Harvey and Liu, Backtesting](https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF)

For this project's protocol, record every outcome-informed choice that contributes to selection: factors, signs, weights, rules, universes, dates, metrics, and rejected alternatives. Searching universes can matter just as searching factors can.

Separate:

- Provider operations and retries.
- Distinct candidate specifications.
- Statistical hypotheses and their declared family.
- Predefined diagnostic perturbations.
- Adaptive changes made after seeing outcomes.

A predefined diagnostic does not mechanically add one independent hypothesis per API request. If its outcome influences which system is selected, that selection must be represented. Keeping only finalists or dropping correlated factors does not erase the research history.

Unknown earlier searches cannot be repaired by pretending the count starts at installation. Record an incomplete search-history status, analyze sensitivity to plausible prior-search assumptions where defensible, and limit the resulting claim.

### 7.4 Specify inference before implementing a statistical badge

Proposed conservative initial statistical design:

1. Freeze the candidate family before an evaluation period is exposed.
2. Use aligned portfolio-level return observations with a declared estimand and null hypothesis.
3. Predeclare a dependence-aware method for individual uncertainty or p-values. Candidates include a correctly specified HAC estimator or a time-block bootstrap; the final choice requires a methods ADR.
4. For that fixed family, consider Holm adjustment with valid individual p-values as the initial family-wise procedure.
5. Use the final untouched holdout for the already frozen decision procedure.

This is a proposal, not an implemented or validated algorithm. Merely counting adaptive searches and applying a correction does not repair all selection bias or repeated peeking. A sequential/adaptive protocol needs its own justification.

Before marking a statistical release ready, specify and test the null, one- or two-sided alternative, frequency, lag or block-length rule, missingness/alignment policy, number of resamples, random seed, family definition, minimum sample requirements, and decision policy. Justify each method with primary sources and numerical verification.

Persist the significance policy as a study input: error rate, method/version, hypothesis family, and assumptions about prior searches. Persist the calculated adjusted p-values and, where the chosen procedure supports it, the applicable critical value. Do not expose an unexplained “required t” number or equate a raw experiment count with an estimated number of independent tests.

When comparing strategies, preserve their cross-strategy dependence in joint resampling. Do not treat stocks, trades, overlapping rolling windows, or repeated backtests as independent replications of the same portfolio hypothesis.

More advanced procedures, such as Romano–Wolf stepdown, a deflated Sharpe ratio, or probability-of-backtest-overfitting diagnostics, may be researched later. Do not assemble a collection of impressive-looking scores without checking their assumptions and applicability.

Report effect estimates, uncertainty, sample size, sensitivity, and economic significance. Report adjusted and unadjusted values with clear labels when applicable. A p-value is not the probability that a strategy will outperform in the future. An inconclusive result is a valid outcome.

### 7.5 Require data integrity appropriate to the claim

The eventual methodology must address:

- Point-in-time availability, reporting delays, and preliminary versus complete financial data.
- Historical universe membership, survivorship, delistings, ticker changes, and stable identifiers.
- Corporate actions, dividends, splits, currencies, and adjusted versus unadjusted prices.
- Actual coverage, missingness, duplicate records, calendar alignment, and changing sample composition.
- Outlier handling and exclusions, with original observations retained.
- Time of signal formation versus first permissible execution.
- Data revisions and the limits of a vendor rerun's reproducibility.

Treat future-return columns as labels, never as signal inputs. Verify labels end within the permitted partition. Do not silently shorten the evaluation window to obtain attractive coverage or performance.

Tiingo can eventually support specified price checks, benchmark series, and forward tracking where its data is suitable. Do not assume it reconstructs Portfolio123's historical fundamentals or universes. Reconcile identifier, calendar, dividend, and price-adjustment conventions before comparing providers.

### 7.6 Test robustness and economic usefulness

Predefine a bounded set of relevant perturbations. Possibilities include neighboring factor weights, removal of one factor, liquidity thresholds, holdings count, rebalance schedule, universe boundaries, signal delays, execution assumptions, and higher costs.

Universe changes alter the opportunity set and may require a different suitable benchmark. Do not require every legitimate strategy to work in every universe. Evaluate whether sensitivity is consistent with the economic hypothesis and intended trading domain.

Inspect contribution concentration by time, sector, security, and extreme events where data permits. Prefer a stable region of reasonable choices over an isolated peak, but do not turn “stability” into an unregistered optimization score.

Evaluate commission, spread/slippage, turnover, financing/borrow where applicable, participation in volume, position size, concentration, cash behavior, and plausible capital capacity. Treat taxes as a separately declared scope choice.

Repricing a fixed trade list under different costs is a useful sensitivity calculation, but it is not always equivalent to a full rerun: costs may change cash, sizing, or subsequent trades. Label that distinction.

Historical trading feasibility remains conditional on assumptions. Forward signal timestamps, paper tracking, and eventually observed fills provide additional evidence. Paper execution alone does not prove achievable market fills.

### 7.7 Keep the assessment multidimensional

Report data quality, historical economic performance, statistical evidence, robustness, and implementation feasibility separately. Define any overall decision as a transparent predeclared rule over those dimensions.

Candidate outcomes include rejected, inconclusive, and meeting predefined criteria for additional forward research. Early releases must not emit affirmative statistical or deployment judgments. Any later terminology about deployment review requires legal review of the actual functionality and presentation; it must not become a recommendation that an individual invest. Passing a backtest is not an assurance of future superiority.

## 8. Portfolio123 reuse and integration findings

The following observations explain integration requirements. Reverify them against the chosen dependency version and account. Pin source commits in implementation evidence when relying on source behavior.

| Observation | Specification implication |
|---|---|
| The official p123api wrapper handles endpoint calls, authentication, and retries | Reuse it; add durable application-level recording and bounded execution. [Wrapper documentation](https://portfolio123.customerly.help/en/articles/13765-the-api-wrapper-p123api) |
| DataMiner exposes YAML-driven operations and CSV export behavior | Read its export files and user-supplied configurations as data, and run backtests on Portfolio123's servers through p123api. Do not copy, port, or import DataMiner code; it is GPL-3.0 (see the third-party code boundary below). Verify one export before generalizing. [DataMiner source, for reference only](https://github.com/portfolio-123/dataminer/blob/master/data_miner.py) |
| DataMiner RankPerformance runs a screen backtest for each bucket | Do not assume direct rank-performance calls are equivalent. [RankPerformance](https://portfolio123.customerly.help/en/articles/14052-dataminer-operation-ranks-performance) |
| RollingScreen shifts start dates; detailed results are optional and off by default | Request the required detail and model overlapping outcomes appropriately. [RollingScreen](https://portfolio123.customerly.help/en/articles/14057-dataminer-operation-rolling-screen) |
| Inline ranking definitions reuse APIRankingSystem; documented zero node weight means equal weighting | Serialize shared-state operations and remove nodes explicitly for factor-removal experiments. [Ranking definitions](https://portfolio123.customerly.help/en/articles/13793-dataminer-ranking-definition) |
| Strategy endpoints document copies, reruns, settings, holdings, and transactions | Verify actual supported parameters and outputs before promising simulation perturbations. [Strategy API](https://portfolio123.customerly.help/en/articles/43325-api-strategy) |
| Wrapper conversions can reshape results and remove metadata | Save the full available provider payload first; distinguish aggregate rows from observations. [Wrapper source](https://github.com/portfolio-123/p123api-py/blob/master/p123api/client.py) |

Explicitly resolve dates, benchmark, price convention, point-in-time method, missing-value handling, costs, and output precision. Do not inherit “today” or zero costs silently. Confirm iteration inheritance semantics instead of guessing them.

Capability verification must cover simulation slippage overrides, historical holdings and return granularity, export detail, provider limits, and shared universe/ranking state. When updates affect a shared object, protect the whole update–execute–capture sequence or use verified isolated objects.

For managed execution, specify a case/request budget and bounded retry policy. Estimate API credits only where the endpoint expansion and pricing are verified; otherwise show request counts and unknown cost components. Preserve returned cost/quota metadata. Reconcile wrapper retries with the attempt log instead of promising visibility into requests the wrapper does not expose.

FactorMiner is optional discovery assistance. Its documentation describes automatic direction selection, filtering extreme returns, possible truncation after completely missing factor dates, next-close prices, and alpha/beta calculations without a risk-free adjustment. Its current factor-analysis source uses an ordinary one-sample t-test for IC. Confine selection to permitted development data, preserve exclusions, reconcile portfolio assumptions, and calculate final inference using the study's specified method. [FactorMiner documentation](https://portfolio123.customerly.help/en/articles/53980-factorminer), [calculation source](https://github.com/portfolio-123/factor-miner/blob/main/src/core/calculations/factor_analysis.py)

Provider access and raw-data redistribution are distinct. Before publishing examples, confirm their redistribution rights; prefer synthetic fixtures. Inspect applicable licenses before copying upstream code. Apply the project's restrictions only to material Nathan Slaughter has rights to license; do not override independent third-party grants. A dependency's permissive license does not make this project permissively licensed. Review copyleft compatibility before incorporating upstream code. Do not fork DataMiner; read its export formats as data and use the official wrapper for API access.

**Third-party code boundary:** integrate with Portfolio123's tools through their outputs and the API, not through their code. As checked on 2026-10-01, DataMiner is licensed under GPL-3.0, FactorMiner's repository declares no license, and p123api-py is licensed under MIT; reverify before relying on these. GPL-3.0 prohibits the further restrictions this project's license imposes, and an unlicensed repository grants no permission to copy or adapt its code, so either code in the distribution would prevent release under section 17's terms. [DataMiner license](https://github.com/portfolio-123/dataminer/blob/master/LICENSE), [p123api-py license](https://github.com/portfolio-123/p123api-py/blob/master/LICENSE)

- Use p123api as the only Portfolio123 code dependency, and list it with its license in THIRD_PARTY_NOTICES.md. Section 17.8 records the obligations for bundling it and its dependencies.
- Do not import, vendor, bundle, or port DataMiner or FactorMiner code, including in containers, notebooks, examples, or test utilities.
- Accept DataMiner exports and user-supplied configurations as data. Matching their file layouts and key names for compatibility is permitted.
- Learn operation behavior from Portfolio123's documentation and observed results. Upstream source may be read to confirm behavior; describe that behavior in original wording and cite it by link and pinned commit. Do not reproduce its code, structure, or distinctive logic, whether copied, retyped, translated, or paraphrased.
- Do not copy fixtures, sample configurations, or sample exports from those repositories; build synthetic fixtures instead.
- Any later need for upstream code requires a recorded license review and the owner's decision before copying.

## 9. Pydantic v2 and protocol conventions

### Pydantic models

Use Pydantic v2 for application-owned configuration, result manifests, study protocols when introduced, assessment records, and other serialized boundaries. Use its v2 validation and serialization methods. Configure unknown-field handling explicitly; reject misspelled application configuration. Parse CSV and provider-specific units in named adapter steps before validating normalized objects. Never use validation bypasses for untrusted input. [Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/)

The following are project design requirements:

- Define explicit unit, missingness, precision, and provenance policies.
- Reject non-finite numbers from interchange JSON; represent unavailable values with a reason.
- Avoid ambiguous booleans, percentage strings, or date coercions.
- Retain unknown provider fields in the source payload even when the normalized contract supports only a subset.
- Separate secret acquisition settings from persisted scientific configuration.
- Validate cross-field conditions such as date ordering and required metric context.
- Test the actual YAML, CSV, JSON, and Python validation paths used by the application.
- Keep large time series and tabular data in suitable tables; Pydantic need not model every dataframe row.

Use Pydantic models as the canonical executable structure and generate published JSON Schemas from them. Specify validation versus serialization schema mode when their representations differ. Schema generation does not encode every custom semantic validator, so test runtime semantics separately. Commit generated schemas and check for drift when the contract implementation exists. [Pydantic JSON Schema](https://pydantic.dev/docs/validation/latest/concepts/json_schema/)

Contract prose remains authoritative for intended meaning. A model defect must be fixed; “the model accepted it” does not establish scientific correctness. Do not independently hand-maintain the same field structure in Python and JSON Schema.

Declare the Pydantic v2 major-version constraint and record the tested dependency resolution. Use immutable or controlled-update representations for frozen plans, while recognizing that model-level frozen settings do not by themselves make nested objects or saved files immutable.

### Protocol interfaces

Use typing.Protocol for narrow behavioral interfaces where interchangeable implementations or test doubles are useful. Protocols provide structural typing; runtime-checkable protocols do not validate complete method signatures or scientific behavior. Use static checking and contract tests for those obligations. [Python typing documentation](https://docs.python.org/3/library/typing.html#typing.Protocol)

Potential interfaces, to introduce only when needed:

| Boundary | Candidate interface | Expected responsibility |
|---|---|---|
| Source import | ResultImporter | Interpret one known export layout and return a validated result |
| Provider execution | ScreenBacktestClient | Execute the supported request and return captured provider evidence |
| Artifact persistence | ArtifactStore | Persist/read artifacts with documented completion semantics; required from 0.1.0 (section 10) |
| Report generation | ReportRenderer | Render a saved assessment without provider access |
| Model access | ModelClient | Send a bounded structured request to the configured model backend and return validated output with usage metadata (section 11) |

The names are illustrative. Define preconditions, return types, exceptions, side effects, and capability limits. Keep data in models and behavior in protocols. Pass dependencies explicitly; avoid global provider clients.

Do not create a universal provider interface with dozens of unsupported methods, a plugin registry, service framework, or speculative abstractions for every future feature. Different import and execution paths can converge on the same result model without pretending they perform the same operation.

### Interface-independent core

The CLI is the first interface, not necessarily the only one; a desktop application, local API, or web UI may follow. Keep the application usable without the CLI from 0.1.0. This is a real boundary, not the speculative service framework excluded above. Section 17.10 covers the licensing conditions for those interfaces.

- The CLI parses arguments, reads configuration files, calls core functions, formats output, and maps errors to exit codes. Core functions accept validated models and return result models; they do not print, prompt, parse arguments, exit the process, or read environment variables.
- Importers accept file content with a declared source name, not only a filesystem path, so an uploaded file follows the same path as a local one.
- Planning returns a plan model. Execution requires an approved plan identified by its hash, so no charged or mutating request depends on an interactive prompt inside the core.
- Long-running execution reports progress through callbacks or events, supports cancellation between provider requests, and holds a lock that prevents two processes from executing the same experiment. Serialize Portfolio123 shared-state operations per account across processes, not only within one.
- Errors are typed, with stable codes and actionable messages. Only the CLI maps them to exit codes.
- Credentials come from an injected source, such as environment variables for the CLI or an operating-system keychain for a desktop application. Core code never reads secrets itself.
- Core functions called by an interface distributed separately from the package become public contract under the semantic versioning policy. Declare in docs/contracts.md whether core functions are public or internal.

## 10. Contracts and storage requirements

Keep the first artifact format small while preserving these concepts:

| Concept | Required meaning |
|---|---|
| Versions | Separate application, artifact schema, parser, provider wrapper, and analytical-method versions |
| Identity | Distinguish study, case, candidate, attempt, source artifact, and assessment identities as they are introduced |
| Source | Provider/import origin, source format, acquisition time, provenance confidence, available capabilities |
| Settings | Original supported input, resolved settings, mutable external references, declared purpose |
| Coverage | Requested and actual dates, frequency, calendar, currency, observation count, exclusions |
| Metrics | Value, unit, definition, context, reported/calculated origin, availability reason, source precision |
| Execution | Planned/running/succeeded/failed/skipped/unknown outcome, attempts, errors, charge information where available |
| Lineage | Input hashes, transformations, analysis settings, code version, random seeds where relevant |

Do not require unavailable future fields to contain fabricated placeholders. Introduce structured fields at the release that can define their semantics; early artifacts may explicitly declare limited capabilities.

### Semantic versioning policy

Application releases MUST use semantic versioning in the form `<major>.<minor>.<patch>`, with three non-negative integers and no leading zeroes. Follow [Semantic Versioning 2.0.0](https://semver.org/).

- From 1.0.0 onward, increment major for incompatible public-contract changes, minor for backward-compatible features or deprecations, and patch for backward-compatible bug fixes.
- Reset minor and patch to zero when major increases; reset patch to zero when minor increases.
- During initial 0.x.y development, this project requires a minor increment for new features or breaking changes. Patch releases must remain backward compatible.
- The first three planned releases are 0.1.0, 0.2.0, and 0.3.0. Use complete version numbers in release specifications, package metadata, and release notes.
- Published releases are immutable. Ship corrections as a new version.

For this project, the public contract includes documented CLI behavior, configuration formats, machine-readable outputs, supported artifact-reading behavior, and any explicitly public Python interfaces. Declare this boundary in docs/contracts.md. Document breaking changes and migration instructions, including during 0.x.y development. Adopt 1.0.0 when this boundary is intentionally declared stable.

Artifact schema versions also use `<major>.<minor>.<patch>` and evolve independently of application versions. A schema's version does not need to match the release introducing it. Define schema compatibility against documented readers and semantics, not field additions alone.

### Artifact compatibility and persistence

Define an artifact compatibility policy before shipping 0.1.0:

- Artifact versions are independent of package versions.
- Readers support documented historical versions with fixtures.
- New optional fields are not automatically assumed compatible with strict readers.
- Unknown schema versions fail clearly or enter an explicit restricted inspection mode.
- Migrations preserve originals and produce new artifacts.
- Configurations are strict; provider payload preservation and artifact extension policies are deliberate and separately specified.

Use raw files/JSON and normalized CSV initially. Add Parquet for large tables when needed. SQLite may later index runs; it must not become an unnecessary first-release prerequisite or an undocumented sole copy of the evidence.

Define atomic completion semantics for saved attempts. Mark a case complete only after its required payload and manifest are durably recorded. Hashes detect changes; they do not prove a provider's scientific correctness or make local files tamper-proof.

Route all artifact reads and writes through the ArtifactStore interface from 0.1.0, with a local filesystem implementation. Record paths in manifests relative to the run root, never as absolute paths, so artifacts stay valid when moved or served by another interface.

For canonical hashes, define ordering, number/date encoding, excluded secrets, and normalization version. Avoid conflating configuration identity with one execution attempt.

Document stdout/stderr, exit codes, output directory behavior, overwrites, unsupported input handling, and partial success. These are CLI behaviors; the core reports the same outcomes through typed results and errors (section 9). Separate process success from a strategy passing any research criterion.

Provider reruns can change because upstream data or engines change. Treat them as new attempts. Offline reproducibility means reproducing a declared analysis from archived inputs with identified code and settings, not promising identical future provider responses.

### Logging, tracing, and local-only diagnostics

Logs and traces are diagnostics, not evidence. Record outcomes, attempts, and accounting in artifacts; a log must never be the only record of an outcome.

**Local only:** no log handler, trace or metrics exporter, crash reporter, analytics call, or update check may send anything off the machine or container running the application. Outbound network traffic is limited to provider requests the user invokes or explicitly enables (Portfolio123, and later Tiingo or an LLM provider under section 11), carrying only what that operation requires. Disable telemetry built into dependencies; for example, Streamlit sends usage statistics by default through `browser.gatherUsageStats` (checked 2026-10-01). Where a container runtime or service manager captures stderr, its handling is the operator's configuration; the application adds no forwarding. The application never uploads logs; users decide whether to share them.

**Content:** logs never contain credentials, strategy definitions, formulas, configuration values, provider payloads, results, or imported file contents, at any level. Reference artifacts by ID and hash instead. Pydantic's default `ValidationError` text includes the invalid input value, so log validation errors from `errors(include_input=False)` or with `hide_input_in_errors` enabled. The CLI may still show an offending value to the user in the terminal. Do not capture local variables in logged tracebacks.

**Consistency:** proposed default: Python's standard `logging` module, with no added dependency.

- Core modules obtain loggers with `logging.getLogger(__name__)` and never configure handlers; the CLI or other interface configures them (section 9).
- Log files contain one JSON object per line with a UTC ISO 8601 timestamp, level, stable dotted event name such as `provider.request.completed`, message, application version, component, and the applicable run, case, attempt, and request IDs. Field names use snake_case. Document event names and fields in docs/contracts.md; they are not public contract unless declared.
- Use ERROR for a failed operation, WARNING for a degraded or unexpected condition the run continues through, INFO for lifecycle milestones, and DEBUG for diagnostic detail.
- The terminal shows human-readable messages on stderr, and the log file receives JSON lines, both from the same events.

**Tracing:** proposed default: use the event log as the trace rather than a separate tracing system. Emit start and end events with duration and outcome for each run, case, attempt, and provider request, linked by their IDs and parent IDs. This gives a local timeline for debugging without a tracing dependency. Adopt OpenTelemetry only through an ADR, with local file exporters only and no auto-instrumentation or environment-configured exporters.

**Metrics:** do not add a metrics system. Record per-run counts and durations in the run manifest, including provider requests, retries, failures, uncertain completions, and returned cost or quota metadata.

**Storage:** write logs and traces to a `logs/` directory within the run's output directory, excluded from artifact hashes, or to a per-user local log directory for commands without an output directory. Bound log size with rotation. Document the locations, and how to delete the logs, in the README.

## 11. Deterministic control and optional agentic research

Conditional execution does not require an agent. Use ordinary code for schema checks, coverage gates, fixed experiment expansion, retry rules, and configured stopping conditions.

Optional runtime LLM use may propose economic hypotheses, explain diagnostics, or suggest additional development experiments. Require structured output validated by Pydantic, a finite proposal/API budget, a declared data-access boundary, and a complete proposal/decision log.

Research agents must not inspect protected outcomes, change acceptance criteria after results, silently discard failures, or authorize trading. Record prompts, model/provider identifiers, relevant settings, tool actions, outputs, and accepted/rejected proposals. Seeds do not guarantee repeatable hosted LLM outputs; preserve actual outputs.

Humans are needed for unresolved economic intent, material protocol changes, uncertain external actions, and deployment decisions. Routine supported perturbations should be generated and run by configuration/API, without a human editing every factor.

### Model backends

Runtime LLM features MUST support three backends, selected by configuration and disabled by default:

| Backend | Access | Where data goes |
|---|---|---|
| Anthropic | Official `anthropic` Python SDK | Anthropic's API |
| OpenAI | Official `openai` Python SDK | OpenAI's API |
| Local model | A model server on the user's machine, reached through a configurable endpoint | Stays on the machine |

- Put the backends behind one narrow protocol that accepts a bounded request and a Pydantic output model, and returns validated output with usage metadata. Features depend on that protocol, never on a vendor SDK.
- Install vendor SDKs as optional extras so the base package has no LLM dependency. As checked on 2026-10-01, `anthropic` is MIT and `openai` is Apache-2.0; record them under section 17.8 when added.
- Proposed default for local models: an OpenAI-compatible chat endpoint with a configurable base URL, which common local servers such as Ollama and llama.cpp's server provide. Verify the chosen server's structured-output support before claiming it. Treat a backend as local only when its endpoint is on the loopback interface; any other host is remote for disclosure purposes.
- Use each provider's structured-output mechanism where available (for Anthropic, `output_config.format`, which the Python SDK's `messages.parse()` validates against a Pydantic model), and validate every response with the project's own Pydantic model regardless. Record and reject invalid, truncated, or refused responses; never repair them silently.
- Model IDs, endpoints, and generation settings are configuration, not code. Credentials come from the injected credential source (section 9).

Sending settings and results to Anthropic or OpenAI is permitted under invariant 14 only after the user enables that backend. Before a run's first model request, show which backend and model will receive data and which categories of data are included; the approved plan (section 9) covers the backend and the request budget. Save what was sent and received as local artifacts. Whatever the backend, including a local model, send nothing outside the declared data-access boundary: no protected evaluation outcomes and no credentials. State in the README that remote backends process data under the provider's own terms.

Test every backend against the same contract tests using recorded or synthetic responses; the default suite makes no model calls. Live model checks follow section 14's opt-in and budget rules.

## 12. Report requirements

Every release produces a report appropriate to its evidence, with unavailable sections identified rather than invented. The eventual report should contain:

1. Objective, primary claim, benchmark, and research status.
2. Strategy definition and what changed from the baseline.
3. Data sources, actual coverage, provenance, missingness, and exclusions.
4. Returns, risks, costs, exposures, and relevant implementation assumptions.
5. All cases and their outcomes, including failed or rejected cases.
6. Robustness results and concentration of contributions.
7. Statistical methods, assumptions, uncertainty, multiplicity handling, and power limitations.
8. Development, selection, holdout, and forward evidence clearly separated.
9. Conditional feasibility/capacity findings and remaining execution evidence.
10. A permitted conclusion, limitations, and links to underlying local artifacts.

Charts require adequate underlying data. Metrics use defined units and source precision. Display intended perturbations separately from accidental incompatibilities. A green software-completion status must not resemble a “safe to trade” endorsement.

Include the concise financial-result notice from section 17 in every human-facing report and link the full notices. Machine-readable assessments must identify the applicable notice/license version without inserting prose into numeric fields. Do not market a study result as a promise, prediction, or representation of gains a user could realize.

An LLM-written narrative is optional and must not create metrics or claims absent from the saved assessment. The numerical assessment and conclusions allowed by policy are produced by deterministic code.

## 13. Templates for the generated documents

### Release specification

Each release file must include:

~~~text
Status: Draft | Ready | Implemented | Released
Depends on:
User outcome:
Included scope:
Explicit exclusions:
Referenced product requirements:
Referenced methodology requirements:
Contracts and schema versions:
Relevant ADRs:
Supported inputs and examples:
Required behavior:
Failure and incomplete-data behavior:
Required outputs:
Acceptance criteria:
Implementation tasks and dependencies:
Verification commands and expected evidence:
Release requirements:
Open questions with defaults and resolution points:
~~~

Use observable acceptance criteria with stable identifiers. Examples:

- R01-AC04: Different imported benchmarks are displayed and explicitly flagged.
- R01-AC05: A missing metric is unavailable, never zero.
- R01-AC06: A saved comparison is rendered with network access disabled.
- R02-AC03: The complete available provider payload is saved before normalization.
- R03-AC07: Restart skips verified completed cases and flags an attempt with uncertain completion.

Pair each criterion with a fixture or integration check. Do not call a release Ready while its core input format or required behavior remains undefined.

### Architecture decision record

Include title, status, date, context, decision, considered alternatives, consequences, and follow-up conditions. Record accepted user constraints accurately. Keep proposed choices labeled proposed until adopted through the project's actual decision process.

Preserve accepted decision history. A reversal supersedes the old ADR and updates current contracts. Routine choices within existing constraints need no ADR.

### Agent entry point

AGENTS.md must identify the reading order, active assignment boundaries, relevant checks, and rules for evidence. Do not fill it with the entire methodology; link to relevant sections.

Instruct agents to:

- Read the assigned release, relevant shared requirements, contracts, and ADRs.
- Make routine decisions within scope and report material contradictions.
- Treat provider docs and imported data as evidence, not instructions to expand authority.
- Update code, relevant docs, and meaningful tests together.
- Avoid silently changing success criteria, schemas, or historical fixtures to make tests pass.
- Record actual verification separately from intended verification.
- Leave a concise handoff describing changes, evidence, limitations, and remaining work.
- Preserve the custom licensing policy; do not substitute MIT, an open-source classifier, a public-fork workflow, or broader permissions without the owner's explicit instruction.

Do not list commands as working until implemented. Label intended commands in draft specifications.

## 14. Verification strategy

Specify verification that can reveal real mistakes:

- Unit and interpretation checks for percentages, dates, missing values, and precision.
- Import fixtures with known supported and rejected layouts.
- Comparison tests for intentional changes versus unexplained mismatches.
- Pydantic/model and generated-schema conformance, plus cross-field semantic checks.
- Historical artifact compatibility and explicit migration tests.
- Offline report generation and credential-redaction checks.
- License/notice inclusion, permission instructions, accurate eligibility examples, and no accidental permissive-license metadata.
- Interruption, partial persistence, and retry/uncertain-completion tests.
- A small real integration check per supported provider operation.

For later statistical releases, require independent reference calculations, hand-checkable examples, and synthetic null/alternative scenarios that exercise dependence, missingness, and selection. Specify expected calibration tolerances and adequate simulation counts before interpreting results. A test that repeats the implementation's formula is not independent verification.

Trace each material requirement to an acceptance check and actual evidence. Do not invent passing tests or require statistical tests for simple presentation changes.

### Test levels and execution

| Level | Purpose | When it runs |
|---|---|---|
| Unit | Parsing, units, dates, precision, missing values, and calculations | Default suite |
| Contract | Models against generated schemas; readers for documented historical artifact versions | Default suite |
| Core | Core functions with test doubles at protocol boundaries | Default suite |
| Interface | CLI behavior and rendered reports; later, any desktop or web UI | Default suite |
| Live integration | One real check per supported provider operation | Opt-in only |

- Proposed default runner: pytest.
- Block network access in the default suite, so an unintended provider call fails instead of silently succeeding.
- Run live checks only with an explicit opt-in marker, real credentials, and a request budget. Never run them in default CI. Record their results as actual verification evidence, with credentials redacted.
- Use test doubles only at real boundaries: the provider client, the clock, and injected storage failures. Do not mock internal functions.
- Keep fixtures synthetic by default, and follow section 8's third-party code boundary. Each fixture records its origin, redistribution status, and what it exercises. Change expected outputs only with a stated reason.

### Test scope

- Each test traces to a requirement, an acceptance criterion, or a corrected defect. Do not add tests that trace to none.
- Test through core functions and CLI commands rather than private helpers, so internal restructuring does not break tests.
- Do not test third-party behavior, such as Pydantic's type validation, p123api's retries, or the argument parser. Test the project's use of it, such as rejecting misspelled configuration fields.
- Do not set a coverage-percentage target. Use coverage reports to find requirements without tests.
- Prefer targeted assertions to whole-file snapshots of HTML, CSV, or JSON. Compare exact output only where the exact bytes are the contract, such as canonical hashing.

### Interface tests

For the CLI, the user interface is the command behavior and the HTML report.

- CLI: run the installed entry point against fixtures. Check exit codes, the separation of stdout and stderr, machine-readable output, the files written, documented overwrite behavior, actionable error messages, and the absence of credentials. Include the clean-install example each release requires.
- Report: parse the HTML and check required sections, the financial-result notice and license links, units, missing metrics shown as unavailable, flagged benchmark and setting differences, and the absence of external resource references. If the report includes scripts, also open it in a headless browser with network access blocked and confirm it renders without errors.
- Logs and traces: run commands at DEBUG level against fixtures seeded with canary values in credentials, formulas, configuration, and results. Check that no canary appears in any log or trace file, and that files are written only to the documented log locations.
- Desktop or web UI, when added: keep logic tested at the core level so UI tests stay few. Cover the primary flows (import → compare → report; plan → approve → run; failure, cancellation, and resume). Check that displayed values match the saved assessment, that the notices appear, that a charged or mutating request cannot run without approval, and that the UI sends no requests other than provider calls the user invoked. Proposed default for a web UI: Playwright.

## 15. Authoring sequence and completion criteria

Produce the initial artifacts in this order:

1. Inspect the repository, existing instructions, and any accepted decisions.
2. Extract user requirements, proposed defaults, and unresolved questions into a small decision table.
3. Write the product vocabulary and enduring invariants.
4. Write the roadmap and exact 0.1.0 scope; outline 0.2.0 and 0.3.0.
5. Write the minimal shared contracts and Pydantic/protocol conventions.
6. Write methodology with explicit future implementation status and evidence requirements.
7. Complete acceptance criteria and tasks for the next implementable release.
8. Record significant decisions in ADRs.
9. Draft the licensing and disclaimer artifacts from section 17, then write the investor README and agent/documentation entry points.
10. Cross-check the resulting set for consistency, unsupported claims, and missing coverage.

Do not replace this guide with a generic software template. Carry forward the specific Portfolio123, statistical, provenance, and incremental-release requirements.

The initial documentation is complete when:

- Another agent can implement 0.1.0 without the original conversation.
- The one-, two-, and three-day increments each have an independent user outcome.
- Current scope is visibly distinct from the eventual scientific system.
- Shared meanings and interfaces have one clear owner.
- Pydantic models and generated schemas have a single structural maintenance path.
- Protocols are narrow and justified by real boundaries.
- Data and research history needed later are preserved from the earliest applicable release.
- No missing evidence is represented as a successful assessment.
- Material open questions identify what they block and recommend a default.
- Source observations have links and are distinguished from proposed design.
- Licensing drafts implement the owner's restrictions, identify Nathan Slaughter and his contact, and preserve non-waivable rights without claiming guaranteed exemption or immunity.
- Links and examples are checked; intended files and commands are not described as already implemented.

Finish the authoring task with the created-file list, the next implementable release, actual checks performed, and any remaining substantive questions with recommended defaults. Do not present the documentation pass as application implementation.

## 16. Defaults and decisions still to resolve

No further substantive clarification is required to start authoring the initial documents. The author has specified the licensing contact and Texas jurisdiction. The final license still needs the legal review and definition choices listed in section 17. Use these defaults while keeping their status visible:

| Topic | Sensible default | Resolve by |
|---|---|---|
| Project/package name | Trial Folio; repository and CLI command `trialfolio`; proposed Python package `trialfolio` | Decided 2026-10-01, except the package name, before packaging |
| Implementation language | Python; Pydantic v2 and appropriate protocols | Established direction |
| Application license | Required custom source-available personal-research license; reserved uses need Nathan Slaughter's prior express written permission | Draft now; legal review and adoption before public release |
| Licensing contact | Nathan Slaughter, git@nathanslaughter.com | Established direction |
| Legal jurisdiction | Texas as the review and proposed governing-law starting point, subject to mandatory applicable law | Legal review before adopting final terms |
| Initial strategy scope | Long-only stock screen comparisons | 0.1.0 specification |
| First export layout | One actual current ScreenBacktest CSV layout | Before importer compatibility is claimed |
| Schema maintenance | Pydantic models generate versioned JSON Schemas | First executable contracts |
| Versioning | Required `<major>.<minor>.<patch>` semantic versioning; independent application and artifact schema versions | First release |
| Storage | Local immutable source artifacts, JSON metadata, CSV normalized output | 0.1.0 |
| Execution | Sequential, finite, explicit cases | 0.2.0 and 0.3.0 |
| Scientific objective | Both objective types supported; one primary per study | Before confirmatory evaluation |
| Benchmark, capital, costs, risk limits | Explicit study inputs; no invented universal settings | Before the relevant assessment |
| Statistical threshold and method | Proposed family-wise 5% level with a justified method; not a hard-coded product-wide truth | Methods ADR and study protocol |
| Historical split | Chronological and justified by data, horizon, prior exposure, and power | Before evaluation data is exposed |
| Runtime LLM use | Optional, deferred, bounded to development; Anthropic, OpenAI, and local-model backends (section 11) | Discovery release |
| Public sample data | Clearly labeled synthetic fixtures | First release |

If a question becomes necessary, ask it with a recommendation. Example: “Which ScreenBacktest export version should 0.1.0 support? Recommended default: the current version from one representative export, with all other layouts explicitly unsupported until verified.”

The goal of the documentation is executable clarity: a narrow first release, honest evidence, and a preserved path to scientifically rigorous evaluation.

## 17. Custom licensing and financial publication policy

This section records Nathan Slaughter's licensing requirements and supplies drafting language for the initial legal artifacts. It is not a legal opinion, an adopted license by itself, or a finding that the product qualifies for a regulatory exclusion. Have Texas counsel with software-licensing and securities-law experience review the actual distribution, functionality, marketing, terms, and assent mechanism before adopting final release terms.

The intended approach is a custom source-available personal-research license with separately negotiated written permissions for reserved uses. It is not an MIT license or an OSI-approved open-source license. Restrictions on professional use and publication are incompatible with the Open Source Definition's required freedoms. [Open Source Definition](https://opensource.org/osd)

### 17.1 Author, contact, and scope

Identify Nathan Slaughter as author and licensor of the material he has rights to license. Use git@nathanslaughter.com for all licensing and permission requests. CONTACT.md must provide that address and state that sending a request does not grant permission.

Use “Nathan Slaughter Personal Research License” as a proposed descriptive title. Clearly mark the initial text as a draft until adopted. Describe the project as source available under a custom license in the README, package metadata, documentation, and release announcements. Do not retain an MIT badge or permissive-license classifier for the project itself.

Define the covered software and associated project materials. Preserve separately licensed dependency rights and notices. Do not claim exclusive ownership over users' inputs, numerical findings, or third-party data through this license.

The author's right to publish his own project does not authorize recipients to republish it. Any contributor arrangements must give the author sufficient rights to distribute accepted contributions under the stated policy; do not assume a public pull request automatically supplies all necessary rights.

### 17.2 Permitted individual research and professional users

The general grant is limited to eligible natural persons for their own private research, including research for investment decisions concerning themselves and family members, subject to the full terms and notices. It permits necessary private copies and private modifications for that authorized purpose. It does not grant public-distribution or sublicensing rights.

An individual is a **Professional User** under this custom license if **any one or more** of the following applies:

1. The individual has **more than US $5,000,000 in liquid assets**.
2. The individual makes investment decisions for **anyone other than themselves and family members**.
3. The individual **resells research about stocks as their primary source of income**.

The conditions are alternatives, not cumulative requirements. Exactly US $5,000,000 does not trigger the asset criterion by itself. Making decisions for an unrelated person triggers the second criterion even without compensation. Meeting the asset or income criterion triggers the permission requirement even when the intended research is only for oneself.

Professional Users must contact Nathan Slaughter and obtain his **prior express written permission before using the project**. An inquiry, silence, attribution, donation, or purchase of an unrelated product is not permission. The written grant must identify the recipient, permitted scope, and any relevant duration or redistribution rights.

“Professional User” is only a contractual category for this project. It is not a statement about investment-adviser registration, accredited-investor status, qualified-purchaser status, or eligibility for a legal exemption. This license does not authorize a user to provide regulated services.

Organizations and persons using the project on an organization's behalf are outside the individual personal-research grant and need separate written authorization. A user who ceases to qualify for the general grant must obtain permission before continuing use outside it.

The final license must define ambiguous terms before adoption. Proposed definitions for review:

| Term | Proposed starting point for author and counsel review |
|---|---|
| Liquid assets | The individual's beneficially owned cash, cash equivalents, and readily marketable financial assets, valued in U.S. dollars; specify valuation timing, joint ownership, retirement-account treatment, and treatment of liabilities |
| Family members | A stated list covering spouse/domestic partner, parents, grandparents, children, grandchildren, and siblings, with adoption and step relationships addressed; do not leave the scope implicit |
| Primary source of income | A specified measurement period and method; consider whether “largest income category” or “more than half of income” matches the author's intent |
| Resells research | Preserve the author's stated criterion; clarify its relationship to original paid research rather than silently changing it to every paid research activity |
| Personal research | Private analysis within the individual/family scope; no implied license for an employer's work, client services, or redistribution |

Keep these definitions visibly proposed until resolved. Do not ask users to upload account balances, bank statements, or family identities merely to run the software. A proportionate local acknowledgment, designed with counsel, is the preferred starting point.

### 17.3 Public projects, published code, and reserved rights

No person may incorporate the covered code, a covered portion, or a covered modification into **any public project or any published code without Nathan Slaughter's prior express written permission**. The rule applies whether the receiving project is free, paid, commercial, nonprofit, source available, or open source.

The final terms must also reserve permission for publishing, redistributing, sublicensing, or supplying the covered code or modified versions to others, including public forks, vendored source, packages, binaries containing the code, containers, notebooks containing copied code, and hosted services incorporating it. Private modifications permitted for personal research do not carry a right to publish them.

Written permission for professional use does not automatically include permission to publish or incorporate code elsewhere. Those rights must be explicit. Preserve any rights that applicable law does not permit the license to restrict.

Distinguish code from results. A data-only finding is not automatically a derivative software distribution. A generated HTML report may contain supplied scripts or templates; decide and document any report-publication permission explicitly. Do not silently create an exception to the author's no-published-code condition. Private report use remains within the permitted research purpose, subject to data-provider rights.

**Hosting compatibility:** public GitHub repositories grant users on-platform viewing and forking rights under GitHub's terms. A custom notice cannot simply pretend those platform grants do not exist. Before publication, select a distribution channel consistent with the author's restrictions or obtain his explicit decision on a narrowly defined hosting exception. Do not silently weaken the restriction to accommodate a preferred host. [GitHub user-generated content terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content)

Review dependency and contribution compatibility. Do not add the project's use restrictions to third-party material licensed independently under different terms. In particular, copying copyleft-covered implementation into a restricted distribution needs compatibility analysis or separate permission. [GNU licensing FAQ](https://www.gnu.org/licenses/gpl-faq.html.en#NoMilitary)

Check for any earlier grants before changing an existing release's license. Do not assume a new notice removes recipients' rights under previously granted terms. No existing MIT-licensed application release has been established by this guide.

### 17.4 Research and financial-result notice

The final terms must require users to understand the limitations of backtesting and the absence of any representation of realizable financial gains. Proposed full notice for review:

> This software, its documentation, examples, analyses, and outputs are provided for general research and informational purposes. They do not constitute personalized investment, financial, legal, accounting, or tax advice, an offer or solicitation concerning any security, or a recommendation to buy, sell, hold, or apply any investment strategy. Use of the software does not itself establish an advisory, fiduciary, brokerage, or client relationship with Nathan Slaughter or the project's contributors.
>
> Historical, hypothetical, simulated, and backtested results are not actual trading results unless expressly identified and supported as such. They depend on data, assumptions, modeling choices, and historical conditions and may be affected by hindsight, selection bias, overfitting, incomplete data, revisions, liquidity constraints, and costs or execution effects that are omitted or inaccurately modeled. Statistical significance does not establish future profitability or practical tradability.
>
> No result, ranking, score, comparison, example, or statement represents or promises that any person could or will realize financial gains, outperform a benchmark, avoid losses, or obtain similar results by investing in any security or applying any strategy. Past or simulated performance is not a reliable assurance of future results. Investments can lose some or all of their value; leveraged positions may produce losses beyond the initial capital.
>
> Users are responsible for independently evaluating information, obtaining appropriate professional advice, complying with applicable law and third-party terms, and making their own decisions. Nathan Slaughter does not undertake through this software to assess any user's financial situation, suitability, objectives, or tolerance for loss.

A concise notice for every report:

> Research output only. Backtested and hypothetical results do not represent achievable returns. No financial gain, future performance, suitability, or protection from loss is represented or promised. This report is not personalized investment advice. See the full license and research limitations.

If a report includes actual forward observations, label which portions are actual, simulated, or hypothetical; do not mislabel the entire report as a backtest. A disclaimer does not cure contradictory marketing or functionality.

### 17.5 Warranty exclusions and liability limitations

Draft the exclusions conspicuously and subject to applicable law. Include Nathan Slaughter and, to the extent appropriate, contributors and licensors. Proposed text for counsel to adapt:

> **AS IS; AS AVAILABLE; WITH ALL FAULTS. TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, THE SOFTWARE AND ALL ASSOCIATED MATERIALS AND OUTPUTS ARE PROVIDED WITHOUT ANY WARRANTY, REPRESENTATION, GUARANTEE, OR CONDITION, WHETHER EXPRESS, IMPLIED, STATUTORY, OR OTHERWISE. THIS INCLUDES WARRANTIES OR CONDITIONS OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, NON-INFRINGEMENT, SATISFACTORY QUALITY, ACCURACY, COMPLETENESS, TIMELINESS, RELIABILITY, AVAILABILITY, SECURITY, COMPATIBILITY, AND THOSE ARISING FROM COURSE OF DEALING, USAGE OF TRADE, OR COURSE OF PERFORMANCE.**
>
> **NO WARRANTY IS MADE THAT THE SOFTWARE IS ERROR-FREE, UNINTERRUPTED, FREE OF HARMFUL COMPONENTS, SUITABLE FOR ANY PARTICULAR PERSON OR INVESTMENT, OR CAPABLE OF PRODUCING ANY FINANCIAL BENEFIT. NO DUTY TO PROVIDE SUPPORT, UPDATES, CORRECTIONS, OR CONTINUED DATA OR SERVICE ACCESS IS UNDERTAKEN EXCEPT UNDER A SEPARATE EXPRESS WRITTEN AGREEMENT.**
>
> **TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, NATHAN SLAUGHTER AND THE COVERED CONTRIBUTORS AND LICENSORS ARE NOT LIABLE FOR LOSSES OR DAMAGES ARISING FROM ACCESS TO, USE OF, RELIANCE ON, OR INABILITY TO USE THE SOFTWARE OR ITS OUTPUTS. THIS LIMITATION INCLUDES DIRECT, INDIRECT, INCIDENTAL, CONSEQUENTIAL, SPECIAL, EXEMPLARY, AND PUNITIVE DAMAGES; INVESTMENT OR TRADING LOSSES; LOST PROFITS, OPPORTUNITIES, SAVINGS, DATA, OR GOODWILL; BUSINESS INTERRUPTION; AND THIRD-PARTY CLAIMS, WHETHER ASSERTED IN CONTRACT, TORT, INCLUDING ORDINARY NEGLIGENCE WHERE LAWFULLY LIMITABLE, STRICT LIABILITY, OR OTHERWISE, EVEN IF THE POSSIBILITY OF SUCH LOSS WAS KNOWN.**
>
> **NOTHING IN THESE TERMS EXCLUDES OR LIMITS LIABILITY, WARRANTIES, REMEDIES, OR RIGHTS THAT APPLICABLE LAW DOES NOT ALLOW TO BE EXCLUDED, LIMITED, OR WAIVED. THIS INCLUDES ANY APPLICABLE NON-WAIVABLE SECURITIES-LAW OR CONSUMER-PROTECTION RIGHTS AND LIABILITY FOR FRAUD, WILLFUL MISCONDUCT, GROSS NEGLIGENCE, OR OTHER CONDUCT TO THE EXTENT ITS EXCLUSION IS PROHIBITED.**

Do not claim these clauses eliminate every possible claim or are enforceable in every jurisdiction. Texas counsel must review conspicuousness, contract formation, treatment of negligence, consumer law, any appropriate fallback liability cap, and the application of sales/warranty law to the actual distribution. Do not invent a monetary cap, arbitration clause, class-action waiver, or indemnity without a separate considered decision.

If the Investment Advisers Act applies, its anti-waiver provision must not be contradicted by a blanket disclaimer. [15 U.S.C. § 80b-15](https://www.law.cornell.edu/uscode/text/15/80b-15)

### 17.6 Publisher's exclusion and actual product behavior

The legal concept to evaluate is the **publisher's exclusion**, not a protection created by writing a disclaimer. The federal definition contains an exclusion for qualifying publications; SEC guidance describes impersonal content, genuine disinterested analysis, and general and regular circulation as relevant requirements. Qualification depends on actual facts and conduct. Software availability and a “not advice” banner do not establish qualification. [15 U.S.C. § 80b-2(a)(11)(D)](https://www.law.cornell.edu/uscode/text/15/80b-2), [SEC publisher-exclusion guidance](https://www.sec.gov/divisions/investment/noaction/2015/jonathon-hendricks-012615-202a.htm)

Texas has its own investment-adviser definition and publisher provision. The state-law and federal analyses must both be reviewed, together with any other applicable jurisdiction; choosing Texas law does not eliminate mandatory laws elsewhere. [Texas Government Code § 4001.059](https://www.ssb.texas.gov/sites/default/files/2025-04/TSAeffective01-01-2022%20%28revised%20copy%29_0.pdf)

Specify these operating safeguards for legal review:

- Present the product as a general research tool with truthful, disinterested methodology and limitations.
- Do not provide individualized buy/sell instructions, suitability assessments, or investment allocations through support or an LLM feature.
- Do not accept trading discretion, custody, or execution authority under the general research license.
- Treat personalized portfolio interpretation, event-driven securities recommendations, paid advisory services, and brokerage connections as new activities requiring separate legal analysis before implementation.
- Review publication practices and any monetization against the actual exclusion criteria. Do not fabricate a publication schedule or assume software release frequency proves general and regular circulation.
- Disclose relevant financial interests, sponsorship, referral compensation, or other conflicts in published material where applicable.
- Keep statistical research criteria distinct from statements that a user should deploy capital.
- Review whether user-parameterized outputs and later research features change the characterization of the product; do not assume automation removes the issue.

Do not state that Nathan Slaughter is registered, exempt, excluded, or immune from liability unless the assertion has been appropriately established. Do not describe this guide as a legal determination.

### 17.7 Legal artifacts and release verification

Prepare LICENSE, CONTACT.md, THIRD_PARTY_NOTICES.md, docs/licensing-policy.md, docs/disclaimers.md, and the licensing ADR. Keep legal rights and financial notices consistent across those files, the README, package metadata, CLI notices, and generated reports.

The final drafting process must address assent, notice delivery, termination for breach, survival of appropriate provisions, severability, written permissions, and changes to future license versions. Texas is the proposed governing-law starting point, subject to mandatory applicable law. Do not invent a county, venue, or legal entity.

Use a separately versioned license identifier and record the applicable license/notice version with artifacts where appropriate. Any acknowledgment should be lightweight and compatible with offline use and automation. Do not add financial-data collection, remote enforcement, or repeated interruption to the first releases without an explicit requirement.

Before public distribution:

1. Confirm final eligibility definitions and the exact permitted individual use.
2. Obtain review of the license, distribution channel, publisher-exclusion analysis, and marketing/product behavior.
3. Confirm Nathan Slaughter has adopted the final text and all contact links work.
4. Verify the license and notices are included in the actual package and reports.
5. Check upstream rights, contributor terms, and any previous license grants.
6. Verify no document, classifier, or badge describes the project as MIT-licensed or OSI-approved open source.
7. Reconcile THIRD_PARTY_NOTICES.md with the resolved dependencies, and meet section 17.8's requirements for any bundled build or container image.

Example eligibility checks for the specification:

| Scenario | Required outcome |
|---|---|
| Individual with US $4 million in liquid assets, researching only personal/family decisions, without the primary-income research-resale criterion | Eligible for the individual grant if all remaining terms are satisfied |
| Individual with exactly US $5 million and neither other criterion | Asset criterion alone does not require professional permission |
| Individual with more than US $5 million, using the tool only personally | Prior express written permission required |
| Individual making investment decisions for an unrelated friend without charging | Prior express written permission required |
| Individual whose primary income is reselling stock research | Prior express written permission required |
| Eligible individual wanting to put modified project code in a public repository or published package | Separate prior express written permission required |
| Professional user who has only emailed a request | No permission until an express written grant is received |
| Separately licensed third-party code obtained independently | Its own license governs; do not claim Nathan controls rights he does not own |

These are specification examples, not a finding that the proposed terms or any automated eligibility mechanism are legally sufficient.

### 17.8 Third-party license obligations and container distribution

Third-party components keep their own licenses. Record each distributed component's name, version, license, and required notices in THIRD_PARTY_NOTICES.md, and regenerate that record from the resolved dependency set for each release. The obligations below were checked on 2026-10-01 against the listed versions; reverify them at release, because licenses and bundled contents can change between versions.

A wheel or source distribution that declares dependencies without bundling them distributes none of their code; installers obtain each dependency from its publisher under its own license. Vendored source, zipapps, frozen executables, notebooks containing copied code, and container images bundle third-party code and trigger the requirements below. Do not apply the project's restrictions to any bundled third-party file.

| Component (version checked) | License | Requirement when bundled |
|---|---|---|
| p123api 3.1.0, pydantic 2.13.5, pydantic-core 2.46.5, annotated-types 0.8.0, typing-inspection 0.4.4, urllib3 2.8.0, charset-normalizer 3.5.2 | MIT | Include each copyright notice and permission notice |
| idna 3.20 | BSD-3-Clause | Reproduce the copyright notice, conditions, and disclaimer; do not use the copyright holders' or contributors' names to endorse or promote the project without permission |
| requests 2.34.2 | Apache-2.0 | Provide the license text and carry the contents of its NOTICE file, currently “Requests / Copyright 2019 Kenneth Reitz”; mark any modified files as changed |
| typing_extensions 4.16.0 | PSF-2.0 | Retain the PSF license agreement and copyright notice; include a summary of changes if modified |
| certifi 2026.7.22 | MPL-2.0 | Its files remain under MPL-2.0; tell recipients where to obtain their source and publish any modifications to those files under MPL-2.0 |

If the p123api pandas extra is adopted, add pandas 3.0.6 (BSD-3-Clause, with vendored components listed in its license file), python-dateutil 2.9.0.post0 (Apache-2.0 for contributions after 2017-12-01 and BSD-3-Clause for all code; satisfy both), six 1.17.0 (MIT), and numpy 2.5.3 (BSD-3-Clause and other permissive licenses). Linux numpy wheels also bundle OpenBLAS and LAPACK (BSD-3-Clause variants), libgfortran (GPL-3.0-or-later with the GCC Runtime Library Exception), and libquadmath (LGPL-2.1-or-later). Keep numpy's bundled license file intact, and make corresponding source for the GCC libraries available as those licenses require when distributing them. The runtime exception permits this combination without applying the GPL to the project's code.

Current wheels ship their license and notice files under `.dist-info`, so a plain installation carries them. Do not strip those directories from a bundled build.

**Container images:** treat any container image as a separate distribution with its own licensing conditions, distinct from the package's. It contains the project's covered code, so publishing it is a reserved distribution under section 17.3 that requires an approved channel and must carry the project's LICENSE, CONTACT.md, and disclaimers. It also contains a base operating system and the Python interpreter, whose licenses the package never carries.

- Provide an image-level notices file covering every component in the image: base-image packages, the Python interpreter (PSF-2.0 plus the components listed in its license), and all installed Python packages, not only direct dependencies.
- Generate that inventory from the built image rather than the dependency declaration, and tie it to the image digest.
- Base images commonly include GPL- and LGPL-licensed programs and libraries, such as the shell and C library. Distributing the image conveys those binaries, so make their corresponding source available as those licenses require. Placing separate programs in one image is aggregation and does not apply their licenses to the project's code. [GNU FAQ on aggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation)
- Do not remove operating-system copyright files or Python `.dist-info` license directories to reduce image size.
- Building or publishing the image from a separate repository or registry does not change these obligations; they follow the image.

### 17.9 Portfolio123 relationship and subscription notices

Place a prominent notice near the top of README.md, before installation instructions, stating that the project requires a Portfolio123 subscription. Do not name a plan, price, or entitlement level unless it has been verified; link to Portfolio123's own information instead of restating it. The README may note that the offline synthetic demo runs without a subscription while that remains true. Proposed text for review:

> **Requires a Portfolio123 subscription.** This project works with Portfolio123 research exports and the Portfolio123 API, which require a Portfolio123 subscription with the appropriate access.

End README.md with a notice stating that the project is not an official Portfolio123 project, has not been reviewed by Portfolio123, and implies no endorsement by Portfolio123. Proposed text for review:

> **Not affiliated with Portfolio123.** This is an independent project. It is not an official Portfolio123 project and has not been reviewed by Portfolio123. No endorsement by Portfolio123 is implied.

Keep both notices consistent with docs/disclaimers.md and the package description. Do not use Portfolio123 logos or styling that suggest an official relationship.

### 17.10 Desktop, local web, and hosted interfaces

Section 9's interface-independent core keeps the code ready for other interfaces. Resolve these licensing and legal conditions before shipping one.

- **Hosting is a reserved use.** Section 17.3 reserves hosted services incorporating the covered code. The final license must state whether an eligible individual may run a web UI or API on their own machine for their own research, and whether family members within the personal-research scope may access it. Do not leave local serving implicit.
- **An author-hosted service needs separate review before launch.** A service producing user-parameterized results for other people is a new activity under section 17.6. It also requires confirming Portfolio123's terms for displaying provider data to other users (section 8) and for handling other users' Portfolio123 credentials.
- **Notices apply on screen.** Treat any screen showing results as a human-facing report under section 12: show the concise financial-result notice and link the full notices. Provide the license acknowledgment in the interface, consistent with section 17.7.
- **Desktop bundles are frozen executables,** so section 17.8's bundling requirements apply to everything packaged, including the interpreter and GUI toolkit. JavaScript dependencies shipped with a web UI also need notices.
- **Choose a GUI toolkit with a compatible license.** As checked on 2026-10-01:
  - PyQt6 is GPL-3.0-only unless a commercial license is purchased. The GPL option is incompatible with this project's license.
  - PySide6 is available under LGPL-3.0. Keep Qt as replaceable shared libraries, give notice of its use, include the LGPL and GPL texts, make Qt's corresponding source available, and ensure the project's terms do not prohibit modifying the Qt portions or reverse engineering to debug such modifications (LGPL-3.0 section 4).
  - Electron is MIT, and Tauri is Apache-2.0 or MIT. Electron also ships Chromium's extensive third-party notices.

Record the interface toolkit and its license review in an ADR.
