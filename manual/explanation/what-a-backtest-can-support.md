# What a backtest can support

A screen backtest's results can support some statements and not others, and Trial Folio's reports say which. This page explains how a report draws that line, and why reviews and experiments never pick a winner.

## Ten sections, whatever the evidence

Every report Trial Folio writes, for a run, a review, or an experiment, has the same ten sections, in the same order. A section the evidence can't support isn't left out, and isn't filled in. It says it's unavailable, or not assessed, and why ([REQ-08](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-requirements), [reports](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#reports)). So the report shows what a screen backtest can't tell you, as plainly as what it can.

For a single screen run, the sections hold this:

| # | Section | What a screen run's report holds |
|---|---|---|
| 1 | Objective, purpose, and research status | The title, the benchmark, and your purpose, if you gave one. The objective is unavailable: a screen run declares no research objective. |
| 2 | Definitions, and changes from a baseline | Each metric's definition. The changes are unavailable: a single run has no baseline. |
| 3 | Data sources, coverage, provenance, and missing values | Where the values came from, the actual coverage against the requested dates, each value's provenance, and any missing value |
| 4 | Returns, risks, costs, and assumptions | The strategy's and the benchmark's metrics, with their units and decimal places, the costs, the implementation assumptions, and every setting |
| 5 | Cases and attempts | The run's case, its plan and budget, and every attempt, whatever its outcome |
| 6 | Robustness and concentration | Not assessed |
| 7 | Statistical methods and uncertainty | Not assessed. No interval, return series, or drawdown history is shown or reconstructed. |
| 8 | Development, selection, holdout, and forward evidence | Unavailable: one backtest over the requested dates has no separate period for any of them |
| 9 | Feasibility, capacity, and missing execution evidence | Trading readiness not assessed, and the execution evidence the run doesn't have, such as actual trades and commission |
| 10 | Conclusion, limitations, and artifacts | The permitted conclusion, the limitations, and links to the run's files |

A run without normalized tables, because its attempt didn't succeed or its response was invalid, says which, and shows the plan's settings instead.

Each value appears exactly as the run's normalized tables hold it, with its unit, so the report's values match `normalized/metrics.csv`. A value never has more decimal places than Portfolio123's response gave it. The response holds summary statistics, and summary statistics alone don't justify reconstructing a return series, a confidence interval, or a drawdown history, so the report shows none ([METH-05.10](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-05-data-integrity-appropriate-to-the-claim)).

## "Not assessed"

Statistical validation and trading readiness read "Not assessed" in every report, and `not_assessed` in every manifest and JSON summary. Trial Folio applies no statistical method yet, and makes no judgment of whether a strategy could be traded. Its methodology lets a report make such a statement only once the method behind it has been validated, and none has ([METH-07.3](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions), [INV-10](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants)).

A command's success says nothing about the strategy either ([METH-07.4](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions), [REQ-13](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-requirements)). Exit code 0, "Run completed", and an outcome of `completed` mean only that the command did its work, and the command's output still says that statistical validation and trading readiness are not assessed. The report shows its status in neutral gray, with nothing styled as a pass, so a completed run can't look like an endorsement to trade.

The report's conclusion says so in its own words.

Synthetic example output from `trialfolio demo`, the permitted conclusion of its report:

> The run completed: Trial Folio wrote the synthetic run and normalized it. That's a statement about execution, not about the strategy. Statistical validation and trading readiness are not assessed, so this report permits no conclusion about whether the strategy is useful, or whether its results could be achieved.

## Unavailable values are never zero

Trial Folio never silently replaces information it doesn't have with zero or a favorable default ([INV-03](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants)). A metric missing from Portfolio123's response shows as unavailable, with the reason, never as zero, a blank, or a placeholder number. In `metrics.csv`, its value is empty, and its `unavailable_reason` column gives the reason code, such as `blank_in_source` when the response has the field but no value, or `unparseable_in_source` when its value can't be read ([metrics and missing values](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#metrics-and-missing-values)).

The same holds when runs are compared. A review shows a missing value as unavailable, with the reason its run's `metrics.csv` gives. A result whose run has no tables, because its request failed or its response was invalid, is still compared, with every metric unavailable, and the review's report says why it has no tables. An experiment's report shows each missing value as unavailable, with its reason code.

## Commission isn't modeled

Portfolio123's API documents no commission parameter. Slippage, which you give as `slippage_percent`, is the only trading cost sent. So the report and `settings.csv` show commission as `not_modeled`, never as zero, because Trial Folio doesn't assume zero costs ([METH-01.4](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-01-define-the-question-before-measuring-success)). For the same reason, slippage has no default: you always state it.

The report's ninth section lists the execution evidence the run doesn't have: actual trades, commission, and the parameters Trial Folio doesn't send, such as `carry_cost`, whose defaults Portfolio123 doesn't document ([reproducibility](reproducibility.md#inferred-defaults-and-settings-not-sent)). The full research notice says that backtested results may be affected by costs or execution effects that are omitted or inaccurately modeled ([DSC-01](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-01-full-research-and-financial-result-notice)).

## When coverage differs from what you asked

The dates a backtest covers can differ from the dates you asked for. Trial Folio reads the actual coverage from the dates of the response's periods: the first transaction date, the end of the last period, and the number of periods. If the response covers different dates than you asked for, the report shows both, and `settings.csv` flags the date `coverage_mismatch`. When the coverage can't be established, Trial Folio compares nothing, and the report says the coverage couldn't be established, rather than showing it as matching ([`p123api-screen-backtest` version 1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#p123api-screen-backtest-version-1)).

Trial Folio's methodology forbids silently shortening an evaluation window to obtain attractive coverage or performance, and its invariants make the actual coverage of every comparison visible ([METH-05.4](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-05-data-integrity-appropriate-to-the-claim), [INV-08](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#enduring-invariants)). So a review computes no difference between two results' metrics when their periods differ, apart from the coverage itself, and gives the reason. An experiment's report shows each case's coverage against the requested dates, which every case shares.

## Why reviews and experiments never rank results

A review compares saved runs with a baseline you choose. It shows which settings differ, and how each metric moved, with the difference only where the two values are comparable. It doesn't rank the runs, or say which strategy is better: its conclusion says what differs ([the review report](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#reports)). To compare runs step by step, see [comparing runs](../how-to/compare-runs.md).

An experiment's report shows the cases' metrics side by side, with a column for each case, in the plan's order. It computes no difference between cases, and orders, ranks, and marks no case by a value. Its conclusion says how many planned cases succeeded, and calls no case best ([the experiment report](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#reports)). Showing each case against the baseline, with a difference, as a review does, was considered for it and not chosen, because that invites reading a case as better or worse.

The reasons are in the release and the methodology behind them:

- **Execution is kept separate from usefulness.** Release 0.3.0 excludes statistical acceptance decisions and ranking cases by "best", and its report never orders or highlights cases by performance as a selection ([release 0.3.0's explicit exclusions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md#explicit-exclusions), [required behavior](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md#required-behavior), 7).
- **Choosing is part of the search.** A variant whose outcome chooses a candidate is part of the search, not independent evidence for that candidate ([METH-03.3](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing), [METH-06.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-06-robustness-and-economic-usefulness)). Picking the best of several cases is such a choice.
- **No judgment before a validated method.** A report makes no affirmative judgment before the method behind it is validated ([METH-07](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions)). No statistical method is applied yet, so the report states no uncertainty for any value or difference. An experiment's counts of cases, attempts, and repeats are its research history, not a multiple-testing family, and its report says so ([METH-03.2](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing)).

## Prior research limits any claim

An experiment declares its prior research: the earlier work on the same idea whose outcomes you saw, in Trial Folio or anywhere else. Its status is `complete` when its description accounts for all of it, or says there was none; `partial` when there was more than it describes; or `unknown` ([prior research](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#prior-research)). Trial Folio records the declaration as you wrote it, and can't verify it. The report shows it, and says it's unverified.

It matters because searching more strategies requires stronger evidence. A search made before Trial Folio recorded it can't be repaired by starting the count at installation, so a study records how complete its search history is, and limits its claim accordingly ([METH-03.4](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing)). An experiment's report therefore lists, among its limitations, that a declaration other than `complete` limits any claim drawn from the cases. To write the declaration, see the [experiment configuration](../reference/experiment-configuration.md).

## The research notice

Every report starts with the concise research notice, before any result ([DSC-02](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-02-concise-report-notice)):

> Research output only. Backtested and hypothetical results do not represent achievable returns. No financial gain, future performance, suitability, or protection from loss is represented or promised. This report is not personalized investment advice. See the full license and research limitations.

Its closing words, "the full license and research limitations", link to the full research and financial-result notice, at the end of the report. [docs/disclaimers.md](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md) holds the full notice, and [LICENSE](https://github.com/promptedportfolio/trialfolio/blob/main/LICENSE) governs every copy of Trial Folio.

The report's closing section carries the Portfolio123 data statement, and two links outside the report: to the license, and to Portfolio123's terms. Trial Folio's license grants no rights to Portfolio123 data, and your use of any Portfolio123 data in a report, sharing it included, is governed by Portfolio123's terms. Sharing it publicly may need Portfolio123's consent ([DSC-06](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-06-portfolio123-notices)). The license link names the tag of the Trial Folio version that rendered the report, such as `v0.1.0`, so it works only once that version is tagged. Reviews and experiments carry the same notices, the same data statement, and the same "Not assessed".

## Where it's specified

- [Reports](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#reports), in contracts.md: the ten sections, and the run, review, and experiment reports.
- [Metrics and missing values](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#metrics-and-missing-values) and [`p123api-screen-backtest` version 1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#p123api-screen-backtest-version-1), in contracts.md: unavailable values, and coverage.
- [METH-03](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing), [METH-05](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-05-data-integrity-appropriate-to-the-claim), and [METH-07](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions), in methodology.md.
- [Disclaimers and notices](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md): the notices' texts, and where each appears.
