# Where Trial Folio is going

Trial Folio grows in releases, each useful on its own. This page gives each release and its status, what the roadmap proposes after them, how their order is chosen, and what Trial Folio won't do.

The roadmap's targets after release 0.4.0 are proposed. They're plans, not commitments: none is a complete specification, and their order has changed before ([how the order is chosen](#how-the-order-is-chosen)). The documents this page links to own everything on it, above all the [roadmap](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md) and each release's file. Where this page and they disagree, they win, and this page is the one to fix.

## What a release's status means

Each release has a file in the repository's `docs/releases/`, and that file's status line is the only record of the release's progress ([how the documents fit together](https://github.com/promptedportfolio/trialfolio/blob/main/docs/README.md#how-the-documents-fit-together)). A release is in one of four statuses:

- **Draft.** Its specification isn't complete. Its dependencies, contracts, evidence, or decisions are still open, and nothing is built from it.
- **Ready.** Its specification is complete, and Trial Folio's owner has signed off on it, so it can be built. It stays Ready while it's built and verified, until the owner has used it privately and sets it to Implemented.
- **Implemented.** It works, it's verified, and the owner has used it privately ([D-08](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)).
- **Released.** It's distributed through the chosen channel, under the adopted license: installable packages, downloaded with the license from the site the README's [installation section](https://github.com/promptedportfolio/trialfolio/blob/main/README.md#installation) names. Trial Folio isn't published on PyPI ([D-22](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)).

Implemented isn't Released. An Implemented release works, but it hasn't been distributed. The public repository doesn't make a release Released ([D-08](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)), and neither does a tag: several releases are tagged, but no release has been distributed yet, so none is Released. Until one is, you run Trial Folio from a copy of its repository, as the [first tutorial](../tutorials/first-backtest.md) shows.

## The releases

These are the releases in `docs/releases/`, with the status each one's status line gives.

| Release | What it adds | Status |
|---|---|---|
| [0.1.0: API execution](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.1.0-api-execution.md) | Runs one screen backtest through the Portfolio123 API, after you approve its plan, and keeps its settings with its results | Implemented, and tagged `v0.1.0` |
| [0.2.0: Review](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.2.0-review.md) | Compares saved runs, offline, against a baseline you choose, and shows exactly what differs | Implemented, and tagged `v0.2.0` |
| [0.2.1: License version 1.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.2.1-license.md) | Changes only the license, to version 1.1. It adds no workflow. | Ready, and tagged `v0.2.1` |
| [0.3.0: Experiments](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md) | Runs a baseline and predefined variants of it as one finite experiment, under one plan and one approval, with resume, and accounts for every planned case | Implemented, and tagged `v0.3.0` |
| [0.4.0: Ranking-weight variants](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.4.0-ranking-weights.md) | Variants that change the weights of a ranking system's nodes, or remove one factor, with every case's ranking definition recorded, and snapshots of a ranking system saved in your account | Ready: its specification is complete, the owner has signed off on it, and its tasks are done, on `main`. It isn't tagged yet. |

Release 0.2.1 is tagged, and each of its release requirements is met, but its status line reads Ready. The owner sets its later statuses.

## What the roadmap proposes next

The roadmap proposes these targets after 0.4.0, in this order. Each is a planning target, not a complete specification, and not an assignment to build it. No release after 0.4.0 is specified yet ([after 0.3.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#after-030)). They put first the evidence that Trial Folio's target user needs ([how the order is chosen](#how-the-order-is-chosen)).

| Target | What it would add |
|---|---|
| 0.5.0: Descriptive return analytics, proposed | Each case's dated return series, as a normalized table, the input every later statistic needs; a fixed, versioned set of descriptive analyses; an explicit comparison with the baseline; and equity and drawdown charts, drawn into the self-contained report, which stays free of scripts. You still run and review experiments from the command line: there's no graphical application. |
| 0.6.0: Statistical evaluation, proposed | Whether a candidate's result holds up under inference that accounts for dependence, and for the search that produced it, rather than reading a backtest's metrics at face value: a study protocol frozen before its evaluation results are seen; uncertainty that allows for dependence, with adjusted and unadjusted values side by side; and, for an experiment treated as a search, diagnostics that account for the selection. An inconclusive result is a valid outcome. |
| 0.7.0: Grid search, proposed | A predefined grid of settings or weights, expanded into listed cases before anything is sent, so the plan shows every case, and the budget covers each, before you approve it; and variants that change several settings. A selection, when an experiment declares one, is a transparent rule declared before the results, reported with 0.6.0's statistics, and never a winner chosen by backtest performance alone. |
| 0.8.0: Robustness and rank diagnostics, proposed | Diagnostics of ranking behavior: bucket performance, and comparisons of ranking definitions, with 0.6.0's inference where its requirements are met |
| 1.0.0: Stable first product, proposed | A supported, statistically sound experiment workflow, with a documented compatibility promise |
| 1.1.0: Forward tracking, proposed | Freezing candidate definitions, recording their selections and signals as time passes, and comparing them with what's observed afterward: the one kind of evidence no backtest can give |
| Reproduction and sensitivity workflow, proposed, with no version | A study's method, deviations, experiments, and findings in one reproducible record, which extends the study record that 0.6.0 defines with its frozen protocol |
| Results workspace, proposed, with no version | A graphical application on your own computer, to browse saved runs and experiments, and see 0.5.0's comparison, charts, and analyses on screen. Running experiments stays in the command line. |
| Graphical experiment workflow, proposed, with no version | Configuring, approving, running, and resuming an experiment without a terminal |

The roadmap's proposed gate for 1.0.0 is one dependable, statistically sound experiment workflow: install and launch Trial Folio; configure a baseline and a finite set of variants, or a grid; review and approve a plan and its budget; run and recover; evaluate a frozen protocol's candidates with 0.6.0's inference, their holdout included; compare and export; and reopen earlier work after an upgrade. Neither a graphical interface, matching DataMiner, nor completing the whole scientific roadmap is enough for 1.0.0 by itself, or needed for it. New research capabilities that keep compatibility can follow as 1.x releases ([readiness for 1.0.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#readiness-for-100)).

## Later increments, without versions

The roadmap also proposes these later increments, with no versions and no fixed order. The manual steps and unanswered questions recorded during studies decide which comes next ([later increments](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#later-increments-selected-by-study-needs)).

- **Simulation review:** inspect a portfolio's implementation: its holdings, transactions, sell rules, turnover, cash, and available performance.
- **Targeted rank inspection, rolling screens, and data access:** explain ranking behavior, inspect selections, test how results depend on the entry date, or get the fields a study lacks.
- **Optional discovery:** generate bounded candidates for development, once evaluation and research history are dependable.

Statistical evaluation and forward tracking were later increments too, until the roadmap gave them versions, 0.6.0 and 1.1.0, on 2026-10-14 ([how the order is chosen](#how-the-order-is-chosen)).

## How the order is chosen

Research workflows come first ([product direction](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#product-direction), [D-23](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). A feature earns its place by helping a researcher answer a stated question, understand a limitation, or remove manual work from a study. Portfolio123's DataMiner helps identify possible tools, but matching its list of operations, or every option, isn't what makes a release, or Trial Folio, complete.

Beyond its owner, Trial Folio is built for the serious researcher who wants statistically sound evaluation of alpha claims: a search that's recorded, inference that accounts for dependence and for that search, and evidence the search never saw ([target user](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#product-direction), [D-42](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). Trial Folio evaluates evidence; it still doesn't judge whether anyone should invest. The target user sets the order of the roadmap's targets, so the targets after 0.4.0 put that researcher's evidence first. Within a target, and among the later increments, the driving use case decides: reproducing published factor research in Portfolio123 ([primary use](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#primary-use)), the kind of study [the research method](the-research-method.md) follows step by step.

The roadmap's other [principles](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#principles) shape each release:

- **Each release is useful on its own.** It stays useful if development pauses for months after it, and it includes its documentation, installation path, verification, and example.
- **A release does less before it defers correctness.** When time is short, its functionality is narrowed. Basic correctness is never deferred, and verification is never skipped to meet an estimate.

Studies refine the later priorities. The roadmap proposes a checkpoint: complete three substantially different reproduction studies, with their evidence and reports assembled in Trial Folio, and record the manual steps that remain ([release planning requirements](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#release-planning-requirements)). It's a planning exercise: not a requirement that their findings be positive, not a statistical validation, and not a gate for 1.0.0.

The order can change. On 2026-10-12 the owner planned ranking-weight variants as 0.4.0, ahead of the results workspace and the graphical experiment workflow, which the roadmap had numbered 0.4.0 and 0.5.0 ([D-34](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). On 2026-10-14 the owner named the user Trial Folio is built for, and reordered the targets after 0.4.0 to put that researcher's evidence first ([D-42](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). Descriptive return analytics became 0.5.0, in the command line's reports, without a graphical application; statistical evaluation became 0.6.0, and grid search 0.7.0; robustness and rank diagnostics moved from 1.1.0 to 0.8.0; and forward tracking, until then a later increment without a version, became 1.1.0. The results workspace and the graphical experiment workflow, which D-34 had numbered 0.5.0 and 0.6.0, moved after the reproduction workflow, without versions. Release 0.4.0's scope didn't change.

The roadmap also defers some things until a study needs them, and lists them in [deferred until a study needs them](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#deferred-until-a-study-needs-them).

## What Trial Folio won't do

The roadmap leaves these out deliberately ([deliberately excluded](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#deliberately-excluded)). Only a later decision could add one. The limits of the whole product are in spec.md's [out of scope](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#out-of-scope) list.

- **Trading and investment advice.** No trading, and no personalized investment advice: Trial Folio is a research tool ([purpose](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#purpose)).
- **Picking a winner.** No unexplained overall score of a strategy's quality, no automatic choice of a winner from backtest performance alone, and no completion status presented as an endorsement to trade. Each assessment stays a separate dimension ([METH-07](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions), [what a backtest can support](what-a-backtest-can-support.md)).
- **DataMiner integration.** No importing results produced elsewhere or DataMiner's configurations, no converting DataMiner's configurations, and no other integration with DataMiner. Trial Folio doesn't import, vendor, bundle, or port DataMiner's or FactorMiner's code either ([REQ-02](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-requirements), [ADR 0005](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0005-build-on-the-portfolio123-api-only.md)).
- **Other data vendors.** FactSet is the only supported vendor. Reconsidering others, Compustat included, would take a new decision by the owner, and an account to test with ([D-16](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)).
- **A hosted service.** No hosted service that produces results for other people. The proposed graphical application would be local, and doesn't imply one.
- **A separate terminal interface.** No text-based interface (TUI) beside the command line and the planned graphical application: interface work goes to the graphical workflow.

## Where it's specified

- [The roadmap](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md): its principles, the proposed targets, the later increments, and what's excluded or deferred.
- The release files: [0.1.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.1.0-api-execution.md), [0.2.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.2.0-review.md), [0.2.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.2.1-license.md), [0.3.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md), and [0.4.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.4.0-ranking-weights.md). Each one's status line is its status.
- [Product direction](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#product-direction), [primary use](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#primary-use), and [out of scope](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#out-of-scope), in spec.md, and its [decisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions): D-08, what Implemented and Released mean; D-22, the distribution channel; D-23, research workflows first; and D-42, the target user, and the order of the targets after 0.4.0.
- [How the documents fit together](https://github.com/promptedportfolio/trialfolio/blob/main/docs/README.md#how-the-documents-fit-together), in the docs map: the four statuses.
