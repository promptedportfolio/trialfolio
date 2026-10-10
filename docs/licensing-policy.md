# Licensing policy

**Status:** Draft. Version 1.1 of the license text was **adopted on 2026-10-07**, and version 1.0 on 2026-10-02.
**Controlling document:** [LICENSE](../LICENSE), the Nathan Slaughter Personal Research License, version 1.1, identifier `LicenseRef-NSPRL-1.1`.
**Owner decisions:** D-03 to D-08, D-27, and D-28 in the [product specification](spec.md). **Related invariant:** INV-13.

This policy explains Trial Folio's license: who may use it, what is reserved, how to get permission, how results may be shared, and what must happen before public distribution. LICENSE controls. If this policy and LICENSE disagree, LICENSE controls and the disagreement is a defect to fix. This policy must not describe any permission that LICENSE doesn't grant.

Research, financial-result, warranty, and Portfolio123 notices are owned by [disclaimers.md](disclaimers.md). Third-party components are recorded in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md). Contact details are in [CONTACT.md](../CONTACT.md).

This policy is not legal advice or a legal determination. Nathan Slaughter may seek legal advice at any time. Legal review is not a condition of adopting the license or of releasing Trial Folio (D-03).

## Requirements

| ID | Requirement | Status |
|---|---|---|
| [LIC-01](#lic-01-license-identity) | Trial Folio is source available under a custom license, never described as open source | Requirement |
| [LIC-02](#lic-02-licensor-and-contact) | Nathan Slaughter is author, licensor, and licensing contact | Requirement |
| [LIC-03](#lic-03-adoption) | Nathan Slaughter adopts each license version; adoption is recorded in LICENSE and the version's ADR | Requirement |
| [LIC-04](#lic-04-personal-research-grant) | The general grant covers eligible individuals' private personal research only | Requirement |
| [LIC-05](#lic-05-professional-users) | Professional Users need prior express written permission | Requirement |
| [LIC-06](#lic-06-written-permission) | Permission is express, written, and specific | Requirement |
| [LIC-07](#lic-07-organizations) | Organizational use needs written permission | Requirement |
| [LIC-08](#lic-08-public-projects-and-published-code) | No public project or published code may include Trial Folio code without permission | Requirement |
| [LIC-09](#lic-09-reserved-distribution-and-hosted-services) | Publication, redistribution, and hosted services are reserved | Requirement |
| [LIC-10](#lic-10-reports-and-other-outputs) | Reports are script-free outputs that users may share with the notice intact | Requirement (D-07, D-14) |
| [LIC-11](#lic-11-notices-and-license-metadata) | License and notices travel with the software, reports, and artifacts | Requirement |
| [LIC-12](#lic-12-acceptance-and-acknowledgment) | Acceptance is lightweight, local, and automation-compatible | Requirement; mechanism D-17 |
| [LIC-13](#lic-13-third-party-components) | Third-party material keeps its own license; no GPL or unlicensed upstream code | Requirement |
| [LIC-14](#lic-14-contributions) | No outside contributions without terms that let the licensor distribute them | Requirement |
| [LIC-15](#lic-15-distribution-channel) | Public distribution uses a channel consistent with the restrictions | Requirement (D-08, D-22) |
| [LIC-16](#lic-16-bundled-builds-and-container-images) | Bundled builds and images meet third-party and reserved-distribution rules | Requirement |
| [LIC-17](#lic-17-other-interfaces) | Desktop, local web, and hosted interfaces are resolved before they ship | Requirement; local serving Open question |
| [LIC-18](#lic-18-regulatory-boundaries) | The license authorizes no regulated activity; new activities need separate analysis | Requirement |
| [LIC-19](#lic-19-release-checklist) | Public distribution follows the release checklist | Requirement |
| [LIC-20](#lic-20-license-changes-and-earlier-grants) | New license versions don't remove rights already granted | Requirement |

## License identity and adoption

### LIC-01 License identity

Trial Folio's own material is licensed under the Nathan Slaughter Personal Research License, version 1.1, identifier `LicenseRef-NSPRL-1.1`, from release 0.2.1. Releases 0.1.0 and 0.2.0 carry version 1.0, `LicenseRef-NSPRL-1.0` ([LIC-20](#lic-20-license-changes-and-earlier-grants)). The license is not MIT and not an OSI-approved open-source license. Its restrictions on professional use and publication are incompatible with the freedoms the [Open Source Definition](https://opensource.org/osd) requires.

- The README, package metadata, documentation, and release announcements MUST describe Trial Folio as "source available under a custom license".
- Package metadata MUST identify the license by the identifier of the version it carries, currently `LicenseRef-NSPRL-1.1`, and include the LICENSE file.
- No document, badge, or package classifier may describe Trial Folio as MIT-licensed, open source, or OSI-approved.

### LIC-02 Licensor and contact

Nathan Slaughter is the author of Trial Folio and licensor of the material he has the right to license. All licensing and permission requests go to git@nathanslaughter.com, as described in [CONTACT.md](../CONTACT.md).

The license covers only material Nathan Slaughter can license. It claims no exclusive ownership of users' inputs, numerical findings, or third-party data.

### LIC-03 Adoption

Nathan Slaughter adopted version 1.0 of LICENSE on 2026-10-02, and version 1.1 on 2026-10-07 ([ADR 0008](adrs/0008-license-version-1-1.md)). He adopts each version himself (D-03). Adopting a version takes these steps:

1. Resolve the decisions marked "before adoption" under [Outstanding decisions](#outstanding-decisions).
2. Remove any drafting notes from LICENSE. Version 1.1 removed a sentence about adoption that version 1.0 had kept from its draft.
3. Change the LICENSE status line to `Status: Adopted YYYY-MM-DD`.
4. Record the same status and date in the version's ADR: [ADR 0004](adrs/0004-custom-personal-research-license.md) for version 1.0, and [ADR 0008](adrs/0008-license-version-1-1.md) for version 1.1.
5. Give the new version a new identifier (LICENSE section 19), and ship it with a new Trial Folio version, tagged on the commit that adopts it. Reports link to the LICENSE at their version's tag ([D-21](spec.md#decisions), [D-27](spec.md#decisions)).


## Who may use Trial Folio

### LIC-04 Personal research grant

The general grant is limited to **eligible individuals**: natural persons who are not Professional Users and who use Trial Folio only on their own behalf. They may use it for their own private research, including research for investment decisions concerning themselves and their family members.

Using Trial Folio for one's own **Personal Vehicle** is acting on one's own behalf (LICENSE section 1.21, D-27). A Personal Vehicle is a revocable trust of which the individual is a grantor and a trustee; an IRA, or any other retirement account, held for their benefit; or a limited liability company of which they are the only member. Services to clients or other persons are never personal research, even through a Personal Vehicle.

The grant permits the copies needed for that use and private modifications, kept on devices, accounts, and storage that only the individual can access. It grants no right to publish, distribute, or sublicense.

### LIC-05 Professional Users

An individual is a **Professional User** if **any one or more** of these applies:

1. They have **more than US $5,000,000 in liquid assets**.
2. They make investment decisions for **anyone other than themselves and their family members**.
3. They **resell research about stocks as their primary source of income**.

A Professional User MUST obtain Nathan Slaughter's **prior express written permission before using** Trial Folio. The conditions are alternatives, so any one is enough. A user who later becomes a Professional User must obtain permission before continuing.

"Professional User" is a contractual category of this license only. It says nothing about investment-adviser registration, accredited-investor or qualified-purchaser status, or eligibility for any legal exemption.

Portfolio123's High-Net-Worth Investor account type uses a similar threshold: "more than $5 million in liquid financial assets" (verified observation, checked 2026-10-01; see [DSC-10](disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users)). That is Portfolio123's separate contractual category. Neither classification implies the other, and the definitions differ.

| Term | Meaning in LICENSE | Status |
|---|---|---|
| Liquid assets | Cash, cash equivalents, and readily marketable financial assets the individual beneficially owns, valued in U.S. dollars, excluding retirement accounts. Assets held through a Personal Vehicle, other than a retirement account, count | Requirement (D-06, D-27), resolved |
| Primary source of income | A source that provides more than half of the individual's total income | Requirement (D-06), resolved |
| Family members | The members of an individual's family; the license adds no list | Requirement (D-06), resolved |
| Resell research | To provide research about stocks to other persons for compensation, whether the individual produced it or obtained it from others | Requirement (D-13) |
| Personal research | Private analysis for the individual's own purposes, including investment decisions concerning themselves and their family members; excludes work for an employer, work for any organization but the individual's Personal Vehicle, client services, and redistribution | Requirement, confirmed as drafted 2026-10-02; the Personal Vehicle exception is D-27 |
| Personal Vehicle | The individual's revocable trust, of which they are a grantor and a trustee; an IRA or any other retirement account held for their benefit; or a limited liability company of which they are the only member. Use for it is use on their own behalf, and investment decisions for it are decisions for themselves | Requirement (D-27) |

Trial Folio MUST NOT ask users to provide account balances, statements, income records, or family identities in order to run. Eligibility is the user's responsibility under the license (see [LIC-12](#lic-12-acceptance-and-acknowledgment)).

#### Eligibility examples

These examples illustrate LICENSE. They are not a finding that the terms or any eligibility mechanism are legally sufficient.

| Scenario | Outcome |
|---|---|
| Individual with US $4 million in liquid assets, researching only personal and family decisions, whose income doesn't come mainly from reselling stock research | Eligible for the personal research grant if all other terms are met |
| Individual with US $4 million in liquid assets plus US $3 million in retirement accounts, no other criterion | Eligible: retirement accounts don't count toward liquid assets |
| Individual with exactly US $5 million in liquid assets and neither other criterion | Eligible: the asset criterion requires more than US $5 million |
| Individual with more than US $5 million in liquid assets, using Trial Folio only personally | Prior express written permission required |
| Individual making investment decisions for an unrelated friend without charging | Prior express written permission required |
| Individual making investment decisions only for themselves and family members | Eligible, if no other criterion applies |
| Individual researching for their own IRA, their 401(k), their revocable living trust, of which they are a grantor and a trustee, or an LLC of which they are the only member, with no other criterion | Eligible: each is a Personal Vehicle, so the use is on their own behalf |
| Individual with US $3 million in a brokerage account and US $3 million more in their single-member LLC's brokerage account | Prior express written permission required: the LLC's assets count, for more than US $5 million in liquid assets |
| Individual providing research or advice to clients through their single-member LLC | Written permission required: services to clients aren't personal research, even through a Personal Vehicle |
| Individual for whom reselling stock research is 60% of total income | Prior express written permission required |
| Individual for whom reselling stock research is exactly 50% of total income | Resale criterion not met; eligible if no other criterion applies |
| Individual using Trial Folio for their employer's research | Written permission required (organizational use) |
| Eligible individual wanting to put modified Trial Folio code in a public repository or published package | Separate prior express written permission required |
| Professional User who has only emailed a request | No permission until an express written grant is received |
| Separately licensed third-party code obtained independently | Its own license governs; Nathan Slaughter claims no rights he doesn't own |

### LIC-06 Written permission

Permission MUST be express and in writing, sent or signed by Nathan Slaughter. It MUST identify the recipient, the permitted scope, any duration, and any publication, distribution, or sublicensing rights. It grants only what it states.

None of these is permission: an inquiry, silence, a lack of objection, an automatic reply, attribution, a donation, or the purchase of an unrelated product. Permission to use Trial Folio as a Professional User or for an organization doesn't include permission to publish or distribute code unless the grant says so expressly.

[CONTACT.md](../CONTACT.md) describes what to send. The [written permission template](written-permission-template.md) shows the form a grant takes (D-28).

### LIC-07 Organizations

Organizations, and individuals using Trial Folio on an organization's behalf (including for an employer), are outside the personal research grant. They need written permission before any use. An individual's use for their own Personal Vehicle isn't use on an organization's behalf ([LIC-04](#lic-04-personal-research-grant)).

## Publication and distribution

### LIC-08 Public projects and published code

No person may incorporate Trial Folio's code, a portion of it, or a modification of it into **any public project or any published code** without Nathan Slaughter's prior express written permission. This applies whether the receiving project is free, paid, commercial, nonprofit, source available, or open source.

Private modifications for personal research carry no right to publish them. Nathan Slaughter's own right to publish Trial Folio doesn't authorize recipients to republish it.

LICENSE section 5.4 makes one narrow exception, for the rights GitHub's terms grant in a public repository: viewing it, and forking it on GitHub ([LIC-15](#lic-15-distribution-channel)). It permits nothing more. Publishing modifications, even in a public fork, still needs permission.

### LIC-09 Reserved distribution and hosted services

These uses are reserved and need prior express written permission, whether or not the code is modified:

- publishing, redistributing, sublicensing, selling, lending, or otherwise supplying copies
- public forks and other public copies of the source, except forks on GitHub within LICENSE section 5.4
- vendored source
- packages, and binaries, executables, or archives containing the code
- container images and virtual-machine images containing the code
- notebooks or documents containing copied code
- hosted services incorporating Trial Folio, meaning any network access to its functionality by anyone other than the licensee and the licensee's family members (LICENSE section 6.2)

### LIC-10 Reports and other outputs

Code and results are different things. Owner decision D-07 settles how reports are treated:

- **Requirement:** Trial Folio's generated HTML reports MUST contain no scripts. They use inline CSS and inline SVG only and load no external resources.
- **Requirement:** A generated report is an output, not covered code. A user MAY share or publish reports they generated, provided the concise financial-result notice ([disclaimers.md](disclaimers.md#dsc-02-concise-report-notice)) stays intact and unaltered.
- **Requirement:** The user is responsible for data-provider terms, including Portfolio123's, that cover provider data in a shared report.
- **Requirement:** Report sharing doesn't permit publishing the software, templates or stylesheets taken out of a report, or any code. Material extracted from an output and used separately remains covered by the license.
- **Requirement (D-14):** Outputs other than reports, such as normalized CSV files and manifests, are treated the same way: the license doesn't restrict sharing them (LICENSE section 7.3). Data-provider terms still apply.

Trial Folio claims no ownership of users' numerical findings. Private use of reports is always within the personal research purpose, subject to data-provider rights.

**Verified observation (checked 2026-10-01):** Portfolio123's [Terms of Use and Conditions](https://www.portfolio123.com/legal) (last updated February 24, 2023) generally prohibit redistributing its Content without its prior written consent. Its Research Provider account type needs written permission to reproduce or redistribute even derived content. A report containing Portfolio123 data will therefore usually need Portfolio123's consent before public sharing. Trial Folio's permission to share reports grants no Portfolio123 right. The extracts are in [disclaimers.md DSC-10](disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users); this is not legal advice about those terms.

### LIC-11 Notices and license metadata

Supports INV-13.

- Every copy of Trial Folio carries LICENSE, CONTACT.md, THIRD_PARTY_NOTICES.md, and docs/disclaimers.md.
- Every human-facing report carries the concise notice and the full notice, as [disclaimers.md](disclaimers.md#dsc-03-where-notices-appear) specifies.
- Machine-readable artifacts that carry assessments or reports record `license_id` (currently `LicenseRef-NSPRL-1.1`) and `notice_version` (currently `1.0`) as fields. They don't insert notice prose into numeric fields. The field definitions belong to [contracts.md](contracts.md).
- The CLI makes the license identifier and the notices available to the user. The release specification defines how.
- The README states the license identity (LIC-01) and the two Portfolio123 notices ([disclaimers.md](disclaimers.md#dsc-06-portfolio123-notices)).

### LIC-12 Acceptance and acknowledgment

Downloading, installing, copying, modifying, or using Trial Folio is acceptance of the license (LICENSE section 11). LICENSE section 9.2 requires users to acknowledge the limitations of backtested and simulated results and that no financial gain is represented.

**Requirements** for any acknowledgment mechanism:

- It works offline and in automation, including CI and scripted runs.
- It makes no network request and sends nothing off the machine (INV-14).
- It collects no financial information, account data, or family identities.
- It doesn't interrupt the user repeatedly, and it adds no remote enforcement.

**Requirement (D-17):** the mechanism is a one-time local acknowledgment for each license and notice version, with non-interactive options for automation. It is specified in [contracts.md, license acknowledgment](contracts.md#license-acknowledgment) and delivered in release 0.1.0.

## Third-party material and contributions

### LIC-13 Third-party components

Third-party components keep their own licenses, which govern them. Trial Folio's restrictions don't apply to them. A dependency's permissive license doesn't make Trial Folio permissively licensed.

- p123api is the only Portfolio123 code dependency.
- DataMiner (GPL-3.0) and FactorMiner (no license declared) code is never imported, vendored, bundled, or ported, including in containers, notebooks, examples, and test utilities. Their exports and configurations are read as data.
- Copying any copyleft-covered implementation into Trial Folio needs a recorded compatibility analysis and Nathan Slaughter's decision first. See the [GNU licensing FAQ](https://www.gnu.org/licenses/gpl-faq.html.en#NoMilitary).
- [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) is regenerated from the resolved dependency set for each release.

### LIC-14 Contributions

Nathan Slaughter must hold enough rights to distribute any accepted contribution under this policy. A public pull request doesn't automatically supply those rights: GitHub's terms license a contribution under the repository's own license, and that license grants no right to distribute, so the contribution couldn't be distributed with Trial Folio. Trial Folio accepts no outside contributions until contributor terms exist that grant them. [CONTRIBUTING.md](../CONTRIBUTING.md) tells visitors so, and outside pull requests are closed without being merged or copied.

## Distribution channel and bundled builds

### LIC-15 Distribution channel

Public distribution ("Released" status) requires both of the following (D-08):

1. The license adopted by Nathan Slaughter (LIC-03).
2. His recorded decision on a distribution channel consistent with the no-publication restriction.

Both exist. He adopted the license and decided the channel on 2026-10-02 ([ADR 0007](adrs/0007-host-the-source-publicly-on-github.md), D-22):

- **Source: a public GitHub repository.** Public GitHub repositories grant users on-platform viewing and forking rights under [GitHub's terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content). A custom notice can't pretend those platform grants don't exist, so LICENSE section 5.4 states a narrow exception that goes no further than they do.
- **Packages: downloaded from the author's site,** delivered with LICENSE.
- **Not PyPI.** Its terms either require a license that lets anyone redistribute the package, or grant every user an irrevocable license to redistribute it (verified observation, checked 2026-10-02).
- **Homebrew, perhaps later:** a personal tap whose formula points at the archive on the author's site, without prebuilt bottles. Homebrew's main repository accepts only free-software licenses.

A public repository isn't a release. A release is Released only when it's distributed through this channel.

The restriction must not be silently weakened to suit a preferred host.

| Option | Consistency with the restrictions | Outcome |
|---|---|---|
| Download controlled by the author, such as a release archive on his own site, delivered with LICENSE | Consistent | Chosen for packages |
| Private repository with access granted per request | Consistent | Not chosen; it limits reach for eligible individuals |
| Public GitHub repository with an explicit, narrowly defined hosting exception | Weakens LIC-08 for on-platform forks only | Chosen for the source, with the exception in LICENSE section 5.4 |
| PyPI | Inconsistent: its terms grant redistribution rights | Not used |

### LIC-16 Bundled builds and container images

A wheel or source distribution that declares dependencies distributes none of their code. Vendored source, zipapps, frozen executables, notebooks containing copied code, and container images do bundle third-party code and must meet the requirements in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

A container image contains Trial Folio's code. Publishing one is a reserved distribution under LIC-09. It requires an approved channel (LIC-15) and must carry LICENSE, CONTACT.md, and disclaimers.md, along with an image-level notices file generated from the built image.

## Other interfaces

### LIC-17 Other interfaces

The CLI is the first interface. Before any desktop, local web, or hosted interface ships:

- **Local serving.** Running Trial Folio on the user's own machine for their own personal research is not a hosted service (LICENSE section 6.1). **Requirement (D-15):** an eligible individual MAY let their family members use an interface the individual runs on a machine they control, for personal research (LICENSE section 6.2). Anyone else using it is a hosted service that needs written permission (LICENSE section 6.3). Portfolio123's terms, not this license, govern whether family members may see Portfolio123 data or trigger requests through the individual's account. Those terms prohibit transferring or lending log-in credentials.
- **Author-hosted services need separate review before launch.** A service producing user-parameterized results for other people is a new activity under [LIC-18](#lic-18-regulatory-boundaries). It also needs confirmation of Portfolio123's terms for showing provider data to other users and for handling other users' Portfolio123 credentials. Portfolio123's terms (verified observation, checked 2026-10-01; [DSC-10](disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users)) prohibit using the service to compete with it, or assisting a third party to do so. They also prohibit transferring or lending log-in credentials. Any multi-user or hosted interface must be reviewed against both clauses.
- **Notices apply on screen.** Any screen showing results is a human-facing report: it shows the concise notice and gives access to the full notice. The interface presents the license acknowledgment consistently with [LIC-12](#lic-12-acceptance-and-acknowledgment).
- **Desktop bundles are frozen executables.** [LIC-16](#lic-16-bundled-builds-and-container-images) applies to everything packaged, including the interpreter and GUI toolkit. JavaScript dependencies shipped with a web UI also need notices.
- **The toolkit license must be compatible.** Verified observation, checked 2026-10-01:
  - PyQt6 is GPL-3.0-only unless a commercial license is purchased. The GPL option is incompatible with this license.
  - PySide6 is available under LGPL-3.0. Using it requires keeping Qt as replaceable shared libraries, giving notice of its use, including the LGPL and GPL texts, and making Qt's corresponding source available. Trial Folio's terms must also not prohibit modifying the Qt portions or reverse engineering to debug such modifications (LGPL-3.0 section 4).
  - Electron is MIT, and Tauri is Apache-2.0 or MIT. Electron also ships Chromium's extensive third-party notices.
- Record the toolkit choice and its license review in an ADR.

## Regulatory boundaries

### LIC-18 Regulatory boundaries

The license authorizes no one to provide regulated services. Trial Folio's operating safeguards, which bear on the publisher's-exclusion analysis, are product requirements owned by [disclaimers.md](disclaimers.md#dsc-07-operating-safeguards).

The following are new activities: an author-hosted service producing results for others, personalized portfolio interpretation, event-driven securities recommendations, paid advisory services, and brokerage or execution connections. Each requires separate legal analysis and Nathan Slaughter's decision before it is built. No document may state that Nathan Slaughter is registered, exempt, excluded, or immune from liability unless that has been established.

## Release requirements

### LIC-19 Release checklist

Before any public distribution:

1. Nathan Slaughter has adopted LICENSE (LIC-03), resolved the "before adoption" decisions, and removed the drafting notes.
2. The distribution channel is decided and recorded (LIC-15).
3. The contact address and every link in LICENSE, CONTACT.md, and the README work.
4. The actual package includes LICENSE and the notices. Generated reports include the concise and full notices, `license_id`, and `notice_version`. The CLI exposes the license and notices.
5. Upstream rights, contributor terms (LIC-14), and any earlier grants (LIC-20) have been checked.
6. No document, classifier, or badge describes Trial Folio as MIT-licensed or OSI-approved open source (LIC-01).
7. THIRD_PARTY_NOTICES.md matches the resolved dependencies. Any bundled build or container image meets LIC-16.
8. The README and package description carry the Portfolio123 subscription and non-affiliation notices, consistent with disclaimers.md.

### LIC-20 License changes and earlier grants

A new license version applies to the Trial Folio versions distributed with it. It doesn't remove rights a recipient already has under terms granted earlier. Before changing an existing release's license, check what earlier grants exist. No MIT-licensed or otherwise permissively licensed release of Trial Folio has been made.

Version 1.1 applies from release 0.2.1. Releases 0.1.0 and 0.2.0, whose tags hold version 1.0, keep it, and so does every copy received under it. Version 1.1 grants more than 1.0. Its one tightening states what 1.0's "beneficially owns" already covered: assets held through a Personal Vehicle count toward liquid assets ([ADR 0008](adrs/0008-license-version-1-1.md)).

## Outstanding decisions

| Decision | Impact | Proposed default | Resolve by |
|---|---|---|---|
| Contributor terms ([LIC-14](#lic-14-contributions)) | Blocks accepting outside contributions | Accept none until terms exist | Before accepting a contribution |
