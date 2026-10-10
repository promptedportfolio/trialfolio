# Graphical prototype

**Status:** Draft. **Don't build from it yet.** GP-T01 completes it, and then the owner sets it to Ready.
**Decided by:** [D-29](spec.md#decisions), on 2026-10-07
**Depends on:** the saved runs of [0.1.0](releases/0.1.0-api-execution.md). It runs alongside 0.3.0's specification work and doesn't wait for it.

This is the read-only prototype that the [roadmap's graphical interface prerequisites](roadmap.md#graphical-interface-prerequisites) call for. It isn't a release: it has no version or tag, and it's never distributed. Its job is evidence:

- **For the toolkit ADR** that [LIC-17](licensing-policy.md#lic-17-other-interfaces) requires before any interface ships. Two candidate toolkits are each built to the same criteria, so the ADR compares them on real builds.
- **For 0.4.0's charts.** Whether a saved run holds the series that equity and drawdown charts need, as the roadmap's 0.4.0 target requires.
- **For the public core.** Which core functions an interface other than the CLI calls. Those are the functions a separately distributed interface would need made public ([public contract boundary](contracts.md#public-contract-boundary)).

0.4.0's specification decides whether any of the prototype's code is kept.

## Completing this specification

GP-T01 completes it. It reads [AGENTS.md](../AGENTS.md), [spec.md](spec.md), LIC-15 to LIC-17 in [licensing-policy.md](licensing-policy.md), and the contracts.md sections on [saved runs](contracts.md#artifact-storage), [metrics](contracts.md#metrics-and-missing-values), the [screen-backtest response](contracts.md#p123api-screen-backtest-version-1), and [reports](contracts.md#reports). Then it:

1. **Proposes two toolkit candidates** that each package a macOS app, with a license check of everything each would bundle. The check covers the toolkit's interpreter and libraries, any web view's JavaScript, and each module the prototype would use. A module, such as a charting module, can be licensed differently from the rest of its toolkit. A candidate that fails the check is replaced, not built.
2. **Says how each candidate is packaged** as a macOS app, and with which tool.
3. **Resolves the open questions,** or confirms their defaults.
4. **Pairs each acceptance criterion with a check,** and gives the verification commands.

It's Ready when every criterion has a check, every open question is resolved or has a default the owner confirmed, and the owner has agreed.

## User outcome

On a Mac, the owner launches a packaged app without a terminal and opens a saved run. The app shows the run's metrics, an equity chart, and a drawdown chart, and then quits. Nothing is sent, and nothing in the run changes.

## Included scope

- A macOS app for each of the two candidates, packaged so that it launches from Finder. Launching it doesn't need a terminal, a server started by hand, or a frontend development toolchain on the Mac that runs it.
- Opening one saved run, written by `trialfolio run` or `trialfolio demo`, from a folder chosen in the system's folder dialog.
- A metrics table, an equity chart of the strategy and its benchmark, and a drawdown chart of the strategy.
- The notices that [LIC-17](licensing-policy.md#lic-17-other-interfaces) requires on any screen that shows results.
- A record of what each build found, written into this file.

## Explicit exclusions

- Any request to Portfolio123, any credentials, and any plan or approval.
- Experiments, which don't exist until 0.3.0, and reviews.
- Exporting, editing, or comparing runs.
- Platforms other than macOS. 0.4.0's specification chooses the supported platforms.
- Distribution of any kind, including code signing and notarization. The built apps stay on the owner's Mac and are never committed or uploaded.
- Any change to the `trialfolio` package's dependencies, CLI, or outputs.

## Referenced requirements

- **Product:** [REQ-03](spec.md#enduring-requirements), the core that doesn't depend on the CLI. [REQ-06](spec.md#enduring-requirements), logs. [REQ-11](spec.md#enduring-requirements): no raw provider data committed. [REQ-13](spec.md#enduring-requirements): process success kept apart from usefulness. [INV-03 and INV-08](spec.md#enduring-invariants): unavailable values are never shown as zero, and limitations stay visible.
- **Licensing and notices:** [LIC-15 to LIC-17](licensing-policy.md), and [DSC-04](disclaimers.md#dsc-04-actual-simulated-and-hypothetical-results) for synthetic results.

## Required behavior

1. **Open read-only.** The app reads the chosen folder through the core's saved-run reader, `read_run` in `src/trialfolio/runs.py`. It writes nothing into that folder.
2. **Show every metric.** Every row of `metrics.csv` appears in its order, with its unit and the digits the source gave. An unavailable value is shown as unavailable, with its reason, and never as zero.
3. **Draw the charts from the saved response.**
   - **Equity:** the strategy's and the benchmark's levels of 100 invested from the response's `chart` arrays ([the screen-backtest response](contracts.md#p123api-screen-backtest-version-1)).
   - **Drawdown:** calculated from the strategy's daily levels as the decline from the highest level so far. It's labeled as calculated, with its method, because Portfolio123 doesn't report the series.
   - A chart whose arrays are missing or unreadable says it's unavailable, and the metrics still show.
4. **Label what it shows.** It shows the concise notice and gives access to the full notice. Statistical validation and trading readiness read "Not assessed". A synthetic run, such as the demo's, is labeled synthetic wherever its values appear, and its values are never called Portfolio123's.
5. **Send nothing.** The app opens no network connection and reads no credentials or environment variables for them.

## Failure behavior

| Situation | Behavior |
|---|---|
| The folder isn't a complete saved run | The reader's refusal message (`input.not_a_run`), and nothing else from that folder |
| An artifact has a schema version with no reader | The reader's message (`artifact.unknown_schema_version`) |
| The response's `chart` arrays are missing or unreadable | Both charts say they're unavailable; the metrics still show |
| The app quits while a run is open | Nothing to clean up, because nothing was written |

## Acceptance criteria

| ID | Criterion |
|---|---|
| GP-AC01 | Each candidate's app launches from Finder on macOS and quits cleanly, with no terminal, no server started by hand, and no frontend toolchain on that Mac |
| GP-AC02 | It opens the demo's run, and a real run from `trialfolio run`, chosen in the system's folder dialog |
| GP-AC03 | A folder that isn't a complete run shows the reader's refusal message |
| GP-AC04 | Every metric appears in order with its unit; an unavailable value is shown as unavailable with its reason, never as zero |
| GP-AC05 | The equity chart shows the strategy's and the benchmark's saved levels. The drawdown chart's deepest point equals the run's reported `max_drawdown` at the digits it was reported with. |
| GP-AC06 | The concise notice and "Not assessed" are shown, the full notice is reachable, and the demo's run is labeled synthetic |
| GP-AC07 | Opening a run changes no file in its folder, and the app opens no network connection |
| GP-AC08 | This file records, for each candidate: the build steps, the app's size, the time to its first window, everything it bundles and the notices each needs, and the core functions it called |

## Tasks

The owner assigns these by ID. They aren't next items: [Doing the next item](../AGENTS.md#doing-the-next-item) goes through the release files only. Branches follow the same form, such as `docs/gp-t01-toolkit-candidates`.

| ID | Task | Depends on |
|---|---|---|
| GP-T01 | **Complete this specification,** as [Completing this specification](#completing-this-specification) says. Then ask the owner to set the status to Ready. | None |
| GP-T02 | **Build the first candidate,** package it, check every criterion, and record what GP-AC08 asks for in this file. | Status Ready |
| GP-T03 | **Build the second candidate,** in the same way. | Status Ready |
| GP-T04 | **Draft the toolkit ADR** from GP-T02 and GP-T03's records, with the license review LIC-17 asks for, as Proposed. Record whether saved runs hold the series 0.4.0's charts need, and which core functions the prototype called. The owner decides the ADR. | GP-T02, GP-T03 |

## Open questions

| Question | Impact | Proposed default | Resolve by |
|---|---|---|---|
| Which two toolkits? | What gets built, and what the ADR compares | GP-T01 proposes them after its license check. The starting suggestion is PySide6 and pywebview, which keep the app in Python with the existing core. Electron and Tauri, which LIC-17 also lists, need a JavaScript or Rust toolchain to build. | GP-T01 |
| Where does the code live? | The repository's checks, and the `trialfolio` package | In `prototypes/graphical/` in this repository, as its own `uv` project that depends on the local `trialfolio` package. It's outside `trialfolio`'s wheel, and the toolkits aren't `trialfolio`'s dependencies. Built apps are git-ignored. | GP-T01 |
| How are the charts drawn? | Whether the screens hold scripts, which bears on the roadmap's open question about REQ-08 and LIC-17 | Each candidate's own way, but without scripts where the toolkit allows. Record which way each one used. | GP-T01 |
| May it call core functions that contracts.md hasn't made public? | Whether it can use `read_run` and the normalization code as they are | Yes. It isn't distributed separately, so the [public contract boundary](contracts.md#public-contract-boundary) doesn't apply. GP-T04 lists the functions it called. | GP-T01 |
| What evidence may be committed? | REQ-11, and Portfolio123's terms | Only the demo's run, in screenshots or numbers. A real run's values and screenshots stay on the owner's Mac. | GP-T01 |
