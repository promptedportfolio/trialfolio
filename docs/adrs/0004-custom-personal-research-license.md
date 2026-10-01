# ADR 0004: Custom personal research license

**Status:** Accepted: licensing approach (owner requirement)
**License text status:** Draft — not yet adopted
**Date:** 2026-10-01
**Decision owner:** Nathan Slaughter
**Owner decisions:** D-03 to D-08 in the [product specification](../spec.md)

When Nathan Slaughter adopts the license, record it here by changing the license text status to `Adopted YYYY-MM-DD`. Make the same change on the status line of [LICENSE](../../LICENSE).

## Context

Trial Folio is a CLI for investors who research strategies with Portfolio123. Nathan Slaughter wants it available to individual investors for their own research. He wants to keep control over professional and organizational use and over any publication of the code.

His requirements:

- Individuals may use it for private research on decisions for themselves and their family members.
- **Professional Users** need his prior express written permission before any use. An individual is a Professional User if any one of these applies: more than US $5,000,000 in liquid assets; making investment decisions for anyone other than themselves and family members; or reselling research about stocks as their primary source of income.
- No one may put the code into any public project or published code without his prior express written permission.
- Users must understand the limitations of backtesting, and nothing may represent that a user will realize financial gains.

An earlier plan recommended the MIT license. MIT permits all of the uses above, so it can't express these restrictions. Restrictions on professional use and publication are incompatible with the [Open Source Definition](https://opensource.org/osd), so no OSI-approved license fits.

Other constraints shape the decision:

- DataMiner is GPL-3.0, and GPL-3.0 forbids adding further restrictions. FactorMiner declares no license, so it grants no permission to copy.
- Public GitHub hosting grants on-platform viewing and forking under [GitHub's terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content).
- Portfolio123's own terms govern its data in any output (verified observation, 2026-10-01; see [disclaimers.md DSC-10](../disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users)).

## Decision

1. License Trial Folio's own material under a custom source-available license, the **Nathan Slaughter Personal Research License**, version 1.0, identifier `LicenseRef-NSPRL-1.0`. The text is in [LICENSE](../../LICENSE) and the plain-language policy in [licensing-policy.md](../licensing-policy.md).
2. Grant eligible natural persons use for private personal and family research only, including private copies and private modifications. Grant no distribution or sublicensing rights. Family members may use an interface the licensee runs on a machine they control, for personal research; access by anyone else is a hosted service that needs written permission (D-15).
3. Require prior express written permission for Professional Users, organizations, public projects and published code, and every reserved distribution form: forks, vendored source, packages, binaries, containers, notebooks with copied code, and hosted services.
4. Adopt the owner's definitions (D-06). Liquid assets exclude retirement accounts. "Primary source of income" means more than half of total income. "Family members" has no defined list. "Resell research" includes research the individual produced as well as research obtained from others (D-13, confirmed 2026-10-01). The definition of "personal research" remains proposed until he confirms it.
5. Treat generated reports as outputs, not covered code (D-07). Reports contain no scripts. Users may share reports they generated with the concise notice intact, and they are responsible for data-provider terms. Outputs other than reports, such as normalized CSV files and manifests, may also be shared (D-14).
6. **Nathan Slaughter adopts the license himself (D-03).** Legal review is not a condition of adoption or release. He may seek legal advice at any time.
7. Govern the license by Texas law, subject to mandatory applicable law (D-05). Add no venue, entity, liability cap, arbitration clause, class-action waiver, or indemnity.
8. Public distribution requires the adopted license and a recorded decision on a distribution channel consistent with the no-publication restriction (D-08). The repository stays private until then.
9. Keep p123api as the only Portfolio123 code dependency. Include no DataMiner or FactorMiner code. Leave third-party components under their own licenses.

## Considered alternatives

| Alternative | Why not chosen |
|---|---|
| MIT (or another permissive license) | Permits professional use, redistribution, and publication without permission, so it can't express the owner's requirements |
| A copyleft license such as GPL-3.0 | Also grants the freedoms to use and redistribute; it's incompatible with added use restrictions |
| A standard source-available license, such as PolyForm Noncommercial, PolyForm Personal Use, or the Business Source License | None expresses the three Professional User criteria or the no-published-code rule as written. The Business Source License converts to an open-source license after a change date, which conflicts with a lasting restriction. Modifying a standard license to fit would lose the benefit of its being standard |
| All rights reserved, with private access by invitation only | Meets the restrictions, but doesn't give individual investors a general grant. That conflicts with the owner's aim of independently useful releases for them |

## Consequences

- Trial Folio is not open source, and no document may call it that. Package metadata uses `LicenseRef-NSPRL-1.0`.
- Contributions need terms that give the licensor enough rights to distribute them. Until those exist, no outside contributions are accepted.
- Dependencies are constrained. No GPL-licensed or unlicensed upstream code can be included. Any GUI toolkit needs a license review, recorded in its own ADR.
- Public GitHub hosting conflicts with the no-publication rule unless the owner makes an explicit, narrowly defined hosting exception.
- Every human-facing report carries the concise notice and the full notice. Artifacts record `license_id` and `notice_version`.
- The license text was drafted without legal review, by the owner's decision. Whether individual terms are enforceable in a given jurisdiction is unknown. The license preserves rights that applicable law doesn't allow to be restricted, and it claims no guaranteed enforceability or immunity.
- The license authorizes no regulated activity. New activities, such as an author-hosted service for others, personalized advice, or brokerage connections, need separate legal analysis and the owner's decision before they are built.

## Follow-up conditions

- **Adoption:** resolve the "before adoption" items in [licensing-policy.md](../licensing-policy.md#outstanding-decisions), remove the drafting notes from LICENSE, and record adoption here and in LICENSE.
- **Distribution channel:** decide and record the channel before any "Released" status.
- **Revisit** this decision, through a superseding ADR, if any of these arise: a hosting exception, a desktop or web interface, contributor terms, an organizational licensing program, a change to the Professional User criteria, or a new license version.
- **Earlier grants:** before changing the license of any distributed version, check which terms recipients already hold. A new version doesn't remove rights already granted.
