# User manual

**Status:** Ready. The owner decided its [open questions](#open-questions), accepted [ADR 0009](adrs/0009-publish-a-user-manual-on-github-pages.md), and set it to Ready on 2026-10-12. UM-T01 (2026-10-12) built the site, and moved the user guide's content into it. UM-T02 (2026-10-12) generated the reference pages from their sources. Each task below is done, so [doing the next item](../AGENTS.md#doing-the-next-item) no longer holds 0.4.0's implementation.
**Decided by:** [D-35](spec.md#decisions), on 2026-10-12
**Depends on:** the [user guide](user-guide.md), as release [0.3.0](releases/0.3.0-experiments.md) left it. It runs alongside [0.4.0](releases/0.4.0-ranking-weights.md)'s specification work, R04-T02 to R04-T04, and finishes before 0.4.0's implementation starts: [doing the next item](../AGENTS.md#doing-the-next-item) holds 0.4.0's implementation tasks until this file's status line says each task below is done.

This is the plan for Trial Folio's user manual: the documentation for people who use Trial Folio, organized by the [Diátaxis](https://diataxis.fr/) framework into tutorials, how-to guides, reference, and explanation. Its pages are in `manual/`, at the repository's root, and [Zensical](https://zensical.org/) builds them into a site that GitHub Pages publishes at `https://promptedportfolio.github.io/trialfolio/` ([D-10](spec.md#decisions)).

It isn't a release: it has no version or tag, and publishing the site distributes no package ([D-08](spec.md#decisions)). It changes no release's scope, and adds nothing to what Trial Folio does.

The manual replaces the user guide, one page of 14 workflows that mixes a first walk-through, steps for particular tasks, tables to look things up in, and the reasons behind the rules. Release 0.4.0's documentation task writes that release's pages in the manual, and turns the user guide into a page that points to it.

## Completing this specification

Done (2026-10-12). The owner decided each [open question](#open-questions), confirmed the rules, criteria, and tasks below as written, and accepted ADR 0009. The owner removed one proposed rule, that the site names no brand: branding may be added to the manual later.

After the iterative review, the owner confirmed three of its changes the same day: [rule 2](#rules) starts at UM-T02, [doing the next item](../AGENTS.md#doing-the-next-item) holds 0.4.0's implementation tasks until this file's tasks are done, and the site's theme files are recorded as distributed. The owner also decided that the pull request that records a new tag updates the home page (rule 8), that UM-T01 adds a check of the built site to `scripts/check` (UM-AC04, UM-AC06, and UM-AC07), and that UM-T02 checks the published site and records its first deployment. Then the owner amended the fallback in the [open question](#open-questions) on the site's build: the build and the check of the built site move together into a job of the docs workflow, which the owner makes a required check.

## User outcome

Someone who has never run Trial Folio follows the first tutorial from setting up to reading the demo's report. Afterward, they find the steps for a task, a setting, an output, or an error from the site's navigation and search, without reading a specification. Someone who wants to know why Trial Folio works as it does reads an explanation page, which links to the specification behind it.

## Layout

A home page and four sections. UM-T01 wrote these pages (2026-10-12), and UM-T02 added `reference/output-fields.md` (2026-10-12). A later task that renames, merges, or adds a page updates this table.

| Section | What it's for | Pages |
|---|---|---|
| Home, `manual/index.md` | What Trial Folio is, the notices, and where to start | `index.md` |
| Tutorials, `manual/tutorials/` | Learning by doing: a guided first run that works | `first-backtest.md`, `first-experiment.md` |
| How-to guides, `manual/how-to/` | The steps for one task the reader already has | `store-credentials.md`, `re-render-a-report.md`, `compare-runs.md`, `recover-from-an-interrupt.md`, `repeat-a-case.md`, `revise-an-experiment.md`, `use-from-a-script.md` |
| Reference, `manual/reference/` | Exact descriptions to look up | `cli.md`, `screen-configuration.md`, `review-configuration.md`, `experiment-configuration.md`, `outputs.md`, `output-fields.md`, `errors.md`, `json-summary.md` |
| Explanation, `manual/explanation/` | Understanding: why Trial Folio works as it does | `plans-and-approval.md`, `credits-and-uncertain-charges.md`, `reproducibility.md`, `what-a-backtest-can-support.md` |
| Third-party notices, `manual/third-party-notices.md` | The licenses of the theme's files the site serves ([tooling and hosting](#tooling-and-hosting)), linked from every page's footer | `third-party-notices.md` |

### Where the user guide's sections go

UM-T01 moved each section's content to these pages (2026-10-12). A page that holds only part of a section links to the page that holds the rest.

| User guide section | Manual pages |
|---|---|
| [1. Set up](user-guide.md#1-set-up) | `tutorials/first-backtest.md`, and `reference/cli.md` for `trialfolio init` |
| [2. Acknowledge the license](user-guide.md#2-acknowledge-the-license) | `tutorials/first-backtest.md`, `reference/cli.md` for the acknowledgment's options, and `how-to/use-from-a-script.md` |
| [3. Try the demo](user-guide.md#3-try-the-demo) | `tutorials/first-backtest.md` |
| [4. Write a screen configuration](user-guide.md#4-write-a-screen-configuration) | `tutorials/first-backtest.md`, `reference/screen-configuration.md`, and `explanation/reproducibility.md` |
| [5. Review the plan](user-guide.md#5-review-the-plan) | `tutorials/first-backtest.md`, `explanation/plans-and-approval.md`, and `how-to/use-from-a-script.md` |
| [6. Set your credentials](user-guide.md#6-set-your-credentials) | `how-to/store-credentials.md`, and `tutorials/first-backtest.md` for the prompt |
| [7. Run a backtest](user-guide.md#7-run-a-backtest) | `tutorials/first-backtest.md`, and `explanation/credits-and-uncertain-charges.md` |
| [8. Read the results](user-guide.md#8-read-the-results) | `tutorials/first-backtest.md`, `reference/outputs.md`, and `explanation/what-a-backtest-can-support.md` |
| [9. Re-render a report](user-guide.md#9-re-render-a-report) | `how-to/re-render-a-report.md`, and `reference/outputs.md` |
| [10. Compare runs with a review](user-guide.md#10-compare-runs-with-a-review) | `how-to/compare-runs.md`, `reference/review-configuration.md`, and `reference/outputs.md` |
| [11. Run an experiment](user-guide.md#11-run-an-experiment) | `tutorials/first-experiment.md`, `reference/experiment-configuration.md`, `reference/outputs.md`, and `how-to/recover-from-an-interrupt.md` |
| [12. Resume, repeat, or revise an experiment](user-guide.md#12-resume-repeat-or-revise-an-experiment) | `how-to/recover-from-an-interrupt.md`, `how-to/repeat-a-case.md`, `how-to/revise-an-experiment.md`, and `explanation/credits-and-uncertain-charges.md` |
| [13. Use it from a script](user-guide.md#13-use-it-from-a-script) | `how-to/use-from-a-script.md`, `reference/json-summary.md`, and `reference/errors.md` for the exit codes |
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

The owner assigns these by ID. They aren't next items: [doing the next item](../AGENTS.md#doing-the-next-item) goes through the release files and the readability refactor's tasks only. Branches follow the same form, such as `docs/um-t01-manual-site`.

| ID | Task | Depends on |
|---|---|---|
| UM-T01 | **Build the site, and move the user guide's content into it.** Add Zensical, `zensical.toml`, the git-ignore entry, and `.github/workflows/docs.yml`. Record Zensical in THIRD_PARTY_NOTICES.md's development tools, and the site there as a distribution form, with the theme's files it serves and their licenses, and have the site carry those files' notices ([tooling and hosting](#tooling-and-hosting)). Have `scripts/check` build the site, and check the built site: it fails when a page loads a resource from another host, such as a script, stylesheet, font, or image (UM-AC07), when a page's footer lacks the non-affiliation notice or the link to LICENSE (UM-AC04), or when a link between pages doesn't resolve (UM-AC06). Turn off anything the theme loads from another host by default, such as web fonts. Write the home page and the four sections' pages from the user guide's content, as [where the user guide's sections go](#where-the-user-guides-sections-go) gives, with the explanation pages, and list the pages written in this file. The reference pages it writes are hand-written until UM-T02 generates them ([rule 2](#rules)). Add a line at the top of the user guide that points to the manual. Add the site's row to [DSC-03](disclaimers.md#dsc-03-where-notices-appear). Link to the site's address, `https://promptedportfolio.github.io/trialfolio/`, from the README's documentation section, [docs/README.md](README.md), and AGENTS.md's reading order: the links resolve once the site first deploys. In AGENTS.md, have a change to behavior update the manual, and the user guide too until 0.4.0's documentation task ([rule 7](#rules)). Ask the owner to set the Pages source to GitHub Actions while its pull request is open, so the deployment after its merge succeeds. It's done when its pull request merges. | Status Ready |
| UM-T02 | **Generate the reference pages:** the commands and their options from the CLI's help, each configuration's and output's fields from the committed schemas, and the errors from [contracts.md](contracts.md)'s table, with a drift check that `scripts/check` runs, as it runs `scripts/schemas --check`. contracts.md's table gives no remedy, so the user guide's "What to do" for each error stays in the manual, beside the generated codes or on a how-to page, and none is lost (UM-AC03). A remedy is advice, not a requirement, so rule 2 allows it by hand. Check UM-AC02 against the published site, which UM-T01's merge first deploys, and record the first deployment in this file: its date and the docs workflow's run. | UM-T01 |

## What UM-T01 settled

**Details from UM-T01 (2026-10-12), confirmed by the owner the same day.** Each is a detail the specification left open:

1. **The footer.** `overrides/partials/copyright.html`, in the theme's `custom_dir`, replaces the theme's footer text on every page. It holds:
   - the copyright line, "Copyright © 2026 Nathan Slaughter", naming the license with a link to LICENSE on `main`;
   - a link to the site's third-party notices;
   - the non-affiliation notice, as the README gives it.

   It leaves out the theme's "Made with Zensical" link. The alternative is to keep that link.
2. **The theme files' notices.** The theme's scripts and stylesheets carry no license headers. So the notices are on a page of their own, `third-party-notices.md`, linked from every footer. Since 2026-10-14 it isn't in the navigation, whose tabs are the home page and the manual's four sections, as the owner decided that day. It holds each license's full text, or Font Awesome's attribution. [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md#the-user-manuals-site) records the site as a distribution form, and asks a pull request that changes Zensical's version to check the files the site serves again.
3. **The configuration** in `zensical.toml`:
   - `strict = true`, so a broken link or anchor fails the build;
   - `font = false`, so pages use the reader's system fonts;
   - no `repo_url`, so the header has no link to the repository. With one, the theme's script would ask GitHub's API for the repository's facts from each reader's browser.
   - the features `navigation.sections` and `content.code.copy`. On 2026-10-14 the site gained more of the theme's features, colors, a logo, and a favicon of its own, as [the site's theme](#the-sites-theme) gives.
4. **The check of the built site** is `scripts/check_manual.py`, with its tests in `tests/manual/`.
   - pyright now checks `scripts/` too.
   - `scripts/check` removes `site/` before it builds, so a removed page can't linger and pass.
   - The check reads the built HTML and the stylesheets. It doesn't run the theme's script, which can fetch from other hosts for features the site doesn't use: diagrams, image lightboxes, runnable Python code blocks, a repository's facts, and a polyfill for a browser without `ResizeObserver`.
   - The check also fails on a page whose markup turns on diagrams, image lightboxes, or runnable Python code blocks, since the theme's script would then fetch from another host. The owner decided this on 2026-10-12, after the review of UM-T01's pull request. The other two features have no such markup: a repository's facts need a `repo_url`, which the configuration doesn't set, and the polyfill depends on the reader's browser.
5. **The docs workflow:**
   - It builds on Python 3.12, with the `check` workflow's version of `uv`.
   - It runs the check of the built site again before publishing, because a pull request can merge without being up to date with `main`.
   - It runs `actions/configure-pages`, as Zensical's own workflow does.
6. **The home page** names `v0.2.1` as the latest tag. It sends the reader of a tagged copy to the user guide at that tag.
7. **Where the user guide was wrong, or incomplete,** the manual follows the owning documents. As the owner decided, UM-T01 corrected the guide in the same places:
   - `--json` gives no summary on a usage error, which exits 2 ([contracts.md](contracts.md#cli-behavior)).
   - The workspace's `screen.yaml` has its `purpose` line commented out.
   - An experiment's `sessions/<s>/` is written only for a run that passed its checks and its approval.
   - Only `trialfolio run` warns about `SSLKEYLOGFILE`.
   - `environment.unsupported` also covers an importable `simplejson`, whose remedy isn't `uv sync`.
   - The errors reference lists all 21 codes, including the three the guide's table leaves out: `license.not_acknowledged`, `artifact.unknown_schema_version`, and `provider.request_rejected`. The guide's table now has the last two. Section 2 covers the first.

   The review of UM-T01's pull request found four more places, which the manual and the guide now both correct. The owner confirmed them on 2026-10-12:
   - The same plan hash also needs the same versions of Trial Folio, `p123api`, `requests`, and `urllib3`, so upgrading any of them changes it.
   - A repeat's confirmation is used only once the repeat may have reached Portfolio123. A repeat that sent nothing, such as one whose authentication failed, leaves it unused.
   - Exit 3 also covers `plan.changed`: an experiment's changed plan whose revision wasn't approved with a reason.
   - `input.not_found` also covers a configuration file that `trialfolio run` or `trialfolio review` couldn't read.

**contracts.md's exit codes,** corrected by the owner's decision on 2026-10-12. The exit-code table in [CLI behavior](contracts.md#cli-behavior) now names `plan.changed` under exit 3, as the [errors](contracts.md#errors) table and the code already did.

**UM-T01's scope,** decided by the owner on 2026-10-12. UM-T01 moves the user guide's content, checked against the owning documents and the code, and corrects the guide where it's wrong. It doesn't audit all present behavior for pages the guide lacks: UM-T02's generated reference pages cover every command, field, and error.

**Deferred by the owner** (2026-10-12): an explanation page on credentials and local data, until a later pull request. It would explain why credentials come only from environment variables, why proxy settings, `.netrc`, and `SSLKEYLOGFILE` are ignored, and why logs stay local. The guide gives the steps, but has no such content to move.


## What UM-T02 settled

**Details from UM-T02 (2026-10-12), confirmed by the owner the same day.** Each is a detail the specification left open:

1. **The generator and its markers.** `scripts/manual_reference.py` generates the reference pages' tables, and holds the registry of what generates each.
   - Each generated region of a page is between `<!-- generated: <region-id> -->` and `<!-- end generated: <region-id> -->`, each on a line of its own. Everything outside them is hand-written.
   - `uv run python scripts/manual_reference.py` rewrites the regions in place, and `--check` writes nothing. `scripts/check` runs the check in its "Manual" step, before the site's build. It fails when a region differs from what its source generates, a page names an unknown region, a registered region is on no page or on more than one, the markers are unbalanced or nested, or a hand-written cell is empty. A rewrite writes nothing while a marker is wrong.
   - The sources: the CLI's parser, `_parser` in `src/trialfolio/cli.py`; the committed schemas in `schemas/`; and [contracts.md](contracts.md)'s "Errors" table and its exit-code table in "CLI behavior".
   - The output depends on the sources only. Usage lines are wrapped as for an 80-column terminal, without color, and argparse's own help texts are read in English, whatever the terminal, the environment, or the locale. The parser is built with a placeholder version, and nothing generated holds a date.
   - Each schema fact is written in plain words: "not all whitespace" for the pattern of text that isn't all whitespace, and "at most 200 characters" for a `maxLength` of 200, for example. A pattern, format, or keyword the generator has no words for fails it, rather than being dropped.
   - Each object of a schema has a table of its own, linked from the key that holds it, under a generated heading with a fixed anchor, the region's ID.
   - On `cli.md`, each command's table leaves out `-h` and `--json`, which the table of options every command takes lists. A flag's default reads "Off", and an option without one "None".
   - On `outputs.md`, the CSV files' columns are described as their row schemas give them, read back: a null is an empty cell, and a list's items are separated by semicolons.
   - Its tests are `tests/manual/test_manual_reference.py`.
2. **The hand-written column, kept by key.** Some tables end with one hand-written column: What to do, on `errors.md`; What it's for, on the configuration pages; and What it holds, in `json-summary.md`'s top-level table. Regenerating keeps each of its cells, matched by the row's key in the first column. A row whose key is new gets an empty cell, which fails the check until it's written, and a row whose key left the source goes, with its cell. The generated columns are never edited by hand: the check finds that too.
3. **What stays hand-written.** The text outside the regions: on `cli.md`, which commands need the license's acknowledgment and which send anything, the plan and approval, `--out`, `--revision-reason`, `--repeat`, credentials, the license acknowledgment, the environment variables, stdout and stderr, and the files `trialfolio init` writes; on the configuration pages, the examples, which keys are sent to Portfolio123, quoting, comments, how values are written, the verified values, and the rules that span keys; on `outputs.md`, each directory's files and the notes on rows and flags; on `json-summary.md`, which command gives which `ids` and `counts`, what each of `outputs`' roles names, the example, and the schema versions; and on `errors.md`, the remedies, "More about some codes", what a failure leaves, and the logs. Where a generated table now gives a fact the hand-written text gave, that text went, and each fact it gave that its source doesn't stayed, in a hand-written cell or the page's prose (UM-AC03).
4. **The new page,** `reference/output-fields.md`, "Output file fields": the fields of each JSON file Trial Folio writes, at the version it writes now. A screen run's plan and records are 1.0.0, and an experiment's 1.1.0, as `src/trialfolio/contracts/schema_files.py` gives. Each file's section links to its section of contracts.md, and its region links to its schema. A test runs `trialfolio demo`, a review of two demo runs, and the core's synthetic experiment, offline, and checks that each JSON file they write is valid against the model of the schema its section names, at that schema's version.
5. **The meanings copied from contracts.md, with absolute links.** `errors.md` copies each meaning as contracts.md gives it, with one change: each link leads to its file on GitHub, such as `https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#the-lock`. The user guide's "What happened" column went: each fact it gave that the meaning doesn't is in What to do, or in "More about some codes". Nothing is filtered out, so the page also carries contracts.md's clause on 0.4.0's ranking snapshots under `input.not_a_run`, which says "From 0.4.0", and its spec-level detail, such as the core's demo client under `output.not_empty`.
6. **The cross-check with `EXIT_CODES`.** The generator fails when contracts.md's errors table and `EXIT_CODES` in `src/trialfolio/errors.py` disagree, in either direction: a code only one of them has, or another exit code. It also fails when the exit-code table lacks an error's exit code or 0, or has one that no error has.

**Deferred by the owner** (2026-10-12): rewording the schema descriptions that name the specification's internals, until a later pull request. About six descriptions on the generated pages do, such as "P-13's default rebalance variant", "(R03-AC08)", and "a flag in `FLAGGING`". They come from the models' docstrings in `src/`, and rewording one behind an earlier schema version, such as the JSON summary's 1.0.0, would change a frozen schema's bytes. Until then, the generated pages give them as the schemas do.

**The first deployment (UM-T02).** The docs workflow's run [38288103983](https://github.com/promptedportfolio/trialfolio/actions/runs/38288103983) deployed the site on 2026-10-12, from 4a3bd93, the squash merge of #78. It started at 18:01:15Z, and ended successfully at 18:02:50Z. **UM-AC02 checked (2026-10-12):** each of the 33 files of a local build of 4a3bd93 was fetched from the published address, and each was byte-identical to it.

## The site's theme

On 2026-10-14 the site gained colors, more of the theme's navigation, a logo, and a favicon of its own. It still loads nothing from another host (UM-AC07), and it serves the same theme files as before ([THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md#the-user-manuals-site)). The owner decided the variant, the colors, the logo and the favicon, and the notices page's place on 2026-10-14, and that the change needs no task. In `zensical.toml`:

- **The variant** is `modern`, the theme's default.
- **The colors** are the theme's `teal`, in a light scheme and a dark one. They follow the reader's system setting, until the reader chooses one with the switch in the header. The system setting's entry names the colors too, so a page starts in teal before the theme's script runs, and stays teal without it.
- **The navigation:**
  - the home page and the four sections are tabs across the top (`navigation.tabs`);
  - each page shows the path to it (`navigation.path`), links to the pages before and after it (`navigation.footer`), and has a button back to the top (`navigation.top`);
  - a link loads the next page without reloading the whole site (`navigation.instant` and `navigation.instant.prefetch`), from this site only;
  - the address and the list of the page's sections follow the section in view (`navigation.tracking` and `toc.follow`);
  - search highlights the words it found on the page it opens (`search.highlight`).
- **The logo** is Lucide's `flask-conical` icon. The favicon, `manual/assets/favicon.svg`, is the same icon, in the theme's teal primary color: `#009485`, and its light shade, `#26a699`, when the browser is dark. The file names those values itself, so a change to the primary color changes them there by hand. The theme's own favicon is still served, though no page uses it, so its notice stays.
- **The third-party notices page** isn't in the navigation. Every page's footer links to it, as [tooling and hosting](#tooling-and-hosting) requires, and that link is now the only one to it. So `scripts/check_manual.py` also fails when a page's footer lacks the link. The review of this change added that check on 2026-10-14, and the owner confirmed it the same day.

## Open questions

The owner decided each question on 2026-10-12. The first five confirmed their defaults, which are now requirements. The last one's default holds for UM-T01, but the owner decided it isn't a requirement. Each alternative is kept for the record.

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| Which version of Trial Folio does the site describe? | A reader running a tagged version could read about behavior on `main` that their version lacks | `main`, until the first release is distributed from the brand's site ([D-22](spec.md#decisions)). The home page says so, and names the latest tag. Whether Zensical builds a site with several versions is unverified: check it before that release. | Confirmed by the owner (2026-10-12). Revisit before the first distributed release. |
| What happens to the user guide between UM-T01 and 0.4.0's documentation task? | Two copies of the same instructions could drift apart | UM-T01 leaves it as it is, except for a line at its top that points to the manual. A change to behavior both describe updates both. 0.4.0's documentation task turns the guide into a page that points to the manual. | Confirmed by the owner (2026-10-12) |
| Where do the notices go on the site? | A reader who arrives from search lands on an inner page, not the home page | The home page carries the README's three notices: the subscription notice before any installation step, the research notice with links to [disclaimers.md](disclaimers.md) and [LICENSE](../LICENSE), and the non-affiliation notice at its end. Every page's footer carries the non-affiliation notice and a copyright line that links to LICENSE. | Confirmed by the owner (2026-10-12) |
| Does the site load anything from another host? | Readers' privacy, and whether a page loads when that host doesn't | No. UM-T01 checks whether Zensical's theme loads fonts or scripts from other hosts by default, and turns that off. | Confirmed by the owner (2026-10-12) |
| Is the site's build checked before a merge? | A page that doesn't build would otherwise fail only the deployment, after the merge | Yes: `scripts/check` builds the site, so the required `check` jobs fail on a manual that doesn't build. If the build slows `scripts/check` noticeably, the build and the check of the built site move together into a job of the docs workflow that runs on each pull request, and the owner adds that job to the ruleset on `main` as a required check. | Confirmed by the owner (2026-10-12), who amended the fallback the same day |
| Does the site carry the brand's credit line? | D-10 allows the credit line in the README only | No. The site's address is the only place the brand appears. | Decided by the owner (2026-10-12): UM-T01 adds no credit line or other branding. That isn't a requirement: the owner may add branding to the manual later, amending [D-10](spec.md#decisions) to allow it. |
