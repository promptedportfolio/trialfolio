# Trial Folio product specification

**Status:** Draft
**Date:** 2026-10-04
**Owner:** Nathan Slaughter

This document owns Trial Folio's purpose, vocabulary, enduring invariants, enduring product requirements, and the record of owner decisions. Release scope lives in [releases/](releases/), interface semantics in [contracts.md](contracts.md), research design in [methodology.md](methodology.md), and legal terms in [../LICENSE](../LICENSE) and [licensing-policy.md](licensing-policy.md). Release 0.1.0's implementation tasks are done; [AGENTS.md](../AGENTS.md) gives its current state.

Requirement keywords follow the [spec authoring guide](spec-authoring-guide.md#2-interpret-requirements-and-uncertainty-consistently): MUST for required behavior, SHOULD for a default whose exceptions need a documented reason, MAY for optional behavior.

## Purpose

Trial Folio is a configuration-driven command-line tool for collecting, comparing, reproducing, and eventually evaluating investment-strategy evidence from Portfolio123 with scientific discipline. It reuses Portfolio123's research engines and its official Python wrapper. Its own contribution is controlled experimentation, durable evidence, transparent comparisons, and defensible evaluation.

Trial Folio is a research tool. It does not give investment advice, place trades, or judge whether anyone should invest.

## Primary use

The driving use case is reproducing published factor research in Portfolio123. A study takes a paper's factors, rebuilds them as Portfolio123 screens and ranking systems, and records what could and could not be reproduced. That work sets these needs, which the roadmap addresses in order:

- Preregistration: the protocol is recorded before any test, and later changes are dated amendments.
- Every study and case is kept and reported, whether or not it reproduces.
- A deviation record compares each setting with the paper's.
- Fixed variants: the paper's construction on the full universe and without microcaps, a practitioner screen variant, and stable-identifier universe slices.
- Results gross and net of declared costs, rolling returns over several holding periods, quantile-bucket returns, and period splits around the paper's sample and publication dates.

[methodology.md](methodology.md) (METH-09) defines the scientific meaning of these needs. [roadmap.md](roadmap.md) shows which increment delivers each one. Trial Folio stays general enough for other strategy research, but when priorities conflict, this use case decides.

## Product direction

**Requirement (D-23).** Prioritize complete research workflows. A feature earns its place by helping a researcher answer a stated question, understand a limitation, or remove manual work from a study. DataMiner's capabilities are a reference for provider operations; matching its operation list or every option is not a release or product-completion criterion.

As the product grows, organize work around the study, its experiments, and its evidence. Keep the question, baseline, known prior research, changes, and findings connected. Provider operations are steps within that workflow. Exploratory work can begin with a lightweight brief; reproduction studies and confirmatory claims still require their respective protocols and evidence under [METH-09 and METH-01 to METH-04](methodology.md).

Favor consistent analysis of archived evidence, explanations of differences and missing data, predefined sensitivity experiments, and records of how a reproduction departs from its source. Preserve failed and inconclusive work. Additional data access, provider options, and discovery tools are prioritized when a study needs them. Scientific assessments remain subject to their methodology requirements; a more convenient interface does not establish validation.

The [roadmap](roadmap.md) owns the sequence, exclusions, and [release planning requirements](roadmap.md#release-planning-requirements). Each release specification turns that direction into observable acceptance criteria. Application 1.0.0 follows the [public-contract stability policy](contracts.md#versioning); adding a graphical interface alone does not satisfy it.

## Users and outcomes

| ID | User outcome | First delivered |
|---|---|---|
| OUT-01 | Run one supported screen backtest and keep the link between its settings and results | [0.1.0](releases/0.1.0-api-execution.md) |
| OUT-02 | Compare saved runs against a baseline, and see exactly what differs | [0.2.0](releases/0.2.0-review.md) |
| OUT-03 | Run and review a finite, controlled experiment in which every planned case is accounted for | [0.3.0](releases/0.3.0-experiments.md) |
| OUT-04 | Evaluate a strategy against a predeclared objective with honest statistics and robustness evidence | [Roadmap](roadmap.md#after-030) |
| OUT-05 | Compare timestamped signals and modeled execution with later observed results | [Roadmap](roadmap.md#after-030) |

The first user is the owner, an individual investor with a Portfolio123 subscription and API access. Later users are other eligible individuals under the [license](../LICENSE).

Trial Folio eventually supports two kinds of research objective. The first is performance above a suitable benchmark after specified costs. The second is attractive standalone returns and risk. Each confirmatory study MUST choose one primary objective, with its decision criteria, before its evaluation results are seen. Reporting both kinds of result does not permit choosing whichever one passes ([METH-01](methodology.md)).

## Vocabulary

| Term | Meaning |
|---|---|
| Study | A research question, objective, data boundaries, search history, and evaluation protocol |
| Experiment | A declared collection of cases addressing one question |
| Case | One resolved configuration or candidate strategy within an experiment |
| Candidate | A strategy specification considered during research; it can appear in several cases |
| Attempt | One execution or acquisition attempt for a case |
| Artifact | Saved input, output, metadata, or derived evidence |
| Assessment | A versioned interpretation of artifacts using specified methods |
| Report | A presentation of an assessment and its evidence |
| Baseline | The run or case that other runs or cases are compared against, chosen explicitly |
| Provenance | Where a value came from and how confident Trial Folio is in it: verified, user-supplied, inferred, or unknown |

These distinctions hold even where an early release uses fewer objects. A retry is an attempt, not a new strategy hypothesis. The number of provider requests is not the size of a multiple-testing family.

## Enduring invariants

These hold in every release that touches the relevant data. Release specifications cite them by ID.

| ID | Invariant |
|---|---|
| INV-01 | Preserve all collected and evaluated evidence within retention rights, including failed, rejected, and abandoned research cases where known. |
| INV-02 | Preserve source provenance, and distinguish verified metadata, user-supplied metadata, inferred values, and unknowns. |
| INV-03 | Never silently replace unavailable information with zero or a favorable default. |
| INV-04 | Keep source responses separate from normalized data and calculated results. |
| INV-05 | Regenerate analysis and reports from archived artifacts without acquiring fresh provider data. |
| INV-06 | Record the inputs, implementation version, and method settings behind every calculated result. |
| INV-07 | Account for every planned case, including skipped, failed, incomplete, and uncertain attempts. |
| INV-08 | Make the settings, actual coverage, costs, and limitations of every comparison visible. |
| INV-09 | Record research history before implementing statistical corrections. |
| INV-10 | Make scientific and trading-readiness claims only when their stated evidence requirements have been met. |
| INV-11 | Keep credentials out of artifacts, logs, fixtures, and reports. |
| INV-12 | Keep historical artifacts readable as the application evolves. |
| INV-13 | Preserve the author's licensing restrictions, attribution, financial-result notices, and applicable third-party rights. |
| INV-14 | Keep logs, traces, and diagnostics on the machine or container that produced them, and never transmit user inputs or outputs except in provider requests the user invokes or explicitly enables. |

"All evidence" means all material retrieved and evaluated, plus known acquisition failures and unavailable fields. It does not imply access to proprietary provider databases or to outputs the API cannot return. An imported CSV cannot recover the raw API responses behind it.

## Enduring requirements

| ID | Requirement | Owner document |
|---|---|---|
| REQ-01 | Trial Folio MUST be implemented in Python, using Pydantic v2 at serialized boundaries and `typing.Protocol` for narrow behavioral interfaces. Releases 0.1.0 to 0.3.0 MUST NOT require an LLM API or any language other than Python. | [ADR 0001](adrs/0001-python-and-portfolio123-integration.md), [ADR 0002](adrs/0002-pydantic-contracts-and-protocols.md) |
| REQ-02 | The official `p123api` wrapper MUST be the only Portfolio123 code dependency, and the only way Trial Folio obtains Portfolio123 results. DataMiner and FactorMiner code MUST NOT be imported, vendored, bundled, or ported, and Trial Folio does not integrate with DataMiner. | [ADR 0001](adrs/0001-python-and-portfolio123-integration.md), [ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md) |
| REQ-03 | The application core MUST be independent of the CLI. Core functions accept validated models and return result models. They do not print, prompt, parse arguments, exit, read environment variables, or read secrets. | [contracts.md](contracts.md#interface-independent-core) |
| REQ-04 | No charged or mutating provider request may run without an approved plan identified by its hash. | [contracts.md](contracts.md#plans-and-approval) |
| REQ-05 | All artifact reads and writes MUST go through the `ArtifactStore` interface, with paths recorded relative to the run root. | [contracts.md](contracts.md#artifact-storage) |
| REQ-06 | Logs are diagnostics, not evidence. They MUST stay local, MUST NOT contain credentials, strategy definitions, formulas, configuration values, provider payloads, results, or imported file contents, and MUST NOT be the only record of an outcome. | [contracts.md](contracts.md#logging-and-local-diagnostics) |
| REQ-07 | Application releases and artifact schemas MUST each use `<major>.<minor>.<patch>` semantic versioning, independently of each other. | [contracts.md](contracts.md#versioning) |
| REQ-08 | Every human-facing report MUST be self-contained, contain no scripts or external resources, show the concise financial-result notice, and label unavailable sections as unavailable instead of inventing them. | [contracts.md](contracts.md#reports), [disclaimers.md](disclaimers.md) |
| REQ-09 | Credentials MUST come from an injected source: environment variables for the CLI, and a keychain or equivalent for any later desktop interface. | [contracts.md](contracts.md#credentials) |
| REQ-10 | Runtime LLM features, when added, MUST support Anthropic, OpenAI, and local-model backends behind one narrow protocol. They MUST be disabled by default, installed as optional extras, and disclosed before the first request of a run. | [roadmap.md](roadmap.md#after-030), [methodology.md](methodology.md) (METH-08) |
| REQ-11 | Raw provider data MUST NOT be committed or published unless the provider's terms are confirmed to permit it. Committed fixtures are synthetic by default, and each records its origin and redistribution status. | [contracts.md](contracts.md#fixtures) |
| REQ-12 | README.md MUST carry the Portfolio123 subscription notice near the top and the non-affiliation notice at the end. | [disclaimers.md](disclaimers.md) |
| REQ-13 | Process success MUST be kept separate from any statement about a strategy's usefulness. A green completion status must not look like an endorsement to trade. | [contracts.md](contracts.md#reports), [methodology.md](methodology.md) (METH-07) |

## Owner decisions and defaults

Decisions are the owner's. Proposed defaults stand until changed before the implementation or study that depends on them. A default that a release's sign-off confirms becomes a requirement, and its row says so. Change a row by editing it and noting the date; record significant reversals in an ADR.

### Decisions

| ID | Decision | Label | Date |
|---|---|---|---|
| D-01 | The product is **Trial Folio**. The repository and CLI command are `trialfolio`. The Python distribution and import package are `trialfolio`; PyPI availability is unchecked. | Requirement. The package name, proposed until then, was confirmed at 0.1.0's sign-off (2026-10-01). | 2026-10-01 |
| D-02 | Python, Pydantic v2, and `typing.Protocol`. Tooling follows the owner's other repositories: Python 3.12 or later, `uv`, and pytest. | Requirement. The tooling, proposed until then, was confirmed at 0.1.0's sign-off (2026-10-01). | 2026-10-01 |
| D-03 | The project's own material is licensed under the custom, source-available Nathan Slaughter Personal Research License. Nathan Slaughter adopts it himself; counsel review is not a condition of adoption or release. | Requirement | 2026-10-01 |
| D-04 | Licensing contact: Nathan Slaughter, git@nathanslaughter.com. The same address takes every other kind of contact ([CONTACT.md](../CONTACT.md)). | Requirement. The address changed on 2026-10-02. | 2026-10-01 |
| D-05 | Texas governing law, subject to mandatory applicable law. | Requirement | 2026-10-01 |
| D-06 | Professional User definitions: liquid assets exclude retirement accounts; "primary source of income" means more than half of total income; "family members" has no defined list. | Requirement | 2026-10-01 |
| D-07 | Reports contain no scripts, count as output rather than covered code, and may be shared with the concise notice intact. Users remain responsible for data-provider terms. | Requirement | 2026-10-01 |
| D-08 | A release is Implemented when it works, is verified, and is used privately. It is Released only when it's distributed through the chosen channel (D-22) under the adopted license. The repository is public separately from any release: public source isn't a release. | Requirement. Reworded on 2026-10-02, when the owner decided to make the repository public ([ADR 0007](adrs/0007-host-the-source-publicly-on-github.md)). It was made public on 2026-10-04. | 2026-10-01 |
| D-09 | The owner keeps Portfolio123 API credentials in a secret manager. Reference data is procured with them when a release needs it, as R01-T01 and R01-T05 did for 0.1.0, and the owner performs Portfolio123 web-UI steps on request. | Requirement | 2026-10-01 |
| D-10 | Trial Folio is the engine for reproducing published factor research. Project materials do not name any publication, brand, or series, with three exceptions: the README's one-line credit to the owner's brand, with a link to its site; the site's address where installation instructions or package links need it (D-22); and the repository's own URL, which contains the brand's name, where a link needs it (D-21). | Requirement. The exceptions were added on 2026-10-02. | 2026-10-01 |
| D-11 | Development workflow: feature branches named `<type>/<short-description>`, pull requests, squash merges with conventional-commit titles, and merges only by the owner. Git hooks in `.githooks/`, adapted from the owner's other repositories, enforce it. | Requirement | 2026-10-01 |
| D-12 | The [spec authoring guide](spec-authoring-guide.md) is bootstrap context. Accepted requirements in the documents that own them take precedence over it. | Requirement | 2026-10-01 |
| D-13 | "Resells research" in the Professional User income criterion includes research the individual produced, not only research obtained from others. | Requirement | 2026-10-01 |
| D-14 | Outputs other than reports, such as normalized CSV files and manifests, may be shared on the same terms as reports. Data-provider terms still apply. | Requirement | 2026-10-01 |
| D-15 | An eligible individual's family members may use an interface that individual runs on a machine they control, for personal research. Access by anyone else is a hosted service needing written permission. | Requirement | 2026-10-01 |
| D-16 | FactSet, Portfolio123's standard data, is the only supported data vendor. An omitted vendor setting is left out of the request and recorded as FactSet, an inferred default. An explicit `FactSet` is accepted and recorded the same way, but not sent, because the endpoint documents no vendor parameter. The screen-backtest response doesn't report the vendor, so it stays inferred. Compustat is out of scope: Trial Folio provides no facilities for it and does not test it. | Requirement | 2026-10-01 |
| D-17 | License acknowledgment: a one-time local acknowledgment for each license and notice version, with non-interactive options for automation, as [contracts.md](contracts.md#license-acknowledgment) specifies. It is a notice, not an eligibility check. | Requirement | 2026-10-01 |
| D-18 | Build on the Portfolio123 API only. Trial Folio does not integrate with DataMiner. Release 0.1.0 runs a screen backtest through the API, 0.2.0 reviews saved runs, and 0.3.0 runs experiments ([ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md)). | Requirement | 2026-10-01 |
| D-19 | Universes have no default. Every configuration names its universe explicitly. To try another universe, run a separate configuration. No release through 0.3.0 varies the universe within one run or experiment. | Requirement | 2026-10-01 |
| D-20 | A release accepts only the setting values a recorded live call has verified. Release 0.1.0 verifies 1-week rebalancing, ranking by name, and ranking by ID, each in its own call, under a budget the owner approves. Other values are verified when a release needs them; for experiments, that's in R03-T01. | Requirement | 2026-10-01 |
| D-21 | Reports link to two pages outside themselves: the LICENSE published with the Trial Folio version that rendered them, and Portfolio123's terms. Next to the full notice, they carry a statement that Trial Folio's license grants no rights to Portfolio123 data and that the user is responsible for following Portfolio123's terms ([DSC-06](disclaimers.md#dsc-06-portfolio123-notices)). The links load nothing, so reports stay self-contained (D-07). The LICENSE link works once the repository is public and the version is tagged. This settles the open question of a public license link ([DSC-03](disclaimers.md#dsc-03-where-notices-appear)). | Requirement | 2026-10-02 |
| D-22 | Distribution channel ([ADR 0007](adrs/0007-host-the-source-publicly-on-github.md)). The source is public on GitHub, under LICENSE section 5.4's narrow exception for viewing and forking there. Installable packages are downloaded from the brand's site, delivered with LICENSE. Trial Folio isn't published on PyPI, whose terms grant redistribution rights the license reserves. A Homebrew tap may follow, pointing at the site's archive, without prebuilt bottles. Outside contributions aren't accepted until contributor terms exist ([LIC-14](licensing-policy.md#lic-14-contributions)). | Requirement | 2026-10-02 |
| D-23 | Prioritize complete research workflows under [Product direction](#product-direction). DataMiner capability coverage is a reference, not a release or product-completion criterion. Release planning must demonstrate the research benefit using the [roadmap's requirements](roadmap.md#release-planning-requirements). | Requirement | 2026-10-04 |
| D-24 | CLI commands are verbs, and a configuration file states its own kind. `trialfolio run <config> --out <dir>` plans, approves, and executes every configuration that sends requests to Portfolio123, choosing what to do by its `kind`: a screen from 0.1.0, and an experiment from 0.3.0, in place of a separate `trialfolio experiment` command. So the command that may cost credits is always `run`, and no other command sends anything. Running an experiment's configuration again into its own output directory resumes it, as [release 0.3.0](releases/0.3.0-experiments.md) specifies. | Requirement | 2026-10-04 |
| D-25 | Release [0.2.0](releases/0.2.0-review.md)'s specification, signed off by the owner, changes these parts its outline settled: a review copies each run's `plan.json` with its manifest and normalized tables; a `run` directory that doesn't exist fails with `input.not_found`, exit 3; a failure or interrupt after a review claims its output directory leaves no review manifest; and R02-AC15 to R02-AC19 are added. It also changes what 0.1.0 built: every command writes JSON summary 1.1.0, so 0.1.0's check of R01-AC18 moves to it, while the 1.0.0 schema stays committed with its bytes unchanged; and the `ArtifactStore` logs a review's copies by their result's position, never their label ([the owner's sign-off](releases/0.2.0-review.md#the-owners-sign-off)). | Requirement | 2026-10-05 |
| D-26 | The package's version becomes a release's version once that release's specification tasks are done, so `trialfolio --version`, and every artifact written from `main` after that, give it. The task that completes the specification sets it in `pyproject.toml`. A release's tag, `v` plus its version, goes on the commit it's released from, which may be older than `main`'s head once the next release's specification is complete. 0.2.0's specification tasks were done on 2026-10-05, so R02-T10 set the version to 0.2.0 ([versioning](contracts.md#versioning)). | Requirement | 2026-10-06 |

### Proposed defaults

| ID | Topic | Default | Resolve by |
|---|---|---|---|
| P-01 | Initial strategy scope | Long-only stock screens | Requirement since 0.1.0's sign-off (2026-10-01) |
| P-02 | First provider response | One verified `p123api` screen-backtest response layout, procured under D-09 | Met by R01-T01 and R01-T05 ([0.1.0](releases/0.1.0-api-execution.md)) |
| P-03 | Schema maintenance | Pydantic models generate versioned JSON Schemas | Requirement since 0.1.0's sign-off (2026-10-01) |
| P-04 | Storage | Local immutable source artifacts, JSON metadata, CSV normalized output | Requirement since 0.1.0's sign-off (2026-10-01) |
| P-05 | Execution | Sequential, finite, explicit cases | 0.2.0 and 0.3.0 |
| P-06 | Benchmark, capital, costs, risk limits | Explicit study inputs; no universal settings | Before the relevant assessment |
| P-07 | Statistical threshold and method | Family-wise 5% level with a method justified in a methods ADR; not a product-wide constant | Methods ADR and study protocol |
| P-08 | Historical split | Chronological, justified by data, horizon, prior exposure, and power | Before evaluation data is exposed |
| P-09 | Runtime LLM use | Optional, deferred, bounded to development data | Optional discovery increment |
| P-10 | Public sample data | Clearly labeled synthetic fixtures | Requirement since 0.1.0's sign-off (2026-10-01) |
| P-11 | Logging | Python's standard `logging`, JSON lines to a local file, human-readable messages on stderr | Requirement since 0.1.0's sign-off (2026-10-01) |
| P-12 | Test runner | pytest, with network access blocked in the default suite | Requirement since 0.1.0's sign-off (2026-10-01) |
| P-13 | Default variant set | Applies to experiments and studies, except paper reproductions, which follow [METH-09.4](methodology.md#meth-09-reproducing-published-research). Periods of 1 week and 4 weeks for screen rebalancing (`rebalance_weeks`), rank performance, and simulation rebalancing. For simulations, sell rules at rank 99 and rank 95 (see the open question on their definition). Defaults apply per setting: values the configuration lists for a setting replace that setting's defaults, and an empty list turns them off. A default identical to the baseline is skipped, so it never adds a duplicate case. Every variant case is recorded in the research history. A variant whose outcome chooses a candidate is part of the search ([METH-03.3](methodology.md#meth-03-research-history-and-multiple-testing)). | 0.3.0 for screens; Robustness and rank diagnostics, and Simulation review, for the rest |

## Out of scope

These are outside Trial Folio unless a later decision adds them after the analysis each one needs:

- Personalized investment advice, suitability assessments, or allocations for any person.
- Trade execution, custody, discretion over accounts, or brokerage connections.
- Autonomous strategy discovery in the first releases.
- Any integration with DataMiner, including importing its exports or configurations ([ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md)).
- A hosted service that produces results for other people.

## Open questions

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| How are the default sell rules at rank 99 and rank 95 defined ([P-13](#proposed-defaults))? | Simulation turnover and results | Sell a holding when its rank falls below 99, or below 95 | The Simulation review specification |
