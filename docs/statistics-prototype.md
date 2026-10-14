# Statistics prototype

**Status:** Draft. **Don't build from it yet.** SP-T01 completes it, once [0.4.0](releases/0.4.0-ranking-weights.md) is Implemented, and then the owner sets it to Ready.
**Decided by:** [D-43](spec.md#decisions), on 2026-10-14.
**Depends on:** release 0.4.0 Implemented, and the experiments of [0.3.0](releases/0.3.0-experiments.md) and 0.4.0 that the owner has saved. It sends nothing to Portfolio123, so it spends no credits.

This is an offline prototype of the statistics the roadmap's [statistical evaluation](roadmap.md) target needs. It isn't a release: it has no version or tag, and it's never distributed. It evaluates methods, not strategies. Its job is evidence:

- **For the methods ADR,** which [methodology.md](methodology.md) requires before statistical evaluation, and which chooses the inference methods ([open questions](methodology.md#open-questions)). Each candidate procedure is run on real saved experiments and on synthetic data with known properties, so the ADR decides on how each one behaves, not on how it's described.
- **For the return series.** Which dated series each case's saved response holds, and whether the statistics calculated from them agree with the metrics Portfolio123 reported.
- **For the statistical evaluation target's specification.** How many observations a typical experiment gives, how strongly its cases are correlated, and so how often a sound test will be inconclusive.

The statistical evaluation target's specification decides whether any of the prototype's code is kept.

## Completing this specification

SP-T01 completes it. It reads [AGENTS.md](../AGENTS.md), [spec.md](spec.md), [METH-01.3, METH-02 to METH-04, METH-06, and METH-07](methodology.md), methodology.md's [verification of statistical methods](methodology.md#verification-of-statistical-methods), and the contracts.md sections on the [screen-backtest response](contracts.md#p123api-screen-backtest-version-1), [metrics](contracts.md#metrics-and-missing-values), [default variants](contracts.md#default-variants), and [experiment output](contracts.md#experiment-output). Then it:

1. **Names each procedure's exact variant and its primary source,** for every procedure in [included scope](#included-scope). For example, which block bootstrap and how its block length is chosen, and which estimate of the effective number of trials the deflated Sharpe ratio uses. It also states the inputs the procedures share: the periods every case's returns are aligned on, and the Sharpe ratio's risk-free series and return convention ([open questions](#open-questions)).
2. **Names each procedure's independent reference calculation:** a published worked example, an established library, or a hand calculation, as methodology.md asks. A library's license is checked before it's used in a check.
3. **Specifies the synthetic data:** the processes, with serial dependence, fat tails, and correlated cases, under a null and under alternatives; and, before any result is seen, the simulation counts, the seeds, and the tolerances ("tolerances first").
4. **Resolves the open questions,** or confirms their defaults.
5. **Pairs each acceptance criterion with a check,** and gives the verification commands.

It's Ready when every criterion has a check, every open question is resolved or has a default the owner confirmed, and the owner has agreed.

## User outcome

The owner points the prototype at a saved experiment, and gets a local record of each candidate procedure's result for it: the observations it used, the assumptions it checked and whether they held, and the choices it made, such as the block length and the seed. The methods ADR then cites what the prototype found, on the owner's experiments and on synthetic data, for each procedure it adopts or rejects.

## Included scope

- **Return series.** Each case's dated period returns, for the strategy and its benchmark, and its daily levels, read from the case's saved response ([the screen-backtest response](contracts.md#p123api-screen-backtest-version-1)), with excess returns over the benchmark calculated and labeled as calculated.
- **Aligned periods.** The joint procedures, and the correlation between cases, need every case's returns over the same periods ([METH-04.1](methodology.md#meth-04-inference-before-any-statistical-badge), item 2). An experiment's cases needn't share their periods: `results.rows` holds one row per rebalance period, and P-13's [default variant](contracts.md#default-variants) gives most experiments one case that rebalances every week where the others rebalance every 4 weeks, or the reverse. How the cases are aligned is an [open question](#open-questions), and SP-T01 sets it as the alignment policy that [METH-04.2](methodology.md#meth-04-inference-before-any-statistical-badge) asks for.
- **Assumption checks.** For each experiment: the number of non-overlapping periods; serial correlation; skewness and kurtosis; the correlation between cases, over the aligned periods; and an estimate of the effective number of independent trials.
- **The candidate procedures** the roadmap's statistical evaluation target names, and methodology.md's open questions weigh:
  - a time-block bootstrap, resampling every case's periods jointly, for each case's mean excess return and Sharpe ratio ([METH-04.3](methodology.md#meth-04-inference-before-any-statistical-badge));
  - a HAC estimator, as an independent reference calculation for the bootstrap;
  - Holm adjustment, and Romano–Wolf stepdown, for a family of cases;
  - the deflated Sharpe ratio, for a case a declared rule selects;
  - the probability of backtest overfitting, through combinatorially symmetric cross-validation, for an experiment treated as a search.
- **Calibration.** Each procedure's rejection rate under synthetic nulls (size) and alternatives (power), at the sample sizes the owner's experiments have.
- **A record of the findings,** written into this file.

## Explicit exclusions

- Any request to Portfolio123, and any credentials. An experiment the prototype needs that the owner hasn't saved is the owner's to run, under its own plan and approval.
- Any change to the `trialfolio` package: its dependencies, CLI, outputs, reports, or contracts.
- **Choosing a candidate strategy.** No result on a real experiment is used to choose a strategy. If one ever informs a choice, that choice is recorded as part of the search ([METH-03.3](methodology.md#meth-03-research-history-and-multiple-testing)).
- Confirmatory claims, and any significance grade in a Trial Folio report ([METH-04](methodology.md#meth-04-inference-before-any-statistical-badge)).
- Choosing the methods. The methods ADR chooses them; the prototype gathers the evidence.
- Distribution of any kind.

## Referenced requirements

- **Methodology:** [METH-01.3](methodology.md#meth-01-define-the-question-before-measuring-success), a Sharpe ratio's stated risk-free series and return convention. [METH-02](methodology.md#meth-02-separate-development-selection-and-confirmation), selection kept apart from confirmation. [METH-03](methodology.md#meth-03-research-history-and-multiple-testing), the research history and multiple testing. [METH-04](methodology.md#meth-04-inference-before-any-statistical-badge), inference before any statistical badge. [METH-06.1](methodology.md#meth-06-robustness-and-economic-usefulness), predefined perturbations. [METH-07](methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions), separate dimensions. [Verification of statistical methods](methodology.md#verification-of-statistical-methods).
- **Product:** [REQ-11](spec.md#enduring-requirements): no raw provider data committed. [REQ-13](spec.md#enduring-requirements): process success kept apart from usefulness. [INV-03](spec.md#enduring-invariants): unavailable values are never shown as zero. INV-09: a provider request count isn't a multiple-testing family size.

## Required behavior

1. **Read only, offline.** The prototype reads a saved experiment through the core's reader, `read_experiment` in `src/trialfolio/experiment_records.py`, and a saved run through `read_run` in `src/trialfolio/runs.py`. It writes nothing into them, and opens no network connection. Its own output goes to a directory the owner chooses.
2. **Use only what the response holds.** Every series comes from a case's saved response, apart from the Sharpe ratio's risk-free series, which no response holds ([open questions](#open-questions)). A case without a usable series is listed as unavailable, with the reason, and never filled in from its summary metrics ([descriptive analysis before further acquisition](roadmap.md#descriptive-analysis-before-further-acquisition)).
3. **Record every choice.** Each result records the procedure's variant, its inputs, its block length or other tuning, its number of resamples, and its seed, so it can be recomputed exactly.
4. **Label what it shows.** Every result is labeled as the prototype's, and descriptive. Adjusted and unadjusted values appear side by side ([METH-04.5](methodology.md#meth-04-inference-before-any-statistical-badge)). Nothing combines them into a single score, and statistical validation reads "Not assessed". A case a declared rule selects is labeled with that rule, never as the best.

## Failure behavior

| Situation | Behavior |
|---|---|
| The directory isn't a complete saved experiment or run | The reader's refusal message (`input.not_a_run`), and nothing else from that directory |
| An artifact has a schema version with no reader | The reader's message (`artifact.unknown_schema_version`) |
| A case's response has no usable series | That case is listed as unavailable, with the reason; the other cases are still analyzed |
| A case's returns can't be aligned with the other cases', as SP-T01 sets the alignment | That case is listed as unavailable to the procedures that use the cases jointly, with the reason, and they run on the other cases |
| No risk-free series is given for an experiment | The Sharpe ratio and the deflated Sharpe ratio are unavailable for it, with the reason; no excess return over the benchmark stands in for them |
| Too few observations for a procedure, as SP-T01 sets the minimum | That procedure's result says it's unavailable, and why; no value is given |

## Acceptance criteria

| ID | Criterion |
|---|---|
| SP-AC01 | It reads a saved 0.3.0 experiment, a saved 0.4.0 experiment, and the committed synthetic experiments, changes no file in their directories, and opens no network connection |
| SP-AC02 | For each case, the period returns and daily levels it reads reproduce the case's `total_return`, `annualized_return`, and `max_drawdown`, at the digits each was reported with, or this file records where and why they don't |
| SP-AC03 | Each procedure agrees with its independent reference calculation, as SP-T01 names it, within the tolerance SP-T01 set before the result was seen |
| SP-AC04 | On synthetic data, each procedure's size and power are recorded, at the sample sizes of the owner's experiments, with the seeds and simulation counts SP-T01 set |
| SP-AC05 | For each of the owner's experiments it's run on, this file records the assumption checks' conclusions, and the number of periods and cases. Values from real experiments stay on the owner's machine. |
| SP-AC06 | Every result records its procedure's variant, inputs, tuning, resamples, and seed; a rerun with the same inputs gives the same values |
| SP-AC07 | Every result is labeled as the prototype's and descriptive, shows adjusted and unadjusted values side by side, gives no single score, and names no case best |
| SP-AC08 | This file records, for each procedure: whether its assumptions held on the owner's experiments, its calibration, how sensitive it was to its tuning, and what the statistical evaluation target's specification would need from it |

## Tasks

The owner assigns these by ID. They aren't next items: [Doing the next item](../AGENTS.md#doing-the-next-item) goes through the release files and the readability refactor's tasks only. Branches follow the same form, such as `docs/sp-t01-statistics-procedures`.

| ID | Task | Depends on |
|---|---|---|
| SP-T01 | **Complete this specification,** as [Completing this specification](#completing-this-specification) says. Then ask the owner to set the status to Ready. | 0.4.0 Implemented |
| SP-T02 | **Read the return series,** check them against the reported metrics (SP-AC01, SP-AC02), and record what it found in this file. | Status Ready |
| SP-T03 | **Build the procedures,** with their reference calculations and their calibration on synthetic data (SP-AC03, SP-AC04, SP-AC06, SP-AC07). | SP-T02 |
| SP-T04 | **Run them on the owner's experiments,** with the owner, and record the conclusions in this file (SP-AC05, SP-AC08). | SP-T03 |
| SP-T05 | **Draft the methods ADR** from what SP-T02 to SP-T04 recorded, as Proposed, with each procedure it adopts or rejects and why. The owner decides the ADR. | SP-T04 |

## Open questions

| Question | Impact | Recommended default | Resolve by |
|---|---|---|---|
| Where does the code live? | The repository's checks, and the `trialfolio` package | In `prototypes/statistics/` in this repository, as its own `uv` project that depends on the local `trialfolio` package. It's outside `trialfolio`'s wheel, and its libraries aren't `trialfolio`'s dependencies. Its outputs are git-ignored. | SP-T01 |
| Which libraries does it use? | What the procedures depend on, and whether the reference calculations are independent | NumPy and SciPy, after SP-T01 checks their licenses. Each procedure is written in the prototype, so the ADR can see exactly what it does; an established library that implements the same procedure serves only as a reference calculation. | SP-T01 |
| How are the cases' returns aligned? | Whether the joint bootstrap, Romano–Wolf, the correlation between cases, and the probability of backtest overfitting can be calculated for an experiment, and on which cases | From each case's daily `chart` levels, which fall on the same weekdays in every case, since no variant changes the dates ([variants](contracts.md#variants)): returns over periods common to every case, whose length SP-T01 sets, labeled as calculated. Each case's own `results.rows` periods stay for SP-AC02's checks. The alternative, analyzing each rebalance frequency's cases apart, splits the family the adjustments cover. | SP-T01 |
| Which risk-free series and return convention does the Sharpe ratio use? | Whether the Sharpe ratio and the deflated Sharpe ratio can be calculated: no response holds a risk-free series, and Portfolio123 doesn't document its Sharpe ratio's rate ([metrics](contracts.md#metrics-and-missing-values)) | A series the owner supplies as a local file, with its source and return convention, which every result that uses it records ([METH-01.3](methodology.md#meth-01-define-the-question-before-measuring-success)). Without one, both are unavailable. The alternative, a stated constant rate such as zero, needs no input, but is a convention, not a series. | SP-T01 |
| Which experiments does it run on? | Whether the evidence matches the experiments the target will evaluate | Every 0.3.0 and 0.4.0 experiment the owner has saved, and the committed synthetic experiments. An experiment large enough to stand in for a grid, if none is saved, is a new experiment for the owner to approve, under its own budget. | SP-T01 |
| What evidence may be committed? | REQ-11, and Portfolio123's terms | Synthetic results, in numbers. For real experiments: the conclusions of each check, and the number of periods and cases, but not their values, which stay on the owner's machine. | SP-T01 |
