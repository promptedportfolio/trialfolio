# ADR 0008: License version 1.1

**Status:** Accepted. Amends decisions 1 and 4 of [ADR 0004](0004-custom-personal-research-license.md).
**License text status:** Adopted 2026-10-07
**Date:** 2026-10-07
**Decision owner:** Nathan Slaughter
**Owner decisions:** D-27 and D-28 in the [product specification](../spec.md#decisions)

Nathan Slaughter adopted version 1.1 of the license on 2026-10-07. The license text status above and the status line of [LICENSE](../../LICENSE) record it.

## Context

On 2026-10-07 the owner reviewed version 1.0 of the license. Two things needed changing.

- **Personal investment vehicles.** Many individual investors hold some of their investments through a revocable trust, a retirement account such as an IRA or a 401(k), or a single-member LLC. Version 1.0 defines an Organization as any entity that isn't a natural person, trusts included. It puts use "on behalf of an Organization" outside the personal research grant (sections 1.6, 1.10, and 4). Read strictly, an investor researching for their own IRA or living trust needed written permission. That wasn't the intent: these vehicles hold the investor's own money, which is what the grant is for. Written permission can't fix this at scale, because each grant must identify its recipient (section 10.1).
- **A leftover sentence.** Version 1.0 still opened with a sentence from its draft: "This text has no effect until Nathan Slaughter adopts it", followed by instructions for recording adoption. Adoption was recorded on 2026-10-02, so the sentence did nothing except invite an argument about whether the license was in effect. [LIC-03](../licensing-policy.md#lic-03-adoption) had called for removing the drafting notes on adoption.

Section 19 of the license makes any change a new version, with a new identifier, and leaves copies received under an earlier version under that version's terms.

## Decision

1. **Version 1.1,** identifier `LicenseRef-NSPRL-1.1`, adopted by Nathan Slaughter on 2026-10-07. Version 1.0 remains the license of releases 0.1.0 and 0.2.0, and of every copy received under it.
2. **Personal Vehicles (section 1.21).** An individual's Personal Vehicle is a revocable trust of which they are a grantor and a trustee; an IRA, or any other retirement account, held for their benefit; or a limited liability company of which they are the only member. Use for one's own Personal Vehicle is use on one's own behalf (sections 1.6 and 4), investment decisions for it are decisions for oneself (section 1.7, condition (b)), and research for it can be personal research (section 1.10). The owner chose any retirement account, not only IRAs, to match the way the Liquid Assets definition already treats retirement accounts as a group. A Personal Vehicle is only the individual's own: a Family Member's trust, retirement account, or LLC isn't one, even when the individual manages it (the owner's decision, 2026-10-07).
3. **Their assets count (section 1.8).** Assets held through a Personal Vehicle, other than a retirement account, count toward the US $5,000,000 Liquid Assets threshold. This makes explicit what "beneficially owns" already most naturally covered, so moving investments into an LLC or a trust doesn't move anyone under the threshold.
4. **Services stay outside.** Services to clients or other persons are never personal research, including when they're provided through a Personal Vehicle (sections 1.10 and 1.21). A single-member LLC that provides research or advice to others needs written permission, as any organization does.
5. **The leftover sentence is removed.** Adoption is recorded by LICENSE's status line, in this ADR, and in the licensing policy ([LIC-03](../licensing-policy.md#lic-03-adoption)).
6. **Release 0.2.1 carries it** (D-27). Reports link to the LICENSE at their version's tag ([D-21](../spec.md#decisions)), so the new text ships with a new version: [0.2.1](../releases/0.2.1-license.md), tagged `v0.2.1` on the commit that merges it.
7. **A public written permission template** (D-28). [written-permission-template.md](../written-permission-template.md) shows what a grant under section 10 contains. It covers license scope only; fees and other commercial terms belong in a separate agreement.

## Considered alternatives

| Alternative | Why not chosen |
|---|---|
| Keep 1.0, and grant written permission case by case | Each grant must name its recipient (section 10.1), so every investor with an IRA or a living trust would have had to ask |
| Edit 1.0 in place | People who received 1.0 keep its terms (section 19, [LIC-20](../licensing-policy.md#lic-20-license-changes-and-earlier-grants)), and one identifier can't name two texts |
| IRAs only | The owner chose any retirement account (decision 2) |
| Leave assets held through an LLC or a trust out of Liquid Assets | Anyone could move under the Professional User threshold by moving investments into an entity |
| Include a Family Member's own trust, retirement account, or LLC, such as a spouse's IRA the individual manages | The owner decided against it on 2026-10-07 (decision 2) |
| Ship version 1.1 with 0.3.0 | The owner chose a patch release, so the new text doesn't wait for 0.3.0's specification |

## Consequences

- Every artifact and report from 0.2.1 records `LicenseRef-NSPRL-1.1`. Runs and reviews written under 1.0 keep their identifier, and still read.
- Users who acknowledged version 1.0 are asked again, once, because an acknowledgment covers one license identifier and one notice version ([D-17](../spec.md#decisions)). The research notice is unchanged, so its version stays 1.0.
- Version 1.1 grants more than 1.0. Its one tightening is decision 3, which states what 1.0's "beneficially owns" already covered. Copies received under 1.0 keep its terms (section 19).
- A Family Member's own trust, retirement account, or LLC isn't a Personal Vehicle of the individual who manages it (decision 2). Anyone unsure whether managing one is covered can ask for written permission.

## Follow-up conditions

- **Tag** `v0.2.1` on the commit that merges this decision, and run the license policy's [release checklist](../licensing-policy.md#lic-19-release-checklist) against it.
- **The adoption date** is the day this decision merges. If that isn't 2026-10-07, change the date in LICENSE, here, in the licensing policy, and in [disclaimers.md](../disclaimers.md) before merging.
- **Revisit** through a superseding ADR on any further license change, as [ADR 0004](0004-custom-personal-research-license.md) says.
