# Commands

This page lists the `trialfolio` command's subcommands, their arguments and options, the license acknowledgment they need, and the environment variables Trial Folio reads.

Until Trial Folio is released as a package, you run it from a copy of its repository: as `uv run trialfolio` there, or through the `trialfolio` alias that [your first backtest](../tutorials/first-backtest.md) sets up. This page writes `trialfolio`. The commands are for macOS and Linux shells. Trial Folio has been tested on macOS only.

## Usage

The usage lines and the tables of arguments and options on this page are generated from the command's own help.

<!-- generated: cli-usage -->

```text
trialfolio [-h] [--version] <command> ...
```

| Argument or option | Required | Default | What it is |
|---|---|---|---|
| `-h`, `--help` | No | None | Show this help message and exit |
| `--version` | No | None | Show program's version number and exit |

<!-- end generated: cli-usage -->

**The commands:**

<!-- generated: cli-commands -->

| Command | What it does |
|---|---|
| [`init`](#trialfolio-init) | Set up a workspace: a folder with a starter screen configuration, a README, and a .gitignore. |
| [`run`](#trialfolio-run) | Plan and execute a screen backtest, or an experiment, once its plan is approved. Run an experiment's configuration again into its output directory to resume or revise it. A ranking snapshot configuration reads a ranking system saved in the account into a ranking snapshot. |
| [`report`](#trialfolio-report) | Re-render a saved run's report offline. |
| [`demo`](#trialfolio-demo) | Write a synthetic example run offline, labeled synthetic, with its report. |
| [`review`](#trialfolio-review) | Compare saved runs with a baseline offline. |
| [`license`](#trialfolio-license) | Print the license, the full notice, and whether you've acknowledged them. |

<!-- end generated: cli-commands -->

`trialfolio --help` lists these commands.

- **The license's acknowledgment:** `run`, `report`, `demo`, and `review` need it, and `init` and `license` don't ([the license acknowledgment](#the-license-acknowledgment)).
- **What each sends to Portfolio123:** `run` sends each request of the plan you approve. The other commands send nothing.

**Options of every command:**

<!-- generated: cli-common-options -->

| Argument or option | Required | Default | What it is |
|---|---|---|---|
| `-h`, `--help` | No | None | Show this help message and exit |
| `--json` | No | Off | Write the result to stdout as one JSON summary |

<!-- end generated: cli-common-options -->

Each command's own table, below, lists its other arguments and options.

- **`-h` and `--help`** need no acknowledgment.
- **With `--json`,** the command writes the [JSON summary](json-summary.md).

## `trialfolio --version`

Prints `trialfolio` and its version, and exits. It needs no acknowledgment.

- **A copy of a tag** prints that tag's version, such as `trialfolio 0.3.0` from `v0.3.0`.
- **A copy of `main`** prints the version of the latest release whose specification is complete, which may not be tagged yet. The package takes a release's version once that release's specification is complete ([D-26](https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md#decisions)).

## `trialfolio init`

<!-- generated: cli-command-init -->

```text
trialfolio init [-h] [--json] [dir]
```

| Argument or option | Required | Default | What it is |
|---|---|---|---|
| `dir` | No | `.` | The workspace: absent, or an empty directory; the current directory by default |

<!-- end generated: cli-command-init -->

It writes three files:

| File | What it is |
|---|---|
| `screen.yaml` | A starter [screen configuration](screen-configuration.md), with a comment on each key |
| `README.md` | The next steps |
| `.gitignore` | Keeps credential files, runs, reports, and reviews out of Git, if you keep the folder in a repository, as [outputs that hold Portfolio123 data](outputs.md#outputs-that-hold-portfolio123-data) lists |

- **The folder must be new or empty.** Running it again on the same folder fails with `output.not_empty`, exit code 4, and changes nothing.
- **It needs no license acknowledgment,** and sends nothing. It exits 0.
- **It logs to the per-user log directory,** not the workspace, so the workspace holds exactly the three files, with no `logs/` folder ([logs](errors.md#logs)).
- **No other command needs a workspace.** Trial Folio reads nothing back from the starter files.

## `trialfolio run`

<!-- generated: cli-command-run -->

```text
trialfolio run [-h] --out DIR [--approve PLAN_HASH]
               [--revision-reason TEXT]
               [--repeat CASE_KEY[:ATTEMPT_ID]] [--json]
               config
```

| Argument or option | Required | Default | What it is |
|---|---|---|---|
| `config` | Yes | None | The screen, experiment, or ranking snapshot configuration, a YAML file |
| `--out DIR` | Yes | None | The output directory: absent, or an empty directory, or, for an experiment, its own output directory, to resume or revise it |
| `--approve PLAN_HASH` | No | None | Approve the plan with its full hash, as shown, without asking |
| `--revision-reason TEXT` | No | None | Why the experiment's plan changed: needed, with the revision's approval, when the configuration or the installed versions no longer give the current plan |
| `--repeat CASE_KEY[:ATTEMPT_ID]` | No | None | Send again the request of an experiment's case that may already have been charged, which may be charged again: once for each case, with the attempt ID the plan shows to confirm it, or asked to confirm in a terminal |

<!-- end generated: cli-command-run -->

`config` is a [screen](screen-configuration.md) or an [experiment](experiment-configuration.md) configuration: its `kind` says which. A screen's run sends one request, which costs 5 API credits. An experiment sends one request for each case, at 5 credits each, within its [budget](experiment-configuration.md#the-budget).

### The plan and its approval

- **Before anything is sent,** `run` builds a plan from the configuration, and shows it. Reviewing it needs no credentials, and creates nothing.
- **In a terminal,** it shows the full plan, and asks you to type `approve`. Any other answer stops it, with `plan.approval_required`, exit code 2, and nothing is sent or created.
- **When its error output isn't a terminal,** as in a script, it shows only the plan hash and the budget, never the formulas. **When its input isn't a terminal,** it doesn't ask. Without `--approve`, either way fails with `plan.approval_required`, and the message gives the exact `--approve` option.
- **The plan hash** is `sha256:` and 64 hex digits. The same configuration, with the same versions of Trial Folio, `p123api`, `requests`, and `urllib3`, gives the same plan hash every time, in any output directory. After an upgrade of any of them, the plan needs approving again. An experiment's later plans also depend on the plan they revise ([the plan hash](../explanation/plans-and-approval.md#the-plan-hash)).
- **`--approve` with the full hash,** exactly as shown, runs without asking. An abbreviated or different hash fails with `plan.approval_required`, and sends nothing.
- **For a revision of an experiment's plan,** each of these failures is `plan.changed`, exit code 3, instead: a refused answer, no `--approve` when Trial Folio doesn't ask, and a hash that isn't the revision's. A revision also needs [`--revision-reason`](#-revision-reason), and fails with `plan.changed` without it. [Revise an experiment](../how-to/revise-an-experiment.md) gives the steps.

[Plans and approval](../explanation/plans-and-approval.md) explains what the plan shows, and why.

### `--out`

- **For a screen,** it names a new or an empty directory. Trial Folio never overwrites anything. A directory that isn't empty fails with `output.not_empty`, exit code 4, before the plan is shown, and nothing in it changes.
- **For a new experiment,** it names a new or an empty directory too.
- **For an existing experiment,** it names the experiment's own directory, which holds `experiment.lock`. Running the same configuration into it resumes the experiment, or revises it after you change the configuration. A configuration with another `experiment_id`, or whose baseline has another universe, is another experiment, and fails there with `output.not_empty`.

[Recovering from an interrupt](../how-to/recover-from-an-interrupt.md) and [revising an experiment](../how-to/revise-an-experiment.md) give the steps.

### `--revision-reason`

- **For an experiment only.** Give it, and approve the revision, after you change the configuration, or the installed versions change. Every revision needs one.
- **The reason** is 1 to 2,000 characters, not all whitespace. Another value is a usage error, exit code 2.
- **It's recorded** in the new plan's `experiment.json`, and shown in the report. It's never sent or logged.
- **A reason when there's no revision** fails with `plan.approval_required`, unless it's the reason the current plan recorded, which resumes that plan.

### `--repeat`

- **For an existing experiment's case awaiting a repeat** only: one whose request may have reached Portfolio123, and none of whose attempts succeeded. With a screen, or a new experiment, it fails with `plan.approval_required`.
- **Give it once for each case** you repeat. A case key given twice is a usage error, exit code 2.
- **With the attempt ID,** `--repeat <case-key>:<attempt-id>`, the option is the confirmation, and Trial Folio doesn't ask. With `--approve`, or from a script, a repeat needs it.
- **With the key alone,** in a terminal without `--approve`, it asks you to type `repeat`, once you've approved the plan.
- **The plan display, the message of a run that leaves such a case, the report, and the JSON summary** each give the case's exact option.

[Repeating a case](../how-to/repeat-a-case.md) gives the steps.

### Credentials

- **`run` reads your API ID and key** from `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`, once the plan is approved, when it has a request to send.
- **Without them,** an approved plan fails with `provider.auth_failed`, exit code 5. The message names the missing variables, and says nothing was sent and no output was created.
- **A resumed experiment that sends nothing,** because no case is due and no repeat is to be made, needs no credentials.

[Storing your credentials](../how-to/store-credentials.md) gives ways to set them.

## `trialfolio report`

<!-- generated: cli-command-report -->

```text
trialfolio report [-h] --out DIR [--json] run-dir
```

| Argument or option | Required | Default | What it is |
|---|---|---|---|
| `run-dir` | Yes | None | The saved run's output directory |
| `--out DIR` | Yes | None | The new output directory for the report: absent, or an empty directory |

<!-- end generated: cli-command-report -->

- **It rebuilds the run's report offline,** from its saved files. It sends nothing, and needs no credentials.
- **It writes only `report.html` and its log** into `--out`. The run's directory isn't changed ([a re-rendered report's directory](outputs.md#a-re-rendered-reports-directory)).
- **A directory that isn't a complete run** fails with `input.not_a_run`, and one that doesn't exist with `input.not_found`, both with exit code 3, and nothing is written. An experiment's directory isn't a run.

[Re-rendering a report](../how-to/re-render-a-report.md) gives the steps.

## `trialfolio demo`

<!-- generated: cli-command-demo -->

```text
trialfolio demo [-h] --out DIR [--json]
```

| Argument or option | Required | Default | What it is |
|---|---|---|---|
| `--out DIR` | Yes | None | The new output directory for the synthetic run: absent, or an empty directory |

<!-- end generated: cli-command-demo -->

- **It writes a complete example run** from invented values, with every file [a run holds](outputs.md#a-runs-directory), labeled synthetic.
- **It needs no Portfolio123 subscription or credentials,** and sends nothing.

## `trialfolio review`

<!-- generated: cli-command-review -->

```text
trialfolio review [-h] --out DIR [--json] config
```

| Argument or option | Required | Default | What it is |
|---|---|---|---|
| `config` | Yes | None | The review configuration, a YAML file naming the runs and the baseline |
| `--out DIR` | Yes | None | The new output directory for the review: absent, or an empty directory |

<!-- end generated: cli-command-review -->

`config` is a [review configuration](review-configuration.md).

- **It compares saved runs with a baseline you choose,** offline: runs that `trialfolio run` or `trialfolio demo` wrote. It sends nothing, and needs no credentials, and it doesn't change the runs' directories.
- **It doesn't rank the runs,** or say which strategy is better.
- **A directory that isn't empty** fails with `output.not_empty`, exit code 4, and nothing in it changes.

[Comparing runs](../how-to/compare-runs.md) gives the steps, and [a review's directory](outputs.md#a-reviews-directory) what it writes.

## `trialfolio license`

<!-- generated: cli-command-license -->

```text
trialfolio license [-h] [--accept] [--json]
```

| Argument or option | Required | Default | What it is |
|---|---|---|---|
| `--accept` | No | Off | Record your acknowledgment of LicenseRef-NSPRL-1.1 and notice version 1.0 |

<!-- end generated: cli-command-license -->

- **Without `--accept`,** it prints the license, the full research notice, and, on its last line, whether you've acknowledged them.
- **It needs no acknowledgment,** and sends nothing.

[LICENSE](https://github.com/promptedportfolio/trialfolio/blob/main/LICENSE) governs every copy of Trial Folio, including one you run from its repository.

## The license acknowledgment

`run`, `report`, `demo`, and `review` need a one-time acknowledgment of the license and the research notice. `--version`, `--help`, `trialfolio init`, and `trialfolio license` don't.

- **An acknowledgment covers one license and one notice version:** now `LicenseRef-NSPRL-1.1` and notice version 1.0.
- **A new version of the license asks again.** Release 0.2.1 brings version 1.1, so an acknowledgment of version 1.0, from 0.1.0 or 0.2.0, doesn't cover it.
- **Read them first** with `trialfolio license`.

### Three ways to acknowledge

| Way | How | What it records |
|---|---|---|
| At the terminal | The first time you run `run`, `report`, `demo`, or `review`, when its input and error output are both terminals, it shows the concise notice and asks you to type `accept`. Any other answer stops it, with `license.not_acknowledged`, and it writes nothing. | The record, with the method `interactive` |
| Ahead of time | `trialfolio license --accept` | The record, with the method `command` |
| For one command | Set `TRIALFOLIO_ACCEPT_LICENSE=LicenseRef-NSPRL-1.1/1.0`, which suits scripts | Nothing |

### The record

- **It's one file,** `acknowledgment.json`, in the per-user configuration directory:

  | System | Per-user configuration directory |
  |---|---|
  | macOS | `~/Library/Application Support/trialfolio` |
  | Linux | `~/.config/trialfolio`, or `$XDG_CONFIG_HOME/trialfolio` |
  | Windows | `%APPDATA%\trialfolio` |

  `TRIALFOLIO_CONFIG_DIR` names another.
- **It holds only** the license identifier, the notice version, the time, and how you acknowledged. It's never sent anywhere.
- **After `trialfolio license --accept`,** the last line of `trialfolio license` says "Acknowledged", with the time and the file it's recorded in.
- **When it can't be written,** an acknowledgment at the terminal counts for that command, with a warning, and Trial Folio asks again next time. `trialfolio license --accept` fails with `storage.write_failed`, exit code 4.

### `TRIALFOLIO_ACCEPT_LICENSE`

- **The exact value** is `LicenseRef-NSPRL-1.1/1.0`: the license identifier, `/`, and the notice version.
- **Any other value is rejected,** even after you've acknowledged, and the message gives the exact value.
- **An empty one** counts as unset.
- **It records nothing:** it acknowledges for that one process.

### Without an acknowledgment

Before you acknowledge, `trialfolio demo --out demo/` from a script, or with its input redirected, fails with `license.not_acknowledged`, exit code 2, and writes nothing. The message gives the ways to acknowledge, and the exact value of `TRIALFOLIO_ACCEPT_LICENSE`.

## Environment variables

| Variable | What it does |
|---|---|
| `TRIALFOLIO_ACCEPT_LICENSE` | Set to exactly `LicenseRef-NSPRL-1.1/1.0`, it acknowledges the license and notice for one process, and records nothing ([the license acknowledgment](#trialfolio_accept_license)) |
| `TRIALFOLIO_P123_API_ID` | Your Portfolio123 API ID, which `trialfolio run` needs to send a request |
| `TRIALFOLIO_P123_API_KEY` | Your Portfolio123 API key, which `trialfolio run` needs to send a request |
| `TRIALFOLIO_LOG_LEVEL` | The level the log files record: `DEBUG`, `INFO`, `WARNING`, or `ERROR`. `INFO` by default. Any other value is ignored, with a warning on stderr. |
| `TRIALFOLIO_LOG_DIR` | The per-user log directory, in place of the [default](errors.md#logs) |
| `TRIALFOLIO_CONFIG_DIR` | The per-user configuration directory, which holds the acknowledgment's [record](#the-record), in place of the default |

**Your API ID and key:**

- **Portfolio123's website lists both** under DataMiner & API.
- **Trial Folio reads them only from these two variables.** It never reads them from a file, and never saves or logs them.
- **It sends them only to Portfolio123's API, directly.** No option, configuration key, or environment variable changes where they go.

**What Trial Folio ignores:**

- **Proxy settings,** such as `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, and `NO_PROXY`; `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE`; and `.netrc` and `NETRC`. So it supports no proxy.
- **`SSLKEYLOGFILE`.** If it's set, `trialfolio run` warns, and removes it from its own environment. Your shell keeps the setting.
- **A `.env` file.** Trial Folio doesn't read one.

## Standard output and standard error

- **stdout** carries the command's result: a short summary on success, and nothing on failure. With `--json`, it carries the [JSON summary](json-summary.md), on success and on failure, except after a usage error.
- **A usage error,** an argument the command line's parser rejects, such as a missing `--out`, exits with code 2. The parser reports it on stderr, with no error code, and no JSON summary, even with `--json`.
- **stderr** carries progress, warnings, which start with `Warning:`, and errors, with their full message. It also carries the plan display and the prompts, which are never logged.

## Exit codes

[Errors and exit codes](errors.md#exit-codes) lists them.
