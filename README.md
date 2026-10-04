# Trial Folio

Brought to you by [The Prompted Portfolio](https://promptedportfolio.com).

> **Requires a Portfolio123 subscription.** This project works with the Portfolio123 API, which requires a Portfolio123 subscription with the appropriate access.

Trial Folio is a command-line tool for investors who research strategies in [Portfolio123](https://www.portfolio123.com/). It helps you:

- Run backtests through the Portfolio123 API, with every setting recorded next to its result.
- Compare runs and see exactly which settings differ between them.
- Keep a durable, inspectable record of what you tested, including the tests that failed.

Portfolio123 does the backtesting. Trial Folio plans each request, records exactly what was sent and returned, and compares the results, so you can see whether they support a conclusion.

## Status

**Pre-release. Nothing is installable yet.** Release 0.1.0 is built and has passed its tests, including a live run through the Portfolio123 API. It hasn't been released.

| Capability | Planned release | Status |
|---|---|---|
| Run one screen backtest through the Portfolio123 API and keep the settings with the results | [0.1.0](docs/releases/0.1.0-api-execution.md) | Built and tested; not yet released |
| Compare saved runs, offline, against a baseline | [0.2.0](docs/releases/0.2.0-review.md) | Outlined (Draft) |
| Run a small, planned experiment of screen variants, with safe resume | [0.3.0](docs/releases/0.3.0-experiments.md) | Outlined (Draft) |
| Descriptive return analytics, robustness diagnostics, statistical evaluation, forward tracking | [Roadmap](docs/roadmap.md) | Not specified |

**Supported inputs:** release 0.1.0 runs one long-only stock screen backtest through the Portfolio123 API, described in a YAML file. It accepts only the settings and values that live calls have verified:

- a universe, at least one screening rule, and a benchmark
- a ranking: one formula, or an existing ranking system by its name or ID
- the maximum number of holdings, the start and end dates, and the slippage. Each is required: there's no default end date, and no default slippage of zero.
- rebalancing every week or every 4 weeks, open prices, complete point-in-time data, and results to 4 decimal places
- Portfolio123's standard FactSet data, in US dollars. You may leave the data vendor out.

Anything else is rejected with a clear error before anything is sent. The text Portfolio123 receives goes in quotes: the rules, a ranking formula or name, the universe, and the benchmark, as in `universe: 'SP500'`. So YAML can't read a `#` in it as the start of a comment. [The screen configuration](docs/contracts.md#screen-configuration) gives every setting, with an example. Trial Folio doesn't import results produced elsewhere.

Statistical validation and trading readiness are **not assessed** by any planned release before the statistical evaluation increment.

## Installation

No installation is available yet. When 0.1.0 is released, this section will give the verified installation steps. Releases will be downloaded from [promptedportfolio.com](https://promptedportfolio.com), not from PyPI, and installed with `uv` or `pipx`. Until then, you can run 0.1.0 from a copy of this repository, as the [user guide](docs/user-guide.md#1-set-up) describes.

## Usage

These are release 0.1.0's commands. The [user guide](docs/user-guide.md) walks through each workflow, from setting up to reading the report, with what to check at each step. Put your Portfolio123 API ID and API key in the environment variables `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`, and run a screen configuration. The user guide's [credentials section](docs/user-guide.md#6-set-your-credentials) shows how to keep the key in your system's keychain or password manager, never in a file or your shell's history:

```text
trialfolio run screen.yaml --out runs/baseline/
```

Trial Folio shows you the exact request, its credit cost, and a plan hash, and sends nothing until you approve. Type `approve` at the prompt, or, where no one is at the terminal, give the full hash with `--approve sha256:<hash>`. Then it writes, into a new or empty directory:

- the request (without credentials) and Portfolio123's full response, saved before anything is derived from them
- normalized results tables (CSV)
- a manifest recording what was run and how
- a self-contained HTML report

A missing value is shown as unavailable, never as zero.

The other commands:

```text
trialfolio init research/
trialfolio report runs/baseline/ --out reports/baseline/
trialfolio demo --out demo/
trialfolio license
```

- `init` sets up a workspace: a new or empty folder with a starter screen configuration, a README of next steps, and a `.gitignore` that keeps credential files, runs, and reports out of Git. It sends nothing, and needs no license acknowledgment.
- `report` re-renders a saved run's report, offline.
- `demo` writes a synthetic example run, labeled synthetic, with its report. It needs no Portfolio123 subscription or credentials: it sends nothing, and every value in it is invented.
- `license` prints the license and the full research notice. The first time, `run`, `report`, and `demo` ask you at the terminal to acknowledge them, by typing `accept`. `trialfolio license --accept` acknowledges them ahead of time, and setting `TRIALFOLIO_ACCEPT_LICENSE` to `LicenseRef-NSPRL-1.0/1.0` acknowledges them for one command without recording anything, which suits scripts.

Add `--json` to any command for one JSON summary on stdout. Release 0.2.0 adds `trialfolio review` to compare saved runs.

## Limitations

- **Summary statistics can't show everything.** Trial Folio reports what Portfolio123 returns. It doesn't reconstruct returns, drawdowns, or confidence intervals from summary statistics.
- **Runs cost API credits.** Each backtest uses Portfolio123 API credits: 5 for a screen backtest, as Portfolio123 documents. Trial Folio shows the documented cost and a request budget before sending anything. Whether Portfolio123 charges for a failed request is unknown, so any request that may have reached Portfolio123 is recorded as possibly charged.
- **No proxy.** Trial Folio connects to Portfolio123's API directly. It ignores proxy settings, such as `HTTPS_PROXY`, certificate-bundle settings, such as `REQUESTS_CA_BUNDLE`, and `.netrc`, so nothing in your environment can redirect your credentials. If you can reach the internet only through a proxy, release 0.1.0 can't run your backtests.
- **Reruns can differ.** A Portfolio123 rerun can give different results as its data and engine change, so Trial Folio treats each run as a new attempt.
- **A backtest is a simulation.** See [research limitations](docs/disclaimers.md).

## Your data stays on your machine

- Trial Folio contacts Portfolio123 only for requests you approve.
- Your API ID and key go only to Portfolio123's API, and are never saved or logged. If `SSLKEYLOGFILE` is set, `trialfolio run` ignores it, with a warning, and removes it from its own environment, so the TLS session keys that would let someone decrypt its traffic, your API key included, are never written to a file. Your shell keeps the setting.
- Re-rendering reports, the demo, and (from 0.2.0) reviews run offline.
- Logs stay local and never contain credentials, strategy definitions, configuration values, or results. A command with an output directory writes its log, `trialfolio.log`, to `logs/` inside that directory. `trialfolio init`, commands without an output directory, such as `trialfolio license`, and an internal error before the output directory is ready write to a per-user log directory instead: `~/.local/state/trialfolio/logs` on Linux (or `$XDG_STATE_HOME/trialfolio/logs`), `~/Library/Logs/trialfolio` on macOS, and `%LOCALAPPDATA%\trialfolio\logs` on Windows, unless `TRIALFOLIO_LOG_DIR` names another. A log file is rotated at 1 MB, and the 3 older files are kept. Delete those directories to delete the logs.
- Acknowledging the license writes one file, `acknowledgment.json`, holding only the license identifier, the notice version, when you acknowledged, and how. It's in `~/.config/trialfolio` on Linux (or `$XDG_CONFIG_HOME/trialfolio`), `~/Library/Application Support/trialfolio` on macOS, and `%APPDATA%\trialfolio` on Windows, unless `TRIALFOLIO_CONFIG_DIR` names another.
- Optional LLM features are planned for a later increment. They will be off by default, and remote model providers will process data under their own terms.

## How it's built

Trial Folio is written with the help of AI coding tools, working from the specifications in [docs/](docs/README.md) and the instructions in [AGENTS.md](AGENTS.md). Every change is proposed separately and waits until I've reviewed and approved it, after the automated checks pass. The current versions of Trial Folio use no AI when they run. [How I use AI to build Trial Folio](docs/ai-development.md) explains the details.

## License

Trial Folio is source available under a custom license, the Nathan Slaughter Personal Research License (`LicenseRef-NSPRL-1.0`). It is not open source.

- Individuals may use it for private research on investment decisions for themselves and their family members.
- Professional Users and organizations need Nathan Slaughter's prior written permission.
- No one may publish, redistribute, or put its code into a public project without that permission.
- You may view and fork this repository on GitHub, as GitHub's terms allow. LICENSE section 5.4 sets the limits: a fork carries no right to publish changes.
- You may share reports Trial Folio generates for you with their notice intact.
- Trial Folio's license grants no Portfolio123 rights. Portfolio123's terms govern any Portfolio123 data a report contains, and you're responsible for following them. Sharing such a report publicly may need Portfolio123's consent.

See [LICENSE](LICENSE), the [licensing policy](docs/licensing-policy.md), and [CONTACT.md](CONTACT.md). Third-party components keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Research notice

> Research output only. Backtested and hypothetical results do not represent achievable returns. No financial gain, future performance, suitability, or protection from loss is represented or promised. This report is not personalized investment advice. See the full license and research limitations.

The full notice is in [docs/disclaimers.md](docs/disclaimers.md).

## Documentation

- [docs/user-guide.md](docs/user-guide.md): how to set up and use Trial Folio, workflow by workflow.
- [docs/README.md](docs/README.md): a map of the specifications.
- [AGENTS.md](AGENTS.md): instructions for coding agents.
- [docs/ai-development.md](docs/ai-development.md): how AI is used to build Trial Folio.
- [CONTRIBUTING.md](CONTRIBUTING.md): why outside changes aren't accepted yet, and how to help instead.

## Contact

Bugs, feature requests, questions, and documentation problems: [CONTACT.md](CONTACT.md) links to a form for each. Licensing and permission requests: Nathan Slaughter, git@nathanslaughter.com. Sending a request does not grant permission.

---

> **Not affiliated with Portfolio123.** This is an independent project. It is not an official Portfolio123 project and has not been reviewed by Portfolio123. No endorsement by Portfolio123 is implied.
