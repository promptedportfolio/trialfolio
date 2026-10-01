# ADR 0005: Build on the Portfolio123 API only

**Status:** Accepted. Supersedes decision 3 of [ADR 0001](0001-python-and-portfolio123-integration.md), and amends the protocol list in [ADR 0002](0002-pydantic-contracts-and-protocols.md).
**Date:** 2026-10-01

## Context

The first plan made release 0.1.0 an offline review of DataMiner exports, with API execution arriving in 0.2.0. DataMiner is Portfolio123's desktop application for running API operations from YAML scripts. Several observations argued against building on it:

- **Distribution.** Portfolio123 distributes DataMiner builds from a shared cloud folder, and the builds may differ from the public source. The public repository was last changed in February 2025 (verified observation, [ADR 0001](0001-python-and-portfolio123-integration.md#verification-notes)). The owner reported that the macOS build is unsigned, so macOS blocks it by default.
- **No automation.** It is a desktop application. Trial Folio can't drive it, and every user would have to install it by hand.
- **Exports lack provenance.** Going by the pinned source, the CSV output records no settings, DataMiner version, credit cost, or timestamp, so settings could come only from configuration files the user attaches. Its documented defaults include an end date of "today" and zero slippage, the kind of silent default Trial Folio exists to prevent ([INV-03](../spec.md#enduring-invariants)).
- **No reusable code.** DataMiner is licensed under GPL-3.0, so its code could never be included in Trial Folio ([ADR 0004](0004-custom-personal-research-license.md)).

The official `p123api` wrapper calls the same screen-backtest endpoint and is MIT-licensed. Version 3.1.0 was released on 2026-08-25. It returns the full decoded response, including the cost and quota metadata.

## Decision

1. **No DataMiner integration.** Trial Folio doesn't import DataMiner exports or configurations, and doesn't offer a configuration conversion. It doesn't depend on DataMiner being installed. The code boundary in [REQ-02](../spec.md#enduring-requirements) is unchanged: no DataMiner or FactorMiner code is ever included.
2. **`p123api` is the only way in.** Every Portfolio123 result Trial Folio holds comes from a request Trial Folio planned, sent, and recorded. Its settings are therefore `verified` rather than user-supplied.
3. **Releases are reordered.**
   - [0.1.0](../releases/0.1.0-api-execution.md) runs one screen backtest through the API and reports it.
   - [0.2.0](../releases/0.2.0-review.md) compares saved runs against a baseline.
   - [0.3.0](../releases/0.3.0-experiments.md) is unchanged.

   Each is still useful on its own.
4. **Reference data comes from the API.** A single live call, made with the owner's credentials and approval under a declared budget, replaces the DataMiner reference exports.
5. **Documentation can still be cited.** Portfolio123's DataMiner documentation MAY be cited for facts about Portfolio123 operations. It's evidence about the provider, not a dependency.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Keep 0.1.0 as an offline review of DataMiner exports | It needs a manually installed desktop tool, and its exports carry no settings or provenance. Most of the review logic would be spent working around missing information. |
| Import exports downloaded from the Portfolio123 website | Their layouts are unverified, and they likely share the provenance gap. This can be reconsidered if users need to bring in past results. |
| Call the HTTP API directly, without `p123api` | As in [ADR 0001](0001-python-and-portfolio123-integration.md), this duplicates maintained authentication and endpoint handling |

## Consequences

- **API access from the start.** Release 0.1.0 needs a Portfolio123 subscription with API access and credits. The offline demo and the default test suite still run without either, using synthetic data.
- **No imported history.** Results users produced earlier in DataMiner or on the website can't be reviewed.
- **Size shift.** Release 0.1.0 is larger than the original plan, and 0.2.0 is correspondingly smaller. Importer, CSV-parsing, and configuration-parsing work drops out entirely.
- **Better comparisons.** Review compares Trial Folio's own records, whose settings and provenance are verified.
- **Superseded parts.** `ResultImporter` is no longer planned (ADR 0002). Decision 3 of ADR 0001 is superseded; its code boundary stays in force through REQ-02.
- **Neutral wording.** Project materials describe DataMiner factually and neutrally. The reasons above are about fitness for Trial Folio, not the quality of Portfolio123's tools.

## Follow-up conditions

- Revisit this decision if users need to review results they produced outside Trial Folio.
- Revisit it if Portfolio123 offers a maintained, scriptable export whose files carry their settings and provenance.
