# ADR 0002: Pydantic contracts and protocols

**Status:** Accepted. Pydantic v2 and `typing.Protocol` are owner requirements; the conventions in [contracts.md](../contracts.md) are proposed defaults until implemented.
**Date:** 2026-10-01

## Context

Trial Folio reads user configuration in YAML and exports in CSV, will receive provider payloads as JSON, and writes manifests, plans, attempt records, and normalized tables. Every one of those boundaries can silently corrupt evidence. Misspelled keys, percentage strings, coerced dates, NaN values, and missing fields turned into zero all risk it. The owner requires Pydantic v2 for validation and serialization boundaries and `typing.Protocol` for behavioral interfaces.

The field structure could be maintained in three places: Python models, JSON Schemas, and prose. If all three are hand-maintained, they drift apart.

## Decision

1. **Pydantic v2 models are the canonical executable structure** for application-owned configuration, manifests, plans, attempt records, and later study protocols and assessments. They live under `src/trialfolio/contracts/`.
2. **JSON Schemas are generated from the models,** committed under `schemas/`, and checked for drift. They are never edited by hand. Each schema states whether it is in validation or serialization mode where the two differ.
3. **Prose is authoritative for meaning.** [contracts.md](../contracts.md) defines what fields mean, and the models implement it. When a model and the prose disagree, the model is fixed; the fact that a model accepted a value never establishes that it is correct.
4. **Strict configuration.** Unknown fields are forbidden, and values are not coerced. Units, missingness, precision, and provenance are explicit, and non-finite numbers are rejected. Provider payloads are preserved whole as artifacts, and normalized models cover only the supported subset.
5. **Adapters before models.** CSV and provider-specific formats are parsed in named adapter steps before normalized models are validated. `model_construct` and other validation bypasses are never used on untrusted input.
6. **Narrow protocols, only when needed.** `typing.Protocol` defines interfaces at real boundaries: `ResultImporter`, `ArtifactStore`, and `ReportRenderer` in 0.1.0; `ScreenBacktestClient` in 0.2.0; `ModelClient` later. Dependencies are passed explicitly. Static type checking and contract tests enforce protocol obligations, because a runtime-checkable protocol does not.
7. **Data in models, behavior in protocols.** There is no universal provider interface, plugin registry, or service framework.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Dataclasses with hand-written validation | This duplicates what Pydantic provides and weakens schema generation. It also contradicts the owner's requirement. |
| Hand-maintained JSON Schema as the source of truth | That would mean two structural definitions, with guaranteed drift. |
| Abstract base classes for interfaces | They force inheritance on test doubles and implementations. Structural protocols fit the explicit-dependency style. |
| A general provider abstraction covering future operations | It would be speculative. It would also hide real differences between import and execution paths. |

## Consequences

- The Pydantic major version is pinned to 2, and each release records its tested dependency resolution.
- Schema generation cannot express every semantic validator, so runtime semantics are tested separately.
- Frozen models protect plans and resolved configurations in memory. Immutability on disk comes from the `ArtifactStore` ([ADR 0003](0003-versioned-research-artifacts.md)).
- Validation errors are logged without input values ([contracts.md, logging](../contracts.md#logging-and-local-diagnostics)).

## Follow-up conditions

- Revisit this ADR if schema drift checks prove impractical, or if a separately distributed interface needs public Python contracts.
