# User manual

**Status:** Ready. The owner decided its [open questions](#open-questions), accepted [ADR 0009](adrs/0009-publish-a-user-manual-on-github-pages.md), and set it to Ready on 2026-10-12. UM-T01 is its first task.
**Decided by:** [D-35](spec.md#decisions), on 2026-10-12
**Depends on:** the [user guide](user-guide.md), as release [0.3.0](releases/0.3.0-experiments.md) left it. It runs alongside [0.4.0](releases/0.4.0-ranking-weights.md)'s specification work, R04-T02 to R04-T04, and finishes before 0.4.0's implementation starts: [doing the next item](../AGENTS.md#doing-the-next-item) holds 0.4.0's implementation tasks until this file's status line says each task below is done.

This is the plan for Trial Folio's user manual: the documentation for people who use Trial Folio, organized by the [Diátaxis](https://diataxis.fr/) framework into tutorials, how-to guides, reference, and explanation. Its pages are in `manual/`, at the repository's root, and [Zensical](https://zensical.org/) builds them into a site that GitHub Pages publishes at `https://promptedportfolio.github.io/trialfolio/` ([D-10](spec.md#decisions)).

It isn't a release: it has no version or tag, and publishing the site distributes no package ([D-08](spec.md#decisions)). It changes no release's scope, and adds nothing to what Trial Folio does.

The manual replaces the user guide, one page of 14 workflows that mixes a first walk-through, steps for particular tasks, tables to look things up in, and the reasons behind the rules. Release 0.4.0's documentation task writes that release's pages in the manual, and turns the user guide into a page that points to it.

## Completing this specification

Done (2026-10-12). The owner decided each [open question](#open-questions), confirmed the rules, criteria, and tasks below as written, and accepted ADR 0009. The owner removed one proposed rule, that the site names no brand: branding may be added to the manual later.

After the iterative review, the owner confirmed three of its changes the same day: [rule 2](#rules) starts at UM-T02, [doing the next item](../AGENTS.md#doing-the-next-item) holds 0.4.0's implementation tasks until this file's tasks are done, and the site's theme files are recorded as distributed. The owner also decided that the pull request that records a new tag updates the home page (rule 8), that UM-T01 adds a check of the built site to `scripts/check` (UM-AC04, UM-AC06, and UM-AC07), and that UM-T02 checks the published site and records its first deployment.

## User outcome

Someone who has never run Trial Folio follows the first tutorial from setting up to reading the demo's report. Afterward, they find the steps for a task, a setting, an output, or an error from the site's navigation and search, without reading a specification. Someone who wants to know why Trial Folio works as it does reads an explanation page, which links to the specification behind it.

## Layout

A home page and four sections. These are the proposed pages: UM-T01 may rename, merge, or add pages, and lists the pages it wrote in this file.

| Section | What it's for | Proposed pages |
|---|---|---|
| Home, `manual/index.md` | What Trial Folio is, the notices, and where to start | `index.md` |
| Tutorials, `manual/tutorials/` | Learning by doing: a guided first run that works | `first-backtest.md`, `first-experiment.md` |
| How-to guides, `manual/how-to/` | The steps for one task the reader already has | `store-credentials.md`, `re-render-a-report.md`, `compare-runs.md`, `repeat-a-case.md`, `revise-an-experiment.md`, `recover-from-an-interrupt.md`, `use-from-a-script.md`, and others UM-T01 finds |
| Reference, `manual/reference/` | Exact descriptions to look up | `cli.md`, `screen-configuration.md`, `review-configuration.md`, `experiment-configuration.md`, `outputs.md`, `errors.md`, `json-summary.md` |
| Explanation, `manual/explanation/` | Understanding: why Trial Folio works as it does | `plans-and-approval.md`, `credits-and-uncertain-charges.md`, `reproducibility.md`, `what-a-backtest-can-support.md`, and others UM-T01 finds |

### Where the user guide's sections go

UM-T01 moves each section's content to these pages, or updates this table where it places it differently.

| User guide section | Manual pages |
|---|---|
| [1. Set up](user-guide.md#1-set-up) | `tutorials/first-backtest.md` |
| [2. Acknowledge the license](user-guide.md#2-acknowledge-the-license) | `tutorials/first-backtest.md`, and `reference/cli.md` for the acknowledgment's options |
| [3. Try the demo](user-guide.md#3-try-the-demo) | `tutorials/first-backtest.md` |
| [4. Write a screen configuration](user-guide.md#4-write-a-screen-configuration) | `tutorials/first-backtest.md`, and `reference/screen-configuration.md` |
| [5. Review the plan](user-guide.md#5-review-the-plan) | `tutorials/first-backtest.md`, and `explanation/plans-and-approval.md` |
| [6. Set your credentials](user-guide.md#6-set-your-credentials) | `how-to/store-credentials.md` |
| [7. Run a backtest](user-guide.md#7-run-a-backtest) | `tutorials/first-backtest.md`, and `explanation/credits-and-uncertain-charges.md` |
| [8. Read the results](user-guide.md#8-read-the-results) | `tutorials/first-backtest.md`, `reference/outputs.md`, and `explanation/what-a-backtest-can-support.md` |
| [9. Re-render a report](user-guide.md#9-re-render-a-report) | `how-to/re-render-a-report.md` |
| [10. Compare runs with a review](user-guide.md#10-compare-runs-with-a-review) | `how-to/compare-runs.md`, and `reference/review-configuration.md` |
| [11. Run an experiment](user-guide.md#11-run-an-experiment) | `tutorials/first-experiment.md`, and `reference/experiment-configuration.md` |
| [12. Resume, repeat, or revise an experiment](user-guide.md#12-resume-repeat-or-revise-an-experiment) | `how-to/recover-from-an-interrupt.md`, `how-to/repeat-a-case.md`, and `how-to/revise-an-experiment.md` |
| [13. Use it from a script](user-guide.md#13-use-it-from-a-script) | `how-to/use-from-a-script.md`, and `reference/json-summary.md` |
| [14. When something goes wrong](user-guide.md#14-when-something-goes-wrong) | `reference/errors.md`, and `how-to/recover-from-an-interrupt.md` |

## Rules

1. **The manual owns no requirement.** It describes Trial Folio's behavior; the documents in `docs/` define it. Where a page and an owning document disagree, the owning document wins, and the page is the one to fix, as for the user guide.
2. **The specifications stay off the site.** `docs/` isn't built into the site. An explanation page links to the specification behind it on GitHub. From UM-T02 on, the site holds no hand-written copy of a requirement: the reference pages that list commands, fields, and errors are generated from their sources. Until then, they hold what UM-T01 moves into them from the user guide.
3. **The site carries the README's notices** ([DSC-03](disclaimers.md#dsc-03-where-notices-appear), [DSC-06](disclaimers.md#dsc-06-portfolio123-notices)). The home page carries all three: the Portfolio123 subscription notice before any installation step, the research notice with links to [disclaimers.md](disclaimers.md) and [LICENSE](../LICENSE), and the non-affiliation notice at its end. Every page's footer carries the non-affiliation notice and a copyright line that links to LICENSE, for a reader who arrives from search on an inner page.
4. **Every example is synthetic.** Each output a page shows, such as a report, a table, a log line, or a JSON summary, comes from the demo or the fake Portfolio123 server, and is labeled synthetic ([DSC-04](disclaimers.md#dsc-04-actual-simulated-and-hypothetical-results)). No page shows Portfolio123 data, a ranking system's name from a real account, or a credential ([REQ-11](spec.md#enduring-requirements)).
5. **A tutorial says what it needs first.** Before its first step, a tutorial says what it needs, such as a Portfolio123 subscription or credentials, and the most credits it can use. The first tutorial starts with the demo, so its first part works without a subscription.
6. **Tutorials are walked through.** From UM-T01 on, each release's verification record includes a walk-through of every tutorial under that release, against the fake Portfolio123 server, as R03-T12 walked through the user guide's experiment workflow ([0.3.0's verification record](releases/0.3.0-verification.md#the-user-guides-experiment-workflow)).
7. **A change to behavior updates the manual.** From UM-T01 on, a change to behavior a page describes updates that page in the same pull request, as AGENTS.md's [rules](../AGENTS.md#rules) ask of the documents. Until 0.4.0's documentation task turns the user guide into a page that points to the manual, the same pull request updates the guide too, where it describes that behavior.
8. **A new tag updates the home page.** The home page names the latest tag ([open questions](#open-questions)). From UM-T01 on, the pull request that records a new tag, in its release's status line, also updates the home page to name it.

## Tooling and hosting

- **Zensical,** a development dependency added with `uv add --dev zensical`, so `uv.lock` pins it. It's recorded in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)'s development tools, with every package it brings in, because the tool itself is never distributed. Its repository gives its license as MIT (verified observation, checked 2026-10-12). The built site does publish the theme's own files, such as its scripts, stylesheets, and icons, and that distributes them. So UM-T01 checks their licenses, records the site in THIRD_PARTY_NOTICES.md as a distribution form, with the files it serves and their licenses, and has the site carry the notices those licenses require: in the files' own license headers, or on a notices page the footer links to.
- **Configuration:** `zensical.toml` at the repository's root, with `docs_dir = "manual"` and `site_dir = "site"`. `/site/` is git-ignored. Zensical doesn't allow the repository's root as `docs_dir` (verified observation, zensical.org, checked 2026-10-12).
- **Building:** `uv run zensical build --clean`, locally and in the workflow, so both use the locked version. Zensical's own example workflow installs it with pip, unpinned.
- **Publishing:** `.github/workflows/docs.yml` builds the site on each push to `main`, uploads `site` as a Pages artifact, and deploys it with `actions/deploy-pages`, with the permissions `contents: read`, `pages: write`, and `id-token: write`. Its actions are pinned by commit, as the `check` workflow's are. The owner authorized adding this workflow on 2026-10-12 ([git workflow](../AGENTS.md#git-workflow)).
- **The owner's steps:** setting the repository's Pages source to GitHub Actions, in the repository's settings, while UM-T01's pull request is open. The workflow can't deploy until then, and it first deploys when that pull request merges. If the site's build moves from `scripts/check` to the docs workflow ([open questions](#open-questions)), the owner also adds the workflow's job that builds and checks the site on each pull request to the ruleset on `main`, as a required check. The pull request that moves the build asks the owner to add the job while it's open.
- **The address:** `https://promptedportfolio.github.io/trialfolio/`, the address GitHub Pages gives this repository. No custom domain.

## Acceptance criteria

If the site's build moves from `scripts/check` to the docs workflow ([open questions](#open-questions)), that workflow's required job takes `scripts/check`'s place in UM-AC01, UM-AC04, UM-AC06, and UM-AC07.

| ID | Criterion |
|---|---|
| UM-AC01 | `uv run zensical build --clean` builds the site from `manual/`, after a fresh `uv sync`, with no error. `scripts/check` builds it too, and fails when it doesn't build. |
| UM-AC02 | The docs workflow publishes the site from `main` at its address, and a page changed on `main` appears there once the workflow ends |
| UM-AC03 | Each of the user guide's 14 sections has a home in the manual, as [where the user guide's sections go](#where-the-user-guides-sections-go) gives, and no step, check, or warning the guide gives is lost |
| UM-AC04 | The home page carries the README's three notices, and every page's footer the non-affiliation notice and a copyright line that links to LICENSE, as [rule 3](#rules) gives. `scripts/check` checks the built site's footers, and fails when a page's footer lacks the non-affiliation notice or the link to LICENSE. |
| UM-AC05 | Every output a page shows is synthetic and labeled so. No page holds Portfolio123 data, a real account's ranking system name, or a credential. |
| UM-AC06 | Every link between pages resolves, and every link to a specification goes to its file on GitHub. `scripts/check` checks the built site's links between pages, and fails when one doesn't resolve. |
| UM-AC07 | Opening any page of the built site loads nothing from another host. `scripts/check` checks the built site, and fails when a page loads a resource from another host, such as a script, stylesheet, font, or image. |
| UM-AC08 | The generated reference pages match the CLI's help, the committed schemas, and [contracts.md](contracts.md)'s errors, and `scripts/check` fails when they don't |

## Tasks

The owner assigns these by ID. They aren't next items: [doing the next item](../AGENTS.md#doing-the-next-item) goes through the release files only. Branches follow the same form, such as `docs/um-t01-manual-site`.

| ID | Task | Depends on |
|---|---|---|
| UM-T01 | **Build the site, and move the user guide's content into it.** Add Zensical, `zensical.toml`, the git-ignore entry, and `.github/workflows/docs.yml`. Record Zensical in THIRD_PARTY_NOTICES.md's development tools, and the site there as a distribution form, with the theme's files it serves and their licenses, and have the site carry those files' notices ([tooling and hosting](#tooling-and-hosting)). Have `scripts/check` build the site, and check the built site: it fails when a page loads a resource from another host, such as a script, stylesheet, font, or image (UM-AC07), when a page's footer lacks the non-affiliation notice or the link to LICENSE (UM-AC04), or when a link between pages doesn't resolve (UM-AC06). Turn off anything the theme loads from another host by default, such as web fonts. Write the home page and the four sections' pages from the user guide's content, as [where the user guide's sections go](#where-the-user-guides-sections-go) gives, with the explanation pages, and list the pages written in this file. The reference pages it writes are hand-written until UM-T02 generates them ([rule 2](#rules)). Add a line at the top of the user guide that points to the manual. Add the site's row to [DSC-03](disclaimers.md#dsc-03-where-notices-appear). Link to the site's address, `https://promptedportfolio.github.io/trialfolio/`, from the README's documentation section, [docs/README.md](README.md), and AGENTS.md's reading order: the links resolve once the site first deploys. In AGENTS.md, have a change to behavior update the manual, and the user guide too until 0.4.0's documentation task ([rule 7](#rules)). Ask the owner to set the Pages source to GitHub Actions while its pull request is open, so the deployment after its merge succeeds. It's done when its pull request merges. | Status Ready |
| UM-T02 | **Generate the reference pages:** the commands and their options from the CLI's help, each configuration's and output's fields from the committed schemas, and the errors from [contracts.md](contracts.md)'s table, with a drift check that `scripts/check` runs, as it runs `scripts/schemas --check`. contracts.md's table gives no remedy, so the user guide's "What to do" for each error stays in the manual, beside the generated codes or on a how-to page, and none is lost (UM-AC03). A remedy is advice, not a requirement, so rule 2 allows it by hand. Check UM-AC02 against the published site, which UM-T01's merge first deploys, and record the first deployment in this file: its date and the docs workflow's run. | UM-T01 |

## Open questions

The owner decided each question on 2026-10-12. The first five confirmed their defaults, which are now requirements. The last one's default holds for UM-T01, but the owner decided it isn't a requirement. Each alternative is kept for the record.

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| Which version of Trial Folio does the site describe? | A reader running a tagged version could read about behavior on `main` that their version lacks | `main`, until the first release is distributed from the brand's site ([D-22](spec.md#decisions)). The home page says so, and names the latest tag. Whether Zensical builds a site with several versions is unverified: check it before that release. | Confirmed by the owner (2026-10-12). Revisit before the first distributed release. |
| What happens to the user guide between UM-T01 and 0.4.0's documentation task? | Two copies of the same instructions could drift apart | UM-T01 leaves it as it is, except for a line at its top that points to the manual. A change to behavior both describe updates both. 0.4.0's documentation task turns the guide into a page that points to the manual. | Confirmed by the owner (2026-10-12) |
| Where do the notices go on the site? | A reader who arrives from search lands on an inner page, not the home page | The home page carries the README's three notices: the subscription notice before any installation step, the research notice with links to [disclaimers.md](disclaimers.md) and [LICENSE](../LICENSE), and the non-affiliation notice at its end. Every page's footer carries the non-affiliation notice and a copyright line that links to LICENSE. | Confirmed by the owner (2026-10-12) |
| Does the site load anything from another host? | Readers' privacy, and whether a page loads when that host doesn't | No. UM-T01 checks whether Zensical's theme loads fonts or scripts from other hosts by default, and turns that off. | Confirmed by the owner (2026-10-12) |
| Is the site's build checked before a merge? | A page that doesn't build would otherwise fail only the deployment, after the merge | Yes: `scripts/check` builds the site, so the required `check` jobs fail on a manual that doesn't build. If the build slows `scripts/check` noticeably, the build and the check of the built site move together into a job of the docs workflow that runs on each pull request, and the owner adds that job to the ruleset on `main` as a required check. | Confirmed by the owner (2026-10-12) |
| Does the site carry the brand's credit line? | D-10 allows the credit line in the README only | No. The site's address is the only place the brand appears. | Decided by the owner (2026-10-12): UM-T01 adds no credit line or other branding. That isn't a requirement: the owner may add branding to the manual later, amending [D-10](spec.md#decisions) to allow it. |
