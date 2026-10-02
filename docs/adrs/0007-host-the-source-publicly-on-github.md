# ADR 0007: Host the source publicly on GitHub

**Status:** Accepted. Supersedes decision 8 of [ADR 0004](0004-custom-personal-research-license.md), which kept the repository private until a channel was chosen, and settles the distribution channel ([LIC-15](../licensing-policy.md#lic-15-distribution-channel)).
**Date:** 2026-10-02
**Decision owner:** Nathan Slaughter
**Owner decisions:** D-08, D-10, and D-22 in the [product specification](../spec.md#decisions)

## Context

Trial Folio asks investors to trust it with their Portfolio123 API credentials and with the record of their research. People trust what they can read before they install it. The owner wants the source public, and wants to build in public, so the specifications, decisions, and history are visible too.

[ADR 0004](0004-custom-personal-research-license.md) kept the repository private until a channel consistent with the license's no-publication restriction was chosen. [LIC-15](../licensing-policy.md#lic-15-distribution-channel) listed three options: a download the author controls, a private repository with access on request, and a public GitHub repository with a narrow hosting exception.

The channels were checked against the license. Each is a verified observation, checked 2026-10-02:

- **GitHub.** [GitHub's Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#d-user-generated-content), section D.5: by making a repository public, the owner agrees "to allow others to view and 'fork'" it, and grants each GitHub user a license to "reproduce (by forking) Your Content through the Service." The grant is limited to GitHub. Forks of a public repository are public.
- **GitHub contributions.** Section D.6 licenses content added to a repository "under the same terms" as the repository's license. Under this license, that wouldn't give the licensor the right to distribute a contribution ([LIC-14](../licensing-policy.md#lic-14-contributions)).
- **PyPI.** [PyPI's terms of use](https://policies.python.org/pypi.org/Terms-of-Use/) require either a license that lets the PSF and "any mirroring facility, public or private" redistribute the package freely, or a grant to "the PSF and all other users of the web site" of "an irrevocable, worldwide, royalty-free, nonexclusive license to reproduce, distribute, transmit, display, perform, and publish the Content." A pure-Python wheel is its source, so either one would give up the reserved right to distribute.
- **Homebrew.** The main repository accepts only licenses compatible with the Debian Free Software Guidelines ([licence guidelines](https://docs.brew.sh/Licence-Guidelines)). A personal tap is a repository of formulae, each pointing at a download URL; it contains no software ([taps](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)).

A history audit on 2026-10-02 covered every commit, including the pull-request commits GitHub keeps, and the pull-request text. It found no credentials, account details, Portfolio123 data, or brand names to remove.

## Decision

1. **Public source.** The source is in a public GitHub repository, `github.com/promptedportfolio/trialfolio`.
2. **A narrow hosting exception.** LICENSE section 5.4 states that the license doesn't restrict the rights GitHub's terms grant: viewing, and reproducing on GitHub by forking. It goes no further: it grants no other use, doesn't permit publishing modifications, even in a public fork, and doesn't permit copying the code into anything else public. The license was adopted with this section, as version 1.0, so the identifier stays `LicenseRef-NSPRL-1.0`.
3. **Packages from the author's site.** Installable releases, a wheel and a source archive, are downloaded from the brand's site, `promptedportfolio.com`, delivered with LICENSE. Users install them with `uv` or `pipx` pointed at the download.
4. **No PyPI.** Trial Folio isn't uploaded to PyPI. The `Private :: Do Not Upload` classifier stays, so PyPI rejects an accidental upload.
5. **Homebrew later, perhaps.** A personal tap may follow, with a formula that points at the archive on the author's site and without prebuilt bottles. Bottles bundle dependencies, so they'd need [LIC-16](../licensing-policy.md#lic-16-bundled-builds-and-container-images)'s review first.
6. **No outside contributions yet.** Until contributor terms exist, outside pull requests are closed without being merged or copied ([LIC-14](../licensing-policy.md#lic-14-contributions)). Issues are open, with a template for each kind of contact ([CONTACT.md](../../CONTACT.md)).
7. **A public repository isn't a release.** A release is Released only when it's distributed through this channel under the adopted license (D-08).

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| A download the author controls, with no public source | Consistent with the license, but users couldn't read the code before installing it, which is the trust this decision is for. It remains the channel for packages. |
| A private repository with access on request | Consistent, but limits reach to people who ask. It suits written-permission grants, not individual investors. |
| PyPI | Its terms grant redistribution rights the license reserves, irrevocably |
| Homebrew's main repository | Accepts only free-software licenses |

## Consequences

- **Forks on GitHub can't be prevented.** LICENSE section 5.4 confines them to what GitHub's terms grant, and says so plainly, instead of pretending the platform grant doesn't exist.
- **The history is public,** including the pull-request conversations. AI review comments appear there under the owner's name, as [ai-development.md](../ai-development.md) explains.
- **The brand appears** in the repository's URL, in the README's credit line, and in installation links (D-10).
- **Contributions wait** for contributor terms. Bug reports, feature requests, questions, and documentation problems go through issues.
- **Reports' license link works.** Reports link to the LICENSE at their version's tag (D-21), which resolves once that version is tagged.

## Follow-up conditions

- **Revisit** if GitHub's terms change what a public repository grants, or if contributor terms are adopted.
- **Reverify** PyPI's terms before ever reconsidering it.
- **Check a Homebrew tap** against LIC-16 before it ships.
