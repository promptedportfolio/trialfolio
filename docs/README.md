# Trial Folio documentation

These are the specifications for Trial Folio. Release 0.1.0's implementation tasks are done; [AGENTS.md](../AGENTS.md) gives its current state. Each document owns one kind of requirement. The other documents reference it instead of copying it, and a contradiction between documents is a defect to fix.

## Where to start

- **Implementing:** read [AGENTS.md](../AGENTS.md), then the assigned release. [0.1.0 API execution](releases/0.1.0-api-execution.md) is Ready, and its implementation tasks are done. [0.2.0](releases/0.2.0-review.md) is an outline, to be completed as a specification before it's implemented.
- **Using Trial Folio:** read the [user guide](user-guide.md).
- **Understanding the product:** read [spec.md](spec.md), then [roadmap.md](roadmap.md).
- **Planning a release:** follow [Product direction (D-23)](spec.md#product-direction) and the [release planning requirements](roadmap.md#release-planning-requirements), then write or complete its release specification. Roadmap targets are not implementation assignments.
- **Checking permissions or notices:** read [../LICENSE](../LICENSE), [licensing-policy.md](licensing-policy.md), and [disclaimers.md](disclaimers.md).

## Documents

| Document | Owns |
|---|---|
| [spec.md](spec.md) | Purpose, primary use, vocabulary, invariants (INV), enduring requirements (REQ), and owner decisions (D) and defaults (P) |
| [roadmap.md](roadmap.md) | Release planning requirements, the proposed sequence and workflow benefits, dependencies, driving-use-case coverage, and excluded or deferred scope |
| [contracts.md](contracts.md) | Interface and artifact meanings: configuration, identity, provenance, metrics, storage, hashing, reports, CLI, errors, protocols, credentials, and logging |
| [methodology.md](methodology.md) | Research design, statistical assumptions, evidence requirements, and interpretation (METH) |
| [licensing-policy.md](licensing-policy.md) | Eligibility, reserved uses, permissions, publication and distribution, and release gates (LIC) |
| [disclaimers.md](disclaimers.md) | Notice texts and placement, warranty summary, Portfolio123 notices and terms, and operating safeguards (DSC) |
| [releases/0.1.0-api-execution.md](releases/0.1.0-api-execution.md) | One screen backtest through the API, with a saved record and report (R01) |
| [releases/0.1.0-verification.md](releases/0.1.0-verification.md) | Release 0.1.0's verification record: each command's date, versions, and outcome, and the evidence for each acceptance criterion |
| [releases/0.2.0-review.md](releases/0.2.0-review.md) | Offline comparison of saved runs against a baseline (R02). An outline, to be completed before implementation |
| [releases/0.3.0-experiments.md](releases/0.3.0-experiments.md) | Finite experiments with resume (R03). An outline, to be completed before implementation |
| [adrs/0001-python-and-portfolio123-integration.md](adrs/0001-python-and-portfolio123-integration.md) | Python, `p123api`, and the third-party code boundary, with verification notes |
| [adrs/0002-pydantic-contracts-and-protocols.md](adrs/0002-pydantic-contracts-and-protocols.md) | Pydantic models, generated schemas, and narrow protocols |
| [adrs/0003-versioned-research-artifacts.md](adrs/0003-versioned-research-artifacts.md) | File-based, immutable, versioned artifacts |
| [adrs/0004-custom-personal-research-license.md](adrs/0004-custom-personal-research-license.md) | The custom source-available license |
| [adrs/0005-build-on-the-portfolio123-api-only.md](adrs/0005-build-on-the-portfolio123-api-only.md) | Building on the Portfolio123 API only, with no DataMiner integration, and the reordered releases |
| [adrs/0006-observe-the-wrappers-http-exchanges.md](adrs/0006-observe-the-wrappers-http-exchanges.md) | Recording each HTTP exchange the `p123api` wrapper makes, so failures are classified by what was sent |
| [adrs/0007-host-the-source-publicly-on-github.md](adrs/0007-host-the-source-publicly-on-github.md) | The public GitHub repository, its hosting exception, and where packages come from |
| [user-guide.md](user-guide.md) | How to set up and use Trial Folio, workflow by workflow, with what to check at each step. It owns no requirement: where it disagrees with an owning document, the guide is fixed. |
| [ai-development.md](ai-development.md) | How AI is used to build Trial Folio, in plain language |
| [spec-authoring-guide.md](spec-authoring-guide.md) | Bootstrap context used to write these documents. Superseded wherever an owning document says otherwise |

At the repository root:
- [../README.md](../README.md), the investor-facing overview.
- [../LICENSE](../LICENSE), which controls the legal grant.
- [../CONTACT.md](../CONTACT.md), which routes each kind of contact.
- [../CONTRIBUTING.md](../CONTRIBUTING.md).
- [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## How the documents fit together

- **Meanings and structures.** The product spec defines enduring obligations, and methodology defines what scientific assessments mean. Release specs define each increment, and contract prose defines interface meaning. Pydantic models define structure, and the JSON Schemas generated from them publish it.
- **Evidence and history.** Tests provide conformance evidence, and ADRs record decisions and their history.
- **Legal documents.** LICENSE, adopted on 2026-10-02, controls the legal grant. Other documents summarize it and never expand it.
- **Release status.** Each release file's **Status** line is the only progress record: Draft, Ready, Implemented, or Released. Implemented means the release works and is used privately. Released means it is distributed through the chosen channel under the adopted license ([D-08](spec.md#decisions), [D-22](spec.md#decisions)). The public repository isn't a release.

## Labels

As defined in the [authoring guide](spec-authoring-guide.md#2-interpret-requirements-and-uncertainty-consistently):

| Label | Meaning |
|---|---|
| Requirement | An owner constraint or adopted product invariant |
| Proposed default | A recommendation that may change before the relevant implementation or study |
| Verified observation | Behavior supported by a cited source or recorded integration evidence |
| Open question | An unresolved matter with a stated impact and resolution point |
| Deferred | Outside the current release |

MUST means required, SHOULD means a default whose exceptions need a documented reason, and MAY means optional.
