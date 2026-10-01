# ADR 0003: Versioned research artifacts

**Status:** Proposed. Adopted when 0.1.0 is implemented with this design.
**Date:** 2026-10-01

## Context

Trial Folio's value depends on evidence that outlives the software version and the provider response that produced it. The requirements are:

- Keep everything collected, including failures (INV-01).
- Keep sources separate from derived data (INV-04).
- Regenerate reports offline (INV-05).
- Keep historical artifacts readable (INV-12).
- Keep artifact paths valid when a directory is moved or served by another interface (REQ-05).

Provider reruns can return different results because upstream data and engines change, so an artifact is the only stable record of what was observed.

## Decision

1. **File-based output directories.** Each command writes one output directory containing byte-for-byte source copies, JSON metadata, and normalized CSV tables. The layout is defined in [contracts.md, artifact storage](../contracts.md#artifact-storage). Parquet MAY be added later for large tables. A SQLite index MAY be added later, but it is never a prerequisite and never the only copy.
2. **All reads and writes go through `ArtifactStore`,** starting with a local filesystem implementation in 0.1.0. Manifests record paths relative to the output root.
3. **Immutable, atomic writes.** Artifacts are written to a temporary name, synced to disk, and published under their final name by a step that fails if the name exists, never by a rename that replaces it ([contracts.md, artifact storage](../contracts.md#artifact-storage) names the mechanism for each platform). Existing artifacts are never overwritten, and corrections and migrations produce new artifacts. The manifest is written last, so a missing manifest means incomplete output.
4. **Independent versions.** Artifact schema versions use `<major>.<minor>.<patch>` independently of application versions. Parser, wrapper, method, and canonicalization versions are recorded separately, as are `license_id` and `notice_version`.
5. **Documented readers.** Every schema version that has been released keeps a reader and a committed fixture. An unknown schema version fails clearly.
6. **Content addressing and canonical identity.** Files are identified by SHA-256. Configuration identity uses canonical JSON under RFC 8785, with decimal strings and UTC datetimes, under a recorded `canonicalization_version`. The one exception is a provider request recorded exactly as it's sent, such as a plan's `params`: its numbers stay JSON numbers, which RFC 8785 writes as ECMAScript does ([contracts.md, canonical hashing](../contracts.md#canonical-hashing)). Configuration identity (`case_id`) is kept separate from execution identity (`attempt_id`).
7. **Logs are not evidence.** `logs/` sits inside the output directory but is excluded from hashes and from the manifest's evidence.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| SQLite as the primary store | It adds a first-release prerequisite, makes the evidence harder to inspect by hand, and risks becoming the only copy. |
| Parquet from the start | It is unnecessary for the small summary tables in 0.1.0 to 0.3.0, and CSV is directly inspectable. |
| Tying the artifact version to the application version | That would force meaningless schema bumps, or hide real schema changes behind application releases. |
| Overwriting outputs on re-run | It destroys evidence and makes interrupted runs ambiguous. |

## Consequences

- Output directories grow with every run. Deleting them is the user's choice and is never automatic.
- Hashes detect change. They do not prove that provider data is correct, and they do not prevent tampering with local files.
- Offline reproducibility means regenerating a declared analysis from archived inputs with identified code and settings. It does not mean a provider rerun will return identical data.
- Every schema change needs a compatibility statement and, for released versions, a fixture.

## Follow-up conditions

- Accept this ADR when the 0.1.0 artifact layout ships. Revisit it before adding Parquet, SQLite, or a restricted inspection mode for unknown versions.
