# Trial Folio user guide

This guide walks through release 0.1.0's workflows, from setting up to reading a report. Each workflow ends with what to check, so you can confirm it works as described.

It describes behavior; it doesn't define it. Where it and an owning document disagree, such as [contracts.md](contracts.md) or the [release specification](releases/0.1.0-api-execution.md), the owning document wins, and this guide is the one to fix.

**Platforms.** So far, 0.1.0 has been tested on macOS only. The commands below are for macOS and Linux shells.

**Your license.** [LICENSE](../LICENSE) governs every copy of Trial Folio, including one you run from this repository. The README's [License section](../README.md#license) summarizes who may use it.

## 1. Set up

Until 0.1.0 is released as a package, run it from a copy of this repository.

You need:

- `git`
- [`uv`](https://docs.astral.sh/uv/)
- Python 3.12 or later. If you don't have it, `uv python install 3.12` installs it.
- For backtests, a Portfolio123 subscription with the appropriate access, and your API ID and key. The demo needs neither.

Steps:

1. Clone the repository, and install its locked dependencies:

   ```sh
   git clone https://github.com/promptedportfolio/trialfolio.git
   cd trialfolio
   uv sync
   ```

2. Make `trialfolio` run from any folder. Replace the path with the repository's:

   ```sh
   alias trialfolio='uv run --project ~/trialfolio trialfolio'
   ```

   Add the line to your shell's startup file, such as `~/.zshrc`, to keep it. The rest of this guide writes `trialfolio` for this command. If you keep your API key in your system's keychain, [setting your credentials](#6-set-your-credentials) replaces this alias with a function.

3. Set up a workspace: a folder of your own, outside the repository, for your configurations and runs. Run the commands from there.

   ```sh
   trialfolio init ~/research
   cd ~/research
   ```

   It writes three files:

   - `screen.yaml`, a starter configuration
   - `README.md`, the next steps
   - `.gitignore`, which keeps credential files, runs, and reports out of Git, if you keep the folder in a repository

   The folder must be new or empty. Given no folder, `trialfolio init` sets up the current one. It needs no license acknowledgment, and sends nothing.

**Check:**

- `trialfolio --version` prints `trialfolio 0.1.0` from the tag `v0.1.0`. A copy of `main` prints the next release's version, `0.2.0`, which the package takes once that release's specification is complete ([D-26](spec.md#decisions)).
- `trialfolio --help` lists `init`, `run`, `report`, `demo`, and `license`.
- `trialfolio init ~/research` exits 0 without asking you to acknowledge the license. The folder holds exactly `screen.yaml`, `README.md`, and `.gitignore`, with no `logs/` folder.
- Running it again on the same folder fails with `output.not_empty`, exit code 4, and changes nothing.

## 2. Acknowledge the license

`run`, `report`, and `demo` need a one-time acknowledgment of the license and the research notice. `--version`, `--help`, `trialfolio init`, and `trialfolio license` don't.

1. Read them: `trialfolio license`. It prints the license, the full research notice, and whether you've acknowledged them.
2. Acknowledge them, in one of three ways:
   - **At the terminal.** The first time you run `run`, `report`, or `demo`, it shows the concise notice and asks you to type `accept`.
   - **Ahead of time.** `trialfolio license --accept`.
   - **For one command, recording nothing.** Set `TRIALFOLIO_ACCEPT_LICENSE=LicenseRef-NSPRL-1.0/1.0`, which suits scripts.

**Check:**

- Before you acknowledge, `trialfolio demo --out demo/` from a script, or with its input redirected, fails with `license.not_acknowledged`, exit code 2, and writes nothing.
- After `trialfolio license --accept`, the last line of `trialfolio license` says "Acknowledged", with the time and the file it's recorded in. The record holds only the license identifier, the notice version, the time, and how you acknowledged.
- Any value of `TRIALFOLIO_ACCEPT_LICENSE` but the exact one is rejected, even after you've acknowledged. An empty one counts as unset.

## 3. Try the demo

The demo writes a complete example run from invented values. It needs no Portfolio123 subscription or credentials, and sends nothing.

```sh
trialfolio demo --out demo/
```

**Check:**

- It exits 0. Its last lines say the synthetic run was written, that nothing was sent to Portfolio123 and every value is invented, where the report is, the plan hash, and that statistical validation and trading readiness are not assessed.
- `demo/report.html` opens in a browser. Its title starts with "Synthetic example", and it says nothing was sent or charged.
- `demo/` holds the files [a run holds](#8-read-the-results).

## 4. Write a screen configuration

A screen configuration is a YAML file describing one long-only stock screen backtest. Start from your workspace's `screen.yaml`. It has the settings of this example, which Portfolio123 accepted in a live call, with a comment on each key:

```yaml
kind: screen
schema_version: 1.0.0
title: Earnings yield with a liquidity floor           # yours; never sent
purpose: Reference backtest for the 0.1.0 response layout.   # optional; never sent
universe: 'SP500'
rules:
  - 'AvgDailyTot(30) > 1000000'                        # at least one rule
ranking:
  formula: 'EarnYield'
  lower_is_better: false
max_holdings: 25
benchmark: 'SPY'
start_date: 2016-01-01
end_date: 2025-12-31
rebalance_weeks: 4                                     # 1 or 4
transaction_price: open                                # open only
slippage_percent: 0.25                                 # 0.25 means 0.25%
pit_method: complete                                   # complete only
precision: 4                                           # 4 only
```

- **Every key but `purpose` and `data_vendor` is required.** There's no default end date, and no default slippage of zero.
- **Text that Portfolio123 receives goes in single quotes:** the rules, the ranking's formula or name, the universe, and the benchmark. Without quotes it's rejected, because outside quotes YAML reads a space and `#` as the start of a comment, with no error. It would cut `FRank("EarnYield", #Industry) > 50` short, and read `name: Core Combo #2` as `Core Combo`, a different ranking system. Single quotes also keep the double quotes inside a formula as they are. Double quotes and block scalars (`|`) work too.
- **Other values need no quotes:** numbers, dates, `true` and `false`, fixed words such as `screen`, `open`, and `complete`, and the title and purpose, which are never sent. A title or purpose that holds a space followed by `#` still needs quotes, or YAML cuts it short.
- **Comments** run from `#` to the end of the line, outside quotes. They aren't part of the plan, so they don't change its hash, and the run keeps them in its copy of the file.
- **A ranking** is one formula, as above, or an existing ranking system in your account, by name or by ID:

  ```yaml
  ranking:
    name: 'My ranking system'
  ```

  ```yaml
  ranking:
    id: 12345
  ```

  A ranking system, like the universe, can change in your account after the run, and 0.1.0 doesn't save its definition. So the run records it as not snapshotted, and its reproducibility as incomplete. A formula ranking is recorded completely.
- **`data_vendor`** may be left out, or given as `FactSet`. Either way it's recorded as FactSet, an inferred default, and isn't sent.
- **Only verified values are accepted.** Portfolio123 documents other values, such as other rebalance frequencies. 0.1.0 rejects them until a live call verifies them.

[The screen configuration](contracts.md#screen-configuration) gives every key's rules.

**Check:**

- A misspelled key, a missing required key, or an unsupported value fails with `config.invalid`, exit code 3. The message lists every problem, and nothing is sent or created. For example, `rebalance_weeks: 2` gives "`rebalance_weeks` input should be 1 or 4."
- A rule without quotes, such as `- AvgDailyTot(30) > 1000000`, fails the same way, with "`rules[0]` is text Portfolio123 receives, written without quotes." So does `universe: SP500`, naming `universe`.
- Adding or changing a comment doesn't change the plan hash that [the plan](#5-review-the-plan) shows.

## 5. Review the plan

Before anything is sent, Trial Folio builds a plan from the configuration and shows it. Reviewing it needs no credentials, and creates nothing.

```sh
trialfolio run screen.yaml --out runs/first/
```

In a terminal, it shows the full plan and asks you to type `approve`. Type anything else to stop.

The plan shows:

- the request, exactly as it will be sent
- every setting, with the provenance each value will have, marking inferred defaults, settings not snapshotted, commission not modeled, and parameters not sent
- the budget: at most 1 request, 5 credits at Portfolio123's documented cost, and that a request that reaches Portfolio123 may be charged even if it fails
- what's sent to Portfolio123, and what isn't
- the plan hash, `sha256:` and 64 hex digits

**Check:**

- After you stop, it fails with `plan.approval_required`, exit code 2. `runs/first/` doesn't exist, and the message says nothing was sent.
- When its error output isn't a terminal, as in a script, it shows only the plan hash and the budget, never the formulas. When its input isn't a terminal, it doesn't ask. Either way, it fails the same way, with the exact `--approve` option in the message.
- The same configuration gives the same plan hash every time, in any output directory. Changing a setting, the title, or the purpose changes it.

## 6. Set your credentials

Trial Folio reads the API ID and key from two environment variables, `TRIALFOLIO_P123_API_ID` and `TRIALFOLIO_P123_API_KEY`. Portfolio123's website lists both under DataMiner & API. Trial Folio never reads them from a file, and never saves or logs them.

Keep the key out of your shell's history, and out of any plain-text file. Don't put it in a `.env` file in your workspace: Trial Folio doesn't read one, and the file would sit beside the runs and reports you might copy, zip, or share. Choose one of these instead.

**In your system's keychain, entered once.** On macOS:

1. Store the ID and the key in your login keychain. Each command asks for the value twice, at a prompt that doesn't show it:

   ```sh
   security add-generic-password -s trialfolio -a p123-api-id -w
   security add-generic-password -s trialfolio -a p123-api-key -w
   ```

2. In your shell's startup file, such as `~/.zshrc`, replace the `alias trialfolio=...` line from [setting up](#1-set-up) with this function. For each command, it reads both values from the keychain and sets them for that command alone, so your shell doesn't keep them. As before, replace the path with the repository's:

   ```sh
   trialfolio() {
     TRIALFOLIO_P123_API_ID="$(security find-generic-password -s trialfolio -a p123-api-id -w)" \
     TRIALFOLIO_P123_API_KEY="$(security find-generic-password -s trialfolio -a p123-api-key -w)" \
       uv run --project ~/trialfolio trialfolio "$@"
   }
   ```

3. Open a new terminal, so the function replaces the alias.

To change the key, run `security add-generic-password -U -s trialfolio -a p123-api-key -w`: `-U` updates the item. To remove both, run `security delete-generic-password -s trialfolio -a p123-api-id`, and the same with `p123-api-key`.

On Linux, a keyring that serves the Secret Service, such as GNOME Keyring, works the same way through `secret-tool`. `secret-tool store --label='Trial Folio API key' service trialfolio account p123-api-key` stores the key, asking for it, and `secret-tool lookup service trialfolio account p123-api-key` reads it, in place of `security find-generic-password ... -w`. Trial Folio hasn't been tested on Linux yet.

**Through your password manager.** Many password managers have a command-line tool that runs one command with secrets set as environment variables. It reads them from a file of references, which name where each secret is kept and never hold the secret itself. Write references for the two variables in such a file in your workspace, with a name such as `.env` or `.env.local`, which the workspace's `.gitignore` keeps out of Git. Then run each `trialfolio` command through the tool, as its documentation describes. The tool starts the command itself, without your shell's aliases, so give it the command the `trialfolio` alias stands for, with the repository's path, such as `uv run --project ~/trialfolio trialfolio run screen.yaml --out runs/first/`.

**At a prompt, for one shell session.** Type each value at a prompt that doesn't show the key:

```sh
read -r TRIALFOLIO_P123_API_ID
read -rs TRIALFOLIO_P123_API_KEY
export TRIALFOLIO_P123_API_ID TRIALFOLIO_P123_API_KEY
```

They last until you close the terminal. `unset TRIALFOLIO_P123_API_ID TRIALFOLIO_P123_API_KEY` removes them sooner.

Trial Folio sends them only to Portfolio123's API, directly. It ignores proxy settings and `.netrc`, and if `SSLKEYLOGFILE` is set, it warns and ignores it.

**Check:**

- With the keychain, this prints `p123-api-id found` and `p123-api-key found`. It checks that both items are there, without printing either value:

  ```sh
  for item in p123-api-id p123-api-key; do
    security find-generic-password -s trialfolio -a "$item" >/dev/null && echo "$item found"
  done
  ```

  If a line is missing, store that item again, as in the keychain's step 1.
- With the keychain function, `type trialfolio` says it's a shell function, and `[ -z "$TRIALFOLIO_P123_API_KEY" ] && echo unset` prints `unset`: your shell doesn't keep the key.
- No command in your shell's history file set the key by name: `grep -c 'TRIALFOLIO_P123_API_KEY[=]' "$HISTFILE"` prints 0. The brackets keep the check from counting itself. It finds only commands such as `TRIALFOLIO_P123_API_KEY=...`, not a key typed or pasted any other way.
- Without them, an approved plan fails with `provider.auth_failed`, exit code 5. The message names the missing variables, and says nothing was sent and no output was created.

## 7. Run a backtest

A run sends one request, which costs 5 API credits.

1. Run the configuration in a terminal, review the plan, and type `approve`:

   ```sh
   trialfolio run screen.yaml --out runs/first/
   ```

   Or, for a plan you've already reviewed, give its hash:

   ```sh
   trialfolio run screen.yaml --out runs/first/ --approve sha256:<the plan hash>
   ```

   `--out` must name a new or an empty directory. Trial Folio never overwrites anything.
2. Wait. Progress goes to the terminal, including how the attempt ended and whether it may have been charged.

**Check:**

- It exits 0. stdout says "Run completed", where the report is, the plan hash, and that statistical validation and trading readiness are not assessed.
- The attempt line says it succeeded, possibly charged, with its attempt record written.
- An abbreviated or different hash fails with `plan.approval_required` and sends nothing. The full hash, exactly as shown, runs without asking.
- Running into a directory that isn't empty fails with `output.not_empty`, exit code 4, before the plan is shown, and changes nothing in it.

## 8. Read the results

A run's directory holds:

| Path | What it is |
|---|---|
| `report.html` | The report: one self-contained file, with no scripts, that opens offline |
| `normalized/metrics.csv` | 20 rows: the response's coverage, its first date, last date, and number of periods, then the strategy's and the benchmark's metrics, with units and source precision |
| `normalized/settings.csv` | The 23 settings, each with its value, provenance, and flags |
| `manifest.json` | What ran and how, its outcome and counts, its reproducibility, and every file's hash. It's written last, so a run without one is incomplete. |
| `plan.json` | The plan you approved, with the versions of the packages that sent it |
| `configuration.yaml` | Your configuration file, byte for byte |
| `cases/<case>/attempts/<attempt>/` | The attempt's records: `started.json`, `attempt.json`, the request without credentials, and Portfolio123's decoded response |
| `logs/trialfolio.log` | The run's log |

**In the report:**

- The research notice is at the top, with a link to the full notice at the end.
- Its ten sections say what a screen backtest can and can't support. A section the run can't support says so, and why.
- A value missing from the response shows as unavailable, with the reason, never as zero.
- Commission shows as not modeled: the API documents no commission setting, and slippage is the only cost sent.
- If the response covers different dates than you asked for, the report shows both, and `settings.csv` flags the date as `coverage_mismatch`.
- Statistical validation and trading readiness read "Not assessed".
- The closing section carries the Portfolio123 data statement and two outside links: the license and Portfolio123's terms. The license link names the tag of the version that rendered the report, such as `v0.1.0`, so it works only once that version is tagged.

[The flag codes](contracts.md#flag-codes) explain each flag in `settings.csv`.

**Check:**

- The report's values match `normalized/metrics.csv`.
- `settings.csv` has 23 rows: commission is `not_modeled`, `data_vendor` and `risk_stats_period` are flagged `inferred_default`, and five parameters are `not_sent`, with `unknown` provenance.
- The universe, and a ranking by name or ID, are flagged `not_snapshotted`, and the manifest's reproducibility is `incomplete`.
- `attempt.json` gives the outcome, `possibly_charged`, and the cost Portfolio123 reported.
- The log holds no credentials, configuration values, formulas, or results.

## 9. Re-render a report

`trialfolio report` rebuilds a saved run's report offline, from its saved files. It sends nothing, and needs no credentials.

```sh
trialfolio report runs/first/ --out reports/first/
```

**Check:**

- It exits 0, and writes only `reports/first/report.html` and its log. The run's directory isn't changed.
- The new report's values match the original's.
- A directory that isn't a complete run fails with `input.not_a_run`, and one that doesn't exist with `input.not_found`, both with exit code 3, and nothing is written.

## 10. Use it from a script

Add `--json` to any command. stdout then holds exactly one JSON object, on success and on failure, and everything else goes to stderr. The object gives the outcome, the exit code, the IDs, such as the plan hash, the output files, the counts, such as `provider_requests` and the credit `cost`, and the error, if any. Its schema is `schemas/json-summary-1.1.0.schema.json`. Trial Folio 0.1.0 writes version 1.0.0, whose schema, `schemas/json-summary-1.0.0.schema.json`, is kept beside it: 1.1.0 only adds to it.

Approve only a plan you've reviewed. A script can read the hash from a run that wasn't approved, in `ids.plan_hash`, and approve it, but that skips the review the plan exists for.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | The command completed. It says nothing about the strategy. |
| 1 | An unexpected internal error |
| 2 | A usage error, a plan not approved, or the license not acknowledged |
| 3 | An invalid configuration, input, artifact, or environment |
| 4 | An output problem: the directory isn't empty, or a write failed |
| 5 | A Portfolio123 error |
| 130 | Interrupted, for example with Ctrl-C |

**Check:**

- `trialfolio demo --out demo2/ --json` prints one object with `"outcome": "completed"`.
- A plan run without approval, with `--json`, prints one object with `"exit_code": 2`, the plan hash in `ids`, and the error.

## 11. When something goes wrong

Every error message says what failed, why, and what to do next. These are the ones you're most likely to see:

| Code | What happened | What to do |
|---|---|---|
| `config.invalid` | The configuration has a problem; the message lists each one | Fix them. Nothing was sent. |
| `output.not_empty` | `--out`, or the folder given to `trialfolio init`, names a directory that isn't empty | Choose a new or empty directory |
| `plan.approval_required` | The plan wasn't approved, or the hash didn't match | Approve it in a terminal, or give its full hash. Nothing was sent. |
| `environment.unsupported` | The installed `p123api`, `requests`, or `urllib3` isn't the verified version | Run `uv sync` in the repository to restore the locked versions |
| `provider.auth_failed` | The credentials are missing, or Portfolio123 refused them | Check the API ID and key |
| `provider.unavailable` | Portfolio123 couldn't be reached; the request wasn't sent | Try again later |
| `provider.quota_exceeded` | Portfolio123 refused the request for quota or credits | Check your API credits. The request may have been charged. |
| `provider.unsupported_capability` | Portfolio123 rejected a setting; its own message follows | Change the setting. The request may have been charged. |
| `provider.outcome_unknown` | The request may have been sent and charged, but no response was saved, for example after a timeout | Trial Folio never resends it on its own. Running the command again is a new attempt, and may be charged again. |
| `provider.response_invalid` | A response was saved, but didn't have the expected layout | The response stays in the run. Report it, because Portfolio123's response may have changed. |
| `storage.write_failed` | A file couldn't be written durably, for example on macOS or Linux to an exFAT or FAT drive, which lacks hard links | Use another drive. If the request was sent, the attempt record says whether it may have been charged. |
| `command.interrupted` | You pressed Ctrl-C | The message says whether a request may have been sent |
| `internal.unexpected` | A defect in Trial Folio | Report it, with the log the message names |

After a Portfolio123 error, the run's directory still has its report and manifest, which record the failure. After an interrupt, a storage failure, or an internal error, there's no manifest, so the run reads as incomplete. [Errors](contracts.md#errors) lists every code.

**Logs.** Each command with an output directory logs to `logs/trialfolio.log` there. `trialfolio init`, `trialfolio license`, and an internal error before the output directory is claimed log to a per-user directory, which the README's [Your data stays on your machine](../README.md#your-data-stays-on-your-machine) lists, with how to delete it. To see more detail, set `TRIALFOLIO_LOG_LEVEL=DEBUG`. At every level, logs hold no credentials, configuration values, formulas, or results.

**Reporting a problem.** [CONTACT.md](../CONTACT.md) links to a form for bugs and questions.
