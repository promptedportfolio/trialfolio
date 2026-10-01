# Disclaimers and notices

**Status:** Draft. **Notice version:** 1.0.
**License:** [LICENSE](../LICENSE), `LicenseRef-NSPRL-1.0`, Draft — not yet adopted.
**Related invariant:** INV-13. **Owner decisions:** D-03 to D-08 in the [product specification](spec.md).

This document owns the text of Trial Folio's research, financial-result, warranty, and Portfolio123 notices, and says where each must appear. It also records the operating safeguards Trial Folio's behavior must follow.

LICENSE controls the legal terms. Its Appendix A contains the research notices in DSC-01 and DSC-02, and the two documents must match word for word. The [licensing policy](licensing-policy.md) covers who may use Trial Folio and how results may be shared.

This document is not a legal opinion or a legal determination. It doesn't establish that Trial Folio or its author qualifies for any regulatory exclusion or exemption.

## Requirements

| ID | Requirement |
|---|---|
| [DSC-01](#dsc-01-full-research-and-financial-result-notice) | Full research and financial-result notice text |
| [DSC-02](#dsc-02-concise-report-notice) | Concise notice text for every report |
| [DSC-03](#dsc-03-where-notices-appear) | Where each notice appears |
| [DSC-04](#dsc-04-actual-simulated-and-hypothetical-results) | Actual, simulated, and hypothetical results are labeled |
| [DSC-05](#dsc-05-warranty-and-liability-summary) | Warranty and liability summary consistent with LICENSE |
| [DSC-06](#dsc-06-portfolio123-notices) | Portfolio123 subscription and non-affiliation notices |
| [DSC-07](#dsc-07-operating-safeguards) | Operating safeguards for product behavior |
| [DSC-08](#dsc-08-statements-the-project-must-not-make) | Statements the project must not make |
| [DSC-09](#dsc-09-notice-versions) | Notice changes create a new notice version |
| [DSC-10](#dsc-10-portfolio123-terms-that-bear-on-users) | Portfolio123 terms that bear on users (verified observation) |

## Notice texts

### DSC-01 Full research and financial-result notice

Requirement. Notice version 1.0.

> This software, its documentation, examples, analyses, and outputs are provided for general research and informational purposes. They do not constitute personalized investment, financial, legal, accounting, or tax advice, an offer or solicitation concerning any security, or a recommendation to buy, sell, hold, or apply any investment strategy. Use of the software does not itself establish an advisory, fiduciary, brokerage, or client relationship with Nathan Slaughter or the project's contributors.
>
> Historical, hypothetical, simulated, and backtested results are not actual trading results unless expressly identified and supported as such. They depend on data, assumptions, modeling choices, and historical conditions and may be affected by hindsight, selection bias, overfitting, incomplete data, revisions, liquidity constraints, and costs or execution effects that are omitted or inaccurately modeled. Statistical significance does not establish future profitability or practical tradability.
>
> No result, ranking, score, comparison, example, or statement represents or promises that any person could or will realize financial gains, outperform a benchmark, avoid losses, or obtain similar results by investing in any security or applying any strategy. Past or simulated performance is not a reliable assurance of future results. Investments can lose some or all of their value; leveraged positions may produce losses beyond the initial capital.
>
> Users are responsible for independently evaluating information, obtaining appropriate professional advice, complying with applicable law and third-party terms, and making their own decisions. Nathan Slaughter does not undertake through this software to assess any user's financial situation, suitability, objectives, or tolerance for loss.

### DSC-02 Concise report notice

Requirement. Notice version 1.0.

> Research output only. Backtested and hypothetical results do not represent achievable returns. No financial gain, future performance, suitability, or protection from loss is represented or promised. This report is not personalized investment advice. See the full license and research limitations.

A user may share or publish a report they generated only while this notice stays intact and unaltered (D-07; [licensing policy LIC-10](licensing-policy.md#lic-10-reports-and-other-outputs)).

## Placement and labeling

### DSC-03 Where notices appear

| Place | Required content | Status |
|---|---|---|
| README.md | The Portfolio123 subscription notice near the top, before installation; a short statement that Trial Folio is research software whose results don't represent achievable returns, with links to this document and LICENSE; the non-affiliation notice at the end | Requirement |
| Every human-facing report, including any results screen in a later interface | The concise notice (DSC-02), and access to the full notice (DSC-01) | Requirement |
| Every human-facing report | The concise notice near the top, before any results. The full notice in a closing section, reached by an in-page link from the concise notice. The license name, `license_id`, and `notice_version` stated alongside | Proposed default |
| Machine-readable assessments and report manifests | `license_id` and `notice_version` recorded as fields, with no notice prose inserted into numeric fields; field definitions are in [contracts.md](contracts.md) | Requirement |
| CLI | The license identifier and notices available to the user; the release specification defines how | Requirement |
| Package metadata and description | License identity per [LIC-01](licensing-policy.md#lic-01-license-identity); Portfolio123 notices consistent with DSC-06 | Requirement |

Reports contain no scripts and load no external resources (D-07). Embedding the full notice keeps a shared or offline report complete without a network link. **Open question:** once a public distribution channel exists, should reports also link to a public copy of the license? Recommended default: add the link then. Resolve with the distribution-channel decision.

### DSC-04 Actual, simulated, and hypothetical results

Requirement.

- Label every result by its nature. **Backtested or simulated** results come from applying rules to historical data. **Hypothetical** results are any other constructed results, such as repricing a trade list under different costs. **Actual** results are records of real transactions that the user supplies, identified by their source.
- If a report includes actual forward observations, label which portions are actual, simulated, or hypothetical. Don't label the whole report as a backtest.
- A software-completion status, such as a run finishing successfully, must not look like an endorsement to trade. Keep execution success separate from any research criterion.
- A disclaimer doesn't cure contradictory marketing or functionality. The product's behavior and presentation must match these notices.

## Warranty and liability

### DSC-05 Warranty and liability summary

Requirement. This is a summary; LICENSE sections 14 to 16 control.

- Trial Folio and its materials and outputs are provided as is, as available, and with all faults. To the maximum extent applicable law permits, no warranty is given, including for accuracy, completeness, fitness for a purpose, or any financial benefit.
- No duty to provide support, updates, corrections, or continued data or service access is undertaken, except under a separate express written agreement.
- To the maximum extent applicable law permits, Nathan Slaughter and the contributors aren't liable for losses arising from using or relying on Trial Folio or its outputs, including investment and trading losses.
- Nothing excludes or limits liability, warranties, remedies, or rights that applicable law doesn't allow to be excluded, limited, or waived. That includes non-waivable securities-law and consumer-protection rights, and liability for fraud, willful misconduct, or gross negligence where exclusion is prohibited. If the Investment Advisers Act applies, its [anti-waiver provision](https://www.law.cornell.edu/uscode/text/15/80b-15) is not contradicted.
- The license is governed by Texas law, subject to mandatory applicable law (D-05).

These clauses are not claimed to eliminate every possible claim or to be enforceable in every jurisdiction.

## Portfolio123

### DSC-06 Portfolio123 notices

Requirement. Proposed text; keep it consistent across the README, this document, and the package description.

The README MUST place this notice near the top, before installation instructions:

> **Requires a Portfolio123 subscription.** This project works with the Portfolio123 API, which requires a Portfolio123 subscription with the appropriate access.

The README MUST end with this notice:

> **Not affiliated with Portfolio123.** This is an independent project. It is not an official Portfolio123 project and has not been reviewed by Portfolio123. No endorsement by Portfolio123 is implied.

- Don't name a Portfolio123 plan, price, or entitlement level unless it has been verified. Link to Portfolio123's own information instead.
- The README MAY note that the offline synthetic demo runs without a subscription, for as long as that remains true.
- Don't use Portfolio123 logos or styling that suggests an official relationship.
- **Proposed default:** the README and the report-sharing guidance also tell users that Trial Folio's license doesn't grant any Portfolio123 right. A report containing Portfolio123 data may need Portfolio123's consent before it is shared publicly (DSC-10).

### DSC-10 Portfolio123 terms that bear on users

Verified observation, checked 2026-10-01. Source: Portfolio123 [Terms of Use and Conditions](https://www.portfolio123.com/legal), "Last Updated February 24, 2023". The link resolves to `https://www.portfolio123.com/doc/p123_terms.html`. These are factual extracts for orientation, not legal advice about what the terms permit. Reverify before relying on them.

| Section | What the terms say | Why it matters to Trial Folio |
|---|---|---|
| §5 Content | "You may not modify, publish, transmit, transfer or sell, reproduce, create derivative works from, distribute, redistribute, store, perform, link, display, or in any way manipulate any of the Content, in whole or in part, except as expressly permitted in these terms and conditions or with the prior written consent of the Company." | Reports and other outputs that contain Portfolio123 data are covered by Portfolio123's terms, not by Trial Folio's license |
| §5 Content | "You may download or copy the Content only for your own personal use … provided that you retain on such materials all copyright and other notices contained in such Content." | Trial Folio keeps provider data on the user's machine and never redistributes it; the user's own use is governed by their Portfolio123 terms |
| §4 Research Provider account type | Covers use "in the regular course of a business or profession relating to equity research or services, including (but not limited to): website or blog, newsletters, … charts, …", and states: "Users in this category must have written permission from the Company to reproduce or redistribute any content or derived content." | Publishing results derived from Portfolio123 data, even as charts, may need Portfolio123's written permission |
| §4 High-Net-Worth Investor account type | Describes users "making investment decisions for themselves and/or family members only, and have more than $5 million in liquid financial assets" | A threshold similar to Trial Folio's Professional User asset criterion, but a separate contractual category. Neither implies the other |
| Competition | "Subscribers may not use, or assist any third party in using, any portion of the Service in any way to compete with the Service." | Relevant to any hosted or multi-user interface ([LIC-17](licensing-policy.md#lic-17-other-interfaces)) |
| §3 | Log-in credentials may not be transferred or loaned | Trial Folio never shares or pools Portfolio123 credentials. A service handling other users' credentials needs separate review |

What follows for Trial Folio:

- D-07 stands. Trial Folio's license permits users to share the reports they generate, but it grants no Portfolio123 right. Under the terms quoted above, a report containing Portfolio123 data will usually need Portfolio123's consent before public sharing. The user is responsible for obtaining it.
- Fixtures, examples, and documentation use synthetic data, not Portfolio123 content, unless Portfolio123's permission to redistribute has been confirmed.

## Operating safeguards

### DSC-07 Operating safeguards

Requirement. These govern Trial Folio's behavior, not just its wording.

The relevant legal concept is the **publisher's exclusion** from the investment-adviser definition. A disclaimer doesn't create it. The federal definition contains an exclusion for qualifying publications. SEC guidance describes impersonal content, genuine disinterested analysis, and general and regular circulation as relevant requirements. Qualification depends on actual facts and conduct. Neither software availability nor a "not advice" banner establishes it. See [15 U.S.C. § 80b-2(a)(11)(D)](https://www.law.cornell.edu/uscode/text/15/80b-2) and [SEC publisher-exclusion guidance](https://www.sec.gov/divisions/investment/noaction/2015/jonathon-hendricks-012615-202a.htm).

Texas has its own investment-adviser definition and publisher provision ([Texas Government Code § 4001.059](https://www.ssb.texas.gov/sites/default/files/2025-04/TSAeffective01-01-2022%20%28revised%20copy%29_0.pdf)). Choosing Texas law for the license doesn't displace mandatory law elsewhere.

Trial Folio MUST:

- Present itself as a general research tool, with truthful, disinterested methodology and limitations.
- Not provide individualized buy or sell instructions, suitability assessments, or investment allocations. That includes through support and through any model-assisted feature.
- Not accept trading discretion, custody, or execution authority under the personal research license.
- Keep statistical research criteria distinct from any statement that a user should deploy capital. Early releases emit no affirmative statistical or deployment judgments.
- Disclose relevant financial interests, sponsorship, referral compensation, or other conflicts in published material where applicable.

The following are new activities: personalized portfolio interpretation, event-driven securities recommendations, paid advisory services, brokerage or execution connections, and an author-hosted service producing user-parameterized results for others. Each requires separate legal analysis and Nathan Slaughter's decision before it is built ([LIC-18](licensing-policy.md#lic-18-regulatory-boundaries)).

Also review:

- publication practices and any monetization, against the actual exclusion criteria. Don't invent a publication schedule, and don't assume software release frequency proves general and regular circulation.
- whether user-parameterized outputs and later research features change how the product is characterized. Automation doesn't remove the question.

### DSC-08 Statements the project must not make

Requirement. No document, report, interface, or announcement may:

- state that Nathan Slaughter is registered, exempt, excluded, or immune from liability, unless that has been established
- describe this document, the license, or the specification as a legal determination
- present a study result as a promise, a prediction, or a representation of gains a user could realize
- present passing a backtest, a statistical test, or a software check as assurance of future superiority, or as "safe to trade"
- describe Trial Folio as open source or MIT-licensed ([LIC-01](licensing-policy.md#lic-01-license-identity))

## Versioning

### DSC-09 Notice versions

Requirement. Any change to the text of DSC-01 or DSC-02 creates a new notice version. LICENSE Appendix A and this document change together. Artifacts record the `notice_version` that applied when they were produced, so a historical report shows which notice it carried.
