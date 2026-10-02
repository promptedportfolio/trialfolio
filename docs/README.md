# Trial Folio documentation

These are the specifications for Trial Folio. Nothing in them is implemented yet. Each document owns one kind of requirement. The other documents reference it instead of copying it, and a contradiction between documents is a defect to fix.

## Where to start

- **Implementing:** read [AGENTS.md](../AGENTS.md), then the assigned release. The next implementable release is [0.1.0 API execution](releases/0.1.0-api-execution.md). It's Ready: the owner signed off on 2026-10-01.
- **Understanding the product:** read [spec.md](spec.md), then [roadmap.md](roadmap.md).
- **Checking permissions or notices:** read [../LICENSE](../LICENSE), [licensing-policy.md](licensing-policy.md), and [disclaimers.md](disclaimers.md).

## Documents

| Document | Owns |
|---|---|
| [spec.md](spec.md) | Purpose, primary use, vocabulary, invariants (INV), enduring requirements (REQ), and owner decisions (D) and defaults (P) |
| [roadmap.md](roadmap.md) | The release sequence, dependencies, the value of each increment, driving-use-case coverage, and deferred scope |
| [contracts.md](contracts.md) | Interface and artifact meanings: configuration, identity, provenance, metrics, storage, hashing, reports, CLI, errors, protocols, credentials, and logging |
| [methodology.md](methodology.md) | Research design, statistical assumptions, evidence requirements, and interpretation (METH) |
| [licensing-policy.md](licensing-policy.md) | Eligibility, reserved uses, permissions, publication and distribution, and release gates (LIC) |
| [disclaimers.md](disclaimers.md) | Notice texts and placement, warranty summary, Portfolio123 notices and terms, and operating safeguards (DSC) |
| [releases/0.1.0-api-execution.md](releases/0.1.0-api-execution.md) | One screen backtest through the API, with a saved record and report (R01) |
| [releases/0.2.0-review.md](releases/0.2.0-review.md) | Offline comparison of saved runs against a baseline (R02). An outline, to be completed before implementation |
| [releases/0.3.0-experiments.md](releases/0.3.0-experiments.md) | Finite experiments with resume (R03). An outline, to be completed before implementation |
| [adrs/0001-python-and-portfolio123-integration.md](adrs/0001-python-and-portfolio123-integration.md) | Python, `p123api`, and the third-party code boundary, with verification notes |
| [adrs/0002-pydantic-contracts-and-protocols.md](adrs/0002-pydantic-contracts-and-protocols.md) | Pydantic models, generated schemas, and narrow protocols |
| [adrs/0003-versioned-research-artifacts.md](adrs/0003-versioned-research-artifacts.md) | File-based, immutable, versioned artifacts |
| [adrs/0004-custom-personal-research-license.md](adrs/0004-custom-personal-research-license.md) | The custom source-available license |
| [adrs/0005-build-on-the-portfolio123-api-only.md](adrs/0005-build-on-the-portfolio123-api-only.md) | Building on the Portfolio123 API only, with no DataMiner integration, and the reordered releases |
| [adrs/0006-observe-the-wrappers-http-exchanges.md](adrs/0006-observe-the-wrappers-http-exchanges.md) | Recording each HTTP exchange the `p123api` wrapper makes, so failures are classified by what was sent |
| [spec-authoring-guide.md](spec-authoring-guide.md) | Bootstrap context used to write these documents. Superseded wherever an owning document says otherwise |

At the repository root:
- [../README.md](../README.md), the investor-facing overview.
- [../LICENSE](../LICENSE), which controls the legal grant.
- [../CONTACT.md](../CONTACT.md).
- [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## How the documents fit together

- **Meanings and structures.** The product spec defines enduring obligations, and methodology defines what scientific assessments mean. Release specs define each increment, and contract prose defines interface meaning. Once implemented, Pydantic models define structure, and the JSON Schemas generated from them publish it.
- **Evidence and history.** Tests provide conformance evidence, and ADRs record decisions and their history.
- **Legal documents.** LICENSE, once adopted, controls the legal grant. Other documents summarize it and never expand it.
- **Release status.** Each release file's **Status** line is the only progress record: Draft, Ready, Implemented, or Released. Implemented means the release works and is used privately. Released means it is publicly distributed, which requires the adopted license and a chosen distribution channel ([D-08](spec.md#decisions)).

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
