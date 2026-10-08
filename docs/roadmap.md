# Trial Folio roadmap

**Status:** Draft
**Date:** 2026-10-04

This document owns release planning requirements, the proposed sequence, dependencies, the value of each increment, and excluded or deferred scope. It follows [Product direction (D-23)](spec.md#product-direction). It does not track progress. Each release specification's **Status** line is authoritative, and the roadmap only links to it. The roadmap by itself is not an implementation assignment; an agent implements only an assigned release whose specification is Ready.

## Principles

- **Each release is useful on its own.** A release must stay useful if development pauses for months after it. A release includes its documentation, installation path, meaningful verification, and example.
- **Prioritize research workflows.** Remove a substantial manual step from a study, enable a stated research question, or make its evidence more dependable. Use DataMiner capability coverage to identify possible tools, not to decide whether Trial Folio is complete (D-23).
- **Narrow before deferring correctness.** When time is short, the functionality is narrowed; basic correctness is never deferred to a later release.
- **Scope targets are not deadlines.** Estimate work after the release's dependencies and verification are understood. Earlier working-day estimates in the initial specifications are historical scope targets, not the schedule for this roadmap. Verification is never skipped to meet an estimate.
- **Implemented is not Released ([D-08](spec.md#decisions)).** A release is Implemented when it works, is verified, and is used privately by the owner. It becomes Released, meaning publicly distributed, only when it's distributed through the chosen channel under the adopted license ([D-22](spec.md#decisions)). The public repository doesn't make a release Released. The gates are listed in [licensing-policy.md](licensing-policy.md).
- **Reference data is procured when needed ([D-09](spec.md#decisions)).** The verified response layout so far is 0.1.0's screen backtest. The first task of each release that depends on a new provider format is procuring a reference sample with the owner's credentials and approval, and the owner does any Portfolio123 web-UI steps.

## Release planning requirements

When proposing or completing a release specification, record the following before it can become Ready (D-23):

| Planning question | Where the release specification records the answer |
|---|---|
| What research task does this improve, and for whom? | User outcome, with the study or workflow that motivates it |
| What manual work does it remove, question does it enable, or evidence problem does it resolve? | Included scope, with the current limitation and resulting behavior |
| What observable scenario demonstrates that benefit? | Acceptance criteria, paired with verification commands and expected evidence |
| What must be verified or decided first? | Dependencies and open questions, including provider capabilities, data availability, contracts, and applicable methodology |
| What is intentionally left out? | Explicit exclusions, distinguishing this release's limits from product-wide exclusions |

For example, the proposed 0.4.0 scenario is: open a saved experiment, identify the baseline and changed assumptions, inspect results and limitations, and export a comparison without assembling a spreadsheet. The release specification must turn this into testable criteria; this example does not declare any work implemented.

Use actual research to refine subsequent priorities. A proposed product checkpoint is completing three substantially different reproduction studies with their evidence and reports assembled in Trial Folio, then recording the remaining manual steps. This is a planning exercise, not a requirement that their findings be positive, a statistical validation, or an additional 1.0.0 gate. Reference payloads stay local; committed examples and fixtures are synthetic under [REQ-11](spec.md#enduring-requirements).

Release specifications continue to own their scope and status. This planning direction leaves 0.1.0's criteria and the settled scope of 0.2.0 and the 0.3.0 outline intact. Future specifications remain Draft until their dependencies, contracts, acceptance evidence, and owner decisions are resolved.

## Releases 0.1.0 to 0.3.0

| Release | User outcome | Adds | Depends on | Key external dependency |
|---|---|---|---|---|
| [0.1.0 API execution](releases/0.1.0-api-execution.md) | Run one supported screen backtest and keep the link between its settings and results | `p123api` execution with plan and approval, a saved request and response, normalized CSV, a manifest, a self-contained report, and offline re-rendering | None | A working account, one reference response procured under D-09, and a real integration check |
| [0.2.0 Review](releases/0.2.0-review.md) | Compare saved runs against a baseline and see exactly what differs | Offline comparison of saved runs, intended changes separated from unexplained mismatches, `differences.csv`, and a review report | 0.1.0 | None beyond 0.1.0 |
| [0.3.0 Experiments](releases/0.3.0-experiments.md) | Run and review a controlled, finite experiment | A baseline plus predefined variants, stable case and attempt identities, sequential execution, resume, and uncertain-completion handling | 0.2.0 | Verified backend support for each variant type offered |

Release [0.2.1](releases/0.2.1-license.md) changes only the license, to version 1.1 ([D-27](spec.md#decisions)). It adds no workflow.

Later releases keep the 0.1.0 run and report path, and 0.2.0 compares the runs it produces. Trial Folio doesn't import results produced elsewhere ([ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md)). Automatic search, sophisticated scheduling, and statistical acceptance decisions are outside all three.

## After 0.3.0

The following are proposed planning targets, not complete release specifications or implementation assignments. No release after 0.3.0 is specified yet. Keep the sequence useful at every stop; refine scope through the planning requirements above rather than adding features to complete an operation checklist.

| Target | Added research value | Intended scope and important dependencies |
|---|---|---|
| **0.4.0: Results workspace and descriptive return analytics** | Review an archived experiment and produce a comparison without manually assembling tables and charts | A packaged local graphical application; saved-run and experiment browsing; explicit baseline comparison; equity and drawdown charts; a fixed, versioned descriptive analysis set; script-free report export. Execution stays in the CLI. Requires adequate archived series, an early packaging prototype, and the interface decisions below. |
| **0.5.0: Graphical experiment workflow** | Configure, approve, run, and revisit a supported finite experiment without a terminal | Configuration and research-context entry; credentials through a keychain or equivalent; plan and budget review; approval; progress; stopping between cases; safe resume and explicit handling of uncertain completion. Uses the same core, contracts, and saved evidence as the CLI. Specify application shutdown and restart behavior. |
| **1.0.0: Stable first product** | Adopt the supported screen-experiment workflow with a documented compatibility promise | Demonstrate installation, execution, recovery, comparison, export, and reopening historical work through real use on the declared supported platforms. Intentionally declare the public contract stable under [contracts.md](contracts.md#versioning). Readiness details are below. |
| **1.1.0: Robustness and rank diagnostics** | Investigate ranking behavior and sensitivity to predefined changes | Bucket performance, comparisons of ranking definitions, and bounded factor-removal or weight variants. Show every case and its settings, coverage, costs, and limitations. Verify provider semantics and protect shared account state before offering inline definitions or mutations. This adds descriptive diagnostics, not automatic winner selection or a scientific assessment without its required evidence. |
| **Following increment: Reproduction and sensitivity workflow** | Assemble a study's method, deviations, experiments, and findings in one reproducible record | Lightweight exploratory briefs; source-method comparisons; dated decisions and amendments; consistent analysis across cases; a reproduction report; targeted cost, microcap, timing, and other sensitivity checks where supported. Full confirmatory protocols and any verdict remain governed by [METH-01, METH-02, and METH-09](methodology.md). Specify the study contract before implementation. |

### Descriptive analysis before further acquisition

Use the responses preserved by 0.1.0's run path, which the proposed 0.3.0 experiments also use. The verified screen-backtest layout includes per-rebalance-period screen and benchmark returns, turnover, position counts, and daily strategy and benchmark values ([`p123api-screen-backtest` version 1](contracts.md#p123api-screen-backtest-version-1)). The proposed analysis set adds full-period summaries, drawdowns, rolling returns, and period splits where the required dates and series are available. Its methods and versions must be specified before it is applied consistently across studies. It makes no significance claim.

Rolling returns calculated from an archived portfolio series describe that portfolio over different windows. Repeated screen backtests with different entry dates, holding periods, or rebalancing rules answer different questions and may require new provider requests ([METH-09.7](methodology.md#meth-09-reproducing-published-research)). Gross-versus-net analysis also needs verified cost semantics and adequate data; changing execution assumptions may require a full rerun ([METH-06](methodology.md#meth-06-robustness-and-economic-usefulness)). Never reconstruct unavailable evidence from summary metrics.

### Graphical interface prerequisites

The 0.4.0 specification must establish supported platforms and prove a small packaged workflow early: launch, open an archived experiment, display a table and chart, and exit. On 2026-10-07 the owner decided to build that prototype now, alongside 0.3.0's specification work, read-only and outside any release ([D-29](spec.md#decisions), [graphical-prototype.md](graphical-prototype.md)). Experiments don't exist until 0.3.0, so it opens saved runs instead. The target user installs and launches an application without manually starting a server or installing a frontend development toolchain. Toolkit and packaging choices belong in the ADR required by [LIC-17](licensing-policy.md#lic-17-other-interfaces); this roadmap does not select them.

There is a policy conflict to resolve before that specification becomes Ready: [LIC-17](licensing-policy.md#lic-17-other-interfaces) treats any results screen as a human-facing report, while [REQ-08 and D-07](spec.md) and the [report contract](contracts.md#reports) require script-free reports. The recommended resolution is to distinguish the interactive application from exported reports in the owning documents, retain on-screen notices, and keep exports self-contained and script-free. This recommendation does not itself amend those requirements. Distribution and bundled-dependency requirements also remain in [LIC-15 to LIC-17](licensing-policy.md).

### Readiness for 1.0.0

The proposed product gate is one dependable screen-experiment workflow: install and launch; configure a baseline and finite variants; review and approve a plan and budget; execute and recover; compare and export; and reopen historical work after an upgrade. The release specification must define the scenarios and evidence, including incomplete outcomes, on the platforms it promises to support.

Correctness, documentation, and installation are required in every earlier release. The 1.0.0 milestone adds an intentional stability commitment, supported by use of the complete workflow. The [public contract and versioning policy](contracts.md#public-contract-boundary) own that commitment. Neither a graphical interface, DataMiner parity, nor completion of the full scientific roadmap is sufficient or necessary by itself. New compatible research capabilities can follow as 1.x releases.

### Later increments selected by study needs

These remain proposed, without assigned versions or a fixed order. Prioritize the next one using the manual steps and unanswered questions recorded during studies.

| Increment | Added research value | Important dependency |
|---|---|---|
| Simulation review | Inspect the portfolio implementation's holdings, transactions, sell rules, turnover, cash, and available performance | Verified strategy endpoints and output granularity; distinct treatment of signal diagnostics and portfolio results |
| Targeted rank inspection, rolling screens, and data access | Explain ranking behavior, inspect selections, test entry-date sensitivity, or obtain the fields a study lacks | Reference responses for each needed capability, cost semantics, point-in-time handling, and identifiers. Present related rank retrieval as one workflow with dates and systems as choices. |
| Statistical evaluation | Evaluate a frozen claim with justified chronological boundaries, uncertainty, and selection-aware inference | Sufficient data, recorded research history and prior exposure, a frozen protocol, validated methods, and a methods ADR. Recording a study earlier does not satisfy this gate. |
| Forward tracking | Freeze candidate definitions and compare timestamped signals with subsequent observations | Dated definitions, identifier alignment, and return and execution conventions. Start preserving prospective records before making assessments; any later fill import needs an explicit decision under [ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md). |
| Optional discovery | Generate bounded development candidates when evaluation and history are dependable | Protected-data boundaries, complete proposal and selection history, finite budgets, and the model backends of [REQ-10](spec.md#enduring-requirements). The prohibition on importing, vendoring, bundling, or porting DataMiner or FactorMiner code remains (REQ-02). |

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
| Settings compared, with intended changes separated from unexplained mismatches | 0.2.0 | The first step toward a deviation record against the paper |
| Deviation record against the paper's method | Reproduction and sensitivity workflow | Bring study records forward without claiming statistical evaluation; their scientific meaning remains in [METH-09](methodology.md#meth-09-reproducing-published-research) |
| Preregistered plan: purpose, planned cases, declared prior research | 0.3.0 (plan and purpose); Reproduction and sensitivity workflow (study record); Statistical evaluation (full confirmatory use) | The approved plan hash records cases declared before execution. Every confirmatory protocol must be frozen before protected outcomes are exposed. |
| Full universe versus excluding microcaps | 0.3.0, if universe variants are verified backend capabilities | Otherwise, the next increment that verifies them |
| Stable-identifier universe slices | 0.3.0, if universe rules can express them | Slices share dates and are not independent confirmations (METH-09) |
| Paper's rebalance versus practitioner screen with a rank-drop sell rule | 0.3.0 for rebalance variants; Simulation review for sell rules | Sell-rule support in screen backtests is unverified |
| Gross and net of declared costs | 0.1.0 (recorded settings); Reproduction and sensitivity workflow (paired analyses) | Requires verified cost semantics and adequate data or reruns; repricing a trade list is not a rerun (METH-06) |
| Rolling returns over several holding periods | 0.4.0 Descriptive return analytics (proposed) | Needs dated return series in the saved responses; distinct from repeated entry-date backtests |
| Quantile-bucket returns and top-minus-bottom spread | 1.1.0 Robustness and rank diagnostics (proposed) | Verify the provider execution path, bucket membership, weighting, and cost semantics before any quantile claim |
| Period splits around the paper's sample and publication | 0.4.0 Descriptive return analytics where dates are supplied; Reproduction and sensitivity workflow for the study context | Descriptive only until Statistical evaluation; prior exposure remains explicit |
| Model-drafted setups logged with first output unedited | Optional discovery | METH-08 |

## Scope choices

### Deliberately excluded

- Importing outside results or DataMiner configurations, converting DataMiner configurations, or any other DataMiner integration. Importing, vendoring, bundling, or porting DataMiner or FactorMiner code is also excluded ([REQ-02](spec.md#enduring-requirements), [ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md)).
- Data vendors other than FactSet, including Compustat ([D-16](spec.md#decisions)). Reconsidering this needs a new owner decision and an account to test with.
- A separate TUI alongside the CLI and planned graphical application. The current direction concentrates interface work on the graphical workflow.
- An unexplained aggregate strategy-quality score, automatic winner selection based only on backtest performance, or a completion status presented as an endorsement to trade. Assessments remain separate dimensions under [METH-07](methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions).
- Trading or personalized investment advice, as stated in [Purpose](spec.md#purpose).
- A hosted service producing results for other people, unless separately adopted under [spec.md](spec.md#out-of-scope) and [LIC-17 and LIC-18](licensing-policy.md). The proposed local application does not imply a hosted service.

### Deferred until a study needs them

- Comprehensive bulk downloads, exhaustive provider-option coverage, and elaborate visual ranking-system editing. Add targeted data access and settings to answer a concrete study need first; do not promise a parity release.
- Parallel or scheduled execution, additional providers such as Tiingo, and storage changes such as Parquet or a SQLite index.
- Adaptive optimization, automatic candidate generation, and runtime LLM features until the evaluation boundaries and research history they require are dependable.

The graphical workflow, descriptive analysis, rank diagnostics, and reproduction workflow have proposed targets above. Simulation review, statistical evaluation, forward tracking, and targeted provider operations remain later increments whose order follows study needs. No scientific or deployment assessment ships before its methodology requirements are satisfied.

## Open questions

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| Which variant types can 0.3.0 offer? | 0.3.0 scope | Only the types whose backend support is recorded with integration evidence in 0.2.0 or 0.3.0 | 0.3.0 specification Ready |
| Which platforms and application toolkit will the first graphical release support? | Installation, packaging, distribution, and maintenance | Prove a small packaged workflow on the initial supported platform set, starting with the prototype of [D-29](spec.md#decisions); record the toolkit and license review in the LIC-17 ADR | 0.4.0 specification Ready |
| How do interactive results screens differ from exported reports under REQ-08, D-07, and LIC-17? | The proposed UI conflicts with the current script-free rule if every screen is a report | Amend the owning documents to distinguish application code from exports, retaining on-screen notices and script-free exports | 0.4.0 specification Ready |
| Which analyses can 0.4.0 compute from archived responses, and what extra study inputs do they need? | Honest coverage and a consistent analysis set | Define and version the supported calculations; label missing inputs and defer analyses that require new acquisition | 0.4.0 specification Ready |
| Which provider path and settings support bucket and ranking-variant studies safely? | Semantics, credit budget, and shared account state | Verify with approved reference calls before specifying support; do not infer an endpoint from a DataMiner operation name | 1.1.0 specification Ready |
| Once studies exist, which record owns the search history: the study, whose search-history status [METH-03.4](methodology.md#meth-03-research-history-and-multiple-testing) requires, or each experiment, whose `prior_research` declaration has used the same statuses since 0.3.0 ([experiment configuration](contracts.md#prior-research))? | A study made of several experiments could hold several statuses for one idea, and a later count of the search could miss or repeat work | The study owns its search-history status. Each experiment's declaration stays as it was declared, and is part of the history the study records. | Reproduction and sensitivity workflow specification Ready |
| How is a case's role in the search recorded: a predefined perturbation of a candidate, a distinct candidate, or a perturbation whose outcome chose a candidate? [METH-03.2](methodology.md#meth-03-research-history-and-multiple-testing) counts these separately, and an experiment's records don't say which a case is. | Multiple-testing counts, and whether a variant is robustness evidence for the candidate it helped choose ([METH-03.3](methodology.md#meth-03-research-history-and-multiple-testing)) | Through 0.3.0, every variant is a predefined perturbation of the baseline's candidate, as [METH-06.1](methodology.md#meth-06-robustness-and-economic-usefulness) lists them, so an experiment has one candidate. A study records each selection a case's outcome informed, naming the cases, which then count as part of the search. Nothing is inferred from a variant's type. | Reproduction and sensitivity workflow specification Ready |
| Which actual studies should determine later priorities? | The next useful increment after the reproduction workflow | Record substantially different study scenarios and their remaining manual steps, then choose the next capability from that evidence | Before assigning the next later increment |
