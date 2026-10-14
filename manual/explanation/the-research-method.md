# The research method, step by step

Trial Folio is built first for one kind of study: reproducing published factor research in Portfolio123. This page explains the method such a study follows, in two parts. The first says what published research has found about backtests, and why that calls for discipline. The second follows a study step by step, from its question to its report, and says which steps Trial Folio does now, which you do by hand, and which are planned.

The method is defined in [methodology.md](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md), Trial Folio's research design. It's a draft: no method in it is implemented or validated ([status and labels](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#status-and-labels)). Where this page describes one of its methods, it says so. Where this page and a specification disagree, the specification wins, and this page is the one to fix.

Nothing here promises a result, or gives advice about investing. A study whose results match a paper's doesn't predict anyone's returns, and doesn't make a strategy safe to trade ([DSC-08](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-08-statements-the-project-must-not-make)).

## Part 1: What the research says

A backtest applies a strategy's rules to historical data. Running many is easy, and the best of many tends to look better than it is. Finance researchers have studied what that does to backtests, and to factors: the stock characteristics that published papers report predict returns. They've also studied how well published factors hold up. Each source below was checked, and its full citation is in [sources](#sources).

### Testing many variants

[Harvey and Liu (2015)](https://doi.org/10.3905/jpm.2015.42.1.013) start from a common practice: discounting a backtest's reported Sharpe ratio by half, because of data mining. They call that a rule of thumb. When a researcher tests many variables, some will look significant by chance, so they use multiple-testing methods to set the discount from the number of tests. The discount isn't the same for every strategy: the highest Sharpe ratios are penalized moderately, and marginal ones heavily.

[Bailey, Borwein, López de Prado, and Zhu (2017)](https://doi.org/10.21314/JCF.2016.322) note that investment firms and portfolio managers rely on backtests to choose strategies and allocate capital, and that standard safeguards against overfitting, such as holding out part of the data, tend to be unreliable for investment backtests. They propose a framework for estimating the probability that a backtest is overfit, and a method to estimate it, which they call combinatorially symmetric cross-validation.

[Bailey and López de Prado (2014)](https://doi.org/10.3905/jpm.2014.40.5.094) describe backtest optimizers that search for the parameters that maximize a strategy's simulated performance, which overfits it. Researchers and managers also tend to report only positive outcomes, and not accounting for the number of trials behind a discovery leads to over-optimistic expectations. Their deflated Sharpe ratio corrects for that selection under multiple testing, and for returns that aren't normally distributed.

### Multiple testing in factor research

[Harvey, Liu, and Zhu (2016)](https://doi.org/10.1093/rfs/hhv059) observe that hundreds of papers and factors attempt to explain the cross-section of expected returns. Given so much data mining, they argue, the usual criteria for significance don't make sense. Their multiple-testing framework gives historical cutoffs from the first empirical tests in 1967 on, and finds that a new factor needs a t-statistic greater than 3.0. They argue that most claimed research findings in financial economics are likely false.

### How many published factors replicate

Here the research disagrees.

- [Hou, Xue, and Zhang (2020)](https://doi.org/10.1093/rfs/hhy131) test 452 anomalies, limiting the influence of microcaps with NYSE breakpoints and value-weighted returns. 65% can't clear an absolute t-value of 1.96, and 82% can't clear a multiple-testing hurdle of 2.78. Even the anomalies that replicate are much smaller economically than originally reported. They conclude that markets are more efficient than previously recognized.
- [Chen and Zimmermann (2022)](https://doi.org/10.1561/104.00000112) provide data and code that reproduce nearly all cross-sectional stock return predictors: 319 characteristics drawn from earlier meta-studies, each compared with its original paper's results. Of the 161 that were clearly significant in the original papers, 98% of their long-short portfolios have t-statistics above 1.96. They also quote Hou, Xue, and Zhang on the original studies' samples: a failure rate of 65.4% with NYSE breakpoints and value-weighted returns drops to 43.1% with breakpoints from NYSE, Amex, and NASDAQ and equal-weighted returns, which give microcaps more weight.
- [Jensen, Kelly, and Pedersen (2023)](https://doi.org/10.1111/jofi.13249) estimate a Bayesian model of factor replication, and reach different conclusions from the papers that argue for a replication crisis. They find that most factors can be replicated, that they work out of sample in a new data set covering 93 countries, and that the large number of factors strengthens the evidence rather than weakening it.

The studies differ in their data, in how they build each factor, and in the standard a factor must meet, and their answers differ with them. Even within one study, the hurdle and the treatment of microcaps change the share that fails. So whether a factor "replicates" depends on what's asked of it, which is why a reproduction states its construction and its criteria before it runs.

### Returns after publication

[McLean and Pontiff (2016)](https://doi.org/10.1111/jofi.12365) study 97 variables shown to predict cross-sectional stock returns. The portfolios' returns are 26% lower out of sample, and 58% lower after publication. They treat the out-of-sample decline as an upper bound on the effect of data mining, and estimate a 32% lower return, the difference between the two, from trading informed by the publication. Their findings suggest that investors learn about mispricing from academic publications.

### Writing the plan first

[Nosek, Ebersole, DeHaven, and Mellor (2018)](https://doi.org/10.1073/pnas.1708274114) distinguish generating hypotheses from existing observations, which they call postdiction, from testing them with new observations, prediction. Mistaking one for the other reduces the credibility of research findings, and ordinary biases, such as hindsight bias, make that mistake hard to avoid. Their remedy is preregistration: defining the research questions and the analysis plan before observing the outcomes. They describe ways to make the best use of it in circumstances short of the ideal, such as when the data already exist, as a backtest's always do.

### What the method takes from it

methodology.md answers these findings with practices more than formulas:

- **Record every try.** Each outcome-informed choice, each case, and each attempt is research history, and the history is recorded before any statistical correction is built. A count of requests to Portfolio123 isn't a count of tests ([METH-03](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing)).
- **Fix the plan and the variants before the results.** A reproduction's protocol, criteria, and variants are recorded before its first test ([METH-09.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research), [METH-06.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-06-robustness-and-economic-usefulness)).
- **Record how a reproduction departs from the paper,** and test its dependence on microcaps with a variant that excludes them ([METH-09.3 and METH-09.4](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)).
- **Split the period** around the end of the paper's sample and its publication ([METH-09.9](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)).
- **Make no statistical claim before a validated method** ([METH-04](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-04-inference-before-any-statistical-badge), [METH-07](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-07-multidimensional-assessment-and-permitted-conclusions)). The methodology takes the lesson of a higher hurdle, not a fixed number: an assessment must never show an unexplained "required t", and a raw count of experiments isn't the number of independent tests (METH-04.4). It defers the deflated Sharpe ratio and diagnostics of the probability of backtest overfitting: they may be researched later, and each needs its assumptions checked for the study's design before it's used (METH-04.7).

Trial Folio applies none of these statistical methods now. Its reports say statistical validation and trading readiness are not assessed ([what a backtest can support](what-a-backtest-can-support.md)).

### Sources

Each was checked on 2026-10-13: its authors, year, title, journal, volume, and pages against its DOI's record, and, where the page would load, its publisher's or an author's page; and its findings against its abstract or its text. Each link goes to the paper's DOI.

- Bailey, David H., Jonathan M. Borwein, Marcos López de Prado, and Qiji Jim Zhu (2017). "[The probability of backtest overfitting](https://doi.org/10.21314/JCF.2016.322)." *Journal of Computational Finance* 20 (4): 39–69.
- Bailey, David H., and Marcos López de Prado (2014). "[The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality](https://doi.org/10.3905/jpm.2014.40.5.094)." *The Journal of Portfolio Management* 40 (5): 94–107.
- Chen, Andrew Y., and Tom Zimmermann (2022). "[Open Source Cross-Sectional Asset Pricing](https://doi.org/10.1561/104.00000112)." *Critical Finance Review* 11 (2): 207–264.
- Harvey, Campbell R., and Yan Liu (2015). "[Backtesting](https://doi.org/10.3905/jpm.2015.42.1.013)." *The Journal of Portfolio Management* 42 (1): 13–28.
- Harvey, Campbell R., Yan Liu, and Heqing Zhu (2016). "[… and the Cross-Section of Expected Returns](https://doi.org/10.1093/rfs/hhv059)." *The Review of Financial Studies* 29 (1): 5–68.
- Hou, Kewei, Chen Xue, and Lu Zhang (2020). "[Replicating Anomalies](https://doi.org/10.1093/rfs/hhy131)." *The Review of Financial Studies* 33 (5): 2019–2133.
- Jensen, Theis Ingerslev, Bryan Kelly, and Lasse Heje Pedersen (2023). "[Is There a Replication Crisis in Finance?](https://doi.org/10.1111/jofi.13249)" *The Journal of Finance* 78 (5): 2465–2518.
- McLean, R. David, and Jeffrey Pontiff (2016). "[Does Academic Research Destroy Stock Return Predictability?](https://doi.org/10.1111/jofi.12365)" *The Journal of Finance* 71 (1): 5–32.
- Nosek, Brian A., Charles R. Ebersole, Alexander C. DeHaven, and David T. Mellor (2018). "[The preregistration revolution](https://doi.org/10.1073/pnas.1708274114)." *Proceedings of the National Academy of Sciences* 115 (11): 2600–2606.

## Part 2: A study, step by step

This part follows one study from its question to its report, as [spec.md's primary use](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#primary-use) and [METH-09](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research) describe it: take a paper's factor, rebuild it in Portfolio123, and test whether the paper's finding holds with an individual investor's tools.

Its example is illustrative, not a real paper: a paper reports that stocks ranked high on a value factor, such as earnings yield, earned more than stocks ranked low, in a long-short portfolio of a broad universe, rebalanced monthly. The page shows no results, since any study's results depend on its data.

Each step is labeled:

- **Trial Folio does this now,** with the release that added it, and the manual page that shows how.
- **By hand now,** with what you do yourself.
- **Planned,** with its target in the [roadmap](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#driving-use-case-coverage), or "later, without a version" when the roadmap gives it none. Release 0.4.0 is specified and Ready, but not built yet. The targets after it are proposed, not commitments ([where Trial Folio is going](where-trial-folio-is-going.md)).

A step can have parts with different labels. Release 0.3.0 added experiments: a copy of Trial Folio at an earlier tag, such as `v0.2.1`, has none.

In the table, a target named without a version is a later increment, which the roadmap gives no version.

| Step | Trial Folio does this now | By hand now | Planned |
|---|---|---|---|
| [1. Choose the paper, and state the question](#step-1-choose-the-paper-and-state-the-question) | The experiment's purpose (0.3.0) | The paper, the claim, and what counts as reproducing it | A study record (Reproduction and sensitivity workflow); confirmatory protocols (Statistical evaluation) |
| [2. Write the plan down before testing](#step-2-write-the-plan-down-before-testing) | The plan, fixed before any result, and the prior-research declaration (0.3.0) | The protocol, committed with its date | A study record with dated amendments (Reproduction and sensitivity workflow) |
| [3. Build the factor, and record each deviation](#step-3-build-the-factor-in-portfolio123-and-record-each-deviation) | Every setting recorded and shown (0.1.0); runs compared with a baseline (0.2.0) | The formulas, and the deviation record | A ranking system's whole definition (0.4.0); a deviation record (Reproduction and sensitivity workflow) |
| [4. Design the experiment](#step-4-design-the-experiment-a-baseline-and-fixed-variants) | A baseline and variants of verified settings, microcaps excluded by a rule (0.3.0) | Another universe, as another experiment | Weight and factor-removal variants (0.4.0); sell rules (Simulation review); universe slices (Reproduction and sensitivity workflow) |
| [5. Approve the plan and its budget](#step-5-approve-the-plan-and-its-budget) | One approval for every case and the budget (0.1.0, 0.3.0) | None | None |
| [6. Run, and resume](#step-6-run-and-resume) | Cases in order, every attempt recorded, a safe resume (0.3.0) | None | None |
| [7. Compare the cases](#step-7-compare-the-cases) | Cases side by side (0.3.0); runs against a baseline (0.2.0) | The results against the paper's | None |
| [8. Describe the results](#step-8-describe-the-results) | Portfolio123's summary statistics (0.1.0); a slippage variant (0.3.0) | Analyses beyond the summary statistics | Rolling returns and period splits (0.5.0); rank buckets (1.1.0); gross and net (Reproduction and sensitivity workflow) |
| [9. Check robustness](#step-9-check-robustness) | Predefined variants, not assessed (0.3.0) | Judging the differences | Weight variants (0.4.0); rank diagnostics (1.1.0); slices and sensitivity checks (Reproduction and sensitivity workflow); simulations (Simulation review) |
| [10. Evaluate](#step-10-evaluate) | "Not assessed" in every report (0.1.0) | The verdict, under your criteria | Statistical evaluation; Forward tracking |
| [11. Report every case](#step-11-report-every-case-failures-included) | Every attempt and every case accounted for (0.1.0, 0.3.0) | The study's report | A reproduction report (Reproduction and sensitivity workflow) |

### Step 1: Choose the paper, and state the question

The study starts with a paper, and one claim from it, such as the illustrative paper's finding that stocks with high earnings yield earned more. Its protocol names the claim being tested, and what would count as reproducing it ([METH-09.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)). A study that later makes a confirmatory claim needs more, such as an economic hypothesis and one primary objective, chosen before any result is seen ([METH-01](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-01-define-the-question-before-measuring-success)); that protocol is proposed, not implemented.

- **Trial Folio does this now** (0.3.0): an experiment's `purpose`, the question it addresses, is required. Trial Folio records it, shows it in the plan and the report, and never sends it ([the research context](../reference/experiment-configuration.md#the-research-context)).
- **By hand now:** choosing the paper, and writing down the claim you'll test and what would count as reproducing it.
- **Planned** (Reproduction and sensitivity workflow, later, without a version): a study record, which keeps the study's method, its experiments, and its findings together.
- **Planned** (Statistical evaluation, later, without a version): confirmatory protocols, whose validation rejects a missing primary objective, benchmark, or cost input.

**The research it answers:** [writing the plan first](#writing-the-plan-first), and [multiple testing in factor research](#multiple-testing-in-factor-research).

### Step 2: Write the plan down before testing

A reproduction's protocol records the paper, the claim, the criteria for reproducing it, the planned deviations, and the version of the analyses it will use, before any test. It's committed before the first test, so its timestamp shows that the criteria came first. Later changes are dated amendments, never edits ([METH-09.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)). It also records what you've already seen. The paper's own sample has been used by its authors, so results over it are retrospective, whatever you do ([METH-09.9](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research), [METH-02.2](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-02-separate-development-selection-and-confirmation)).

- **Trial Folio does this now** (0.3.0): an experiment's plan holds every case, compiled to its full settings, and is recorded in the experiment's directory before the first request. The hash you approve identifies it, so the cases are fixed before any result exists. The experiment declares its prior research, the earlier work on the same idea whose results you saw, in Trial Folio or anywhere else, with its status: `complete`, `partial`, or `unknown`. Trial Folio records the declaration as you wrote it, and can't verify it. A change to the plan is a revision, with a reason, and the earlier cases stay in the record ([plans and approval](plans-and-approval.md), [prior research limits any claim](what-a-backtest-can-support.md#prior-research-limits-any-claim), [revise an experiment](../how-to/revise-an-experiment.md)).
- **By hand now:** the rest of the protocol: the paper, the claim, the criteria, the planned deviations, and the measures you'll compare, written before the first test, and committed to a repository or another record that dates it. Each amendment is added with its date.
- **Planned** (Reproduction and sensitivity workflow, later, without a version): a study record, with dated decisions and amendments.
- **Planned** (Statistical evaluation, later, without a version): a frozen confirmatory protocol, archived before protected results are released ([METH-02.5](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-02-separate-development-selection-and-confirmation)).

A tool on your machine can't prove you never looked at the data elsewhere. The methodology marks that unavailable by nature, and an assessment must say so (METH-02.6).

**The research it answers:** [writing the plan first](#writing-the-plan-first), and [testing many variants](#testing-many-variants).

### Step 3: Build the factor in Portfolio123, and record each deviation

The paper's factor becomes a Portfolio123 formula or ranking system, and its portfolio a screen: a universe, rules, a ranking, holdings, and dates. Exact reproduction is rarely possible without the original data and tools, so the method records how the reproduction differs, rather than hiding it. The deviation record compares each setting with the paper's: the universe, the treatment of microcaps, breakpoints, long-only or long-short construction, weighting, rebalance frequency, the data vendor, point-in-time handling, delisting returns, and the sample period. A setting the paper doesn't give is recorded as unknown, not assumed ([METH-09.3](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)).

Some of the illustrative study's deviations come from Trial Folio itself. Its screens are long-only, where the paper's portfolio is long-short ([P-01](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#proposed-defaults)). They rebalance every week or every 4 weeks, the only frequencies verified so far, where the paper rebalances monthly. And FactSet is the only data vendor ([D-16](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)).

- **Trial Folio does this now** (0.1.0): a screen configuration records every setting, and accepts only the values a live call has verified. The plan shows every setting before anything is sent, with where its value will come from. Trial Folio assumes no benchmark, cost, or end date: you state them, and commission shows as not modeled, never as zero. A formula ranking is recorded completely, while a ranking system named from your account is recorded as not snapshotted ([screen configuration](../reference/screen-configuration.md), [reproducibility](reproducibility.md)).
- **Trial Folio does this now** (0.2.0): a review compares saved runs with a baseline, and separates the changes you declared from unexplained mismatches. It compares runs with each other, not with the paper: the roadmap calls it the first step toward a deviation record ([compare runs](../how-to/compare-runs.md)).
- **By hand now:** writing the formulas, rules, and universe, checking them against Portfolio123's documentation, and writing the deviation record. If a model drafts the formulas, the methodology asks you to keep its first output unedited, and to record each formula that failed or was invented, with its correction ([METH-09.12](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)).
- **Planned** (0.4.0, Ready, not built yet): a ranking system's whole definition, in a file the configuration names, or a snapshot of one saved in your account, so a ranking of several factors is recorded completely.
- **Planned** (Reproduction and sensitivity workflow, later, without a version): a deviation record against the paper's method.
- **Planned** (Optional discovery, later, without a version): recording a model's drafts, with its first output unedited.

**The research it answers:** [how many published factors replicate](#how-many-published-factors-replicate).

### Step 4: Design the experiment: a baseline and fixed variants

The study runs its closest reproduction as a baseline, with a fixed set of variants beside it, each listed before testing. For a reproduction, the methodology proposes four: the paper's construction on the full universe; the same without microcaps, with the cutoff stated; a practitioner's version, a weekly screen used as a buy list, with a rank-drop sell rule; and the paper's construction on each of four slices of the universe, split by a stable identifier. Each runs only where Portfolio123's support for it has been verified ([METH-09.4](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)). A variant whose outcome chooses a candidate is part of the search, not independent evidence for it ([METH-03.3](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing)).

- **Trial Folio does this now** (0.3.0): an experiment configuration declares a baseline screen, and variants that each change one setting: the maximum holdings, the rebalance frequency, the slippage, or a rule, replaced or added. An added rule such as `MktCap > 300` gives the variant without microcaps, with its cutoff stated in the rule. Without a rebalance variant of your own, Trial Folio adds one for the other verified frequency. Every case is compiled before anything is sent ([your first experiment](../tutorials/first-experiment.md), [variants](../reference/experiment-configuration.md#variants)).
- **By hand now:** another universe is another experiment, since the universe isn't a variant ([D-19](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)). Declare the earlier experiment in the later one's prior research, so the search stays visible. A backtest you run outside Trial Folio, on Portfolio123's website, isn't in any experiment's record, since Trial Folio doesn't import results produced elsewhere. It's prior research too, as in the [experiment configuration's example](../reference/experiment-configuration.md#example).
- **Planned** (0.4.0, Ready, not built yet): variants that change the weights of the ranking system's factors, or remove one factor.
- **Planned** (Simulation review, later, without a version): the practitioner's rank-drop sell rule. Sell rules in screen backtests are unverified.
- **Planned** (Reproduction and sensitivity workflow, later, without a version): universe slices, once a study verifies that `StockID` stays the same for each stock across the test period. Trial Folio accepts a `Mod(StockID,4)` rule as it does any added rule, but doesn't offer or label it as a slice ([what R03-T01 verified](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md#what-r03-t01-verified)). Slices share their dates, so they aren't independent confirmations ([METH-09.5](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)).

**The research it answers:** [testing many variants](#testing-many-variants), and [how many published factors replicate](#how-many-published-factors-replicate).

### Step 5: Approve the plan and its budget

- **Trial Folio does this now** (0.1.0 for a screen, 0.3.0 for an experiment): before anything is sent, Trial Folio shows the plan. For an experiment, that's each case, with its `case_id`, its change from the baseline, and its request exactly as it will be sent, and the budget: the most provider requests the experiment may send, with their credits. One approval of the plan's hash covers every case, and nothing is sent without it ([plans and approval](plans-and-approval.md), [credits and uncertain charges](credits-and-uncertain-charges.md), [reviewing an experiment's plan](../tutorials/first-experiment.md#step-2-review-the-plan)).

The approval also fixes the number of tries. The plan names every case before any result exists, so a case added later is a revision, with its reason, not a quiet extra test.

**The research it answers:** [testing many variants](#testing-many-variants).

### Step 6: Run, and resume

- **Trial Folio does this now** (0.3.0): the cases run one at a time, and each attempt is saved before the next case starts. A case that fails is recorded, and the next one runs. A stopped run resumes with the same command, which skips the cases that succeeded. A request that may have been charged, with an unknown outcome, is never sent again on its own: repeating its case needs your confirmation ([recover from an interrupt](../how-to/recover-from-an-interrupt.md), [repeat a case](../how-to/repeat-a-case.md), [credits and uncertain charges](credits-and-uncertain-charges.md)).

Each attempt is part of the research history. A rerun is a new attempt, never a silent replacement ([METH-05.7](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-05-data-integrity-appropriate-to-the-claim)), and a retry isn't a new hypothesis ([METH-03.2](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing)).

**The research it answers:** [multiple testing in factor research](#multiple-testing-in-factor-research).

### Step 7: Compare the cases

- **Trial Folio does this now** (0.3.0): the experiment's report shows the cases' metrics side by side, in the plan's order, with each case's change from the baseline and its coverage. It computes no difference between cases, and ranks or marks none, because picking the best case would be a choice that's part of the search ([why reviews and experiments never rank results](what-a-backtest-can-support.md#why-reviews-and-experiments-never-rank-results)).
- **Trial Folio does this now** (0.2.0): a review compares saved screen runs with a baseline you choose, such as the same screen on another universe, and shows each difference in their settings as declared or unexplained. A review reads runs, not experiments ([compare runs](../how-to/compare-runs.md)).
- **By hand now:** comparing the results with the paper's, and comparing the cases of two experiments, whose reports you read side by side.

**The research it answers:** [how many published factors replicate](#how-many-published-factors-replicate).

### Step 8: Describe the results

The methodology's analyses for a reproduction are descriptive: results before and after the declared trading costs; rolling returns over several holding periods; returns by rank bucket, with the top-minus-bottom spread; and the measures over three periods, before the end of the paper's sample, between it and publication, and after publication. They're a fixed, versioned set, chosen before results and applied the same way to every study, because choosing them after seeing results is data snooping ([METH-09.6 to METH-09.10](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)). These analyses are proposed, not implemented.

- **Trial Folio does this now** (0.1.0): a run's report shows Portfolio123's summary statistics for the strategy and the benchmark, such as total and annualized return, maximum drawdown, and Sharpe ratio, with their units, and never more precisely than Portfolio123 reported them. It shows the coverage against the dates you asked for, and a missing value as unavailable, never zero. The response's per-period returns and daily values are saved, but not interpreted: Trial Folio reconstructs no return series, interval, or drawdown history ([what a backtest can support](what-a-backtest-can-support.md), [outputs](../reference/outputs.md)).
- **Trial Folio does this now** (0.3.0): a slippage variant runs the same screen again with other slippage, such as a higher one, beside the baseline. Commission isn't modeled ([variants](../reference/experiment-configuration.md#variants), [commission isn't modeled](what-a-backtest-can-support.md#commission-isnt-modeled)).
- **By hand now:** any analysis beyond the summary statistics, from the saved results, or from separate runs over each period, which a review shows side by side. Separate backtests with different dates answer a different question from splitting one run's series ([descriptive analysis before further acquisition](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#descriptive-analysis-before-further-acquisition)).
- **Planned** (0.5.0, proposed): a fixed, versioned set of descriptive analyses of archived evidence, with drawdowns, rolling returns, and period splits where the dates are supplied. A descriptive t-statistic of mean excess return, labeled descriptive, is proposed for the same increment ([open questions](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#open-questions)).
- **Planned** (1.1.0, proposed): returns by rank bucket, with the top-minus-bottom spread.
- **Planned** (Reproduction and sensitivity workflow, later, without a version): paired analyses before and after costs, and the period splits in the study's context.

**The research it answers:** [returns after publication](#returns-after-publication).

### Step 9: Check robustness

The methodology asks whether a result survives predefined, reasonable changes, such as neighboring factor weights, removing one factor, liquidity, holdings, rebalancing, and higher costs. It prefers a stable region of reasonable choices to an isolated peak, without making stability an unregistered score to optimize, and asks whether any sensitivity is consistent with the economic hypothesis ([METH-06](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-06-robustness-and-economic-usefulness)). A strong factor diagnostic isn't evidence that a portfolio is tradable (METH-06.8). This assessment is proposed, not implemented.

- **Trial Folio does this now** (0.3.0): the experiment's variants of holdings, rebalancing, slippage, and rules, run beside the baseline. The report's robustness section says it's not assessed, or unavailable, and why: Trial Folio shows the cases, and judges none ([variants](../reference/experiment-configuration.md#variants), [what a backtest can support](what-a-backtest-can-support.md)).
- **By hand now:** judging whether the differences between cases are consistent with the paper's economic idea, and with how the strategy would be traded.
- **Planned** (0.4.0, Ready, not built yet): weight and factor-removal variants.
- **Planned** (1.1.0, proposed): bucket performance, and comparisons of ranking definitions, as descriptive diagnostics, not a scientific assessment without the evidence it requires.
- **Planned** (Reproduction and sensitivity workflow, later, without a version): universe slices, and targeted checks of sensitivity to costs, microcaps, and timing, where supported.
- **Planned** (Simulation review, later, without a version): a portfolio's holdings, transactions, sell rules, turnover, and cash.

**The research it answers:** [testing many variants](#testing-many-variants).

### Step 10: Evaluate

A reproduction's verdict, "reproduced" or "did not reproduce", compares its results with the paper's claim under the criteria written first. It isn't a statistical decision until the methodology's inference methods are validated ([METH-09.11](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)). An inconclusive result is a valid outcome ([METH-04.5](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-04-inference-before-any-statistical-badge)). For a reproduction, the period after publication is out of sample for the paper, but not necessarily unseen by you (METH-09.9).

- **Trial Folio does this now** (0.1.0): every report says statistical validation and trading readiness are not assessed, and keeps a command's success apart from any statement about the strategy ([what a backtest can support](what-a-backtest-can-support.md)).
- **By hand now:** the verdict, under the criteria in your protocol.
- **Planned** (Statistical evaluation, later, without a version): a frozen claim, evaluated with justified chronological boundaries, uncertainty, and inference that accounts for selection. The methodology proposes a design for it, neither implemented nor validated: a frozen family of candidates; a method for each p-value that allows for dependence, a time-block bootstrap or a HAC estimator, chosen in a methods ADR; Holm's adjustment across the family, as the initial procedure to consider; and one application to a holdout no one has touched ([METH-04.1](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-04-inference-before-any-statistical-badge)). It needs the research history Trial Folio records now ([METH-03.5](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-03-research-history-and-multiple-testing)).
- **Planned** (Forward tracking, later, without a version): comparing the signals of frozen definitions with what's observed afterward.

**The research it answers:** [multiple testing in factor research](#multiple-testing-in-factor-research), [testing many variants](#testing-many-variants), and [returns after publication](#returns-after-publication).

### Step 11: Report every case, failures included

Every study and every case is reported on the same terms, whether or not it reproduces the paper. A study is never abandoned or hidden because of its result, and if it stops, the reason is recorded ([METH-09.2](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research)). Reporting only what worked is the selection that inflates performance, as [testing many variants](#testing-many-variants) describes.

- **Trial Folio does this now** (0.1.0): every attempt is recorded, failures included, and every report has the same sections, marking the ones the evidence can't support as unavailable or not assessed. Each report labels its results' nature, backtested, or synthetic for the demo ([what a backtest can support](what-a-backtest-can-support.md), [DSC-04](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-04-actual-simulated-and-hypothetical-results)).
- **Trial Folio does this now** (0.3.0): every planned case is accounted for. The cases that succeeded, failed, were skipped, are unknown, or haven't run add up to the planned cases, in the report and the manifest, and the report lists every case with its outcome ([why every attempt is recorded](reproducibility.md#why-every-attempt-is-recorded), [an experiment's directory](../reference/outputs.md#an-experiments-directory)).
- **By hand now:** the study's report: its question, protocol, deviations, experiments and cases, verdict, and limits, such as a prior-research declaration that isn't `complete`.
- **Planned** (Reproduction and sensitivity workflow, later, without a version): a reproduction report, assembled from the study's record.

**Publishing.** Your reports and other outputs hold Portfolio123 data, which Portfolio123's terms govern, not Trial Folio's license. Publishing results derived from Portfolio123 data, even as charts, may need Portfolio123's written permission, and getting it is your responsibility ([DSC-10](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users), [DSC-06](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-06-portfolio123-notices)). A published result is never a promise, a prediction, or a representation of gains anyone could realize ([DSC-08](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-08-statements-the-project-must-not-make)).

**The research it answers:** [testing many variants](#testing-many-variants), and [writing the plan first](#writing-the-plan-first).

## Where it's specified

- [methodology.md](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md): the research design, a draft whose methods are neither implemented nor validated. [METH-09](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#meth-09-reproducing-published-research) defines a reproduction study, and its [traceability](https://github.com/promptedportfolio/trialfolio/blob/main/docs/methodology.md#traceability) table gives each method's status.
- [Primary use](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#primary-use) and [product direction](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#product-direction), in spec.md.
- [Driving use case coverage](https://github.com/promptedportfolio/trialfolio/blob/main/docs/roadmap.md#driving-use-case-coverage), in roadmap.md: which increment first delivers each need of a reproduction study.
- The release files: [0.1.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.1.0-api-execution.md), [0.2.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.2.0-review.md), [0.3.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.3.0-experiments.md), and [0.4.0](https://github.com/promptedportfolio/trialfolio/blob/main/docs/releases/0.4.0-ranking-weights.md). Each one's status line is its status.
- [DSC-04](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-04-actual-simulated-and-hypothetical-results), [DSC-08](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-08-statements-the-project-must-not-make), and [DSC-10](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users), in disclaimers.md: labeling results, statements the project never makes, and Portfolio123's terms.
