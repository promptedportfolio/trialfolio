# Trial Folio

This is Trial Folio's user manual. This page says what Trial Folio is, which version the manual describes, and where to start.

## What Trial Folio is

Trial Folio is a command-line tool for investors who research strategies in [Portfolio123](https://www.portfolio123.com/). It helps you:

- Run backtests through the Portfolio123 API, with every setting recorded next to its result.
- Run a small, planned experiment: a baseline screen and a few variants of it, under one approval and one budget, which you can resume safely.
- Vary a ranking system's weights, or remove one of its factors, as an experiment's variants, with each case's whole ranking definition recorded.
- Compare runs and see exactly which settings differ between them.
- Keep a durable, inspectable record of what you tested, including the tests that failed.

Portfolio123 does the backtesting. Trial Folio plans each request, records exactly what was sent and returned, and compares the results, so you can see whether they support a conclusion.

> **Requires a Portfolio123 subscription.** This project works with the Portfolio123 API, which requires a Portfolio123 subscription with the appropriate access.

The demo runs without one. `trialfolio demo` writes a complete example run from invented values, and sends nothing to Portfolio123, so you can try Trial Folio before you use your subscription.

## Which version this manual describes

This manual describes Trial Folio as it is on the `main` branch of [its repository](https://github.com/promptedportfolio/trialfolio), until the first release is distributed. Until then, you run Trial Folio from a copy of the repository, as the [first tutorial](tutorials/first-backtest.md) shows.

The latest tagged version is `v0.4.0`. A tagged version can lack behavior this manual describes: an earlier tag has none of release 0.4.0's ranking definitions and snapshots. If you run a tagged copy, follow the documentation at its tag instead: for `v0.3.0` and earlier tags, the user guide, such as [the user guide at `v0.3.0`](https://github.com/promptedportfolio/trialfolio/blob/v0.3.0/docs/user-guide.md); for a later tag, this manual's pages as that tag holds them, in its `manual/` folder.

The manual describes Trial Folio's behavior; it doesn't define it. The [specifications](https://github.com/promptedportfolio/trialfolio/blob/main/docs/README.md) define it. Where the manual and a specification disagree, the specification wins, and the manual is the one to fix.

## Where to start

If you're new to Trial Folio, start with the first tutorial, [Your first backtest](tutorials/first-backtest.md). Its first part runs the demo, and needs no subscription.

The manual has four sections.

### Tutorials

Lessons that walk you through a first run that works, step by step, with what you should see after each step.

- [Your first backtest](tutorials/first-backtest.md): set up Trial Folio, try the demo, write a screen configuration, review its plan, run it, and read the results.
- [Your first experiment](tutorials/first-experiment.md): run a baseline screen and a few variants of it, under one plan and one approval.

### How-to guides

The steps for a task you already have.

- [Store your credentials](how-to/store-credentials.md)
- [Re-render a report](how-to/re-render-a-report.md)
- [Compare runs](how-to/compare-runs.md)
- [Recover from an interrupt](how-to/recover-from-an-interrupt.md)
- [Repeat a case](how-to/repeat-a-case.md)
- [Revise an experiment](how-to/revise-an-experiment.md)
- [Vary a ranking system's weights](how-to/vary-a-ranking-systems-weights.md)
- [Take a ranking snapshot](how-to/take-a-ranking-snapshot.md)
- [Use Trial Folio from a script](how-to/use-from-a-script.md)

### Reference

Exact descriptions of the commands, configurations, outputs, and errors, to look things up.

- [Commands](reference/cli.md)
- [Screen configuration](reference/screen-configuration.md)
- [Review configuration](reference/review-configuration.md)
- [Experiment configuration](reference/experiment-configuration.md)
- [Ranking definitions](reference/ranking-definitions.md)
- [Ranking snapshot configuration](reference/ranking-snapshot-configuration.md)
- [Outputs](reference/outputs.md)
- [Errors](reference/errors.md)
- [JSON summary](reference/json-summary.md)

### Explanation

Why Trial Folio works as it does, with links to the specifications behind it.

- [Plans and approval](explanation/plans-and-approval.md)
- [Credits and uncertain charges](explanation/credits-and-uncertain-charges.md)
- [Reproducibility](explanation/reproducibility.md)
- [What a backtest can support](explanation/what-a-backtest-can-support.md)
- [`ApiRankingSystem` and the ranking lock](explanation/apirankingsystem-and-the-ranking-lock.md)
- [The research method, step by step](explanation/the-research-method.md)
- [Where Trial Folio is going](explanation/where-trial-folio-is-going.md)

## Research notice

> Research output only. Backtested and hypothetical results do not represent achievable returns. No financial gain, future performance, suitability, or protection from loss is represented or promised. This report is not personalized investment advice. See the full license and research limitations.

The full notice is in [docs/disclaimers.md](https://github.com/promptedportfolio/trialfolio/blob/main/docs/disclaimers.md), and the full license in [LICENSE](https://github.com/promptedportfolio/trialfolio/blob/main/LICENSE).

## Your license

[LICENSE](https://github.com/promptedportfolio/trialfolio/blob/main/LICENSE) governs every copy of Trial Folio, including one you run from a copy of its repository. The README's [License section](https://github.com/promptedportfolio/trialfolio/blob/main/README.md#license) summarizes who may use it.

---

> **Not affiliated with Portfolio123.** This is an independent project. It is not an official Portfolio123 project and has not been reviewed by Portfolio123. No endorsement by Portfolio123 is implied.
