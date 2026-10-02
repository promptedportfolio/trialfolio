# Third-party notices

Trial Folio's own material is licensed under the [Nathan Slaughter Personal Research License](LICENSE) (`LicenseRef-NSPRL-1.0`, draft, not yet adopted). Third-party components keep their own licenses. Nothing in Trial Folio's license restricts the rights those licenses grant, and its restrictions don't apply to any third-party file.

## Current status

No Trial Folio package, archive, executable, or image has been distributed. This repository contains no third-party code. Since R01-T06, `pyproject.toml` declares the runtime dependencies, and `uv.lock` resolves them to exact versions. This file records them, the components still planned, the development tools, and the rules for keeping this record accurate.

At each release, regenerate the component tables from the resolved dependency set, record the versions actually distributed, and reverify each license. Licenses and bundled contents can change between versions.

## Direct dependencies

| Component | Role | Status | License |
|---|---|---|---|
| p123api | Portfolio123 API wrapper; the only Portfolio123 code dependency. Pinned exactly, to the verified version in [contracts.md, plan contents](docs/contracts.md#plan-contents). | Declared since R01-T06: 3.1.0 | MIT |
| requests | HTTP client under p123api. Trial Folio's transport adapter subclasses its `HTTPAdapter` ([ADR 0006](docs/adrs/0006-observe-the-wrappers-http-exchanges.md)). Pinned exactly, to the verified version in [contracts.md, plan contents](docs/contracts.md#plan-contents). | Declared since R01-T06: 2.34.2 | Apache-2.0 |
| urllib3 | HTTP library under requests. The adapter reads its connection errors ([ADR 0006](docs/adrs/0006-observe-the-wrappers-http-exchanges.md)). Pinned exactly, to the verified version in [contracts.md, plan contents](docs/contracts.md#plan-contents). | Declared since R01-T06: 2.8.0 | MIT |
| pydantic | Contracts: validation and serialization | Planned for 0.1.0 (R01-T07) | MIT |

Record any other dependency here when it's added, for example a YAML parser or a templating library, together with every package it brings in.

**The locked runtime set** (`uv export --frozen --no-dev --no-emit-project`, checked 2026-10-02): p123api 3.1.0, requests 2.34.2, urllib3 2.8.0, certifi 2026.7.22, charset-normalizer 3.5.2, idna 3.20, and typing_extensions 4.16.0. Each is the version whose license the next table records.

Verified observation, checked 2026-10-01: p123api 3.1.0 (MIT, released 2026-08-25) depends on `requests` and `typing_extensions`, and has an optional pandas extra. `requests` in turn brings in `urllib3`, `charset-normalizer`, `idna`, and `certifi`.

## Licenses observed for the dependency set

Verified observation, checked 2026-10-01 against the versions listed. The table includes the dependencies of pydantic and p123api.

| Component (version checked) | License | Requirement when bundled |
|---|---|---|
| p123api 3.1.0, pydantic 2.13.5, pydantic-core 2.46.5, annotated-types 0.8.0, typing-inspection 0.4.4, urllib3 2.8.0, charset-normalizer 3.5.2 | MIT | Include each copyright notice and permission notice |
| idna 3.20 | BSD-3-Clause | Reproduce the copyright notice, conditions, and disclaimer; don't use the copyright holders' or contributors' names to endorse or promote Trial Folio without permission |
| requests 2.34.2 | Apache-2.0 | Provide the license text and carry the contents of its NOTICE file, currently "Requests / Copyright 2019 Kenneth Reitz"; mark any modified files as changed |
| typing_extensions 4.16.0 | PSF-2.0 | Retain the PSF license agreement and copyright notice; include a summary of changes if modified |
| certifi 2026.7.22 | MPL-2.0 | Its files remain under MPL-2.0; tell recipients where to obtain their source, and publish any modifications to those files under MPL-2.0 |

**If the p123api pandas extra is adopted**, add pandas 3.0.6 (BSD-3-Clause, with vendored components listed in its license file), python-dateutil 2.9.0.post0 (Apache-2.0 for contributions after 2017-12-01 and BSD-3-Clause for all code; satisfy both), six 1.17.0 (MIT), and numpy 2.5.3 (BSD-3-Clause and other permissive licenses).

Linux numpy wheels also bundle OpenBLAS and LAPACK (BSD-3-Clause variants), libgfortran (GPL-3.0-or-later with the GCC Runtime Library Exception), and libquadmath (LGPL-2.1-or-later). Keep numpy's bundled license file intact. When distributing those GCC libraries, make their corresponding source available as their licenses require. The runtime exception permits this combination without applying the GPL to Trial Folio's code.

## Development tools

These are never distributed. The `dev` dependency group in `pyproject.toml` installs them for development only, and a built wheel neither declares nor contains them. The build backend runs only while a wheel is built. Verified observation from each package's metadata, checked 2026-10-02, at the versions in `uv.lock`, and for hatchling at its pin:

| Component (version) | Role | License |
|---|---|---|
| pytest 9.1.1, with iniconfig 2.3.0, packaging 26.3, pluggy 1.6.0, Pygments 2.21.0, and, on Windows only, colorama 0.4.6 | Test runner | pytest, iniconfig, and pluggy MIT; packaging Apache-2.0 OR BSD-2-Clause; Pygments BSD-2-Clause; colorama BSD, by its classifier |
| ruff 0.16.10 | Formatter and linter | MIT |
| pyright 1.1.414, with nodeenv 1.11.0 | Type checker | pyright MIT; nodeenv BSD |
| nodejs-wheel-binaries 24.19.0, through pyright's `nodejs` extra | The Node.js runtime pyright runs on, so pyright never downloads one | MIT, with Node.js's own license file in its `.dist-info/licenses` |
| hatchling 1.32.4, pinned exactly in `[build-system]` | Build backend | MIT. Its build-time dependencies, resolved when a wheel is built, include pathspec (MPL-2.0), tomlkit (MIT), and trove-classifiers (Apache-2.0), checked at their current versions. |

## What each distribution form carries

- **Wheels and source distributions** declare dependencies without bundling them, so they distribute none of that code. Installers obtain each dependency from its publisher under its own license. Current wheels ship their license and notice files under `.dist-info`, so a plain installation carries them.
- **Bundled forms** do carry third-party code: vendored source, zipapps, frozen executables, notebooks containing copied code, and container images. Each must meet the "Requirement when bundled" column for every component it contains. Don't strip `.dist-info` license directories from a bundled build.
- **A desktop bundle** is a frozen executable. The bundling rules apply to everything packaged, including the Python interpreter and any GUI toolkit. JavaScript dependencies shipped with a web interface also need notices.

Publishing any of these forms is also a reserved distribution of Trial Folio's own code. See [the licensing policy](docs/licensing-policy.md).

## Container images

A container image is a separate distribution with its own conditions, distinct from the package's.

- It contains Trial Folio's code, so publishing it requires an approved channel and must carry [LICENSE](LICENSE), [CONTACT.md](CONTACT.md), and [docs/disclaimers.md](docs/disclaimers.md).
- Provide an image-level notices file covering every component in the image. That means base-image packages, the Python interpreter (PSF-2.0 plus the components listed in its license), and all installed Python packages, not only direct dependencies.
- Generate that inventory from the built image, not from the dependency declaration, and tie it to the image digest.
- Base images commonly include GPL- and LGPL-licensed programs and libraries, such as the shell and C library. Distributing the image conveys those binaries, so make their corresponding source available as those licenses require. Placing separate programs in one image is aggregation and doesn't apply their licenses to Trial Folio's code. See the [GNU FAQ on aggregation](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation).
- Don't remove operating-system copyright files or Python `.dist-info` license directories to reduce image size.
- Building or publishing the image from a separate repository or registry doesn't change these obligations. They follow the image.

## Portfolio123 software

Trial Folio works with Portfolio123's tools through their outputs and the API, not through their code. Verified observation, checked 2026-10-01; reverify before relying on it.

| Software | License observed | How Trial Folio uses it |
|---|---|---|
| [p123api-py](https://github.com/portfolio-123/p123api-py/blob/master/LICENSE) | MIT | Declared dependency, from 0.1.0. It is the only Portfolio123 code dependency. |
| [DataMiner](https://github.com/portfolio-123/dataminer/blob/master/LICENSE) | GPL-3.0 | Not used. Trial Folio doesn't read its files or include its code ([ADR 0005](docs/adrs/0005-build-on-the-portfolio123-api-only.md)). |
| [FactorMiner](https://github.com/portfolio-123/factor-miner) | No license declared | Not used in current releases. No code is included. |

- DataMiner and FactorMiner code is never imported, vendored, bundled, or ported. That includes containers, notebooks, examples, and test utilities. GPL-3.0 prohibits the further restrictions Trial Folio's license imposes. A repository without a license grants no permission to copy or adapt its code.
- Fixtures, sample configurations, and sample exports are never copied from those repositories. Trial Folio uses synthetic fixtures.
- Any later need for upstream code requires a recorded license review and Nathan Slaughter's decision before anything is copied.

Portfolio123 **data** is not a third-party software component, and nothing in this repository contains it. Portfolio123's [Terms of Use and Conditions](https://www.portfolio123.com/legal) govern its Content. They generally prohibit redistributing it without Portfolio123's prior written consent (verified observation, checked 2026-10-01; extracts in [docs/disclaimers.md](docs/disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users)). Trial Folio's fixtures and examples are synthetic.

## Future optional components

| Component | License (checked 2026-10-01) | When |
|---|---|---|
| anthropic (Python SDK) | MIT | Optional extra for runtime model features; record the version when added |
| openai (Python SDK) | Apache-2.0 | Optional extra for runtime model features; record the version and any NOTICE contents when added |

Desktop and web interface toolkits need their own license review before adoption. See [the licensing policy](docs/licensing-policy.md#lic-17-other-interfaces).
