# ADR 0009: Publish a user manual on GitHub Pages

**Status:** Proposed. The owner decides it.
**Date:** 2026-10-12
**Decision owner:** Nathan Slaughter
**Owner decisions:** D-10 and D-35 in the [product specification](../spec.md#decisions)

## Context

Users learn Trial Folio from the [user guide](../user-guide.md): one page of 14 numbered workflows, which grew with each release. It mixes four kinds of writing: a first walk-through, the steps for particular tasks, tables to look things up in, and the reasons behind the rules. A reader looking up an error reads past a walk-through, and a new reader meets reference tables in the middle of a first run. Release 0.4.0 adds ranking-weight variants, and each later release adds workflows, so the page keeps growing.

The guide sits in `docs/` among the specifications, which are written for agents and reviewers. [docs/README.md](../README.md) maps it as the one document there that owns no requirement.

The [Diátaxis](https://diataxis.fr/) framework sorts documentation by what the reader needs: tutorials for learning, how-to guides for a task, reference for looking things up, and explanation for understanding.

Moving the specifications to make room isn't free. Each is a verified observation, checked 2026-10-12:

- **LICENSE names `docs/disclaimers.md`,** in section 9.1, among the files every copy keeps intact, and in Appendix A, which must match it word for word. Moving it would change the license's text, which takes a new license version ([LIC-20](../licensing-policy.md#lic-20-license-changes-and-earlier-grants)).
- **Six committed schemas name `docs/contracts.md`** in their descriptions, which their models' docstrings give. Changing those descriptions would change the bytes of schema versions that tagged releases carry, which D-25 and D-33 kept unchanged for the JSON summary's earlier versions. Leaving them would leave descriptions that name a path that's gone.
- **147 files outside `docs/` name paths in it,** mostly the source modules' and tests' comments and docstrings.

The tool was checked too, on 2026-10-12:

- **[Zensical](https://zensical.org/)** is a static site generator by the Material for MkDocs team (its repository's description). Its repository gives its license as MIT. It's a Python package, so `uv` installs and locks it with the other development tools ([D-02](../spec.md#decisions)).
- **Configuration:** `zensical.toml`, whose `docs_dir` can't be the repository's root.
- **Publishing:** its documentation gives a GitHub Actions workflow that builds with `zensical build --clean`, uploads `site` as a Pages artifact, and deploys it with `actions/deploy-pages`, with the permissions `contents: read`, `pages: write`, and `id-token: write`. The repository's Pages source must be set to GitHub Actions. The site appears at `<owner>.github.io/<repository>`.
- **Unverified:** whether Zensical builds a site with several versions.

## Decision

1. **A Diátaxis manual.** User documentation is organized as a home page and four sections: tutorials, how-to guides, reference, and explanation.
2. **In `manual/`, with `docs/` unchanged.** The manual's pages are in a new top-level `manual/`. `docs/` stays the specifications, with every path unchanged.
3. **Built with Zensical,** a development dependency, configured by `zensical.toml` at the repository's root.
4. **Published on GitHub Pages,** at `promptedportfolio.github.io/trialfolio`, by a workflow that builds and deploys the site from `main`. No custom domain.
5. **D-10 is amended** to allow the site's address, which contains the brand's name, as it allows the repository's URL.
6. **The manual owns no requirement, and the specifications stay off the site.** Explanation pages link to the specifications on GitHub, and reference pages that list commands, fields, and errors are generated from their sources.
7. **A track outside any release** ([D-35](../spec.md#decisions)), specified in [user-manual.md](../user-manual.md), whose tasks the owner assigns by ID. It runs alongside 0.4.0's specification work and finishes before 0.4.0's implementation starts. 0.4.0's documentation task then writes that release's pages in the manual, and turns the user guide into a page that points to it.

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| Reorganize `docs/` into the four sections, with the specifications beside them | It moves `docs/disclaimers.md`, which takes a new license version; changes six committed schemas, or leaves them naming a path that's gone; and edits 147 files. It also mixes the specifications with the user documentation. |
| Split the user guide into four sections of Markdown files, read on GitHub | No build and no dependency, but no navigation or search beyond GitHub's file view, and readers find it by browsing the specifications' repository |
| MkDocs, with Material for MkDocs | The established generator from the team that builds Zensical. The owner chose Zensical. |
| Sphinx | Its own format is reStructuredText, and the documentation is Markdown |
| A custom domain on the brand's site | The brand would appear in more places than D-10 allows, and its domain's DNS would need changing. The Pages address needs neither. |

## Consequences

- **Two places for documentation.** `docs/` holds the specifications, for agents and reviewers. `manual/` holds the user documentation. [docs/README.md](../README.md) maps both.
- **A development dependency and a workflow.** `uv.lock` pins Zensical, and the workflow's actions are pinned by commit. The built site publishes the theme's own files, which [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md) records with their licenses.
- **The brand appears in the site's address** (D-10, as amended).
- **The site is public once it deploys,** and publishing it isn't a release ([D-08](../spec.md#decisions)). It describes `main` until the first release is distributed, unless the owner decides otherwise ([user-manual.md's open questions](../user-manual.md#open-questions)).
- **Two copies for a while.** Until 0.4.0's documentation task, the user guide and the manual describe the same workflows.
- **An account-side step.** The owner sets the repository's Pages source to GitHub Actions.

## Follow-up conditions

- **Revisit versioning** before the first release is distributed: whether the site keeps a version for each release.
- **Revisit the tool** if Zensical's license changes, or its development stops.
- **Revisit hosting** if the manual should move to the brand's site, which would need D-10 amended again.
