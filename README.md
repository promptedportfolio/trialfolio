# Trial Folio

> **Requires a Portfolio123 subscription.** This project works with Portfolio123 research exports and the Portfolio123 API, which require a Portfolio123 subscription with the appropriate access.

Trial Folio is a command-line tool for investors who research strategies in [Portfolio123](https://www.portfolio123.com/). It helps you:

- Compare backtest results.
- See exactly which settings differ between them.
- Keep a durable, inspectable record of what you tested, including the tests that failed.

Portfolio123 does the backtesting. Trial Folio records what you tested and compares the results, so you can see whether they support a conclusion.

## Status

**Pre-release. Nothing is installable yet.** The specifications are drafted. No release has been implemented.

| Capability | Planned release | Status |
|---|---|---|
| Compare DataMiner screen-backtest exports and their configurations, offline, against a baseline | [0.1.0](docs/releases/0.1.0-review.md) | Specified (Draft) |
| Run one screen backtest through the Portfolio123 API and keep the settings with the results | [0.2.0](docs/releases/0.2.0-api-execution.md) | Outlined (Draft) |
| Run a small, planned experiment of screen variants, with safe resume | [0.3.0](docs/releases/0.3.0-experiments.md) | Outlined (Draft) |
| Descriptive return analytics, robustness diagnostics, statistical evaluation, forward tracking | [Roadmap](docs/roadmap.md) | Not specified |

**Supported formats:** none yet. Release 0.1.0 will support exactly one DataMiner ScreenBacktest CSV layout, once a real export has verified it. Every other layout will be rejected with a clear error, never guessed at.

Statistical validation and trading readiness are **not assessed** by any planned release before the statistical evaluation increment.

## Installation

No installation is available yet. When 0.1.0 is implemented, this section will give the verified installation steps. How the software is distributed has not been decided.

## Example

This is the planned command; it does not work yet:

```text
trialfolio review comparison.yaml --out review/
```

It will copy your exports and configurations unchanged into `review/`. It will then write:

- normalized comparison tables (CSV)
- a manifest recording what was imported and how
- a self-contained HTML report that flags differing benchmarks, dates, costs, and other settings

A missing value is shown as unavailable, never as zero.

## Limitations

- **Summary exports can't show everything.** Trial Folio compares what an export contains. It does not reconstruct returns, drawdowns, or confidence intervals from summary statistics.
- **Your files are taken as you supplied them.** Imported files and configurations are recorded as user-supplied. Trial Folio can't confirm how they were produced.
- **Reruns can differ.** A Portfolio123 rerun can give different results as its data and engine change, so Trial Folio treats each run as a new attempt.
- **A backtest is a simulation.** See [research limitations](docs/disclaimers.md).

## Your data stays on your machine

- Releases 0.1.0 and later run the review offline.
- From 0.2.0, Trial Folio contacts Portfolio123 only for requests you approve.
- Logs stay local and never contain credentials, strategy definitions, configuration values, or results. They will be written to `logs/` inside each output directory. Delete that directory to delete them.
- Optional LLM features are planned for a later increment. They will be off by default, and remote model providers will process data under their own terms.

## License

Trial Folio is source available under a custom license, the Nathan Slaughter Personal Research License (`LicenseRef-NSPRL-1.0`, draft, not yet adopted). It is not open source.

- Individuals may use it for private research on investment decisions for themselves and their family members.
- Professional Users and organizations need Nathan Slaughter's prior written permission.
- No one may publish, redistribute, or put its code into a public project without that permission.
- You may share reports Trial Folio generates for you with their notice intact. Portfolio123's terms still govern any Portfolio123 data they contain.

See [LICENSE](LICENSE), the [licensing policy](docs/licensing-policy.md), and [CONTACT.md](CONTACT.md). Third-party components keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Research notice

> Research output only. Backtested and hypothetical results do not represent achievable returns. No financial gain, future performance, suitability, or protection from loss is represented or promised. This report is not personalized investment advice. See the full license and research limitations.

The full notice is in [docs/disclaimers.md](docs/disclaimers.md).

## Documentation

- [docs/README.md](docs/README.md): a map of the specifications.
- [AGENTS.md](AGENTS.md): instructions for coding agents.

## Contact

Licensing and permission requests: Nathan Slaughter, nathan@nathanslaughter.com. See [CONTACT.md](CONTACT.md). Sending a request does not grant permission.

---

> **Not affiliated with Portfolio123.** This is an independent project. It is not an official Portfolio123 project and has not been reviewed by Portfolio123. No endorsement by Portfolio123 is implied.
