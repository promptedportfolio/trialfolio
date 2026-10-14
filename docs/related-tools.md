# Related tools

**Status:** Verified observations, checked 2026-10-13, with nine checked again, and two added, on 2026-10-14. Recheck before relying on them.
**Written by:** UM-T03 ([user-manual.md](user-manual.md#tasks)), on 2026-10-13

This survey holds the facts behind the user manual's claims about other tools ([rule 10](user-manual.md#rules)): the tools a Portfolio123 member could use for some of what Trial Folio does. A manual page that says what another tool does or doesn't do, or that no other tool does something, cites this file and the date its facts were checked. A fact that another document in `docs/` owns, such as one of [ADR 0001](adrs/0001-python-and-portfolio123-integration.md)'s about `p123api`, keeps citing that document rather than this survey, so the fact has one source. The sections on [DataMiner](#dataminer) and [the API](#the-api-and-its-python-wrapper-p123api) say which of their facts ADR 0001 and ADR 0005 own.

It owns no requirement. Each fact about another tool is a verified observation, with its source and the date it was checked. The owner decided on 2026-10-14 which claim in [what the facts support](#what-the-facts-support) the page on why Trial Folio exists makes. Where a fact here differs from one another document recorded earlier, [changes to facts the project recorded earlier](#changes-to-facts-the-project-recorded-earlier) lists it, and the owner decides whether that document changes.

## What's compared

### What Trial Folio does

Trial Folio is "a configuration-driven command-line tool for collecting, comparing, reproducing, and eventually evaluating investment-strategy evidence from Portfolio123 with scientific discipline" ([spec.md](spec.md#purpose)). It "reuses Portfolio123's research engines and its official Python wrapper". Its own contribution is "controlled experimentation, durable evidence, transparent comparisons, and defensible evaluation". The [README](../README.md) puts it this way: "Portfolio123 does the backtesting. Trial Folio plans each request, records exactly what was sent and returned, and compares the results".

What its releases do, as the README gives them on 2026-10-14:

- **0.1.0** runs one long-only stock screen backtest through the Portfolio123 API. It shows the exact request, its credit cost, and a plan hash, and sends nothing until the user approves. It records every setting next to the result, and keeps the tests that fail.
- **0.2.0** compares saved runs, offline, against a baseline.
- **0.3.0** runs a small, planned experiment: a baseline screen and a few variants of it, "under one approval and one budget", which can be resumed safely. Each variant changes one of four settings. The configuration declares the experiment's purpose, the earlier research on the same idea, and a budget of provider requests. It's built, tested, in private use, and tagged.
- **0.4.0** is specified, but not built yet: an experiment's variants change a ranking system's weights, or remove a factor.

None has been released. No release before the statistical evaluation increment assesses statistical validation or trading readiness.

Its driving use is reproducing published factor research in Portfolio123 ([spec.md](spec.md#primary-use)). That use sets needs the roadmap addresses in order: preregistration, keeping every study and case, a deviation record, fixed variants, and results gross and net of costs. Most of them aren't built yet.

### The questions asked of each tool

| Question | What it asks |
|---|---|
| Engine and data | Whose engine computes the results, and whose data they come from |
| Many variants | Whether it runs many variants of a test as one job |
| What it records | What it keeps of each run, such as settings, versions, times, requests, responses, failures, and costs |
| Before a run | Whether it shows a plan or a cost estimate, or asks for approval, before it runs |
| Study discipline | Whether it supports holdout data, preregistration, or an adjustment for testing many variants |
| Access and license | How it's obtained, its license, and its cost structure |
| Uses Portfolio123 | Whether it uses Portfolio123's engine or data, and how |

Each tool's entry says how it compares with Trial Folio: what it does that Trial Folio does, and what it doesn't. For the factor datasets and the tracking tools, the group's introduction says it once.

## How the survey was done

The survey was done in three parts on 2026-10-13: Portfolio123's own tools; tools others have built on Portfolio123, with the factor datasets and the tracking and preregistration tools; and general backtesting products. Each fact was read from its source that day.

**Sources.**

- Portfolio123's help center, `portfolio123.customerly.help`. A help article's "modified" date is the `dateModified` in its page metadata; the page itself shows only a relative date.
- portfolio123.com's research, data-mining, AI Factor, and legal pages, its [Terms of Use](https://www.portfolio123.com/doc/p123_terms.html), and the API's public [OpenAPI file](https://api.portfolio123.com/docs/api-docs.yml).
- Portfolio123's public forum, `community.portfolio123.com`, read through its public JSON view. A post is cited by topic and post number, with its date. "A Portfolio123 staff account" means the forum marks the account as staff.
- GitHub repositories, their license files, and their source at named commits, with GitHub's public REST and search APIs, read-only. PyPI's public JSON and its simple index.
- Each other product's public pages, documentation, repository, and license file, and WealthLab's public forum.
- The datasets' sites, repositories, and technical documents, and OSF's public API.

**Rules.**

- Public pages only. Nothing was logged into, no form was submitted, and nothing was posted. Nothing was installed, or downloaded and run: source code was read, not run.
- Quotes are exact, including the sources' typos, with curly quotation marks written as straight ones. "…" marks an omission.
- No Portfolio123 plan, price, or entitlement level is named ([DSC-06](disclaimers.md#dsc-06-portfolio123-notices)). For other products the survey gives the cost structure, not the price: prices change, and the link has them.
- Each tool is described factually and neutrally, as [ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md) describes DataMiner. Nothing here judges a tool's quality or fitness for anyone else's purpose.
- No individual is named. A forum member is "a member"; Portfolio123's staff is "a Portfolio123 staff account". Some sources' addresses contain a member's handle, or, for the published factor library, its author's name. The owner decided on 2026-10-14 to keep those links, since each fact needs its source (UM-AC09).

**Labels.** Every fact is a verified observation: the cited source said it when it was checked. "Not found" means the public sources named describe none. It doesn't mean the tool lacks it: anything behind a login wasn't checked. "Not verified" means the survey looked and couldn't confirm. A vendor's claim, such as that its data is point-in-time, is the vendor's statement; the survey didn't test it.

**Limits.**

- **Logged-in features** of Portfolio123 and of every other product weren't checked.
- **Pages that couldn't be read:** Portfolio123's pricing page and DataMiner's Dropbox folder render in the browser, and returned nothing readable. Bloomberg's pages and GuruFocus's tutorial page returned HTTP 403. Zacks's pages blocked the fetcher, and were read as raw page text. QuantConnect's LEAN CLI Morningstar page and Equities Lab's pricing page returned 404. AsPredicted's FAQ page returned "does not exist". Google Drive folders, the Book Optimizer app, and linked spreadsheets weren't opened.
- **Search coverage:** GitHub's repository search covers public repositories, and its code search only indexed files. The forum's search returns at most 50 topics a query; where it reported more, only the first 50 titles were read. PyPI's search page needs JavaScript, so its simple index was matched instead. [The searches](#appendix-the-searches) gives each query and what it returned.
- **Not searched:** Reddit, YouTube, X, Discord, and forums other than Portfolio123's and WealthLab's. Tools shared privately weren't searched either, and couldn't be: several forum posts offer code by direct message. So "none found" applies only to the searches listed.
- **Facts change.** Each was true of its source on its check date. Recheck before relying on one.

**Spot checks.** After the three parts, 14 of the facts that bear most on the claims were checked again against their sources, the same day. Three were corrected here: `p123api` 3.1.0's upload date, which API responses document their cost and quota, and the wording of a quote from WealthLab's extension page. The rest held. On 2026-10-14, in the review of this survey, nine facts the claims rest on were checked again against their sources, and all held: WealthLab's extension page; §17 of Portfolio123's terms; QuantConnect's optimization deployment and pricing pages; Portfolio123's API credits page, its API page for AI Factor, and its list of DataMiner operations; the Download Factors estimate post; and `p123api`'s `client.py`. The review also found a fact the survey had missed: the LEAN CLI asks the user to confirm a cloud optimization's estimated cost before starting it. [LEAN](#lean) and [QuantConnect](#quantconnect) now give it, read from QuantConnect's two optimization deployment pages that day. It found a second: Equities Lab keeps a named backtest's completed results until the user removes them. [Equities Lab](#equities-lab) now gives it, read from its Recent Backtests page that day.

## Summary

One row per tool, with short cells. "Not found" means the public sources checked describe none; "n/a" means the question doesn't apply. The sections below give each cell's sources. Trial Folio's row is for comparison.

| Tool | Engine and data | Many variants | What it records | Before a run | Study discipline | Access and license | Uses Portfolio123 |
|---|---|---|---|---|---|---|---|
| *Trial Folio, for comparison* | Portfolio123's, through `p123api` | Declared variants (0.3.0) | Each request, response, failure, and reported cost | Plan, budget, and approval | Not assessed yet | Custom license; not released | Its API |
| **Portfolio123's own tools** | | | | | | | |
| Screens and screen backtests | Portfolio123's | Not in the screener | Saved screens; run history not verified | Not found | Guidance on curve fitting | Website service | Its own |
| Simulations and books | Portfolio123's | Through the Optimizer or the API | Saved simulations; history not verified | Not found | Guidance; notes | Website service | Its own |
| Ranking systems and Rank Performance | Portfolio123's | One per test; `rank_perf` through the API | Saved systems; downloadable results | Not found | First and second halves | Website service | Its own |
| Optimizer | Portfolio123's | Yes: permutations | Stored studies | Not found | Not found | Website service | Its own |
| AI Factor | Portfolio123's servers and data | Yes: model grids | Validated models and predictions | Hourly training charge; no estimate found | Holdouts, cross-validation, gaps | Extra costs beyond the subscription | Its own |
| Download Factors | Portfolio123's | Many factors a dataset | Settings; metadata in the dataset | Credit estimate | Not found | Uses API credits | Its own |
| FactorMiner | Its own code, on a Portfolio123 dataset | Yes: factors and analyses | Each analysis's parameters, times, status, and errors | Credit estimate for the dataset | "Pre-analysis tool" | Hosted; source declares no license | Its own |
| DataMiner | Portfolio123's, through the API | Yes: YAML iterations | Results CSV; no settings or costs | Not found | Not found | Free download; GPL-3.0 | Its own |
| The API and `p123api` | Portfolio123's | Whatever the caller sends | Responses carry cost and quota; the wrapper keeps the last | No estimate endpoint | n/a | API access; wrapper MIT | Its own |
| Notes; Designer Model revisions | n/a | n/a | Dated notes; disclosed revisions | n/a | Against hindsight bias | Website service | Its own |
| **Built on Portfolio123** | | | | | | | |
| Single-factor testing tool | Portfolio123's, through `rank_perf` | Yes: hundreds of factors | Results file; a 2025 version saves settings | Not found | Not found | Forum code; no license stated | API |
| Members' backtest loops | Portfolio123's, through the API or DataMiner | Yes | Whatever the loop writes | Not found | Not found | Forum code | API |
| P123-Claude-Skill | Portfolio123's, through `p123api` | One call a script | Prints cost and quota; CSV | Not found | Factor-replication recipes | MIT | API |
| Backtest-review Claude skill | None: analyzes the user's returns | Not verified | Not stated | n/a | Deflated Sharpe, overfitting tests | MIT; free | Not stated |
| Dashboard123 | Portfolio123's API; no backtests | No | Cached holdings, notes | n/a | Not found | MIT | API |
| P123_PySR | Its own, on exported data | Yes: formula search | Saved sessions | Not found | Temporal holdout | MIT | Exported data |
| HFRE | Its own, on a factor download | Yes: grid search | HTML report | Not found | Walk-forward or holdout | Free; closed source | Exported data |
| Quant Toolkit | Its own, on a downloaded dataset | Reruns | Projects; HTML report | Not found | Leakage checks | Free download; no license stated | Exported data |
| P123 Book Optimizer | Its own, on exported results | Weight optimization | Not mentioned | Not found | Not mentioned | Hosted; cost not stated | Exported results |
| finantic.Portfolio123 | WealthLab's engine; Portfolio123's rankings | WealthLab's | Not described | Not found | WealthLab's | Paid extension; WealthLab subscription | API: rankings |
| QuantSolvings Factors page | Portfolio123's simulations | Six factors, three universes | Published curves | n/a | Not stated | Free to view | Simulations |
| Optimization aids | Portfolio123's Optimizer, or their own | Yes | Not described | Not found | Cross-validation in one | Spreadsheet; code by message | Optimizer or exports |
| Smaller projects (11) | Varied | Varied | Varied | Not found | Not found | Varied | Varied |
| **General backtesting products** | | | | | | | |
| LEAN | Its own; the user's data | Yes: grid, Euler | JSON results a run | In the cloud, an estimate to confirm | Walk-forward in code | Apache-2.0 | Not found |
| QuantConnect | LEAN; Morningstar fundamentals | Yes: grid | Parameters, code, version, errors | Cost estimate to confirm; stops when credit runs out | Probabilistic Sharpe ratio | Free plan; paid tiers | Not found |
| zipline-reloaded | Its own; the user's data | Not found | Performance file | Not found | Not found | Apache-2.0 | Not found |
| Backtrader | Its own; the user's data | Yes | Parameters and analyzers | Not found | Not found | GPL-3.0 | Not found |
| vectorbt and VectorBT PRO | Its own; the user's data | Yes: thousands at once | Saved objects | Not found | Splitters; deflated Sharpe | Apache-2.0 with Commons Clause; PRO paid | Not found |
| backtesting.py | Its own; the user's prices | Yes: grid, SAMBO | Stats with trades | Not found | Examples only | AGPL-3.0 | Not found |
| bt | Its own; the user's prices | Several together | Result object | Not found | Random-portfolio benchmark | MIT | Not found |
| QuantRocket | Its own; Sharadar by subscription | Yes: parameter scans | Results CSV | Not found | Walk-forward, for ML | Free sample tier; paid | Not found |
| Qlib | Its own; the user's data | Yes: task queues | Parameters, metrics, artifacts | Not found | Train, valid, and test segments | MIT | Not found |
| WealthLab | Its own; the user's providers | Yes: optimizers | Saves and resumes long runs | Not found | Walk-forward, out-of-sample | Subscription | Through an extension |
| Zacks Research Wizard | Zacks's | Not found | Saved screens; Excel export | Not found | Not found | Paid; free trial | Not found |
| Equities Lab | Its own; Morningstar built in | Not found | Trade log; named backtests' results, until removed | Not found | Not found | Subscription; free trial | Not found |
| GuruFocus screener backtest | GuruFocus's | Not found | Results and holdings | Not found | Not found | Membership | Not found |
| Portfolio Visualizer | Its own; Morningstar, CSI, others | Not found | Saved portfolios and results | Not found | Not found | Free and paid plans | Not found |
| **Factor datasets** | | | | | | | |
| Open Source Asset Pricing | Its authors' code; CRSP, Compustat, others | 212 predictors | Versioned releases | n/a | Placebos | Free downloads; code GPL-2.0; some data needs WRDS | No |
| Global Factor Data (jkpfactors.com) | Its authors' code; WRDS data | 153 factors, 93 countries | Dated updates | n/a | Not described | Data CC BY-NC 4.0; code MIT | No |
| q-factor data library | Its authors'; CRSP, Compustat | 201 anomalies | Dated releases | n/a | Not described | Free downloads; terms not stated | No |
| Tuck School data library | Its authors'; CRSP, Compustat | Many sorts and regions | Monthly updates | n/a | n/a | Free downloads | No |
| **Tracking and preregistration** | | | | | | | |
| MLflow | None: records the user's code | Logs nested runs | Parameters, metrics, commit, failed status | n/a | Not found | Apache-2.0 | Not found |
| Weights & Biases | None | Sweeps | Config, metrics, commit, run state | n/a | Not found | Client MIT; free and paid tiers | Not found |
| DVC | None | Queued sweeps | Parameters, metrics, Git commit | n/a | Not found | Apache-2.0 | Not found |
| OSF Registries | None | n/a | Frozen, timestamped registration | It holds the plan | Preregistration | Free; hosting a registry costs | A member's project |
| AsPredicted | None | n/a | Timestamped PDF | It holds the plan | Preregistration | Free, per a secondary source | Not found |

## Portfolio123's own tools

### Screens and screen backtests

Checked 2026-10-13.

- **What it is:** The screener filters a universe by rules and backtests them, with "Advanced tools like rolling backtests and hedging" ([Stock Screener][hc-13610]). A screen backtest puts an equal amount into each passing stock, and compounds from one rebalance to the next ([Reproduce a simulation with the screener][hc-13881]).
- **Engine and data:** Portfolio123's. Research backtests use "FactSet's historical database (or S&P Compustat if you have a license with them)" ([Introduction][hc-13609]). Portfolio123 states it has "Point-In-Time data with no survivorship or look-ahead biases" ([Research Tools][p123-research]). It always includes dead companies, and uses the provider's effective dates, falling back to SEC filing dates, then to fixed lags ([Backtesting biases][hc-13678]). Estimates aren't snapshotted: "We do not snapshot other data, which will, on rare occasions, change a little" ([a Portfolio123 staff account, 2021][f-59479-29]).
- **Many variants:** Not as a batch inside the screener, in the sources read. Batches go through the Optimizer, DataMiner, or the API.
- **What it records:** Screens are saved items that count against the account's Resource Units ([Resource Units][hc-13619]). Whether the site keeps a history of a screen's backtests, settings, or versions: not verified. The only direct statement found is from 2015, about a universe and a ranking system: "Unfortunately we have no history of the changes" ([a Portfolio123 staff account][f-45787-2]). It may not describe today's site.
- **Before a run:** The help pages describe no plan, cost estimate, or approval step ([Stock Screener][hc-13610], [Introduction][hc-13609]).
- **Study discipline:** [Backtesting biases][hc-13678] names curve fitting and congruence bias. It suggests rerunning a strategy without the stocks a previous run used, and using rolling simulations and rank performance tests. The pages read describe no preregistration, holdout setting, or adjustment for testing many variants.
- **Access and license:** A website service under Portfolio123's [terms][p123-terms].
- **Compared with Trial Folio:** Trial Folio runs the same kind of screen backtest, through the API's `/screen/backtest`. The website runs it interactively.
- **Not verified:** whether website backtests use API credits.

### Simulations and books

Checked 2026-10-13.

- **What it is:** A strategy combines a universe, a ranking system, buy and sell rules, position sizing, hedging, and restrictions into a "virtual portfolio manager". It's tested as a simulation, then can be launched live ([Portfolio Strategy][hc-13612]). Books run "simulations of multiple strategies together with different weights" ([Research Tools][p123-research]).
- **Engine and data:** Portfolio123's engines, "which are as point-in-time as we can make them" ([Portfolio Strategy][hc-13612]). Trades fill at one reference price, with an advanced, variable, or fixed slippage model ([Simulation Assumptions][hc-13753], [Transaction Cost Model][hc-65080]). Simulations and screen backtests treat shares and dividends differently, so "The results will almost never be identical" ([Reproduce a simulation with the screener][hc-13881]).
- **Many variants:** Through the Optimizer, or through the API. `strategy_rerun` takes start and end dates and trading-system settings, such as the universe, ranking system, rules, and rebalancing ([OpenAPI file][p123-openapi], [API: Strategy][hc-43325]). On testing sell-rule variants, a Portfolio123 staff account wrote in 2026 that the rerun endpoint "lets you modify the sell rules (and other things) in the simulation and rerun it", and that the user can store the details "in a file for each sell rule tested" ([post][f-76489-3]).
- **What it records:** A simulation is a saved item ([Resource Units][hc-13619]). The API returns a strategy's "summary, holdings, statistics and performance", and its transactions for a date range ([OpenAPI file][p123-openapi], [API: Strategy][hc-43325]).
- **Before a run:** None found.
- **Study discipline:** [Portfolio Strategy][hc-13612] warns of the "data-mining" trap: changing "PE < 20" to "PE < 19.63" because the simulated return improved. A Portfolio123 staff account wrote in 2024 that "the only realistic, real life method is out of sample" ([post][f-67247-18]). Notes can be attached to a strategy ([below](#notes-designer-model-revisions-and-planned-apps)). No preregistration, holdout setting, or multiple-testing adjustment found.
- **Compared with Trial Folio:** Trial Folio's 0.3.0 varies screen settings, not simulations. The website and the API rerun simulations with changed settings, and the user keeps each result.
- **Not verified:** whether a simulation keeps its earlier runs or settings when it's rerun or edited; whether `strategy_rerun` saves the changed settings into the simulation; whether website simulations use API credits.

### Ranking systems and Rank Performance tests

Checked 2026-10-13.

- **What it is:** A ranking system orders a universe's stocks by weighted factor and composite nodes, as a percentile rank ([Ranking System][hc-13611], [How Ranking Works][hc-17976]). Rank Performance "is a powerful tool used to backtest ranking systems". It splits the ranked stocks into quantiles on each rebalance date, and reports returns by quantile ([Rank Performance][hc-13770]). It was redesigned on 2024-02-08 ([a Portfolio123 staff account][f-66025-1]).
- **Engine and data:** Portfolio123's. Missing values rank "NA Negative" by default, or "NA Neutral" ([How Ranking Works][hc-17976]).
- **Many variants:** The website runs one ranking system a test, and the Optimizer runs weight variants. The API's `rank_perf` "allows you to run multiple consecutive rank performance tests programmatically", for example one for each factor in a spreadsheet ([Rank Performance][hc-13770]). Through the API, an inline ranking definition updates one shared system, `ApiRankingSystem`, with `rank_update`. `rank_create`, marked new, creates a named system ([API: Rank][hc-43323]).
- **What it records:** Ranking systems are saved items ([Resource Units][hc-13619]). The redesign lets users "Download all the data to do your own analysis" ([post][f-66025-1]). Shared systems change in place: "Changes to shared resources automatically propagate to everyone using them" ([Sharing Resources][hc-43819]). Whether past test runs are kept: not verified.
- **Before a run:** None found.
- **Study discipline:** Statistics are shown for the whole period, and separately for its first and second halves. The page also recommends tests on "unrelated universes" ([Rank Performance][hc-13770]). A Portfolio123 staff account wrote in 2025: "It's a 100% curve fitting process basically". It said the half-period view "helps a bit", and that Portfolio123 is "brainstorming bringing cross-validation and weight optimization to classic ranking system" ([post][f-67823-7]). No multiple-testing adjustment found.
- **Compared with Trial Folio:** Trial Folio's 0.4.0, specified but not built yet, varies a ranking system's weights through the same API path. Portfolio123 already runs weight studies on the website, and `rank_perf` tests through the API.
- **Not verified:** whether past Rank Performance runs are kept; whether they use API credits.

### The Optimizer

Checked 2026-10-13.

- **What it is:** Launched in 2012 as tools "for automatically running simulations and ranking system performance test with permutations": of a simulation's rules and settings, or of a ranking system's node weights ([a Portfolio123 staff account, 2012][f-32268-1]). Portfolio123's page today: "Optimizer to find the best weights" ([Data Mining][p123-mining]). In 2026, a staff account gave the steps for a trading-system study, ending "Generate Combinations, then Run Combinations" ([post][f-76489-2]).
- **Engine and data:** Portfolio123's.
- **Many variants:** Yes. The user defines the permutations, and the tool generates and runs the combinations ([2012 launch post][f-32268-1], [2026 post][f-76489-2]).
- **What it records:** Studies are saved items ([Resource Units][hc-13619]). "Each permutation stores a lot of data" ([a Portfolio123 staff account, 2013][f-36891-2]). A running study's progress reappears when the user returns to it ([2023][f-63244-3]). A study shows its permutations' results together ([2012 launch post][f-32268-1]).
- **Before a run:** None found.
- **Study discipline:** None found. In 2024 a staff account wrote "The optimizer is for adjusting weights", and planned statistics for the "entire period and the two halves" ([post][f-66025-33]). Whether that shipped: not verified.
- **Compared with Trial Folio:** This is Portfolio123's own tool for running many variants of a simulation or a ranking system, with stored results. Trial Folio's 0.3.0 runs a finite set of declared screen variants, and excludes "Automatic search, adaptive variant generation, and optimization" ([0.3.0](releases/0.3.0-experiments.md)).
- **Not verified:** its current limit on permutations, which was 10 at its 2012 beta launch; what a study stores today, and whether it records the settings it ran with; whether Optimizer runs use API credits. Separately, a Portfolio123 staff account described automating its own ranking-weight tests "with a combination of the P123 API and Selenium" ([2026][f-76521-8]). That's a fact about one workflow, not about the Optimizer.

### AI Factor

Checked 2026-10-13.

- **What it is:** A no-code machine-learning workflow: a target, universe, features, dataset, validation of many models, and a trained predictor used through `AIFactor()` in ranking systems, screens, and rules ([AI Workflow][hc-30638], [AI Factors User Guide][hc-34576], [What Is the AI Factor?][hc-41457]).
- **Engine and data:** Portfolio123's servers ("workers") and data. The user chooses the worker ([AI Factors User Guide][hc-34576]). In backtests, `AIFactor()` "can only be used up to 5 years in the past" ([AI Factors User Guide][hc-34576]).
- **Many variants:** Yes. "The Grid tool can be used to generate a matrix of hyperparameter combinations"; the guide's example "created 120 models" ([AI Factors User Guide][hc-34576]). The Data Mining page still labels AI grid search "(coming soon)" ([Data Mining][p123-mining]), so the two pages differ.
- **What it records:** Validated models and their results, compared "using metrics like RMSE, Spearman's rank, or raw portfolio performance"; saved validation predictions, optionally; and predictors ([AI Factors User Guide][hc-34576]).
- **Before a run:** Training is charged "based on the time utilized for training", at a rate set by the worker chosen ([AI Factors User Guide][hc-34576]). AI Factor "has some costs in addition to your Portfolio123 subscription" ([Costs of AI Factor][hc-35810]). No estimate or approval step for a run found.
- **Study discipline:** Holdouts and validation are built in. Validation uses "a separate portion of the dataset called the validation holdout set", with a gap "to avoid data leakage". The methods include a basic holdout, time-series and rolling time-series cross-validation, and blocked k-fold. A backtest is "only valid if the start date of the backtest period is later than the end date of the predictor training period plus a gap" ([AI Factors User Guide][hc-34576]). Portfolio123's own S&P 500 model keeps "a long, untouched holdout period" ([model overview][hc-61649]). The workflow page warns that more iterations raise "the chances of over-fitting" ([AI Workflow][hc-30638]). In 2024 a staff account listed the Deflated Sharpe Ratio among "things we haven't considered for our AI implementation" ([post][f-66362-1]).
- **Access and license:** A website service, with costs beyond the subscription ([Costs of AI Factor][hc-35810]). The API has only `aifactor_predict`: training and validation have no endpoint ([API: AI Factor][hc-43320], [OpenAPI file][p123-openapi]).
- **Compared with Trial Folio:** AI Factor already provides holdout periods, cross-validation, gaps, and a comparison of many models, for machine-learning factors, inside Portfolio123. Trial Folio does no machine learning, and its releases don't yet assess statistical validity.
- **Not verified:** whether AI Factor keeps a dated history of settings or validation runs; whether a multiple-testing adjustment has shipped since 2024.

### Download Factors

Checked 2026-10-13.

- **What it is:** Research > Tools > Download Factors builds a factor list and generates a dataset, for AI work and for FactorMiner ([FactorMiner][hc-53980], [launch post][f-76504-1]).
- **Engine and data:** Portfolio123's. Generating a dataset uses API credits ([FactorMiner][hc-53980]).
- **What it records:** "Settings are saved between downloads", and a Save As was added ([a Portfolio123 staff account, 2024][f-65947-1]). The dataset "contains all the metadata (factor formulas, names, settings, etc) used to generate it" ([2025][f-75497-20]). The account's API usage can be downloaded from Account Settings ([2024 post][f-65947-1]).
- **Before a run:** It shows an API-credit estimate before generating. A Portfolio123 staff account explained on 2026-07-31: "The estimate is based on the current universe size". So the estimate can be too low when a universe held more stocks in early years. In its test, the estimate was 181 credits, and the use 227 ([post][f-76682-2]).
- **Compared with Trial Folio:** This is Portfolio123's own example of an API-credit estimate shown before a run. Trial Folio's plan also gives the credits before anything is sent.
- **Not verified:** what the downloadable usage report lists: each request, its time, its endpoint, or its cost.

### FactorMiner

Checked 2026-10-13.

- **What it is:** A "Tool to analyze datasets and identify high-alpha factors", which automates single-factor analysis ([FactorMiner][hc-53980]). Live since 2026-05-03 ([launch post][f-76504-1]).
- **Engine and data:** A dataset from Download Factors, from Portfolio123's data. The computation is FactorMiner's own Python code, not Portfolio123's backtest engine. "Transaction prices in FactorMiner are based on the next close", and its results "will show slight deviations" in a screen or ranking-system backtest ([FactorMiner][hc-53980]). Portfolio123 hosts it as "a Streamlit app running in our servers" ([launch post][f-76504-1]).
- **Many variants:** Yes: many factors an analysis, and "multiple analysis per dataset with different parameters" ([a Portfolio123 staff account, 2025][f-75497-20]).
- **What it records:** "The results are saved, and can be named and annotated" ([2025 post][f-75497-20]). The source stores one JSON file an analysis, with its status, creation, start, and finish times, dataset version, parameters, notes, results, and any error ([models.py][gh-fm-models], [analysis_service.py][gh-fm-service]). "Use Last Settings" restores the previous configuration ([FactorMiner][hc-53980]).
- **Before a run:** Generating the dataset shows a credit estimate (Download Factors). For the analysis itself, none found.
- **Study discipline:** Portfolio123 calls it "a pre-analysis tool. Always validate results in full trading simulations". Alpha and beta "do not currently correct for the risk-free rate" ([FactorMiner][hc-53980]). Its IC t-statistic is a one-sample t-test on each date's IC ([factor_analysis.py, line 179][gh-fm-analysis]). No holdout or multiple-testing adjustment is documented, and none was found in the analysis source's imports.
- **Access and license:** Launched from Download Factors, on Portfolio123's servers. Portfolio123 writes that "FactorMiner is an open source project", which users can download and run locally ([launch post][f-76504-1]). Its [repository][gh-fm] declares no license: GitHub reports none, and the tree has no LICENSE file. Its last push was 2026-05-29, at `d814c5df`.
- **Compared with Trial Folio:** FactorMiner keeps a dated, parameterized, annotated record of each analysis, failures included. That's close to Trial Folio's records, but it's for screening single factors in a downloaded dataset with its own code, not for backtests on Portfolio123's engine.
- **Not verified:** whether the hosted version matches the public source. The two differ in one place found: the help gives the correlation threshold's default as 0.50, and the source's default is 0.7.

### DataMiner

Checked 2026-10-13.

- **What it is:** A desktop app to "run dozens of backtest with a single click", including "multiple backtest variations of screens and ranking systems", and to download data ([DataMiner][hc-13764]). It runs operations from YAML files: Data, DataUniverse, RankMulti, RankPerformance, Ranks, RanksPeriod, RollingScreen, ScreenBacktest, and ScreenRun ([DataMiner Operations][hc-13772]).
- **Engine and data:** Portfolio123's, through the API. Its public source imports `p123api` ([repository][gh-dm]). RankPerformance "runs a screen backtest for each bucket", and its output "includes many more statistics than what the website offers" ([RankPerformance][hc-14052]). In 2023 a Portfolio123 staff account wrote that it has no function "for running rolling ranking performance tests" ([post][f-62174-3]).
- **Many variants:** Yes. A script's iterations each hold "overrides of the settings in the prior iteration" ([RankPerformance][hc-14052], [RollingScreen][hc-14057]). An inline ranking definition creates a system in the account that "will always contain the version specified by the last iteration" ([Ranking Definition][hc-13793]). In the public source, ScreenBacktest runs one backtest without iterations, and RollingScreen and RankPerformance iterate ([operation.py][gh-dm-operation]).
- **What it records:** In the public source, version 1.1.7 ([cons.py][gh-dm-cons]), the output table can be saved as CSV, or auto-saved to a folder. An auto-saved file is named `<operation>_<YYYYMMDD_HHMMSS>.csv`: a timestamp in the file name, not in the contents ([data_miner.py, lines 604 to 610][gh-dm-save]). Rows hold the results, with each iteration's name. No settings, DataMiner version, credit cost, or quota is written, and the source never reads `cost` or `quotaRemaining`. Errors go to a local log and to the app's console.
- **Before a run:** "DataMiner operations may use multiple API endpoints so their costs is the sum of all the endpoints used" ([API Cost and Monthly Cap][hc-13766]). The public source has no estimate or approval step. The documented defaults include an end date of today and a slippage of 0 ([ScreenBacktest][hc-14056], [RankPerformance][hc-14052], [RollingScreen][hc-14057]).
- **Study discipline:** None found.
- **Access and license:** Downloaded from a Dropbox folder linked from the API-key page, with versions for Linux, macOS, and Windows ([DataMiner][hc-13764]). "DataMiner is an open-source project" ([DataMiner][hc-13764]). The [repository][gh-dm] is licensed GPL-3.0, with two commits; the last was pushed 2025-02-19.
- **Compared with Trial Folio:** DataMiner is Portfolio123's official no-code client for running batches of API operations from configuration files. Trial Folio is also a configuration-driven client over `p123api`, and covers fewer operations. Trial Folio records what DataMiner's public source doesn't write: settings, costs, attempts, and failures.
- **Not verified:** the version distributed now, and whether it differs from the public source, since the Dropbox listing couldn't be read; the owner's report that the macOS build is unsigned ([ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md#context)), since nothing was downloaded.
- **Facts other documents own:** [ADR 0001's verification notes](adrs/0001-python-and-portfolio123-integration.md#verification-notes) own DataMiner's license, its distribution, its last push at `721f3dea`, its saved credentials, its ScreenBacktest defaults, and what its pinned source suggests about its output. [ADR 0005's context](adrs/0005-build-on-the-portfolio123-api-only.md#context) owns what its exports record, and the owner's report on its macOS build. A manual page cites those documents for these facts ([rule 10](user-manual.md#rules)). Where this section differs from them, [changes to facts the project recorded earlier](#changes-to-facts-the-project-recorded-earlier) lists it.

### The API and its Python wrapper, p123api

Checked 2026-10-13.

- **What it is:** A REST API at api.portfolio123.com, with a public [Swagger page][p123-swagger] and [OpenAPI file][p123-openapi], "P123 API" version 1.0.0. Its groups cover authentication, AI Factor prediction, data, data series, ranking systems, screens, stock factors, strategies, and universes. `p123api` wraps each endpoint, and handles "retries, authentication and low level http request" ([The API Wrapper][hc-13765]). Portfolio123 presents the API as the alternative to screen scraping, which "is very unreliable" ([Introduction to the API][hc-13919]).
- **Engine and data:** Portfolio123's. `pitMethod`, Complete or Prelim, is a request parameter ([API: Screen][hc-43324]). The data operations need a vendor license beyond a small trial set ([API: Data Retrieval][hc-43321]).
- **Many variants:** Whatever the caller's code sends. There's no batch endpoint for backtests. `ApiUniverse` and `ApiRankingSystem` are single shared objects in each account, updated in place ([API: Universe][hc-43322], [API: Rank][hc-43323]). A screen backtest can return `406` "Another request is already running" ([OpenAPI file][p123-openapi]).
- **What it records:** The OpenAPI file documents `cost` and `quotaRemaining` in a shared result schema. 35 of its 39 documented success responses include it, the screen backtest's among them; those of `/auth`, `GET /rank`, `/rank/create`, and `/rank/{id}/touch` don't. It documents `402` "Request quota exhausted" and `409` "Operation failed" ([OpenAPI file][p123-openapi]). `p123api` copies `cost` and `quotaRemaining` onto the client after each call, where the next call overwrites them, and it has no logging ([client.py][gh-api-client]). The account's remaining credits are shown on the Dashboard and in Account Settings ([API Cost and Monthly Cap][hc-13766]).
- **Before a run:** No estimate endpoint or dry run found ([OpenAPI file][p123-openapi], [API Cost and Monthly Cap][hc-13766]).
- **Credits:** Each endpoint has a fixed or dynamic cost, and "The minimum cost when an API endpoint is invoked is 1 API credit". The monthly cap "depends on your membership". Unused credits "do not roll over to the next month", and "Purchased credits never expire" ([API Cost and Monthly Cap][hc-13766]). Documented costs include 5 credits for `screen_backtest` and for `screen_rolling_backtest`, 2 for `screen_run` ([API: Screen][hc-43324]), 3 for `rank_perf`, and 1 each for `rank_update`, `rank_create`, and `rank_get` ([API: Rank][hc-43323]). Portfolio123's terms say such costs "may be amended at Company's sole discretion from time to time without notice" (§15, [terms][p123-terms]).
- **Access and license:** The API needs an API ID and key, created on the website ([DataMiner][hc-13764]). `/auth` can return `402` "Paying subscription required" ([OpenAPI file][p123-openapi]). `p123api` is licensed MIT, on [PyPI][pypi-p123api] and [GitHub][gh-api]. Its latest stable release is 3.1.0, uploaded 2026-08-25, and pre-releases 3.1.1a1 (2026-09-03) and 3.1.1a2 (2026-09-22) followed ([PyPI][pypi-p123api]).
- **Compared with Trial Folio:** Trial Folio is built on this wrapper and endpoint ([ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md)). Anything Trial Folio sends, a user's own script could send. What Trial Folio adds is what it records and checks around each call.
- **Not verified:** whether failed requests are charged, which the credits page, the Screen API page, and the OpenAPI file don't say; rate limits, beyond a `429` documented for `/data/prices`.
- **Facts other documents own:** [ADR 0001's verification notes](adrs/0001-python-and-portfolio123-integration.md#verification-notes) own the project's facts about `p123api` at its pinned commit, `7b449eeb`: its license, version 3.1.0 and its date, how it returns `cost` and `quotaRemaining` and copies them onto the client, its retries, and its errors. They also own a screen backtest's cost of 5 credits, and that whether failed requests are charged is unverified. A manual page cites ADR 0001 for these facts ([rule 10](user-manual.md#rules)). Where this section differs from it, [changes to facts the project recorded earlier](#changes-to-facts-the-project-recorded-earlier) lists it.

### Notes, Designer Model revisions, and planned apps

Checked 2026-10-13.

- **Notes:** "a simple note feature can become a powerful tool to combat hindsight bias". Notes attach to a stock, the account, or a strategy, and all of them appear on one page, where they can be edited and searched ([Notes][hc-13606]).
- **Designer Model revisions:** A launched Designer Model can be revised "once every six months", and Portfolio123 directs its designer to send subscribers "a brief explanation of the revision" ([Launching Designer Models][hc-13614]). "Portfolio123 tracks how the live model's recommendations have done since launch" ([Follow Designer Models][hc-13737]). It's a record kept after launch, with disclosed changes, for published models.
- **Preregistration, approval, and testing adjustments:** The help pages and forum searches found no preregistration, no plan approved before running, and no multiple-testing adjustment in any Portfolio123 tool. Staff posts of 2024 discuss the Deflated Sharpe Ratio as not yet considered ([one][f-66362-1], [another][f-67247-18]). [The searches](#searches-for-portfolio123s-own-features) give the queries.
- **Apps:** A Portfolio123 staff account wrote in 2025 that "Apps will have access to storage and API endpoints", and that their development "will depend on the interest from community to develop third party apps" ([post][f-75497-20]). In 2026: "The plan is to get the flywheel moving with apps that do all sorts of stuff" ([post][f-76343-15]). Alphanaut, Portfolio123's AI agent in the screener, was announced 2026-03-25 ([topic 76418][f-76418]). It wasn't surveyed.

[hc-13606]: https://portfolio123.customerly.help/en/articles/13606-notes
[hc-13609]: https://portfolio123.customerly.help/en/articles/13609-introduction
[hc-13610]: https://portfolio123.customerly.help/en/articles/13610-stock-screener
[hc-13611]: https://portfolio123.customerly.help/en/articles/13611-ranking-system
[hc-13612]: https://portfolio123.customerly.help/en/articles/13612-portfolio-strategy
[hc-13614]: https://portfolio123.customerly.help/en/articles/13614-launching-designer-models-faq
[hc-13619]: https://portfolio123.customerly.help/en/articles/13619-resource-units
[hc-13678]: https://portfolio123.customerly.help/en/articles/13678-backtesting-biases
[hc-13737]: https://portfolio123.customerly.help/en/articles/13737-follow-designer-models-faq
[hc-13753]: https://portfolio123.customerly.help/en/articles/13753-simulation-assumptions
[hc-13764]: https://portfolio123.customerly.help/en/articles/13764-dataminer
[hc-13765]: https://portfolio123.customerly.help/en/articles/13765-the-api-wrapper-p123api
[hc-13766]: https://portfolio123.customerly.help/en/articles/13766-api-credits
[hc-13770]: https://portfolio123.customerly.help/en/articles/13770-how-to-run-a-rank-performance-test
[hc-13772]: https://portfolio123.customerly.help/en/articles/13772-dataminer-operations
[hc-13793]: https://portfolio123.customerly.help/en/articles/13793-dataminer-ranking-definition
[hc-13881]: https://portfolio123.customerly.help/en/articles/13881-how-to-reproduce-a-strategy-backtest-using-the-screener
[hc-13919]: https://portfolio123.customerly.help/en/articles/13919-introduction-to-the-api-and-tools
[hc-14052]: https://portfolio123.customerly.help/en/articles/14052-dataminer-operation-ranks-performance
[hc-14056]: https://portfolio123.customerly.help/en/articles/14056-dataminer-operation-screen-backtest
[hc-14057]: https://portfolio123.customerly.help/en/articles/14057-dataminer-operation-rolling-screen
[hc-17976]: https://portfolio123.customerly.help/en/articles/17976-how-ranking-works
[hc-30638]: https://portfolio123.customerly.help/en/articles/30638-ai-workflow
[hc-34576]: https://portfolio123.customerly.help/en/articles/34576-ai-factors-user-guide
[hc-35810]: https://portfolio123.customerly.help/en/articles/35810-costs-associated-with-using-aifactor
[hc-41457]: https://portfolio123.customerly.help/en/articles/41457-what-is-the-ai-factor
[hc-43320]: https://portfolio123.customerly.help/en/articles/43320-api-ai-factor
[hc-43321]: https://portfolio123.customerly.help/en/articles/43321-api-data-retrieval
[hc-43322]: https://portfolio123.customerly.help/en/articles/43322-api-universe
[hc-43323]: https://portfolio123.customerly.help/en/articles/43323-api-rank
[hc-43324]: https://portfolio123.customerly.help/en/articles/43324-api-screen
[hc-43325]: https://portfolio123.customerly.help/en/articles/43325-api-strategy
[hc-43819]: https://portfolio123.customerly.help/en/articles/43819-sharing-resources
[hc-53980]: https://portfolio123.customerly.help/en/articles/53980-factorminer
[hc-61649]: https://portfolio123.customerly.help/en/articles/61649-ai-factor-s-p500-model-configuration-overview
[hc-65080]: https://portfolio123.customerly.help/en/articles/65080-transaction-costs-model-a-k-a-slippage
[p123-research]: https://www.portfolio123.com/research
[p123-mining]: https://www.portfolio123.com/research/dataminer-api
[p123-terms]: https://www.portfolio123.com/doc/p123_terms.html
[p123-swagger]: https://api.portfolio123.com/docs/index.html
[p123-openapi]: https://api.portfolio123.com/docs/api-docs.yml
[gh-dm]: https://github.com/portfolio-123/dataminer
[gh-dm-cons]: https://github.com/portfolio-123/dataminer/blob/721f3deaa8bcb564846229506e6f84e3a41f9008/cons.py
[gh-dm-save]: https://github.com/portfolio-123/dataminer/blob/721f3deaa8bcb564846229506e6f84e3a41f9008/data_miner.py#L604-L610
[gh-dm-operation]: https://github.com/portfolio-123/dataminer/blob/721f3deaa8bcb564846229506e6f84e3a41f9008/p123/operation.py
[gh-fm]: https://github.com/portfolio-123/factor-miner
[gh-fm-analysis]: https://github.com/portfolio-123/factor-miner/blob/d814c5df5000dc536de65a578da6ce42c05b17bf/src/core/calculations/factor_analysis.py#L179
[gh-fm-models]: https://github.com/portfolio-123/factor-miner/blob/d814c5df5000dc536de65a578da6ce42c05b17bf/src/core/types/models.py
[gh-fm-service]: https://github.com/portfolio-123/factor-miner/blob/d814c5df5000dc536de65a578da6ce42c05b17bf/src/workers/analysis_service.py
[gh-api]: https://github.com/portfolio-123/p123api-py
[gh-api-client]: https://github.com/portfolio-123/p123api-py/blob/master/p123api/client.py
[pypi-p123api]: https://pypi.org/project/p123api/
[f-32268-1]: https://community.portfolio123.com/t/32268/1
[f-36891-2]: https://community.portfolio123.com/t/36891/2
[f-45787-2]: https://community.portfolio123.com/t/45787/2
[f-59479-29]: https://community.portfolio123.com/t/59479/29
[f-62174-3]: https://community.portfolio123.com/t/62174/3
[f-63244-3]: https://community.portfolio123.com/t/63244/3
[f-65947-1]: https://community.portfolio123.com/t/65947/1
[f-66025-1]: https://community.portfolio123.com/t/66025/1
[f-66025-33]: https://community.portfolio123.com/t/66025/33
[f-66362-1]: https://community.portfolio123.com/t/66362/1
[f-67247-18]: https://community.portfolio123.com/t/67247/18
[f-67823-7]: https://community.portfolio123.com/t/67823/7
[f-75497-20]: https://community.portfolio123.com/t/75497/20
[f-76343-15]: https://community.portfolio123.com/t/76343/15
[f-76418]: https://community.portfolio123.com/t/say-hello-to-alphanaut-our-new-ai-agent/76418
[f-76489-2]: https://community.portfolio123.com/t/76489/2
[f-76489-3]: https://community.portfolio123.com/t/76489/3
[f-76504-1]: https://community.portfolio123.com/t/76504/1
[f-76521-8]: https://community.portfolio123.com/t/76521/8
[f-76682-2]: https://community.portfolio123.com/t/76682/2

## Tools others have built on Portfolio123

These come from public repositories, pages, and forum threads, found by [the searches](#searches-for-tools-built-on-portfolio123). A forum topic is at `https://community.portfolio123.com/t/<topic>`, and a post at `/t/<topic>/<post>`.

### Single-factor testing tool

Checked 2026-10-13.

- **What it is:** A script a member posted in 2021 ([post 1][t59260-1]). It reads a spreadsheet of "hundreds of factors or formulas", "automatically runs ranking system performance tests for each of them and writes the results to a file". An Excel sheet then scores each factor ([post 6][t59260-6]). It began as a Google Colab notebook, and members later posted local Python versions ([post 44][t59260-44]). A Portfolio123 staff account replies in the thread as the script's maintainer, and wrote on 2024-02-22: "The Colab script has been fixed" ([post 41][t59260-41]). The next day it wrote: "This is currently the only tool that automates running rank performance tests on a large number of different factors" ([post 43][t59260-43]). That was before FactorMiner.
- **Engine and data:** Portfolio123's, through the API's rank performance operation ([post 6][t59260-6]). The posted versions hard-code `PitMethod = "Prelim"` ([post 44][t59260-44], [post 54][t59260-54]).
- **Many variants:** Yes: one rank performance test a factor.
- **What it records:** The results go to an output file, a workbook in the local versions. A member's version of 2025-09-13 saves "all run settings to a "Settings" sheet in the output file", resumes "from the last completed factor if stopped", and writes a temporary file it renames on completion ([post 54][t59260-54]). On 2023-05-02 the same staff account reported the tests using "2 credits per test" ([post 37][t59260-37]). The Rank API page now gives `rank_perf` as 3 credits ([API: Rank][hc-43323], modified 2026-07-24).
- **Before a run:** None described.
- **Study discipline:** None built in. The thread cautions that "you are looking back to see which factors performed well in the past" ([post 13][t59260-13]). Post 6 suggests splitting the universe, and looking for factors that work in both parts: a robustness check, not a holdout.
- **Access and license:** A public Google Drive folder, not opened, and code in the thread. No license stated in the posts read. It needs Portfolio123 API credentials. The latest post is from 2026-02-27.
- **Compared with Trial Folio:** It runs a batch of Portfolio123 tests through the API. Its 2025 version saves each run's settings with the results, and resumes. The posts show no plan, approval, or budget, and no saved responses.
- **Not verified:** whether any version saves raw requests or responses, or a log of failed factors.

### Members' scripts that loop screen backtests

Checked 2026-10-13.

- **What they are:** Threads in which members batch screen backtests. In 2024, a loop backtests each ranking system named in a CSV, for "a large quantity of ranking systems (2000)" ([topic 67749][t67749]). In 2023, a member feeds "100x RS" into DataMiner's ScreenBacktest ([topic 63573][t63573]). Another 2023 thread asks for code to test "thousands of ranking systems" with re-weighted nodes, to "(over)optimize" ([topic 63454][t63454]).
- **Engine and data:** Portfolio123's, through the API or DataMiner.
- **What they record:** Whatever the loop writes. The 2024 reply writes each backtest's results. No settings or response archive, plan, or failure accounting is described.
- **Access and license:** Code in public forum posts, with no license.
- **Compared with Trial Folio:** Like a Trial Folio experiment, they run many Portfolio123 backtests through the API that differ in one input.

### P123-Claude-Skill

Checked 2026-10-13.

- **What it is:** An open-source "Agent Skill" that "turns Claude into a reliable Portfolio123 (P123) assistant": writing screen rules and formulas, building ranking-system XML, "replicating published factors", and pulling data through `p123api`. It's an "Independent community project", "not affiliated with, sponsored by, or endorsed by Portfolio123" ([README][skill]).
- **Engine and data:** Portfolio123's. Its nine example scripts call the screen, rank, data, and AI Factor prediction operations, and a gated rebalance ([scripts/README.md][skill-scripts]).
- **Many variants:** No batch runner: each script runs one call, "teaching examples first, utilities second".
- **What it records:** The scripts print `cost` and `quotaRemaining` after each call, and the tabular ones save a CSV with `--csv`. No log of settings, requests, responses, or failures is described.
- **Study discipline:** [factor-replication.md][skill-replication] gives "35 recipes" for published anomalies. It lists "Seven constructions P123 genuinely cannot reproduce", each with "the closest honest proxy", and carries "No performance figures". No preregistration, holdout, or multiple-testing feature found.
- **Access and license:** MIT. Releases v4.0.0, v4.1.0, and v4.1.1, all of 2026-09-17 ([commits][skill-commits]). Announced on the forum ([topic 76399][t76399], [topic 76818][t76818]).
- **Compared with Trial Folio:** The closest third-party match to Trial Folio's driving use. It maps published factors to Portfolio123 constructions, and says where Portfolio123 can't match the paper, as Trial Folio's planned deviation record would ([METH-09](methodology.md#meth-09-reproducing-published-research)). It's guidance for an agent, not a record of runs.

### A backtest-review Claude skill

Checked 2026-10-13.

- **What it is:** A free Claude skill from QuantSolvings, "built from 71 quant finance papers", that reviews a backtest the user supplies. Its scripts include "deflated Sharpe", "probability of backtest overfitting", "purged cross-validation", a "static scanner for look-ahead bias in backtest code", and a "minimum backtest length calculation" ([release post, 2026-07-29][qs-skill], [topic 76679][t76679]).
- **Engine and data:** It runs no backtests. It analyzes a CSV of dates and returns, or files the user points it to. The page doesn't say it connects to Portfolio123, and it names P123-Claude-Skill as a companion.
- **What it records:** Not stated.
- **Access and license:** "MIT licensed and open source", and free, downloaded from quantsolvings.com. No GitHub link found.
- **Compared with Trial Folio:** It covers statistical checks that Trial Folio's methodology leaves for later ([METH-03](methodology.md#meth-03-research-history-and-multiple-testing), [METH-04](methodology.md#meth-04-inference-before-any-statistical-badge)), on results the user brings. It doesn't run or record Portfolio123 work.
- **Not verified:** which inputs each test needs, and whether its overfitting tests take several variants' results.

### Dashboard123

Checked 2026-10-13.

- **What it is:** An "Open-source desktop dashboard for monitoring your Portfolio123 strategies, screens, and rankings in real time", built with Streamlit. A rebalance panel can "commit trades via P123 API" ([README][dash], [forum, 2026-03-09][t76382]).
- **Engine and data:** Portfolio123's API for holdings, screen runs, ranks, strategies, and rebalancing. It makes no backtest calls ([p123_client.py][dash-client]). Other panels use yfinance, FRED, and Finnhub.
- **What it records:** Holdings "cached to disk", and notes for each ticker. No run history.
- **Access and license:** MIT. Created 2026-03-06; last push 2026-04-10. A copy, [S-P500-dashboard][dash-copy], has a shortened copy of its README.
- **Compared with Trial Folio:** Both use the official API. Dashboard123 monitors live strategies, and runs no backtests.

### P123_PySR

Checked 2026-10-13.

- **What it is:** A Streamlit app that searches for formulas by symbolic regression on exported Portfolio123 data, and translates them into "P123 syntax" for ranking nodes ([README][pysr], [forum, 2026-04-09][t76450]).
- **Engine and data:** Its own computation, PySR, on "panel data from P123's Data Miner or AI Factor export" that the user uploads. No API calls found.
- **Many variants:** It searches many candidate formulas, and compares formulas side by side.
- **What it records:** "Session persistence". No run log described.
- **Study discipline:** "Temporal holdout - automatic train/test split by date to prevent overfitting", and "IS vs OOS validation".
- **Access and license:** MIT. "No support is offered." Created and last pushed 2026-04-09.
- **Compared with Trial Folio:** It searches outside Portfolio123, on exported data. It has a holdout, which Trial Folio's methodology plans for later ([METH-02](methodology.md#meth-02-separate-development-selection-and-confirmation)).

### HFRE, the Hierarchical Factor Ranking Engine

Checked 2026-10-13.

- **What it is:** A desktop app that "builds a Portfolio123 Ranking System using a structured, two-layer linear hierarchy", and exports it as XML ([forum release thread, 2026-02-08][t76207]).
- **Engine and data:** Its own models, fitted on a CSV from Portfolio123's factor download. The user backtests the exported system in Portfolio123.
- **Many variants:** Yes, inside the app. Version 2.5, of 2026-02-21, added a grid search for the validation settings.
- **What it records:** "an HTML report that can be saved as reference".
- **Study discipline:** "Walk-forward Time Series CV or Basic Holdout".
- **Access and license:** "free to use but closed source": a Windows executable, in beta.
- **Compared with Trial Folio:** It generates ranking-system candidates offline. It doesn't run or record Portfolio123 backtests.

### Quant Toolkit

Checked 2026-10-13.

- **What it is:** A beta desktop tool for "Advanced Pre-Training Analysis" of features, including "automated data leakage detection", with an HTML report ([forum, 2026-01-02][t75604]).
- **Engine and data:** Its own analysis of a dataset downloaded once from Portfolio123.
- **What it records:** "Save/Load projects".
- **Access and license:** A free download; the beta was "fully functional until January 14, 2026". No license stated. Its status since then: not verified.
- **Compared with Trial Folio:** It analyzes downloaded data offline, and makes no Portfolio123 runs.

### P123 Book Optimizer

Checked 2026-10-13.

- **What it is:** A hosted app for "a simple weight optimization" across the strategies in a book ([guide, 2026-03-23][bookopt], [topic 76413][t76413]).
- **Engine and data:** Performance CSVs the user exports from each strategy. No API calls mentioned. It "can only work with the historical data you provide".
- **What it records, and study discipline:** Not mentioned.
- **Access and license:** A hosted web app, not opened. Its cost, license, and source aren't stated.
- **Compared with Trial Folio:** It works on the exported results of Portfolio123's simulations.

### finantic.Portfolio123 (WealthLab extension)

Checked 2026-10-13.

- **What it is:** A commercial WealthLab extension: "A two-way connection between Wealth-Lab and Portfolio123". It downloads historical ranking results for a ranking system and a universe, builds WealthLab DataSets from them, such as the top 50 stocks each quarter, and gives access to the fundamentals the ranking contains. It also sends WealthLab indicators to Portfolio123 as a data series or a stock factor ([extension page][wl-ext]).
- **Engine and data:** The rankings come from Portfolio123. Backtests run in WealthLab's engine, with prices from another provider: the page requires "A historical data provider like Norgate Data" ([extension page][wl-ext]). On WealthLab's forum, the extension's author wrote: "The Portfolio123 API allows the download of historical ranking data only. There is no download for Screens." (2025-03-15). It downloads a ranking "just once and stores it on the local" machine to save credits (2025-03-17) ([beta thread][wl-beta]). On 2025-09-11 the author wrote: "You have to reformulate the formulas and conditions from your screen to a ranking" ([release thread][wl-release]). These are the author's statements, not Portfolio123's. Portfolio123's API does run screen backtests ([API: Screen][hc-43324]), so they describe what the extension downloads as data.
- **Many variants and study discipline:** WealthLab's own ([below](#wealthlab)).
- **What it records:** Not described.
- **Access and license:** A paid annual extension, with a 14-day trial; "all Extensions require a WealthLab Subscription". It also needs Portfolio123 API access and a price-data provider. Initial release: "WealthLab 8 Build 1", 2025-03-18 ([extension page][wl-ext]).
- **Compared with Trial Folio:** An existing third-party integration with Portfolio123's API, since March 2025. Its backtests run on WealthLab's engine, not Portfolio123's.
- **Not verified:** whether it records the requests and responses it makes; which API operation it uses.

### QuantSolvings Factors page

Checked 2026-10-13.

- **What it is:** A public page of "Daily simulated equity curves" for six factors, including value, momentum, and quality, on three universes of US stocks defined by size, from 2000, updated "Every weekday". It's labeled "Research illustration only" ([factors page][qs-factors]).
- **Engine and data:** "Portfolio123 strategy simulations". The practice "is an independent practice, not owned by or part of Portfolio123".
- **Access and license:** No fee stated for viewing. No code published.
- **Compared with Trial Folio:** Published factor results computed on Portfolio123's engine: a comparison point, not a tool.
- **Not verified:** how the factors are constructed; the linked articles weren't read.

### Optimization aids

Checked 2026-10-13.

- A "Ranking System optimizer" spreadsheet, a new version posted in 2015, generates node-weight permutations for Portfolio123's Optimizer ([topic 45889][t45889]). The linked file wasn't opened.
- A 2025 thread in which a member describes a genetic-algorithm weight search, then 5-fold cross-validation, on DataMiner downloads. The member offered the code by direct message rather than posting it ([topic 70837][t70837]).
- A 2026 post describes an Optuna hyperparameter search for models trained on Portfolio123 data ([topic 76359][t76359]).

None describes what it records, or a preregistration or testing adjustment. Compared with Trial Folio, they search for variants around Portfolio123 rankings, and keep no records that the posts describe.

### Smaller projects

Checked 2026-10-13, with GitHub's API or the forum.

| Project | What it does with Portfolio123 | Status |
|---|---|---|
| [puts-backtest](https://github.com/ricardoatencio2105-tech/puts-backtest) | Gets weekly S&P 500 ranks from `/rank/ranks`, and backtests selling puts on options data in its own engine | 2026-01-26; README says MIT, no license file |
| [RankToGod](https://github.com/itayt23/RankToGod) | Combines `rank_ranks` with scores from other sites into one weighted score | 2023-05-04 to 2023-09-07; no license |
| [market-dashboard](https://github.com/smallfishmacro-Git/market-dashboard) | Pulls S&P 500 aggregate series with `p123api` in a GitHub Actions job | Last push 2026-10-13; no license |
| [P123-AUTO](https://github.com/TOURINGNO/P123-AUTO) | Logs into the website with browser automation, not the API, runs two screens, and copies the results to Google Sheets | 2026-07-22; no license |
| [LLM123](https://github.com/remmosnoraa/LLM123) | Copies of Portfolio123 reference documents, for LLM use | 2026-03-14 to 2026-03-15 |
| [TradingStrategy](https://github.com/itayt23/TradingStrategy) | Lists `p123api` as a requirement; its backtester and optimizer are its own, and no Portfolio123 calls were found | 2024-01-23 |
| [Swing-Long-System](https://github.com/LongVu5228/Swing-Long-System) | One script loads Portfolio123 API credentials; its calls weren't identified | Last push 2026-09-25 |
| [ib-bandit-trade-optimizer](https://github.com/jrinne314/ib-bandit-trade-optimizer) | Chooses among a broker's order algorithms, "designed as a lightweight proof-of-concept for the Portfolio123 community"; no Portfolio123 calls | MIT |
| [A program for P123 users](https://community.portfolio123.com/t/a-program-for-p123-users/37410) | Compares two portfolios' downloaded transaction files | Forum post, 2013 |
| [A factor library viewer](https://community.portfolio123.com/t/ken-french-database-explorer/72007) | A Streamlit viewer of a published factor library's sort portfolios; no Portfolio123 link | Forum post, 2025-05-19 |
| [Sector allocation app](https://community.portfolio123.com/t/streamlit-app-to-check-historical-sector-allocation/76558) | Shows a strategy's historical sector allocation, from rules the user prepares | Forum post, 2026-05-28 |

[t59260-1]: https://community.portfolio123.com/t/single-factor-testing-tool-developed-using-the-api/59260
[t59260-6]: https://community.portfolio123.com/t/single-factor-testing-tool-developed-using-the-api/59260/6
[t59260-13]: https://community.portfolio123.com/t/single-factor-testing-tool-developed-using-the-api/59260/13
[t59260-37]: https://community.portfolio123.com/t/single-factor-testing-tool-developed-using-the-api/59260/37
[t59260-41]: https://community.portfolio123.com/t/single-factor-testing-tool-developed-using-the-api/59260/41
[t59260-43]: https://community.portfolio123.com/t/single-factor-testing-tool-developed-using-the-api/59260/43
[t59260-44]: https://community.portfolio123.com/t/single-factor-testing-tool-developed-using-the-api/59260/44
[t59260-54]: https://community.portfolio123.com/t/single-factor-testing-tool-developed-using-the-api/59260/54
[t45889]: https://community.portfolio123.com/t/new-ranking-system-optimizer-spreadsheet/45889
[t63454]: https://community.portfolio123.com/t/automatically-test-and-optimize-ranking-systems/63454
[t63573]: https://community.portfolio123.com/t/dataminer-screenbacktest-test-x-numbers-of-rankingsystems/63573
[t67749]: https://community.portfolio123.com/t/colab-mass-screen-backtest/67749
[t70837]: https://community.portfolio123.com/t/genetic-algorithm-to-replace-manual-optimizaton-in-p123-classic/70837
[t75604]: https://community.portfolio123.com/t/algomans-quant-toolkit-advanced-pre-training-analysis-for-tree-based-models/75604
[t76207]: https://community.portfolio123.com/t/algoman-hfre-v2-4-hierarchical-factor-ranking-engine-download/76207
[t76359]: https://community.portfolio123.com/t/minimize-turnover-cost-with-ai-models-hyperparameter-grid-search/76359
[t76382]: https://community.portfolio123.com/t/dashboard123-a-real-time-streamlit-portfolio-dashboard-for-p123-users/76382
[t76399]: https://community.portfolio123.com/t/open-source-p123-skill-for-ai-coding-agents-claude-code-cursor-codex/76399
[t76413]: https://community.portfolio123.com/t/p123-book-optimizer/76413
[t76450]: https://community.portfolio123.com/t/symbolic-regression-for-feature-generation-free-streamlit-app-made-for-p123/76450
[t76679]: https://community.portfolio123.com/t/a-free-claude-skill-that-argues-with-your-backtest/76679
[t76818]: https://community.portfolio123.com/t/releasing-p123-claude-skill-v4-1-1/76818
[skill]: https://github.com/cmoralesm/P123-Claude-Skill
[skill-scripts]: https://github.com/cmoralesm/P123-Claude-Skill/blob/main/scripts/README.md
[skill-replication]: https://github.com/cmoralesm/P123-Claude-Skill/blob/main/references/factor-replication.md
[skill-commits]: https://github.com/cmoralesm/P123-Claude-Skill/commits/main
[qs-skill]: https://quantsolvings.com/insights/free-quant-investor-claude-skill/
[qs-factors]: https://quantsolvings.com/factors/
[dash]: https://github.com/Algoman123/Dashboard123
[dash-client]: https://github.com/Algoman123/Dashboard123/blob/main/services/p123_client.py
[dash-copy]: https://github.com/gloual88/S-P500-dashboard
[pysr]: https://github.com/Algoman123/P123_PySR
[bookopt]: https://systvest.substack.com/p/my-portfolio123-book-optimizer
[wl-ext]: https://wealth-lab.com/extension/detail/Portfolio123
[wl-beta]: https://wealth-lab.com/Discussion/WANTED-Beta-Tester-for-Portfolio123-extension-12272
[wl-release]: https://wealth-lab.com/Discussion/Build-1-of-Portfolio123-extension-released-12300

## General backtesting products and libraries

Each library below accepts the user's own data. Whether a member may move Portfolio123 data into one is a matter of Portfolio123's terms ([DSC-10](disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users)), which this survey doesn't decide. A product's repository dates come from GitHub's API, and its release dates from GitHub or PyPI.

### LEAN

Checked 2026-10-13.

- **What it is:** QuantConnect's open-source engine, "an event-driven, professional-caliber algorithmic trading platform" ([repository][lean]).
- **Engine and data:** Its own engine. Running it locally "requires you to have your own local data" ([LEAN CLI custom data][lean-custom]). The CLI lists QuantConnect's own datasets and third-party providers ([LEAN CLI datasets][lean-datasets]).
- **Many variants:** `lean optimize` runs a grid search, "all possible combinations of parameters", or an Euler search, with a target statistic and constraints ([optimization deployment][lean-opt]).
- **Before a run:** Locally, "After configuring the constraints the optimizer starts running". A cloud optimization, `lean cloud optimize`, runs on QuantConnect's nodes. It shows the estimated number of backtests, batch time, and batch cost, and the organization's balance, then asks "Do you want to start the optimization on the selected node type? [Y/n]" ([optimization deployment][lean-opt], checked 2026-10-14). No budget cap besides the balance is described ([QuantConnect](#quantconnect)).
- **What it records:** Each backtest's results, in JSON files in a timestamped folder, and one JSON file for each backtest of an optimization ([backtesting deployment][lean-bt], [optimization deployment][lean-opt]).
- **Study discipline:** Walk-forward optimization inside an algorithm, "periodically adjusting the logic or parameters of a strategy". No separate holdout period, or feature for planning a study, found ([walk-forward optimization][qc-wfo]).
- **Access and license:** Apache-2.0 ([LICENSE][lean-license]). Last push 2026-10-12. To use the CLI, "you must be a member in an organization on a paid tier" ([LEAN CLI custom data][lean-custom]).
- **Uses Portfolio123:** No integration documented. A code search for "portfolio123" in QuantConnect's GitHub organization returned nothing.
- **Compared with Trial Folio:** It runs many variants of one strategy, and keeps each result in a timestamped folder, on its own engine and data. In the cloud, it asks the user to confirm a batch's estimated cost before starting it.
- **Not verified:** whether its result files record the LEAN version, the data version, or the parameters.

### QuantConnect

Checked 2026-10-13.

- **What it is:** A hosted research, backtesting, and live-trading platform built on LEAN, with a free plan and paid tiers ([pricing][qc-pricing]).
- **Engine and data:** LEAN, in QuantConnect's cloud. US fundamentals are Morningstar's, for about 8,000 US equities from January 1998, delisted companies included. A filing date is used when present; "For older symbols, the file date is approximated 45 days after the as of date". Figures are "As Original Reported". From 2026-09-23, fundamentals come from new feeds, "so backtest results change", and backtests run on the earlier data "will not reproduce" ([Morningstar fundamentals][qc-morningstar]). Cloud access to this data is listed as "Free" ([dataset listing][qc-dataset]).
- **Many variants:** Cloud optimization "runs concurrent backtests", on up to 24 nodes. "Grid search is the only strategy currently available" ([strategies][qc-opt-strategies], [deployment][qc-opt-deploy]).
- **Before a run:** The deployment wizard estimates a job's cost, once the algorithm has been backtested, and "The final cost that you pay can vary from the estimate". The job deducts the cost as each backtest completes, "and stops when all credit is consumed" ([deployment][qc-opt-deploy]). A backtest that throws a runtime error "will not complete but you will still be charged" ([optimization results][qc-opt-results]). After the estimate, the wizard's last step is "Click Launch Optimization" ([deployment][qc-opt-deploy], checked 2026-10-14), and the LEAN CLI asks the user to confirm a cloud optimization's estimate before starting it ([LEAN](#lean)). No budget cap besides the credit balance is described.
- **What it records:** A backtest's page shows "the project files used to run the backtest", and its logs. Backtests with a runtime error stay in the project's table ([backtest results][qc-bt-results]). The API's backtest record holds the parameters used, its creation time, status, error, and stack trace, and a "LEAN Version" statistic ([backtest statistics API][qc-api]). An optimization counts its failed backtests ([optimization results][qc-opt-results]).
- **Study discipline:** A warning to "be wary of overfitting" ([optimization][qc-opt]). A "Probabilistic Sharpe Ratio" statistic, whose description doesn't mention the number of variants tested ([backtest statistics API][qc-api]). No feature for planning a study, or for holding out data, found.
- **Access and license:** A free plan with "unlimited backtesting" on one backtest node, and paid tiers. QuantConnect Credit pays for optimization and for local data downloads. Other datasets are bought separately ([pricing][qc-pricing]). The platform is proprietary; its engine is LEAN.
- **Uses Portfolio123:** No integration documented.
- **Compared with Trial Folio:** The closest match among the general products to Trial Folio's records and budget: each backtest's parameters, code, engine version, time, and errors, and a cost estimate that the user confirms before a batch, with a stop when credit runs out. It runs on QuantConnect's engine and Morningstar data, not Portfolio123's.
- **Not verified:** whether a backtest's record identifies the data version used.

### zipline-reloaded

Checked 2026-10-13.

- **What it is:** A maintained fork of Quantopian's Zipline, "a Pythonic event-driven system for backtesting" ([repository][zipline]). Release 3.1.1, on PyPI 2025-07-19.
- **Engine and data:** Its own engine, on data the user brings as a "bundle". The default bundle's source has been discontinued, and "no longer updates" ([bundles][zipline-bundles]). Fundamentals can enter through loaders, whose dates "should be labelled with the first date on which a value would be available to an algorithm" ([DataFrameLoader][zipline-loader]). So point-in-time correctness depends on how the user dates the data.
- **Many variants:** None found: one strategy a run.
- **What it records:** A performance file. An option selects an earlier data ingestion by its timestamp ([bundles][zipline-bundles]).
- **Access and license:** Apache-2.0; free.
- **Compared with Trial Folio:** It backtests rules on a stock universe from code, and can pin a data ingestion. No batch of variants or run record beyond its output.

### Backtrader

Checked 2026-10-13.

- **What it is:** A "Python Backtesting library for trading strategies" ([repository][backtrader]). Last push 2024-08-19; latest PyPI release 1.9.78.123, of 2023-04-19.
- **Engine and data:** Its own engine. The user supplies the data; fundamentals can be added as extra lines on a feed ([extending a data feed][backtrader-feed]).
- **Many variants:** Optimization runs a strategy over parameter sets, on several CPU cores, and each run returns its parameters and analyzers ([optimization][backtrader-opt]).
- **What it records:** A writer saves a CSV stream, and a summary of the strategies' parameters and the analyzers' results ([writer][backtrader-writer]).
- **Access and license:** GPL-3.0; free.
- **Compared with Trial Folio:** It runs parameter variants, and can write each one's parameters next to its outputs, on its own engine and the user's data.

### vectorbt and VectorBT PRO

Checked 2026-10-13.

- **What it is:** A vectorized Python backtesting library, "the community edition" of VectorBT PRO ([repository][vbt]). Release v1.1.2, of 2026-10-09.
- **Engine and data:** Its own engine. Price adapters, such as Yahoo Finance; no fundamentals named ([features][vbt-features]). PRO lists "20+" data sources ([vectorbt.pro][vbt-pro]).
- **Many variants:** It "packs thousands of configurations into NumPy arrays" ([repository][vbt]). PRO: "Sweep millions of parameter combinations" ([PRO optimization][vbt-pro-opt]).
- **What it records:** Objects "can be saved to a file and retrieved back" ([features][vbt-features]).
- **Study discipline:** Rolling and expanding walk-forward splitters, and train and test splits ([splitters][vbt-splitters]). A deflated Sharpe ratio, whose number of trials defaults to the number of columns: the variants in the run ([returns accessors][vbt-returns]). PRO adds purged splits, permutation tests, and baselines ([PRO optimization][vbt-pro-opt]). No feature for planning a study found.
- **Access and license:** The open-source edition is Apache 2.0 with the Commons Clause, which withholds "the right to Sell the Software" ([LICENSE.md][vbt-license]). PRO is a paid membership, monthly, annual, or lifetime, with a "Private source repository" ([vectorbt.pro][vbt-pro]).
- **Compared with Trial Folio:** It runs many variants as one computation, and its deflated Sharpe ratio adjusts for the number of variants tested: a step no Trial Folio release assesses yet. It runs on its own engine and data.

### backtesting.py

Checked 2026-10-13.

- **What it is:** "a Python framework for inferring viability of trading strategies on historical (past) data" ([docs][btpy]). Release 0.6.6, on PyPI 2026-07-22.
- **Engine and data:** Its own engine, on a DataFrame of open, high, low, and close prices the user brings ([API docs][btpy-api]). No portfolio-level stock selection or fundamentals found.
- **Many variants:** `Backtest.optimize` searches a grid, exhaustively or at random, or with SAMBO, and can return the results of every admissible combination ([API docs][btpy-api]).
- **What it records:** A statistics series that includes the strategy, the equity curve, and the trades ([API docs][btpy-api]).
- **Study discipline:** An example tells users to "always split your data into train and test sets" ([ML example][btpy-ml]). It's an example, not a built-in feature.
- **Access and license:** AGPL-3.0; free.
- **Compared with Trial Folio:** It sweeps parameters and keeps every combination's result, for strategies on one instrument's prices, on its own engine.

### bt

Checked 2026-10-13.

- **What it is:** "Flexible Backtesting for Python" ([docs][bt]). Release v1.4.1, of 2026-10-10.
- **Engine and data:** Its own engine, on prices the user supplies. Its Yahoo data access is deprecated ([bt source][bt-init]).
- **Many variants:** `run` "Runs a series of backtests and returns a Result object" ([backtest.py][bt-backtest]). No optimizer found.
- **Study discipline:** `benchmark_random` compares a backtest with "a number of random portfolios" ([backtest.py][bt-backtest]). No holdout or testing adjustment found.
- **Access and license:** MIT; free.
- **Compared with Trial Folio:** It runs and compares several backtests together, on its own engine and data.

### QuantRocket

Checked 2026-10-13.

- **What it is:** Self-hosted software to "Research and trade quantitative strategies in global markets using Python", which "runs anywhere Docker runs". It bundles Zipline, Alphalens, and its own backtesters, Moonshot and MoonshotML ([quantrocket.com][qr]).
- **Engine and data:** Its own. Fundamentals come from Sharadar, for "Users who subscribe to Sharadar data through Nasdaq Data Link" ([docs][qr-docs]). The docs describe a "Point-in-time dimension to data", and say its Pipeline "processes data in a point-in-time fashion that prevents lookahead bias".
- **Many variants:** "1-dimensional or 2-dimensional parameter scans" ([docs][qr-docs]).
- **What it records:** A results CSV, and, for a walk-forward run, a zip file with the results and the trained model ([docs][qr-docs]).
- **Study discipline:** MoonshotML supports "rolling and expanding walk-forward optimization" ([docs][qr-docs]). No testing adjustment or planning feature found.
- **Access and license:** A free tier with sample data, and paid full access ([pricing][qr-pricing]). Its client, Moonshot, and Zipline fork are Apache-2.0.
- **Uses Portfolio123:** The documentation doesn't mention Portfolio123, and a code search in its GitHub organization returned nothing.
- **Compared with Trial Folio:** It scans strategy variants on point-in-time fundamentals from a separate subscription, on its own engine.
- **Not verified:** whether its results record the parameters, software version, or data version.

### Qlib

Checked 2026-10-13.

- **What it is:** "an open-source, AI-oriented quantitative investment platform" from Microsoft ([repository][qlib]). Release v0.9.8, of 2026-10-08.
- **Engine and data:** Its own engine. "The official dataset is disabled temporarily", and its collected public data "might not be perfect" ([repository][qlib]). A point-in-time database keeps financial-report data as of each date ([PIT][qlib-pit]); its collector's example downloads Chinese stocks ([PIT collector][qlib-pit-collector]).
- **Many variants:** Task management can "automatically generate and execute different tasks", and "fetch undone tasks automatically" ([task management][qlib-tasks]).
- **What it records:** A YAML configuration drives each run. A recorder logs parameters, metrics, artifacts, and tags, with an implementation based on MLflow ([workflow][qlib-workflow], [recorder][qlib-recorder]).
- **Study discipline:** The example configuration has separate train, valid, and test periods ([workflow][qlib-workflow]).
- **Access and license:** MIT; free.
- **Compared with Trial Folio:** Configuration-driven runs, recorded parameters and artifacts, resumable task queues, and a point-in-time store: close in kind to Trial Folio's records and resume, on its own engine and the user's data.

### WealthLab

Checked 2026-10-13.

- **What it is:** A commercial backtesting and trading platform, WealthLab 9 ([wealth-lab.com][wl], [features][wl-features]).
- **Engine and data:** Its own engine. Data comes from a built-in provider and from data-provider extensions; fundamentals "from many data vendors", none named ([features][wl-features]).
- **Many variants:** "Built-in Exhaustive and Shrinking Window optimizers" ([features][wl-features]).
- **What it records:** "Save long optimization runs to disk and resume your analysis later" ([features][wl-features]). Walk-forward results are saved as they progress, and WealthLab "attempts to continue a previously saved incomplete WFO instead of rerunning completed intervals" ([WFOOptimizer][wl-wfo]).
- **Study discipline:** A walk-forward optimization "divides the available historical data into a sequence of in-sample and out-of-sample intervals" ([WFOOptimizer][wl-wfo]). No testing adjustment or planning feature found.
- **Access and license:** A proprietary subscription, monthly, annual, or lifetime ([plans][wl-plans]).
- **Uses Portfolio123:** Yes, through the paid finantic.Portfolio123 extension ([above](#finanticportfolio123-wealthlab-extension)).
- **Compared with Trial Folio:** It saves and resumes long runs, as Trial Folio resumes experiments, on its own engine.
- **Not verified:** whether WealthLab records each run's settings and software version.

### Zacks Research Wizard

Checked 2026-10-13.

- **What it is:** "a powerful custom equity screening program" with backtesting, on "Zacks data servers" ([product page][zacks]).
- **Engine and data:** Zacks's. Zacks's published strategy results "assume no transaction costs". Zacks states that "Backtesting can at times produce an unintended look-ahead bias", and that the program is aligned "to the extent possible" to eliminate it ([About Zacks Performance][zacks-perf]). Zacks's pages give three different lengths of history: 5, 7, and 12 years ([Research Wizard][zacks-rw], [screener guide][zacks-guide], [offer][zacks-offer]).
- **Many variants:** None found. A separate Zacks Pro Backtester, for advisors, can "run automated backtesting routines to verify a model's robustness" ([Pro Backtester][zacks-pro]).
- **What it records:** Saved screens, and results exported to Excel ([offer][zacks-offer]).
- **Access and license:** Proprietary and paid, with a free trial; pricing by contacting Zacks ([product page][zacks]).
- **Compared with Trial Folio:** It backtests fundamental stock screens on a vendor's database, as Portfolio123 does.

### Equities Lab

Checked 2026-10-13.

- **What it is:** A web platform for screening, backtesting, and simulation ([equitieslab.com][eqlab]).
- **Engine and data:** Its own engine, with Morningstar data built in: "This means no data fees for you". Its dataset contains delisted stocks ([FAQ][eqlab-faq]). It claims "no survivorship bias, no lookahead bias, no restatement bias" ([equitieslab.com][eqlab]). These are the vendor's claims.
- **Many variants:** None found.
- **What it records:** A log of every trade ([FAQ][eqlab-faq]). A backtest sent to the background is named: "Name the strategy and press okay". Its completed results "will stay instantly available to you for as long as you keep them saved in the recent backtest area", until the user removes each one, or all of them with "Clear All" ([Recent Backtests][eqlab-recent], linked from the FAQ, checked 2026-10-14). The page isn't dated.
- **Access and license:** A proprietary subscription, with a "Free one month trial".
- **Compared with Trial Folio:** It backtests fundamental screens on bundled data, and keeps each named backtest's results until the user removes them. No batch of variants found.
- **Not verified:** whether a saved backtest keeps the settings it ran with, or the software or data version; whether a failed backtest is kept.

### GuruFocus screener backtest

Checked 2026-10-13.

- **What it is:** A backtesting tab in GuruFocus's All-in-One Screener ([feature highlight, 2025-06-19][guru]).
- **Engine and data:** GuruFocus's, back to January 2006 for the US. "The backtesting results should be free of survival bias", and "some filters may not be supported by backtesting" ([feature highlight][guru]). Rebalancing is quarterly, semi-annual, or annual ([2021 announcement][guru-2021]).
- **Many variants, records, and study discipline:** None found beyond a results chart and historical holdings.
- **Access and license:** A membership; the length of backtest history depends on the membership tier, and each region is a separate subscription ([feature highlight][guru], [2021 announcement][guru-2021]).
- **Compared with Trial Folio:** It backtests fundamental screens on a vendor's data, with a statement on survivorship bias. No batch or record features found.
- **Not verified:** whether its fundamentals are point-in-time; its data vendor.

### Portfolio Visualizer

Checked 2026-10-13.

- **What it is:** A web tool for portfolio and asset-class backtests, Monte Carlo simulation, optimization, and factor regression ([portfoliovisualizer.com][pv]).
- **Engine and data:** Its own. Market data "provided by Morningstar Inc and Commodity Systems Inc", and factor data from published libraries ([FAQ][pv-faq]). No backtest of stock screens selected by fundamentals found.
- **What it records:** Users can "save both portfolio backtest and tactical asset allocation model results as benchmarks" ([FAQ][pv-faq]).
- **Access and license:** Proprietary, with free and paid plans ([pricing][pv-pricing]). It imports custom return series.
- **Compared with Trial Folio:** Little overlap: it backtests allocations to funds and asset classes, not fundamental stock selection.

### Institutional systems, and products checked and dropped

Checked 2026-10-13.

- **FactSet Alpha Testing:** "Easily backtest and visualize factor performance, statistics and correlations over deep histories and custom scenarios", offered through a free-trial contact ([product page][factset]). Whether its fundamentals are point-in-time, what it records, and its prices: not verified.
- **Bloomberg's screening and backtesting:** not verified. Its pages returned HTTP 403.
- **Dropped, with no fundamental-screen backtesting confirmed:** Stock Rover: "we do not currently have a dedicated backtesting feature" ([FAQ][stockrover]). Finviz Elite's page doesn't mention backtesting ([Elite][finviz]). AAII Stock Investor Pro's page mentions no backtesting feature for users ([product page][aaii]).

[lean]: https://github.com/QuantConnect/Lean
[lean-custom]: https://www.quantconnect.com/docs/v2/lean-cli/datasets/custom-data
[lean-datasets]: https://www.quantconnect.com/docs/v2/lean-cli/datasets
[lean-opt]: https://www.quantconnect.com/docs/v2/lean-cli/optimization/deployment
[lean-bt]: https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment
[lean-license]: https://raw.githubusercontent.com/QuantConnect/Lean/master/LICENSE
[qc-wfo]: https://www.quantconnect.com/docs/v2/writing-algorithms/optimization/walk-forward-optimization
[qc-pricing]: https://www.quantconnect.com/pricing/
[qc-morningstar]: https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/morningstar/us-fundamental-data
[qc-dataset]: https://www.quantconnect.com/data/morning-star-us-fundamentals
[qc-opt]: https://www.quantconnect.com/docs/v2/cloud-platform/optimization
[qc-opt-strategies]: https://www.quantconnect.com/docs/v2/cloud-platform/optimization/strategies
[qc-opt-deploy]: https://www.quantconnect.com/docs/v2/cloud-platform/optimization/deployment
[qc-opt-results]: https://www.quantconnect.com/docs/v2/cloud-platform/optimization/results
[qc-bt-results]: https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/results
[qc-api]: https://www.quantconnect.com/docs/v2/cloud-platform/api-reference/backtest-management/read-backtest/backtest-statistics
[zipline]: https://github.com/stefan-jansen/zipline-reloaded
[zipline-bundles]: https://zipline.ml4trading.io/bundles.html
[zipline-loader]: https://zipline.ml4trading.io/_modules/zipline/pipeline/loaders/frame.html
[backtrader]: https://github.com/mementum/backtrader
[backtrader-feed]: https://www.backtrader.com/docu/extending-a-datafeed/
[backtrader-opt]: https://www.backtrader.com/docu/optimization-improvements/
[backtrader-writer]: https://www.backtrader.com/docu/writer/
[vbt]: https://github.com/polakowo/vectorbt
[vbt-features]: https://vectorbt.dev/getting-started/features/
[vbt-splitters]: https://vectorbt.dev/api/generic/splitters/
[vbt-returns]: https://vectorbt.dev/api/returns/accessors/
[vbt-license]: https://raw.githubusercontent.com/polakowo/vectorbt/master/LICENSE.md
[vbt-pro]: https://vectorbt.pro/
[vbt-pro-opt]: https://vectorbt.pro/features/optimization
[btpy]: https://kernc.github.io/backtesting.py/
[btpy-api]: https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html
[btpy-ml]: https://kernc.github.io/backtesting.py/doc/examples/Trading%20with%20Machine%20Learning.html
[bt]: https://pmorissette.github.io/bt/
[bt-init]: https://github.com/pmorissette/bt/blob/master/bt/__init__.py
[bt-backtest]: https://github.com/pmorissette/bt/blob/master/bt/backtest.py
[qr]: https://www.quantrocket.com/
[qr-docs]: https://www.quantrocket.com/docs/
[qr-pricing]: https://www.quantrocket.com/pricing/
[qlib]: https://github.com/microsoft/qlib
[qlib-pit]: https://qlib.readthedocs.io/en/latest/advanced/PIT.html
[qlib-pit-collector]: https://github.com/microsoft/qlib/blob/main/scripts/data_collector/pit/README.md
[qlib-tasks]: https://qlib.readthedocs.io/en/latest/advanced/task_management.html
[qlib-workflow]: https://qlib.readthedocs.io/en/latest/component/workflow.html
[qlib-recorder]: https://qlib.readthedocs.io/en/latest/component/recorder.html
[wl]: https://www.wealth-lab.com/
[wl-features]: https://www.wealth-lab.com/features
[wl-wfo]: https://wealth-lab.com/Support/ApiReference/WFOOptimizer
[wl-plans]: https://wealth-lab.com/Software/SubscriptionPlans
[zacks]: https://zackspro.com/products.asp?id=6
[zacks-perf]: https://www.zacks.com/p/p/7203
[zacks-rw]: https://woas.zacks.com/rw/
[zacks-guide]: https://woas.zacks.com/zcom/zcsguide/custom_screener.html
[zacks-offer]: https://www.zacks.com/registration/rw/welcome/eoffer/4a27
[zacks-pro]: https://advisortools-st2.zacks.com/Screening/ZacksProBacktester
[eqlab]: https://www.equitieslab.com/
[eqlab-faq]: https://www.equitieslab.com/faq/
[eqlab-recent]: https://www.equitieslab.com/run-backtests-in-the-background-with-recent-backtests/
[guru]: https://www.gurufocus.com/news/1811493/gurufocus-feature-highlight-backtesting-in-the-screener
[guru-2021]: https://www.gurufocus.com/news/1527290/allinone-screener-backtesting-now-available-for-over-80-countries
[pv]: https://www.portfoliovisualizer.com/
[pv-faq]: https://www.portfoliovisualizer.com/faq
[pv-pricing]: https://www.portfoliovisualizer.com/pricing
[factset]: https://www.factset.com/marketplace/catalog/product/alpha-testing
[stockrover]: https://ww1.stockrover.com/?p=845
[finviz]: https://finviz.com/elite.ashx
[aaii]: https://www.aaii.com/stock-investor-pro

## Datasets that replicate published factors

These publish factor returns and signals that their authors' code computes, on CRSP- and Compustat-family data. None runs on Portfolio123's engine. For Trial Folio's driving use, they're targets to compare a reproduction with.

### Open Source Asset Pricing

Checked 2026-10-13.

- **What it is:** "test asset returns and signals replicated from the academic asset pricing literature" ([openassetpricing.com][osap]). The current release is "October 2025", "version 2.0.0", with "Monthly long-short returns of 212 predictors following OPs", the original papers, and "209 predictive firm-level characteristics" ([data page][osap-data]).
- **Engine and data:** Its authors' code, on Compustat, IBES, OptionMetrics, and 13F data ([FAQ][osap-faq]), downloaded from WRDS ([code][osap-code]). Annual accounting data is lagged "6 months past the datadate" ([FAQ][osap-faq]). Most data "run through December 2024" ([data page][osap-data]). The firm-level file is keyed by CRSP's `permno` and the month ([1_pack_signals.r][osap-pack]).
- **Many variants:** The original papers' methods, deciles, quintiles, equal and value weights, and price filters ([openassetpricing on PyPI][osap-pypi]). The code also builds placebo signals ([code][osap-code]).
- **What it records:** Versioned releases, which the package can load by vintage, and public code with its history ([PyPI][osap-pypi]).
- **Access and license:** Downloads, or `pip install openassetpricing` ([data page][osap-data]). "To download all signals, you need a WRDS account" ([PyPI][osap-pypi]). The code is GPL-2.0. No data license is stated ([FAQ][osap-faq]).
- **Not verified:** its data terms of use.

### Global Factor Data (jkpfactors.com)

Checked 2026-10-13.

- **What it is:** "153 characteristics/factors clustered into 13 themes", in 93 countries, updated "through December 2025" ([jkpfactors.com][jkp]). Its code, [jkp-data][jkp-code], replaces an earlier repository marked "NO LONGER MAINTAINED" ([ReplicationCrisis][jkp-old]).
- **Engine and data:** Its authors' code, which "requires a valid WRDS subscription". "The authors do not distribute WRDS, CRSP, Compustat, or IBES data" ([jkp-data][jkp-code]).
- **Study discipline:** It accompanies the paper "Is There a Replication Crisis in Finance?" ([jkp-data][jkp-code]).
- **Access and license:** Factor portfolios download from the site. "Data is licensed under CC BY-NC 4.0"; the code is MIT ([jkpfactors.com][jkp]). Stock-level data needs WRDS access ([jkp-data][jkp-code]).
- **Not verified:** how characteristics are dated; whether CC BY-NC 4.0 allows uploading the factor returns into a Portfolio123 account.

### q-factor data library (global-q.org)

Checked 2026-10-13.

- **What it is:** The q5 factors and benchmark portfolios, at daily to annual frequencies, on a "1967-2025 sample", latest release 2026-07-30 ([factors][q-factors]). Testing portfolios for 201 anomalies, mostly deciles ([testing portfolios][q-testing]).
- **Engine and data:** Its authors' computation, on CRSP returns and Compustat annual and quarterly accounting data, for "all domestic common stocks listed on NYSE, Amex, and Nasdaq". Quarterly earnings are used after their announcement dates, and returns "are adjusted for delisting" ([technical document, July 2026][q-doc]).
- **Access and license:** Direct CSV links, with no login seen. No terms of use stated on the pages read.

### The Tuck School's factor data library

Checked 2026-10-13.

- **What it is:** US three- and five-factor data, momentum, and sort portfolios, with international factors, at daily, weekly, and monthly frequencies. The returns table is labeled "August 2026" ([data library][french]).
- **Engine and data:** Its authors' computation. US returns come from CRSP ([three-factor page][french-3f]). "Book equity is constructed from Compustat data or collected from the Moody's Industrial, Financial, and Utilities manuals" ([variable definitions][french-vars]).
- **Access and license:** Zip downloads, with no registration seen.
- **Not verified:** its terms for redistribution or upload.

### Bringing them into Portfolio123

Checked 2026-10-13.

- Portfolio123 accepts outside data in two forms. A data series, "a list of dates and values", can be used in rules with `GetSeries` ([a Portfolio123 staff account, 2019][f-58409]). An imported stock factor, of dates, stock identifiers, and values, can be used "in any formula for screening, ranking and backtesting" ([Imported Stock Factors][hc-61922]). `p123api` has upload operations for both ([client.py][gh-api-client]).
- An imported stock factor identifies stocks by "a Portfolio123 StockID, current ticker, GVKey, current FIGI, or CIK" ([Imported Stock Factors][hc-61922]). That list doesn't include `permno`, so a firm-level file keyed by it would need a mapping.
- So factor return series could be uploaded as data series. Or the published constructions can be rebuilt as Portfolio123 rankings and screens, which is what P123-Claude-Skill's recipes and Trial Folio's [METH-09](methodology.md#meth-09-reproducing-published-research) aim at.
- **Not verified:** whether an imported data series can be a screen backtest's benchmark; whether each dataset's terms allow uploading it to Portfolio123.

[osap]: https://www.openassetpricing.com/
[osap-data]: https://www.openassetpricing.com/data/
[osap-faq]: https://www.openassetpricing.com/faq/
[osap-code]: https://github.com/OpenSourceAP/CrossSection
[osap-pack]: https://github.com/OpenSourceAP/CrossSection/blob/master/Shipping/Code/1_pack_signals.r
[osap-pypi]: https://pypi.org/project/openassetpricing/
[jkp]: https://jkpfactors.com/
[jkp-code]: https://github.com/bkelly-lab/jkp-data
[jkp-old]: https://github.com/bkelly-lab/ReplicationCrisis
[q-factors]: https://global-q.org/factors.html
[q-testing]: https://global-q.org/testingportfolios.html
[q-doc]: https://global-q.org/uploads/1/2/2/6/122679606/factorstd_2026jul.pdf
[french]: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
[french-3f]: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_factors.html
[french-vars]: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/variable_definitions.html
[f-58409]: https://community.portfolio123.com/t/factor-and-data-series-importing/58409
[hc-61922]: https://portfolio123.customerly.help/en/articles/61922-imported-stock-factors

## Tools for tracking experiments and preregistering studies

None of these runs a backtest or uses Portfolio123's engine. Code searches that combined `p123api` or `portfolio123` with MLflow, W&B, DVC, or preregistration returned nothing ([the searches](#searches-for-tools-built-on-portfolio123)).

### MLflow Tracking

Checked 2026-10-13.

- **What it is:** An open-source tracker in which "An experiment groups together runs and models for a specific task" ([MLflow Tracking][mlflow]).
- **Engine and data:** None of its own: it records what the user's code runs.
- **Many variants:** It logs runs that other libraries launch. Its tuning tutorial logs each Optuna trial as a child run, under a parent run ([tutorial][mlflow-tuning]).
- **What it records:** "metrics, parameters, start and end times", artifacts, and tags ([MLflow Tracking][mlflow]). A tag for the Git commit, set "When run from git repo" ([tracking API][mlflow-api]). Run statuses include FAILED and KILLED ([run_status.py][mlflow-status]), and a run that raises an exception ends FAILED ([fluent.py][mlflow-fluent]). A provider's requests, responses, and costs aren't built-in fields; the user's code could log them.
- **Study discipline:** None found.
- **Access and license:** Apache-2.0. Release v3.17.1, of 2026-10-13.
- **Compared with Trial Folio:** It records parameters, metrics, versions, times, and a failed status for runs of any code: part of what Trial Folio records.

### Weights & Biases

Checked 2026-10-13.

- **What it is:** A hosted experiment tracker, whose documentation now redirects to docs.coreweave.com ([runs][wandb-runs]).
- **Many variants:** Sweeps "automate hyperparameter search" with "Bayesian, grid search, and random" methods ([sweeps][wandb-sweeps]).
- **What it records:** A run's config, "the input values and settings for an experiment", its metrics, summaries, and artifacts ([runs][wandb-runs]). With code saving on, the "latest git commit", a "diff.patch" of uncommitted changes, and the requirements file ([logging][wandb-log]). Run states include Crashed and Failed ([run states][wandb-states]). No provider-cost field.
- **Study discipline:** None found.
- **Access and license:** The client library is MIT. The service has free, paid, enterprise, and academic tiers ([pricing][wandb-pricing]).
- **Compared with Trial Folio:** It records settings, code version, output, and failure state for runs of any code.

### DVC experiments

Checked 2026-10-13.

- **What it is:** Git-based tracking of experiments, data, and models. Experiments are stored as "custom Git references" ([experiment management][dvc]).
- **Many variants:** `--queue` adds an experiment "for future execution", and sweeps can "add multiple experiments to the queue" ([exp run][dvc-run]).
- **What it records:** "parameters, metrics, and plots data saved in standard structured files", tracked data and models, and the Git baseline commit ([experiment management][dvc]). The queue shows each experiment's status ([queue status][dvc-queue]).
- **Study discipline:** None found.
- **Access and license:** Apache-2.0.
- **Compared with Trial Folio:** It queues parameter variants, and versions their inputs and outputs in Git.
- **Not verified:** how a failed queued experiment is recorded.

### OSF Registries

Checked 2026-10-13.

- **What it is:** Preregistration on the Open Science Framework. A registration "is a frozen version of your project that can never be edited or deleted", though it can be withdrawn. Changes with a justification are made as updates. Templates include OSF Preregistration and a template for secondary data ([OSF help][osf-help]). Registrations are archived as a "timestamped, immutable registration" ([OSF Registries][osf-reg]).
- **Engine and data:** None. It runs nothing.
- **What it records:** The plan, files, and metadata at registration, and the justified updates.
- **Access and license:** The Center for Open Science describes OSF as "A free, open-source platform" ([OSF][osf]). Organizations that host their own registry pay an annual fee ([OSF Registries][osf-reg]).
- **Use with Portfolio123:** A member announced "Two Pre-Registered Designer Models on OSF" on 2026-07-29 ([topic 76678][t76678]). The linked OSF project states an intent to run two models for a set period, and test their excess returns against the Russell 2000. OSF's public API reports it as a project, not a registration, with no registrations ([node][osf-node], [registrations][osf-node-reg]).
- **Compared with Trial Folio:** It provides the time-stamped, unmodifiable protocol that [METH-09](methodology.md#meth-09-reproducing-published-research) asks for. It doesn't run anything, or connect to Portfolio123.

### AsPredicted

Checked 2026-10-13.

- **What it is:** "A platform that makes pre-registrations easy to make and evaluate". A pre-registration "remains private until an author makes it public", coauthors approve it, "Public pre-registrations cannot be modified", and each can be downloaded as a time-stamped PDF ([aspredicted.org][aspredicted]).
- **Engine and data:** None.
- **Access and license:** A secondary source lists it as "Completely free of charge" ([ZBW Open Economics, undated][aspredicted-zbw]). Not verified on AsPredicted's own pages.
- **Compared with Trial Folio:** As for OSF: a time-stamped protocol, with no execution and no Portfolio123 link.

[mlflow]: https://mlflow.org/docs/latest/ml/tracking/
[mlflow-tuning]: https://mlflow.org/docs/latest/ml/getting-started/hyperparameter-tuning/
[mlflow-api]: https://mlflow.org/docs/latest/ml/tracking/tracking-api/
[mlflow-status]: https://github.com/mlflow/mlflow/blob/master/mlflow/entities/run_status.py
[mlflow-fluent]: https://github.com/mlflow/mlflow/blob/master/mlflow/tracking/fluent.py
[wandb-runs]: https://docs.coreweave.com/guides/runs/
[wandb-sweeps]: https://docs.coreweave.com/models/sweeps
[wandb-log]: https://docs.coreweave.com/models/track/log
[wandb-states]: https://docs.coreweave.com/guides/runs/run-states/
[wandb-pricing]: https://coreweave.com/forge-pricing
[dvc]: https://doc.dvc.org/user-guide/experiment-management
[dvc-run]: https://doc.dvc.org/command-reference/exp/run
[dvc-queue]: https://doc.dvc.org/command-reference/queue/status
[osf-help]: https://help.osf.io/article/330-welcome-to-registrations
[osf-reg]: https://www.cos.io/products/osf-registries
[osf]: https://www.cos.io/products/osf
[osf-node]: https://api.osf.io/v2/nodes/u78c5/
[osf-node-reg]: https://api.osf.io/v2/nodes/u78c5/registrations/
[t76678]: https://community.portfolio123.com/t/two-pre-registered-designer-models-on-osf/76678
[aspredicted]: https://aspredicted.org/
[aspredicted-zbw]: https://openeconomics.zbw.eu/en/knowledgebase/aspredicted/

## Changes to facts the project recorded earlier

These compare the sources above, as checked on 2026-10-13, with what [ADR 0001's verification notes](adrs/0001-python-and-portfolio123-integration.md#verification-notes), [ADR 0005](adrs/0005-build-on-the-portfolio123-api-only.md#context), the [spec-authoring guide's section 8](spec-authoring-guide.md#8-portfolio123-reuse-and-integration-findings), and [DSC-10](disclaimers.md#dsc-10-portfolio123-terms-that-bear-on-users) recorded, mostly on 2026-10-01. This survey changes none of those documents, except DSC-10, which now quotes §17's first sentence, as the owner decided on 2026-10-13. The owner decides whether each of the others changes. Each entry gives a recommended default, an open question until the owner decides it.

**FactorMiner.** The project recorded it as a factor-analysis tool whose repository declares no license, at `d814c5df`, and whose source uses an ordinary one-sample t-test for IC. All of that still holds. Not in the earlier records:

- Portfolio123 also hosts it, as "a Streamlit app running in our servers", live since 2026-05-03. Portfolio123 calls it "an open source project", while the repository still declares no license ([FactorMiner](#factorminer)).
- It records each analysis, with its parameters, dataset version, times, status, notes, and errors.
- Its documented correlation default, 0.50, differs from the source's, 0.7.

**Recommended default:** no change to ADR 0001 or the spec-authoring guide. What they recorded still holds, and the facts they don't have are this survey's.

**DataMiner's exports.** ADR 0005's context says the CSV output records "no settings, DataMiner version, credit cost, or timestamp", going by the pinned source. ADR 0001's verification notes say the same of the pinned source: it "suggests a multi-section CSV with `Stats`, `Results`, and `Time Series` sections and no configuration, version, cost, or timestamp". An auto-saved export carries a timestamp in its file name, `<operation>_<YYYYMMDD_HHMMSS>.csv`, though not in its contents ([data_miner.py][gh-dm-save], lines 604 to 610, at `721f3dea`). So both statements hold for the file's contents only. Exports also carry each iteration's name ([DataMiner](#dataminer)). DataMiner's license, GPL-3.0, its last push, 2025-02-19 at `721f3dea`, and its two commits are unchanged.

**Recommended default:** add a dated note to ADR 0001's DataMiner note and to ADR 0005's context, saying that an auto-saved export's file name carries a timestamp, and linking to this entry. What they recorded on 2026-10-01 stays as it is. A page that cites them for what an export records then gets the whole fact. The alternative is no change, since both statements hold for the file's contents.

**The API's cost and quota in responses.** ADR 0001 says of the screen backtest: "The response fields are not documented." The public OpenAPI file now documents them. The screen backtest's result schema has `stats`, `results`, and `chart`, with `cost` and `quotaRemaining` from a shared schema, which 35 of the file's 39 documented success responses include. The file also documents `402` "Request quota exhausted", `406` "Another request is already running", and `409` "Operation failed" ([OpenAPI file][p123-openapi]). Whether the file was public when ADR 0001 was written isn't known. Whether failed requests are charged is still undocumented. A screen backtest still costs 5 credits, and `p123api` 3.1.0, of 2026-08-25, is still the latest stable release; pre-releases 3.1.1a1 and 3.1.1a2 have followed.

**Recommended default:** add a dated note under ADR 0001's "The response fields are not documented", saying that the public OpenAPI file documents them, and linking to this entry. What it recorded on 2026-10-01 stays as it is. The alternative is no change, since ADR 0001's notes record what was documented when they were written, and the 0.1.0 reference response already confirms the fields.

**Portfolio123's terms, §17.** The terms are still dated "Last Updated: February 24, 2023". DSC-10 quoted §17's second sentence, under "Competition", without its section number. §17 is titled "Non-Compete, Right to Terminate", and its first sentence reads: "The Company reserves the right to terminate your access to the site if Company believes that you are providing services that are detrimental to Company's business including, but not limited to, services that offer similar functionality." ([terms][p123-terms]). Its third sentence says that if the Company believes, in good faith, that a subscriber is competing with the Service, it may terminate the agreement and "pursue any and all remedies for the breach". As the owner decided on 2026-10-13, DSC-10 now quotes the first sentence too, under §17's number and title, checked again on 2026-10-14. These are factual extracts, not legal advice.

## What the facts support

The owner gave three claims, in order of preference, for the page on why Trial Folio exists ([UM-T05](user-manual.md#tasks)). For each: whether the facts support it, the facts that decide it, and the narrowest form they would support. Every "not found" below is bounded by [the survey's limits](#how-the-survey-was-done).

### Claim 1: Trial Folio is unique

**Not supported as stated.** Each of Trial Folio's main capabilities exists in at least one other tool:

- **Many variants of a Portfolio123 test:** the Optimizer, DataMiner's iterations, the API's `rank_perf`, the single-factor testing tool, and members' loops over `screen_backtest`.
- **Durable records of each run:** FactorMiner's record of each analysis, with its parameters, dataset version, times, status, and errors; the single-factor tool's 2025 settings sheet; QuantConnect's backtest records, with parameters, code, engine version, and errors; and MLflow, W&B, and DVC for any code.
- **A cost estimate, and a confirmation, before running:** Download Factors' estimate, on Portfolio123; and QuantConnect's estimate for an optimization, which the LEAN CLI asks the user to confirm before it starts, and which stops when credit runs out.
- **Resuming an interrupted run:** the single-factor tool's 2025 version, WealthLab's walk-forward runs, and Qlib's task management.
- **Mapping published factors to Portfolio123:** P123-Claude-Skill's recipes, which also say where Portfolio123 can't match the paper.
- **Study discipline Trial Folio's releases don't yet provide:** AI Factor's holdouts and cross-validation, Rank Performance's half-period split, vectorbt's deflated Sharpe ratio, the backtest-review skill's overfitting checks, and preregistration on OSF and AsPredicted. A member announced two Portfolio123 models as preregistered on OSF, in an OSF project rather than a frozen registration ([OSF Registries](#osf-registries)).

**What decides it is the combination.** In the sources searched, no other tool was found that runs Portfolio123's own backtests as a declared, finite experiment, under a plan and a budget approved before anything is sent, and keeps each request, response, and failure, with the cost Portfolio123 reported. Within Portfolio123's tools, `p123api` keeps only the last call's cost, DataMiner's public source writes no settings or costs, and no plan or estimate was found for the Optimizer. QuantConnect comes closest, on its own engine and data: the LEAN CLI shows a cloud optimization's estimated cost and the organization's balance, and asks whether to start it. That confirms an estimate, with the credit balance as the only limit described. Trial Folio's approval is of a plan, by its hash, and in an experiment it covers a budget of provider requests.

**Narrowest form supported:** a dated "none found", bounded by the searches. As of 2026-10-13, the searches this survey lists found no other tool that runs Portfolio123's backtests through its API as a declared, finite experiment, under a plan and a budget approved before anything is sent, and keeps each request, response, and failure, with the cost Portfolio123 reported. Not "unique": a tool shared privately can't be ruled out, logged-in features weren't checked, and each part exists elsewhere.

### Claim 2: Trial Folio was needed for a complete integration with Portfolio123

**Not supported.**

- Portfolio123 provides its own ways in: the API, with a public OpenAPI file, the MIT-licensed `p123api`, and DataMiner, a no-code client for nine operations.
- Trial Folio uses the same wrapper, and covers fewer operations than DataMiner. Release 0.1.0 runs one kind of screen backtest, and 0.3.0's variants change one of four settings.
- The API has no endpoints for AI Factor training or validation, or for the Optimizer, so no tool built on the API alone integrates completely.
- Other integrations exist: WealthLab's extension brings Portfolio123's rankings into WealthLab, and Dashboard123 and P123-Claude-Skill call the API.

**What bears on it:** No tool was found that connects Portfolio123's API to an experiment record or a preregistration. The API's shared `ApiRankingSystem` and its `406` response mean variants are sent one at a time. Its responses carry `cost` and `quotaRemaining`, which the wrapper returns and keeps only until the next call, and whether failed requests are charged is undocumented. These are reasons for careful handling, not gaps in what Portfolio123 offers.

**Narrowest form supported:** a statement of what Trial Folio adds, not that it was needed. For the operations it supports, it adds a durable record of each request, response, failure, and reported cost, and a budget approved before sending, on top of Portfolio123's official wrapper. No ready-made tool was found that does this. Without one, a member would write code around `p123api`.

### Claim 3: Its economics serve Portfolio123's members better than the alternatives do

**Not supported in a comparative form.** The facts that bear on it:

- Trial Folio runs on the engine and data a member already has through Portfolio123. Among the general products, those with point-in-time fundamentals use their own data, such as QuantConnect's Morningstar data, free in its cloud, or Equities Lab's built-in data, or a separate subscription, such as QuantRocket's Sharadar data. WealthLab's route to Portfolio123's rankings adds a WealthLab subscription, a paid extension, and a price-data provider. The open-source libraries are free, but bring no US point-in-time fundamentals.
- Research through the API spends credits on each call, 5 for a screen backtest. Unused monthly credits don't roll over, and costs can change without notice. Trial Folio gives a plan's credits before sending, and keeps the cost Portfolio123 reports. Portfolio123's own Download Factors estimate can be too low when a universe's size varied, and QuantConnect also estimates a batch's cost first.
- Saved items on Portfolio123, such as screens, simulations, and optimizer studies, use the account's Resource Units. Records kept on the user's machine don't.

**What decides it is what's missing.** Whether website screens, simulations, Rank Performance tests, and Optimizer runs use API credits isn't verified, so Trial Folio's cost can't be compared with Portfolio123's own tools. QuantConnect's free plan offers unlimited backtesting, and lists cloud access to its Morningstar fundamentals as free. And this survey holds no facts about what Trial Folio costs its user beyond credits.

**Narrowest form supported:** a statement of cost structure, not of better economics. Trial Folio uses the data and engine a member already has through Portfolio123, so it needs no second data subscription. It shows the credits a plan may spend before sending anything, and keeps the cost Portfolio123 reports for each request.

### Terms that bear on every claim

Portfolio123's terms let it terminate access for services "that offer similar functionality", and bar using the Service "to compete with the Service" (§17). They restrict storing, redistributing, or manipulating Content without consent (§5) ([terms][p123-terms]). These are factual extracts, not legal advice. [Rule 10](user-manual.md#rules) already has each page present Trial Folio as built on Portfolio123's own engines and data, not as a substitute for Portfolio123.

### The claim the page makes

The owner decided on 2026-10-14 that the page makes claim 1, in its narrowest supported form. It's the owner's first preference, and the facts support it in that form. Claim 2 isn't supported in any form that says Trial Folio was needed, and its narrow form, what Trial Folio adds, is part of this claim. Claim 3's narrow form is a cost structure, which the page gives anyway as what using Trial Folio costs. The page could state it as:

> As of 2026-10-13, the [survey of related tools](https://github.com/promptedportfolio/trialfolio/blob/main/docs/related-tools.md) found no other tool that runs Portfolio123's backtests through its API as a planned experiment: a fixed set of cases, under a plan and a budget you approve before anything is sent, with each request, response, and failure kept, along with the cost Portfolio123 reported. Each part exists elsewhere. Portfolio123's Optimizer and DataMiner run many variants, FactorMiner keeps a record of each analysis, and Download Factors estimates the credits it will use. QuantConnect records each backtest, and estimates a batch's cost and asks you to confirm it, on its own engine and data. The survey searched public sources only, without logging in, so a tool shared privately, or a feature behind a login, may do the same.

## Appendix: the searches

All run on 2026-10-13. They're the evidence behind each "none found".

### Searches for tools built on Portfolio123

GitHub's search covers only public repositories, and its code search only indexed files. The forum's search returns at most 50 topics a query; where it reported more, shown as "50+", only the first 50 titles were read.

**GitHub repository search:**

| Query | Returned | Related to Portfolio123 |
|---|---|---|
| `portfolio123` | 100, the limit | Dashboard123, p123api-py, P123-Claude-Skill, P123_PySR, trialfolio. Most others are personal portfolio sites named "portfolio123". |
| `p123api` | 2 | p123api-py, P123-Claude-Skill |
| `p123` | 50 | P123-Claude-Skill, p123api-py, P123_PySR, P123-AUTO, LLM123. The `p123client` repositories are clients for an unrelated "123" cloud drive. |
| `portfolio123 ranking` | 1 | puts-backtest |
| `portfolio123 python` | 1 | p123api-py |
| `portfolio123 api`, `portfolio123 backtest`, `portfolio123 screen`, `portfolio123 optimizer`, `portfolio123 rank`, `portfolio123 machine learning`, `portfolio123 factor`, `portfolio 123 stock` | 0 each | None |
| `topic:portfolio123`, `topic:p123` | 0 each | None |

**GitHub code search** (hits, then distinct repositories):

| Query | Returned | Related to Portfolio123 |
|---|---|---|
| `import p123api` | 23 / 10 | p123api-py, P123-Claude-Skill, Dashboard123, factor-miner, S-P500-dashboard, RankToGod, market-dashboard, and a mirror of documentation for LLMs. Two plugins for a cloud drive are unrelated. |
| `p123api.Client` | 22 / 8 | The same set |
| `from p123api` | 10 / 3 | p123api-py, P123-Claude-Skill, dataminer |
| `p123api` | 58 / 24 | The same set, and TradingStrategy; the rest unrelated |
| `P123_API_KEY`, `P123_API_ID` | 21 / 5 each | Dashboard123, P123-Claude-Skill, S-P500-dashboard, and market-dashboard for both; RankToGod for the key, and Swing-Long-System for the ID |
| `screen_rolling_backtest` | 9 / 3 | p123api-py, P123-Claude-Skill, dataminer |
| `screen_backtest(` | 23 / 15 | Only P123-Claude-Skill, p123api-py, and dataminer |
| `rank_perf(` | 22 / 17 | Only P123-Claude-Skill and p123api-py |
| `rank_ranks(` | 34 / 24 | Dashboard123, S-P500-dashboard, RankToGod, P123-Claude-Skill, p123api-py, dataminer |
| `strategy_rebalance` | 100 / 60 | p123api-py, P123-Claude-Skill, Dashboard123, S-P500-dashboard |
| `client.screen_run` | 8 / 7 | The same Portfolio123 set |
| `api.portfolio123.com` | 4 / 2 | P123-Claude-Skill, p123api-py |
| `portfolio123`; `portfolio123.com` | 100 / 38; 100 / 70 | Mostly lists, corpora, and name collisions; the related ones are above |
| `P123 ranking system`, `P123 factor`, `Portfolio123 ranking system`, `Portfolio123 screen`, `Portfolio123 backtest` | 5, 9, 3, 2, and 2 hits | Dashboard123, P123_PySR, S-P500-dashboard, P123-Claude-Skill, factor-miner; the others are research notes |
| `screen_backtest p123`, `rank_perf p123`, `rank_update p123`, `data_universe p123`, `data_prices p123`, `Portfolio123 DataMiner`, `p123 screen backtest`, `portfolio123 simulation` | 0 each | None |
| `p123api mlflow`, `p123api wandb`, `p123api dvc`, `portfolio123 mlflow`, `portfolio123 wandb`, `portfolio123 preregistration` | 0 each | None |

**GitHub dependents** of p123api-py ([network/dependents](https://github.com/portfolio-123/p123api-py/network/dependents)): "8 repositories and 0 packages", approximate. The first page shows [all](https://github.com/alphavector/all), [pipy_server](https://github.com/Lyn4ever29/pipy_server), TradingStrategy, and dataminer.

**PyPI:** Its search page needs JavaScript, so the public simple index, of 912,762 project names, was matched against `p123|portfolio123|portfolio-123|portfolio_123|pf123`. The matches are `p123api`, Portfolio123's own; `p123`, `p123client`, and `p123dav`, clients for an unrelated "123" web disk; and `pp123`, unrelated. Libraries.io's dependents view is "currently disabled".

**Portfolio123's forum search:**

| Query | Topics | Relevant topics |
|---|---|---|
| `github` | 50+ | 76382, 76413, 76399, 76571, 76818, 76583, 76450, 76504 |
| `p123api` | 43 | 67749, 59260, 76399, 76382, 76342 |
| `open source` | 50+ | 76399, 76207, 76413, 75604, 76504 |
| `python script` | 38 | 68757, 59260, 75604, 76207, 70837, 37410 |
| `dataminer script` | 30 | 59260, 59280, 62174; no new tool |
| `optimizer` | 50+ | 45889, 63454, 63850, 76413, 76571 |
| `streamlit` | 13 | 76558, 76382, 76450, 76413, 72007, 76359, 76207, 76504 |
| `save backtest results` | 50+ | 67749, 59280 |
| `replicate paper` | 44 | None that is a tool |
| `colab` | 47 | 67749, 59260 |
| `jupyter` | 42 | 76207, 73235 |
| `deflated sharpe` | 10 | 76679 |
| `data snooping` | 15 | None that is a tool |
| `multiple testing` | 50+ | 46484, 63573, 63454 |
| `version control` | 50+ | None that is a tool |
| `free app` | 50+ | 76450 |
| `MCP` | 8 | 76818, a planned MCP server, not released |
| `claude skill` | 9 | 76583, 76679, 76818, 76399 |
| `excel add-in` | 50+ | 30808, 39943: an Excel add-in distributed in 2011; its availability now not verified |
| `app store` | 50+ | 76382, 76343 |
| `audit trail` | 5 | None |
| `holdout`, `walk forward` | 50+ each | 76450, 76207, 67754, a discussion |
| `osf` | 5 | 76678 |
| `wandb`; `weights and biases` | 1; 50+ | None that uses a tracker |
| `backtest log`, `track backtests`, `rolling backtest api`, `batch backtest`, `experiment tracking`, `preregistration` | 0 each | None |

**General web search:**

| Query | Result |
|---|---|
| `"Portfolio123" API integration third-party tool extension backtest` | The WealthLab extension; nothing else new |
| `"p123api" python ranking system optimization github OR blog` | Nothing related to Portfolio123 |
| `Portfolio123 ranking system automated weight optimization script API tool substack` | Nothing new |

**Not searched:** Reddit, YouTube, X, Discord, and other forums, and tools shared only by private message.

### Searches for Portfolio123's own features

- **History of a screen's or a simulation's runs and versions:** the help center's Research, Overview, Library, and Manage collections, and forum searches for "version history", "revision history simulation", "restore previous version", "undo changes ranking system", and "save screen backtest results history". The only direct statement found was the 2015 staff post ([screens](#screens-and-screen-backtests)).
- **Preregistration, a plan approved before running, and testing adjustments:** the help collections above, and forum searches for "preregistration", "multiple testing bonferroni", and "deflated sharpe". They found staff posts of 2024 that discuss the Deflated Sharpe Ratio as not yet considered, and no feature.

### Searches for general products' Portfolio123 integrations

- A GitHub code search for "portfolio123" in QuantConnect's organization, and another in QuantRocket's, returned nothing. QuantRocket's documentation page doesn't mention Portfolio123.
- The general web search above found the WealthLab extension, the only integration found.
