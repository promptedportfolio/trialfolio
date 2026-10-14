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
| [0.4.0: Ranking-weight variants](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.4.0-ranking-weights.md) | Variants that change the weights of a ranking system's nodes, or remove one factor, with every case's ranking definition recorded, and snapshots of a ranking system saved in your account | Ready: its specification is complete, and it isn't built yet |

Release 0.2.1 is tagged, and each of its release requirements is met, but its status line reads Ready. The owner sets its later statuses.

## What the roadmap proposes next

The roadmap proposes these targets after 0.4.0. Each is a planning target, not a complete specification, and not an assignment to build it. No release after 0.4.0 is specified yet ([after 0.3.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#after-030)).

| Target | What it would add |
|---|---|
| 0.5.0: Results workspace and descriptive return analytics, proposed | A graphical application on your own computer, to browse saved runs and experiments, compare them, and see charts and descriptive analyses |
| 0.6.0: Graphical experiment workflow, proposed | Configuring, approving, running, and resuming an experiment without a terminal |
| 1.0.0: Stable first product, proposed | The screen-experiment workflow, with a documented compatibility promise |
| 1.1.0: Robustness and rank diagnostics, proposed | Descriptive diagnostics of ranking behavior: bucket performance, and comparisons of ranking definitions |
| Reproduction and sensitivity workflow, proposed, with no version | A study's method, deviations, experiments, and findings in one reproducible record |

Neither a graphical interface, matching DataMiner, nor completing the whole scientific roadmap is enough for 1.0.0 by itself, or needed for it. New research capabilities that keep compatibility can follow as 1.x releases ([readiness for 1.0.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#readiness-for-100)).

## Later increments, without versions

The roadmap also proposes these later increments, with no versions and no fixed order. The manual steps and unanswered questions recorded during studies decide which comes next ([later increments](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#later-increments-selected-by-study-needs)).

- **Simulation review:** inspect a portfolio's implementation: its holdings, transactions, sell rules, turnover, cash, and available performance.
- **Targeted rank inspection, rolling screens, and data access:** explain ranking behavior, inspect selections, test how results depend on the entry date, or get the fields a study lacks.
- **Statistical evaluation:** evaluate a frozen claim, with justified chronological boundaries, uncertainty, and inference that accounts for selection. It needs a frozen protocol and validated methods first.
- **Forward tracking:** freeze candidate definitions, and compare their timestamped signals with what's observed afterward.
- **Optional discovery:** generate bounded candidates for development, once evaluation and research history are dependable.

## How the order is chosen

Research workflows come first ([product direction](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#product-direction), [D-23](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). A feature earns its place by helping a researcher answer a stated question, understand a limitation, or remove manual work from a study. Portfolio123's DataMiner helps identify possible tools, but matching its list of operations, or every option, isn't what makes a release, or Trial Folio, complete.

The roadmap's other [principles](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#principles) shape each release:

- **Each release is useful on its own.** It stays useful if development pauses for months after it, and it includes its documentation, installation path, verification, and example.
- **A release does less before it defers correctness.** When time is short, its functionality is narrowed. Basic correctness is never deferred, and verification is never skipped to meet an estimate.

Studies decide the later priorities. The roadmap proposes a checkpoint: complete three substantially different reproduction studies, with their evidence and reports assembled in Trial Folio, and record the manual steps that remain ([release planning requirements](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#release-planning-requirements)). It's a planning exercise: not a requirement that their findings be positive, not a statistical validation, and not a gate for 1.0.0.

The order can change. On 2026-10-12 the owner planned ranking-weight variants as 0.4.0, ahead of the results workspace and the graphical experiment workflow, which the roadmap had numbered 0.4.0 and 0.5.0 ([D-34](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)).

Some things wait until a study needs them ([deferred until a study needs them](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#deferred-until-a-study-needs-them)):

- comprehensive bulk downloads, every provider option, and elaborate visual editing of ranking systems;
- parallel or scheduled execution, other providers, such as Tiingo, and other storage, such as Parquet or a SQLite index;
- adaptive optimization, automatic generation of candidates, and LLM features at runtime, until the evaluation boundaries and research history they need are dependable.

## What Trial Folio won't do

Trial Folio leaves these out deliberately. Only a later decision, after the analysis it needs, could add one ([out of scope](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#out-of-scope), [deliberately excluded](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#deliberately-excluded)).

- **Investment advice.** No personalized investment advice, suitability assessments, or allocations for any person.
- **Trading.** No trade execution, custody, discretion over accounts, or connections to a broker.
- **Picking a winner.** No unexplained overall score of a strategy's quality, no automatic choice of a winner from backtest performance alone, and no completion status presented as an endorsement to trade. Each assessment stays a separate dimension ([METH-07](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions), [what a backtest can support](what-a-backtest-can-support.md)).
- **DataMiner integration.** No importing results produced elsewhere, or DataMiner's exports or configurations, no converting DataMiner's configurations, and no other integration with DataMiner. Trial Folio doesn't import, vendor, bundle, or port DataMiner's or FactorMiner's code either ([REQ-02](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-requirements), [ADR 0005](https://github.com/promptedportfolio/trialfolio/blob/main/docs/adrs/0005-build-on-the-portfolio123-api-only.md)).
- **Other data vendors.** FactSet is the only supported vendor. Reconsidering others, Compustat included, would take a new decision by the owner, and an account to test with ([D-16](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)).
- **A hosted service.** No hosted service that produces results for other people. The proposed graphical application would be local, and doesn't imply one.
- **A separate terminal interface.** No text-based interface (TUI) beside the command line and the planned graphical application: interface work goes to the graphical workflow.
- **Autonomous strategy discovery in the first releases.** Optional discovery is one of the [later increments](#later-increments-without-versions), once evaluation and research history are dependable.

## Where it's specified

- [The roadmap](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md): its principles, the proposed targets, the later increments, and what's excluded or deferred.
- The release files: [0.1.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.1.0-api-execution.md), [0.2.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.2.0-review.md), [0.2.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.2.1-license.md), [0.3.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md), and [0.4.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.4.0-ranking-weights.md). Each one's status line is its status.
- [Product direction](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#product-direction) and [out of scope](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#out-of-scope), in spec.md, and its [decisions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions): D-08, what Implemented and Released mean; D-22, the distribution channel; and D-23, research workflows first.
- [How the documents fit together](https://github.com/promptedportfolio/trialfolio/blob/main/docs/README.md#how-the-documents-fit-together), in the docs map: the four statuses.
